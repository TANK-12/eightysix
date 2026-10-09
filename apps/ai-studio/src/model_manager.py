"""Installs, deletes and runs catalog models.

A model is a list of parts (catalog/); each part is one file, stored once in
models/parts/ and shared by file name between models. Files from before the
rebuild in models/sd/catalog/ still count, and LoRA parts live in
models/sd/lora/ because sd-server loads LoRAs by name from one folder.

This module also owns the sd-server child processes for the active image
model (the FastAPI app starts and stops them, which is what lets the UI
switch models without restarting the app). Video models run per job through
the sd CLI instead (video_models.py), and world models through the world
runners (worlds/).
"""

import json
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import config
import engine_flags
from catalog import CATALOG, DEFAULT_MODEL_ID

STATE_PATH = config.MODELS_DIR / "sd" / "active_model.json"
PARTS_DIR = config.PARTS_DIR
DOWNLOAD_DIR = config.LEGACY_MODEL_DIR  # pre-rebuild model folder, still read
LORA_DIR = config.SD_LORA_DIR
SPARE_BYTES = config.DISK_SPARE_BYTES
CHUNK = 1024 * 1024

# Model files outside the catalog that "Delete all models" lists:
# (id, label, folder, ticked by default, note).
EXTRA_MODELS = [
    (
        "lora",
        "LCM speed-up add-on (LCM-LoRA)",
        LORA_DIR,
        True,
        "Downloaded again with the model that needs it.",
    ),
    (
        "upscale",
        "Upscale models (Real-ESRGAN)",
        config.UPSCALE_MODELS_DIR,
        False,
        "Upscale needs these, and AI Studio cannot download them again.",
    ),
    (
        "interp",
        "Smooth-motion model (RIFE)",
        config.RIFE_MODEL_DIR,
        False,
        "Smooth motion needs this, and AI Studio cannot download it again.",
    ),
]

NOT_SET_UP = "Needs the 3D world runtime, not set up yet"


class DownloadError(Exception):
    """A download that cannot start; status is the HTTP code to answer with."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class Cancelled(Exception):
    pass


# ---- the heavy-job guard -------------------------------------------------------
# A video model or a 3D world holds most of the RAM (31 GiB, no swap); loading
# the image sd-server beside one would freeze the laptop. Whatever runs heavy
# jobs registers a probe; while any probe reports a job, nothing starts the
# image servers and other heavy jobs are refused.

VIDEO_BUSY = "A video is being made. Wait for it or cancel it first."
WORLD_BUSY = "A 3D world is running. Stop it first."

_busy_probes = []  # callables -> None or {"kind", "id", "detail"}


class Busy(RuntimeError):
    """A heavy job is running; the message is the plain detail to show."""


def register_busy_probe(probe):
    if probe not in _busy_probes:
        _busy_probes.append(probe)


def busy():
    """The heavy job running now, as {"kind", "id", "detail"}, or None."""
    for probe in list(_busy_probes):
        try:
            got = probe()
        except Exception:
            got = None
        if got:
            return got
    return None


def require_not_busy(except_kind=None):
    """Raise Busy unless no heavy job (other than one of except_kind) runs."""
    got = busy()
    if got and got.get("kind") != except_kind:
        raise Busy(got["detail"])


# ---- where parts live --------------------------------------------------------


def _search_dirs():
    return [PARTS_DIR, DOWNLOAD_DIR, LORA_DIR]


def target_path(part):
    """Where a part is downloaded to."""
    folder = LORA_DIR if part["role"] == "lora" else PARTS_DIR
    return Path(folder) / part["filename"]


def _tmp_path(part):
    dest = target_path(part)
    return dest.with_name(dest.name + ".part")


def part_path(part):
    """The part's file on disk, or None. A symlink to a file counts (a model
    shared from another folder); it is used but never deleted from here."""
    for folder in _search_dirs():
        p = Path(folder) / part["filename"]
        if p.is_file():
            return p
    return None


def is_installed(model_id):
    entry = CATALOG[model_id]
    return all(part_path(p) for p in entry["parts"])


def part_paths(entry):
    """filename -> Path for an installed entry."""
    return {p["filename"]: part_path(p) for p in entry["parts"]}


def _installed_ids():
    return [mid for mid in CATALOG if is_installed(mid)]


def _filenames_used_by(model_ids):
    return {p["filename"] for mid in model_ids for p in CATALOG[mid]["parts"]}


# ---- which model is active ---------------------------------------------------


def _state():
    if STATE_PATH.is_file():
        try:
            data = json.loads(STATE_PATH.read_text())
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
    return {}


def _save_state(data):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data))


def _kind(model_id):
    return CATALOG[model_id].get("kind", "image")


def get_active_id():
    """The active image model (the one sd-server runs), or None."""
    saved = _state().get("active")
    if saved in CATALOG and _kind(saved) == "image" and is_installed(saved):
        return saved
    if DEFAULT_MODEL_ID in CATALOG and is_installed(DEFAULT_MODEL_ID):
        return DEFAULT_MODEL_ID
    return None


def set_active_id(model_id):
    data = _state()
    data["active"] = model_id
    _save_state(data)


def get_active_video_id():
    saved = _state().get("active_video")
    if saved in CATALOG and _kind(saved) == "video" and is_installed(saved):
        return saved
    return next((m for m in _installed_ids() if _kind(m) == "video"), None)


def set_active_video_id(model_id):
    data = _state()
    data["active_video"] = model_id
    _save_state(data)


def get_active_entry():
    active = get_active_id()
    return CATALOG[active] if active else None


def run_settings(entry):
    """An entry's generation defaults, in the names the generate routes use.
    A dict already in those names (the pre-rebuild flat entry shape) passes
    through, so older callers and test stubs keep working."""
    s = entry.get("settings", entry)
    return {
        "steps": s.get("steps", 20),
        "cfg_scale": s.get("cfg_scale", 7.0),
        "sampler": s.get("sampler", "euler"),
        "use_lcm": bool(s.get("use_lcm", False)),
        "default_width": s.get(
            "width", s.get("default_width", config.DEFAULT_BASE_SIZE)
        ),
        "default_height": s.get(
            "height", s.get("default_height", config.DEFAULT_BASE_SIZE)
        ),
    }


# ---- cards, quotes -----------------------------------------------------------


def _world_status(entry):
    try:
        import worlds  # pyright: ignore[reportMissingImports]

        can, note = worlds.runner_status(entry)
        return bool(can), str(note or "")
    except Exception:
        return False, NOT_SET_UP


def run_status(entry):
    """(can_run, plain note) for a card."""
    if any(p.get("gated") for p in entry["parts"]) and not _hf_token():
        return False, "Needs a Hugging Face sign-in to download, not set up yet"
    engine = entry.get("engine", "sd")
    if engine.startswith("world:"):
        return _world_status(entry)
    if not engine_flags.build_available(entry):
        return False, "Needs an engine update"
    return True, ""


def _hf_token():
    import os

    return os.environ.get("HF_TOKEN") or None


def free_bytes():
    folder = Path(config.MODELS_DIR)
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    return shutil.disk_usage(folder).free


def total_bytes(entry):
    return sum(p["size_bytes"] for p in entry["parts"])


def _partial_bytes(part):
    tmp = _tmp_path(part)
    if tmp.is_file():
        return min(tmp.stat().st_size, part["size_bytes"])
    return 0


def quote(model_id):
    """What downloading this model costs: total size, what is still missing
    (parts not on disk, minus bytes already in .part files), and whether that
    fits with SPARE_BYTES left over."""
    entry = CATALOG[model_id]
    needed = sum(
        p["size_bytes"] - _partial_bytes(p) for p in entry["parts"] if not part_path(p)
    )
    # Space other running downloads are about to take is not free.
    with _jobs_lock:
        reserved = sum(
            max(0, j.total_bytes - j.done_bytes)
            for mid, j in _jobs.items()
            if mid != model_id and j.state == "running"
        )
    free = max(0, free_bytes() - reserved)
    fits = free - needed >= SPARE_BYTES
    if needed == 0:
        message = "Already downloaded."
    elif fits:
        message = f"Needs {_human(needed)}; {_human(free - needed)} stays free."
    else:
        message = (
            f"Needs {_human(needed)} but only {_human(free)} is free, and "
            f"{_human(SPARE_BYTES)} has to stay free. Delete something first."
        )
    return {
        "total_bytes": total_bytes(entry),
        "needed_bytes": needed,
        "free_bytes": free,
        "fits": fits,
        "message": message,
    }


def _human(n):
    gb = n / 1024**3
    return f"{gb:.1f} GB" if gb >= 1 else f"{n / 1024**2:.0f} MB"


def card(model_id):
    entry = CATALOG[model_id]
    can_run, note = run_status(entry)
    kind = entry.get("kind", "image")
    active = (
        model_id == get_active_id()
        if kind == "image"
        else model_id == get_active_video_id() if kind == "video" else False
    )
    rs = run_settings(entry)
    return {
        "id": model_id,
        "kind": kind,
        "label": entry["label"],
        "blurb": entry["blurb"],
        "description": entry["blurb"],  # the pre-rebuild page reads this name
        "tier": entry["tier"],
        "installed": is_installed(model_id),
        "active": active,
        "can_run": can_run,
        "run_note": note,
        "download": download_state(model_id),
        "total_bytes": total_bytes(entry),
        "steps": rs["steps"],
        "cfg_scale": rs["cfg_scale"],
        "default_width": rs["default_width"],
        "default_height": rs["default_height"],
    }


def catalog_status():
    return [card(mid) for mid in CATALOG]


def models_payload():
    return {
        "models": catalog_status(),
        "disk": {"free_bytes": free_bytes()},
        "busy": busy(),
    }


# ---- downloads ---------------------------------------------------------------


class DownloadJob:
    def __init__(self, model_id, parts):
        self.model_id = model_id
        self.parts = parts
        self.state = "running"
        self.total_bytes = sum(p["size_bytes"] for p in parts)
        self.started_with = {p["filename"]: _partial_bytes(p) for p in parts}
        self.done_bytes = sum(self.started_with.values())
        self.message = "Starting"
        self.cancel = threading.Event()
        self.thread: threading.Thread | None = None

    def snapshot(self):
        return {
            "state": self.state,
            "done_bytes": self.done_bytes,
            "total_bytes": self.total_bytes,
            "message": self.message,
        }


_jobs = {}  # model_id -> DownloadJob (running, failed or cancelled)
_jobs_lock = threading.Lock()
_file_locks = {}  # filename -> Lock, so two models never write one .part at once


def download_state(model_id):
    with _jobs_lock:
        job = _jobs.get(model_id)
        return job.snapshot() if job else None


def _file_lock(filename):
    with _jobs_lock:
        return _file_locks.setdefault(filename, threading.Lock())


class _Redirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but never carry the sign-in token to another host
    (Hugging Face sends file downloads on to its CDN)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            old_host = urllib.parse.urlsplit(req.full_url).hostname
            if urllib.parse.urlsplit(newurl).hostname != old_host:
                new.headers.pop("Authorization", None)
                new.unredirected_hdrs.pop("Authorization", None)
        return new


_opener = urllib.request.build_opener(_Redirect)


def _request(part, start):
    headers = {"User-Agent": "ai-studio"}
    if start:
        headers["Range"] = f"bytes={start}-"
    token = _hf_token()
    if token and part["url"].startswith("https://huggingface.co/"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(part["url"], headers=headers)


def _fetch(part, job):
    """Download one part into its .part file, resuming with a Range request,
    then check its size and move it into place."""
    dest = target_path(part)
    tmp = _tmp_path(part)
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = part["size_bytes"]
    have = tmp.stat().st_size if tmp.is_file() else 0
    if have > size:
        tmp.unlink()
        job.done_bytes -= size
        have = 0
    if have < size:
        try:
            resp = _opener.open(_request(part, have), timeout=60)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(
                    f"{part['filename']}: the site refused the download "
                    "(it may need a Hugging Face sign-in)"
                )
            raise RuntimeError(f"{part['filename']}: download failed ({e.code})")
        with resp:
            if have and resp.status != 206:
                job.done_bytes -= have  # server ignored Range: start over
                have = 0
            with open(tmp, "ab" if have else "wb") as f:
                while True:
                    if job.cancel.is_set():
                        raise Cancelled()
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    have += len(chunk)
                    job.done_bytes += len(chunk)
                    if have > size:
                        break
    if have != size:
        if have > size:
            tmp.unlink()
        raise RuntimeError(
            f"{part['filename']}: got {have} bytes, expected {size}; try again"
        )
    tmp.replace(dest)


def _run_download(job):
    try:
        for part in job.parts:
            lock = _file_lock(part["filename"])
            while not lock.acquire(timeout=0.5):
                if job.cancel.is_set():
                    raise Cancelled()
            try:
                if part_path(part):
                    # another model's download just finished it
                    job.done_bytes += part["size_bytes"] - job.started_with.get(
                        part["filename"], 0
                    )
                    continue
                job.message = f"Downloading {part['role']} file"
                _fetch(part, job)
            finally:
                lock.release()
        missing = [p for p in CATALOG[job.model_id]["parts"] if not part_path(p)]
        if missing:
            # e.g. a shared part deleted by another model's Delete meanwhile
            job.state = "failed"
            job.message = "A file went missing, press Download again."
            return
        with _jobs_lock:
            _jobs.pop(job.model_id, None)
        _activate_if_none(job.model_id)
    except Cancelled:
        job.state = "cancelled"
        job.message = "Cancelled. Download again to carry on where it stopped."
    except Exception as e:
        job.state = "failed"
        job.message = str(e) or e.__class__.__name__


def _activate_if_none(model_id):
    kind = _kind(model_id)
    if kind == "image" and get_active_id() is None:
        set_active_id(model_id)
    elif kind == "video" and _state().get("active_video") is None:
        set_active_video_id(model_id)


def start_download(model_id):
    """Start downloading every missing part. Returns the job snapshot, or None
    when the model is already installed. Raises DownloadError (403 sign-in
    needed, 409 already running, 507 not enough space)."""
    entry = CATALOG[model_id]
    if is_installed(model_id):
        return None
    if any(p.get("gated") for p in entry["parts"]) and not _hf_token():
        raise DownloadError(
            403, "This model needs a Hugging Face sign-in to download, not set up yet."
        )
    with _jobs_lock:
        old = _jobs.get(model_id)
        if old and old.state == "running":
            raise DownloadError(409, "This model is already downloading.")
    q = quote(model_id)
    if not q["fits"]:
        raise DownloadError(507, q["message"])
    job = DownloadJob(model_id, [p for p in entry["parts"] if not part_path(p)])
    with _jobs_lock:
        _jobs[model_id] = job
    thread = threading.Thread(target=_run_download, args=(job,), daemon=True)
    job.thread = thread
    thread.start()
    return job.snapshot()


def download_model(model_id):
    """Pre-rebuild name: start the download and return its thread."""
    start_download(model_id)
    with _jobs_lock:
        job = _jobs.get(model_id)
    return job.thread if job else None


def cancel_download(model_id, wait=5.0):
    """Stop a running download, keeping its .part files for a resume.
    Returns True if one was running."""
    with _jobs_lock:
        job = _jobs.get(model_id)
    if not job or job.state != "running":
        return False
    job.cancel.set()
    if job.thread:
        job.thread.join(timeout=wait)
    return True


# ---- deleting ----------------------------------------------------------------


def _switch_after_losing_active(kept_ids):
    images = [m for m in kept_ids if _kind(m) == "image"]
    if not images:
        set_active_id(None)
    elif busy():
        set_active_id(images[0])  # servers stay down; they start after the job
    else:
        servers.switch_to(images[0])


def _downloading_model_ids(exclude=()):
    with _jobs_lock:
        return [
            mid
            for mid, job in _jobs.items()
            if mid not in exclude and job.state == "running"
        ]


def delete_model(model_id):
    """Delete a model's parts that no other installed model uses, and its
    unfinished .part files. Deleting the active image model stops its
    sd-servers first, then switches to another installed image model, or
    leaves none active. Returns the bytes freed."""
    entry = CATALOG[model_id]
    was_active = model_id == get_active_id()
    was_video = _state().get("active_video") == model_id
    cancel_download(model_id)
    if was_active:
        servers.stop()
    others = [m for m in _installed_ids() if m != model_id]
    # Parts of models still downloading are kept too: they may already have
    # some of their shared files.
    keep = _filenames_used_by(others + _downloading_model_ids(exclude={model_id}))
    downloading_now = _filenames_being_downloaded(exclude=model_id)
    freed = 0
    for part in entry["parts"]:
        if part["filename"] in keep:
            continue
        path = part_path(part)
        if path and not path.is_symlink():
            freed += path.stat().st_size
            path.unlink()
        tmp = _tmp_path(part)
        if tmp.is_file() and part["filename"] not in downloading_now:
            freed += tmp.stat().st_size
            tmp.unlink()
    with _jobs_lock:
        _jobs.pop(model_id, None)
    if was_active:
        _switch_after_losing_active(_installed_ids())
    if was_video:
        set_active_video_id(None)
    return freed


def _filenames_being_downloaded(exclude=None):
    with _jobs_lock:
        return {
            p["filename"]
            for mid, job in _jobs.items()
            if mid != exclude and job.state == "running"
            for p in job.parts
        }


def _files_in(folder):
    """Regular files under folder. Symlinks are skipped: a linked file belongs
    to another app or a shared Forge folder, and is never deleted from here."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and not p.is_symlink())


def _size(path):
    try:
        return path.stat().st_size
    except OSError:
        return None  # vanished meanwhile (a download finished or was deleted)


def _item(item_id, label, files, default, note="", active=False):
    sizes = [(p, _size(p)) for p in files]
    sizes = [(p, n) for p, n in sizes if n is not None]
    return {
        "id": item_id,
        "label": label,
        "files": [str(p) for p, _ in sizes],
        "bytes": sum(n for _, n in sizes),
        "default": default,
        "note": note,
        "active": active,
    }


def delete_all_plan():
    """What "Delete all models" offers, one item per installed model plus the
    leftover files and tool folders. Everything listed is inside AI Studio's
    own models folder; a model whose main file is a link to elsewhere is not
    listed, and Jan's models and other apps' files are never on it."""
    active = get_active_id()
    items = []
    owned = {
        Path(folder) / p["filename"]
        for e in CATALOG.values()
        for p in e["parts"]
        for folder in _search_dirs()
    }
    for mid, entry in CATALOG.items():
        if not entry["parts"] or not is_installed(mid):
            continue
        main = part_path(entry["parts"][0])
        if main is None or main.is_symlink():
            continue  # a model shared from elsewhere
        files = []
        for p in entry["parts"]:
            path = part_path(p)
            if path and not path.is_symlink() and path not in files:
                files.append(path)
        items.append(
            _item(f"model:{mid}", entry["label"], files, True, active=mid == active)
        )
    downloading = {
        _tmp_path(p).name
        for mid in _downloading_model_ids()
        for p in CATALOG[mid]["parts"]
    }
    other = [
        p
        for folder in (PARTS_DIR, DOWNLOAD_DIR)
        for p in _files_in(folder)
        if p not in owned and p.name not in downloading
    ]
    if other:
        items.append(
            _item(
                "other",
                "Other files in the model folder",
                other,
                True,
                "Unfinished downloads or models no longer in the list.",
            )
        )
    for item_id, label, folder, default, note in EXTRA_MODELS:
        files = _files_in(folder)
        if files:
            items.append(_item(item_id, label, files, default, note))
    return items


def delete_all(ids):
    """Delete the plan items named in ids; ids not on the plan are ignored.

    A part still used by a model that stays is kept. If the active model goes,
    its sd-servers stop and the first image model left takes over, or none.
    """
    wanted = set(ids)
    chosen = [i for i in delete_all_plan() if i["id"] in wanted]
    gone = {i["id"].split(":", 1)[1] for i in chosen if i["id"].startswith("model:")}
    for mid in gone:
        cancel_download(mid)
    staying = [m for m in _installed_ids() if m not in gone]
    kept = {
        str(part_path(p))
        for mid in staying + _downloading_model_ids(exclude=gone)
        for p in CATALOG[mid]["parts"]
        if part_path(p)
    }
    active = get_active_id()
    if active in gone:
        servers.stop()
    freed = 0
    done = set()
    for item in chosen:
        for name in item["files"]:
            p = Path(name)
            if name in kept or name in done or p.is_symlink() or not p.is_file():
                continue
            done.add(name)
            freed += p.stat().st_size
            p.unlink()
    with _jobs_lock:
        for mid in gone:
            _jobs.pop(mid, None)
    if active in gone:
        _switch_after_losing_active(staying)
    if _state().get("active_video") in gone:
        set_active_video_id(None)
    return {"deleted": [i["id"] for i in chosen], "freed_bytes": freed}


# ---- sd-server processes -----------------------------------------------------


def ensure_running():
    """Start the sd-servers for the active model if they run another or none,
    e.g. after every model was deleted and one was downloaded again, or after
    a video job stopped them to free memory, or after sd-server crashed.
    Raises Busy while a video or world job holds the memory."""
    active = get_active_id()
    if active and (servers.active_id != active or not servers.alive()):
        require_not_busy()
        servers.switch_to(active)


class ServerManager:
    """Runs sd-server on the iGPU for the active image model, plus a second
    one on CPU for the small models that opt in (engine_flags.wants_cpu_helper).
    """

    def __init__(self):
        self.gpu_proc = None
        self.cpu_proc = None
        self.active_id = None
        self._lock = threading.RLock()

    def alive(self):
        return self.gpu_proc is not None and self.gpu_proc.poll() is None

    @property
    def has_cpu(self):
        return self.cpu_proc is not None and self.cpu_proc.poll() is None

    def _launch(self, entry, port, backend):
        cmd = engine_flags.server_cmd(entry, part_paths(entry), port, backend, LORA_DIR)
        log_path = (
            config.OUTPUTS_DIR
            / f"sd-server-{'cpu' if backend.startswith('diffusion=cpu') else 'gpu'}.log"
        )
        log = open(log_path, "ab")
        return subprocess.Popen(
            cmd,
            cwd=config.ROOT,
            env=engine_flags.engine_env(entry),
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    def start(self, model_id=None):
        with self._lock:
            self._start(model_id)

    def _start(self, model_id=None):
        require_not_busy()
        model_id = model_id or get_active_id()
        if model_id is None or not is_installed(model_id):
            raise RuntimeError("no installed model to start sd-server with")
        entry = CATALOG[model_id]
        can, note = run_status(entry)
        if not can:
            raise RuntimeError(note)
        self.gpu_proc = self._launch(
            entry, config.GPU_SERVER_PORT, engine_flags.GPU_BACKEND
        )
        if engine_flags.wants_cpu_helper(entry):
            self.cpu_proc = self._launch(
                entry, config.CPU_SERVER_PORT, engine_flags.CPU_BACKEND
            )
        self.active_id = model_id
        self._wait_ready()

    def _wait_ready(self, timeout=300):
        urls = [f"{config.GPU_SERVER_URL}/sdapi/v1/samplers"]
        if self.cpu_proc:
            urls.append(f"{config.CPU_SERVER_URL}/sdapi/v1/samplers")
        for url in urls:
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    urllib.request.urlopen(url, timeout=2)
                    break
                except Exception:
                    if self.gpu_proc and self.gpu_proc.poll() is not None:
                        self.active_id = None  # it exited; the log says why
                        return
                    time.sleep(0.5)

    def stop(self):
        with self._lock:
            for proc in (self.gpu_proc, self.cpu_proc):
                if proc and proc.poll() is None:
                    proc.terminate()
            for proc in (self.gpu_proc, self.cpu_proc):
                if proc:
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            self.gpu_proc = None
            self.cpu_proc = None
            self.active_id = None

    def switch_to(self, model_id):
        """Run model_id instead. Raises Busy (and changes nothing) while a
        video or world job holds the memory."""
        with self._lock:
            require_not_busy()
            self.stop()
            set_active_id(model_id)
            self._start(model_id)


servers = ServerManager()

"""
OpenAI-compatible client for Jan's local llama.cpp server, with:

- streaming token feed (on_delta callback)
- a HARD kill: the streaming loop checks a KillSwitch every line and closes the
  socket immediately, so "stop" actually stops within a fraction of a second.
- "thinking" handling: Qwen3 / reasoning models on llama.cpp stream their chain
  of thought as `reasoning_content` and, under a token cap, can spend the whole
  budget thinking and return NO prose. We disable thinking via
  chat_template_kwargs, keep the reasoning separately, and fall back / retry
  when a model ignores the switch.
- tokens/sec + token-count reporting
- friendly, specific errors.

Concurrency / memory safety
---------------------------
Every request to Jan in this process goes through ONE re-entrant gate
(`_JAN_GATE`), so there is never more than a single model request in flight.
Before this, two worker threads — a chapter generation plus, say, a PDF style
analysis kicked off from the References tab — could hit Jan at the same moment.
Jan's llama.cpp router (`--models-max 2`) would then hold two multi-GB models
resident at once and the laptop ran out of RAM and froze. The gate + the RAM
guard below are the fix.
"""

import json
import time
import threading

import requests


# --------------------------------------------------------------------------
# Global Jan access gate + published busy/idle state (for the GUI indicator)
# --------------------------------------------------------------------------
_JAN_GATE = threading.RLock()
_STATE_LOCK = threading.Lock()
_STATE = {"busy": False, "label": "", "since": 0.0, "last_ok": 0.0, "queue": 0}
_STATE_CB = []


def set_state_callback(fn):
    """GUI hook: fn(state_dict) is invoked whenever Jan's busy state changes."""
    if fn not in _STATE_CB:
        _STATE_CB.append(fn)


def jan_state():
    with _STATE_LOCK:
        return dict(_STATE)


def jan_busy():
    with _STATE_LOCK:
        return _STATE["busy"]


def _publish():
    with _STATE_LOCK:
        snap = dict(_STATE)
    for fn in list(_STATE_CB):
        try:
            fn(snap)
        except Exception:
            pass


class _Gate:
    """Hold the global Jan gate for the duration of one request and publish the
    busy state. Re-entrant: complete()'s own retry recursion re-enters freely,
    only the outermost holder owns the public 'busy' flag."""

    def __init__(self, label):
        self.label = label
        self.owner = False

    def __enter__(self):
        with _STATE_LOCK:
            _STATE["queue"] += 1
        _publish()
        _JAN_GATE.acquire()
        with _STATE_LOCK:
            _STATE["queue"] = max(0, _STATE["queue"] - 1)
            if not _STATE["busy"]:
                self.owner = True
                _STATE["busy"] = True
                _STATE["label"] = self.label
                _STATE["since"] = time.time()
        if self.owner:
            _publish()
        return self

    def __exit__(self, *exc):
        if self.owner:
            with _STATE_LOCK:
                _STATE["busy"] = False
                _STATE["label"] = ""
                _STATE["last_ok"] = time.time()
            _publish()
        _JAN_GATE.release()


# --------------------------------------------------------------------------
# RAM guard
# --------------------------------------------------------------------------
def ram_status():
    """Current system memory picture. `available_gb` is None if psutil is absent."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {"available_gb": vm.available / 2 ** 30,
                "total_gb": vm.total / 2 ** 30,
                "used_gb": (vm.total - vm.available) / 2 ** 30,
                "percent": vm.percent, "ok": True}
    except Exception:
        return {"available_gb": None, "total_gb": None, "used_gb": None,
                "percent": None, "ok": False}


def ram_is_low(min_free_gb):
    s = ram_status()
    if s["available_gb"] is None:
        return False, s
    return s["available_gb"] < float(min_free_gb), s


def free_jan_memory(base_url, keep_model=None, timeout=6):
    """Best-effort: ask Jan to drop idle models. A no-op (returns False) on Jan
    builds that don't expose an unload route — the llama.cpp router already
    LRU-evicts past --models-max, so this is only a nudge, never load-bearing."""
    base = (base_url or "").rstrip("/")
    tried = []
    candidates = [
        ("post", f"{base}/models/stop", {"model": keep_model or ""}),
        ("post", f"{base}/models/unload", {}),
        ("delete", f"{base}/models", {}),
    ]
    for method, url, payload in candidates:
        try:
            r = getattr(requests, method)(url, json=payload, timeout=timeout)
            tried.append(f"{url} -> {r.status_code}")
            if r.status_code < 300:
                return True, tried
        except Exception as e:
            tried.append(f"{url} -> {str(e)[:40]}")
    return False, tried


class KillSwitch:
    def __init__(self):
        self._soft = threading.Event()
        self._hard = threading.Event()
        self.keep_partial = True

    def request_soft(self):
        self._soft.set()

    def request_hard(self, keep_partial=True):
        self.keep_partial = keep_partial
        self._hard.set()
        self._soft.set()

    def reset(self):
        self._soft.clear()
        self._hard.clear()
        self.keep_partial = True

    @property
    def soft(self):
        return self._soft.is_set()

    @property
    def hard(self):
        return self._hard.is_set()

    @property
    def any(self):
        return self._soft.is_set() or self._hard.is_set()


class JanError(RuntimeError):
    pass


class Completion:
    def __init__(self, text, finish_reason, tokens, elapsed, aborted,
                 reasoning="", thinking_leaked=False):
        self.text = text
        self.finish_reason = finish_reason        # stop | length | abort | error
        self.tokens = tokens
        self.elapsed = max(elapsed, 1e-6)
        self.aborted = aborted
        self.reasoning = reasoning
        # True when the model spent its budget "thinking" and returned no prose.
        self.thinking_leaked = thinking_leaked

    @property
    def tps(self):
        return self.tokens / self.elapsed

    @property
    def hit_length_cap(self):
        return self.finish_reason == "length"


# chat_template_kwargs that turn off <think> for the templates that support it.
_NO_THINK_KW = {"enable_thinking": False, "thinking": False}


class JanClient:
    def __init__(self, base_url, timeout=900):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        # models proven to reject chat_template_kwargs -> stop sending it to them
        self._no_kwargs = set()
        self._models_cache = []

    # ---------------- model discovery ----------------
    def list_models(self):
        # Don't block the UI's periodic refresh behind a running generation:
        # if the gate is held, hand back the last known list.
        if not _JAN_GATE.acquire(timeout=0.4):
            return list(self._models_cache)
        try:
            r = self._session.get(f"{self.base_url}/models", timeout=8)
            r.raise_for_status()
            got = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
            if got:
                self._models_cache = got
            with _STATE_LOCK:
                _STATE["last_ok"] = time.time()
            return got
        except Exception:
            return list(self._models_cache)
        finally:
            _JAN_GATE.release()

    def ping(self):
        # Mid-generation the gate is held and Jan is provably up — say so rather
        # than flapping the connection dot to "offline".
        if not _JAN_GATE.acquire(timeout=0.4):
            return (time.time() - jan_state()["last_ok"]) < 180
        try:
            ok = self._session.get(f"{self.base_url}/models", timeout=5).status_code == 200
            if ok:
                with _STATE_LOCK:
                    _STATE["last_ok"] = time.time()
            return ok
        except Exception:
            return False
        finally:
            _JAN_GATE.release()

    # ---------------- payload ----------------
    def _payload(self, model, system, user, max_tokens, temperature, extra, no_think):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})
        p = {
            "model": model,
            "messages": msgs,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "stream": True,
        }
        if no_think and model not in self._no_kwargs:
            p["chat_template_kwargs"] = dict(_NO_THINK_KW)
        if extra:
            for k, v in extra.items():
                if k == "chat_template_kwargs" and isinstance(v, dict) and "chat_template_kwargs" in p:
                    p["chat_template_kwargs"].update(v)
                else:
                    p[k] = v
        return p

    # ---------------- generation ----------------
    def complete(self, model, system, user, max_tokens=1024, temperature=0.7,
                 kill=None, on_delta=None, extra=None, no_think=True, _retry=0,
                 label="generating"):
        # One request at a time, process-wide. Re-entrant for the retry recursion.
        with _Gate(label):
            return self._complete_locked(model, system, user, max_tokens, temperature,
                                         kill, on_delta, extra, no_think, _retry, label)

    def _complete_locked(self, model, system, user, max_tokens, temperature,
                         kill, on_delta, extra, no_think, _retry, label):
        payload = self._payload(model, system, user, max_tokens, temperature, extra, no_think)
        started = time.time()
        parts, reasoning_parts = [], []
        finish_reason = "stop"
        aborted = False
        approx_tokens = 0

        try:
            resp = self._session.post(f"{self.base_url}/chat/completions",
                                      json=payload, stream=True, timeout=self.timeout)
        except requests.exceptions.ConnectionError as e:
            raise JanError(
                f"Can't reach Jan at {self.base_url}. Open Jan and make sure the "
                "Local API Server is running (Settings -> Local API Server).") from e
        except requests.exceptions.Timeout as e:
            raise JanError("The request to Jan timed out before it started.") from e

        if resp.status_code == 404:
            resp.close()
            raise JanError(
                f"Jan returned 404 for model '{model}'. The id must match Jan exactly; "
                "open the model in Jan once so it's registered, or pick another.")
        if resp.status_code >= 400:
            body = ""
            try:
                body = resp.text[:400]
            except Exception:
                pass
            resp.close()
            # Some templates reject chat_template_kwargs -> retry once without it.
            if _retry == 0 and "chat_template_kwargs" in payload:
                self._no_kwargs.add(model)
                return self.complete(model, system, user, max_tokens, temperature,
                                     kill, on_delta, extra, no_think=False, _retry=1,
                                     label=label)
            raise JanError(f"Jan error {resp.status_code}: {body}")

        try:
            for chunk in self._iter_sse(resp, kill):
                if kill is not None and kill.hard:
                    aborted = True
                    finish_reason = "abort"
                    break
                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece is None and isinstance(choice.get("message"), dict):
                    piece = choice["message"].get("content")
                rpiece = delta.get("reasoning_content") or delta.get("reasoning")
                if rpiece:
                    reasoning_parts.append(rpiece)
                if piece:
                    parts.append(piece)
                    approx_tokens += max(1, len(piece) // 4)
                    if on_delta:
                        try:
                            on_delta(piece)
                        except Exception:
                            pass
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
        except requests.exceptions.ChunkedEncodingError:
            aborted = aborted or (kill is not None and kill.hard)
        except Exception as e:
            if not (kill is not None and kill.hard):
                resp.close()
                raise JanError(f"Stream failed: {e}") from e
            aborted = True
        finally:
            resp.close()

        text = "".join(parts).strip()
        reasoning = "".join(reasoning_parts).strip()
        elapsed = time.time() - started

        # The model thought instead of answering and hit the cap with no prose.
        thinking_leaked = (not text and bool(reasoning)
                           and finish_reason in ("length", "stop") and not aborted)

        if thinking_leaked and _retry < 2:
            # Retry: force the no-think template kwarg AND prepend /no_think, and
            # give it more room so thinking (if it still happens) doesn't eat it all.
            self._no_kwargs.discard(model)
            bump = min(int(max_tokens * 1.5) + 512, 32000)
            return self.complete(model, system, "/no_think\n" + user, bump, temperature,
                                 kill, on_delta, extra, no_think=True, _retry=_retry + 1,
                                 label=label)

        if not text and not aborted and not reasoning:
            # server didn't stream at all -> one blocking attempt
            text, finish_reason = self._blocking(model, system, user, max_tokens,
                                                 temperature, extra, no_think)
            approx_tokens = max(1, len(text) // 4)
            elapsed = time.time() - started

        return Completion(text, finish_reason, approx_tokens, elapsed, aborted,
                          reasoning=reasoning, thinking_leaked=thinking_leaked)

    @staticmethod
    def _iter_sse(resp, kill):
        """Yield parsed SSE 'data:' JSON objects, decoding on whole-line
        boundaries so multi-byte UTF-8 split across network chunks is never
        mangled (requests' iter_lines(decode_unicode=True) gets this wrong)."""
        buf = b""
        for raw in resp.iter_content(chunk_size=2048):
            if kill is not None and kill.hard:
                return
            if not raw:
                continue
            buf += raw
            while b"\n" in buf:
                bline, buf = buf.split(b"\n", 1)
                line = bline.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    return
                try:
                    yield json.loads(line)
                except Exception:
                    continue

    def _blocking(self, model, system, user, max_tokens, temperature, extra, no_think):
        payload = self._payload(model, system, user, max_tokens, temperature, extra, no_think)
        payload["stream"] = False
        try:
            r = self._session.post(f"{self.base_url}/chat/completions",
                                   json=payload, timeout=self.timeout)
            r.raise_for_status()
            choice = (r.json().get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            return (msg.get("content", "") or "").strip(), choice.get("finish_reason", "stop")
        except Exception as e:
            raise JanError(f"Non-streaming fallback also failed: {e}") from e

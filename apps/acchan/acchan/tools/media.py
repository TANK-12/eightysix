"""Music and video: control any player, play files, transcripts, frames, ffmpeg.

Player control is MPRIS through playerctl, so it reaches every player that
publishes media controls: mpv, Firefox tabs (Qobuz, YouTube, Spotify web),
Chromium, Elisa, VLC, Forge's Media app. Transcripts come from YouTube's own
subtitles when there are any (fast, no model), else faster-whisper from
MediaForge's venv (a shared install; nothing new is downloaded except
Whisper's `base` model on first use, about 150 MB).
"""

from __future__ import annotations

import base64
import json
import re
import tempfile
from pathlib import Path
from typing import Annotated

from ..registry import ToolError, tool
from ..sysutil import CACHE, clip, run, spawn
from ..sysutil import path as to_path

TOOLSET = "media"
TOOLSET_SUMMARY = "play/pause/skip/seek/volume on any player (Qobuz, YouTube, mpv...), play files, video transcripts, frames, convert/cut with ffmpeg"

TOOLSET_KEYWORDS = (
    "play",
    "pause",
    "resume",
    "stop",
    "skip",
    "next song",
    "previous",
    "song",
    "track",
    "music",
    "volume",
    "louder",
    "quieter",
    "mute",
    "video",
    "youtube",
    "mpv",
    "qobuz",
    "spotify",
    "playing",
    "transcript",
    "subtitle",
    "frame",
    "convert",
    "ffmpeg",
    "mp3",
    "mp4",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_COMPANIONS = ("find_files",)
TOOLSET_EXAMPLES = [
    ("pause the music", "media_control", {"action": "pause"}),
    (
        "what does this youtube video say about batteries https://youtu.be/x",
        "video_transcript",
        {"source": "https://youtu.be/x", "question": "batteries"},
    ),
]

WHISPER_PY = Path.home() / "Forge/apps/mediaforge/.venv/bin/python"
MPV_SOCKET = "/tmp/acchan-mpv.sock"


def _players() -> list[str]:
    code, out = run(["playerctl", "-l"], timeout=5)
    return [p.strip() for p in out.splitlines() if p.strip() and "No players" not in p]


def _pick(player: str) -> list[str]:
    """playerctl arguments selecting the player a person means."""
    if not player:
        return []
    names = _players()
    want = player.lower().replace(" ", "")
    for name in names:
        if want in name.lower():
            return ["-p", name]
    # A web player lives inside the browser's MPRIS entry.
    if want in ("qobuz", "youtube", "spotify", "soundcloud", "web", "browser"):
        for name in names:
            if "firefox" in name or "chrom" in name:
                return ["-p", name]
    raise ToolError(
        f"No player called {player!r}. Playing now: {', '.join(names) or 'none'}."
    )


@tool(
    TOOLSET,
    phrases=[
        "what is playing",
        "what song is this",
        "what is this song",
        "who is this",
        "what am i listening to",
        "what is on",
    ],
    voice="ok",
)
def now_playing() -> str:
    """Show every media player and what it is playing (title, artist, status, position)."""
    names = _players()
    if not names:
        return "No media players are running."
    rows = []
    fmt = "{{status}} | {{artist}} - {{title}} | {{duration(position)}}/{{duration(mpris:length)}} | vol {{volume}}"
    for name in names:
        code, out = run(
            ["playerctl", "-p", name, "metadata", "--format", fmt], timeout=5
        )
        rows.append(f"{name}: {out.strip()}")
    return "\n".join(rows)


@tool(
    TOOLSET,
    example={"action": "play-pause", "player": ""},
    phrases=[
        ("pause", {"action": "pause"}),
        ("pause music", {"action": "pause"}),
        ("pause this", {"action": "pause"}),
        ("pause video", {"action": "pause"}),
        ("pause song", {"action": "pause"}),
        ("stop music", {"action": "pause"}),
        ("resume", {"action": "play"}),
        ("resume music", {"action": "play"}),
        ("unpause", {"action": "play"}),
        ("play music", {"action": "play"}),
        ("keep playing", {"action": "play"}),
        ("next song", {"action": "next"}),
        ("next track", {"action": "next"}),
        ("skip", {"action": "next"}),
        ("skip this", {"action": "next"}),
        ("skip song", {"action": "next"}),
        ("skip this song", {"action": "next"}),
        ("previous song", {"action": "previous"}),
        ("previous track", {"action": "previous"}),
        ("last song", {"action": "previous"}),
        ("go back a song", {"action": "previous"}),
        ("play last song again", {"action": "previous"}),
    ],
    voice="ok",
)
def media_control(
    action: Annotated[str, "play, pause, play-pause, next, previous or stop"],
    player: Annotated[
        str, "Player name like qobuz, firefox, mpv; empty for the active one"
    ] = "",
) -> str:
    """Play, pause, skip or stop music/video in any player, including Qobuz or YouTube in the browser."""
    action = (
        action.lower().strip().replace("toggle", "play-pause").replace("skip", "next")
    )
    if action in ("prev", "back"):
        action = "previous"
    if action not in ("play", "pause", "play-pause", "next", "previous", "stop"):
        raise ToolError(
            "action must be play, pause, play-pause, next, previous or stop."
        )
    code, out = run(["playerctl", *_pick(player), action], timeout=5)
    if code != 0:
        raise ToolError(out.strip() or "No player answered.")
    return f"Sent {action}." + (
        "\n" + now_playing() if action in ("next", "previous") else ""
    )


@tool(TOOLSET, example={"seconds": 30, "player": ""}, voice="ok")
def media_seek(
    seconds: Annotated[
        float, "Seconds to jump; negative goes back. Use absolute=true to go to a time"
    ],
    player: Annotated[str, "Player name; empty for the active one"] = "",
    absolute: Annotated[bool, "Treat seconds as a position from the start"] = False,
) -> str:
    """Jump forward or back in the playing track or video, or to an exact time."""
    value = f"{abs(seconds):g}" + ("" if absolute else ("+" if seconds >= 0 else "-"))
    code, out = run(["playerctl", *_pick(player), "position", value], timeout=5)
    if code != 0:
        raise ToolError(out.strip() or "Seek failed.")
    return f"Position now {out.strip() or value}."


@tool(
    TOOLSET,
    example={"percent": 40},
    phrases=[
        "volume {percent}",
        "set volume to {percent}",
        "set volume {percent}",
        "volume to {percent}",
        "change volume to {percent}",
        "turn volume to {percent}",
        "turn volume up to {percent}",
        "turn volume down to {percent}",
        "turn it up to {percent}",
        "turn it down to {percent}",
        "put volume at {percent}",
        "make it {percent}",
    ],
    voice="ok",
)
def set_volume(
    percent: Annotated[int, "Volume 0-150"],
    player: Annotated[
        str, "Player name for that app's own volume; empty for the whole system"
    ] = "",
) -> str:
    """Set the volume of the whole system, or of one player."""
    level = max(0, min(percent, 150))
    if player:
        run(
            ["playerctl", *_pick(player), "volume", f"{level / 100:.2f}"],
            timeout=5,
            check=True,
        )
        return f"{player} volume {level}%."
    run(
        ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{level / 100:.2f}"],
        timeout=5,
        check=True,
    )
    return f"System volume {level}%."


@tool(TOOLSET, example={"source": "~/Videos/clip.mp4"}, voice="ok")
def play_media(
    source: Annotated[
        str, "A music/video file, folder, playlist or web address (YouTube works)"
    ],
) -> str:
    """Play a file, folder or online video in mpv."""
    text = source.strip()
    target = text if re.match(r"^[a-z]+://", text) else str(to_path(text))
    if "://" not in target and not Path(target).exists():
        raise ToolError(f"{target} does not exist. Use find_files first.")
    spawn(["mpv", "--force-window=yes", f"--input-ipc-server={MPV_SOCKET}", target])
    return f"Playing {target} in mpv."


def _is_url(text: str) -> bool:
    return bool(re.match(r"^[a-z]+://", text.strip()))


@tool(TOOLSET, example={"source": "~/Videos/talk.mp4"}, voice="ok")
def video_info(source: Annotated[str, "Video/audio file or address"]) -> str:
    """Duration, size, codecs and title of a video or audio file."""
    if _is_url(source):
        code, out = run(
            ["yt-dlp", "-J", "--no-warnings", "--skip-download", source], timeout=60
        )
        try:
            data = json.loads(out[out.find("{") :])
        except ValueError:
            raise ToolError(out.strip()[-500:])
        return (
            f"{data.get('title')}\nby {data.get('uploader')}\n"
            f"length {data.get('duration_string')}  views {data.get('view_count')}\n"
            f"{(data.get('description') or '')[:800]}"
        )
    code, out = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(to_path(source)),
        ],
        timeout=30,
        check=True,
    )
    return out


def _subtitles(url: str) -> str | None:
    work = Path(tempfile.mkdtemp(prefix="acchan-subs-"))
    run(
        [
            "yt-dlp",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "en.*,en",
            "--sub-format",
            "vtt",
            "-o",
            str(work / "s"),
            url,
        ],
        timeout=120,
    )
    files = sorted(work.glob("*.vtt"))
    if not files:
        return None
    lines, last = [], ""
    for block in files[0].read_text(encoding="utf-8", errors="replace").split("\n\n"):
        stamp = re.search(r"(\d\d:\d\d:\d\d)\.\d+ -->", block)
        text = " ".join(
            re.sub(r"<[^>]+>", "", line).strip()
            for line in block.splitlines()
            if "-->" not in line
            and not line.startswith(("WEBVTT", "Kind:", "Language:"))
        ).strip()
        if text and text != last and stamp:
            lines.append(f"[{stamp.group(1)}] {text}")
            last = text
    for file in work.iterdir():
        file.unlink()
    work.rmdir()
    return "\n".join(lines)


def transcribe(source: str) -> str:
    cache = CACHE / "transcripts"
    cache.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^\w]+", "_", source)[-120:]
    hit = cache / f"{key}.txt"
    if hit.exists():
        return hit.read_text(encoding="utf-8")
    text = _subtitles(source) if _is_url(source) else None
    if not text:
        if not WHISPER_PY.exists():
            raise ToolError(
                "No subtitles, and faster-whisper (MediaForge's venv) is missing."
            )
        media = source
        if _is_url(source):
            work = Path(tempfile.mkdtemp(prefix="acchan-audio-"))
            run(
                [
                    "yt-dlp",
                    "-x",
                    "--audio-format",
                    "m4a",
                    "-o",
                    str(work / "a.%(ext)s"),
                    source,
                ],
                timeout=900,
                check=True,
            )
            media = str(next(work.glob("a.*")))
        script = (
            "import sys\nfrom faster_whisper import WhisperModel\n"
            "m=WhisperModel('base',device='cpu',compute_type='int8',cpu_threads=4)\n"
            "segs,_=m.transcribe(sys.argv[1],vad_filter=True)\n"
            "for s in segs:\n h,r=divmod(int(s.start),3600);mi,se=divmod(r,60)\n print(f'[{h:02d}:{mi:02d}:{se:02d}] {s.text.strip()}',flush=True)\n"
        )
        code, out = run(
            [
                str(WHISPER_PY),
                "-c",
                script,
                str(to_path(media)) if not _is_url(media) else media,
            ],
            timeout=3600,
        )
        text = "\n".join(line for line in out.splitlines() if line.startswith("["))
        if not text:
            raise ToolError(f"Transcription failed: {out.strip()[-400:]}")
    hit.write_text(text, encoding="utf-8")
    return text


@tool(
    TOOLSET,
    example={
        "source": "https://youtube.com/watch?v=...",
        "question": "what does he say about taxes?",
    },
    voice="ok",
)
def video_transcript(
    source: Annotated[str, "Video file or address (YouTube etc.)"],
    question: Annotated[str, "Optional: only return the parts relevant to this"] = "",
    start: Annotated[int, "Character offset to continue from"] = 0,
) -> str:
    """Get what is said in a video, with timestamps. With a question, returns only the relevant parts."""
    text = transcribe(source)
    if question:
        from .docs import best_passages

        hits = best_passages(text, question, k=6, size=900)
        return "Relevant parts of the transcript:\n\n" + "\n---\n".join(hits)
    piece = text[start : start + 8000]
    more = (
        f"\n[{start + len(piece)} of {len(text)} characters; call with start={start + len(piece)} for more]"
        if start + len(piece) < len(text)
        else ""
    )
    return piece + more


@tool(
    TOOLSET,
    example={
        "source": "~/Videos/clip.mp4",
        "time": "00:01:30",
        "question": "what is on screen?",
    },
    voice="ok",
)
def video_frame(
    source: Annotated[str, "Video file or address"],
    time: Annotated[str, "When, like 90 or 00:01:30"],
    question: Annotated[
        str, "What to find out about the frame"
    ] = "Describe this frame.",
) -> str:
    """Look at one moment of a video and describe it (uses the vision model)."""
    from ..llm import describe_image

    target = source
    if _is_url(source):
        code, out = run(
            ["yt-dlp", "-g", "-f", "best[height<=720]/best", source], timeout=60
        )
        target = out.strip().splitlines()[0] if out.strip() else source
    else:
        target = str(to_path(source))
    frame = Path(tempfile.mkstemp(suffix=".jpg", prefix="acchan-frame-")[1])
    run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            str(time),
            "-i",
            target,
            "-frames:v",
            "1",
            "-vf",
            "scale='min(1024,iw)':-2",
            str(frame),
        ],
        timeout=120,
        check=True,
    )
    data = base64.b64encode(frame.read_bytes()).decode()
    frame.unlink(missing_ok=True)
    return describe_image(data, question, mime="image/jpeg")


@tool(
    TOOLSET,
    example={
        "source": "~/in.mkv",
        "output": "~/out.mp4",
        "start": "",
        "end": "",
        "options": "",
    },
    risky=True,
)
def convert_media(
    source: Annotated[str, "Input video or audio file"],
    output: Annotated[
        str, "Output file; the extension picks the format (.mp4, .mp3, .gif, .webm...)"
    ],
    start: Annotated[str, "Optional start time to cut from, like 00:01:00"] = "",
    end: Annotated[str, "Optional end time to cut to"] = "",
    options: Annotated[
        str, "Extra ffmpeg output options, like -crf 28 or -vf scale=1280:-2"
    ] = "",
) -> str:
    """Convert, cut, compress or extract audio from a video/audio file with ffmpeg."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if start:
        cmd += ["-ss", start]
    if end:
        cmd += ["-to", end]
    cmd += ["-i", str(to_path(source))]
    if options:
        cmd += options.split()
    out_path = to_path(output)
    cmd.append(str(out_path))
    code, out = run(cmd, timeout=3600)
    if code != 0:
        raise ToolError(clip(out.strip(), 1200))
    return f"Wrote {out_path} ({out_path.stat().st_size // 1024} KB)."

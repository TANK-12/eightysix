"""
Content-based hashing for video/audio files, using the actual decoded audio —
not the filename, not the container, not a head/tail byte hash. Two files with
wildly different names, sizes, bitrates or containers but the SAME underlying
recording hash identically; two files with the same or near-identical name but
genuinely different audio hash differently. That's what lets the media-type
sorter tell "same video, re-encoded" apart from "different video, same title".

Needs ffmpeg/ffprobe (already a MediaForge dependency). Degrades gracefully —
callers should fall back to manifest.quick_hash() when this returns None (no
audio stream, corrupt file, ffmpeg missing).
"""

import hashlib
import shutil
import subprocess

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def audio_content_hash(path, minutes=3, sample_rate=8000, timeout=180):
    """SHA1 of the first `minutes` of decoded mono PCM audio at a low sample
    rate. Cheap (no need to decode video frames or the whole file) and robust
    to container/bitrate/metadata differences. None if there's no usable audio
    track, the file is unreadable, or ffmpeg isn't available."""
    if not FFMPEG:
        return None
    cmd = [FFMPEG, "-v", "error", "-i", str(path), "-t", str(max(1, minutes) * 60),
          "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"]
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout)
    except Exception:
        return None
    # need at least ~1s of real decoded audio to trust the hash
    if r.returncode not in (0, None) and not r.stdout:
        return None
    if not r.stdout or len(r.stdout) < sample_rate * 2:
        return None
    return hashlib.sha1(r.stdout).hexdigest()


def probe_duration(path, timeout=20):
    """Duration in seconds (float), or None."""
    if not FFPROBE:
        return None
    cmd = [FFPROBE, "-v", "error", "-show_entries", "format=duration",
          "-of", "csv=p=0", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
        return float(out)
    except Exception:
        return None


def format_duration(seconds):
    """1553.2 -> '25m53s'; 3661 -> '1h01m'."""
    if seconds is None:
        return None
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"

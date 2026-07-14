"""In-app video playback (audio + video) via ffpyplayer.

The decoder plays audio itself; we pull RGB frames and let the UI blit them onto
the projection canvas. All transport (play/pause/seek) is controlled from the app.
"""
import os
import re
import shutil
import subprocess
import sys
from typing import Optional, Tuple

# ffpyplayer's bundled decoder doesn't support AV1 (common on freshly downloaded
# YouTube videos) — it just silently never produces a frame, leaving the
# projection black. These codecs are known to play back reliably.
_PLAYABLE_VIDEO_CODECS = {"h264", "mpeg4", "mjpeg"}

# On Windows, launching a console-mode exe (ffmpeg.exe) from a windowed app
# briefly flashes a black console window unless this flag is set. No-op
# elsewhere — macOS/Linux processes are never attached to a console here.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def probe_video_codec(path: str, ffmpeg_exe: str) -> Optional[str]:
    """Return the lowercase video codec name (e.g. 'av1', 'h264'), or None if
    it couldn't be determined. Explicit utf-8/replace decoding — ffmpeg's
    stderr often echoes a video's title/metadata verbatim, which can contain
    non-ASCII characters (very common in YouTube downloads); on Windows the
    default subprocess text-decoding locale is not UTF-8, and would otherwise
    raise UnicodeDecodeError here — silently treated as "codec unknown" by
    the except below, which used to be misread downstream as "safe to play"."""
    try:
        r = subprocess.run([ffmpeg_exe, "-i", path], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=20, creationflags=_NO_WINDOW)
        m = re.search(r"Video:\s*([a-zA-Z0-9_]+)", r.stderr)
        return m.group(1).lower() if m else None
    except Exception:
        return None


def needs_transcode(codec: Optional[str]) -> bool:
    """True unless the codec is positively confirmed to be one we can play.
    An undetermined codec (None — probe failed/timed out/unrecognized output)
    is treated as needing transcode too: guessing "safe" here is exactly how
    the black-screen bug slipped back in for videos where detection failed
    silently instead of raising."""
    return codec not in _PLAYABLE_VIDEO_CODECS


def transcode_to_h264(path: str, ffmpeg_exe: str) -> bool:
    """Re-encode `path` in place to H.264/AAC. Returns True on success.

    The intermediate file is written to the system temp dir, not next to
    `path` — otherwise it briefly shows up in the destination folder (e.g. in
    a file picker) under a different name than the final one, and picking it
    mid-conversion leaves a dangling reference once it gets renamed away.
    """
    import tempfile
    base, _ext = os.path.splitext(path)
    fd, tmp_out = tempfile.mkstemp(suffix=".mp4", prefix="transcode_")
    os.close(fd)
    try:
        subprocess.run([ffmpeg_exe, "-y", "-i", path,
                        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                        "-c:a", "aac", "-b:a", "192k", tmp_out],
                       capture_output=True, timeout=3600, check=True,
                       creationflags=_NO_WINDOW)
    except Exception:
        if os.path.isfile(tmp_out):
            try:
                os.remove(tmp_out)
            except Exception:
                pass
        return False
    final_path = base + ".mp4"
    try:
        os.remove(path)
    except Exception:
        pass
    try:
        # shutil.move (not os.replace) — tmp_out lives in the system temp dir,
        # which can be a different filesystem/volume than the destination.
        shutil.move(tmp_out, final_path)
    except Exception:
        return False
    return True


class VideoPlayer:
    def __init__(self, path: str):
        from ffpyplayer.player import MediaPlayer
        self.path = path
        self._mp = MediaPlayer(path, ff_opts={"out_fmt": "rgb24"})
        self._paused = False
        self._finished = False
        self._duration = 0.0
        self._size = (0, 0)

    # -- frame access ---------------------------------------------------------
    def get_frame(self):
        """Return (PIL.Image | None, finished: bool). Call ~30×/s."""
        if self._finished:
            return None, True
        try:
            frame, val = self._mp.get_frame()
        except Exception:
            self._finished = True
            return None, True
        if val == "eof":
            self._finished = True
            return None, True
        if frame is None:
            return None, False
        img, _pts = frame
        try:
            from PIL import Image
            w, h = img.get_size()
            self._size = (w, h)
            data = bytes(img.to_bytearray()[0])
            return Image.frombytes("RGB", (w, h), data), False
        except Exception:
            return None, False

    # -- transport ------------------------------------------------------------
    def toggle(self):
        self._paused = not self._paused
        try:
            self._mp.set_pause(self._paused)
        except Exception:
            pass

    def pause(self):
        self._paused = True
        try:
            self._mp.set_pause(True)
        except Exception:
            pass

    def play(self):
        self._paused = False
        try:
            self._mp.set_pause(False)
        except Exception:
            pass

    def seek(self, seconds: float):
        try:
            self._mp.seek(max(0.0, seconds), relative=False, accurate=False)
            self._finished = False
        except Exception:
            pass

    def restart(self):
        self.seek(0.0)

    @property
    def position(self) -> float:
        try:
            return max(0.0, float(self._mp.get_pts()))
        except Exception:
            return 0.0

    @property
    def duration(self) -> float:
        if self._duration <= 0:
            try:
                md = self._mp.get_metadata() or {}
                self._duration = float(md.get("duration") or 0.0)
            except Exception:
                self._duration = 0.0
        return self._duration

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def finished(self) -> bool:
        return self._finished

    def close(self):
        try:
            self._mp.close_player()
        except Exception:
            pass

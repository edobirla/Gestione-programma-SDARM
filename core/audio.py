"""Audio engine.

Two backends, on purpose:
  • MusicPlayer  → pygame.mixer.music (ONE stream, but seekable) for the main
    controllable media (hymn base / audio element). The seek bar works here.
  • Sound channels → pygame.mixer.Channel for things that may overlap and don't
    need seeking: pause-music playlist, bell, warning tone.
"""
import os
import threading
import time
import random
from typing import Optional, Callable, List

# Must be set before pygame is ever imported — silences its import-time banner
# (which would show up garbled in a windowed/frozen app with no console).
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

_mixer_ready = False
_mixer_failed = False


def _ensure_mixer():
    """Init pygame's mixer once. On a machine with no usable audio device
    (headless PC, projector-only setup, missing drivers) pygame.mixer.init()
    raises — that must NOT crash the whole app at startup: every playback
    call already guards itself, so we just record the failure and the app
    runs normally, silently, instead. `_mixer_failed` prevents re-trying
    (and re-failing, with a multi-second device probe) on every sound."""
    global _mixer_ready, _mixer_failed
    if _mixer_ready or _mixer_failed:
        return
    try:
        import pygame
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=1024)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(8)
        _mixer_ready = True
    except Exception:
        _mixer_failed = True


def _duration(path: str) -> float:
    try:
        from mutagen import File
        f = File(path)
        if f and getattr(f, "info", None):
            return float(f.info.length)
    except Exception:
        pass
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
class MusicPlayer:
    """Single seekable stream via pygame.mixer.music (mp3/ogg/wav)."""

    def __init__(self):
        self._path: Optional[str] = None
        self._label = ""
        self._duration = 0.0
        self._offset = 0.0          # seconds where the current play() started
        self._playing = False
        self._paused = False
        self._volume = 1.0
        self.on_end: Optional[Callable] = None
        self._stop_evt = threading.Event()

    # -- loading / transport --------------------------------------------------
    def load(self, path: str, label: str = "") -> bool:
        _ensure_mixer()
        if not path or not os.path.isfile(path):
            return False
        self.stop()
        self._path = path
        self._label = label or os.path.basename(path)
        self._duration = _duration(path)
        self._offset = 0.0
        self._paused = False
        return True

    def play(self, start: float = 0.0):
        if not self._path:
            return
        import pygame
        try:
            pygame.mixer.music.load(self._path)
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play(start=start)
        except Exception:
            try:
                pygame.mixer.music.play()
            except Exception:
                return
        self._offset = start
        self._playing = True
        self._paused = False
        self._stop_evt.clear()
        threading.Thread(target=self._watch, daemon=True).start()

    def toggle(self):
        if self._playing:
            self.pause()
        elif self._paused:
            self.unpause()
        elif self._path:
            self.play()

    def pause(self):
        import pygame
        if self._playing:
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass
            self._playing = False
            self._paused = True

    def unpause(self):
        import pygame
        if self._paused:
            try:
                pygame.mixer.music.unpause()
            except Exception:
                pass
            self._playing = True
            self._paused = False

    def stop(self):
        import pygame
        self._stop_evt.set()
        if _mixer_ready:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self._playing = False
        self._paused = False

    def seek(self, seconds: float):
        if not self._path:
            return
        seconds = max(0.0, min(seconds, self._duration or seconds))
        was_paused = self._paused and not self._playing
        self.play(start=seconds)
        if was_paused:
            self.pause()

    def restart(self):
        self.seek(0.0)

    def set_volume(self, v: float):
        import pygame
        self._volume = max(0.0, min(1.0, v))
        if _mixer_ready:
            try:
                pygame.mixer.music.set_volume(self._volume)
            except Exception:
                pass

    # -- state ----------------------------------------------------------------
    @property
    def position(self) -> float:
        import pygame
        if not _mixer_ready or (not self._playing and not self._paused):
            return self._offset
        try:
            ms = pygame.mixer.music.get_pos()
            if ms < 0:
                return self._offset
            return self._offset + ms / 1000.0
        except Exception:
            return self._offset

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def has_media(self) -> bool:
        return self._path is not None

    @property
    def label(self) -> str:
        return self._label

    @property
    def current_path(self) -> Optional[str]:
        return self._path

    def _watch(self):
        import pygame
        while not self._stop_evt.is_set():
            time.sleep(0.2)
            if not self._playing:
                continue
            try:
                busy = pygame.mixer.music.get_busy()
            except Exception:
                break
            if not busy and self._playing:
                self._playing = False
                if self.on_end:
                    try:
                        self.on_end()
                    except Exception:
                        pass
                break


# ─────────────────────────────────────────────────────────────────────────────
class PlaylistChannel:
    """Pause-music playlist on a Sound channel (overlaps main media; no seek)."""

    def __init__(self, channel_idx: int = 1):
        self._idx = channel_idx
        self._files: List[str] = []
        self._i = 0
        self._mode = "shuffle"
        self._sound = None
        self._playing = False
        self._paused = False
        self._volume = 1.0
        self._stop_evt = threading.Event()
        self.on_track: Optional[Callable[[str], None]] = None

    def set_volume(self, v: float):
        self._volume = max(0.0, min(1.0, v))
        if _mixer_ready:
            try:
                self._chan().set_volume(self._volume)
            except Exception:
                pass

    def _chan(self):
        import pygame
        return pygame.mixer.Channel(self._idx)

    def load_folder(self, folder: str, mode: str = "shuffle"):
        _ensure_mixer()
        exts = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac")
        try:
            self._files = [os.path.join(folder, f) for f in os.listdir(folder)
                           if os.path.splitext(f)[1].lower() in exts]
        except Exception:
            self._files = []
        if mode == "shuffle":
            random.shuffle(self._files)
        else:
            self._files.sort()
        self._mode = mode
        self._i = 0

    def play(self):
        if not self._files:
            return
        self._play_current()
        threading.Thread(target=self._watch, daemon=True).start()

    def _play_current(self):
        import pygame
        if not self._files:
            return
        path = self._files[self._i % len(self._files)]
        try:
            self._sound = pygame.mixer.Sound(path)
            self._chan().play(self._sound)
            self._chan().set_volume(self._volume)
            self._playing = True
            self._paused = False
            self._stop_evt.clear()
            if self.on_track:
                self.on_track(path)
        except Exception:
            pass

    def skip(self):
        self._i = (self._i + 1) % max(1, len(self._files))
        self._play_current()

    def prev(self):
        self._i = (self._i - 1) % max(1, len(self._files))
        self._play_current()

    def stop(self, fade_ms: int = 0):
        self._stop_evt.set()
        self._playing = False
        self._paused = False
        if _mixer_ready:
            try:
                if fade_ms > 0:
                    self._chan().fadeout(fade_ms)
                else:
                    self._chan().stop()
            except Exception:
                pass

    def pause(self):
        if _mixer_ready:
            self._chan().pause()
            self._playing = False
            self._paused = True

    def unpause(self):
        if _mixer_ready:
            self._chan().unpause()
            self._playing = True
            self._paused = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def current_file(self) -> Optional[str]:
        return self._files[self._i % len(self._files)] if self._files else None

    def _watch(self):
        while not self._stop_evt.is_set():
            time.sleep(0.3)
            if not self._playing:
                continue
            try:
                if not self._chan().get_busy():
                    self._i = (self._i + 1) % max(1, len(self._files))
                    if self._mode == "shuffle" and self._i == 0:
                        random.shuffle(self._files)
                    self._play_current()
            except Exception:
                break


# ─────────────────────────────────────────────────────────────────────────────
class _OneShot:
    """A short non-overlapping sound (bell / warning)."""

    def __init__(self, channel_idx):
        self._idx = channel_idx

    def play(self, path, volume: float = 1.0):
        _ensure_mixer()
        if not path or not os.path.isfile(path):
            return
        import pygame
        try:
            snd = pygame.mixer.Sound(path)
            snd.set_volume(max(0.0, min(1.0, volume)))
            pygame.mixer.Channel(self._idx).play(snd)
        except Exception:
            pass


class AudioManager:
    def __init__(self):
        _ensure_mixer()
        self.music = MusicPlayer()                 # seekable main media
        self.playlist = PlaylistChannel(1)         # pause background music
        self._bell = _OneShot(2)
        self._warning = _OneShot(3)

    # -- main media -----------------------------------------------------------
    def load_media(self, path: str, label: str = "") -> bool:
        return self.music.load(path, label)

    def play_media(self, path: str, label: str = ""):
        if self.music.load(path, label):
            self.music.play()

    # -- pause music ----------------------------------------------------------
    def start_pause_music(self, folder, mode="shuffle", on_track_change=None, volume: float = 1.0):
        self.playlist.on_track = on_track_change
        self.playlist.set_volume(volume)
        self.playlist.load_folder(folder, mode)
        self.playlist.play()

    def set_pause_music_volume(self, volume: float):
        self.playlist.set_volume(volume)

    def stop_pause_music(self, fade_ms: int = 800):
        self.playlist.stop(fade_ms=fade_ms)

    def skip_pause_music(self):
        self.playlist.skip()

    def prev_pause_music(self):
        self.playlist.prev()

    def pause_pause_music(self):
        self.playlist.pause()

    def resume_pause_music(self):
        self.playlist.unpause()

    def pause_music_is_playing(self) -> bool:
        return self.playlist.is_playing

    def pause_music_is_paused(self) -> bool:
        return self.playlist.is_paused

    def current_pause_track(self):
        return self.playlist.current_file

    # -- one-shots ------------------------------------------------------------
    def play_bell(self, path):
        self._bell.play(path)

    def play_warning(self, path, volume: float = 1.0):
        self._warning.play(path, volume=volume)

    # -- compat / status ------------------------------------------------------
    def hymn_base_is_playing(self) -> bool:
        return self.music.is_playing

    def shutdown(self):
        try:
            self.music.stop()
            self.playlist.stop()
        except Exception:
            pass
        if _mixer_ready:
            try:
                import pygame
                pygame.mixer.quit()
            except Exception:
                pass

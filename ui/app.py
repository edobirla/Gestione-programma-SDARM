"""Main application window — Gestione programma SDARM."""
from __future__ import annotations
import gc
import os
import re
import sys
import threading
import time

# Tkinter/Tcl calls are only safe from the thread that owns the interpreter
# (the main thread). CPython's cyclic garbage collector can run on ANY
# thread whenever an allocation threshold is hit — including a background
# worker thread doing completely unrelated work (e.g. importing a module).
# If that GC pass happens to collect a leftover tkinter.font.Font object
# (this app creates many, e.g. every autofit calculation), its __del__ calls
# into Tcl from the wrong thread and deadlocks permanently — no exception,
# no timeout, just a hung thread. Confirmed via a live repro: a background
# YouTube-download thread's `import yt_dlp` froze forever inside
# `tkinter/font.py Font.__del__` for exactly this reason. Fix: disable
# automatic GC (so it never fires on a worker thread) and instead run it
# manually on a timer via `self.after(...)`, which always executes on the
# main thread — see App._periodic_gc.
gc.disable()

# yt-dlp's own progress percentage can come wrapped in ANSI color escape
# codes when it thinks it's writing to a color-capable terminal — harmless
# in a real terminal, but shows up as garbled "code" in a GUI label. Strip
# it defensively wherever we fall back to yt-dlp's own formatted string.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Fix SSL on python.org builds (needed for YouTube downloads) — must run early.
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("SSL_CERT_DIR", os.path.dirname(certifi.where()))
except Exception:
    pass
import tkinter as tk
from tkinter import filedialog, colorchooser
from typing import Optional, List, Callable

import customtkinter as ctk
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import settings as cfg
from core import prayers as prayers_store
from core import lesson
from core import bible_ref
from core.history import History
from core.schedule import Schedule, Section, Slot, SLOT_TYPES
from core.audio import AudioManager
from core.database import load_database
from core.hymn import Hymn
from core import projector
from ui.projection import ProjectionWindow

try:
    from core.bible import BibleLibrary
    _HAS_BIBLE = True
except Exception:
    _HAS_BIBLE = False

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    import tkinter as _tk_patch
    # tkinterdnd2-universal only patches BaseWidget, not Tk (ctk.CTk inherits Tk→Misc).
    # Propagate all DnD-related attributes to Misc so the root window gets them too.
    if hasattr(_tk_patch.BaseWidget, "drop_target_register") and \
            not hasattr(_tk_patch.Misc, "drop_target_register"):
        for _attr in ("_subst_format_dnd", "_subst_format_str_dnd", "_substitute_dnd",
                      "_dnd_bind", "dnd_bind",
                      "drag_source_register", "drag_source_unregister",
                      "drop_target_register", "drop_target_unregister"):
            if hasattr(_tk_patch.BaseWidget, _attr):
                setattr(_tk_patch.Misc, _attr, getattr(_tk_patch.BaseWidget, _attr))
    del _tk_patch
    _HAS_DND = True
except Exception:
    _HAS_DND = False

_NAV_W = 64
_DIVIDER_W = 8
_MIN_PANEL = 170
# Default (x, y, w, h) boxes — 0..1 fractions of the screen — for the main
# verse text and its reference. Kept apart on purpose so the reference never
# looks glued to the verse text; must mirror core/settings.py DEFAULTS.
_VERSE_TEXT_BOX_DEFAULT = [0.07, 0.10, 0.86, 0.55]
_VERSE_REF_BOX_DEFAULT = [0.25, 0.78, 0.50, 0.08]

# media file extensions for the in-app library picker
_VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm")
_AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac")

SLOT_LABELS = {
    "inno": "Inno", "versetto": "Versetto", "presentazione": "Presentazione",
    "timer": "Timer", "audio": "Audio", "video": "Video", "lezione": "Lezione",
    "documento": "Documento", "qrcode": "QR Offerta", "immagine": "Immagine",
    "testo": "Testo", "campana": "Campana", "predica": "Predica",
    "preghiera": "Preghiere", "altro": "Elemento",
}

# Types the user can actually add from the "+" picker (campana/predica excluded).
ADDABLE_TYPES = ["inno", "versetto", "lezione", "presentazione", "timer",
                 "audio", "video", "documento", "qrcode", "immagine", "testo", "preghiera"]

# Visual language (palette, fonts, icons) lives in ui/theme.py — imported
# under the same names used throughout this file so the redesign applies
# without touching every call site at once (see design/ for the source mockup).
from ui.theme import (SLOT_COLORS, ACCENT, ACCENT_HOVER, SEL_BG, SEL_BORDER,
                       LESSON_BG, CARD, CARD_ROW, MUTED, HEADER_FG,
                       BTN_SECONDARY, BTN_SECONDARY_HOVER, DANGER, DANGER_HOVER,
                       ACTIVE_GREEN, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY,
                       TEXT_FAINT, BORDER, BORDER_SUBTLE, SURFACE_3, SURFACE_4,
                       DANGER_FILL, DANGER_FILL_HOVER, DANGER_FILL_TEXT, TEXT_LABEL)
from ui import theme

_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
         "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _today_title() -> str:
    from datetime import date
    d = date.today()
    return f"{_GIORNI[d.weekday()].capitalize()} {d.day} {_MESI[d.month - 1]} {d.year}"


def _circle(parent, text, size, corner_radius, fg_color, text_color, font=None,
            command=None, hover_color=None, width=None, height=None):
    """A fixed-size circular/pill CTkFrame with a purely decorative CTkLabel
    placed on top, instead of putting text/an image directly on a CTkButton
    or CTkLabel. Both of those silently grow past an explicit width to fit
    their content once corner_radius gets close to half their size (measured:
    a 40x40 CTkButton with an 18px icon and corner_radius=20 renders at
    62×40; a 34x34 CTkLabel with 2-letter text and corner_radius=17 renders
    at 54×34) — turning an intended circle into a flat-sided pill. A
    CTkFrame has no such content-driven sizing logic, so it stays exact.
    `size` sets a square; pass `width`/`height` instead for a pill shape
    (e.g. a fixed-width numbered chip). Returns the frame (its fg_color is
    the toggle point for callers that need a "selected" look elsewhere);
    the decorative label is reachable as `frame.lbl` for callers that need
    to update the glyph/text later (e.g. a play/pause toggle)."""
    frame = ctk.CTkFrame(parent, width=width or size, height=height or size,
                         corner_radius=corner_radius,
                         fg_color=fg_color, cursor="hand2" if command else "")
    frame.grid_propagate(False)
    lbl = ctk.CTkLabel(frame, text=text, text_color=text_color, font=font)
    lbl.place(relx=0.5, rely=0.5, anchor="center")
    frame.lbl = lbl
    if command:
        if hover_color:
            def on_enter(_e, f=frame, hv=hover_color):
                f.configure(fg_color=hv)

            def on_leave(_e, f=frame, fg=fg_color):
                f.configure(fg_color=fg)
            for w in (frame, lbl):
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
        for w in (frame, lbl):
            w.bind("<Button-1>", lambda _e: command())
    return frame


def _bind_textbox_scroll(box):
    """Let a CTkTextbox scroll with the mouse wheel under the cursor even
    when a CTkScrollableFrame is anywhere on screen — CTkScrollableFrame
    installs a `bind_all` MouseWheel handler (application-wide, not scoped
    to its own subtree) that otherwise always wins and scrolls itself
    instead. Binding directly on the textbox's inner Text widget and
    returning "break" takes priority over that bind_all handler."""
    def _scroll(event):
        if getattr(event, "num", None) == 4:
            box.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            box.yview_scroll(1, "units")
        else:
            box.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"
    box._textbox.bind("<MouseWheel>", _scroll)
    box._textbox.bind("<Button-4>", _scroll)
    box._textbox.bind("<Button-5>", _scroll)


def _fmt_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _auto_wrap_label(lbl: ctk.CTkLabel) -> None:
    """Bind lbl so its wraplength tracks its actual pixel width."""
    _last = [0]
    def _resize(_e=None):
        w = lbl.winfo_width()
        if w > 1 and w != _last[0]:
            _last[0] = w
            lbl.configure(wraplength=w)
    lbl.bind("<Configure>", _resize)
    lbl.after(80, _resize)


# ─────────────────────────────────────────────────────────────────────────────
# Audio player widget
# ─────────────────────────────────────────────────────────────────────────────
class AudioPlayerWidget(ctk.CTkFrame):
    """Controls the single seekable MusicPlayer (audio_mgr.music)."""

    def __init__(self, master, audio_mgr: AudioManager, label: str = "", **kw):
        super().__init__(master, **kw)
        self._mgr = audio_mgr
        self._dragging = False
        self._alive = True

        if label:
            ctk.CTkLabel(self, text=label, font=theme.font_body(12, bold=True),
                         text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", padx=8, pady=(6, 0))

        self._seek = ctk.CTkSlider(self, from_=0, to=1000, command=self._on_drag,
                                   progress_color=ACCENT, button_color=ACCENT,
                                   button_hover_color=ACCENT_HOVER, fg_color=SURFACE_3)
        self._seek.set(0)
        self._seek.pack(fill="x", padx=8, pady=(6, 2))
        self._seek.bind("<ButtonPress-1>", lambda e: setattr(self, "_dragging", True))
        self._seek.bind("<ButtonRelease-1>", self._on_seek_release)

        self._time_lbl = ctk.CTkLabel(self, text="00:00 / 00:00", font=theme.font_body(11),
                                      text_color=TEXT_TERTIARY)
        self._time_lbl.pack()

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=(4, 6))
        _circle(row, "↺", 34, 17, SURFACE_3, TEXT_SECONDARY, font=theme.font_body(15),
               hover_color=SURFACE_4, command=self._restart).pack(side="left", padx=3)
        self._play_btn = _circle(row, "▶", 40, 20, ACCENT, "white", font=theme.font_body(15),
                                 hover_color=ACCENT_HOVER, command=self._toggle)
        self._play_btn.pack(side="left", padx=3)
        _circle(row, "■", 34, 17, SURFACE_3, TEXT_SECONDARY, font=theme.font_body(13),
               hover_color=SURFACE_4, command=self._stop).pack(side="left", padx=3)

        self.bind("<Destroy>", lambda e: setattr(self, "_alive", False))
        self._update()

    def _m(self):
        return self._mgr.music

    def _toggle(self):
        self._m().toggle()

    def _stop(self):
        self._m().stop()

    def _restart(self):
        self._m().seek(0.0)

    def _on_drag(self, _v):
        # while dragging, only update the time label preview
        if self._dragging:
            dur = self._m().duration or 0
            self._time_lbl.configure(
                text=f"{_fmt_time((self._seek.get() / 1000.0) * dur)} / {_fmt_time(dur)}")

    def _on_seek_release(self, _e):
        m = self._m()
        if m.duration > 0:
            m.seek((self._seek.get() / 1000.0) * m.duration)
        self._dragging = False

    def _update(self):
        if not self._alive:
            return
        try:
            m = self._m()
            dur = m.duration or 1
            if not self._dragging:
                self._seek.set(min(1000, (m.position / dur) * 1000))
                self._time_lbl.configure(text=f"{_fmt_time(m.position)} / {_fmt_time(dur)}")
            self._play_btn.lbl.configure(text="⏸" if m.is_playing else "▶")
            self.after(300, self._update)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Video player widget — same seek-bar pattern as AudioPlayerWidget, for the
# in-app VideoPlayer. Queries `app._video` fresh on every tick (rather than
# capturing one VideoPlayer instance) since the active player gets replaced/
# closed whenever the operator stops or re-projects a video.
# ─────────────────────────────────────────────────────────────────────────────
class VideoPlayerWidget(ctk.CTkFrame):
    def __init__(self, master, app: "App", **kw):
        super().__init__(master, **kw)
        self._app = app
        self._dragging = False
        self._alive = True

        self._seek = ctk.CTkSlider(self, from_=0, to=1000, command=self._on_drag,
                                   progress_color=ACCENT, button_color=ACCENT,
                                   button_hover_color=ACCENT_HOVER, fg_color=SURFACE_3)
        self._seek.set(0)
        self._seek.pack(fill="x", padx=8, pady=(6, 2))
        self._seek.bind("<ButtonPress-1>", lambda e: setattr(self, "_dragging", True))
        self._seek.bind("<ButtonRelease-1>", self._on_seek_release)

        self._time_lbl = ctk.CTkLabel(self, text="00:00 / 00:00", font=theme.font_body(11),
                                      text_color=TEXT_TERTIARY)
        self._time_lbl.pack()

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=(4, 6))
        _circle(row, "↺", 34, 17, SURFACE_3, TEXT_SECONDARY, font=theme.font_body(15),
               hover_color=SURFACE_4, command=self._restart).pack(side="left", padx=3)
        self._play_btn = _circle(row, "⏸", 40, 20, ACCENT, "white", font=theme.font_body(15),
                                 hover_color=ACCENT_HOVER, command=self._toggle)
        self._play_btn.pack(side="left", padx=3)
        _circle(row, "■", 34, 17, SURFACE_3, TEXT_SECONDARY, font=theme.font_body(13),
               hover_color=SURFACE_4, command=self._app._stop_projection).pack(side="left", padx=3)

        self.bind("<Destroy>", lambda e: setattr(self, "_alive", False))
        self._update()

    def _v(self):
        return self._app._video

    def _toggle(self):
        v = self._v()
        if v:
            v.toggle()

    def _restart(self):
        v = self._v()
        if v:
            v.restart()

    def _on_drag(self, _v):
        # while dragging, only update the time label preview
        if self._dragging:
            v = self._v()
            dur = (v.duration if v else 0) or 0
            self._time_lbl.configure(
                text=f"{_fmt_time((self._seek.get() / 1000.0) * dur)} / {_fmt_time(dur)}")

    def _on_seek_release(self, _e):
        v = self._v()
        if v and v.duration > 0:
            v.seek((self._seek.get() / 1000.0) * v.duration)
        self._dragging = False

    def _update(self):
        if not self._alive:
            return
        try:
            v = self._v()
            if v is None:
                self.after(300, self._update)
                return
            dur = v.duration or 1
            if not self._dragging:
                self._seek.set(min(1000, (v.position / dur) * 1000))
                self._time_lbl.configure(text=f"{_fmt_time(v.position)} / {_fmt_time(dur)}")
            self._play_btn.lbl.configure(text="▶" if v.is_paused else "⏸")
            self.after(300, self._update)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Pause-music mini player — same visual family as AudioPlayerWidget/
# VideoPlayerWidget, but PlaylistChannel (the pause-music backend) is a plain
# pygame Channel with no position/duration API, so there is no seek bar here:
# just prev / play-pause / skip / stop and the current track name.
# ─────────────────────────────────────────────────────────────────────────────
class PauseMusicWidget(ctk.CTkFrame):
    def __init__(self, master, app: "App", **kw):
        super().__init__(master, **kw)
        self._app = app
        self._alive = True

        ctk.CTkLabel(self, text="MUSICA PAUSA", font=theme.font_label(11),
                     text_color=TEXT_LABEL, anchor="w").pack(fill="x", padx=8, pady=(6, 0))
        self._track_lbl = ctk.CTkLabel(self, text="Nessuna musica in riproduzione",
                                       font=theme.font_body(10), text_color=TEXT_FAINT,
                                       anchor="w", wraplength=240)
        self._track_lbl.pack(fill="x", padx=8, pady=(2, 4))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=(4, 8))
        _circle(row, "⏮", 34, 17, SURFACE_3, TEXT_SECONDARY, font=theme.font_body(13),
               hover_color=SURFACE_4, command=self._prev).pack(side="left", padx=3)
        self._play_btn = _circle(row, "▶", 40, 20, ACCENT, "white", font=theme.font_body(15),
                                 hover_color=ACCENT_HOVER, command=self._toggle)
        self._play_btn.pack(side="left", padx=3)
        _circle(row, "⏭", 34, 17, SURFACE_3, TEXT_SECONDARY, font=theme.font_body(13),
               hover_color=SURFACE_4, command=self._skip).pack(side="left", padx=3)
        _circle(row, "■", 34, 17, SURFACE_3, TEXT_SECONDARY, font=theme.font_body(13),
               hover_color=SURFACE_4, command=self._stop).pack(side="left", padx=3)

        self.bind("<Destroy>", lambda e: setattr(self, "_alive", False))
        self._update()

    def _mgr(self):
        return self._app._audio

    def _active(self):
        a = self._mgr()
        return a.pause_music_is_playing() or a.pause_music_is_paused()

    def _toggle(self):
        a = self._mgr()
        if a.pause_music_is_playing():
            a.pause_pause_music()
        elif a.pause_music_is_paused():
            a.resume_pause_music()
        else:
            self._app._start_pause_music()

    def _prev(self):
        if self._active():
            self._mgr().prev_pause_music()

    def _skip(self):
        if self._active():
            self._mgr().skip_pause_music()

    def _stop(self):
        self._mgr().stop_pause_music()

    def _update(self):
        if not self._alive:
            return
        try:
            a = self._mgr()
            playing = a.pause_music_is_playing()
            track = a.current_pause_track()
            if self._active() and track:
                self._track_lbl.configure(text=os.path.basename(track))
            else:
                self._track_lbl.configure(text="Nessuna musica in riproduzione")
            self._play_btn.lbl.configure(text="⏸" if playing else "▶")
            self.after(500, self._update)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Timer widget: [−] TIME [+]  +  Avvia/Pausa/Reset  + Proietta
# ─────────────────────────────────────────────────────────────────────────────
class TimerWidget(ctk.CTkFrame):
    def __init__(self, master, app: "App", **kw):
        super().__init__(master, **kw)
        self._app = app
        self._total = app._settings.get("timer_default_minutes", 10) * 60
        self._remaining = self._total
        self._running = False
        self._warned = False
        self._fade_started = False
        self._stop = threading.Event()
        self._alive = True

        disp = ctk.CTkFrame(self, fg_color="transparent")
        disp.pack(pady=(6, 4))
        _circle(disp, "−", 40, 20, SURFACE_3, TEXT_SECONDARY, font=theme.font_body(20),
               hover_color=SURFACE_4, command=lambda: self._adjust(-60)).pack(side="left", padx=8)
        self._lbl = ctk.CTkLabel(disp, text=_fmt_time(self._remaining),
                                 font=theme.font_title(), text_color=TEXT_PRIMARY, width=130)
        self._lbl.pack(side="left")
        _circle(disp, "+", 40, 20, SURFACE_3, TEXT_SECONDARY, font=theme.font_body(20),
               hover_color=SURFACE_4, command=lambda: self._adjust(60)).pack(side="left", padx=8)

        presets = ctk.CTkFrame(self, fg_color="transparent")
        presets.pack(pady=4)
        for m in (5, 10, 15):
            _circle(presets, f"{m} min", None, 14, width=64, height=36,
                   fg_color=CARD_ROW, text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                   hover_color=SURFACE_4, command=lambda mm=m: self._set_minutes(mm)
                   ).pack(side="left", padx=3)

        self._start_btn = ctk.CTkButton(self, text="Avvia timer", height=36, corner_radius=13,
                                        font=theme.font_body(13, bold=True),
                                        fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                        command=self._toggle)
        self._start_btn.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkButton(self, text="Personalizza aspetto…", height=24, corner_radius=10,
                      font=theme.font_body(11, bold=True),
                      fg_color="transparent", text_color=ACCENT,
                      hover_color=SURFACE_3,
                      command=self._app._open_timer_appearance).pack()

        self.bind("<Destroy>", lambda e: setattr(self, "_alive", False))

    def _set_minutes(self, m):
        self._total = m * 60
        self._remaining = self._total
        if not self._running:
            self._refresh()

    def _adjust(self, delta):
        if self._running:
            self._remaining = max(0, self._remaining + delta)
        else:
            self._total = max(60, self._total + delta)
            self._remaining = self._total
        self._refresh()

    def _toggle(self):
        if self._running:
            self._running = False
            self._stop.set()
            self._start_btn.configure(text="Avvia timer")
        else:
            if self._remaining <= 0:
                self._remaining = self._total
            self._running = True
            self._warned = False
            self._fade_started = False
            self._stop.clear()
            self._start_btn.configure(text="Pausa")
            if self._app._settings.get("pause_music_autoplay", False) \
                    and not self._app._audio.pause_music_is_playing():
                self._app._start_pause_music()
            self._app._project_timer(self._remaining)   # show on projector
            threading.Thread(target=self._tick, daemon=True).start()

    def _reset(self):
        self._running = False
        self._stop.set()
        self._remaining = self._total
        self._warned = False
        self._fade_started = False
        self._start_btn.configure(text="Avvia timer")
        self._refresh()

    def _tick(self):
        while not self._stop.is_set() and self._remaining > 0:
            time.sleep(1)
            if self._stop.is_set():
                break
            self._remaining -= 1
            self._check_warn()
            self._safe(self._refresh)
            self._safe(self._app._update_timer_projection, self._remaining)
        if self._remaining <= 0 and not self._stop.is_set():
            self._running = False
            self._safe(lambda: self._start_btn.configure(text="Avvia timer"))
            if self._app._settings.get("timer_auto_bell", False):
                self._safe(self._app._ring_bell)

    # Pause music fades out over this many seconds and finishes exactly as
    # the warning sound fires, so the warning is never heard on top of it.
    _FADE_LEAD_SECONDS = 3

    def _check_warn(self):
        s = self._app._settings
        if not s.get("timer_warning_enabled", True):
            return
        warn_at = s.get("timer_warning_seconds", 60)
        if not self._fade_started and self._remaining <= warn_at + self._FADE_LEAD_SECONDS \
                and self._app._audio.pause_music_is_playing():
            self._fade_started = True
            self._app._audio.stop_pause_music(fade_ms=self._FADE_LEAD_SECONDS * 1000)
        if self._warned:
            return
        snd = s.get("timer_warning_sound", "")
        if self._remaining <= warn_at and snd:
            self._warned = True
            volume = s.get("timer_warning_volume", 100) / 100
            self._app._audio.play_warning(snd, volume=volume)

    def _project(self):
        self._app._project_timer(self._remaining)

    def _refresh(self):
        try:
            self._lbl.configure(text=_fmt_time(self._remaining))
        except Exception:
            pass

    def _safe(self, fn, *a):
        if not self._alive:
            return
        try:
            self.after(0, lambda: fn(*a))
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────
class App(ctk.CTk):
    NAV = [("scaletta", "scaletta", "Scaletta"), ("inni", "inno", "Inni"),
           ("bibbia", "bibbia", "Bibbia"), ("preghiere", "preghiere", "Preghiere"),
           ("media", "media", "Media"), ("impostazioni", "impostazioni", "Impostazioni")]

    def __init__(self):
        super().__init__()
        self._settings = cfg.load()
        ctk.set_appearance_mode(self._settings.get("appearance_mode", "System"))
        ctk.set_default_color_theme("blue")

        self.title("Gestione programma SDARM")
        self.geometry(self._settings.get("window_geometry", "1280x720"))
        self.minsize(960, 640)
        self.configure(fg_color=theme.BG)

        self._history = History(self._settings.get("max_history", 100))
        self._history.load_from_dicts(self._settings.get("hymn_history", []),
                                      self._settings.get("verse_history", []))

        sched = self._settings.get("schedule", [])
        self._schedule = Schedule.from_list(sched) if sched else Schedule.default()
        self._prayers = prayers_store.load()
        self._prayer_selected_ids = set()

        self._audio = AudioManager()
        self._hymns: List[Hymn] = []
        self._db_loading = False

        self._bible = None
        if _HAS_BIBLE:
            self._bible = BibleLibrary()
            self._bible.load_active_from_settings(self._settings.get("bible_versions", {}))

        # picker state
        self._picker_slot: Optional[Slot] = None
        self._picker_type: Optional[str] = None

        # selections
        self._sel_hymn: Optional[Hymn] = None
        self._sel_slot: Optional[Slot] = None

        # bible browsing state — book/chapter/verse are shown in three
        # always-visible columns (see _render_bib_columns), so the current
        # selection doubles as "what's highlighted", no separate "last
        # opened" state needed.
        self._bib_book: Optional[int] = None
        self._bib_book_name = ""
        self._bib_chapter: Optional[int] = None
        self._bib_testament = "AT"
        # Created here (not lazily in the Bibbia view builder) so that
        # projecting a verse from a lezione citation works even if the user
        # hasn't visited the Bibbia tab yet this session — _project_verse_ref
        # references both unconditionally.
        self._bib_tab = tk.StringVar(value="Naviga")
        self._bib_search = tk.StringVar()
        self._lang_extra = set(self._settings.get("bible_extra_langs", []))

        self._left_w = self._settings.get("left_panel_width", 240)
        self._right_w = self._settings.get("right_panel_width", 240)
        self._inni_preview_w = self._settings.get("inni_preview_width", 520)
        self._left_collapsed = False
        self._right_collapsed = False
        self._sec_open = {}  # section.id -> bool, persists expand/collapse across re-renders

        self._projection: Optional[ProjectionWindow] = None
        self._proj_mode = None  # "timer" | "verse" | "slides" | ...
        self._np_video_dragging = False  # right-panel video seek slider mid-drag guard
        self._np_audio_dragging = False  # right-panel audio seek slider mid-drag guard

        self._modal = None  # active overlay frame
        self._projected = set()  # slot ids already projected this session
        self._video = None       # active VideoPlayer (in-app video)

        self._dnd_drop_targets: list = []  # [(widget, slot)] for global drop dispatch

        # initialise tkdnd BEFORE _build_ui so _require loads the extension
        if _HAS_DND:
            try:
                TkinterDnD._require(self)
            except Exception as e:
                print(f"[DnD] _require failed: {e}")

        self._build_ui()
        self._setup_dnd()  # register drop targets
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._load_db_async()

        # At construction time the window isn't mapped to screen yet, so any
        # CTkScrollableFrame built with a non-default panel width (loaded from
        # settings) can't measure its true container size and stays stuck at
        # its intrinsic width — leaving an empty band before the divider. Force
        # one rebuild once the window has actually been realized on screen.
        self.after(150, self._refresh_panels_after_startup)
        self.after(400, self._check_today_lesson)
        self.after(600, self._maybe_show_tutorial)
        self.after(30000, self._periodic_gc)

    # ── UI scaffold ────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        sb = ctk.CTkFrame(self, width=_NAV_W, corner_radius=0, fg_color=CARD_ROW,
                          border_width=0)
        sb.grid(row=0, column=0, sticky="ns")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(len(self.NAV) - 1, weight=1)  # spacer before the last icon
        self._nav_btns = {}
        self._nav_icon_lbls = {}
        self._nav_icon_names = {}
        self._current = None
        for i, (name, icon_name, _t) in enumerate(self.NAV):
            self._nav_icon_names[name] = icon_name
            # CTkButton can't be a true 40×40 circle: corner_radius reserves
            # minsize padding of `corner_radius` on EACH side internally, so
            # corner_radius=20 (half the button) alone demands 40px just for
            # padding before any image is placed — CTkButton then silently
            # grows past the requested width to fit the icon too (measured:
            # 62×40, not 40×40), and a radius=20 circle stretched over that
            # wider rect renders as a flat-topped/bottomed pill, not a circle
            # — the "cut off" look. A plain CTkFrame has no such image-driven
            # sizing logic, so it stays exactly 40×40; the icon is a
            # separately placed, purely decorative label on top, with click/
            # hover handled manually. "impostazioni" is the last entry and
            # sits in the expanding spacer row, landing at the rail's bottom.
            cell = ctk.CTkFrame(sb, width=40, height=40, corner_radius=20,
                                fg_color="transparent", cursor="hand2")
            cell.grid_propagate(False)
            is_last = (i == len(self.NAV) - 1)
            cell.grid(row=i, column=0, padx=(_NAV_W - 40) // 2,
                      pady=(5, 16) if is_last else 5, sticky="s" if is_last else "n")

            icon_lbl = ctk.CTkLabel(cell, text="", image=theme.icon(icon_name, "muted", size=18),
                                    cursor="hand2")
            icon_lbl.place(relx=0.5, rely=0.5, anchor="center")

            def on_enter(_e, c=cell, n=name):
                if self._current != n:
                    c.configure(fg_color=BTN_SECONDARY_HOVER)

            def on_leave(_e, c=cell, n=name):
                if self._current != n:
                    c.configure(fg_color="transparent")

            for w in (cell, icon_lbl):
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
                w.bind("<Button-1>", lambda _e, n=name: self._nav(n))
            self._nav_btns[name] = cell
            self._nav_icon_lbls[name] = icon_lbl

        main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # No shared topbar — the mockup has none; each screen carries its own
        # title (date+time inline in the scaletta's left panel, a screen
        # title elsewhere). `_proj_pill`/`_stop_proj_btn` stay as real,
        # never-mapped widgets purely so the ~20 existing call sites that
        # call .configure(text=...) on them elsewhere in this file keep
        # working untouched — the actual visible "in proiezione" status now
        # lives in the scaletta's right panel (_build_right_panel).
        self._proj_pill = ctk.CTkLabel(self, text="○ Niente in proiezione",
                                       font=("", 11), text_color=MUTED)
        self._stop_proj_btn = ctk.CTkButton(self, text="Togli proiezione",
                                            state="disabled", command=self._stop_projection)

        self._content = ctk.CTkFrame(main, corner_radius=0, fg_color="transparent")
        self._content.grid(row=0, column=0, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._bind_global_keys()

        self._nav("scaletta")

    def _bind_global_keys(self):
        """Root-level key bindings. A separate method (not inline in
        _build_ui) because the tutorial overlay temporarily replaces the
        arrow-key bindings while it's open and calls this again on close to
        restore them."""
        # advance/retreat a projected slideshow from anywhere in the app
        # PageDown/PageUp: standard presenter-remote keys
        self.bind("<Next>", lambda e: self._slide_next())
        self.bind("<Prior>", lambda e: self._slide_prev())
        # Right/Left arrows: some presenter remotes use these; only act when
        # the current projection mode actually supports advance/retreat
        # (see _proj_registry — this is derived, not a hardcoded mode list).
        self.bind("<Right>", lambda e: self._proj_can_nav() and self._slide_next())
        self.bind("<Left>", lambda e: self._proj_can_nav() and self._slide_prev())
        # Quick projection commands — Ctrl+letter would collide with normal
        # typing in search/text boxes elsewhere in the app, so these use
        # Ctrl+number instead (never typed as text).
        self.bind("<Control-Key-1>", lambda e: self._proj_quick_cmd("black"))
        self.bind("<Control-Key-2>", lambda e: self._proj_quick_cmd("background"))
        self.bind("<Control-Key-3>", lambda e: self._proj_quick_cmd("freeze"))

    def _nav(self, name: str):
        self._close_modal()
        for n, cell in self._nav_btns.items():
            active = (n == name)
            cell.configure(fg_color=ACCENT if active else "transparent")
            self._nav_icon_lbls[n].configure(
                image=theme.icon(self._nav_icon_names[n], "white" if active else "muted", size=18))
        for w in self._content.winfo_children():
            w.destroy()
        {"scaletta": self._view_scaletta, "inni": self._view_inni,
         "bibbia": self._view_bibbia, "preghiere": self._view_preghiere,
         "media": self._view_media,
         "impostazioni": self._view_settings}[name]()
        self._current = name

    # ── In-app modal overlay (NOT a new window) ─────────────────────────────────
    def _close_modal(self):
        if self._modal is not None:
            try:
                self._modal.destroy()
            except Exception:
                pass
            self._modal = None

    def _open_modal(self, title: str, build: Callable[[ctk.CTkFrame], None],
                    width: int = 460, height: int = 360):
        self._close_modal()
        # Tk/customtkinter has no real alpha compositing between sibling
        # widgets — a "transparent" CTkFrame just paints itself with its
        # resolved bg_color (a solid rect), it does NOT show whatever is
        # drawn underneath. Placed over the *whole* root window that used to
        # paint over the nav rail and topbar too, making the entire app
        # appear to vanish behind a flat color the instant any modal opened.
        # Scoping the scrim to self._content only (below the topbar, right of
        # the nav rail) keeps those always visible, so the app never fully
        # disappears — the honest fix available without OS-level screen
        # capture (which would need extra permissions on both Mac and
        # Windows just to open an "Aggiungi elemento" dialog).
        scrim = ctk.CTkFrame(self._content, fg_color="transparent")
        scrim.place(relx=0, rely=0, relwidth=1, relheight=1)
        scrim.bind("<Button-1>", lambda e: self._close_modal())

        card = ctk.CTkFrame(scrim, width=width, height=height, corner_radius=14,
                            fg_color=CARD, border_width=0)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)
        card.bind("<Button-1>", lambda e: "break")

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(head, text=title, font=theme.font_section(17),
                     text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkButton(head, text="×", width=26, height=26, corner_radius=11,
                      fg_color=SURFACE_3, text_color=TEXT_TERTIARY,
                      hover_color=SURFACE_4,
                      command=self._close_modal).pack(side="right")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(4, 14))
        build(body)
        self._modal = scrim

    def _ask_text(self, title: str, on_ok: Callable[[str], None],
                  initial: str = "", label: str = "Nome:"):
        def build(body):
            ctk.CTkLabel(body, text=label, anchor="w").pack(fill="x")
            entry = ctk.CTkEntry(body)
            entry.pack(fill="x", pady=(4, 14))
            entry.insert(0, initial)
            entry.focus_set()

            def confirm():
                val = entry.get().strip()
                self._close_modal()
                if val:
                    on_ok(val)
            entry.bind("<Return>", lambda e: confirm())
            btns = ctk.CTkFrame(body, fg_color="transparent")
            btns.pack(fill="x")
            ctk.CTkButton(btns, text="Annulla", width=100, fg_color=BTN_SECONDARY,
                          text_color=TEXT_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          command=self._close_modal).pack(side="right", padx=4)
            ctk.CTkButton(btns, text="Conferma", width=100,
                          command=confirm).pack(side="right", padx=4)
        self._open_modal(title, build, width=420, height=230)

    def _ask_confirm(self, title: str, message: str, on_yes: Callable[[], None],
                     confirm_text: str = "Elimina"):
        def build(body):
            ctk.CTkLabel(body, text=message, wraplength=380,
                         justify="left").pack(fill="x", pady=(0, 16))
            btns = ctk.CTkFrame(body, fg_color="transparent")
            btns.pack(fill="x")

            def yes():
                self._close_modal()
                on_yes()
            ctk.CTkButton(btns, text="Annulla", width=100, fg_color=BTN_SECONDARY,
                          text_color=TEXT_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          command=self._close_modal).pack(side="right", padx=4)
            ctk.CTkButton(btns, text=confirm_text, width=100, fg_color=DANGER,
                          hover_color=DANGER_HOVER, command=yes).pack(side="right", padx=4)
        self._open_modal(title, build, width=420, height=220)

    def _info(self, title: str, message: str):
        def build(body):
            ctk.CTkLabel(body, text=message, wraplength=380,
                         justify="left").pack(fill="x", pady=(0, 16))
            ctk.CTkButton(body, text="OK", width=100,
                          command=self._close_modal).pack()
        self._open_modal(title, build, width=420, height=200)

    # ════════════════════════════════════════════════════════════════════════
    #  SCALETTA
    # ════════════════════════════════════════════════════════════════════════
    def _view_scaletta(self):
        outer = ctk.CTkFrame(self._content, fg_color="transparent")
        outer.pack(fill="both", expand=True)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(2, weight=1)
        self._scaletta_outer = outer

        # ── LEFT ──
        if self._left_collapsed:
            strip = ctk.CTkFrame(outer, width=30, corner_radius=0)
            strip.grid(row=0, column=0, sticky="ns")
            strip.grid_propagate(False)
            ctk.CTkButton(strip, text="▶", width=24, height=30,
                          command=self._toggle_left).pack(pady=8)
        else:
            self._left_panel = ctk.CTkFrame(outer, width=self._left_w, corner_radius=0,
                                            fg_color=theme.BG)
            self._left_panel.grid(row=0, column=0, sticky="ns")
            # The panel's children are pack()-managed, so pack_propagate(False)
            # (not grid_propagate) is what makes configure(width=…) actually
            # stick — otherwise the panel shrink-wraps to its content and the
            # resize divider appears to do nothing.
            self._left_panel.grid_propagate(False)
            self._left_panel.pack_propagate(False)
            self._build_program_list()
            # Deliberately not draggable (no cursor hint, no bindings): a
            # narrow left panel overlaps the date/clock header text, so its
            # width stays fixed at whatever was last saved instead of being
            # user-resizable.
            ld = ctk.CTkFrame(outer, width=_DIVIDER_W, fg_color=BORDER)
            ld.grid(row=0, column=1, sticky="ns")

        # ── CENTER ──
        self._center = ctk.CTkFrame(outer, fg_color="transparent")
        self._center.grid(row=0, column=2, sticky="nsew")
        self._center.grid_rowconfigure(0, weight=1)
        self._center.grid_columnconfigure(0, weight=1)
        # Built once and reused (only their children are destroyed/recreated
        # in _render_center) — a freshly-constructed CTkScrollableFrame briefly
        # shows Tk's raw white canvas background before customtkinter applies
        # the theme color at the end of its __init__, which flashed on every
        # single slot click when "frame" used to be recreated there each time.
        self._center_empty = ctk.CTkFrame(self._center, fg_color="transparent")
        self._center_scroll = ctk.CTkScrollableFrame(self._center, fg_color="transparent")
        self._render_center()

        # ── RIGHT ──
        if self._right_collapsed:
            strip = ctk.CTkFrame(outer, width=30, corner_radius=0)
            strip.grid(row=0, column=4, sticky="ns")
            strip.grid_propagate(False)
            ctk.CTkButton(strip, text="◀", width=24, height=30,
                          command=self._toggle_right).pack(pady=8)
        else:
            rd = ctk.CTkFrame(outer, width=_DIVIDER_W, cursor="sb_h_double_arrow",
                              fg_color=BORDER)
            rd.grid(row=0, column=3, sticky="ns")
            rd.bind("<B1-Motion>", self._resize_right)
            rd.bind("<ButtonRelease-1>", self._resize_right_end)
            self._right_panel = ctk.CTkFrame(outer, width=self._right_w, corner_radius=0,
                                             fg_color=theme.BG)
            self._right_panel.grid(row=0, column=4, sticky="ns")
            self._right_panel.grid_propagate(False)
            self._right_panel.pack_propagate(False)
            self._build_right_panel()

    def _refresh_panels_after_startup(self):
        if hasattr(self, "_left_panel") and self._left_panel.winfo_exists():
            self._build_program_list()
        if hasattr(self, "_right_panel") and self._right_panel.winfo_exists():
            self._build_right_panel()

    def _toggle_left(self):
        self._left_collapsed = not self._left_collapsed
        self._view_scaletta_refresh()

    def _toggle_right(self):
        self._right_collapsed = not self._right_collapsed
        self._view_scaletta_refresh()

    def _view_scaletta_refresh(self):
        for w in self._content.winfo_children():
            w.destroy()
        self._view_scaletta()

    def _build_program_list(self):
        for w in self._left_panel.winfo_children():
            w.destroy()
        # header: date + live clock, and an item count — replaces the old
        # shared topbar, which the mockup doesn't have at all.
        head = ctk.CTkFrame(self._left_panel, fg_color="transparent")
        head.pack(side="top", fill="x", padx=14, pady=(16, 12))
        date_row = ctk.CTkFrame(head, fg_color="transparent")
        date_row.pack(fill="x")
        # Clock packed FIRST (side=right): pack allocates space in packing
        # order, so on a narrow panel (fresh installs default to 240px) the
        # wide 28px date label can no longer push the clock out of view —
        # that made "data e ora" invisible on a brand-new install. The date
        # label wraps onto a second line instead of clipping.
        self._clock_lbl = ctk.CTkLabel(date_row, text="", font=theme.font_section(16, bold=False),
                                       text_color=TEXT_TERTIARY, anchor="e")
        self._clock_lbl.pack(side="right", padx=(8, 0), anchor="n", pady=(6, 0))
        date_lbl = ctk.CTkLabel(date_row, text=_today_title(), font=theme.font_title(),
                                text_color=TEXT_PRIMARY, anchor="w", justify="left")
        date_lbl.pack(side="left", fill="x", expand=True)
        _auto_wrap_label(date_lbl)
        self._tick_clock()
        n_slots = sum(len(sec.slots) for sec in self._schedule.sections)
        ctk.CTkLabel(head, text=f"{n_slots} element{'o' if n_slots == 1 else 'i'} nella scaletta",
                     font=theme.font_body(12), text_color=TEXT_FAINT, anchor="w"
                     ).pack(fill="x", pady=(2, 0))

        # bottom bar first (so it stays pinned), then scroll fills the rest
        bottom = ctk.CTkFrame(self._left_panel, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=8, pady=8)
        # Dashed-border look isn't available on CTkButton (no dash pattern on
        # its rounded-rect draw) — a thin solid BORDER-colored outline on a
        # transparent fill is the closest honest approximation.
        ctk.CTkButton(bottom, text="+  Aggiungi programma", height=34,
                      corner_radius=13, fg_color="transparent",
                      border_width=1, border_color=BORDER,
                      text_color=TEXT_SECONDARY, hover_color=SURFACE_3,
                      font=theme.font_body(13, bold=True),
                      command=self._add_section).pack(fill="x")
        row2 = ctk.CTkFrame(bottom, fg_color="transparent")
        row2.pack(fill="x", pady=(6, 0))
        row2.grid_columnconfigure((0, 1, 2), weight=1, uniform="bottombtn")
        ctk.CTkButton(row2, text="Salva", height=28, corner_radius=12,
                      fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                      text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                      command=self._save_template_quick
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(row2, text="Carica", height=28, corner_radius=12,
                      fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                      text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                      command=self._open_templates
                      ).grid(row=0, column=1, sticky="ew", padx=3)
        ctk.CTkButton(row2, text="Azzera", height=28, corner_radius=12,
                      fg_color=DANGER_FILL, hover_color=DANGER_FILL_HOVER,
                      text_color=DANGER_FILL_TEXT, font=theme.font_body(12, bold=True),
                      command=self._confirm_reset_scaletta
                      ).grid(row=0, column=2, sticky="ew", padx=(3, 0))
        self._sections_box = ctk.CTkScrollableFrame(self._left_panel, fg_color="transparent")
        self._sections_box.pack(fill="both", expand=True, padx=4, pady=(6, 0))
        self._render_sections()

    def _tick_clock(self):
        if not hasattr(self, "_clock_lbl") or not self._clock_lbl.winfo_exists():
            return
        from datetime import datetime
        self._clock_lbl.configure(text=datetime.now().strftime("%H:%M"))
        # Single-loop guard: _build_program_list runs on every scaletta
        # rebuild and calls this again — without cancelling the previous
        # pending tick, each rebuild would ADD one more 1s loop (the old
        # loop's exists-check passes because self._clock_lbl now points to
        # the NEW label), silently multiplying wakeups over a long session.
        if getattr(self, "_clock_after_id", None):
            try:
                self.after_cancel(self._clock_after_id)
            except Exception:
                pass
        self._clock_after_id = self.after(1000, self._tick_clock)

    def _render_sections(self):
        # Rebuilding destroys and recreates every row, which resets the
        # scrollable frame's scroll position to the top — jarring since this
        # runs on every click/rename/drag, not just structural edits. Save and
        # restore the position around the rebuild so the list stays put.
        # Restoring it requires an update_idletasks() call (so the new
        # scrollregion is known before yview_moveto), but that call forces an
        # actual screen redraw — briefly showing the list at the top before it
        # snaps back, i.e. a one-frame flash. Unmapping the list for the
        # duration of the rebuild (pack_forget/pack) prevents anything from
        # being drawn until it's already in its final, correct state.
        canvas = getattr(self._sections_box, "_parent_canvas", None)
        scroll_pos = canvas.yview()[0] if canvas else None
        self._sections_box.pack_forget()
        for w in self._sections_box.winfo_children():
            w.destroy()
        self._slot_rows = {}  # slot.id -> row frame, so selection can restyle in place
        self._section_wraps = {}  # section.id -> wrap frame, for live drag re-packing
        for idx, sec in enumerate(self._schedule.sections):
            self._render_section(sec, idx)
        if canvas and scroll_pos:
            self._sections_box.update_idletasks()
            canvas.yview_moveto(scroll_pos)
        self._sections_box.pack(fill="both", expand=True, padx=4, pady=(6, 0))

    def _render_section(self, sec: Section, idx: int):
        # No card background around the whole section — the mockup keeps
        # section headers as bare labels on the panel background; only
        # individual slot rows below get the card treatment.
        wrap = ctk.CTkFrame(self._sections_box, corner_radius=0, fg_color="transparent")
        wrap.pack(fill="x", pady=3)
        wrap._section_id = sec.id  # for drag-reorder hit-testing
        self._section_wraps[sec.id] = wrap

        header = ctk.CTkFrame(wrap, fg_color="transparent")
        header.pack(fill="x")
        # Grid layout: col0=handle, col1=arrow, col2=name(expands), col3=sacts(hidden), col4=plus
        header.grid_columnconfigure(2, weight=1)

        is_open = self._sec_open.setdefault(sec.id, True)
        slots_frame = ctk.CTkFrame(wrap, fg_color="transparent")

        handle = ctk.CTkLabel(header, text="⠿", width=14, text_color=TEXT_FAINT, cursor="fleur")
        handle.grid(row=0, column=0, padx=(6, 0), pady=4)
        handle.bind("<ButtonPress-1>", lambda e: self._sdrag_start(sec))

        arrow = ctk.CTkButton(header, text="▼" if is_open else "▶", width=24, height=24,
                              fg_color="transparent", text_color=TEXT_TERTIARY,
                              hover_color=SURFACE_3)
        arrow._is_collapse = True
        arrow.grid(row=0, column=1, pady=4)

        def toggle():
            self._sec_open[sec.id] = not self._sec_open[sec.id]
            arrow.configure(text="▼" if self._sec_open[sec.id] else "▶")
            if self._sec_open[sec.id]:
                slots_frame.pack(fill="x", padx=8, pady=(0, 6))
            else:
                slots_frame.pack_forget()
        arrow.configure(command=toggle)

        name = ctk.CTkLabel(header, text=sec.name.upper(), font=theme.font_label(11),
                            text_color=TEXT_LABEL, anchor="w", justify="left")
        name.grid(row=0, column=2, sticky="ew", padx=6, pady=6)
        name.bind("<Double-Button-1>", lambda e: self._rename_section(sec))
        _auto_wrap_label(name)

        # sacts: shown on hover via grid(), hidden with grid_remove() — takes no space when hidden
        sacts = ctk.CTkFrame(header, fg_color="transparent")
        s_btn_ren = ctk.CTkButton(sacts, text="✎", width=24, height=24, fg_color="transparent",
                                  text_color=TEXT_TERTIARY, hover_color=SURFACE_3,
                                  command=lambda: self._rename_section(sec))
        s_btn_ren.pack(side="left", padx=1)
        s_btn_del = ctk.CTkButton(sacts, text="✕", width=24, height=24, fg_color="transparent",
                                  text_color=TEXT_TERTIARY, hover_color=DANGER_HOVER,
                                  command=lambda: self._delete_section(sec))
        s_btn_del.pack(side="left", padx=1)
        # sacts not gridded initially

        plus_btn = ctk.CTkButton(header, text="＋", width=22, height=22, corner_radius=10,
                                 fg_color=SURFACE_3, text_color=TEXT_SECONDARY,
                                 hover_color=SURFACE_4,
                                 command=lambda: self._add_slot(sec))
        plus_btn.grid(row=0, column=4, padx=(0, 6), pady=4)

        def sshow(_e=None):
            sacts.grid(row=0, column=3, pady=4)

        def shide(_e=None):
            sacts.grid_remove()

        for w in (header, name, arrow, handle, plus_btn, sacts, s_btn_ren, s_btn_del):
            w.bind("<Enter>", sshow)
        wrap.bind("<Leave>", lambda e: self.after(80, lambda: self._maybe_hide(wrap, shide)))

        if is_open:
            slots_frame.pack(fill="x", padx=8, pady=(0, 6))
        if not sec.slots:
            empty = ctk.CTkLabel(slots_frame, text="vuoto — usa ＋ per aggiungere",
                                 text_color=MUTED, font=("", 11))
            empty.pack(anchor="w", padx=6, pady=2)
        for si, slot in enumerate(sec.slots):
            self._render_slot_row(slots_frame, sec, slot, si)

    def _maybe_hide(self, wrap, hide):
        try:
            x, y = self.winfo_pointerxy()
            w = self.winfo_containing(x, y)
            while w is not None:
                if w == wrap:
                    return  # pointer still inside the section wrap
                w = getattr(w, "master", None)
            hide()
        except Exception:
            hide()

    _FILEABLE = ("presentazione", "documento", "audio", "video", "immagine")

    def _slot_value(self, slot: Slot):
        """Return (text, filled) for the slot-row title.

        A user-set custom title (stored in slot.data["title"] via the ✎/
        double-click rename) overrides the *displayed text* but never the
        `filled` flag — so e.g. an empty inno that's been named still counts
        as not-filled and clicking it still opens the picker.
        """
        text, filled = self._derived_slot_value(slot)
        custom = (slot.data.get("title") or "").strip()
        if custom:
            return (custom, filled)
        return (text, filled)

    def _derived_slot_value(self, slot: Slot):
        """Return (text, filled) derived from the slot's actual content."""
        t = slot.slot_type
        if t == "inno":
            h = slot.data.get("hymn")
            return (f"{h['number']} — {h['title']}", True) if h else ("— scegli —", False)
        if t == "versetto":
            v = slot.data.get("verse")
            return (v["ref"], True) if v else ("— scegli —", False)
        if t in self._FILEABLE:
            p = slot.data.get("path")
            return (os.path.basename(p), True) if p else ("— scegli file —", False)
        if t == "lezione":
            _s, les = self._current_lesson()
            if les:
                return (les.get("title") or les.get("titolo") or "Lezione", True)
            return ("— nessuna —", False)
        if t == "timer":
            mins = slot.data.get("minutes", self._settings.get("timer_default_minutes", 10))
            return (f"{mins} min", True)
        if t == "testo":
            txt = slot.data.get("text", "")
            return ((txt.split(chr(10))[0][:24] or "—"), bool(txt))
        if t == "preghiera":
            n = len(self._prayers)
            return (f"{n} richiest{'a' if n == 1 else 'e'}", True)
        if slot.display_name:
            return (slot.display_name, True)
        return ("", True)

    def _restyle_slot_selection(self, prev_slot, new_slot):
        """Recolor just the previously/newly selected row in place — avoids
        rebuilding the whole schedule list for something that's only a
        background-color change on at most two existing widgets."""
        rows = getattr(self, "_slot_rows", {})
        if prev_slot is not None:
            r = rows.get(prev_slot.id)
            if r is not None and r.winfo_exists():
                r.configure(fg_color=CARD_ROW, border_width=0)
        if new_slot is not None:
            r = rows.get(new_slot.id)
            if r is not None and r.winfo_exists():
                r.configure(fg_color=SEL_BG, border_width=1, border_color=SEL_BORDER)

    def _render_slot_row(self, parent, sec: Section, slot: Slot, idx: int):
        t = slot.slot_type
        cat_color = SLOT_COLORS.get(t, MUTED)
        selected = (self._sel_slot is slot)
        bg = SEL_BG if selected else CARD_ROW
        row = ctk.CTkFrame(parent, corner_radius=13, fg_color=bg,
                           border_width=1 if selected else 0, border_color=SEL_BORDER)
        row.pack(fill="x", pady=2)
        row._slot_id = slot.id
        row._sec_id = sec.id
        self._slot_rows[slot.id] = row

        value, filled = self._slot_value(slot)
        type_text = SLOT_LABELS.get(t, t.capitalize()).upper()
        _invis = bg if isinstance(bg, str) else bg[1]

        if value:
            # ── TOP BAR: dot + type label left, ✎✕ right (appear on hover) ──
            top = ctk.CTkFrame(row, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(7, 0))
            top.bind("<ButtonPress-1>", lambda e: self._drag_start(sec, slot, parent))

            dot_sym = "●" if slot.id in self._projected else "○"
            dotcol = ACTIVE_GREEN if slot.id in self._projected else BORDER
            dot_lbl = ctk.CTkLabel(top, text=dot_sym, width=16, font=("", 10),
                                   text_color=dotcol)
            dot_lbl.pack(side="left")

            type_lbl = ctk.CTkLabel(top, text=type_text, font=theme.font_label(10),
                                    text_color=cat_color, anchor="w")
            type_lbl.pack(side="left")

            acts = ctk.CTkFrame(top, fg_color="transparent")
            btn_ren = ctk.CTkButton(acts, text="✎", width=24, height=18,
                                    fg_color="transparent", text_color=_invis,
                                    hover_color=SURFACE_3,
                                    command=lambda: self._rename_slot(slot))
            btn_ren.pack(side="left", padx=1)
            btn_del = ctk.CTkButton(acts, text="✕", width=24, height=18,
                                    fg_color="transparent", text_color=_invis,
                                    hover_color=DANGER_HOVER,
                                    command=lambda: self._delete_slot(sec, slot))
            btn_del.pack(side="left")
            acts.pack(side="right")

            # ── SEPARATOR ────────────────────────────────────────────────────
            ctk.CTkFrame(row, height=1, fg_color=BORDER_SUBTLE).pack(
                fill="x", padx=10, pady=(4, 0))

            # ── TITLE: full-width text ────────────────────────────────────────
            title_row = ctk.CTkFrame(row, fg_color="transparent")
            title_row.pack(fill="x", padx=10, pady=(6, 8))

            lbl = ctk.CTkLabel(title_row, text=value, anchor="w", justify="left",
                               font=theme.font_body(13, bold=filled) if filled
                               else ("", 13, "italic"),
                               text_color=(TEXT_TERTIARY if not filled else TEXT_PRIMARY))
            lbl.pack(side="left", fill="x", expand=True)

            _wc = [0]
            def _upd(_e=None, _lbl=lbl, _tr=title_row):
                w = _tr.winfo_width()
                if w > 10 and w != _wc[0]:
                    _wc[0] = w
                    _lbl.configure(wraplength=w)
            title_row.bind("<Configure>", _upd)
            title_row.after(120, _upd)

            click_targets = (row, top, type_lbl, title_row, lbl, dot_lbl)
            dbl_target = lbl

            def show(_e=None):
                btn_ren.configure(text_color=MUTED)
                btn_del.configure(text_color=MUTED)
            def hide(_e=None):
                btn_ren.configure(text_color=_invis)
                btn_del.configure(text_color=_invis)
            for w in (*click_targets, acts, btn_ren, btn_del):
                w.bind("<Enter>", show)

        else:
            # ── SIMPLE SLOT (no value): dot + type name, single line ──────────
            body = ctk.CTkFrame(row, fg_color="transparent")
            body.pack(fill="x", padx=10, pady=8)
            body.bind("<ButtonPress-1>", lambda e: self._drag_start(sec, slot, parent))

            dot_sym = "●" if slot.id in self._projected else "○"
            dotcol = ACTIVE_GREEN if slot.id in self._projected else BORDER
            dot_lbl = ctk.CTkLabel(body, text=dot_sym, width=16, font=("", 10),
                                   text_color=dotcol)
            dot_lbl.pack(side="left")

            lbl = ctk.CTkLabel(body, text=type_text, anchor="w", font=theme.font_label(11),
                               text_color=cat_color)
            lbl.pack(side="left", fill="x", expand=True)

            acts = ctk.CTkFrame(body, fg_color="transparent")
            btn_ren = ctk.CTkButton(acts, text="✎", width=24, height=20,
                                    fg_color="transparent", text_color=_invis,
                                    hover_color=SURFACE_3,
                                    command=lambda: self._rename_slot(slot))
            btn_ren.pack(side="left", padx=1)
            btn_del = ctk.CTkButton(acts, text="✕", width=24, height=20,
                                    fg_color="transparent", text_color=_invis,
                                    hover_color=DANGER_HOVER,
                                    command=lambda: self._delete_slot(sec, slot))
            btn_del.pack(side="left")
            acts.pack(side="right")

            click_targets = (row, body, lbl, dot_lbl)
            dbl_target = lbl

            def show(_e=None):
                btn_ren.configure(text_color=MUTED)
                btn_del.configure(text_color=MUTED)
            def hide(_e=None):
                btn_ren.configure(text_color=_invis)
                btn_del.configure(text_color=_invis)
            for w in (*click_targets, acts, btn_ren, btn_del):
                w.bind("<Enter>", show)

        def click(_e=None):
            # Every slot type — filled or not — only selects and shows in the
            # center panel when clicked from the schedule list; picking a file
            # / hymn / verse is reached exclusively via the "Scegli…"/"Cambia…"
            # button there, never by clicking the row directly.
            prev = self._sel_slot
            self._sel_slot = slot
            # Recolor just the two affected rows in place instead of rebuilding
            # the whole list (that used to destroy/recreate every row on a mere
            # selection click, which — even scroll-position-preserving — still
            # caused a visible flash as the list briefly went through an empty
            # state during the rebuild).
            self._restyle_slot_selection(prev, slot)
            self._render_center()
        for w in click_targets:
            w.bind("<Button-1>", click)
        dbl_target.bind("<Double-Button-1>", lambda e: self._rename_slot(slot))
        row.bind("<Leave>", lambda e: self.after(80, lambda: self._maybe_hide(row, hide)))

    # ── section drag-to-reorder (live) ────────────────────────────────────────
    def _sdrag_start(self, sec):
        self._sdrag = sec
        self._sdrag_last = 0.0
        self.bind("<B1-Motion>", self._sdrag_motion)
        self.bind("<ButtonRelease-1>", self._sdrag_end)

    def _sdrag_motion(self, _e):
        sec = getattr(self, "_sdrag", None)
        if not sec:
            return
        now = time.time()
        if now - getattr(self, "_sdrag_last", 0) < 0.05:
            return
        self._sdrag_last = now
        try:
            y = self.winfo_pointery()
            wraps = [w for w in self._sections_box.winfo_children()
                     if hasattr(w, "_section_id")]
            target = len(wraps) - 1
            for i, w in enumerate(wraps):
                if y < w.winfo_rooty() + w.winfo_height() // 2:
                    target = i
                    break
            cur = [s.id for s in self._schedule.sections].index(sec.id)
        except (ValueError, Exception):
            return
        if target != cur:
            s = self._schedule.sections.pop(cur)
            self._schedule.sections.insert(target, s)
            self._repack_sections_live()  # live shift — no rebuild, see below

    def _repack_sections_live(self):
        """Re-order the already-existing section wrap frames to match
        self._schedule.sections, without destroying/recreating anything and
        without ever unmapping them. A full _render_sections() rebuild runs
        ~20x/second during a live drag (throttled to 50ms) — destroying and
        recreating every row that often was visibly flashing. The first fix
        (pack_forget/pack per wrap) removed the destroy/recreate but still
        unmapped each wrap for an instant, which showed as white stripes —
        each CTkFrame's rounded-rect shape is drawn on its own canvas, and
        that canvas's raw (white) background peeks through at the edges while
        the shape is being redrawn after being remapped. pack(after=...) only
        reorders an already-mapped widget in place — it's never unmapped."""
        wraps = [self._section_wraps.get(sec.id) for sec in self._schedule.sections]
        wraps = [w for w in wraps if w is not None and w.winfo_exists()]
        for prev, cur in zip(wraps, wraps[1:]):
            cur.pack(after=prev)

    def _sdrag_end(self, _e):
        if getattr(self, "_sdrag", None):
            self._sdrag = None
            self.unbind("<B1-Motion>")
            self.unbind("<ButtonRelease-1>")
            self._save_schedule()
            self._render_sections()

    # ── slot drag-to-reorder (live) ───────────────────────────────────────────
    def _slot_rows_for(self, sec_id):
        rows = []
        def scan(w):
            for c in w.winfo_children():
                if getattr(c, "_slot_id", None) is not None and getattr(c, "_sec_id", None) == sec_id:
                    rows.append(c)
                scan(c)
        scan(self._sections_box)
        return rows

    def _drag_start(self, sec, slot, slots_frame):
        self._drag = {"sec": sec, "slot": slot}
        self._drag_last = 0.0
        # root-level bindings survive the re-renders during live reordering
        self.bind("<B1-Motion>", self._drag_motion)
        self.bind("<ButtonRelease-1>", self._drag_end)

    def _drag_motion(self, _e):
        d = getattr(self, "_drag", None)
        if not d:
            return
        now = time.time()
        if now - getattr(self, "_drag_last", 0) < 0.05:
            return
        self._drag_last = now
        sec, slot = d["sec"], d["slot"]
        try:
            y = self.winfo_pointery()
            rows = self._slot_rows_for(sec.id)
            if not rows:
                return
            target = len(rows) - 1
            for i, r in enumerate(rows):
                if y < r.winfo_rooty() + r.winfo_height() // 2:
                    target = i
                    break
            cur = sec.slots.index(slot)
        except (ValueError, Exception):
            return
        if target != cur:
            sec.slots.pop(cur)
            sec.slots.insert(target, slot)
            self._repack_slots_live(sec)  # live shift (no save yet) — no rebuild

    def _repack_slots_live(self, sec: Section):
        """Re-order the already-existing row widgets for this section to match
        sec.slots, without destroying/recreating anything and without ever
        unmapping them — same reasoning as _repack_sections_live."""
        rows = [self._slot_rows.get(s.id) for s in sec.slots]
        rows = [r for r in rows if r is not None and r.winfo_exists()]
        for prev, cur in zip(rows, rows[1:]):
            cur.pack(after=prev)

    def _drag_end(self, _e):
        if getattr(self, "_drag", None):
            self._drag = None
            self.unbind("<B1-Motion>")
            self.unbind("<ButtonRelease-1>")
            self._save_schedule()
            self._render_sections()

    # ── schedule templates ─────────────────────────────────────────────────────
    def _templates_dir(self):
        from core.paths import config_dir
        d = os.path.join(config_dir(), "templates")
        os.makedirs(d, exist_ok=True)
        return d

    def _list_templates(self):
        try:
            return sorted(f[:-5] for f in os.listdir(self._templates_dir())
                          if f.endswith(".json"))
        except Exception:
            return []

    def _save_template_quick(self):
        import json

        def build(body):
            ctk.CTkLabel(body, text="Nome scaletta:", anchor="w",
                         text_color=MUTED).pack(fill="x", pady=(0, 4))
            entry = ctk.CTkEntry(body, placeholder_text="Es. Culto del sabato")
            entry.pack(fill="x")
            entry.focus()

            def save():
                name = entry.get().strip()
                # Strip characters Windows forbids in filenames (macOS only
                # rejects "/" and ":") — the name doubles as the .json filename.
                name = re.sub(r'[\\/:*?"<>|]', "-", name).strip()
                if not name:
                    return
                path = os.path.join(self._templates_dir(), name + ".json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._schedule.to_list(), f, ensure_ascii=False, indent=2)
                self._close_modal()
            entry.bind("<Return>", lambda e: save())
            ctk.CTkButton(body, text="Salva", command=save).pack(anchor="e", pady=(12, 0))
        self._open_modal("Salva scaletta", build, width=380, height=160)

    def _open_templates(self):
        def build(body):
            ctk.CTkLabel(body, text="Scalette salvate:", anchor="w",
                         text_color=MUTED).pack(fill="x")
            lst = ctk.CTkScrollableFrame(body, fg_color="transparent", height=260)
            lst.pack(fill="both", expand=True, pady=4)
            names = self._list_templates()
            if not names:
                ctk.CTkLabel(lst, text="Nessuna scaletta salvata", text_color=MUTED).pack(pady=10)
            for nm in names:
                row = ctk.CTkFrame(lst, fg_color=CARD_ROW, corner_radius=10)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=nm, anchor="w").pack(side="left", fill="x",
                                                            expand=True, padx=8, pady=4)
                ctk.CTkButton(row, text="Carica", width=70, height=26,
                              command=lambda n=nm: self._load_template(n)).pack(side="left", padx=2)
                ctk.CTkButton(row, text="✕", width=30, height=26, fg_color="transparent",
                              text_color=MUTED, hover_color="#dc2626",
                              command=lambda n=nm: self._delete_template(n)).pack(side="left", padx=(0, 6))
        self._open_modal("Scalette salvate", build, width=420, height=400)

    def _load_template(self, name):
        import json
        path = os.path.join(self._templates_dir(), name + ".json")

        def do():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._schedule = Schedule.from_list(data)
                self._sel_slot = None
                self._projected.clear()
                self._save_schedule()
                self._close_modal()
                self._build_program_list()
                self._render_center()
            except Exception as ex:
                self._info("Errore", f"Impossibile caricare il modello:\n{ex}")
        self._ask_confirm("Carica modello",
                          f"Sostituire la scaletta attuale con «{name}»?", do,
                          confirm_text="Sostituisci")

    def _delete_template(self, name):
        path = os.path.join(self._templates_dir(), name + ".json")
        try:
            os.remove(path)
        except Exception:
            pass
        self._open_templates()

    # scaletta actions
    def _confirm_reset_scaletta(self):
        self._ask_confirm(
            "Azzera scaletta",
            "Eliminare tutte le sezioni e gli elementi? Questa azione non è reversibile.",
            self._reset_scaletta)

    def _reset_scaletta(self):
        self._schedule.sections.clear()
        self._sel_slot = None
        self._projected.clear()
        self._save_schedule()
        self._build_program_list()
        self._render_center()

    def _add_section(self):
        self._ask_text("Nuova sezione", lambda v: (
            self._schedule.add_section(v), self._save_schedule(),
            self._render_sections()), label="Nome sezione:")

    def _rename_section(self, sec: Section):
        self._ask_text("Rinomina sezione", lambda v: (
            setattr(sec, "name", v), self._save_schedule(),
            self._render_sections()), initial=sec.name)

    def _delete_section(self, sec: Section):
        self._ask_confirm("Elimina sezione",
                          f"Eliminare la sezione «{sec.name}» e tutti i suoi elementi?",
                          lambda: (self._schedule.remove_section(sec.id),
                                   self._sec_open.pop(sec.id, None),
                                   self._save_schedule(), self._render_sections()))

    def _add_slot(self, sec: Section):
        def build(body):
            ctk.CTkLabel(body, text="Scegli il tipo di elemento", anchor="w",
                         font=theme.font_body(12), text_color=TEXT_TERTIARY
                         ).pack(fill="x", pady=(0, 10))
            grid = ctk.CTkFrame(body, fg_color="transparent")
            grid.pack(fill="both", expand=True)
            cols = 3

            def add(t):
                slot = Slot(slot_type=t)
                sec.add_slot(slot)
                self._save_schedule()
                self._close_modal()
                self._sel_slot = slot
                self._render_sections()
                self._render_center()

            for i, t in enumerate(ADDABLE_TYPES):
                icon_img = theme.icon(t, "category", size=20)
                ctk.CTkButton(grid, text=SLOT_LABELS.get(t, t), image=icon_img,
                              compound="top", height=64,
                              corner_radius=15, fg_color=CARD_ROW,
                              text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                              hover_color=SURFACE_4,
                              command=lambda tt=t: add(tt)
                              ).grid(row=i // cols, column=i % cols, padx=4, pady=4, sticky="ew")
            for c in range(cols):
                grid.grid_columnconfigure(c, weight=1)
        # one click on a type adds it immediately — no scrolling, nothing hidden
        # (height must fit all 4 rows of the 3-col icon grid — measured
        # requirement is ~390px; 400 leaves a small margin)
        self._open_modal(f"Aggiungi a «{sec.name}»", build, width=440, height=400)

    def _rename_slot(self, slot: Slot):
        # Rename acts on the element's title/value (the text shown in the
        # card's title row — filename, hymn title, etc.), NOT on the type
        # label. Stored as a custom override in slot.data["title"].
        current, filled = self._slot_value(slot)
        initial = current if filled else (slot.data.get("title") or "")
        self._ask_text("Rinomina elemento", lambda v: (
            slot.data.__setitem__("title", v), self._save_schedule(),
            self._render_sections(), self._render_center()),
            initial=initial, label="Titolo:")

    def _delete_slot(self, sec: Section, slot: Slot):
        def do():
            sec.remove_slot(slot.id)
            if self._sel_slot is slot:
                self._sel_slot = None
            self._save_schedule()
            self._render_sections()
            self._render_center()
        self._ask_confirm("Elimina elemento",
                          f"Eliminare «{slot.label()}»?", do)

    # center detail
    def _fit_center_textbox(self, box, frame):
        """Stretch a CTkTextbox to fill the remaining vertical space in the
        scrollable center panel. CTkScrollableFrame sizes its inner frame to
        its content and ignores pack(expand=True), so the box's height is
        computed by hand instead: viewport height minus everything else
        currently packed in `frame`. Re-run on window resize."""
        center = self._center

        def _resize(_e=None):
            if not box.winfo_exists() or not frame.winfo_exists():
                return
            frame.update_idletasks()
            others = frame.winfo_reqheight() - box.winfo_reqheight()
            # Generous safety margin (not just a few px) so the buttons
            # below the box always stay comfortably clear of the visible
            # viewport's bottom edge, with no scrolling needed to see them.
            target = center.winfo_height() - others - 64
            if target > 120:
                box.configure(height=target)
        center.bind("<Configure>", _resize)
        frame.after(120, _resize)

    def _mark_projected(self, slot):
        if slot is not None:
            self._projected.add(slot.id)
            self._render_sections()

    def _render_center(self):
        slot = self._sel_slot
        if slot is None:
            self._center_scroll.grid_remove()
            for w in self._center_empty.winfo_children():
                w.destroy()
            self._center_empty.grid(row=0, column=0)
            ctk.CTkLabel(self._center_empty, text="☰", font=("", 42),
                         text_color=TEXT_FAINT).pack()
            ctk.CTkLabel(self._center_empty, text="Seleziona un elemento dalla scaletta",
                         font=theme.font_body(15), text_color=TEXT_TERTIARY).pack(pady=(8, 0))
            ctk.CTkLabel(self._center_empty, text="Dettagli e comandi dell'elemento compaiono qui.",
                         font=theme.font_body(11), text_color=TEXT_FAINT).pack(pady=(2, 0))
            return
        self._center_empty.grid_remove()
        for w in self._center_scroll.winfo_children():
            w.destroy()
        frame = self._center_scroll
        frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=14)

        # ── header: type eyebrow (colored dot + label) + title + divider ──
        head = ctk.CTkFrame(frame, fg_color="transparent")
        head.pack(fill="x", pady=(0, 14))
        eyebrow = ctk.CTkFrame(head, fg_color="transparent")
        eyebrow.pack(fill="x")
        color = SLOT_COLORS.get(slot.slot_type, "#6b7280")
        ctk.CTkLabel(eyebrow, text="●", text_color=color, font=("", 11)).pack(side="left")
        ctk.CTkLabel(eyebrow, text=SLOT_LABELS.get(slot.slot_type, slot.slot_type).upper(),
                     text_color=("gray45", "gray55"), font=("", 11, "bold")).pack(
                         side="left", padx=(6, 0))
        title = ctk.CTkLabel(head, text=slot.label(), font=("", 22, "bold"),
                             anchor="w", justify="left")
        title.pack(fill="x", pady=(4, 0))
        _auto_wrap_label(title)
        ctk.CTkFrame(head, height=1, fg_color=("gray80", "gray28")).pack(
            fill="x", pady=(12, 0))
        {
            "inno": self._detail_inno, "versetto": self._detail_versetto,
            "timer": self._detail_timer, "presentazione": self._detail_file_pres,
            "audio": self._detail_audio, "documento": self._detail_documento,
            "qrcode": self._detail_qrcode, "testo": self._detail_testo,
            "campana": self._detail_campana, "video": self._detail_video,
            "lezione": self._detail_lezione, "predica": self._detail_predica,
            "preghiera": self._detail_preghiera, "immagine": self._detail_immagine,
        }.get(slot.slot_type, self._detail_generic)(frame, slot)

    def _detail_preghiera(self, frame, slot):
        n = len(self._prayers)
        ctk.CTkLabel(frame, text=f"{n} richiest{'a' if n == 1 else 'e'} di preghiera attiv{'a' if n == 1 else 'e'}",
                     text_color=TEXT_SECONDARY, font=theme.font_body(13, bold=True)
                     ).pack(anchor="w", pady=(0, 8))
        if n:
            for it in self._prayers[:5]:
                txt = it["name"] + (f" — {it['reason']}" if it.get("reason") else "")
                ctk.CTkLabel(frame, text=txt, anchor="w", text_color=TEXT_SECONDARY,
                             font=theme.font_body(13), wraplength=560, justify="left"
                             ).pack(anchor="w", pady=1)
            if n > 5:
                ctk.CTkLabel(frame, text=f"… e altre {n - 5}.", text_color=TEXT_FAINT,
                             font=theme.font_body(12)).pack(anchor="w")
        else:
            ctk.CTkLabel(frame, text="Nessuna richiesta di preghiera.",
                         text_color=TEXT_TERTIARY).pack(anchor="w", pady=4)
        ctk.CTkButton(frame, text="Apri Preghiere →", height=32, corner_radius=11,
                      font=theme.font_body(12, bold=True), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=lambda: self._nav("preghiere")).pack(anchor="w", pady=6)

    def _detail_lezione(self, frame, slot):
        cat = SLOT_COLORS["lezione"]
        ls, les = self._current_lesson()

        if not les:
            ctk.CTkLabel(frame, text="Nessuna lezione corrisponde a oggi.",
                         text_color=TEXT_TERTIARY).pack(anchor="w", pady=(8, 4))
            if ls and ls.titles():
                self._lesson_picker_widget(
                    frame, ls, after=lambda: (self._render_sections(), self._render_center()))
            ctk.CTkButton(frame, text="Gestisci lezione (Impostazioni)", height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=lambda: self._goto_settings("lezione")).pack(anchor="w", pady=6)
            return

        title_row = ctk.CTkFrame(frame, fg_color="transparent")
        title_row.pack(fill="x", pady=(4, 0))
        kicker = les.get("trimestre", "")
        title_text = f"Lezione {les['numero_lezione']}" if les.get("numero_lezione") else "Lezione"
        if les.get("title") or les.get("titolo"):
            title_text += f" — {les.get('title') or les.get('titolo')}"
        ctk.CTkLabel(title_row, text=title_text, font=theme.font_section(18),
                     text_color=TEXT_PRIMARY, wraplength=420, justify="left"
                     ).pack(side="left")
        if ls and ls.titles():
            cambia = ctk.CTkFrame(title_row, fg_color="transparent")
            cambia.pack(side="right")
            self._lesson_picker_widget(
                cambia, ls, after=lambda: (self._render_sections(), self._render_center()))
        if kicker:
            ctk.CTkLabel(frame, text=kicker, font=theme.font_body(12),
                         text_color=TEXT_TERTIARY).pack(anchor="w", pady=(0, 4))
        for k in ("date", "date_start", "data_sabato", "memory_verse"):
            if les.get(k):
                ctk.CTkLabel(frame, text=f"{k}: {les[k]}", anchor="w", text_color=TEXT_FAINT,
                             font=theme.font_body(11), wraplength=560, justify="left"
                             ).pack(anchor="w")

        domande = lesson.flatten_domande(les)
        if not domande:
            ctk.CTkLabel(frame, text='Questa lezione non ha domande nel file JSON '
                                     '(campo "domande" oppure "giorni" → "domande").',
                         text_color=TEXT_TERTIARY, wraplength=560, justify="left"
                         ).pack(anchor="w", pady=6)
            ctk.CTkButton(frame, text="Gestisci lezione (Impostazioni)", height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=lambda: self._goto_settings("lezione")).pack(anchor="w", pady=6)
            return

        if not hasattr(self, "_lesson_browse_idx"):
            self._lesson_browse_idx = 0
        i = max(0, min(self._lesson_browse_idx, len(domande) - 1))
        self._lesson_browse_idx = i
        dom = domande[i]

        # day pills (mockup 4d) replace the old "Vai a" dropdown — one pill
        # per day ("sottotitolo"), so the operator can jump straight from
        # e.g. the first question to the last without clicking "Successiva"
        # through every question in between.
        day_start_idx = {}
        day_labels = []  # (short_label, full_label) in first-seen order
        for idx, d in enumerate(domande):
            if not d["day"]:
                continue
            full = f"{d['day']} — {d['day_title']}"
            if full not in day_start_idx:
                day_start_idx[full] = idx
                day_labels.append((d["day"][:3].capitalize(), full))
        if day_labels:
            cur_full = f"{dom['day']} — {dom['day_title']}"
            jump_row = ctk.CTkFrame(frame, fg_color="transparent")
            jump_row.pack(fill="x", pady=(10, 0))
            for short, full in day_labels:
                on = full == cur_full
                _circle(jump_row, short, None, 11, width=52, height=30,
                       fg_color=ACCENT if on else CARD_ROW,
                       text_color="white" if on else TEXT_TERTIARY,
                       font=theme.font_body(12, bold=True),
                       hover_color=ACCENT_HOVER if on else SURFACE_4,
                       command=(lambda f=full: (
                           setattr(self, "_lesson_browse_idx", day_start_idx[f]),
                           self._render_center()))
                       ).pack(side="left", padx=2)

        if self._graphic_profile("domanda").get("template", ""):
            photo_row = ctk.CTkFrame(frame, fg_color="transparent")
            photo_row.pack(fill="x", pady=(6, 0))
            cur_photo = self._lesson_photo(les)
            ctk.CTkLabel(photo_row, text="Foto della lezione: " +
                                         (os.path.basename(cur_photo) if cur_photo else "nessuna"),
                         text_color=TEXT_TERTIARY, font=theme.font_body(11)).pack(side="left")
            ctk.CTkButton(photo_row, text="Cambia foto", width=110, height=26, corner_radius=10,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(11, bold=True),
                          command=lambda: self._pick_lesson_photo(les)
                          ).pack(side="left", padx=8)

        # live-projection status — only shown when the domanda being browsed
        # right now is the exact one on screen, so it's clear that browsing
        # (Precedente/Successiva, day pills) never projects anything by
        # itself; it disappears the moment you navigate away from what's
        # actually live.
        if self._proj_mode == "lezione" and getattr(self, "_proj_lesson_idx", None) == i:
            ctk.CTkLabel(frame, text="● Questa domanda è in proiezione ora",
                         text_color=ACTIVE_GREEN, font=theme.font_body(11, bold=True)
                         ).pack(anchor="w", pady=(10, 0))

        card = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=13)
        card.pack(fill="x", pady=(10, 4))
        day_kicker = f"{dom['day'].upper()} — {dom['day_title']}" if dom["day"] else ""
        head_text = f"{day_kicker}  ·  Domanda {dom['day_index'] + 1}/{dom['day_count']}" if day_kicker \
            else f"Domanda {dom['day_index'] + 1}/{dom['day_count']}"
        header_color = self._settings.get("lesson_header_color", cat)
        question_color = self._settings.get("lesson_question_color", TEXT_PRIMARY)
        text_col = ctk.CTkFrame(card, fg_color="transparent")
        text_col.pack(side="left", fill="both", expand=True, padx=(14, 8), pady=12)
        ctk.CTkLabel(text_col, text=head_text, font=theme.font_label(11),
                     text_color=header_color, wraplength=420, justify="left"
                     ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(text_col, text=dom["question"], anchor="w", wraplength=420,
                     justify="left", font=theme.font_body(14), text_color=question_color
                     ).pack(anchor="w")
        ctk.CTkButton(card, text="Proietta questa domanda", height=32, corner_radius=11,
                      font=theme.font_body(12, bold=True), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=lambda: (self._mark_projected(slot), self._project_lesson_domanda(i))
                      ).pack(side="right", padx=14, pady=12)

        def browse(delta):
            self._lesson_browse_idx = max(0, min(i + delta, len(domande) - 1))
            self._render_center()

        nav = ctk.CTkFrame(frame, fg_color="transparent")
        nav.pack(fill="x", pady=6)
        ctk.CTkButton(nav, text="‹ Precedente", width=120, height=32, corner_radius=11,
                      fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                      text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                      command=lambda: browse(-1)).pack(side="left", padx=2)
        ctk.CTkButton(nav, text="Successiva ›", width=120, height=32, corner_radius=11,
                      fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                      text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                      command=lambda: browse(1)).pack(side="left", padx=2)

        if dom["verses"]:
            ctk.CTkLabel(frame, text="VERSETTI", font=theme.font_label(10),
                         text_color=TEXT_LABEL).pack(anchor="w", pady=(16, 6))
            for item in self._lesson_resolve_verses(dom):
                row = ctk.CTkFrame(frame, fg_color=CARD_ROW, corner_radius=12)
                row.pack(fill="x", pady=3)
                info = ctk.CTkFrame(row, fg_color="transparent")
                info.pack(side="left", fill="x", expand=True, padx=12, pady=8)
                if item["resolved"]:
                    label = f"{item['book_name']} {item['chapter']}:" + \
                            ",".join(str(v) for v in item["verses"])
                    preview = " ".join(t for t in item["texts"] if t)
                    if len(preview) > 220:
                        preview = preview[:220] + "…"
                    ctk.CTkLabel(info, text=label, anchor="w", font=theme.font_label(11),
                                 text_color=SLOT_COLORS["versetto"]).pack(anchor="w")
                    ctk.CTkLabel(info, text=preview or "(testo non trovato nel database biblico)",
                                 anchor="w", text_color=TEXT_SECONDARY, wraplength=380,
                                 justify="left", font=theme.font_body(12)).pack(anchor="w", pady=(2, 0))
                    ctk.CTkButton(row, text="Proietta", width=80, height=28, corner_radius=11,
                                  font=theme.font_body(12, bold=True),
                                  command=lambda b=item["book"], c=item["chapter"],
                                                 vs=item["verses"], idx=i:
                                      (self._mark_projected(slot),
                                       self._project_lesson_verse_citation(b, c, vs, idx))
                                  ).pack(side="right", padx=8)
                else:
                    ctk.CTkLabel(info, text=item["raw"], anchor="w", font=theme.font_label(11),
                                 text_color=SLOT_COLORS["versetto"]).pack(anchor="w")
                    ctk.CTkLabel(info, text="Riferimento non riconosciuto — verrà proiettato "
                                            "solo il testo scritto nel file.",
                                 anchor="w", text_color=TEXT_FAINT, wraplength=380,
                                 justify="left", font=theme.font_body(11)).pack(anchor="w", pady=(2, 0))
                    ctk.CTkButton(row, text="Proietta", width=80, height=28, corner_radius=11,
                                  font=theme.font_body(12, bold=True),
                                  command=lambda idx=i, t=item["raw"], q=dom["question"]:
                                      (self._mark_projected(slot),
                                       self._project_lesson_raw_text(idx, t, q))
                                  ).pack(side="right", padx=8)

        if dom["note"]:
            ctk.CTkLabel(frame, text="NOTA", font=theme.font_label(10),
                         text_color=TEXT_LABEL).pack(anchor="w", pady=(16, 6))
            note_preview = dom["note"] if len(dom["note"]) <= 400 else dom["note"][:400] + "…"
            note_card = ctk.CTkFrame(frame, fg_color=CARD_ROW, corner_radius=12)
            note_card.pack(fill="x")
            ctk.CTkLabel(note_card, text=note_preview, anchor="w", text_color=TEXT_SECONDARY,
                         wraplength=440, justify="left", font=theme.font_body(12)
                         ).pack(side="left", fill="x", expand=True, padx=12, pady=10)
            ctk.CTkButton(note_card, text="Proietta", height=28, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: (self._mark_projected(slot), self._project_lesson_note(i))
                          ).pack(side="right", padx=12, pady=10)

        ctk.CTkLabel(frame, text="‹ › qui sopra spostano solo l'anteprima, senza proiettare "
                                 "nulla. Quando la lezione è già in proiezione, le frecce ← → "
                                 "della tastiera passano alla domanda successiva/precedente "
                                 "sullo schermo (senza versetti o nota).",
                     text_color=TEXT_FAINT, font=theme.font_body(10), wraplength=560,
                     justify="left").pack(anchor="w", pady=(12, 0))

        ctk.CTkButton(frame, text="Gestisci lezione (Impostazioni)", height=32, corner_radius=11,
                      fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                      text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                      command=lambda: self._goto_settings("lezione")).pack(anchor="w", pady=(14, 4))

    def _detail_predica(self, frame, slot):
        box = ctk.CTkTextbox(frame, height=200, corner_radius=12, fg_color=CARD_ROW,
                             text_color=TEXT_PRIMARY, font=theme.font_body(14))
        box.pack(fill="both", expand=True, pady=6)
        box.insert("0.0", slot.data.get("text", ""))
        def save():
            slot.data["text"] = box.get("0.0", "end").strip()
            if slot.data["text"] and not slot.display_name:
                slot.display_name = slot.data["text"].split("\n")[0][:30]
            self._save_schedule(); self._render_sections()
        ctk.CTkButton(frame, text="💾 Salva", height=32, corner_radius=11,
                      font=theme.font_body(12, bold=True), command=save).pack(anchor="w")

    def _detail_generic(self, frame, slot):
        ctk.CTkLabel(frame, text="Nessuna anteprima per questo tipo.",
                     text_color=TEXT_TERTIARY).pack(anchor="w")

    def _detail_campana(self, frame, slot):
        bell = self._settings.get("bell_sound", "")
        if bell and os.path.isfile(bell):
            ctk.CTkLabel(frame, text=f"Suono: {os.path.basename(bell)}",
                         text_color=TEXT_TERTIARY, font=theme.font_body(12)).pack(anchor="w", pady=2)
        else:
            ctk.CTkLabel(frame, text="Nessun suono campana configurato.",
                         text_color=TEXT_TERTIARY, font=theme.font_body(12)).pack(anchor="w", pady=2)
        ctk.CTkButton(frame, text="Suona campana", height=40, corner_radius=13,
                      font=theme.font_body(13, bold=True),
                      command=self._ring_bell).pack(anchor="w", pady=6)
        ctk.CTkButton(frame, text="Cambia suono (Impostazioni)", height=32, corner_radius=11,
                      fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                      text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                      command=lambda: self._goto_settings("campanello")).pack(anchor="w")

    def _detail_video(self, frame, slot):
        path = slot.data.get("path", "")
        r = ctk.CTkFrame(frame, fg_color="transparent")
        r.pack(fill="x", pady=4)
        vid_browse = [("Video", "*.mp4 *.mov *.avi *.mkv *.m4v *.webm")]
        ctk.CTkButton(r, text="Scegli video", height=32, corner_radius=11,
                      font=theme.font_body(12, bold=True),
                      command=lambda: self._open_media_library(
            slot, _VIDEO_EXTS, title="Libreria video", browse_types=vid_browse)
            ).pack(side="left", padx=2)
        self._register_drop(frame, slot)
        if path:
            ctk.CTkButton(r, text="Proietta video", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: (self._mark_projected(slot),
                                           self._project_video(path),
                                           self._render_center())).pack(side="left", padx=2)
            ctk.CTkButton(r, text="Apri esterno", height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=lambda: projector.open_file_external(path)).pack(side="left", padx=2)
            if (self._proj_mode == "video" and self._video
                    and os.path.abspath(self._video.path) == os.path.abspath(path)):
                VideoPlayerWidget(frame, self).pack(fill="x", pady=6)
            else:
                ctk.CTkLabel(frame, text="Proietta il video per vedere qui i comandi di riproduzione "
                                         "(anche nel pannello a destra).",
                             text_color=TEXT_FAINT, font=theme.font_body(11)).pack(anchor="w", pady=4)

    def _detail_inno(self, frame, slot):
        h = slot.data.get("hymn")
        if h:
            box = None
            if h.get("slides_text"):
                box = ctk.CTkTextbox(frame, height=200, corner_radius=12, fg_color=CARD_ROW,
                                     text_color=TEXT_SECONDARY, font=theme.font_body(20))
                box.pack(fill="both", expand=True, pady=6)
                box.insert("0.0", "\n\n".join(h["slides_text"]))
                box.configure(state="disabled")
                _bind_textbox_scroll(box)
            ap = h.get("audio_path", "")
            if ap and os.path.isfile(ap):
                m = self._audio.music
                if not m.is_playing and m.current_path != ap:
                    m.load(ap, label=f"Base — {h['title']}")
                AudioPlayerWidget(frame, self._audio,
                                  label="Base musicale").pack(fill="x", pady=6)
            r = ctk.CTkFrame(frame, fg_color="transparent")
            r.pack(fill="x", pady=4)
            ctk.CTkButton(r, text="Proietta", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: (self._mark_projected(slot),
                                           self._project_hymn(h.get("slides_text", []),
                                                              f"Inno {h['number']}",
                                                              h.get("path", "")))).pack(side="left", padx=2)
            ctk.CTkButton(r, text="Cambia inno", height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=lambda: self._start_picker("inno", slot)).pack(side="left", padx=2)
            if box is not None:
                self._fit_center_textbox(box, frame)
        else:
            ctk.CTkLabel(frame, text="Nessun inno assegnato", text_color=TEXT_TERTIARY,
                         font=theme.font_body(13)).pack(anchor="w", pady=(0, 8))
            ctk.CTkButton(frame, text="Seleziona inno", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: self._start_picker("inno", slot)).pack(anchor="w")

    def _detail_versetto(self, frame, slot):
        v = slot.data.get("verse")
        if v:
            if self._bible and v.get("book") is not None:
                lang_row = ctk.CTkFrame(frame, fg_color="transparent")
                lang_row.pack(fill="x", pady=(8, 0))
                ctk.CTkLabel(lang_row, text="PROIETTA IN", font=theme.font_label(10),
                             text_color=TEXT_LABEL).pack(side="left", padx=(0, 8))
                active_langs = v.get("langs", [])
                for code in self._bible.languages():
                    on = code in active_langs
                    ctk.CTkButton(lang_row, text=("✓ " if on else "") + code.upper(),
                                  width=60, height=26, corner_radius=13,
                                  font=theme.font_body(11, bold=True),
                                  fg_color=ACCENT if on else "transparent",
                                  text_color="white" if on else TEXT_TERTIARY,
                                  border_width=0 if on else 1, border_color=BORDER,
                                  hover_color=ACCENT_HOVER if on else SURFACE_3,
                                  command=lambda c=code: self._toggle_verse_slot_lang(slot, c)
                                  ).pack(side="left", padx=3)
            top_row = ctk.CTkFrame(frame, fg_color="transparent")
            top_row.pack(fill="x", pady=(8, 0))
            text_col = ctk.CTkFrame(top_row, fg_color="transparent")
            text_col.pack(side="left", fill="x", expand=True)
            for code, txt in v.get("texts", {}).items():
                lab = self._bible.language_label(code) if self._bible else code
                ctk.CTkLabel(text_col, text=lab, font=theme.font_label(11),
                             text_color=TEXT_LABEL).pack(anchor="w", pady=(8, 0))
                ctk.CTkLabel(text_col, text=txt, wraplength=440, justify="left",
                             font=theme.font_body(13), text_color=TEXT_SECONDARY
                             ).pack(anchor="w")
            ctk.CTkButton(top_row, text="Proietta versetto", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: (self._mark_projected(slot),
                                           self._project_verse_data(v))
                          ).pack(side="right", padx=(10, 2), anchor="n", pady=(8, 0))
            r = ctk.CTkFrame(frame, fg_color="transparent")
            r.pack(fill="x", pady=10)
            ctk.CTkButton(r, text="Cambia versetto", height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=lambda: self._start_picker("versetto", slot)).pack(side="left", padx=2)
            nav = ctk.CTkFrame(frame, fg_color="transparent")
            nav.pack(fill="x", pady=6)
            ctk.CTkButton(nav, text="‹ Versetto precedente", width=160, height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._slide_prev).pack(side="left", padx=2)
            ctk.CTkButton(nav, text="Versetto successivo ›", width=160, height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._slide_next).pack(side="left", padx=2)
            ctk.CTkLabel(frame, text="(avanti/indietro anche con le frecce ← → o PagSù/PagGiù, "
                         "mentre il versetto è in proiezione)",
                         text_color=TEXT_FAINT, font=theme.font_body(10)).pack(anchor="w")
        else:
            ctk.CTkLabel(frame, text="Nessun versetto assegnato", text_color=TEXT_TERTIARY,
                         font=theme.font_body(13)).pack(anchor="w", pady=(0, 8))
            ctk.CTkButton(frame, text="Seleziona versetto", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: self._start_picker("versetto", slot)).pack(anchor="w")

    def _toggle_verse_slot_lang(self, slot, code: str):
        """Change which languages a verse already assigned to a scaletta slot
        will project — independent from whatever was selected at pick time,
        re-fetched live from book/chapter/verse numbers stored on the slot."""
        v = slot.data.get("verse")
        if not v:
            return
        langs = list(v.get("langs", []))
        if code in langs:
            if len(langs) <= 1:
                return  # at least one language must stay selected
            langs.remove(code)
        else:
            langs.append(code)
        v["langs"] = langs
        v["texts"] = {c: (self._bible.get_verse(c, v["book"], v["chapter"], v["verse"]) or "")
                      for c in langs}
        self._save_schedule()
        self._render_center()

    def _detail_timer(self, frame, slot):
        TimerWidget(frame, self).pack(fill="x", pady=4)
        PauseMusicWidget(frame, self).pack(fill="x", pady=4)

    def _detail_file_pres(self, frame, slot):
        path = slot.data.get("path", "")
        r = ctk.CTkFrame(frame, fg_color="transparent")
        r.pack(fill="x", pady=4)
        ctk.CTkButton(r, text="Scegli file", height=32, corner_radius=11,
                      font=theme.font_body(12, bold=True),
                      command=lambda: self._pick_file_for(
            slot, [("Presentazioni/PDF", "*.pptx *.ppt *.pdf")])).pack(side="left", padx=2)
        self._register_drop(frame, slot)

        if not path:
            ctk.CTkLabel(frame, text="Trascina qui un file PDF o PowerPoint",
                         text_color=TEXT_FAINT, font=theme.font_body(11)).pack(anchor="w", pady=6)
            return

        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            ctk.CTkButton(r, text="Proietta come diapositive", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: (self._mark_projected(slot),
                                           self._project_pdf(path))).pack(side="left", padx=2)
            # slideshow navigation controls
            nav = ctk.CTkFrame(frame, fg_color="transparent")
            nav.pack(fill="x", pady=6)
            ctk.CTkButton(nav, text="‹ Precedente", width=120, height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._slide_prev).pack(side="left", padx=2)
            self._slide_lbl = ctk.CTkLabel(nav, text="— / —", width=80, font=theme.font_body(13),
                                           text_color=TEXT_SECONDARY)
            self._slide_lbl.pack(side="left", padx=6)
            ctk.CTkButton(nav, text="Successiva ›", width=120, height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._slide_next).pack(side="left", padx=2)
            ctk.CTkLabel(frame, text="(controlli anche nel pannello a destra e con PagSù/PagGiù)",
                         text_color=TEXT_FAINT, font=theme.font_body(10)).pack(anchor="w")
        else:
            ctk.CTkButton(r, text="Proietta", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: (self._mark_projected(slot),
                                           self._present_pptx(path))).pack(side="left", padx=2)
            ctk.CTkLabel(frame, text="Si apre in PowerPoint sullo schermo secondario. "
                         "Avanti/indietro con PagSù/PagGiù o le frecce; "
                         "«Togli proiezione» chiude la presentazione.",
                         text_color=TEXT_FAINT, font=theme.font_body(11), wraplength=560,
                         justify="left").pack(anchor="w", pady=(8, 0))

    def _detail_documento(self, frame, slot):
        path = slot.data.get("path", "")
        r = ctk.CTkFrame(frame, fg_color="transparent")
        r.pack(fill="x", pady=4)
        ctk.CTkButton(r, text="Scegli file", height=32, corner_radius=11,
                      font=theme.font_body(12, bold=True),
                      command=lambda: self._pick_file_for(
            slot, [("Documenti", "*.docx *.doc *.txt")])).pack(side="left", padx=2)
        self._register_drop(frame, slot)
        if path and path.lower().endswith(".pdf"):
            ctk.CTkButton(r, text="Apri documento", height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=lambda: projector.open_file_external(path)).pack(side="left", padx=2)

        if path and not path.lower().endswith(".pdf"):
            from core.documents import read_text_blocks
            blocks = read_text_blocks(path)
            if not blocks:
                ctk.CTkLabel(frame, text="(nessun testo estratto)",
                             text_color=TEXT_TERTIARY).pack(anchor="w", pady=6)
                return
            ctk.CTkLabel(frame, text="Clicca un blocco per proiettarlo:", font=theme.font_body(11),
                         text_color=TEXT_TERTIARY).pack(anchor="w", pady=(10, 6))
            box = ctk.CTkScrollableFrame(frame, fg_color="transparent", height=300)
            box.pack(fill="both", expand=True)
            for i, blk in enumerate(blocks):
                b = ctk.CTkFrame(box, fg_color=CARD_ROW, corner_radius=12)
                b.pack(fill="x", pady=3)
                preview = blk.replace("\n", " ⏎ ")
                preview = (preview[:80] + "…") if len(preview) > 80 else preview
                lbl = ctk.CTkLabel(b, text=preview, anchor="w", wraplength=520, justify="left",
                                   font=theme.font_body(12), text_color=TEXT_SECONDARY)
                lbl.pack(side="left", fill="x", expand=True, padx=10, pady=8)
                ctk.CTkButton(b, text="Proietta", width=84, height=28, corner_radius=11,
                              font=theme.font_body(12, bold=True),
                              command=lambda t=blk: (self._mark_projected(slot),
                                                     self._project_text_block(t))).pack(side="right", padx=6)

    def _detail_testo(self, frame, slot):
        box = ctk.CTkTextbox(frame, height=180, corner_radius=12, fg_color=CARD_ROW,
                             text_color=TEXT_PRIMARY, font=theme.font_body(14))
        box.pack(fill="x", pady=(0, 10))
        box.insert("0.0", slot.data.get("text", ""))

        def save_and_project():
            txt = box.get("0.0", "end").strip()
            slot.data["text"] = txt
            if txt and not slot.display_name:
                slot.display_name = txt.split("\n")[0][:30]
            self._save_schedule()
            self._render_sections()
            if txt:
                self._mark_projected(slot)
                self._project_text_block(txt)
        r = ctk.CTkFrame(frame, fg_color="transparent")
        r.pack(fill="x")
        ctk.CTkButton(r, text="Salva", height=34, corner_radius=12,
                      fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                      text_color=TEXT_SECONDARY, font=theme.font_body(13, bold=True),
                      command=lambda: (slot.data.__setitem__("text", box.get("0.0", "end").strip()),
                                       self._save_schedule(),
                                       self._render_sections())).pack(side="left", padx=2)
        ctk.CTkButton(r, text="Proietta", height=34, corner_radius=12,
                      font=theme.font_body(13, bold=True),
                      command=save_and_project).pack(side="left", padx=2)

    def _detail_qrcode(self, frame, slot):
        img = self._settings.get("offering_image", "")
        if img and os.path.isfile(img):
            self._show_image_thumb(frame, img, max_w=420)
            ctk.CTkButton(frame, text="Proietta offerta", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: (self._mark_projected(slot),
                                           self._project_fullscreen_image(img))).pack(anchor="w", pady=8)
            ctk.CTkButton(frame, text="Cambia immagine (Impostazioni)", height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=lambda: self._goto_settings("offerta")).pack(anchor="w")
        else:
            ctk.CTkLabel(frame, text="Nessuna immagine offerta impostata.",
                         text_color=TEXT_TERTIARY).pack(anchor="w", pady=4)
            ctk.CTkButton(frame, text="Imposta immagine offerta", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: self._goto_settings("offerta")).pack(anchor="w")

    def _detail_immagine(self, frame, slot):
        path = slot.data.get("path", "")
        r = ctk.CTkFrame(frame, fg_color="transparent")
        r.pack(fill="x", pady=4)
        ctk.CTkButton(r, text="Scegli immagine", height=32, corner_radius=11,
                      font=theme.font_body(12, bold=True),
                      command=lambda: self._pick_file_for(
            slot, [("Immagini", "*.png *.jpg *.jpeg *.bmp *.gif")])).pack(side="left", padx=2)
        self._register_drop(frame, slot)
        if path and os.path.isfile(path):
            ctk.CTkButton(r, text="Proietta immagine", height=32, corner_radius=11,
                          fg_color=ACCENT, hover_color=ACCENT_HOVER,
                          font=theme.font_body(12, bold=True),
                          command=lambda: (self._mark_projected(slot),
                                           self._project_image(path))).pack(side="left", padx=2)
            self._show_image_thumb(frame, path, max_w=420)
        else:
            ctk.CTkLabel(frame, text="Nessuna immagine — scegli un file oppure trascinalo "
                                     "direttamente sulla scheda.",
                         text_color=TEXT_TERTIARY, wraplength=420, justify="left"
                         ).pack(anchor="w", pady=(10, 0))

    def _project_image(self, path: str):
        """Full-screen image slide (e.g. an announcement graphic) — shown as
        large as possible without ever cropping it, whatever its native
        aspect ratio."""
        self._proj_mode = "immagine"
        win = self._ensure_projection()
        win.show_image(path)
        self._proj_pill.configure(text="● Immagine", text_color="#22c55e")

    def _show_image_thumb(self, parent, path, max_w=300):
        try:
            from PIL import Image
            im = Image.open(path)
            w, h = im.size
            scale = min(max_w / w, 1.0)
            size = (int(w * scale), int(h * scale))
            # CTkImage keeps the PIL image it's given alive for the widget's
            # whole lifetime — downscale it first (2x the display size, so
            # Retina/HiDPI still renders sharp) instead of pinning a full
            # multi-megapixel photo in RAM just to show a small thumbnail.
            im.thumbnail((size[0] * 2, size[1] * 2))
            ctk_img = ctk.CTkImage(light_image=im, dark_image=im, size=size)
            lbl = ctk.CTkLabel(parent, image=ctk_img, text="")
            lbl.image = ctk_img
            lbl.pack(anchor="w", pady=6)
        except Exception:
            ctk.CTkLabel(parent, text=os.path.basename(path),
                         text_color="gray").pack(anchor="w")

    def _detail_audio(self, frame, slot):
        path = slot.data.get("path", "")
        if path:
            m = self._audio.music
            if not m.is_playing and m.current_path != path:
                m.load(path, label=os.path.basename(path))
            AudioPlayerWidget(frame, self._audio,
                              label="Audio").pack(fill="x", pady=6)
        aud_browse = [("Audio", "*.mp3 *.wav *.ogg *.m4a *.flac *.aac")]
        ctk.CTkButton(frame, text="Scegli file audio", height=32, corner_radius=11,
                      font=theme.font_body(12, bold=True),
                      command=lambda: self._open_media_library(
                          slot, _AUDIO_EXTS, title="Libreria audio",
                          browse_types=aud_browse)).pack(anchor="w", pady=4)
        self._register_drop(frame, slot)

    def _pick_file_for(self, slot: Slot, types):
        path = filedialog.askopenfilename(title="Scegli file",
                                          filetypes=types + [("Tutti", "*.*")])
        if path:
            self._set_slot_file(slot, path)

    def _set_slot_file(self, slot: Slot, path: str):
        slot.data["path"] = path
        if not slot.display_name:
            slot.display_name = os.path.splitext(os.path.basename(path))[0]
        self._save_schedule()
        self._render_sections()
        self._render_center()

    # ── in-app media library picker ───────────────────────────────────────────
    def _media_library_files(self, exts):
        """Finished media files (matching `exts`) across the app's known
        folders, newest first. Lets the user pick from inside the app instead
        of leaving for Finder/Explorer. Only lists files that exist *now*, so
        a file still being transcoded in the system temp dir is never shown."""
        folders, seen_dir = [], set()
        for key in ("youtube_folder", "background_music_folder"):
            f = self._settings.get(key, "")
            rp = os.path.realpath(f) if f else ""
            if f and os.path.isdir(f) and rp not in seen_dir:
                seen_dir.add(rp); folders.append(f)
        dl = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.isdir(dl) and os.path.realpath(dl) not in seen_dir:
            folders.append(dl)
        out, seen = [], set()
        for folder in folders:
            try:
                names = os.listdir(folder)
            except Exception:
                continue
            for name in names:
                if os.path.splitext(name)[1].lower() not in exts:
                    continue
                p = os.path.join(folder, name)
                rp = os.path.realpath(p)
                if rp in seen or not os.path.isfile(p):
                    continue
                seen.add(rp); out.append(p)

        def _mtime(p):
            # A file can disappear between the listdir above and this sort
            # (cloud-synced folders, another app cleaning up) — treat it as
            # oldest instead of crashing the whole library modal.
            try:
                return os.path.getmtime(p)
            except OSError:
                return 0.0
        out.sort(key=_mtime, reverse=True)
        return out

    def _open_media_library(self, slot: Slot, exts, title="Libreria",
                            browse_types=None):
        """Modal listing media files from known folders; click to assign to
        the slot. Falls back to the native picker via «Sfoglia sul computer»."""
        files = self._media_library_files(exts)

        def build(body):
            ctk.CTkLabel(body, text="Scegli un file dalla libreria — "
                         "oppure trascinalo direttamente sulla scheda.",
                         text_color=MUTED, font=("", 11), anchor="w",
                         justify="left").pack(fill="x")
            lst = ctk.CTkScrollableFrame(body, fg_color="transparent")
            lst.pack(fill="both", expand=True, pady=(8, 10))
            if not files:
                ctk.CTkLabel(lst, text="Nessun file nelle cartelle note.\n"
                             "Scaricane da YouTube (sezione Media) o usa "
                             "«Sfoglia sul computer».",
                             text_color=MUTED, justify="left").pack(
                                 anchor="w", padx=6, pady=12)
            for p in files:
                row = ctk.CTkFrame(lst, fg_color=CARD_ROW, corner_radius=10)
                row.pack(fill="x", pady=2)

                def choose(_e=None, pp=p):
                    self._close_modal()
                    self._set_slot_file(slot, pp)
                ctk.CTkLabel(row, text="▷", text_color=ACCENT, width=20).pack(
                    side="left", padx=(8, 2))
                nm = ctk.CTkLabel(row, text=os.path.splitext(os.path.basename(p))[0],
                                  anchor="w", cursor="hand2")
                nm.pack(side="left", fill="x", expand=True, padx=4, pady=8)
                ctk.CTkLabel(row, text=self._file_meta(p), text_color=ACCENT,
                             font=("", 10)).pack(side="left", padx=6)
                ctk.CTkButton(row, text="Scegli", width=64, height=26,
                              command=choose).pack(side="left", padx=(2, 8))
                for w in (row, nm):
                    w.bind("<Button-1>", choose)

            ctk.CTkButton(body, text="Sfoglia sul computer…", height=30,
                          fg_color="#475569", hover_color="#334155",
                          command=lambda: (self._close_modal(),
                                           self._pick_file_for(
                                               slot, browse_types or []))
                          ).pack(fill="x")
        self._open_modal(title, build, width=600, height=520)

    def _setup_dnd(self):
        """Register drop targets: tkdnd for window drops, ::tk::mac::OpenDocument
        as override to prevent Tk's default file-dialog on Apple-Event drops."""
        # Override macOS Apple-Event handler so it dispatches to the active slot
        # (prevents Tk's default behaviour of opening a file-chooser dialog)
        def on_open_document(*paths):
            for p in paths:
                if not os.path.isfile(p):
                    continue
                active = [(f, s) for f, s in self._dnd_drop_targets if f.winfo_exists()]
                if active:
                    _, slot = active[-1]
                    self._set_slot_file(slot, p)
                break
        try:
            self.createcommand("::tk::mac::OpenDocument", on_open_document)
        except Exception:
            pass

        # tkdnd: register the root window so drops fire <<Drop>> anywhere on the window
        if not _HAS_DND:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_dnd_drop)
        except Exception as e:
            print(f"[DnD] drop_target_register failed: {e}")

    def _on_dnd_drop(self, event):
        """Receive a file dragged onto the window and assign it to the active slot."""
        raw = (event.data or "").strip()
        # tkdnd wraps paths with spaces in {braces}
        if raw.startswith("{"):
            path = raw[1:raw.index("}")] if "}" in raw else raw.strip("{}")
        else:
            path = raw.split()[0] if " " in raw and not os.path.exists(raw) else raw
        if not os.path.isfile(path):
            return event.action
        # Dispatch to most-recently-registered drop target that's still alive
        self._dnd_drop_targets = [(f, s) for f, s in self._dnd_drop_targets if f.winfo_exists()]
        if self._dnd_drop_targets:
            _, slot = self._dnd_drop_targets[-1]
            self._set_slot_file(slot, path)
        return event.action

    def _register_drop(self, widget, slot: Slot):
        """Track widget as a drop target for slot; actual drop handled by _on_dnd_drop."""
        if not _HAS_DND:
            return
        self._dnd_drop_targets.append((widget, slot))

    def _qcmd_icon(self, name: str):
        """12x12 solid-color swatch for a quick-command row (Nero/Sfondo/
        Congela) — plain PIL squares, not part of the shared theme.icon()
        registry since they're arbitrary per-command colors, not category
        hues."""
        cache = getattr(self, "_qcmd_icon_cache", None)
        if cache is None:
            cache = self._qcmd_icon_cache = {}
        img = cache.get(name)
        if img is None:
            try:
                path = os.path.join(theme._ICONS_DIR, f"qcmd-{name}-swatch.png")
                pil = Image.open(path)
                img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(12, 12))
            except Exception:
                # Missing/corrupt asset must not take down the whole right
                # panel — the button just renders without its color swatch.
                img = None
            cache[name] = img
        return img

    # right panel — control hub: what's in proiezione, campanello, everything
    # currently playing
    def _build_right_panel(self):
        for w in self._right_panel.winfo_children():
            w.destroy()
        panel = ctk.CTkScrollableFrame(self._right_panel, fg_color="transparent")
        panel.pack(fill="both", expand=True, padx=6, pady=6)

        top_head = ctk.CTkFrame(panel, fg_color="transparent")
        top_head.pack(fill="x", pady=(2, 10))
        ctk.CTkLabel(top_head, text="IN PROIEZIONE", font=theme.font_label(11),
                     text_color=TEXT_LABEL).pack(side="left")
        _circle(top_head, "▶", 22, 11, "transparent", TEXT_TERTIARY,
                hover_color=SURFACE_3, command=self._toggle_right).pack(side="right")
        self._right_stop_btn = ctk.CTkButton(
            top_head, text="Stop", width=48, height=20, corner_radius=14,
            font=theme.font_body(10, bold=True),
            fg_color=DANGER_FILL, hover_color=DANGER_FILL_HOVER, text_color=DANGER_FILL_TEXT,
            command=self._stop_projection)
        # dynamic area: shows cards only when something is active
        self._np_box = ctk.CTkFrame(panel, fg_color="transparent")
        self._np_box.pack(fill="x", pady=(0, 18))

        ctk.CTkLabel(panel, text="CAMPANELLO", font=theme.font_label(11),
                     text_color=TEXT_LABEL).pack(anchor="w", pady=(0, 4))
        ctk.CTkButton(panel, text="Suona campanello", height=38, corner_radius=13,
                      font=theme.font_body(13, bold=True),
                      command=self._ring_bell).pack(fill="x", pady=(0, 18))

        ctk.CTkLabel(panel, text="COMANDI RAPIDI", font=theme.font_label(11),
                     text_color=TEXT_LABEL).pack(anchor="w", pady=(0, 6))
        quick = ctk.CTkFrame(panel, fg_color="transparent")
        quick.pack(fill="x", pady=(0, 2))
        self._quick_btns = {}
        for name, swatch, label in (("black", "nero", "Nero"),
                                     ("background", "sfondo", "Sfondo"),
                                     ("freeze", "congela", "Congela")):
            b = ctk.CTkButton(quick, text=label, image=self._qcmd_icon(swatch),
                              compound="left", anchor="w", height=36, corner_radius=12,
                              fg_color=SURFACE_4, hover_color=SURFACE_3,
                              text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                              command=lambda c=name: self._proj_quick_cmd(c))
            b.pack(fill="x", pady=2)
            self._quick_btns[name] = b
        ctk.CTkLabel(panel, text="Ctrl+1 / Ctrl+2 / Ctrl+3 — agiscono subito, senza cambiare "
                     "l'elemento selezionato in scaletta",
                     text_color=TEXT_FAINT, font=theme.font_body(10), wraplength=220,
                     justify="left").pack(anchor="w", pady=(2, 8))
        self._restyle_quick_cmd_btns()
        self._refresh_now_playing()

    def _schedule_np_refresh(self, delay: int = 700):
        """Schedule the next now-playing refresh, cancelling any tick already
        pending — _build_right_panel runs on every scaletta rebuild and calls
        _refresh_now_playing again, so without this each rebuild would ADD one
        more 700ms polling loop (the old loop keeps passing its exists-check
        because self._np_box now points to the NEW box), each one tearing down
        and rebuilding the same cards — wasted CPU that grows over a session."""
        if getattr(self, "_np_after_id", None):
            try:
                self.after_cancel(self._np_after_id)
            except Exception:
                pass
        self._np_after_id = self.after(delay, self._refresh_now_playing)

    def _np_wanted_cards(self):
        """(title, kind) pairs the now-playing box should show right now —
        computed without touching any widget so it can be compared tick to
        tick to decide whether a rebuild is actually needed."""
        cards = []
        proj_mode = self._proj_mode
        if proj_mode in ("slides", "textslides") and self._projection and self._projection.winfo_exists():
            i = self._projection.slide_index + 1
            n = self._projection.slide_count
            prefix = getattr(self, "_proj_pill_prefix", "")
            title = f"{prefix}  {i}/{n}" if prefix else f"Diapositive  {i}/{n}"
            cards.append((title, "slides"))
        elif proj_mode == "video" and self._video:
            v = self._video
            cards.append((f"Video|{v.is_paused}", "video"))
        elif proj_mode == "verse" and self._projection and self._projection.winfo_exists():
            pill = self._proj_pill.cget("text") if hasattr(self, "_proj_pill") else ""
            label = pill.lstrip("● ").strip() or "Versetto"
            cards.append((label, "verse"))
        elif proj_mode == "lezione" and self._projection and self._projection.winfo_exists():
            pill = self._proj_pill.cget("text") if hasattr(self, "_proj_pill") else ""
            label = pill.lstrip("● ").strip() or "Lezione"
            cards.append((label, "lezione"))
        elif proj_mode in ("text", "cover", "timer") and \
                self._projection and self._projection.winfo_exists():
            pill = self._proj_pill.cget("text") if hasattr(self, "_proj_pill") else ""
            label = pill.lstrip("● ").strip() or proj_mode.capitalize()
            cards.append((label, "other"))

        m = self._audio.music
        if m.has_media and (m.is_playing or m.is_paused):
            cards.append((f"{m.label or 'Audio'}|{m.is_playing}", "main"))

        if self._audio.pause_music_is_playing():
            track = self._audio.current_pause_track()
            name = os.path.basename(track) if track else "Musica pausa"
            cards.append((name, "pause"))
        return cards

    def _refresh_now_playing(self):
        if not hasattr(self, "_np_box") or not self._np_box.winfo_exists():
            return
        if getattr(self, "_np_video_dragging", False) or getattr(self, "_np_audio_dragging", False):
            # Rebuilding mid-drag would cut the seek gesture short. Skip this
            # tick entirely; the next one (after release) rebuilds normally
            # with the new position.
            self._schedule_np_refresh()
            return

        wanted = self._np_wanted_cards()
        # Destroying and recreating every card on every 700ms tick — even
        # when nothing changed — made a freshly-built CTkFrame briefly show
        # Tk's raw background before customtkinter applied the theme color
        # (the same flash documented on _center_scroll above), which reads
        # as a constant flicker on Windows. Only rebuild when what should be
        # shown actually changed; otherwise just push the new slider
        # position / elapsed time into the widgets already on screen.
        if wanted == getattr(self, "_np_last_wanted", None) and self._np_box.winfo_children():
            self._np_update_live()
            self._schedule_np_refresh()
            return
        self._np_last_wanted = wanted

        for w in self._np_box.winfo_children():
            w.destroy()
        self._np_live = {}

        for title, kind in wanted:
            self._np_card(self._np_box, title.split("|", 1)[0], kind)

        if not self._np_box.winfo_children():
            ctk.CTkLabel(self._np_box, text="Niente in proiezione", anchor="w",
                         font=theme.font_body(12), text_color=TEXT_FAINT).pack(fill="x")

        if hasattr(self, "_right_stop_btn") and self._right_stop_btn.winfo_exists():
            if self._proj_mode is not None:
                self._right_stop_btn.pack(side="right", padx=(0, 6))
            else:
                self._right_stop_btn.pack_forget()

        self._restyle_quick_cmd_btns()
        try:
            self._schedule_np_refresh()
        except Exception:
            pass

    def _np_update_live(self):
        """Lightweight per-tick update for cards left in place (see
        _refresh_now_playing): just the slider position and elapsed-time
        label, no widget destruction."""
        live = getattr(self, "_np_live", {})
        m = self._audio.music
        if "main" in live and m.has_media:
            dur = m.duration or 0
            slider, lbl = live["main"]
            if dur > 0 and slider.winfo_exists():
                slider.set(min(1000, (m.position / dur) * 1000))
            if lbl.winfo_exists():
                lbl.configure(text=f"{_fmt_time(m.position)} / {_fmt_time(dur)}")
        v = self._video
        if "video" in live and v:
            dur = v.duration or 0
            slider, lbl = live["video"]
            if dur > 0 and slider.winfo_exists():
                slider.set(min(1000, (v.position / dur) * 1000))
            if lbl.winfo_exists():
                lbl.configure(text=f"{_fmt_time(v.position)} / {_fmt_time(dur)}")

    def _np_card(self, parent, title, kind):
        card = ctk.CTkFrame(parent, fg_color=SEL_BG, corner_radius=14,
                            border_width=1, border_color=SEL_BORDER)
        card.pack(fill="x", pady=3)
        ctk.CTkLabel(card, text=title, anchor="w", font=theme.font_body(13, bold=True),
                     text_color=TEXT_PRIMARY, wraplength=190).pack(fill="x", padx=10, pady=(8, 4))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=(0, 6))
        if kind == "slides":
            ctk.CTkButton(row, text="‹", width=46, height=32, font=("", 18),
                          command=self._slide_prev).pack(side="left", padx=2)
            ctk.CTkButton(row, text="›", width=46, height=32, font=("", 18),
                          command=self._slide_next).pack(side="left", padx=2)
            ctk.CTkButton(row, text="⬛", width=36, height=32,
                          fg_color=("gray70", "gray20"), hover_color=("gray60", "gray15"),
                          command=self._proj_black).pack(side="right", padx=2)
        elif kind == "other":
            ctk.CTkButton(row, text="⬛", width=36, height=32,
                          fg_color=("gray70", "gray20"), hover_color=("gray60", "gray15"),
                          command=self._proj_black).pack(side="left", padx=2)
            ctk.CTkButton(row, text="■  Stop", width=80, height=32,
                          fg_color=("gray70", "gray20"), hover_color="#dc2626",
                          command=self._stop_projection).pack(side="left", padx=2)
        elif kind == "verse":
            ctk.CTkButton(row, text="‹", width=36, height=32, font=("", 16),
                          command=self._slide_prev).pack(side="left", padx=2)
            ctk.CTkButton(row, text="›", width=36, height=32, font=("", 16),
                          command=self._slide_next).pack(side="left", padx=2)
            ctk.CTkButton(row, text="⬛", width=32, height=32,
                          fg_color=("gray70", "gray20"), hover_color=("gray60", "gray15"),
                          command=self._proj_black).pack(side="left", padx=2)
            ctk.CTkButton(row, text="■", width=32, height=32,
                          fg_color=("gray70", "gray20"), hover_color="#dc2626",
                          command=self._stop_projection).pack(side="left", padx=2)
        elif kind == "lezione":
            ctk.CTkButton(row, text="‹", width=36, height=32, font=("", 16),
                          command=self._slide_prev).pack(side="left", padx=2)
            ctk.CTkButton(row, text="›", width=36, height=32, font=("", 16),
                          command=self._slide_next).pack(side="left", padx=2)
            _ls, les = self._current_lesson()
            domande = lesson.flatten_domande(les) if les else []
            idx = getattr(self, "_proj_lesson_idx", 0)
            dom = domande[idx] if 0 <= idx < len(domande) else None
            if dom and dom["note"]:
                ctk.CTkButton(row, text="Nota", width=46, height=32,
                              command=lambda i=idx: self._project_lesson_note(i)
                              ).pack(side="left", padx=2)
            ctk.CTkButton(row, text="⬛", width=32, height=32,
                          fg_color=("gray70", "gray20"), hover_color=("gray60", "gray15"),
                          command=self._proj_black).pack(side="left", padx=2)
            ctk.CTkButton(row, text="■", width=32, height=32,
                          fg_color=("gray70", "gray20"), hover_color="#dc2626",
                          command=self._stop_projection).pack(side="left", padx=2)
        elif kind == "main":
            m = self._audio.music
            ctk.CTkButton(row, text="↺", width=36, height=28,
                          command=m.restart).pack(side="left", padx=2)
            ctk.CTkButton(row, text="⏸" if m.is_playing else "▶", width=42, height=28,
                          command=m.toggle).pack(side="left", padx=2)
            ctk.CTkButton(row, text="■", width=36, height=28,
                          command=m.stop).pack(side="left", padx=2)
            dur = m.duration or 0
            if dur > 0:
                slider = ctk.CTkSlider(card, from_=0, to=1000, height=14)
                slider.set(min(1000, (m.position / dur) * 1000))
                slider.pack(fill="x", padx=8, pady=(0, 2))
                slider.bind("<ButtonPress-1>",
                           lambda e: setattr(self, "_np_audio_dragging", True))

                def _release(_e, s=slider, mm=m, d=dur):
                    mm.seek((s.get() / 1000.0) * d)
                    self._np_audio_dragging = False
                slider.bind("<ButtonRelease-1>", _release)
                time_lbl = ctk.CTkLabel(card, text=f"{_fmt_time(m.position)} / {_fmt_time(dur)}",
                                        font=("", 10), text_color=MUTED)
                time_lbl.pack()
                self._np_live["main"] = (slider, time_lbl)
        elif kind == "pause":
            ctk.CTkButton(row, text="⏮", width=36, height=28,
                          command=self._audio.prev_pause_music).pack(side="left", padx=2)
            ctk.CTkButton(row, text="⏭", width=36, height=28,
                          command=self._audio.skip_pause_music).pack(side="left", padx=2)
            ctk.CTkButton(row, text="■", width=36, height=28,
                          command=self._audio.stop_pause_music).pack(side="left", padx=2)
        elif kind == "video":
            v = self._video
            ctk.CTkButton(row, text="↺", width=34, height=28,
                          command=v.restart).pack(side="left", padx=2)
            ctk.CTkButton(row, text="▶" if v.is_paused else "⏸", width=40, height=28,
                          command=v.toggle).pack(side="left", padx=2)
            ctk.CTkButton(row, text="-10s", width=44, height=28,
                          command=lambda: v.seek(max(0, v.position - 10))).pack(side="left", padx=2)
            ctk.CTkButton(row, text="+10s", width=44, height=28,
                          command=lambda: v.seek(v.position + 10)).pack(side="left", padx=2)
            ctk.CTkButton(row, text="■", width=34, height=28,
                          command=self._stop_projection).pack(side="left", padx=2)
            dur = v.duration or 0
            if dur > 0:
                slider = ctk.CTkSlider(card, from_=0, to=1000, height=14)
                slider.set(min(1000, (v.position / dur) * 1000))
                slider.pack(fill="x", padx=8, pady=(0, 2))
                slider.bind("<ButtonPress-1>",
                           lambda e: setattr(self, "_np_video_dragging", True))

                def _release(_e, s=slider, vv=v, d=dur):
                    vv.seek((s.get() / 1000.0) * d)
                    self._np_video_dragging = False
                slider.bind("<ButtonRelease-1>", _release)
                time_lbl = ctk.CTkLabel(card, text=f"{_fmt_time(v.position)} / {_fmt_time(dur)}",
                                        font=("", 10), text_color=MUTED)
                time_lbl.pack()
                self._np_live["video"] = (slider, time_lbl)

    # ── tutorial ─────────────────────────────────────────────────────────────
    def _maybe_show_tutorial(self):
        """First-run only: open the welcome walkthrough once, ever. Marked as
        seen immediately (not on close) so a crash or force-quit mid-tutorial
        can't re-trigger it forever."""
        if self._settings.get("tutorial_seen"):
            return
        self._set("tutorial_seen", True)
        self._show_tutorial()

    def _show_tutorial(self):
        from ui.tutorial import TutorialOverlay
        if getattr(self, "_tutorial", None) is not None and self._tutorial.winfo_exists():
            return
        self._tutorial = TutorialOverlay(
            self, on_close=lambda: setattr(self, "_tutorial", None))

    def _goto_settings(self, cat: str):
        """Jump straight to a specific Impostazioni category — every
        "(Impostazioni)" link throughout the app should use this instead of
        a bare self._nav("impostazioni"), which just reopens whatever
        category was last open and silently drops the user somewhere
        unrelated to the button they clicked."""
        self._settings_cat = cat
        self._nav("impostazioni")

    def _open_timer_appearance(self):
        """Jump to Impostazioni → Pausa (Timer settings live there now, merged
        with the pause-music settings), where this is edited inline (no modal)."""
        self._goto_settings("pausa")

    def _pick_color(self, key, swatch):
        # `or` (not just a dict default) because some settings — e.g. the
        # lesson_letter/date/verse_color "fall back to header color" trio —
        # legitimately store "" for "unset", which askcolor rejects outright.
        c = colorchooser.askcolor(title="Scegli colore",
                                  initialcolor=self._settings.get(key) or "#ffffff")
        if c and c[1]:
            self._set(key, c[1])
            swatch.configure(fg_color=c[1])

    def _pick_timer_bg_image_lbl(self, lbl):
        p = filedialog.askopenfilename(title="Immagine sfondo timer",
                                       filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Tutti", "*.*")])
        if p:
            self._set("timer_bg_image", p)
            lbl.configure(text=os.path.basename(p))

    def _pick_warning_sound_lbl(self, lbl):
        p = filedialog.askopenfilename(title="Audio avviso",
                                       filetypes=[("Audio", "*.mp3 *.wav *.ogg *.m4a"), ("Tutti", "*.*")])
        if p:
            self._set("timer_warning_sound", p)
            lbl.configure(text=os.path.basename(p))

    def _save_warn_sec_val(self, var):
        try:
            self._set("timer_warning_seconds", int(var.get()))
        except (ValueError, AttributeError):
            pass

    def _resize_right(self, e):
        nw = self._right_panel.winfo_rootx() + self._right_panel.winfo_width() - self.winfo_pointerx()
        nw = max(_MIN_PANEL, min(560, nw))
        self._right_w = nw
        self._right_panel.configure(width=nw)
        outer = self._scaletta_outer
        outer.grid_columnconfigure(4, minsize=nw, weight=0)
        outer.update_idletasks()

    def _resize_right_end(self, _e=None):
        self.update_idletasks()
        self._settings["right_panel_width"] = self._right_w
        cfg.save(self._settings)

    # ── picker ──────────────────────────────────────────────────────────────
    def _start_picker(self, ptype: str, slot: Slot):
        self._picker_type = ptype
        self._picker_slot = slot
        self._nav("inni" if ptype == "inno" else "bibbia")

    def _finish_picker(self):
        self._picker_type = None
        self._picker_slot = None
        self._nav("scaletta")

    def _picker_context_label(self) -> str:
        """Return 'SEZIONE > slot_type' for the active picker banner."""
        slot = self._picker_slot
        if slot is None:
            return ""
        for sec in self._schedule.sections:
            if any(s.id == slot.id for s in sec.slots):
                return f"{sec.name}  ›  {SLOT_LABELS.get(slot.slot_type, slot.slot_type)}"
        return SLOT_LABELS.get(slot.slot_type, slot.slot_type)

    # ════════════════════════════════════════════════════════════════════════
    #  INNI
    # ════════════════════════════════════════════════════════════════════════
    def _view_inni(self):
        outer = ctk.CTkFrame(self._content, fg_color="transparent")
        outer.pack(fill="both", expand=True)
        outer.grid_rowconfigure(1, weight=1)
        # Hymn list fills whatever's left; the preview column has a fixed
        # pixel width set by dragging the divider (see _resize_inni_preview),
        # same pattern as the scaletta's side panels.
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=0)
        outer.grid_columnconfigure(2, minsize=self._inni_preview_w, weight=0)
        self._inni_outer = outer

        if self._picker_type == "inno":
            banner = ctk.CTkFrame(outer, fg_color="#d97706", corner_radius=0)
            banner.grid(row=0, column=0, columnspan=3, sticky="ew")
            ctx = self._picker_context_label()
            banner_text = f"Seleziona un inno  —  {ctx}" if ctx else "Seleziona un inno"
            ctk.CTkLabel(banner, text=banner_text,
                         text_color="white", font=("", 12, "bold")).pack(side="left", padx=12, pady=6)
            ctk.CTkButton(banner, text="Annulla", width=80, height=26,
                          fg_color="#b45309", hover_color="#92400e",
                          command=self._finish_picker).pack(side="right", padx=8)

        left = ctk.CTkFrame(outer, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew")
        left.grid_rowconfigure(3, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # title + inline database chip (was a full-width selector row above
        # the search box — now "Innario — <nome db> ⌄" on one line)
        title_row = ctk.CTkFrame(left, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 2))
        ctk.CTkLabel(title_row, text="Innario", font=theme.font_title(),
                     text_color=TEXT_PRIMARY).pack(side="left")
        dbs = self._settings.get("databases", [])
        if dbs:
            names = [os.path.basename(d) or d for d in dbs]
            cur = self._settings.get("last_database", dbs[0])
            cur_name = os.path.basename(cur) or cur
            self._db_var = tk.StringVar(value=cur_name if cur_name in names else names[0])
            ctk.CTkOptionMenu(title_row, values=names, variable=self._db_var,
                              command=self._on_db_change, height=24, width=1,
                              corner_radius=8, fg_color=CARD_ROW,
                              button_color=CARD_ROW, button_hover_color=SURFACE_3,
                              dropdown_fg_color=CARD, dropdown_hover_color=SURFACE_3,
                              text_color=TEXT_TERTIARY, font=theme.font_body(13),
                              dynamic_resizing=True
                              ).pack(side="left", padx=(8, 0), pady=(8, 0))

        sr = ctk.CTkFrame(left, fg_color="transparent")
        sr.grid(row=1, column=0, sticky="ew", padx=8, pady=6)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._refresh_hymn_list())
        ctk.CTkEntry(sr, placeholder_text="🔍  Numero, titolo, testo… (accenti ignorati)",
                     textvariable=self._search_var, height=36, corner_radius=13,
                     fg_color=CARD_ROW, border_color=BORDER, border_width=1,
                     text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_FAINT
                     ).pack(side="left", fill="x", expand=True)
        self._base_only = tk.BooleanVar(value=False)
        self._base_btn = ctk.CTkButton(sr, text="♪ Base", width=80, height=36, corner_radius=13,
                                       command=self._toggle_base_only)
        self._base_btn.pack(side="left", padx=8)
        self._restyle_base_btn()

        self._inni_tab = tk.StringVar(value="Risultati")
        ctk.CTkSegmentedButton(left, values=["Risultati", "Cronologia"],
                               variable=self._inni_tab, height=34,
                               fg_color=CARD_ROW, selected_color=ACCENT,
                               selected_hover_color=ACCENT_HOVER,
                               unselected_color=CARD_ROW, unselected_hover_color=SURFACE_3,
                               text_color=TEXT_TERTIARY, text_color_disabled=TEXT_TERTIARY,
                               font=theme.font_body(12, bold=True),
                               command=lambda v: self._refresh_hymn_list()
                               ).grid(row=2, column=0, padx=8, pady=(0, 6), sticky="ew")

        self._hymn_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._hymn_list.grid(row=3, column=0, sticky="nsew", padx=4)

        pd = ctk.CTkFrame(outer, width=_DIVIDER_W, cursor="sb_h_double_arrow",
                          fg_color=BORDER)
        pd.grid(row=1, column=1, sticky="ns")
        pd.bind("<B1-Motion>", self._resize_inni_preview)
        pd.bind("<ButtonRelease-1>", self._resize_inni_preview_end)

        self._preview = ctk.CTkFrame(outer, width=self._inni_preview_w, corner_radius=0,
                                     fg_color=theme.BG, border_width=0)
        self._preview.grid(row=1, column=2, sticky="nsew")
        self._preview.grid_propagate(False)
        self._preview.pack_propagate(False)
        self._render_hymn_preview()
        self._refresh_hymn_list()

    def _resize_inni_preview(self, e):
        nw = self._preview.winfo_rootx() + self._preview.winfo_width() - self.winfo_pointerx()
        nw = max(_MIN_PANEL, min(900, nw))
        self._inni_preview_w = nw
        self._preview.configure(width=nw)
        self._inni_outer.grid_columnconfigure(2, minsize=nw, weight=0)
        self._inni_outer.update_idletasks()

    def _resize_inni_preview_end(self, _e=None):
        self.update_idletasks()
        self._settings["inni_preview_width"] = self._inni_preview_w
        cfg.save(self._settings)

    def _toggle_base_only(self):
        self._base_only.set(not self._base_only.get())
        self._restyle_base_btn()
        self._refresh_hymn_list()

    def _restyle_base_btn(self):
        on = self._base_only.get()
        self._base_btn.configure(fg_color=ACCENT if on else "transparent",
                                 text_color="white" if on else ACCENT,
                                 border_width=0 if on else 1, border_color=ACCENT,
                                 hover_color=ACCENT_HOVER if on else SURFACE_3)

    def _refresh_hymn_list(self):
        if not hasattr(self, "_hymn_list") or not self._hymn_list.winfo_exists():
            return
        for w in self._hymn_list.winfo_children():
            w.destroy()
        if self._inni_tab.get() == "Cronologia":
            if not self._history.hymns:
                ctk.CTkLabel(self._hymn_list, text="Nessuna cronologia",
                             text_color=TEXT_TERTIARY).pack(pady=20)
            for e in self._history.hymns:
                row = ctk.CTkFrame(self._hymn_list, fg_color=CARD_ROW, corner_radius=12)
                row.pack(fill="x", pady=3)
                # Match by number AND title, not number alone — different
                # databases can reuse the same number for a different hymn
                # (confirmed with the user's real databases), so a
                # number-only match risked silently reusing the wrong hymn
                # instead of just failing to find it.
                h = next((x for x in self._hymns
                          if x.number == e.number and x.title == e.title), None)
                col = ctk.CTkFrame(row, fg_color="transparent",
                                   cursor="hand2" if h else "")
                col.pack(side="left", fill="x", expand=True, padx=14, pady=10)
                ctk.CTkLabel(col, text=e.display, anchor="w",
                             cursor="hand2" if h else "",
                             font=theme.font_body(14, bold=True),
                             text_color=TEXT_PRIMARY).pack(anchor="w")
                used_at = self._format_used_at(e)
                if used_at:
                    ctk.CTkLabel(col, text=used_at, anchor="w",
                                 cursor="hand2" if h else "",
                                 font=theme.font_body(11), text_color=TEXT_TERTIARY
                                 ).pack(anchor="w", pady=(2, 0))
                if h:
                    for w in (row, col):
                        w.bind("<Button-1>", lambda ev, hy=h: self._pick_hymn(hy))
                    _circle(row, "↺", 30, 15, "transparent", TEXT_TERTIARY,
                           font=theme.font_body(15), hover_color=SURFACE_3,
                           command=lambda hy=h: self._pick_hymn(hy)
                           ).pack(side="right", padx=10)
                else:
                    ctk.CTkLabel(row, text="Non nel database attuale",
                                 font=theme.font_body(10), text_color=TEXT_FAINT
                                 ).pack(side="right", padx=12)
            return
        if not self._hymns:
            msg = ("Caricamento database…" if self._db_loading else
                   "Nessun database.\nAggiungi una cartella in Impostazioni.")
            ctk.CTkLabel(self._hymn_list, text=msg, text_color=TEXT_TERTIARY,
                         justify="center").pack(pady=20)
            return
        q = self._search_var.get().strip().lower()
        res = [h for h in self._hymns if h.matches(q)]
        if self._base_only.get():
            res = [h for h in res if h.has_audio]
        ctk.CTkLabel(self._hymn_list, text=f"{len(res)} risultati",
                     font=theme.font_body(12), text_color=TEXT_FAINT).pack(anchor="w", padx=6,
                                                                            pady=(0, 6))
        for h in res[:2000]:
            selected = self._sel_hymn is not None and self._sel_hymn.number == h.number
            row = ctk.CTkFrame(self._hymn_list, corner_radius=12, cursor="hand2",
                               fg_color=SEL_BG if selected else "transparent",
                               border_width=1 if selected else 0, border_color=SEL_BORDER)
            row.pack(fill="x", pady=1)
            lbl = ctk.CTkLabel(row, text=h.display_name, anchor="w", cursor="hand2",
                               font=theme.font_body(14, bold=selected),
                               text_color=TEXT_PRIMARY if selected else TEXT_SECONDARY)
            lbl.pack(side="left", fill="x", expand=True, padx=14, pady=11)
            if not selected and h.has_audio:
                ctk.CTkLabel(row, text="♪", width=22, text_color=ACCENT,
                             cursor="hand2").pack(side="right", padx=10)
            for w in (row, lbl):
                w.bind("<Button-1>", lambda ev, hy=h: self._pick_hymn(hy))

    def _on_db_change(self, name: str):
        dbs = self._settings.get("databases", [])
        match = next((d for d in dbs if (os.path.basename(d) or d) == name), None)
        if match:
            self._settings["last_database"] = match
            cfg.save(self._settings)
            self._hymns = []
            self._refresh_hymn_list()
            self._load_db_async()

    def _pick_hymn(self, hymn: Hymn):
        """Click on a hymn: show preview only (do NOT auto-assign)."""
        self._sel_hymn = hymn
        self._render_hymn_preview()
        self._refresh_hymn_list()

    def _assign_hymn(self, hymn: Hymn):
        """Explicit confirm: assign selected hymn to the picker slot."""
        if self._picker_type == "inno" and self._picker_slot is not None:
            slot = self._picker_slot
            slot.data["hymn"] = {
                "number": hymn.number, "title": hymn.title, "path": hymn.file_path,
                "audio_path": hymn.audio_path or "", "slides_text": hymn.slides_text,
            }
            slot.display_name = f"Inno {hymn.number} — {hymn.title}"
            found = self._schedule.find_slot(slot.id)
            section_name = found[0].name if found else ""
            self._history.add_hymn(hymn.number, hymn.title, hymn.file_path,
                                   section_name=section_name, slot_name=slot.label())
            self._save_schedule()
            self._save_history()
            self._finish_picker()

    def _format_history_meta(self, e) -> str:
        parts = []
        if getattr(e, "date_str", ""):
            parts.append("usato il " + self._format_date(e.date_str))
        if getattr(e, "section_name", ""):
            parts.append("in " + e.section_name)
        return " · ".join(parts)

    def _format_date(self, iso: str) -> str:
        try:
            from datetime import date
            d = date.fromisoformat(iso)
            return f"{d.day} {_MESI[d.month - 1]} {d.year}"
        except Exception:
            return iso

    def _format_used_at(self, e) -> str:
        """'Usato oggi, 09:14' / 'Usato ieri, 10:02' / 'Usato 19 giu, 09:40'
        — the relative-date cronologia format from the redesign."""
        from datetime import date, timedelta
        try:
            d = date.fromisoformat(e.date_str)
        except Exception:
            return ""
        today = date.today()
        if d == today:
            day_part = "oggi"
        elif d == today - timedelta(days=1):
            day_part = "ieri"
        else:
            day_part = f"{d.day} {_MESI[d.month - 1][:3]}"
        time_part = getattr(e, "time_str", "")
        return f"Usato {day_part}, {time_part}" if time_part else f"Usato {day_part}"

    def _render_hymn_preview(self):
        for w in self._preview.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._preview, text="ANTEPRIMA", font=theme.font_label(10),
                     text_color=SLOT_COLORS["inno"]).pack(anchor="w", padx=14, pady=(14, 2))
        h = self._sel_hymn
        if not h:
            ctk.CTkLabel(self._preview, text="Clicca un inno",
                         text_color=TEXT_TERTIARY).pack(expand=True)
            return
        ctk.CTkLabel(self._preview, text=f"Inno {h.number}", text_color=TEXT_PRIMARY,
                     font=theme.font_section(18)).pack(anchor="w", padx=14, pady=(6, 0))
        title_lbl = ctk.CTkLabel(self._preview, text=h.title, font=theme.font_body(13),
                                 text_color=TEXT_SECONDARY, justify="left")
        title_lbl.pack(anchor="w", fill="x", padx=14)

        _wc = [0]
        def _upd_title_wrap(_e=None, _lbl=title_lbl, _p=self._preview):
            w = _p.winfo_width() - 28
            if w > 10 and w != _wc[0]:
                _wc[0] = w
                _lbl.configure(wraplength=w)
        self._preview.bind("<Configure>", _upd_title_wrap)
        self._preview.after(120, _upd_title_wrap)
        if h.slides_text:
            box = ctk.CTkTextbox(self._preview, height=220, corner_radius=13,
                                 fg_color=CARD_ROW, text_color=TEXT_SECONDARY,
                                 border_width=1, border_color=BORDER_SUBTLE,
                                 font=theme.font_body(19))
            box.pack(fill="both", expand=True, padx=8, pady=8)
            box.insert("0.0", h.full_text)
            box.configure(state="disabled")
            _bind_textbox_scroll(box)
        if h.has_audio:
            m = self._audio.music
            if not m.is_playing and m.current_path != h.audio_path:
                m.load(h.audio_path, label=f"Base — {h.title}")
            AudioPlayerWidget(self._preview, self._audio,
                              label="Base musicale").pack(fill="x", padx=14, pady=4)
        if self._picker_type == "inno":
            ctk.CTkButton(self._preview, text="✓ Scegli questo inno", height=40, corner_radius=13,
                          fg_color=ACTIVE_GREEN, hover_color="#1ea34e",
                          font=theme.font_body(13, bold=True),
                          command=lambda: self._assign_hymn(h)).pack(fill="x", padx=14, pady=8)
        ctk.CTkButton(self._preview, text="Proietta", corner_radius=13,
                      font=theme.font_body(13, bold=True),
                      command=lambda: self._project_hymn(h.slides_text, f"Inno {h.number}",
                                                         h.file_path)
                      ).pack(padx=14, pady=4, fill="x")

    # ════════════════════════════════════════════════════════════════════════
    #  BIBBIA
    # ════════════════════════════════════════════════════════════════════════
    def _view_bibbia(self):
        if not self._bible or not self._bible.ready:
            f = ctk.CTkFrame(self._content, fg_color="transparent")
            f.pack(expand=True)
            ctk.CTkLabel(f, text="Nessuna Bibbia installata.", font=("", 14)).pack(pady=6)
            ctk.CTkLabel(f, text="Le Bibbie (.db) vanno nella cartella 'bibles'.",
                         text_color=MUTED).pack()
            return

        outer = ctk.CTkFrame(self._content, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        if self._picker_type == "versetto":
            banner = ctk.CTkFrame(outer, fg_color="#d97706", corner_radius=0)
            banner.pack(fill="x")
            ctx = self._picker_context_label()
            banner_text = f"Seleziona un versetto  —  {ctx}" if ctx else "Seleziona un versetto"
            ctk.CTkLabel(banner, text=banner_text,
                         text_color="white", font=("", 12, "bold")).pack(side="left", padx=12, pady=6)
            ctk.CTkButton(banner, text="Annulla", width=80, height=26,
                          fg_color="#b45309", hover_color="#92400e",
                          command=self._finish_picker).pack(side="right", padx=8)

        # _bib_tab/_bib_search/_lang_extra themselves already exist from
        # __init__ (so projecting a lezione-cited verse works even before
        # this view is ever built) — only the search-debounce trace binding
        # is one-time view-builder setup, guarded separately here.
        if not hasattr(self, "_bib_search_job"):
            self._bib_search_job = None

            def _on_search_write(*_a):
                # Debounced: re-rendering up to 80 search-result rows on
                # every single keystroke (with no delay) is what made typing
                # in this box feel like it froze — wait for a short pause in
                # typing instead of rebuilding on every character.
                if self._bib_search_job is not None:
                    self.after_cancel(self._bib_search_job)
                self._bib_search_job = self.after(250, self._render_bib_content)
            self._bib_search.trace_add("write", _on_search_write)

        # Toolbar (search + single-select primary language) is always
        # visible now — the three nav columns below replace what used to be
        # three mutually-exclusive full-screen states, so there's no more
        # "verse list has its own header, hide the generic one" special case.
        top = ctk.CTkFrame(outer, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkEntry(top, placeholder_text="🔍  Cerca testo o riferimento…",
                     textvariable=self._bib_search, height=34, corner_radius=13,
                     fg_color=CARD_ROW, border_color=BORDER, border_width=1,
                     text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_FAINT
                     ).pack(side="left", fill="x", expand=True)
        self._lang_btns = {}
        for code in self._bible.languages():
            b = ctk.CTkButton(top, text=code.upper(), width=40, height=28, corner_radius=12,
                              font=theme.font_body(11, bold=True),
                              command=lambda c=code: self._set_primary_lang(c))
            b.pack(side="left", padx=3)
            self._lang_btns[code] = b
        self._restyle_primary_lang_btns()

        tabs = ctk.CTkSegmentedButton(outer, values=["Naviga", "Cronologia versetti"],
                                      variable=self._bib_tab, height=32,
                                      fg_color=CARD_ROW, selected_color=ACCENT,
                                      selected_hover_color=ACCENT_HOVER,
                                      unselected_color=CARD_ROW, unselected_hover_color=SURFACE_3,
                                      text_color=TEXT_TERTIARY, text_color_disabled=TEXT_TERTIARY,
                                      font=theme.font_body(12, bold=True),
                                      command=lambda v: self._render_bib_content())
        tabs.pack(anchor="center", pady=(0, 6))

        self._bib_content_row = ctk.CTkFrame(outer, fg_color="transparent")
        self._bib_content_row.pack(fill="both", expand=True)
        self._render_bib_content()

    def _restyle_primary_lang_btns(self):
        """Single-select primary-language row: book/chapter names and the
        verse reference always follow it, and it's always the base language
        of the projected verse text too — separate from the small "+ ALTRE
        LINGUE" row above the Versetti column, which only ever *adds*
        further languages alongside the primary one."""
        primary = self._primary_lang()
        for code, b in getattr(self, "_lang_btns", {}).items():
            on = code == primary
            b.configure(fg_color=ACCENT if on else "transparent",
                        text_color="white" if on else ACCENT,
                        border_width=0 if on else 1, border_color=ACCENT,
                        hover_color=ACCENT_HOVER if on else SURFACE_3)

    def _set_primary_lang(self, code: str):
        self._settings["bible_primary_lang"] = code
        cfg.save(self._settings)
        self._restyle_primary_lang_btns()
        self._render_bib_content()

    def _restyle_lang_btns_verse(self):
        """"+ ALTRE LINGUE" row above the Versetti column (checkmark-pill
        look) — languages added *on top of* the primary one for the verse
        text. The primary language itself never appears here since it's
        always included regardless (see _selected_langs)."""
        for code, b in getattr(self, "_lang_btns_verse", {}).items():
            on = code in self._lang_extra
            b.configure(text=("✓ " if on else "") + code.upper(),
                        fg_color=ACCENT if on else "transparent",
                        text_color="white" if on else TEXT_TERTIARY,
                        border_width=0 if on else 1, border_color=BORDER,
                        hover_color=ACCENT_HOVER if on else SURFACE_3)

    def _toggle_lang(self, code):
        primary = self._primary_lang()
        if code == primary:
            return  # always included — nothing to toggle here
        if code in self._lang_extra:
            self._lang_extra.discard(code)
        else:
            self._lang_extra.add(code)
        self._settings["bible_extra_langs"] = sorted(self._lang_extra)
        cfg.save(self._settings)
        self._refresh_bib_col_verses()

    def _primary_lang(self) -> str:
        """The single language used for book/chapter names, the verse
        reference (e.g. "Genesi 1:1"), AND as the base language of the verse
        *text* — _selected_langs() always includes it first, with
        self._lang_extra only ever adding further languages on top."""
        langs = self._bible.languages()
        code = self._settings.get("bible_primary_lang")
        if code and code in langs:
            return code
        return langs[0] if langs else "it"

    def _selected_langs(self) -> List[str]:
        primary = self._primary_lang()
        extras = [c for c in self._lang_extra if c != primary]
        return [primary] + extras

    def _view_bibbia_refresh(self):
        for w in self._content.winfo_children():
            w.destroy()
        self._view_bibbia()

    def _bib_select_book(self, num: int, name: str):
        self._bib_book = num
        self._bib_book_name = name
        self._bib_chapter = None
        self._bib_testament = "AT" if num <= 39 else "NT"
        self._render_bib_content()

    def _bib_select_chapter(self, ch: int):
        self._bib_chapter = ch
        self._render_bib_content()

    def _render_bib_content(self):
        row = getattr(self, "_bib_content_row", None)
        if not row or not row.winfo_exists():
            return
        for w in row.winfo_children():
            w.destroy()
        if self._bib_tab.get().startswith("Cronologia"):
            self._bib_content = self._make_bib_single_pane(row)
            self._render_verse_history()
            return
        query = self._bib_search.get().strip()
        if query:
            self._bib_content = self._make_bib_single_pane(row)
            self._render_bib_search(query)
            return
        self._bib_content = None
        self._render_bib_columns(row)

    def _reset_bib_content_grid(self, row):
        """_render_bib_columns and _make_bib_single_pane configure the same
        `row` frame with different column weights — grid_columnconfigure
        settings stick around on a widget even after its children are
        destroyed, so switching modes without clearing the *other* mode's
        weights first left leftover columns reserving empty space (e.g. a
        huge unused block to the right of Cronologia versetti, still sized
        per the 3-column Naviga proportions)."""
        for col in range(3):
            row.grid_columnconfigure(col, weight=0)

    def _make_bib_single_pane(self, row):
        self._reset_bib_content_grid(row)
        row.grid_rowconfigure(0, weight=1)
        row.grid_columnconfigure(0, weight=1)
        pane = ctk.CTkScrollableFrame(row, fg_color="transparent")
        pane.grid(row=0, column=0, sticky="nsew", padx=10)
        return pane

    def _set_bib_testament(self, t: str):
        self._bib_testament = t
        self._refresh_bib_col_books()

    def _render_bib_columns(self, row):
        """Libri / Capitoli / Versetti, always visible side by side —
        clicking a book updates the chapters column, clicking a chapter
        updates the verses column, with no back-and-forth navigation."""
        self._reset_bib_content_grid(row)
        row.grid_columnconfigure(0, weight=3)
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(2, weight=3)
        row.grid_rowconfigure(0, weight=1)

        self._bib_col_books = ctk.CTkScrollableFrame(row, fg_color="transparent")
        self._bib_col_books.grid(row=0, column=0, sticky="nsew", padx=(10, 4))
        self._render_book_column()

        self._bib_col_chapters = ctk.CTkScrollableFrame(row, fg_color="transparent")
        self._bib_col_chapters.grid(row=0, column=1, sticky="nsew", padx=4)
        self._render_chapter_column()

        self._bib_col_verses = ctk.CTkScrollableFrame(row, fg_color="transparent")
        self._bib_col_verses.grid(row=0, column=2, sticky="nsew", padx=(4, 10))
        self._render_verse_column()

    def _refresh_bib_col_books(self):
        col = getattr(self, "_bib_col_books", None)
        if not col or not col.winfo_exists():
            return
        for w in col.winfo_children():
            w.destroy()
        self._render_book_column()

    def _refresh_bib_col_chapters(self):
        col = getattr(self, "_bib_col_chapters", None)
        if not col or not col.winfo_exists():
            return
        for w in col.winfo_children():
            w.destroy()
        self._render_chapter_column()

    def _refresh_bib_col_verses(self):
        col = getattr(self, "_bib_col_verses", None)
        if not col or not col.winfo_exists():
            return
        for w in col.winfo_children():
            w.destroy()
        self._render_verse_column()

    def _render_book_column(self):
        c = self._bib_col_books
        ctk.CTkLabel(c, text="Bibbia", font=theme.font_title(),
                     text_color=TEXT_PRIMARY).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(c, text="Scegli un libro", font=theme.font_body(12),
                     text_color=TEXT_TERTIARY).pack(anchor="w", pady=(0, 10))

        tabsf = ctk.CTkFrame(c, fg_color="transparent")
        tabsf.pack(fill="x", pady=(0, 12))
        for key, label in (("AT", "Antico Test."), ("NT", "Nuovo Test.")):
            on = self._bib_testament == key
            ctk.CTkButton(tabsf, text=label, height=30, corner_radius=15,
                         font=theme.font_body(12, bold=True),
                         fg_color=ACCENT if on else CARD_ROW,
                         text_color="white" if on else TEXT_TERTIARY,
                         hover_color=ACCENT_HOVER if on else SURFACE_3,
                         command=lambda k=key: self._set_bib_testament(k)
                         ).pack(side="left", fill="x", expand=True, padx=(0, 3) if key == "AT" else (3, 0))

        primary = self._primary_lang()
        books = self._bible.books(primary)   # 66, ordered by position
        group = books[:39] if self._bib_testament == "AT" else books[39:]
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill="x")
        cols = 3
        for i, (num, name) in enumerate(group):
            selected = num == self._bib_book
            grp_border, grp_fill, grp_text = theme.bible_book_group_colors(self._bib_testament, i)
            btn = ctk.CTkButton(grid, text=name, height=46, corner_radius=20,
                                font=theme.font_body(15, bold=selected),
                                fg_color=SEL_BG if selected else grp_fill,
                                border_width=1,
                                border_color=SEL_BORDER if selected else grp_border,
                                text_color=TEXT_PRIMARY if selected else grp_text,
                                hover_color=SURFACE_4,
                                command=lambda n=num, nm=name: self._bib_select_book(n, nm))
            btn.grid(row=i // cols, column=i % cols, padx=3, pady=3, sticky="ew")
        for col in range(cols):
            grid.grid_columnconfigure(col, weight=1)

    def _render_chapter_column(self):
        c = self._bib_col_chapters
        if self._bib_book is None:
            ctk.CTkLabel(c, text="Scegli un libro per vedere i capitoli.",
                         text_color=TEXT_FAINT, font=theme.font_body(12),
                         wraplength=160, justify="left").pack(anchor="w", pady=20, padx=4)
            return
        # Recomputed from the book number every render (not read back from
        # self._bib_book_name) so switching the primary language updates the
        # title immediately instead of showing a stale name.
        self._bib_book_name = self._bible.book_name(self._primary_lang(), self._bib_book)
        ctk.CTkLabel(c, text=self._bib_book_name, font=theme.font_section(18),
                     text_color=TEXT_PRIMARY, wraplength=200, justify="left"
                     ).pack(anchor="w", pady=(4, 2))
        chs = self._bible.chapters(self._primary_lang(), self._bib_book)
        ctk.CTkLabel(c, text=f"{len(chs)} capitoli", font=theme.font_body(11),
                     text_color=TEXT_TERTIARY).pack(anchor="w", pady=(0, 10))
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill="x")
        cols = 4
        for i, ch in enumerate(chs):
            selected = ch == self._bib_chapter
            _circle(grid, str(ch), None, 22, width=54, height=50,
                   fg_color=ACCENT if selected else CARD_ROW,
                   text_color="white" if selected else TEXT_SECONDARY,
                   font=theme.font_body(15, bold=selected),
                   hover_color=ACCENT_HOVER if selected else SURFACE_4,
                   command=lambda ch_=ch: self._bib_select_chapter(ch_)
                   ).grid(row=i // cols, column=i % cols, padx=2, pady=2)

    def _render_verse_column(self):
        c = self._bib_col_verses
        if self._bib_book is None or self._bib_chapter is None:
            ctk.CTkLabel(c, text="Scegli un libro e un capitolo per vedere i versetti.",
                         text_color=TEXT_FAINT, font=theme.font_body(12),
                         wraplength=280, justify="left").pack(anchor="w", pady=20, padx=4)
            return
        title_row = ctk.CTkFrame(c, fg_color="transparent")
        title_row.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(title_row, text=self._bib_book_name, font=theme.font_section(18),
                     text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkLabel(title_row, text=f"capitolo {self._bib_chapter}", font=theme.font_body(13),
                     text_color=TEXT_TERTIARY).pack(side="left", padx=(8, 0), pady=(4, 0))

        primary = self._primary_lang()
        lang_row = ctk.CTkFrame(c, fg_color="transparent")
        lang_row.pack(fill="x", pady=(10, 12))
        ctk.CTkLabel(lang_row, text="+ ALTRE LINGUE", font=theme.font_label(10),
                     text_color=TEXT_LABEL).pack(side="left", padx=(0, 8))
        self._lang_btns_verse = {}
        for code in self._bible.languages():
            if code == primary:
                continue
            b = ctk.CTkButton(lang_row, text=code.upper(), width=52, height=26, corner_radius=13,
                              font=theme.font_body(11, bold=True),
                              command=lambda c_=code: self._toggle_lang(c_))
            b.pack(side="left", padx=3)
            self._lang_btns_verse[code] = b
        self._restyle_lang_btns_verse()
        ctk.CTkButton(lang_row, text="+", width=26, height=26, corner_radius=13,
                      fg_color=SURFACE_3, text_color=TEXT_TERTIARY, hover_color=SURFACE_4,
                      font=theme.font_body(13, bold=True),
                      command=self._open_bible_language_settings).pack(side="left", padx=(6, 0))

        for vnum, _t in self._bible.verses(primary, self._bib_book, self._bib_chapter):
            self._verse_card(vnum, primary)

    def _open_bible_language_settings(self):
        self._goto_settings("bibbia")

    def _verse_card(self, vnum, primary_lang):
        cat = SLOT_COLORS["versetto"]
        pd = self._proj_verse_data if self._proj_mode == "verse" else None
        is_live = bool(pd and pd.get("book") == self._bib_book
                       and pd.get("chapter") == self._bib_chapter and pd.get("verse") == vnum)
        row = ctk.CTkFrame(self._bib_col_verses, corner_radius=12,
                           fg_color=SEL_BG if is_live else CARD_ROW,
                           border_width=1 if is_live else 0, border_color=SEL_BORDER)
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=str(vnum), width=26, font=theme.font_label(12),
                     text_color=cat).pack(side="left", padx=(12, 4), pady=10)
        txt = self._bible.get_verse(primary_lang, self._bib_book, self._bib_chapter, vnum) or ""
        vlbl = ctk.CTkLabel(row, text=txt, anchor="w", justify="left",
                            font=theme.font_body(13),
                            text_color=TEXT_PRIMARY if is_live else TEXT_SECONDARY)
        vlbl.pack(side="left", fill="x", expand=True, pady=10)
        _auto_wrap_label(vlbl)
        if is_live:
            ctk.CTkLabel(row, text="In proiezione", font=theme.font_body(11, bold=True),
                         text_color=ACCENT).pack(side="right", padx=12)
        else:
            ctk.CTkButton(row, text="Proietta", width=88, height=26, corner_radius=13,
                          font=theme.font_body(12, bold=True),
                          command=lambda v=vnum: self._project_verse(v)).pack(side="right", padx=8)

    def _resolve_theme_color(self, value):
        """A (light, dark) theme tuple resolved to the single hex that's
        actually active right now — needed for plain tkinter widgets (e.g.
        Text, used for search-match highlighting) which aren't
        appearance-mode-aware the way CTk widgets are."""
        if isinstance(value, tuple):
            return value[1] if ctk.get_appearance_mode() == "Dark" else value[0]
        return value

    def _highlighted_verse_text(self, parent, text, query, wrap_chars=68):
        """A read-only Text widget showing `text` with every occurrence of
        `query` highlighted — matched the same accent/case-insensitive way
        as core.bible's own search (via core.textutil.normalize), which a
        plain CTkLabel can't render (no inline multi-color runs). Height is
        estimated from character count up front, synchronously — the
        previous version measured actual wrapped line count via a
        <Configure> binding + a deferred .after() per widget, which was fine
        for one widget but made typing in the search box feel like it froze
        once up to 80 of these got rebuilt on every keystroke."""
        from core.textutil import normalize
        n_lines = max(1, -(-len(text) // wrap_chars))  # ceil division, no import needed
        tv = tk.Text(parent, wrap="word", height=n_lines, bd=0, highlightthickness=0,
                     font=theme.font_body(13), padx=0, pady=0, cursor="arrow", takefocus=0,
                     bg=self._resolve_theme_color(CARD_ROW),
                     fg=self._resolve_theme_color(TEXT_SECONDARY))
        tv.insert("1.0", text)
        norm_text, norm_query = normalize(text), normalize(query)
        if norm_query and len(norm_text) == len(text):
            tv.tag_configure("hl", background="#ff9800", foreground="#1a1000",
                             font=theme.font_body(13, bold=True))
            start, n = 0, len(norm_query)
            while True:
                idx = norm_text.find(norm_query, start)
                if idx < 0:
                    break
                tv.tag_add("hl", f"1.0+{idx}c", f"1.0+{idx + n}c")
                start = idx + n
        tv.configure(state="disabled")
        return tv

    def _render_bib_search(self, query):
        primary = self._primary_lang()
        results = self._bible.search(primary, query, limit=80)
        ctk.CTkLabel(self._bib_content, text=f"{len(results)} risultati per «{query}»",
                     text_color=TEXT_FAINT, font=theme.font_body(11)).pack(anchor="w", pady=4)
        cat = SLOT_COLORS["versetto"]
        for book, chap, vnum, _txt in results:
            card = ctk.CTkFrame(self._bib_content, fg_color=CARD_ROW, corner_radius=13)
            card.pack(fill="x", pady=2)
            ref = f"{self._bible.book_name(primary, book)} {chap}:{vnum}"
            top = ctk.CTkFrame(card, fg_color="transparent"); top.pack(fill="x")
            ctk.CTkLabel(top, text=ref, font=theme.font_label(11),
                         text_color=cat).pack(side="left", padx=10, pady=6)
            ctk.CTkButton(top, text="Proietta", width=84, height=24, corner_radius=12,
                          font=theme.font_body(12, bold=True),
                          command=lambda b=book, c=chap, v=vnum: self._project_verse_ref(b, c, v)
                          ).pack(side="right", padx=8)
            t = self._bible.get_verse(primary, book, chap, vnum) or ""
            self._highlighted_verse_text(card, t, query).pack(fill="x", padx=10, pady=(0, 8))

    def _render_verse_history(self):
        if not self._history.verses:
            ctk.CTkLabel(self._bib_content, text="Nessuna cronologia",
                         text_color=TEXT_TERTIARY).pack(pady=20)
        cat = SLOT_COLORS["versetto"]
        name_to_num = {name: num for num, name in self._bible.books(self._primary_lang())}
        for e in self._history.verses:
            row = ctk.CTkFrame(self._bib_content, fg_color=CARD_ROW, corner_radius=12)
            row.pack(fill="x", pady=3)
            col = ctk.CTkFrame(row, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True, padx=14, pady=10)
            ctk.CTkLabel(col, text=e.ref, anchor="w", font=theme.font_label(11),
                         text_color=cat).pack(anchor="w")
            prev = (e.text_it[:70] + "…") if len(e.text_it) > 70 else e.text_it
            ctk.CTkLabel(col, text=prev, anchor="w", wraplength=380, justify="left",
                         font=theme.font_body(13), text_color=TEXT_PRIMARY
                         ).pack(anchor="w", pady=(2, 0))
            used_at = self._format_used_at(e)
            if used_at:
                ctk.CTkLabel(col, text=used_at, anchor="w", font=theme.font_body(11),
                             text_color=TEXT_TERTIARY).pack(anchor="w", pady=(2, 0))
            book_num = name_to_num.get(e.book)
            if book_num is not None:
                _circle(row, "↺", 30, 15, "transparent", TEXT_TERTIARY,
                       font=theme.font_body(15), hover_color=SURFACE_3,
                       command=lambda b=book_num, c=e.chapter, v=e.verse:
                           self._project_verse_ref(b, c, v)
                       ).pack(side="right", padx=10)
        if self._history.verses:
            ctk.CTkButton(self._bib_content, text="Pulisci cronologia versetti", corner_radius=13,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._clear_verse_history).pack(pady=10)

    def _project_verse_ref(self, book, chap, vnum, profile: str = "bibbia", lesson_ctx=None):
        self._bib_book = book
        self._bib_book_name = self._bible.book_name(self._primary_lang(), book)
        self._bib_chapter = chap
        self._bib_testament = "AT" if book <= 39 else "NT"
        self._bib_tab.set("Naviga")
        self._bib_search.set("")
        self._project_verse(vnum, profile=profile, lesson_ctx=lesson_ctx)
        self._render_bib_content()

    def _build_verse_data(self, vnum: int) -> dict:
        langs = self._selected_langs()
        texts = {c: (self._bible.get_verse(c, self._bib_book, self._bib_chapter, vnum) or "")
                 for c in langs}
        ref = f"{self._bib_book_name} {self._bib_chapter}:{vnum}"
        return {"book": self._bib_book, "book_name": self._bib_book_name,
                "chapter": self._bib_chapter, "verse": vnum,
                "ref": ref, "langs": langs, "texts": texts}

    def _project_verse(self, vnum: int, profile: str = "bibbia", lesson_ctx=None):
        self._lesson_verse_ctx = None
        data = self._build_verse_data(vnum)
        self._project_verse_data(data, profile=profile, lesson_ctx=lesson_ctx)
        primary_text = data["texts"].get(data["langs"][0], "")
        self._history.add_verse(data["book_name"], data["chapter"], vnum, text_it=primary_text)
        self._save_history()
        if self._picker_type == "versetto" and self._picker_slot is not None:
            self._picker_slot.data["verse"] = data
            self._picker_slot.display_name = data["ref"]
            self._save_schedule()
            self._finish_picker()

    def _clear_verse_history(self):
        self._history.clear_verses()
        self._save_history()
        self._render_bib_content()

    # ════════════════════════════════════════════════════════════════════════
    #  PREGHIERE — persistent list of prayer requests (own JSON store, not
    #  part of the schedule): enter/track name+motivo, project one-at-a-time
    #  with next/prev (via _proj_registry, like Bible verses) or the whole
    #  list at once as a static slide.
    # ════════════════════════════════════════════════════════════════════════
    @staticmethod
    def _initials(name: str) -> str:
        parts = [p for p in name.strip().split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def _view_preghiere(self):
        cat = SLOT_COLORS["preghiera"]
        self._prayer_selected_ids &= {it["id"] for it in self._prayers}
        outer = ctk.CTkFrame(self._content, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        badge = ctk.CTkFrame(outer, fg_color="transparent")
        badge.pack(anchor="w", pady=(0, 4))
        icon_img = theme.icon("preghiera", "category", size=15)
        if icon_img is not None:
            ctk.CTkLabel(badge, text="", image=icon_img).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(badge, text="PREGHIERE", font=theme.font_label(11),
                     text_color=cat).pack(side="left")

        top = ctk.CTkFrame(outer, fg_color="transparent")
        top.pack(fill="x", pady=(0, 14))
        n = len(self._prayers)
        ctk.CTkLabel(top, text=f"{n} richiest{'a' if n == 1 else 'e'} attiv{'a' if n == 1 else 'e'}",
                     font=theme.font_title(), text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkButton(top, text="＋ Nuova richiesta", width=170, corner_radius=13,
                      font=theme.font_body(13, bold=True),
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._prayer_add_modal).pack(side="right")
        if self._prayers:
            ctk.CTkButton(top, text="Proietta elenco", width=140, corner_radius=13,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._project_prayer_list).pack(side="right", padx=6)
            n_sel = len(self._prayer_selected_ids)
            if n_sel:
                ctk.CTkButton(top, text=f"Proietta selezionati ({n_sel})", width=170,
                              corner_radius=13, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                              font=theme.font_body(12, bold=True),
                              command=self._project_prayer_selected).pack(side="right", padx=6)

        scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        if not self._prayers:
            ctk.CTkLabel(scroll, text="Nessuna richiesta di preghiera. Aggiungine una.",
                         text_color=TEXT_TERTIARY).pack(anchor="w", pady=20)
            return

        avatar_bg = theme._blend(cat, CARD_ROW[0], 0.25), theme._blend(cat, CARD_ROW[1], 0.25)
        for i, item in enumerate(self._prayers):
            row = ctk.CTkFrame(scroll, fg_color=CARD_ROW, corner_radius=14)
            row.pack(fill="x", pady=3)
            checked = item["id"] in self._prayer_selected_ids
            # Nested CTkFrame circles (corner_radius≈width/2) showed visible
            # seam artifacts at this small a size on customtkinter's
            # polygon-based draw engine, however the radius/border was tuned
            # — that engine just isn't built for true circles this small. A
            # plain tk.Canvas oval bypasses it entirely and is pixel-exact.
            ring_color = self._resolve_theme_color(SEL_BORDER if checked else BORDER)
            fill_color = self._resolve_theme_color(ACCENT if checked else CARD_ROW)
            hover_color = self._resolve_theme_color(ACCENT_HOVER if checked else SURFACE_4)
            row_bg = self._resolve_theme_color(CARD_ROW)
            chk = tk.Canvas(row, width=22, height=22, highlightthickness=0, bd=0,
                            bg=row_bg, cursor="hand2")
            circle = chk.create_oval(2, 2, 20, 20, fill=fill_color, outline=ring_color, width=2)
            if checked:
                chk.create_text(11, 11, text="✓", fill="white", font=("Helvetica", 12, "bold"))

            def _toggle(_e=None, iid=item["id"]):
                self._toggle_prayer_selected(iid)

            def _chk_enter(_e, c=chk, o=circle, hv=hover_color):
                c.itemconfigure(o, fill=hv)

            def _chk_leave(_e, c=chk, o=circle, fg=fill_color):
                c.itemconfigure(o, fill=fg)
            chk.bind("<Button-1>", _toggle)
            chk.bind("<Enter>", _chk_enter)
            chk.bind("<Leave>", _chk_leave)
            chk.pack(side="left", padx=(12, 4), pady=10)
            # Same fix as the nav rail: a CTkLabel with corner_radius this
            # close to half its size silently widens past width=34 to fit
            # the text (measured: 54×34), turning the circle into a pill.
            # A fixed-size CTkFrame + a separately overlaid, purely
            # decorative text label keeps the circle geometrically exact.
            avatar = ctk.CTkFrame(row, width=34, height=34, corner_radius=17,
                                  fg_color=avatar_bg)
            avatar.grid_propagate(False)
            avatar.pack(side="left", padx=(4, 10), pady=10)
            ctk.CTkLabel(avatar, text=self._initials(item["name"]), text_color=cat,
                        font=theme.font_label(13)).place(relx=0.5, rely=0.5, anchor="center")
            txt = ctk.CTkFrame(row, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True, pady=8)
            ctk.CTkLabel(txt, text=item["name"], anchor="w", font=theme.font_body(14, bold=True),
                         text_color=TEXT_PRIMARY).pack(anchor="w")
            if item.get("reason"):
                reason_color = theme.prayer_reason_color(
                    item["reason"], self._settings.get("prayer_reason_colors", {}))
                ctk.CTkLabel(txt, text=item["reason"], anchor="w", text_color=reason_color,
                             font=theme.font_body(12, bold=True)).pack(anchor="w")
            ctk.CTkButton(row, text="Proietta", width=80, height=28, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda idx=i: self._project_prayer(idx)).pack(side="left", padx=4)
            ctk.CTkButton(row, text="✎", width=30, height=28, corner_radius=11, fg_color="transparent",
                          text_color=TEXT_TERTIARY, hover_color=SURFACE_3,
                          command=lambda idx=i: self._prayer_edit_modal(idx)).pack(side="left", padx=2)
            ctk.CTkButton(row, text="✕", width=30, height=28, corner_radius=11, fg_color="transparent",
                          text_color=TEXT_TERTIARY, hover_color=DANGER_HOVER,
                          command=lambda idx=i: self._prayer_delete(idx)).pack(side="left", padx=(2, 10))

    def _view_preghiere_refresh(self):
        for w in self._content.winfo_children():
            w.destroy()
        self._view_preghiere()

    def _prayer_form_modal(self, title, name_init, reason_init, on_confirm):
        def build(body):
            ctk.CTkLabel(body, text="Nome:", anchor="w").pack(fill="x")
            name_e = ctk.CTkEntry(body)
            name_e.pack(fill="x", pady=(4, 12))
            name_e.insert(0, name_init)
            name_e.focus_set()

            ctk.CTkLabel(body, text="Motivo (opzionale):", anchor="w").pack(fill="x")
            reason_row = ctk.CTkFrame(body, fg_color="transparent")
            reason_row.pack(fill="x", pady=(4, 14))
            reason_e = ctk.CTkEntry(reason_row)
            reason_e.pack(side="left", fill="x", expand=True)
            reason_e.insert(0, reason_init)

            reason_colors = self._settings.get("prayer_reason_colors", {})
            cur_color = [theme.prayer_reason_color(reason_init, reason_colors)]
            swatch = ctk.CTkButton(reason_row, text="Colore", width=70, height=28,
                                   corner_radius=11, font=theme.font_body(12, bold=True),
                                   fg_color=cur_color[0],
                                   text_color=theme.readable_text_for(cur_color[0]))

            def pick_reason_color():
                reason = reason_e.get().strip()
                c = colorchooser.askcolor(title="Colore per questo motivo",
                                          initialcolor=cur_color[0])
                if c and c[1] and reason:
                    self._set_prayer_reason_color(reason, c[1])
                    cur_color[0] = c[1]
                    swatch.configure(fg_color=c[1], text_color=theme.readable_text_for(c[1]))
            swatch.configure(command=pick_reason_color)
            swatch.pack(side="left", padx=(8, 0))

            def _update_swatch(_e=None):
                reason = reason_e.get().strip()
                col = theme.prayer_reason_color(reason, self._settings.get("prayer_reason_colors", {}))
                cur_color[0] = col
                swatch.configure(fg_color=col, text_color=theme.readable_text_for(col))
            reason_e.bind("<KeyRelease>", _update_swatch)

            def confirm():
                name = name_e.get().strip()
                reason = reason_e.get().strip()
                self._close_modal()
                if name:
                    on_confirm(name, reason)
            name_e.bind("<Return>", lambda e: confirm())
            reason_e.bind("<Return>", lambda e: confirm())
            btns = ctk.CTkFrame(body, fg_color="transparent")
            btns.pack(fill="x")
            ctk.CTkButton(btns, text="Annulla", width=100, fg_color=BTN_SECONDARY,
                          text_color=TEXT_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          command=self._close_modal).pack(side="right", padx=4)
            ctk.CTkButton(btns, text="Salva", width=100, command=confirm).pack(side="right", padx=4)
        self._open_modal(title, build, width=420, height=280)

    def _set_prayer_reason_color(self, reason: str, hexcol: str):
        key = reason.strip().lower()
        if not key:
            return
        colors = dict(self._settings.get("prayer_reason_colors", {}))
        colors[key] = hexcol
        self._settings["prayer_reason_colors"] = colors
        cfg.save(self._settings)

    def _prayer_add_modal(self):
        self._prayer_form_modal("Nuova richiesta di preghiera", "", "", self._prayer_add_confirm)

    def _prayer_edit_modal(self, idx):
        item = self._prayers[idx]
        self._prayer_form_modal("Modifica richiesta", item["name"], item.get("reason", ""),
                                lambda name, reason: self._prayer_edit_confirm(idx, name, reason))

    def _prayer_add_confirm(self, name, reason):
        self._prayers.append(prayers_store.new_item(name, reason))
        prayers_store.save(self._prayers)
        self._view_preghiere_refresh()

    def _prayer_edit_confirm(self, idx, name, reason):
        self._prayers[idx]["name"] = name
        self._prayers[idx]["reason"] = reason
        prayers_store.save(self._prayers)
        self._view_preghiere_refresh()

    def _prayer_delete(self, idx):
        item = self._prayers[idx]

        def do_delete():
            del self._prayers[idx]
            prayers_store.save(self._prayers)
            if self._proj_mode == "prayer" and getattr(self, "_proj_prayer_idx", None) == idx:
                self._stop_projection()
            self._view_preghiere_refresh()
        self._ask_confirm("Elimina richiesta",
                          f"Eliminare la richiesta di preghiera per \"{item['name']}\"?", do_delete)

    def _project_prayer(self, idx: int):
        if not self._prayers or not (0 <= idx < len(self._prayers)):
            return
        item = self._prayers[idx]
        self._proj_mode = "prayer"
        self._proj_prayer_idx = idx
        win = self._ensure_projection()
        win.set_background(self._settings.get("verse_bg_color", "#0b132b"),
                           self._settings.get("verse_bg_image", ""))
        win.set_text_color(self._settings.get("verse_text_color", "#ffffff"))
        reason_color = theme.prayer_reason_color(
            item.get("reason", ""), self._settings.get("prayer_reason_colors", {}))
        win.show_text(item["name"], secondary=item.get("reason", ""), secondary_pos="bottom",
                      autofit=True, secondary_scale=0.08, secondary_italic=True,
                      secondary_color=reason_color)
        n = len(self._prayers)
        self._proj_pill.configure(text=f"● Preghiera {idx + 1}/{n} — {item['name']}",
                                  text_color="#22c55e")

    def _prayer_step(self, delta: int):
        if self._proj_mode != "prayer" or not self._prayers:
            return
        idx = getattr(self, "_proj_prayer_idx", 0) + delta
        if not (0 <= idx < len(self._prayers)):
            return
        self._project_prayer(idx)

    def _project_prayer_list(self):
        if not self._prayers:
            return
        self._proj_mode = "text"
        win = self._ensure_projection()
        win.set_background(self._settings.get("verse_bg_color", "#0b132b"),
                           self._settings.get("verse_bg_image", ""))
        win.set_text_color(self._settings.get("verse_text_color", "#ffffff"))
        reason_colors = self._settings.get("prayer_reason_colors", {})
        rows = [(it["name"], it.get("reason", ""),
                 theme.prayer_reason_color(it.get("reason", ""), reason_colors))
                for it in self._prayers]
        win.show_table(rows)
        self._proj_pill.configure(text=f"● Elenco preghiere ({len(rows)})", text_color="#22c55e")

    def _toggle_prayer_selected(self, item_id: str):
        if item_id in self._prayer_selected_ids:
            self._prayer_selected_ids.discard(item_id)
        else:
            self._prayer_selected_ids.add(item_id)
        self._view_preghiere_refresh()

    def _project_prayer_selected(self):
        reason_colors = self._settings.get("prayer_reason_colors", {})
        rows = [(it["name"], it.get("reason", ""),
                 theme.prayer_reason_color(it.get("reason", ""), reason_colors))
                for it in self._prayers if it["id"] in self._prayer_selected_ids]
        if not rows:
            return
        self._proj_mode = "text"
        win = self._ensure_projection()
        win.set_background(self._settings.get("verse_bg_color", "#0b132b"),
                           self._settings.get("verse_bg_image", ""))
        win.set_text_color(self._settings.get("verse_text_color", "#ffffff"))
        win.show_table(rows)
        self._proj_pill.configure(text=f"● Preghiere selezionate ({len(rows)})",
                                  text_color="#22c55e")

    # ════════════════════════════════════════════════════════════════════════
    #  MEDIA
    # ════════════════════════════════════════════════════════════════════════
    def _download_dest(self):
        return (self._settings.get("youtube_folder", "")
                or self._settings.get("background_music_folder", "")
                or os.path.join(os.path.expanduser("~"), "Downloads"))

    def _view_media(self):
        scroll = ctk.CTkScrollableFrame(self._content, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(scroll, text="Media", font=theme.font_title(),
                     text_color=TEXT_PRIMARY).pack(anchor="w", pady=(0, 16))

        ctk.CTkLabel(scroll, text="DOWNLOAD DA YOUTUBE", font=theme.font_label(11),
                     text_color=TEXT_LABEL).pack(anchor="w", pady=(0, 8))
        r = ctk.CTkFrame(scroll, fg_color="transparent")
        r.pack(fill="x", pady=(0, 4))
        self._yt_url = ctk.CTkEntry(r, placeholder_text="Incolla link video…", height=38,
                                    corner_radius=13, fg_color=CARD_ROW, border_color=BORDER,
                                    border_width=1, text_color=TEXT_PRIMARY,
                                    placeholder_text_color=TEXT_FAINT)
        self._yt_url.pack(side="left", fill="x", expand=True)
        self._yt_kind = tk.StringVar(value="audio")
        ctk.CTkOptionMenu(r, values=["audio", "video"], variable=self._yt_kind, width=90,
                          height=38, corner_radius=13, fg_color=CARD_ROW,
                          button_color=SURFACE_3, button_hover_color=SURFACE_4,
                          text_color=TEXT_PRIMARY, font=theme.font_body(13)).pack(side="left", padx=6)
        # NOT reset here: a download may already be running in the background
        # (started before the user navigated away from this page) — resetting
        # these on every rebuild is what left the Annulla button permanently
        # stuck disabled after leaving and re-entering the Media tab.
        if not hasattr(self, "_dl_active"):
            self._dl_active = False
            self._dl_cancel = False
        ctk.CTkButton(r, text="Scarica", width=90, height=38, corner_radius=13,
                      font=theme.font_body(13, bold=True), fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=lambda: self._download_youtube(self._yt_kind.get())).pack(side="left")
        self._yt_cancel_btn = ctk.CTkButton(r, text="Annulla", width=80, height=38, corner_radius=13,
                                             font=theme.font_body(13, bold=True),
                                             fg_color=DANGER_FILL, hover_color=DANGER_FILL_HOVER,
                                             text_color=DANGER_FILL_TEXT,
                                             command=self._cancel_download,
                                             state=("normal" if self._dl_active else "disabled"))
        self._yt_cancel_btn.pack(side="left", padx=(4, 0))
        self._yt_status = ctk.CTkLabel(scroll, text=getattr(self, "_dl_status_text", ""),
                                       text_color=TEXT_TERTIARY, font=theme.font_body(11),
                                       anchor="w")
        self._yt_status.pack(fill="x", pady=(4, 0))

        # downloaded files list
        self._dl_list = ctk.CTkFrame(scroll, fg_color="transparent")
        self._dl_list.pack(fill="x", pady=(6, 26))
        self._refresh_downloads()

        # pause-music folder + track list
        ctk.CTkLabel(scroll, text="MUSICA DI SOTTOFONDO — PAUSA", font=theme.font_label(11),
                     text_color=TEXT_LABEL).pack(anchor="w", pady=(0, 8))
        r2 = ctk.CTkFrame(scroll, fg_color="transparent")
        r2.pack(fill="x", pady=(0, 10))
        folder = self._settings.get("background_music_folder", "")
        self._music_lbl = ctk.CTkLabel(r2, text=folder or "Nessuna cartella",
                                       text_color=TEXT_TERTIARY, font=theme.font_body(12))
        self._music_lbl.pack(side="left")
        ctk.CTkButton(r2, text="Cambia", width=110, height=32, corner_radius=12,
                      fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                      text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                      command=self._pick_music_folder).pack(side="right")
        ctk.CTkButton(r2, text="▶ Avvia", width=80, height=32, corner_radius=12,
                      font=theme.font_body(12, bold=True),
                      command=self._start_pause_music).pack(side="right", padx=6)
        self._pause_track_list = ctk.CTkFrame(scroll, fg_color="transparent")
        self._pause_track_list.pack(fill="x")
        self._refresh_pause_tracks()

    def _refresh_downloads(self):
        if not hasattr(self, "_dl_list") or not self._dl_list.winfo_exists():
            return
        for w in self._dl_list.winfo_children():
            w.destroy()
        dest = self._download_dest()
        video_exts = (".mp4", ".mov", ".mkv", ".webm", ".avi")
        audio_exts = (".mp3", ".m4a", ".wav", ".ogg", ".flac")
        try:
            files = [f for f in os.listdir(dest)
                     if os.path.splitext(f)[1].lower() in (*audio_exts, *video_exts)]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(dest, f)), reverse=True)
        except Exception:
            files = []
        if not files:
            ctk.CTkLabel(self._dl_list, text="Nessun file scaricato in questa cartella.",
                         text_color=TEXT_FAINT, font=theme.font_body(11)).pack(anchor="w", pady=6)
            return
        for f in files[:30]:
            path = os.path.join(dest, f)
            is_video = os.path.splitext(f)[1].lower() in video_exts
            icon_img = theme.icon("video" if is_video else "audio", "category", size=26)
            row = ctk.CTkFrame(self._dl_list, fg_color=CARD_ROW, corner_radius=12)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text="", image=icon_img, width=44, height=30
                        ).pack(side="left", padx=(12, 10), pady=10)
            col = ctk.CTkFrame(row, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True, pady=8)
            ctk.CTkLabel(col, text=os.path.splitext(f)[0], anchor="w",
                         font=theme.font_body(13, bold=True), text_color=TEXT_PRIMARY
                         ).pack(anchor="w")
            ctk.CTkLabel(col, text=f"Scaricato — {self._file_meta(path)}", anchor="w",
                         font=theme.font_body(11), text_color=TEXT_TERTIARY).pack(anchor="w")
            _circle(row, "▷", 30, 15, "transparent", TEXT_TERTIARY, hover_color=SURFACE_3,
                   font=theme.font_body(13),
                   command=lambda p=path: self._use_download(p)).pack(side="left", padx=2)
            _circle(row, "✕", 30, 15, "transparent", TEXT_TERTIARY, hover_color=DANGER_HOVER,
                   font=theme.font_body(12),
                   command=lambda p=path: self._delete_download(p)).pack(side="left", padx=(0, 10))

    def _refresh_pause_tracks(self):
        """Read-only list of tracks in the pause-music folder, matching the
        mockup's look — the currently-playing one is highlighted via
        AudioManager.current_pause_track(). There's deliberately no
        click-to-play-this-specific-track: PlaylistChannel only exposes
        "start the whole folder" (shuffle/sequential), not "play track N", so
        adding per-track selection would be a new backend feature, not a
        restyle — flagged as a possible follow-up, not built here."""
        box = getattr(self, "_pause_track_list", None)
        if box is None or not box.winfo_exists():
            return
        for w in box.winfo_children():
            w.destroy()
        folder = self._settings.get("background_music_folder", "")
        exts = (".mp3", ".m4a", ".wav", ".ogg", ".flac")
        try:
            files = sorted(f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in exts)
        except Exception:
            files = []
        if not files:
            return
        current = self._audio.current_pause_track() if self._audio.pause_music_is_playing() else None
        for f in files[:30]:
            path = os.path.join(folder, f)
            playing = current and os.path.samefile(path, current) if current and os.path.exists(current) \
                else False
            row = ctk.CTkFrame(box, corner_radius=12,
                               fg_color=SEL_BG if playing else "transparent",
                               border_width=1 if playing else 0, border_color=SEL_BORDER)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="▶" if playing else "♪", width=24,
                         text_color="white" if playing else TEXT_TERTIARY,
                         font=theme.font_body(12)).pack(side="left", padx=(12, 2), pady=10)
            ctk.CTkLabel(row, text=os.path.splitext(f)[0], anchor="w",
                         font=theme.font_body(13, bold=playing),
                         text_color=TEXT_PRIMARY if playing else TEXT_SECONDARY
                         ).pack(side="left", fill="x", expand=True, pady=10)
            if playing:
                ctk.CTkLabel(row, text="In riproduzione", font=theme.font_body(11, bold=True),
                             text_color=ACCENT).pack(side="right", padx=12)

    def _file_meta(self, path):
        try:
            mb = os.path.getsize(path) / (1024 * 1024)
        except Exception:
            mb = 0
        dur = ""
        try:
            from mutagen import File as MF
            f = MF(path)
            if f and getattr(f, "info", None):
                s = int(f.info.length); dur = f"{s // 60}:{s % 60:02d} · "
        except Exception:
            pass
        return f"{dur}{mb:.0f} MB"

    def _use_download(self, path):
        # play audio on the main player; open video externally
        if os.path.splitext(path)[1].lower() in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
            projector.open_file_external(path)
        else:
            self._audio.play_media(path, label=os.path.basename(path))

    def _delete_download(self, path):
        self._ask_confirm("Elimina file", f"Eliminare «{os.path.basename(path)}»?",
                          lambda: (os.remove(path) if os.path.isfile(path) else None,
                                   self._refresh_downloads()))

    def _cancel_download(self):
        self._dl_cancel = True

    def _download_youtube(self, kind: str = "audio"):
        url = self._yt_url.get().strip()
        if not url:
            return
        self._dl_cancel = False
        self._dl_active = True
        self._dl_status_text = "Download in corso… (può richiedere un minuto)"
        self._yt_status.configure(text=self._dl_status_text)
        try:
            self._yt_cancel_btn.configure(state="normal")
        except Exception:
            pass
        dest = (self._settings.get("youtube_folder", "")
                or self._settings.get("background_music_folder", "")
                or os.path.join(os.path.expanduser("~"), "Downloads"))

        def safe_cfg(attr, **kwargs):
            # The user may navigate away from the Media view while a download
            # runs in the background — its widgets get destroyed, but this
            # closure still fires later via `after()`. Guard against that.
            # Status text is also mirrored onto self so a fresh _view_media()
            # rebuild (after navigating back) picks up where things left off
            # instead of showing a blank label.
            if attr == "_yt_status" and "text" in kwargs:
                self._dl_status_text = kwargs["text"]
            w = getattr(self, attr, None)
            if w is not None and w.winfo_exists():
                w.configure(**kwargs)

        def progress_hook(d):
            if self._dl_cancel:
                raise Exception("Annullato dall'utente")
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes")
                if total and downloaded is not None:
                    pct = f"{downloaded / total * 100:.0f}%"
                else:
                    pct = _ANSI_RE.sub("", d.get("_percent_str", "")).strip()
                self._safe_after(lambda: safe_cfg("_yt_status", text=f"Download… {pct}"))

        def run():
            try:
                import yt_dlp
            except Exception:
                self._safe_after(lambda: safe_cfg("_yt_status", text="yt-dlp non disponibile."))
                return
            outtmpl = os.path.join(dest, "%(title)s.%(ext)s")
            ffmpeg_loc = None
            try:
                import imageio_ffmpeg
                ffmpeg_loc = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                pass
            # A pasted single-video link often still carries a playlist ID
            # (e.g. "watch?v=X&list=Y" from a "up next"/queue context) —
            # without noplaylist, yt-dlp downloads the entire playlist instead
            # of just that one video.
            if kind == "audio":
                opts = {"format": "bestaudio/best", "outtmpl": outtmpl, "noplaylist": True,
                        "postprocessors": [{"key": "FFmpegExtractAudio",
                                            "preferredcodec": "mp3"}],
                        "progress_hooks": [progress_hook], "quiet": True, "no_warnings": True}
            else:
                # Honor Impostazioni → YouTube → "Qualità predefinita": cap the
                # video height for 720p/1080p, keep the historical
                # best-available format string otherwise.
                quality = self._settings.get("youtube_quality", "Migliore disponibile")
                cap = {"720p": 720, "1080p": 1080}.get(quality)
                fmt = (f"bv*[height<={cap}]+ba/best[height<={cap}]" if cap
                       else "bv*+ba/best")
                opts = {"format": fmt, "outtmpl": outtmpl, "noplaylist": True,
                        "merge_output_format": "mp4",
                        "progress_hooks": [progress_hook], "quiet": True, "no_warnings": True}
            if ffmpeg_loc:
                opts["ffmpeg_location"] = ffmpeg_loc
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                final_path = None
                try:
                    final_path = info["requested_downloads"][0]["filepath"]
                except Exception:
                    try:
                        final_path = ydl.prepare_filename(info)
                    except Exception:
                        final_path = None
                msg = f"Completato! Salvato in: {dest}"
                # YouTube often serves AV1 video, which the in-app player can't
                # decode (silent black screen) — re-encode to H.264 so it plays.
                if kind == "video" and ffmpeg_loc and final_path and os.path.isfile(final_path):
                    from core.video import probe_video_codec, needs_transcode, transcode_to_h264
                    codec = probe_video_codec(final_path, ffmpeg_loc)
                    if needs_transcode(codec):
                        codec_label = codec or "non rilevato"
                        self._safe_after(lambda: safe_cfg(
                            "_yt_status", text=f"Conversione in formato compatibile ({codec_label} → H.264)…"))
                        if transcode_to_h264(final_path, ffmpeg_loc):
                            msg = f"Completato! Convertito in H.264 e salvato in: {dest}"
                        else:
                            msg = "Scaricato, ma la conversione è fallita: potrebbe non riprodursi."
            except Exception as ex:
                txt = str(ex)
                if self._dl_cancel:
                    msg = "Download annullato."
                elif "ffmpeg" in txt.lower():
                    msg = "Serve ffmpeg per la conversione. Installalo o scarica come Video."
                else:
                    msg = f"Errore: {txt[:160]}"
            self._dl_cancel = False
            self._dl_active = False
            self._safe_after(lambda: safe_cfg("_yt_status", text=msg))
            self._safe_after(lambda: safe_cfg("_yt_cancel_btn", state="disabled"))
            self._safe_after(self._refresh_downloads)
        threading.Thread(target=run, daemon=True).start()

    def _pick_music_folder(self):
        folder = filedialog.askdirectory(title="Cartella musica di pausa")
        if folder:
            self._settings["background_music_folder"] = folder
            cfg.save(self._settings)
            self._music_lbl.configure(text=folder)
            self._refresh_pause_tracks()

    def _start_pause_music(self):
        folder = self._settings.get("background_music_folder", "")
        if not folder:
            self._info("Musica pausa", "Nessuna cartella configurata (sezione Media).")
            return
        volume = self._settings.get("pause_music_volume", 70) / 100
        self._audio.start_pause_music(folder, self._settings.get("background_music_mode", "shuffle"),
                                      on_track_change=self._on_track_change, volume=volume)
        self._refresh_pause_tracks()

    def _on_track_change(self, path):
        if hasattr(self, "_pause_lbl") and self._pause_lbl.winfo_exists():
            self._safe_after(lambda: self._pause_lbl.configure(text=os.path.basename(path)))
        self._refresh_pause_tracks()

    # ════════════════════════════════════════════════════════════════════════
    #  IMPOSTAZIONI
    # ════════════════════════════════════════════════════════════════════════
    SETTINGS_CATS = [
        ("generale", "Generale"),
        ("inni", "Inni"),
        ("bibbia", "Bibbia"),
        ("pausa", "Pausa"),
        ("offerta", "Offerta"),
        ("sfondo", "Sfondo"),
        ("lezione", "Lezione"),
        ("campanello", "Campanello"),
        ("youtube", "YouTube"),
        ("cronologia", "Cronologia"),
    ]

    def _view_settings(self):
        outer = ctk.CTkFrame(self._content, fg_color="transparent")
        outer.pack(fill="both", expand=True)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=1)

        cats = ctk.CTkFrame(outer, width=180, corner_radius=0, fg_color=theme.BG)
        cats.grid(row=0, column=0, sticky="ns")
        cats.grid_propagate(False)
        ctk.CTkLabel(cats, text="IMPOSTAZIONI", font=theme.font_label(11),
                     text_color=TEXT_LABEL).pack(anchor="w", padx=14, pady=(14, 8))
        if not hasattr(self, "_settings_cat"):
            self._settings_cat = "generale"
        self._cat_btns = {}
        for key, label in self.SETTINGS_CATS:
            b = ctk.CTkButton(cats, text=label, anchor="w", height=34, corner_radius=12,
                              font=theme.font_body(13, bold=(key == self._settings_cat)),
                              fg_color=ACCENT if key == self._settings_cat else "transparent",
                              text_color="white" if key == self._settings_cat else TEXT_SECONDARY,
                              hover_color=SURFACE_3,
                              command=lambda k=key: self._select_settings_cat(k))
            b.pack(fill="x", padx=8, pady=1)
            self._cat_btns[key] = b

        self._settings_body = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        self._settings_body.grid(row=0, column=1, sticky="nsew", padx=16, pady=12)
        self._render_settings_cat()

    def _select_settings_cat(self, key):
        self._settings_cat = key
        for k, b in self._cat_btns.items():
            on = (k == key)
            b.configure(fg_color=ACCENT if on else "transparent",
                        text_color="white" if on else TEXT_SECONDARY,
                        font=theme.font_body(13, bold=on))
        self._render_settings_cat()

    def _render_settings_cat(self):
        body = self._settings_body
        for w in body.winfo_children():
            w.destroy()

        def hdr(t):
            ctk.CTkLabel(body, text=t.upper(), font=theme.font_label(11),
                         text_color=TEXT_LABEL).pack(anchor="w", pady=(12, 4))

        def card():
            c = ctk.CTkFrame(body, fg_color=CARD)
            c.pack(fill="x", pady=4)
            return c

        cat = self._settings_cat
        if cat == "generale":
            hdr("Aspetto applicazione")
            am = tk.StringVar(value=self._settings.get("appearance_mode", "System"))
            ctk.CTkSegmentedButton(body, values=["Light", "Dark", "System"], variable=am,
                                   height=32, fg_color=CARD_ROW, selected_color=ACCENT,
                                   selected_hover_color=ACCENT_HOVER, unselected_color=CARD_ROW,
                                   unselected_hover_color=SURFACE_3, text_color=TEXT_TERTIARY,
                                   text_color_disabled=TEXT_TERTIARY, font=theme.font_body(12, bold=True),
                                   command=self._change_appearance).pack(anchor="w", pady=2)
            hdr("Schermo di proiezione")
            mons = []
            try:
                from ui.projection import list_monitors
                mons = list_monitors()
            except Exception:
                pass
            if mons:
                names = [f"Schermo {i+1} ({m['width']}×{m['height']})" + (" • principale" if m['primary'] else "")
                         for i, m in enumerate(mons)]
                idx = self._settings.get("projection_screen", 1)
                cur = names[idx] if 0 <= idx < len(names) else names[-1]
                var = tk.StringVar(value=cur)
                ctk.CTkOptionMenu(body, values=names, variable=var, height=34, corner_radius=13,
                                  fg_color=CARD_ROW, button_color=SURFACE_3,
                                  button_hover_color=SURFACE_4, text_color=TEXT_PRIMARY,
                                  font=theme.font_body(13),
                                  command=lambda v: self._set("projection_screen", names.index(v))
                                  ).pack(anchor="w", pady=2)
            else:
                ctk.CTkLabel(body, text="Rilevamento schermi non disponibile.",
                             text_color=TEXT_TERTIARY).pack(anchor="w")
            hdr("Tutorial")
            ctk.CTkLabel(body, text="La guida passo-passo mostrata al primo avvio: "
                                    "scaletta, inni, Bibbia, lezione, proiezione e comandi rapidi.",
                         text_color=TEXT_TERTIARY, wraplength=520, justify="left",
                         font=theme.font_body(12)).pack(anchor="w", pady=(0, 4))
            ctk.CTkButton(body, text="Rivedi il tutorial", height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=self._show_tutorial).pack(anchor="w", pady=2)

        elif cat == "inni":
            hdr("Database inni")
            for folder in self._settings.get("databases", []):
                row = ctk.CTkFrame(body, fg_color=CARD_ROW, corner_radius=12)
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(row, text=os.path.basename(folder) or folder, anchor="w",
                             font=theme.font_body(13, bold=True), text_color=TEXT_PRIMARY).pack(
                    side="left", fill="x", expand=True, padx=12, pady=8)
                ctk.CTkLabel(row, text=folder, text_color=TEXT_FAINT,
                             font=theme.font_body(10)).pack(side="left", padx=6)
                _circle(row, "✕", 30, 15, "transparent", TEXT_TERTIARY, hover_color=DANGER_HOVER,
                       command=lambda f=folder: self._remove_db(f)).pack(side="right", padx=8)
            ctk.CTkButton(body, text="＋ Aggiungi cartella", height=34, corner_radius=13,
                          font=theme.font_body(12, bold=True),
                          command=self._add_db_folder).pack(anchor="w", pady=6)

        elif cat == "bibbia":
            hdr("Versioni installate")
            if self._bible and self._bible.ready:
                for code in self._bible.languages():
                    row = ctk.CTkFrame(body, fg_color=CARD_ROW, corner_radius=12)
                    row.pack(fill="x", pady=3)
                    ctk.CTkLabel(row, text=self._bible.language_label(code), width=110,
                                 anchor="w", font=theme.font_body(13, bold=True),
                                 text_color=TEXT_PRIMARY).pack(side="left", padx=12, pady=8)
                    vers = self._bible.versions(code)
                    if self._bible.has_multiple_versions(code):
                        var = tk.StringVar(value=self._bible.active_version_short(code))
                        ctk.CTkOptionMenu(row, values=[s for s, _f in vers], variable=var,
                                          height=28, corner_radius=10, fg_color=SURFACE_3,
                                          button_color=SURFACE_4, button_hover_color=BORDER,
                                          text_color=TEXT_PRIMARY, font=theme.font_body(12),
                                          command=lambda v, c=code: self._set_bible_version(c, v)
                                          ).pack(side="left", padx=4)
                    else:
                        ctk.CTkLabel(row, text=(vers[0][0] if vers else "—"),
                                     text_color=TEXT_TERTIARY, font=theme.font_body(12)
                                     ).pack(side="left", padx=4)
                    ctk.CTkButton(row, text="+ Aggiungi versione", width=140, height=26,
                                  corner_radius=11, fg_color=SURFACE_3, hover_color=SURFACE_4,
                                  text_color=TEXT_SECONDARY, font=theme.font_body(11, bold=True),
                                  command=lambda c=code: self._add_bible_version_for(c)
                                  ).pack(side="right", padx=8)
            else:
                ctk.CTkLabel(body, text="Nessuna Bibbia (metti i .db in 'bibles/').",
                             text_color=TEXT_TERTIARY).pack(anchor="w")
            ctk.CTkButton(body, text="+ Aggiungi lingua (.bib)", height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._add_bible_language).pack(anchor="w", pady=(8, 0))
            hdr("Grafica versetto")
            ctk.CTkLabel(body, text="Un template facoltativo, dedicato solo al versetto proiettato "
                                    "da questa sezione Bibbia — separato da quello usato per un "
                                    "versetto citato dentro una domanda di lezione.",
                         text_color=TEXT_TERTIARY, wraplength=520, justify="left"
                         ).pack(anchor="w", pady=(0, 8))

            hdr("Colori testo")
            vb_crow = ctk.CTkFrame(body, fg_color="transparent")
            vb_crow.pack(fill="x", pady=4)
            for key, label, default in (("testo", "Colore testo", "#ffffff"),
                                        ("riferimento", "Colore riferimento", SLOT_COLORS["lezione"])):
                self._profile_color_swatch(vb_crow, "versetto_bibbia", key, label, default)

            hdr("Carattere")
            for settings_key, label in (("verse_font_family", "Font testo"),
                                        ("verse_ref_font_family", "Font riferimento")):
                self._font_family_picker(
                    body, label,
                    get_value=lambda k=settings_key: self._settings.get(k, "Helvetica"),
                    set_value=lambda v, k=settings_key: self._set(k, v))

            hdr("Dimensione massima testo")
            for key, label in (("testo", "Testo"), ("riferimento", "Riferimento")):
                ctk.CTkLabel(body, text=label, anchor="w", font=theme.font_body(11, bold=True),
                             text_color=TEXT_SECONDARY).pack(anchor="w", pady=(2, 0))
                self._max_size_slider(
                    body, max_val=200,
                    get_value=lambda k=key: self._profile_max_size("versetto_bibbia", k),
                    set_value=lambda v, k=key: self._set_profile_max_size("versetto_bibbia", k, v))

            hdr("Template e riquadri")
            self._graphic_profile_editor(body, "versetto_bibbia", self._VERSE_GRAPHIC_BOX_DEFS, "bibbia")

        elif cat == "pausa":
            hdr("Musica di pausa")
            r = ctk.CTkFrame(body, fg_color="transparent")
            r.pack(fill="x", pady=2)
            folder = self._settings.get("background_music_folder", "")
            self._music_lbl = ctk.CTkLabel(r, text=folder or "Nessuna cartella",
                                           text_color=TEXT_TERTIARY, font=theme.font_body(12))
            self._music_lbl.pack(side="left")
            ctk.CTkButton(r, text="Sfoglia…", width=110, height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=self._pick_music_folder).pack(side="left", padx=8)
            mr = ctk.CTkFrame(body, fg_color="transparent")
            mr.pack(fill="x", pady=8)
            ctk.CTkLabel(mr, text="Modalità:", font=theme.font_body(12),
                         text_color=TEXT_SECONDARY).pack(side="left")
            mode = tk.StringVar(value=self._settings.get("background_music_mode", "shuffle"))
            ctk.CTkSegmentedButton(mr, values=["shuffle", "sequenza"], variable=mode, height=30,
                                   fg_color=CARD_ROW, selected_color=ACCENT,
                                   selected_hover_color=ACCENT_HOVER, unselected_color=CARD_ROW,
                                   unselected_hover_color=SURFACE_3, text_color=TEXT_TERTIARY,
                                   font=theme.font_body(12, bold=True),
                                   command=lambda v: self._set("background_music_mode", v)
                                   ).pack(side="left", padx=8)
            ap = tk.BooleanVar(value=self._settings.get("pause_music_autoplay", False))
            ctk.CTkSwitch(body, text="Riproduci automaticamente quando parte il timer", variable=ap,
                         progress_color=ACCENT, font=theme.font_body(13), text_color=TEXT_SECONDARY,
                         command=lambda: self._set("pause_music_autoplay", ap.get())
                         ).pack(anchor="w", pady=(6, 2))

            pvr = ctk.CTkFrame(body, fg_color="transparent")
            pvr.pack(fill="x", pady=(10, 2))
            ctk.CTkLabel(pvr, text="Volume musica di pausa:", font=theme.font_body(12),
                         text_color=TEXT_SECONDARY).pack(side="left")
            pv_lbl = ctk.CTkLabel(pvr, text=f"{self._settings.get('pause_music_volume', 70)}%",
                                  font=theme.font_body(12, bold=True), text_color=TEXT_PRIMARY, width=42)
            pv_lbl.pack(side="right")

            def _on_pause_volume(v, lb=pv_lbl):
                lb.configure(text=f"{int(v)}%")
                self._set("pause_music_volume", int(v))
                self._audio.set_pause_music_volume(int(v) / 100)
            pv_slider = ctk.CTkSlider(body, from_=0, to=100,
                                      progress_color=ACCENT, button_color=ACCENT,
                                      button_hover_color=ACCENT_HOVER, fg_color=SURFACE_3,
                                      command=_on_pause_volume)
            pv_slider.set(self._settings.get("pause_music_volume", 70))
            pv_slider.pack(fill="x", pady=(0, 6))

            hdr("Preset minuti rapidi")
            pr = ctk.CTkFrame(body, fg_color="transparent")
            pr.pack(fill="x", pady=(0, 6))
            for m in (5, 10, 15, 20):
                _circle(pr, str(m), None, 11, width=48, height=32,
                       fg_color=CARD_ROW, text_color=TEXT_SECONDARY,
                       font=theme.font_body(12, bold=True), hover_color=SURFACE_4,
                       command=lambda mm=m: self._set("timer_default_minutes", mm)
                       ).pack(side="left", padx=(0, 6))

            hdr("Aspetto e avviso timer")
            ctk.CTkLabel(body, text="Testo sopra il conto alla rovescia:", anchor="w",
                         font=theme.font_body(12), text_color=TEXT_SECONDARY).pack(fill="x")
            tv = tk.StringVar(value=self._settings.get("timer_text", ""))
            e = ctk.CTkEntry(body, textvariable=tv, height=34, corner_radius=11,
                             fg_color=CARD_ROW, border_color=BORDER, border_width=1,
                             text_color=TEXT_PRIMARY)
            e.pack(fill="x", pady=(4, 10))
            e.bind("<FocusOut>", lambda ev: self._set("timer_text", tv.get()))

            cr = ctk.CTkFrame(body, fg_color="transparent")
            cr.pack(fill="x", pady=4)
            bgsw = ctk.CTkButton(cr, text="Colore sfondo", width=130, height=32, corner_radius=11,
                                 font=theme.font_body(12, bold=True),
                                 fg_color=self._settings.get("timer_bg_color", "#0b132b"))
            bgsw.configure(command=lambda: self._pick_color("timer_bg_color", bgsw))
            bgsw.pack(side="left", padx=2)
            fgsw = ctk.CTkButton(cr, text="Colore testo", width=130, height=32, corner_radius=11,
                                 text_color="black", font=theme.font_body(12, bold=True),
                                 fg_color=self._settings.get("timer_text_color", "#ffffff"))
            fgsw.configure(command=lambda: self._pick_color("timer_text_color", fgsw))
            fgsw.pack(side="left", padx=2)

            ir = ctk.CTkFrame(body, fg_color="transparent")
            ir.pack(fill="x", pady=4)
            img = self._settings.get("timer_bg_image", "")
            il = ctk.CTkLabel(ir, text=os.path.basename(img) if img else "Nessuna immagine",
                              text_color=TEXT_TERTIARY, font=theme.font_body(12))
            il.pack(side="left")
            ctk.CTkButton(ir, text="Immagine sfondo", width=140, height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: self._pick_timer_bg_image_lbl(il)).pack(side="left", padx=6)
            ctk.CTkButton(ir, text="Rimuovi", width=70, height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=lambda: (self._set("timer_bg_image", ""),
                                           il.configure(text="Nessuna immagine"))).pack(side="left")

            hdr("Comportamento a fine timer")
            ab = tk.BooleanVar(value=self._settings.get("timer_auto_bell", False))
            ctk.CTkSwitch(body, text="Suona campanello automaticamente", variable=ab,
                         progress_color=ACCENT, font=theme.font_body(13), text_color=TEXT_SECONDARY,
                         command=lambda: self._set("timer_auto_bell", ab.get())).pack(anchor="w", pady=2)

            ctk.CTkLabel(body, text="Avviso sonoro prima della fine:", anchor="w",
                         font=theme.font_body(12), text_color=TEXT_SECONDARY
                         ).pack(fill="x", pady=(10, 0))
            wen = tk.BooleanVar(value=self._settings.get("timer_warning_enabled", True))
            ctk.CTkSwitch(body, text="Abilita avviso", variable=wen, progress_color=ACCENT,
                         font=theme.font_body(13), text_color=TEXT_SECONDARY,
                         command=lambda: self._set("timer_warning_enabled", wen.get())
                         ).pack(anchor="w", pady=2)
            wr = ctk.CTkFrame(body, fg_color="transparent")
            wr.pack(fill="x")
            ctk.CTkLabel(wr, text="Secondi prima:", font=theme.font_body(12),
                         text_color=TEXT_SECONDARY).pack(side="left")
            ws = tk.StringVar(value=str(self._settings.get("timer_warning_seconds", 60)))
            we = ctk.CTkEntry(wr, textvariable=ws, width=70, height=32, corner_radius=10,
                              fg_color=CARD_ROW, border_color=BORDER, border_width=1)
            we.pack(side="left", padx=6)
            we.bind("<FocusOut>", lambda ev: self._save_warn_sec_val(ws))
            sr = ctk.CTkFrame(body, fg_color="transparent")
            sr.pack(fill="x", pady=4)
            snd = self._settings.get("timer_warning_sound", "")
            sl = ctk.CTkLabel(sr, text=os.path.basename(snd) if snd else "Nessun file",
                              text_color=TEXT_TERTIARY, font=theme.font_body(12))
            sl.pack(side="left")
            ctk.CTkButton(sr, text="Scegli audio avviso", width=150, height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=lambda: self._pick_warning_sound_lbl(sl)).pack(side="left", padx=6)

            vr = ctk.CTkFrame(body, fg_color="transparent")
            vr.pack(fill="x", pady=(10, 2))
            ctk.CTkLabel(vr, text="Volume avviso:", font=theme.font_body(12),
                         text_color=TEXT_SECONDARY).pack(side="left")
            wv_lbl = ctk.CTkLabel(vr, text=f"{self._settings.get('timer_warning_volume', 100)}%",
                                  font=theme.font_body(12, bold=True), text_color=TEXT_PRIMARY, width=42)
            wv_lbl.pack(side="right")
            wv_slider = ctk.CTkSlider(body, from_=0, to=100,
                                      progress_color=ACCENT, button_color=ACCENT,
                                      button_hover_color=ACCENT_HOVER, fg_color=SURFACE_3,
                                      command=lambda v, lb=wv_lbl: (
                                          lb.configure(text=f"{int(v)}%"),
                                          self._set("timer_warning_volume", int(v))))
            wv_slider.set(self._settings.get("timer_warning_volume", 100))
            wv_slider.pack(fill="x", pady=(0, 6))

        elif cat == "offerta":
            hdr("Immagine offerta (QR)")
            oimg = self._settings.get("offering_image", "")
            self._offer_lbl = ctk.CTkLabel(body, text=os.path.basename(oimg) if oimg else "Nessuna immagine",
                                           text_color=TEXT_TERTIARY, font=theme.font_body(12))
            self._offer_lbl.pack(anchor="w")
            self._offer_thumb_holder = ctk.CTkFrame(body, fg_color="transparent")
            self._offer_thumb_holder.pack(anchor="w")
            if oimg and os.path.isfile(oimg):
                self._show_image_thumb(self._offer_thumb_holder, oimg, max_w=320)
            orow = ctk.CTkFrame(body, fg_color="transparent")
            orow.pack(fill="x", pady=4)
            ctk.CTkButton(orow, text="Carica immagine…", width=190, height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=self._pick_offering_image).pack(side="left", padx=2)
            ctk.CTkButton(orow, text="Rimuovi", width=90, height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._clear_offering_image).pack(side="left", padx=2)
            hdr("Testo di accompagnamento")
            ot = tk.StringVar(value=self._settings.get("offering_text", "Inquadra per l'offerta"))
            oe = ctk.CTkEntry(body, textvariable=ot, height=34, corner_radius=11,
                              fg_color=CARD_ROW, border_color=BORDER, border_width=1,
                              text_color=TEXT_PRIMARY)
            oe.pack(fill="x", pady=(0, 4))
            oe.bind("<FocusOut>", lambda ev: self._set("offering_text", ot.get()))

        elif cat == "sfondo":
            hdr("Sfondo di proiezione predefinito")
            bimg = self._settings.get("background_image", "")
            self._bg_img_lbl = ctk.CTkLabel(
                body, text=os.path.basename(bimg) if bimg else "Nessuno sfondo impostato",
                text_color=TEXT_TERTIARY, font=theme.font_body(12))
            self._bg_img_lbl.pack(anchor="w")
            self._bg_img_thumb_holder = ctk.CTkFrame(body, fg_color="transparent")
            self._bg_img_thumb_holder.pack(anchor="w")
            if bimg and os.path.isfile(bimg):
                self._show_image_thumb(self._bg_img_thumb_holder, bimg, max_w=320)
            brow = ctk.CTkFrame(body, fg_color="transparent")
            brow.pack(fill="x", pady=4)
            ctk.CTkButton(brow, text="Immagine", width=190, height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=self._pick_background_image).pack(side="left", padx=2)
            ctk.CTkButton(brow, text="Rimuovi", width=90, height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._clear_background_image).pack(side="left", padx=2)
            ctk.CTkLabel(body, text="Lo sfondo viene mostrato a schermo intero (su nero) "
                         "premendo «Sfondo» nel pannello destro o Ctrl+2.",
                         text_color=TEXT_FAINT, font=theme.font_body(11), wraplength=420,
                         justify="left").pack(anchor="w", pady=(8, 0))

        elif cat == "lezione":
            hdr("Lezione (Scuola del Sabato)")
            lf = self._settings.get("lesson_file", "")
            self._lesson_lbl = ctk.CTkLabel(body, text=os.path.basename(lf) if lf else "Nessun file lezioni",
                                            text_color=TEXT_TERTIARY, font=theme.font_body(12))
            self._lesson_lbl.pack(anchor="w")
            ctk.CTkButton(body, text="Carica file lezioni (JSON)", width=200, height=32,
                          corner_radius=11, font=theme.font_body(12, bold=True),
                          command=self._pick_lesson_file).pack(anchor="w", pady=4)
            ls = self._load_lesson_set()
            if ls:
                self._lesson_picker_widget(body, ls, after=lambda: self._nav("impostazioni"))
                _s, today = self._current_lesson()
                ctk.CTkLabel(body, text="Lezione attiva: " +
                             (today.get("title", "—") if today else "nessuna per oggi"),
                             text_color=TEXT_TERTIARY, font=theme.font_body(11)).pack(anchor="w")

            hdr("Grafica lezione")
            ctk.CTkLabel(body, text="Un template dedicato per contesto — domanda, nota e versetto "
                                    "citato dentro una domanda hanno ciascuno il proprio template, "
                                    "riquadri, colori e dimensioni, indipendenti tra loro.",
                         text_color=TEXT_TERTIARY, wraplength=520, justify="left"
                         ).pack(anchor="w", pady=(0, 8))
            lez_tabs = [("domanda", "Domanda", self._LESSON_BOX_DEFS),
                       ("nota", "Nota", self._NOTA_BOX_DEFS),
                       ("versetto_lezione", "Versetto citato", self._VERSETTO_LEZIONE_BOX_DEFS)]
            cur_tab = getattr(self, "_lezione_graphic_tab", "domanda")
            tab_var = tk.StringVar(value=next(lbl for key, lbl, _ in lez_tabs if key == cur_tab))

            def _on_lez_tab(v):
                self._lezione_graphic_tab = next(key for key, lbl, _ in lez_tabs if lbl == v)
                self._select_settings_cat("lezione")
            ctk.CTkSegmentedButton(body, values=[lbl for _k, lbl, _b in lez_tabs], variable=tab_var,
                                   height=32, fg_color=CARD_ROW, selected_color=ACCENT,
                                   selected_hover_color=ACCENT_HOVER, unselected_color=CARD_ROW,
                                   unselected_hover_color=SURFACE_3, text_color=TEXT_TERTIARY,
                                   font=theme.font_body(12, bold=True),
                                   command=_on_lez_tab).pack(anchor="w", pady=(0, 10))
            box_defs = next(b for k, _l, b in lez_tabs if k == cur_tab)

            if cur_tab == "domanda":
                # Existing flat-key mechanism, unchanged — "domanda" already
                # had full color/size control before this feature grew to
                # cover nota/versetto_lezione too.
                hdr("Colori testo")
                lcr = ctk.CTkFrame(body, fg_color="transparent")
                lcr.pack(fill="x", pady=4)
                hcol = self._settings.get("lesson_header_color", SLOT_COLORS["lezione"])
                hsw = ctk.CTkButton(lcr, text="Colore intestazione", width=160, height=32,
                                    corner_radius=11, text_color="black",
                                    font=theme.font_body(12, bold=True), fg_color=hcol)
                hsw.configure(command=lambda: self._pick_color("lesson_header_color", hsw))
                hsw.pack(side="left", padx=2)
                qcol = self._settings.get("lesson_question_color", TEXT_PRIMARY)
                qsw = ctk.CTkButton(lcr, text="Colore domanda", width=160, height=32,
                                    corner_radius=11, text_color="black",
                                    font=theme.font_body(12, bold=True), fg_color=qcol)
                qsw.configure(command=lambda: self._pick_color("lesson_question_color", qsw))
                qsw.pack(side="left", padx=2)

                lcr2 = ctk.CTkFrame(body, fg_color="transparent")
                lcr2.pack(fill="x", pady=4)
                for key, label in (("lesson_letter_color", "Colore lettera/numero"),
                                   ("lesson_date_color", "Colore data"),
                                   ("lesson_verse_color", "Colore versetto")):
                    col = self._settings.get(key, "") or hcol
                    sw = ctk.CTkButton(lcr2, text=label, width=160, height=32,
                                       corner_radius=11, text_color="black",
                                       font=theme.font_body(12, bold=True), fg_color=col)
                    sw.configure(command=lambda k=key, s=sw: self._pick_color(k, s))
                    sw.pack(side="left", padx=2)

                hdr("Carattere")
                self._font_family_picker(
                    body, "Font",
                    get_value=lambda: self._settings.get("lesson_font_family")
                                     or self._settings.get("verse_font_family", "Helvetica"),
                    set_value=lambda v: self._set("lesson_font_family", v))

                hdr("Numerazione domande")
                ctk.CTkLabel(body, text="Il marcatore prima di ogni domanda (dipende dal "
                                        "trimestrale in uso — alcuni usano lettere, altri numeri).",
                             text_color=TEXT_FAINT, font=theme.font_body(11), wraplength=520,
                             justify="left").pack(anchor="w", pady=(0, 4))
                numbering_var = tk.StringVar(
                    value="Numeri (1, 2, 3)"
                    if self._settings.get("lesson_question_numbering", "letters") == "numbers"
                    else "Lettere (a, b, c)")
                ctk.CTkSegmentedButton(
                    body, values=["Lettere (a, b, c)", "Numeri (1, 2, 3)"], variable=numbering_var,
                    height=32, fg_color=CARD_ROW, selected_color=ACCENT,
                    selected_hover_color=ACCENT_HOVER, unselected_color=CARD_ROW,
                    unselected_hover_color=SURFACE_3, text_color=TEXT_TERTIARY,
                    font=theme.font_body(12, bold=True),
                    command=lambda v: self._set("lesson_question_numbering",
                                                "numbers" if v.startswith("Numeri") else "letters")
                    ).pack(anchor="w", pady=(0, 8))

                hdr("Dimensione massima testo")
                for key, label in (("lesson_header_max_size", "Intestazione"),
                                   ("lesson_date_max_size", "Data"),
                                   ("lesson_question_max_size", "Domanda"),
                                   ("lesson_verse_max_size", "Versetto")):
                    ctk.CTkLabel(body, text=label, anchor="w", font=theme.font_body(11, bold=True),
                                 text_color=TEXT_SECONDARY).pack(anchor="w", pady=(2, 0))
                    self._max_size_slider(body, key, max_val=200)
            else:
                # nota / versetto_lezione — independent colors/sizes per box,
                # nested in this profile's own settings (see _profile_color/
                # _profile_max_size), not shared with any other profile.
                hdr("Colori testo")
                default_by_key = {"header": SLOT_COLORS["lezione"], "date": SLOT_COLORS["lezione"],
                                  "testo": "#ffffff", "riferimento": SLOT_COLORS["lezione"]}
                label_by_key = {"header": "Colore titolo", "date": "Colore data",
                               "testo": "Colore testo", "riferimento": "Colore riferimento"}
                crow = ctk.CTkFrame(body, fg_color="transparent")
                crow.pack(fill="x", pady=4)
                for key, _label, _color, _default_box in box_defs:
                    self._profile_color_swatch(crow, cur_tab, key, label_by_key[key],
                                               default_by_key[key])

                hdr("Carattere")
                self._font_family_picker(
                    body, "Font",
                    get_value=lambda: self._profile_font_family(cur_tab)
                                     or self._settings.get("verse_font_family", "Helvetica"),
                    set_value=lambda v: self._set_profile_font_family(cur_tab, v))

                hdr("Dimensione massima testo")
                size_label_by_key = {"header": "Titolo", "date": "Data", "testo": "Testo",
                                     "riferimento": "Riferimento"}
                for key, _label, _color, _default_box in box_defs:
                    ctk.CTkLabel(body, text=size_label_by_key[key], anchor="w",
                                 font=theme.font_body(11, bold=True),
                                 text_color=TEXT_SECONDARY).pack(anchor="w", pady=(2, 0))
                    self._max_size_slider(
                        body, max_val=200,
                        get_value=lambda k=key: self._profile_max_size(cur_tab, k),
                        set_value=lambda v, k=key: self._set_profile_max_size(cur_tab, k, v))

            hdr("Template e riquadri")
            self._graphic_profile_editor(body, cur_tab, box_defs, "lezione")

        elif cat == "campanello":
            hdr("Suono")
            r = ctk.CTkFrame(body, fg_color="transparent")
            r.pack(fill="x", pady=2)
            bs = self._settings.get("bell_sound", "")
            self._bell_lbl = ctk.CTkLabel(r, text=os.path.basename(bs) if bs else "Nessun file",
                                          text_color=TEXT_TERTIARY, font=theme.font_body(12))
            self._bell_lbl.pack(side="left")
            ctk.CTkButton(r, text="Scegli audio", width=140, height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=self._pick_bell_sound).pack(side="left", padx=8)
            ctk.CTkButton(body, text="Prova", width=100, height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=self._ring_bell).pack(anchor="w", pady=6)

        elif cat == "youtube":
            hdr("Cartella download video")
            yf = self._settings.get("youtube_folder", "")
            self._yt_folder_lbl = ctk.CTkLabel(body, text=yf or "(cartella musica o Download)",
                                               text_color=TEXT_TERTIARY, font=theme.font_body(12))
            self._yt_folder_lbl.pack(anchor="w")
            ctk.CTkButton(body, text="Sfoglia…", width=190, height=32, corner_radius=11,
                          font=theme.font_body(12, bold=True),
                          command=self._pick_youtube_folder).pack(anchor="w", pady=4)
            hdr("Qualità predefinita")
            q = tk.StringVar(value=self._settings.get("youtube_quality", "Migliore disponibile"))
            ctk.CTkSegmentedButton(body, values=["720p", "1080p", "Migliore disponibile"],
                                   variable=q, height=32, fg_color=CARD_ROW, selected_color=ACCENT,
                                   selected_hover_color=ACCENT_HOVER, unselected_color=CARD_ROW,
                                   unselected_hover_color=SURFACE_3, text_color=TEXT_TERTIARY,
                                   font=theme.font_body(12, bold=True),
                                   command=lambda v: self._set("youtube_quality", v)
                                   ).pack(anchor="w", pady=2)

        elif cat == "cronologia":
            hdr("Cronologia")
            for label, count, clear in (
                ("Inni usati", len(self._history.hymns), lambda: (
                    self._history.clear_hymns(), self._save_history())),
                ("Versetti usati", len(self._history.verses), lambda: (
                    self._history.clear_verses(), self._save_history())),
                ("Richieste di preghiera", len(self._prayers), lambda: (
                    self._prayers.clear(), prayers_store.save(self._prayers))),
            ):
                row = ctk.CTkFrame(body, fg_color=CARD_ROW, corner_radius=12)
                row.pack(fill="x", pady=3)
                col = ctk.CTkFrame(row, fg_color="transparent")
                col.pack(side="left", fill="x", expand=True, padx=12, pady=8)
                ctk.CTkLabel(col, text=label, anchor="w", font=theme.font_body(13, bold=True),
                             text_color=TEXT_PRIMARY).pack(anchor="w")
                ctk.CTkLabel(col, text=f"{count} vo{'ce' if count == 1 else 'ci'}", anchor="w",
                             font=theme.font_body(11), text_color=TEXT_TERTIARY).pack(anchor="w")
                ctk.CTkButton(row, text="Pulisci", width=90, height=30, corner_radius=11,
                              fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                              text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                              command=lambda c=clear: (c(), self._select_settings_cat("cronologia"))
                              ).pack(side="right", padx=10)
            hdr("Azione irreversibile")
            zrow = ctk.CTkFrame(body, fg_color=CARD_ROW, corner_radius=12)
            zrow.pack(fill="x", pady=3)
            ctk.CTkLabel(zrow, text="Azzera tutta la cronologia", anchor="w",
                         font=theme.font_body(13, bold=True), text_color=TEXT_PRIMARY
                         ).pack(side="left", padx=12, pady=10)

            def _clear_all_history():
                self._history.clear_hymns()
                self._history.clear_verses()
                self._prayers.clear()
                prayers_store.save(self._prayers)
                self._save_history()
                self._select_settings_cat("cronologia")
            ctk.CTkButton(zrow, text="Azzera tutto", width=110, height=30, corner_radius=11,
                          fg_color=DANGER_FILL, hover_color=DANGER_FILL_HOVER,
                          text_color=DANGER_FILL_TEXT, font=theme.font_body(12, bold=True),
                          command=lambda: self._ask_confirm(
                              "Azzera tutta la cronologia",
                              "Cancellare cronologia inni, versetti e richieste di preghiera? "
                              "Azione irreversibile.", _clear_all_history)
                          ).pack(side="right", padx=10)

    def _available_fonts(self):
        """System font families, cached — same list is queried repeatedly every
        time the user revisits a font-picker settings tab."""
        if not hasattr(self, "_font_families_cache"):
            try:
                import tkinter.font as tkfont
                fams = sorted({f for f in tkfont.families() if f and not f.startswith("@")},
                              key=str.lower)
            except Exception:
                fams = []
            self._font_families_cache = fams or ["Helvetica", "Arial", "Times New Roman", "Courier New"]
        return list(self._font_families_cache)

    def _style_font_dropdown(self, option_menu, font_names, size=13):
        """Best-effort: render each entry in a font-family CTkOptionMenu's
        dropdown list using that font itself, so the name previews its own
        style — like a font picker in Word/Google Docs. Reaches into
        CTkOptionMenu's internal `_dropdown_menu` (a real tkinter.Menu,
        which natively supports a per-entry `font`, unlike CTkOptionMenu's
        own single dropdown-wide `font` option) — a private attribute, so
        this is wrapped defensively in case a future customtkinter version
        restructures it; worst case, the dropdown just keeps the uniform
        font it already had."""
        try:
            menu = option_menu._dropdown_menu
            for i, name in enumerate(font_names):
                menu.entryconfigure(i, font=(name, size))
        except Exception:
            pass

    def _font_family_picker(self, parent, label, get_value, set_value):
        """Labeled font-family dropdown, live-styled per entry (see
        _style_font_dropdown) — `get_value`/`set_value` decouple this from
        any one settings shape, so it works for a flat key (Bibbia, domanda)
        or a nested per-profile one (nota/versetto_lezione, via
        _profile_font_family/_set_profile_font_family)."""
        frow = ctk.CTkFrame(parent, fg_color="transparent")
        frow.pack(fill="x", pady=2)
        ctk.CTkLabel(frow, text=f"{label}:", width=110, anchor="w",
                     font=theme.font_body(12), text_color=TEXT_SECONDARY).pack(side="left")
        fams = self._available_fonts()
        cur_fam = get_value() or "Helvetica"
        if cur_fam not in fams:
            fams = [cur_fam] + fams
        fam_menu = ctk.CTkOptionMenu(frow, values=fams, width=220, height=32, corner_radius=11,
                                     fg_color=SURFACE_3, button_color=SURFACE_4,
                                     button_hover_color=BORDER, text_color=TEXT_PRIMARY,
                                     font=theme.font_body(12),
                                     variable=tk.StringVar(value=cur_fam),
                                     command=lambda v: set_value(v))
        fam_menu.pack(side="left", padx=8)
        self._style_font_dropdown(fam_menu, fams)

    def _max_size_slider(self, body, key=None, refresh=None, max_val=200,
                        get_value=None, set_value=None):
        """Labeled slider for a max-size setting (px, 0 = 'Automatica' = no
        cap, the historical behavior) — used for every projected text element
        that supports the manual max-size clamp on top of its box-based
        autofit. By default reads/writes the flat setting named `key`; pass
        `get_value`/`set_value` instead for settings nested somewhere other
        than a top-level flat key (e.g. a graphic profile's own max_sizes
        dict — see `_profile_max_size`/`_set_profile_max_size`). `refresh`,
        if given, is called after every change so a live preview (e.g. the
        Bibbia box preview) stays in sync."""
        get_value = get_value or (lambda: int(self._settings.get(key, 0) or 0))
        set_value = set_value or (lambda v: self._set(key, v))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(row, text="Dimensione massima:", width=140, anchor="w",
                     font=theme.font_body(12), text_color=TEXT_SECONDARY).pack(side="left")
        cur = get_value()
        val_lbl = ctk.CTkLabel(row, text=(f"{cur}px" if cur else "Automatica"),
                               font=theme.font_body(12, bold=True), text_color=TEXT_PRIMARY, width=80)
        val_lbl.pack(side="right")

        def _on_change(v, lb=val_lbl):
            iv = int(v)
            lb.configure(text=(f"{iv}px" if iv else "Automatica"))
            set_value(iv)
            if refresh:
                refresh()
        slider = ctk.CTkSlider(body, from_=0, to=max_val, progress_color=ACCENT,
                               button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                               fg_color=SURFACE_3, command=_on_change)
        slider.set(cur)
        slider.pack(fill="x", pady=(0, 6))

    # settings actions
    def _set(self, key, value):
        self._settings[key] = value
        cfg.save(self._settings)

    def _add_db_folder(self):
        folder = filedialog.askdirectory(title="Cartella database inni")
        if not folder:
            return
        dbs = self._settings.get("databases", [])
        if folder not in dbs:
            dbs.append(folder)
        self._settings["databases"] = dbs
        self._settings["last_database"] = folder
        cfg.save(self._settings)
        self._nav("impostazioni")
        self._load_db_async()

    def _remove_db(self, folder):
        dbs = [d for d in self._settings.get("databases", []) if d != folder]
        self._settings["databases"] = dbs
        if self._settings.get("last_database") == folder:
            self._settings["last_database"] = dbs[0] if dbs else ""
        cfg.save(self._settings)
        self._nav("impostazioni")
        self._load_db_async()

    def _set_bible_version(self, code, short):
        self._bible.set_active_version(code, short)
        self._settings["bible_versions"] = self._bible.active_mapping()
        cfg.save(self._settings)

    def _add_bible_version_for(self, lang_code: str):
        """Add another .bib version for a language that's already installed
        (e.g. a second Italian translation alongside LND) — the code is
        fixed to lang_code, no confirmation step needed since it's not
        ambiguous like a brand-new language would be."""
        p = filedialog.askopenfilename(title=f"Scegli file .bib per "
                                             f"{self._bible.language_label(lang_code)}",
                                       filetypes=[("BibleShow", "*.bib"), ("Tutti", "*.*")])
        if not p:
            return
        self._run_bible_import(p, lang_code)

    def _add_bible_language(self):
        """Add a brand-new language from a .bib file — the language code is
        auto-detected but shown for confirmation/correction first, since
        getting it wrong here (unlike _add_bible_version_for) would create a
        stray extra language instead of just failing obviously."""
        p = filedialog.askopenfilename(title="Scegli file Bibbia (.bib)",
                                       filetypes=[("BibleShow", "*.bib"), ("Tutti", "*.*")])
        if not p:
            return
        try:
            from tools.convert_bib import detect_info
            info = detect_info(p)
        except ImportError:
            self._info("Serve un pacchetto in più",
                      "Per importare Bibbie da file .bib serve il pacchetto Python "
                      "\"access-parser\". Apri il Terminale ed esegui:\n\n"
                      "pip install access-parser\n\ne poi riprova.")
            return
        except Exception as ex:
            self._info("File non valido", f"Non riesco a leggere questo file .bib:\n{ex}")
            return
        self._confirm_bible_language(p, info)

    def _confirm_bible_language(self, bib_path: str, info: dict):
        code_var = tk.StringVar(value=info["code"])

        def build(body):
            ctk.CTkLabel(body, text=f"Lingua rilevata: {info['language'] or '(sconosciuta)'}",
                         anchor="w", font=theme.font_body(13, bold=True)
                         ).pack(fill="x", pady=(0, 2))
            ctk.CTkLabel(body, text=f"Versione: {info['full']}", anchor="w",
                         text_color=TEXT_TERTIARY, font=theme.font_body(12)
                         ).pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(body, text="Codice lingua (2 lettere — correggi se necessario):",
                         anchor="w", font=theme.font_body(12)).pack(fill="x")
            e = ctk.CTkEntry(body, textvariable=code_var, width=80)
            e.pack(anchor="w", pady=(4, 10))
            note = ctk.CTkLabel(body, text="", anchor="w", text_color=TEXT_TERTIARY,
                                font=theme.font_body(11), wraplength=440, justify="left")
            note.pack(fill="x", pady=(0, 14))

            def _upd_note(*_a):
                c = code_var.get().strip().lower()
                existing = self._bible.languages() if self._bible else []
                if c in existing:
                    note.configure(text=f"Questo codice è già usato da "
                                        f"\"{self._bible.language_label(c)}\" — verrà aggiunta "
                                        f"come nuova versione di quella lingua, non come lingua nuova.")
                else:
                    note.configure(text="Verrà aggiunta come nuova lingua.")
            code_var.trace_add("write", _upd_note)
            _upd_note()
            btns = ctk.CTkFrame(body, fg_color="transparent")
            btns.pack(fill="x")
            ctk.CTkButton(btns, text="Annulla", width=100, fg_color=BTN_SECONDARY,
                          text_color=TEXT_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          command=self._close_modal).pack(side="right", padx=4)
            ctk.CTkButton(btns, text="Importa", width=100,
                          command=lambda: self._run_bible_import(
                              bib_path, code_var.get().strip().lower())).pack(side="right", padx=4)
        self._open_modal("Importa Bibbia", build, width=480, height=320)

    def _run_bible_import(self, bib_path: str, code: str):
        self._close_modal()
        self._info("Importazione in corso",
                  "Sto convertendo il file — può richiedere qualche secondo, "
                  "specialmente per Bibbie intere. Questa finestra si chiuderà da sola.")

        def run():
            try:
                from tools.convert_bib import convert
                result = convert(bib_path, self._bible.dir, code)
                err = None
            except Exception as ex:
                result, err = None, str(ex)
            self._safe_after(lambda: self._on_bible_import_done(result, err))
        threading.Thread(target=run, daemon=True).start()

    def _on_bible_import_done(self, result, err):
        if err:
            self._info("Importazione fallita", f"Errore durante la conversione:\n{err}")
            return
        self._bible.reload()
        self._info("Bibbia importata",
                  f"{result['language']} — {result['full']}\n"
                  f"{result['books']} libri, {result['verses']} versetti.")
        self._goto_settings("bibbia")

    def _save_warn_sec(self):
        try:
            self._set("timer_warning_seconds", int(self._warn_sec.get()))
        except (ValueError, AttributeError):
            pass

    def _pick_warning_sound(self):
        p = filedialog.askopenfilename(title="Audio avviso",
                                       filetypes=[("Audio", "*.mp3 *.wav *.ogg *.m4a"), ("Tutti", "*.*")])
        if p:
            self._set("timer_warning_sound", p)
            self._warn_snd_lbl.configure(text=os.path.basename(p))

    def _pick_bell_sound(self):
        p = filedialog.askopenfilename(title="Audio campana",
                                       filetypes=[("Audio", "*.mp3 *.wav *.ogg *.m4a"), ("Tutti", "*.*")])
        if p:
            self._set("bell_sound", p)
            self._bell_lbl.configure(text=os.path.basename(p))

    def _pick_timer_bg_color(self):
        c = colorchooser.askcolor(title="Colore sfondo timer",
                                  initialcolor=self._settings.get("timer_bg_color", "#0b132b"))
        if c and c[1]:
            self._set("timer_bg_color", c[1])
            self._bg_swatch.configure(fg_color=c[1])

    def _pick_timer_text_color(self):
        c = colorchooser.askcolor(title="Colore testo timer",
                                  initialcolor=self._settings.get("timer_text_color", "#ffffff"))
        if c and c[1]:
            self._set("timer_text_color", c[1])
            self._fg_swatch.configure(fg_color=c[1])

    def _pick_timer_bg_image(self):
        p = filedialog.askopenfilename(title="Immagine sfondo timer",
                                       filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Tutti", "*.*")])
        if p:
            self._set("timer_bg_image", p)
            self._timer_img_lbl.configure(text=os.path.basename(p))

    def _change_appearance(self, mode):
        ctk.set_appearance_mode(mode)
        self._set("appearance_mode", mode)

    def _pick_offering_image(self):
        p = filedialog.askopenfilename(title="Immagine offerta (slide/QR)",
                                       filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Tutti", "*.*")])
        if p:
            self._set("offering_image", p)
            self._offer_lbl.configure(text=os.path.basename(p))
            for w in self._offer_thumb_holder.winfo_children():
                w.destroy()
            self._show_image_thumb(self._offer_thumb_holder, p, max_w=320)

    def _clear_offering_image(self):
        self._set("offering_image", "")
        self._offer_lbl.configure(text="Nessuna immagine")
        for w in self._offer_thumb_holder.winfo_children():
            w.destroy()

    def _pick_background_image(self):
        p = filedialog.askopenfilename(title="Sfondo (comando rapido)",
                                       filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp *.gif"), ("Tutti", "*.*")])
        if p:
            self._set("background_image", p)
            self._bg_img_lbl.configure(text=os.path.basename(p))
            for w in self._bg_img_thumb_holder.winfo_children():
                w.destroy()
            self._show_image_thumb(self._bg_img_thumb_holder, p, max_w=320)

    def _clear_background_image(self):
        self._set("background_image", "")
        self._bg_img_lbl.configure(text="Nessuno sfondo impostato")
        for w in self._bg_img_thumb_holder.winfo_children():
            w.destroy()

    def _pick_lesson_file(self):
        p = filedialog.askopenfilename(title="File lezioni",
                                       filetypes=[("JSON", "*.json"), ("Tutti", "*.*")])
        if p:
            self._set("lesson_file", p)
            self._set("lesson_override_index", -1)
            self._proj_lesson_idx = 0
            self._nav("impostazioni")

    # Box shapes shared by every graphic profile — (key, label, outline color,
    # default box [x,y,w,h] as fractions of the template's own pixel size).
    _LESSON_BOX_DEFS = [
        ("header", "Titolo", "#4ade80", [0.03, 0.02, 0.55, 0.10]),
        ("date", "Data", "#fb923c", [0.75, 0.02, 0.22, 0.10]),
        ("photo", "Foto", "#60a5fa", [0.0, 0.16, 1.0, 0.35]),
        ("question", "Testo domanda", "#c084fc", [0.05, 0.55, 0.9, 0.4]),
    ]
    _VERSE_GRAPHIC_BOX_DEFS = [
        ("testo", "Testo", "#3b82f6", list(_VERSE_TEXT_BOX_DEFAULT)),
        ("riferimento", "Riferimento", "#ec4899", list(_VERSE_REF_BOX_DEFAULT)),
    ]
    # Nota/versetto-citato-in-lezione shapes: unlike versetto_bibbia (no
    # lezione day context at all), these two also carry a header/date so the
    # day being browsed stays visible whichever lezione element is on screen.
    _NOTA_BOX_DEFS = [
        ("header", "Titolo", "#4ade80", [0.03, 0.02, 0.55, 0.10]),
        ("date", "Data", "#fb923c", [0.75, 0.02, 0.22, 0.10]),
        ("testo", "Testo", "#3b82f6", list(_VERSE_TEXT_BOX_DEFAULT)),
    ]
    _VERSETTO_LEZIONE_BOX_DEFS = [
        ("header", "Titolo", "#4ade80", [0.03, 0.02, 0.55, 0.10]),
        ("date", "Data", "#fb923c", [0.75, 0.02, 0.22, 0.10]),
        ("testo", "Testo", "#3b82f6", list(_VERSE_TEXT_BOX_DEFAULT)),
        ("riferimento", "Riferimento", "#ec4899", list(_VERSE_REF_BOX_DEFAULT)),
    ]

    def _graphic_profile(self, name):
        """Read-only view of one named graphic profile — {} (no template
        configured) means: fall back to the plain-background rendering for
        that context, exactly as before graphic profiles existed."""
        return self._settings.get("lesson_graphic_profiles", {}).get(name, {})

    def _set_graphic_profile_template(self, name, path):
        profiles = dict(self._settings.get("lesson_graphic_profiles", {}))
        prof = dict(profiles.get(name, {}))
        prof["template"] = path
        profiles[name] = prof
        self._settings["lesson_graphic_profiles"] = profiles
        cfg.save(self._settings)

    def _profile_color(self, profile_name, box_key):
        """Independent per-profile, per-box color — "" means unset (the
        caller decides the fallback, usually the header color or white)."""
        return self._graphic_profile(profile_name).get("colors", {}).get(box_key, "")

    def _set_profile_color(self, profile_name, box_key, color):
        profiles = dict(self._settings.get("lesson_graphic_profiles", {}))
        prof = dict(profiles.get(profile_name, {}))
        colors = dict(prof.get("colors", {}))
        colors[box_key] = color
        prof["colors"] = colors
        profiles[profile_name] = prof
        self._settings["lesson_graphic_profiles"] = profiles
        cfg.save(self._settings)

    def _profile_max_size(self, profile_name, box_key):
        return self._graphic_profile(profile_name).get("max_sizes", {}).get(box_key, 0)

    def _set_profile_max_size(self, profile_name, box_key, value):
        profiles = dict(self._settings.get("lesson_graphic_profiles", {}))
        prof = dict(profiles.get(profile_name, {}))
        sizes = dict(prof.get("max_sizes", {}))
        sizes[box_key] = value
        prof["max_sizes"] = sizes
        profiles[profile_name] = prof
        self._settings["lesson_graphic_profiles"] = profiles
        cfg.save(self._settings)

    def _profile_font_family(self, profile_name):
        """One font shared by every box in this profile — "" means fall back
        to the shared verse_font_family, same fallback convention as
        _profile_color. Not per-box (unlike colors/max-sizes) — a lezione
        profile's boxes are one cohesive graphic, not independently styled
        typography."""
        return self._graphic_profile(profile_name).get("font_family", "")

    def _set_profile_font_family(self, profile_name, family):
        profiles = dict(self._settings.get("lesson_graphic_profiles", {}))
        prof = dict(profiles.get(profile_name, {}))
        prof["font_family"] = family
        profiles[profile_name] = prof
        self._settings["lesson_graphic_profiles"] = profiles
        cfg.save(self._settings)

    def _profile_color_swatch(self, parent, profile_name, box_key, label, default):
        """Color swatch button for one (profile, box) pair — independent of
        every other profile's colors, unlike the shared verse_*/lesson_*
        color settings `domanda` and `versetto_bibbia` still use."""
        col = self._profile_color(profile_name, box_key) or default
        sw = ctk.CTkButton(parent, text=label, width=160, height=32, corner_radius=11,
                           text_color="black", font=theme.font_body(12, bold=True), fg_color=col)

        def pick():
            c = colorchooser.askcolor(title="Scegli colore", initialcolor=col)
            if c and c[1]:
                self._set_profile_color(profile_name, box_key, c[1])
                sw.configure(fg_color=c[1])
        sw.configure(command=pick)
        sw.pack(side="left", padx=2)

    def _set_graphic_profile_box(self, name, box_key, box):
        profiles = dict(self._settings.get("lesson_graphic_profiles", {}))
        prof = dict(profiles.get(name, {}))
        boxes = dict(prof.get("boxes", {}))
        boxes[box_key] = box
        prof["boxes"] = boxes
        profiles[name] = prof
        self._settings["lesson_graphic_profiles"] = profiles
        cfg.save(self._settings)

    def _graphic_profile_editor(self, body, profile_name, box_defs, settings_cat):
        """Visual editor, reused for every projection context (lezione
        domanda/nota/versetto, Bibbia versetto): once a template is loaded
        for `profile_name`, its boxes (named by `box_defs`) sit as draggable/
        resizable rectangles over a scaled-down preview of it — dragging the
        body moves a box, dragging its bottom-right handle resizes it. Boxes
        save themselves (as 0..1 fractions of the template's own pixel size)
        on mouse release. `settings_cat` is which Impostazioni tab to
        re-render after loading/removing a template (since profiles now live
        in different tabs: lezione or bibbia)."""
        prof = self._graphic_profile(profile_name)
        tmpl_path = prof.get("template", "")

        def pick_template():
            p = filedialog.askopenfilename(title="Scegli template grafica",
                                           filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp"),
                                                      ("Tutti", "*.*")])
            if not p:
                return
            self._set_graphic_profile_template(profile_name, p)
            self._goto_settings(settings_cat)

        def remove_template():
            self._set_graphic_profile_template(profile_name, "")
            self._goto_settings(settings_cat)

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=os.path.basename(tmpl_path) if tmpl_path else "Nessun template",
                    text_color=TEXT_TERTIARY, font=theme.font_body(12)).pack(side="left")
        ctk.CTkButton(row, text="Carica template", width=150, height=32, corner_radius=11,
                      font=theme.font_body(12, bold=True),
                      command=pick_template).pack(side="left", padx=8)
        if tmpl_path:
            ctk.CTkButton(row, text="Rimuovi", width=90, height=32, corner_radius=11,
                          fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
                          text_color=TEXT_SECONDARY, font=theme.font_body(12, bold=True),
                          command=remove_template).pack(side="left", padx=2)

        if not (tmpl_path and os.path.isfile(tmpl_path)):
            ctk.CTkLabel(body, text="Carica un'immagine (PNG/JPG) per posizionare i riquadri di "
                                    "testo su un template, invece dello sfondo semplice.",
                        text_color=TEXT_TERTIARY,
                        wraplength=520, justify="left").pack(anchor="w", pady=(4, 8))
            return

        try:
            from PIL import ImageTk
            img = Image.open(tmpl_path)
            iw, ih = img.size
        except Exception:
            ctk.CTkLabel(body, text="Non riesco ad aprire questo file come immagine.",
                        text_color=TEXT_TERTIARY).pack(anchor="w", pady=(4, 8))
            return

        prev_w = 520
        prev_h = max(1, int(prev_w * ih / iw))
        photo = ImageTk.PhotoImage(img.resize((prev_w, prev_h)))

        canvas = tk.Canvas(body, width=prev_w, height=prev_h, highlightthickness=0, bd=0)
        canvas.pack(anchor="w", pady=(6, 2))
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo  # keep a reference alive past this call

        saved_boxes = prof.get("boxes", {})
        boxes = {key: list(saved_boxes.get(key, default_box))
                for key, _label, _color, default_box in box_defs}
        rect_items, handle_items = {}, {}
        HS = 9  # resize-handle square size, in preview pixels

        def redraw(key):
            x, y, w, h = boxes[key]
            px, py, pw, ph = x * prev_w, y * prev_h, w * prev_w, h * prev_h
            canvas.coords(rect_items[key], px, py, px + pw, py + ph)
            canvas.coords(handle_items[key], px + pw - HS, py + ph - HS, px + pw, py + ph)

        for key, label, color, _default_box in box_defs:
            x, y, w, h = boxes[key]
            px, py, pw, ph = x * prev_w, y * prev_h, w * prev_w, h * prev_h
            rect_items[key] = canvas.create_rectangle(px, py, px + pw, py + ph,
                                                       outline=color, width=2)
            canvas.create_text(px + 4, py + 3, text=label, fill=color, anchor="nw",
                               font=("Helvetica", 10, "bold"))
            handle_items[key] = canvas.create_rectangle(px + pw - HS, py + ph - HS, px + pw, py + ph,
                                                         fill=color, outline="")

        drag = {"key": None, "mode": None, "x": 0, "y": 0}

        def on_press(e):
            for key, _l, _c, _d in reversed(box_defs):
                hx0, hy0, hx1, hy1 = canvas.coords(handle_items[key])
                if hx0 - 4 <= e.x <= hx1 + 4 and hy0 - 4 <= e.y <= hy1 + 4:
                    drag.update(key=key, mode="resize", x=e.x, y=e.y)
                    return
            for key, _l, _c, _d in reversed(box_defs):
                rx0, ry0, rx1, ry1 = canvas.coords(rect_items[key])
                if rx0 <= e.x <= rx1 and ry0 <= e.y <= ry1:
                    drag.update(key=key, mode="move", x=e.x, y=e.y)
                    return
            drag.update(key=None, mode=None)

        def on_drag(e):
            key = drag["key"]
            if not key:
                return
            dx, dy = e.x - drag["x"], e.y - drag["y"]
            x, y, w, h = boxes[key]
            if drag["mode"] == "move":
                x = max(0.0, min(1 - w, x + dx / prev_w))
                y = max(0.0, min(1 - h, y + dy / prev_h))
            else:
                w = max(0.03, min(1 - x, w + dx / prev_w))
                h = max(0.03, min(1 - y, h + dy / prev_h))
            boxes[key] = [x, y, w, h]
            drag["x"], drag["y"] = e.x, e.y
            redraw(key)

        def on_release(_e):
            key = drag["key"]
            if key:
                self._set_graphic_profile_box(profile_name, key, boxes[key])
            drag.update(key=None, mode=None)

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

        ctk.CTkLabel(body, text="Trascina i riquadri per spostarli, il quadratino in basso a "
                                "destra per ridimensionarli — si salvano da soli.",
                    text_color=TEXT_FAINT, font=theme.font_body(10)).pack(anchor="w", pady=(2, 8))

    def _set_lesson_choice(self, value: str, titles: list, after=None):
        idx = titles.index(value) - 1  # 0th is "Automatico"
        self._set("lesson_override_index", idx)
        self._proj_lesson_idx = 0
        (after or (lambda: self._nav("impostazioni")))()

    def _lesson_picker_widget(self, parent, ls, after):
        """Dropdown to override which lesson is 'current', shared by the
        Impostazioni tab and the Lezione slot's own detail panel."""
        titles = ["Automatico (per data)"] + ls.titles()
        cur_idx = self._settings.get("lesson_override_index", -1)
        cur = titles[cur_idx + 1] if 0 <= cur_idx < len(ls.titles()) else titles[0]
        var = tk.StringVar(value=cur)
        ctk.CTkOptionMenu(parent, values=titles, variable=var, width=280,
                          command=lambda v: self._set_lesson_choice(v, titles, after)
                          ).pack(anchor="w", pady=2)

    def _pick_youtube_folder(self):
        folder = filedialog.askdirectory(title="Cartella download YouTube")
        if folder:
            self._set("youtube_folder", folder)
            self._yt_folder_lbl.configure(text=folder)

    # ── projection ─────────────────────────────────────────────────────────────
    def _ensure_projection(self, clear_overlay: bool = True) -> ProjectionWindow:
        """clear_overlay=False is used by the quick commands themselves (Nero/
        Sfondo), which set their own overlay right after — clearing it first
        here would just undo the toggle they're about to perform."""
        if self._projection is None or not self._projection.winfo_exists():
            self._projection = ProjectionWindow(
                self,
                self._settings.get("projection_screen", 1),
                on_slide_change=lambda _idx: self._update_slide_label(),
                on_close=self._stop_projection,
                on_nav=lambda d: self._slide_next() if d > 0 else self._slide_prev(),
                on_quick=self._proj_quick_cmd,
            )
        elif clear_overlay:
            self._projection.clear_overlay()
        try:
            self._stop_proj_btn.configure(state="normal")
        except Exception:
            pass
        return self._projection

    def _present_pptx(self, path, title=""):
        """Launch the real PowerPoint slideshow on the secondary screen.

        No Keynote / PNG export: PowerPoint drives the projection, and slide
        advance / ending the show are controlled from the app (PagSù/PagGiù,
        frecce, «Togli proiezione»)."""
        if not os.path.isfile(path):
            self._info("Errore", f"File non trovato:\n{path}")
            return
        name = title or os.path.splitext(os.path.basename(path))[0]
        # Close any in-app projection first — external PowerPoint takes over.
        if self._projection and self._projection.winfo_exists():
            self._projection.close()
            self._projection = None
        if projector.present_powerpoint(path):
            self._proj_mode = "external"
            self._proj_pill.configure(text=f"● {name} (PowerPoint)", text_color="#22c55e")
            try:
                self._stop_proj_btn.configure(state="normal")
            except Exception:
                pass
        else:
            self._info("Proiezione",
                       "Impossibile avviare PowerPoint.\n"
                       "Verifica che Microsoft PowerPoint sia installato.")

    def _project_hymn(self, slides_text, title="", pptx_path=""):
        """Project a hymn. Uses the real PowerPoint file if it exists; else the
        in-app text slides."""
        if pptx_path and os.path.isfile(pptx_path):
            self._present_pptx(pptx_path, title=title or "Inno")
            return
        # Fall back to text slides
        slides = [s for s in (slides_text or []) if s.strip()]
        if not slides:
            self._info("Inno", "Nessun testo da proiettare per questo inno.")
            return
        self._proj_mode = "slides"
        self._proj_pill_prefix = title or 'Inno'
        win = self._ensure_projection()
        win.set_background(self._settings.get("verse_bg_color", "#0b132b"),
                           self._settings.get("verse_bg_image", ""))
        win.set_text_color(self._settings.get("verse_text_color", "#ffffff"))
        win.show_text_slides(slides, start=0)
        self._update_slide_label()

    def _project_verse_data(self, data: dict, profile: str = "bibbia", lesson_ctx=None):
        """`profile` picks which graphic profile's optional template/boxes
        apply — "bibbia" for a verse projected from the Bibbia section
        itself (no lezione day context), "lezione" for one cited from inside
        a lezione question (`lesson_ctx` = (les, dom) for that day's
        header/date). Both profiles have their own independent
        colors/max-sizes (see _show_lesson_profile_text) and both fall back
        to the exact same plain rendering (using the legacy shared verse_*
        settings) when no template is configured. Called directly (not via
        _project_verse) by the "versetto" schedule-slot's own Proietta
        button, so it always clears `_lesson_verse_ctx` for a non-lezione
        profile — otherwise a stale ctx from an earlier lezione citation
        would leak the lezione graphic onto a later, unrelated verse once
        _verse_step runs (see the "wrong graphic when stepping" bug)."""
        if profile != "lezione":
            self._lesson_verse_ctx = None
        self._proj_mode = "verse"
        self._proj_verse_data = data
        win = self._ensure_projection()
        win.set_background(self._settings.get("verse_bg_color", "#0b132b"),
                           self._settings.get("verse_bg_image", ""))
        win.set_text_color(self._settings.get("verse_text_color", "#ffffff"))
        win.set_ref_color(self._settings.get("verse_ref_color", "#ffffff"))
        body = "\n\n".join(t for t in data["texts"].values() if t)

        if profile == "bibbia":
            prof_name, box_defs, les, dom = "versetto_bibbia", self._VERSE_GRAPHIC_BOX_DEFS, None, None
        else:
            prof_name, box_defs = "versetto_lezione", self._VERSETTO_LEZIONE_BOX_DEFS
            les, dom = lesson_ctx or (None, None)
        template = self._graphic_profile(prof_name).get("template", "")
        if template and os.path.isfile(template):
            self._show_lesson_profile_text(win, prof_name, box_defs, les, dom, body, data["ref"])
        else:
            # no template for this profile (or no day context available for
            # the lezione case) — fall back to the plain rendering shared by
            # both profiles, using the legacy flat verse_* settings.
            win.show_text(body, secondary=data["ref"],
                          font_family=self._settings.get("verse_font_family", "Helvetica"),
                          text_box=self._settings.get("verse_text_box", _VERSE_TEXT_BOX_DEFAULT),
                          ref_box=self._settings.get("verse_ref_box", _VERSE_REF_BOX_DEFAULT),
                          ref_font_family=self._settings.get("verse_ref_font_family", "Helvetica"),
                          text_max_size=self._settings.get("verse_text_max_size") or None,
                          ref_max_size=self._settings.get("verse_ref_max_size") or None)
        self._proj_pill.configure(text=f"● {data['ref']}", text_color="#22c55e")
        self._refresh_bib_verse_ui()

    def _refresh_bib_verse_ui(self):
        """Keep the Versetti column's 'In proiezione' row in sync — needed
        both for direct clicks and for arrow-key stepping through verses
        while that screen is already open."""
        self._refresh_bib_col_verses()

    def _verse_step(self, delta: int):
        """Move the currently-projected verse forward/back, crossing into the
        next/previous chapter of the same book once the current one ends —
        UNLESS the verse was opened from a lezione citation (self._lesson_verse_ctx),
        in which case stepping is constrained to that citation's own verse list
        and simply stops at its first/last verse instead of continuing into
        verses that weren't actually cited."""
        d = getattr(self, "_proj_verse_data", None)
        if not d or self._proj_mode != "verse":
            return
        langs = d.get("langs") or self._selected_langs()
        ctx = getattr(self, "_lesson_verse_ctx", None)
        # Same condition drives both "how do we step" AND "which graphic
        # profile applies" below — a stale ctx (left over from an earlier,
        # unrelated lezione citation, e.g. after projecting a plain
        # schedule-slot verse directly via _project_verse_data) must not
        # leak the lezione profile just because self._lesson_verse_ctx
        # happens to still be truthy.
        in_lesson_ctx = bool(ctx and ctx["book"] == d["book"] and ctx["chapter"] == d["chapter"])

        if in_lesson_ctx:
            new_pos = ctx["pos"] + delta
            if not (0 <= new_pos < len(ctx["verses"])):
                return  # already at the citation's first/last verse — stop here
            book, chapter = ctx["book"], ctx["chapter"]
            nxt = ctx["verses"][new_pos]
            texts = {c: (self._bible.get_verse(c, book, chapter, nxt) or "") for c in langs}
            if not any(texts.values()):
                return
            ctx["pos"] = new_pos
        else:
            primary = langs[0]
            book, chapter, vnum = d["book"], d["chapter"], d["verse"]
            nxt = vnum + delta
            if not (nxt >= 1 and self._bible.get_verse(primary, book, chapter, nxt)):
                chapters = self._bible.chapters(primary, book)
                try:
                    idx = chapters.index(chapter) + (1 if delta > 0 else -1)
                except ValueError:
                    return
                if not (0 <= idx < len(chapters)):
                    return  # already at the book's first/last chapter
                chapter = chapters[idx]
                verses = self._bible.verses(primary, book, chapter)
                if not verses:
                    return
                nxt = verses[0][0] if delta > 0 else verses[-1][0]
            texts = {c: (self._bible.get_verse(c, book, chapter, nxt) or "") for c in langs}
            if not any(texts.values()):
                return

        new_data = {"book": book, "book_name": d["book_name"], "chapter": chapter,
                    "verse": nxt, "ref": f"{d['book_name']} {chapter}:{nxt}",
                    "langs": langs, "texts": texts}
        lesson_ctx = (ctx.get("les"), ctx.get("dom")) if in_lesson_ctx else None
        self._project_verse_data(new_data, profile=("lezione" if in_lesson_ctx else "bibbia"),
                                 lesson_ctx=lesson_ctx)
        it_text = texts.get("it", next(iter(texts.values()), ""))
        self._history.add_verse(d["book_name"], chapter, nxt, text_it=it_text)
        self._save_history()

    def _project_text_block(self, text: str):
        self._proj_mode = "text"
        win = self._ensure_projection()
        win.set_background(self._settings.get("verse_bg_color", "#0b132b"),
                           self._settings.get("verse_bg_image", ""))
        win.set_text_color(self._settings.get("verse_text_color", "#ffffff"))
        win.show_text(text, autofit=True)
        self._proj_pill.configure(text="● Testo", text_color="#22c55e")

    def _project_fullscreen_image(self, path: str):
        """Project the offering slide — shown as large as possible without
        ever cropping it, so it stays fully visible (and scannable, if it
        contains a QR code)."""
        self._proj_mode = "qr"
        win = self._ensure_projection()
        win.show_image(path, caption=self._settings.get("offering_text", ""))
        self._proj_pill.configure(text="● Offerta", text_color="#22c55e")

    def _project_pdf(self, path: str):
        """Render a PDF and project it as a navigable slideshow."""
        try:
            from core.render import render_pdf
            self._slides_images = render_pdf(path, dpi=150)
        except Exception as ex:
            self._info("Errore PDF", f"Impossibile leggere il PDF:\n{ex}")
            return
        if not self._slides_images:
            self._info("PDF", "Nessuna pagina trovata nel PDF.")
            return
        self._proj_mode = "slides"
        self._proj_pill_prefix = os.path.splitext(os.path.basename(path))[0]
        win = self._ensure_projection()
        win.show_slides(self._slides_images, start=0)
        self._update_slide_label()

    def _project_video(self, path: str):
        if not os.path.isfile(path):
            self._info("Errore video", f"File non trovato:\n{path}")
            return
        # Codec check: catches videos assigned via "Scegli video"/drag-and-drop
        # (never auto-transcoded) and any download-time transcode that was
        # silently skipped — surfaces a clear reason instead of a plain black
        # screen. The probe itself is a fast header read, not a decode.
        try:
            from core.video import probe_video_codec, needs_transcode
            import imageio_ffmpeg
            ffmpeg_loc = imageio_ffmpeg.get_ffmpeg_exe()
            codec = probe_video_codec(path, ffmpeg_loc)
            if needs_transcode(codec):
                self._info("Video potrebbe non essere compatibile",
                          f"Questo file usa un codec video ({codec or 'non rilevato'}) che il "
                          "proiettore interno potrebbe non riuscire a decodificare (schermo nero, "
                          "audio senza immagine). Se il video è stato scaricato con la funzione "
                          "YouTube dell'app, la conversione automatica potrebbe non essere riuscita — "
                          "prova a riscaricarlo. In alternativa usa \"Apri esterno\" per riprodurlo "
                          "con l'app video del sistema.")
        except Exception:
            pass  # never block playback attempt on the codec check itself
        try:
            from core.video import VideoPlayer
            if self._video:
                self._video.close()
            self._video = VideoPlayer(path)
        except Exception as ex:
            self._info("Errore video", f"Impossibile riprodurre il video:\n{ex}")
            return
        self._proj_mode = "video"
        win = self._ensure_projection()
        win.show_video()
        self._proj_pill.configure(text=f"● Video: {os.path.basename(path)}",
                                  text_color="#22c55e")
        self._video_tick()

    def _video_tick(self):
        if self._proj_mode != "video" or not self._video:
            return
        if not (self._projection and self._projection.winfo_exists()):
            return
        try:
            img, done = self._video.get_frame()
            if img is not None:
                self._projection.draw_video_frame(img)
            if done:
                self._video.pause()
        except Exception as _e:
            print(f"[video_tick] {_e}")
        # ~30 fps
        self.after(33, self._video_tick)

    def _proj_registry(self):
        """mode -> {"next": fn, "prev": fn, "stop": fn}: the one place that
        knows which projection modes support advance/retreat, and any extra
        teardown a mode needs before the generic stop. _slide_next/_slide_prev,
        _stop_projection and the arrow-key bindings all consult this instead of
        hardcoding a list of mode names — wiring a future projectable type
        (e.g. an announcement slide, a prayer-request list) into keyboard nav
        means adding one entry here, not touching those methods."""
        def _slides_next():
            if self._projection and self._projection.winfo_exists():
                self._projection.next_slide()
                self._update_slide_label()
        def _slides_prev():
            if self._projection and self._projection.winfo_exists():
                self._projection.prev_slide()
                self._update_slide_label()
        return {
            "slides": {"next": _slides_next, "prev": _slides_prev},
            "verse": {"next": lambda: self._verse_step(1), "prev": lambda: self._verse_step(-1)},
            "prayer": {"next": lambda: self._prayer_step(1), "prev": lambda: self._prayer_step(-1)},
            "lezione": {"next": lambda: self._lesson_step(1), "prev": lambda: self._lesson_step(-1)},
            "external": {"next": projector.powerpoint_next, "prev": projector.powerpoint_prev,
                         "stop": projector.powerpoint_end},
        }

    def _proj_can_nav(self) -> bool:
        return bool(self._proj_registry().get(self._proj_mode))

    def _slide_next(self):
        fn = self._proj_registry().get(self._proj_mode, {}).get("next")
        if fn:
            fn()

    def _slide_prev(self):
        fn = self._proj_registry().get(self._proj_mode, {}).get("prev")
        if fn:
            fn()

    def _update_slide_label(self):
        if self._projection and self._projection.winfo_exists() and self._projection.slide_count:
            i = self._projection.slide_index + 1
            n = self._projection.slide_count
            if hasattr(self, "_slide_lbl") and self._slide_lbl.winfo_exists():
                self._slide_lbl.configure(text=f"{i} / {n}")
            prefix = getattr(self, "_proj_pill_prefix", "Diapositive")
            self._proj_pill.configure(text=f"● {prefix} ({i}/{n})", text_color="#22c55e")

    def _timer_font_px(self):
        h = 0
        try:
            if self._projection and self._projection.winfo_exists():
                h = self._projection.winfo_height()
        except Exception:
            pass
        return max(120, int((h or 1080) * 0.32))

    def _project_timer(self, remaining: int):
        self._proj_mode = "timer"
        win = self._ensure_projection()
        win.set_background(self._settings.get("timer_bg_color", "#0b132b"),
                           self._settings.get("timer_bg_image", ""))
        win.set_text_color(self._settings.get("timer_text_color", "#ffffff"))
        win.show_text(_fmt_time(remaining), secondary=self._settings.get("timer_text", ""),
                      secondary_pos="top", autofit=False, fixed_font=self._timer_font_px())
        self._proj_pill.configure(text="● Timer", text_color="#22c55e")

    def _update_timer_projection(self, remaining: int):
        if self._proj_mode == "timer" and self._projection and self._projection.winfo_exists():
            self._projection.show_text(_fmt_time(remaining),
                                       secondary=self._settings.get("timer_text", ""),
                                       secondary_pos="top", autofit=False,
                                       fixed_font=self._timer_font_px())

    def _proj_quick_cmd(self, cmd: str):
        """Dispatch Ctrl+1/2/3 (from either window) or a right-panel button
        press to the matching quick command."""
        {"black": self._proj_black, "background": self._proj_background,
         "freeze": self._proj_freeze}.get(cmd, lambda: None)()

    def _proj_black(self):
        """Toggle a black overlay — instant, doesn't touch the selected slot
        or change what's actually loaded, just what's visible on screen."""
        if self._proj_mode == "external":
            self._info("Nero", "PowerPoint sta proiettando la sua finestra: "
                       "questo comando non può oscurarla. Usa i comandi di PowerPoint stesso.")
            return
        win = self._ensure_projection(clear_overlay=False)
        win.show_black()
        self._restyle_quick_cmd_btns()

    def _proj_background(self):
        """Toggle a full-screen background-image overlay — same idea as Nero."""
        if self._proj_mode == "external":
            self._info("Sfondo", "PowerPoint sta proiettando la sua finestra: "
                       "questo comando non può sovrapporsi ad essa.")
            return
        path = self._settings.get("background_image", "")
        if not path or not os.path.isfile(path):
            self._info("Sfondo", "Nessuno sfondo configurato (Impostazioni → Sfondo).")
            return
        win = self._ensure_projection(clear_overlay=False)
        win.show_background(path)
        self._restyle_quick_cmd_btns()

    def _proj_freeze(self):
        """Toggle freezing the current output in place. For a video, also
        pauses real playback so unfreezing doesn't jump ahead in time."""
        if not (self._projection and self._projection.winfo_exists()):
            return
        if self._proj_mode == "external":
            self._info("Congela", "PowerPoint sta proiettando la sua finestra: "
                       "questo comando non può congelarla.")
            return
        was_frozen = self._projection.overlay == "freeze"
        if was_frozen:
            self._projection.unfreeze()
            if self._proj_mode == "video" and self._video and getattr(self, "_freeze_resume_video", False):
                self._video.play()
            self._freeze_resume_video = False
        else:
            if self._proj_mode == "video" and self._video:
                self._freeze_resume_video = not self._video.is_paused
                self._video.pause()
            self._projection.freeze()
        self._restyle_quick_cmd_btns()

    def _restyle_quick_cmd_btns(self):
        """Highlight whichever quick command (if any) is currently active."""
        overlay = self._projection.overlay if (self._projection and self._projection.winfo_exists()) else None
        for name, btn in getattr(self, "_quick_btns", {}).items():
            on = (overlay == name)
            btn.configure(fg_color=ACCENT if on else SURFACE_4,
                          hover_color=ACCENT_HOVER if on else SURFACE_3)

    def _stop_projection(self):
        stop_fn = self._proj_registry().get(self._proj_mode, {}).get("stop")
        if stop_fn:
            stop_fn()
        if self._video:
            try:
                self._video.close()
            except Exception:
                pass
            self._video = None
        if self._projection and self._projection.winfo_exists():
            self._projection.close()
        self._projection = None
        self._proj_mode = None
        self._proj_pill.configure(text="○ Niente in proiezione", text_color=MUTED)
        try:
            self._stop_proj_btn.configure(state="disabled")
        except Exception:
            pass
        self._refresh_bib_verse_ui()

    # ── audio ──────────────────────────────────────────────────────────────────
    def _ring_bell(self):
        bell = self._settings.get("bell_sound", "")
        if bell and os.path.isfile(bell):
            self._audio.play_bell(bell)
        else:
            self._info("Campana", "Nessun audio campana configurato (Impostazioni).")

    # ── database ─────────────────────────────────────────────────────────────
    def _load_db_async(self):
        last = self._settings.get("last_database", "")
        if not last or not os.path.isdir(last):
            self._hymns = []
            self._db_loading = False
            self._safe_after(self._on_db_loaded)
            return
        # generation counter: the latest request always wins, even mid-load
        self._db_gen = getattr(self, "_db_gen", 0) + 1
        gen = self._db_gen
        self._db_loading = True

        def run():
            try:
                hymns = load_database(last)
            except Exception as ex:
                print("[DB] error:", ex)
                hymns = []
            if gen != getattr(self, "_db_gen", gen):
                return  # superseded by a newer request
            self._hymns = hymns
            self._db_loading = False
            self._safe_after(self._on_db_loaded)
        threading.Thread(target=run, daemon=True).start()

    def _on_db_loaded(self):
        if getattr(self, "_current", "") == "inni":
            self._refresh_hymn_list()

    # ── lesson ─────────────────────────────────────────────────────────────────
    def _load_lesson_set(self):
        path = self._settings.get("lesson_file", "")
        if not path or not os.path.isfile(path):
            return None
        try:
            return lesson.LessonSet.load(path)
        except Exception as ex:
            print("[Lesson] error:", ex)
            return None

    def _current_lesson(self):
        ls = self._load_lesson_set()
        if not ls:
            return None, None
        idx = self._settings.get("lesson_override_index", -1)
        if isinstance(idx, int) and idx >= 0:
            return ls, ls.get(idx)
        return ls, ls.find_for()

    def _lesson_day_key(self, les: dict, dom: dict):
        """(data_sabato, day_position) identifies a day across a whole lesson
        without relying on the "giorno" name string, which real Lezionario
        files have been seen to mislabel/duplicate within the same lesson
        (e.g. two days both called "Mercoledì"). Returns None if the lesson
        has no date or the domanda has no day grouping."""
        sabato = les.get("data_sabato") or les.get("date") or ""
        pos = dom.get("day_position", 0)
        if not sabato or not pos:
            return None
        return sabato, pos

    def _lesson_date_badge(self, les: dict, dom: dict) -> str:
        """'Lun, 29 Giu' — the day's real calendar date, computed from
        data_sabato (the Sabbath that opens the week) + the day's 1-based
        position within "giorni" (Domenica=1, Lunedì=2, ...)."""
        key = self._lesson_day_key(les, dom)
        if not key:
            return ""
        sabato, pos = key
        from datetime import datetime, timedelta
        try:
            d = datetime.strptime(sabato.strip(), "%Y-%m-%d").date() + timedelta(days=pos)
        except ValueError:
            return ""
        return f"{_GIORNI[d.weekday()][:3].capitalize()}, {d.day} {_MESI[d.month - 1][:3].capitalize()}"

    def _lesson_photo(self, les: dict) -> str:
        """One photo shared by every day/question of the whole lezione
        (not per day — see HANDOFF for the migration from the old
        per-day-within-a-lezione shape), keyed by data_sabato alone."""
        sabato = les.get("data_sabato") or les.get("date") or ""
        if not sabato:
            return ""
        return self._settings.get("lesson_photos", {}).get(sabato, "")

    def _set_lesson_photo(self, les: dict, path: str):
        sabato = les.get("data_sabato") or les.get("date") or ""
        if not sabato:
            return
        photos = self._settings.setdefault("lesson_photos", {})
        photos[sabato] = path
        cfg.save(self._settings)

    def _pick_lesson_photo(self, les: dict):
        p = filedialog.askopenfilename(title="Foto della lezione",
                                       filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp *.gif"),
                                                  ("Tutti", "*.*")])
        if not p:
            return
        self._set_lesson_photo(les, p)
        self._render_center()

    def _lesson_resolve_verses(self, dom: dict) -> list:
        """Resolve a domanda's reference strings against the Bible DB, so the
        panel can preview and project the actual verse text (not just the
        citation) — falling back to unresolved (raw text only) when a
        reference can't be matched to a known book."""
        if not (self._bible and self._bible.ready):
            return [{"raw": r, "resolved": False, "book": None, "book_name": None,
                     "chapter": None, "verses": [], "texts": []} for r in dom["verses"]]
        lang = self._primary_lang()
        books = self._bible.books(lang)
        parsed = bible_ref.parse_references(dom["verses"], books)
        for item in parsed:
            item["texts"] = [self._bible.get_verse(lang, item["book"], item["chapter"], v)
                             for v in item["verses"]] if item["resolved"] else []
        return parsed

    def _project_lesson_verse_citation(self, book: int, chapter: int, verses: list, idx: int):
        """Project the first verse of a lezione citation, then constrain
        next/prev (_verse_step) to that citation's own verse list — so
        advancing stops at the citation's last verse instead of continuing
        through the rest of the chapter. `idx` is the domanda this citation
        belongs to — needed so the projected verse can show that day's
        header/date, same as _project_lesson_domanda/_project_lesson_note."""
        verses = sorted(verses)
        _ls, les = self._current_lesson()
        domande = lesson.flatten_domande(les) if les else []
        dom = domande[idx] if les and 0 <= idx < len(domande) else None
        self._project_verse_ref(book, chapter, verses[0], profile="lezione",
                                lesson_ctx=(les, dom))
        self._proj_lesson_idx = idx
        self._lesson_browse_idx = idx
        self._lesson_verse_ctx = {"book": book, "chapter": chapter, "verses": verses, "pos": 0,
                                  "les": les, "dom": dom}

    def _lesson_header_date(self, les: dict, dom: dict):
        """(header_text, date_text) for the day `dom` belongs to — shared by
        every lezione-context graphic profile (domanda/nota/versetto_lezione)
        so the same day always shows the same header/date regardless of
        which element is currently projected."""
        header_text = f"{dom['day_position']}. {dom['day_title'].upper()}" \
            if dom.get("day_title") else ""
        return header_text, self._lesson_date_badge(les, dom)

    def _lesson_question_marker(self, dom: dict) -> str:
        """The "a."/"b." or "1."/"2." marker drawn before a domanda's
        question text — style picked by `lesson_question_numbering`
        (some quarterlies' source material uses letters, others numbers;
        not recorded in the lesson JSON itself, see core/settings.py)."""
        if self._settings.get("lesson_question_numbering", "letters") == "numbers":
            return str(dom["day_index"] + 1)
        return chr(ord('a') + dom["day_index"])

    def _project_lesson_domanda(self, idx: int):
        _ls, les = self._current_lesson()
        if not les:
            return
        domande = lesson.flatten_domande(les)
        if not (0 <= idx < len(domande)):
            return
        self._proj_lesson_idx = idx
        self._lesson_browse_idx = idx
        self._proj_mode = "lezione"
        dom = domande[idx]
        kicker = f"{dom['day']} — Domanda {dom['day_index'] + 1}/{dom['day_count']}" if dom["day"] \
            else f"Domanda {dom['day_index'] + 1}/{dom['day_count']}"
        win = self._ensure_projection()
        header_color = self._settings.get("lesson_header_color", SLOT_COLORS["lezione"])
        question_color = self._settings.get("lesson_question_color", "#ffffff")
        domanda_profile = self._graphic_profile("domanda")
        template = domanda_profile.get("template", "")
        if template and os.path.isfile(template):
            header_text, date_text = self._lesson_header_date(les, dom)
            saved_boxes = domanda_profile.get("boxes", {})
            boxes = {key: saved_boxes.get(key, default_box)
                    for key, _label, _color, default_box in self._LESSON_BOX_DEFS}
            win.show_lesson_graphic(
                template, boxes, header_text=header_text, date_text=date_text,
                photo_path=self._lesson_photo(les),
                letter=self._lesson_question_marker(dom),
                question_text=dom["question"], verse_text="; ".join(dom["verses"]),
                header_color=header_color, question_color=question_color,
                letter_color=self._settings.get("lesson_letter_color") or None,
                date_color=self._settings.get("lesson_date_color") or None,
                verse_color=self._settings.get("lesson_verse_color") or None,
                header_max_size=self._settings.get("lesson_header_max_size") or None,
                date_max_size=self._settings.get("lesson_date_max_size") or None,
                question_max_size=self._settings.get("lesson_question_max_size") or None,
                verse_max_size=self._settings.get("lesson_verse_max_size") or None,
                font_family=self._settings.get("lesson_font_family")
                           or self._settings.get("verse_font_family", "Helvetica"))
        else:
            win.set_background(self._settings.get("verse_bg_color", "#0b132b"),
                               self._settings.get("verse_bg_image", ""))
            win.set_text_color(question_color)
            win.show_text(dom["question"], secondary=kicker,
                          secondary_pos="top", autofit=True, secondary_scale=0.045,
                          secondary_color=header_color)
        self._proj_pill.configure(text=f"● Lezione — {kicker}", text_color="#22c55e")

    def _project_lesson_note(self, idx: int):
        _ls, les = self._current_lesson()
        if not les:
            return
        domande = lesson.flatten_domande(les)
        if not (0 <= idx < len(domande)):
            return
        dom = domande[idx]
        if not dom["note"]:
            return
        self._proj_lesson_idx = idx
        self._lesson_browse_idx = idx
        self._proj_mode = "lezione"
        win = self._ensure_projection()
        win.set_background(self._settings.get("verse_bg_color", "#0b132b"),
                           self._settings.get("verse_bg_image", ""))
        win.set_text_color(self._settings.get("verse_text_color", "#ffffff"))
        # No riferimento box for nota — a note has no reference of its own;
        # showing the question there was a mistake from when this profile
        # was first split out, since fixed at the user's request.
        self._show_lesson_profile_text(win, "nota", self._NOTA_BOX_DEFS, les, dom, dom["note"])
        kicker = f"{dom['day']} — Domanda {dom['day_index'] + 1}/{dom['day_count']}" if dom["day"] \
            else f"Domanda {dom['day_index'] + 1}/{dom['day_count']}"
        self._proj_pill.configure(text=f"● Lezione — Nota ({kicker})", text_color="#22c55e")

    def _show_lesson_profile_text(self, win, profile_name, box_defs, les, dom, main_text, ref_text=""):
        """Shared by _project_lesson_note, _project_lesson_raw_text, and
        _project_verse_data's lezione branch: use `profile_name`'s
        template+boxes+independent colors/max-sizes (header/date/testo[/
        riferimento], per `box_defs`) if a template is configured, else fall
        back to the plain legacy caption-above-text rendering exactly as
        before graphic profiles existed. `les`/`dom` (the current lesson set
        and the specific day) drive the header/date text — pass None/None if
        unavailable (falls back to no header/date, template path still used
        if configured)."""
        profile = self._graphic_profile(profile_name)
        template = profile.get("template", "")
        if template and os.path.isfile(template):
            saved_boxes = profile.get("boxes", {})
            boxes = {key: saved_boxes.get(key, default_box)
                    for key, _label, _color, default_box in box_defs}
            header_text, date_text = self._lesson_header_date(les, dom) if (les and dom) else ("", "")
            colors = profile.get("colors", {})
            sizes = profile.get("max_sizes", {})
            header_color = colors.get("header") or SLOT_COLORS["lezione"]
            date_color = colors.get("date") or header_color
            testo_color = colors.get("testo") or "#ffffff"
            riferimento_color = colors.get("riferimento") or header_color
            win.show_lesson_graphic(
                template, boxes, header_text=header_text, date_text=date_text,
                header_color=header_color, date_color=date_color,
                header_max_size=sizes.get("header") or None, date_max_size=sizes.get("date") or None,
                testo_text=main_text, testo_color=testo_color,
                testo_max_size=sizes.get("testo") or None,
                riferimento_text=ref_text, riferimento_color=riferimento_color,
                riferimento_max_size=sizes.get("riferimento") or None,
                font_family=self._profile_font_family(profile_name)
                           or self._settings.get("verse_font_family", "Helvetica"))
        else:
            win.show_text(main_text, secondary=ref_text, secondary_pos="top",
                          autofit=True, secondary_scale=0.04, secondary_italic=True)

    def _project_lesson_raw_text(self, idx: int, text: str, question: str):
        """Fallback for a versetti citation the Bible-reference parser couldn't
        resolve to a book/chapter/verse — projects the raw citation text as-is."""
        if not text:
            return
        self._proj_lesson_idx = idx
        self._lesson_browse_idx = idx
        self._proj_mode = "lezione"
        win = self._ensure_projection()
        win.set_background(self._settings.get("verse_bg_color", "#0b132b"),
                           self._settings.get("verse_bg_image", ""))
        win.set_text_color(self._settings.get("verse_text_color", "#ffffff"))
        win.set_ref_color(self._settings.get("verse_ref_color", "#ffffff"))
        _ls, les = self._current_lesson()
        domande = lesson.flatten_domande(les) if les else []
        dom = domande[idx] if les and 0 <= idx < len(domande) else None
        self._show_lesson_profile_text(win, "versetto_lezione", self._VERSETTO_LEZIONE_BOX_DEFS,
                                       les, dom, text, question)
        self._proj_pill.configure(text="● Lezione — Versetto (riferimento)", text_color="#22c55e")

    def _lesson_step(self, delta: int):
        if self._proj_mode != "lezione":
            return
        _ls, les = self._current_lesson()
        if not les:
            return
        domande = lesson.flatten_domande(les)
        idx = getattr(self, "_proj_lesson_idx", 0) + delta
        if not (0 <= idx < len(domande)):
            return
        self._project_lesson_domanda(idx)

    def _check_today_lesson(self):
        path = self._settings.get("lesson_file", "")
        if not path:
            return  # no lesson file configured yet → stay silent
        ls = self._load_lesson_set()
        if not ls:
            self._info("Lezione", "File lezioni non valido o illeggibile.\n"
                                   "Controlla il file nelle Impostazioni.")
            return
        _set, lesson = self._current_lesson()
        if lesson is None:
            self._info("Nessuna lezione per oggi",
                       "Non c'è una lezione che corrisponde alla data di oggi.\n"
                       "Vai in Impostazioni → Lezione per sceglierne una manualmente "
                       "o caricare il file aggiornato.")

    # ── persistence ──────────────────────────────────────────────────────────
    def _save_schedule(self):
        self._settings["schedule"] = self._schedule.to_list()
        cfg.save(self._settings)

    def _save_history(self):
        self._settings["hymn_history"] = self._history.hymns_to_dicts()
        self._settings["verse_history"] = self._history.verses_to_dicts()
        cfg.save(self._settings)

    def _safe_after(self, fn):
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _periodic_gc(self):
        """Runs the cyclic garbage collector — see the gc.disable() comment
        at the top of this file for why automatic collection is off and this
        must always happen here (main thread) instead."""
        try:
            gc.collect()
        except Exception:
            pass
        self.after(30000, self._periodic_gc)

    def _on_close(self):
        self._settings["window_geometry"] = self.geometry()
        self._settings["left_panel_width"] = self._left_w
        self._settings["right_panel_width"] = self._right_w
        self._save_schedule()
        self._save_history()
        if self._bible:
            self._settings["bible_versions"] = self._bible.active_mapping()
        cfg.save(self._settings)
        self._audio.shutdown()
        self.destroy()

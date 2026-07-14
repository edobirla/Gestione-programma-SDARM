"""Central visual language for the operator UI (ui/app.py only — the
projected second-screen output in ui/projection.py is a separate, independent
concern with its own user-configurable colors and is NOT governed by this
module).

Source of truth: design/Specifiche implementazione customtkinter.md, produced
from the Claude Design mockup at design/Redesign.dc.html. Any future UI work
should pull its colors/fonts/icons from here rather than hardcoding new ones.

Font/color objects that need a live Tk interpreter (CTkFont, CTkImage) are
built lazily on first use, not at import time, since ui/theme.py is imported
before the App's root window exists.
"""
import os
import sys

import customtkinter as ctk
from PIL import Image

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
_ICONS_DIR = os.path.join(_ASSETS, "icons")


def _register_bundled_fonts():
    """Windows only: register the bundled Inter (assets/fonts) as a private
    font so the UI renders with the intended typeface even when Inter isn't
    installed system-wide. FR_PRIVATE (0x10) scopes it to this process — no
    admin rights, no system install, gone when the app exits. On macOS Tk
    only sees installed fonts; FONT_FAMILY already falls back silently there."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        path = os.path.join(_ASSETS, "fonts", "Inter-Variable.ttf")
        if os.path.isfile(path):
            ctypes.windll.gdi32.AddFontResourceExW(path, 0x10, 0)
    except Exception:
        pass


_register_bundled_fonts()

# ── Palette — (light, dark) tuples for anything that changes between themes;
# plain strings for accent/error, which the spec says stay identical. ──────
BG = ("#e5e8ed", "#06070a")
CARD = ("#dadee5", "#0b0d12")          # surface 1 — card
CARD_ROW = ("#d0d4dc", "#111419")      # surface 2 — row / inner card
SURFACE_3 = ("#c9ced6", "#15181e")     # secondary button
SURFACE_4 = ("#c0c4cc", "#1c1f25")     # active button / row
BORDER = ("#b3b8bf", "#25292f")
BORDER_SUBTLE = ("#b9bec6", "#21242a")

TEXT_PRIMARY = ("#030304", "#f0f2f4")
TEXT_SECONDARY = ("#17181b", "#cbced2")
TEXT_TERTIARY = ("#474b50", "#8c8f95")
TEXT_LABEL = ("#63666c", "#6e7278")     # uppercase section/category labels
TEXT_FAINT = ("#83868c", "#4f5358")

ACCENT = "#2b6dd3"
ACCENT_HOVER = "#478af1"
DANGER = "#c74b47"
DANGER_HOVER = "#b33d3a"

# Backward-compatible aliases (old names used throughout ui/app.py) — keep the
# names so existing call sites pick up the new palette with no edits, only
# for genuinely equivalent roles. New code should prefer the names above.
MUTED = TEXT_TERTIARY
HEADER_FG = TEXT_LABEL
BTN_SECONDARY = SURFACE_3
BTN_SECONDARY_HOVER = SURFACE_4

# ── Promoted from the 6 most-repeated inline hex patterns found in ui/app.py
# (secondary buttons, active/live indicator, delete hover, destructive
# actions) — applied screen-by-screen as each phase touches that code. ──────
ACTIVE_GREEN = "#22c55e"   # "in proiezione" / "already projected" indicator

# Destructive-fill button (e.g. "Azzera scaletta") — deliberately a different,
# more muted red than DANGER/DANGER_HOVER (used for the small per-row delete
# hover), per the spec's explicit "mai lo stesso rosso del tasto Azzera
# generico" rule. (light, dark) background + hover + text tuples.
DANGER_FILL = ("#f3d9d8", "#3a201f")
DANGER_FILL_HOVER = ("#ecc6c4", "#4a2624")
DANGER_FILL_TEXT = ("#7a2a26", "#e0c2c0")


def _blend(fg_hex: str, bg_hex: str, alpha: float) -> str:
    """Flatten fg_hex at `alpha` opacity over bg_hex into one solid hex —
    Tk widgets can't do real alpha compositing, so the spec's "accento al 16%"
    selected-card background is precomputed once per theme instead."""
    fg = tuple(int(fg_hex[i:i + 2], 16) for i in (1, 3, 5))
    bg = tuple(int(bg_hex[i:i + 2], 16) for i in (1, 3, 5))
    out = tuple(round(f * alpha + b * (1 - alpha)) for f, b in zip(fg, bg))
    return "#%02x%02x%02x" % out


# Selected/active card: accent @16% over the row surface, per theme, + a solid
# accent border (use SEL_BORDER as border_color on a border_width=1+ widget).
SEL_BG = (_blend(ACCENT, CARD_ROW[0], 0.16), _blend(ACCENT, CARD_ROW[1], 0.16))
SEL_BORDER = ACCENT
LESSON_BG = "#14532d"  # unused today, kept for backward compatibility

_BIBLE_GROUP_COLOR_CACHE = {}


def bible_book_group_colors(testament: str, local_index: int):
    """(border, fill, text) theme tuples for the book at `local_index` within
    books[:39] (AT) / books[39:] (NT) — muted via _blend() rather than a
    hand-picked hex, per BIBLE_BOOK_GROUPS. `fill` is a semi-transparent
    wash of the group hue (still readable, never a loud full-saturation
    fill); `text` stays a fixed neutral color so it reads on every hue.
    Falls back to the neutral BORDER/CARD_ROW/TEXT_PRIMARY triple outside
    any known range."""
    key = (testament, local_index)
    cached = _BIBLE_GROUP_COLOR_CACHE.get(key)
    if cached is not None:
        return cached
    for lo, hi, _name, hexcol in BIBLE_BOOK_GROUPS.get(testament, []):
        if lo <= local_index <= hi:
            border = (_blend(hexcol, CARD_ROW[0], 0.85), _blend(hexcol, CARD_ROW[1], 0.85))
            fill = (_blend(hexcol, CARD_ROW[0], 0.60), _blend(hexcol, CARD_ROW[1], 0.60))
            result = (border, fill, TEXT_PRIMARY)
            _BIBLE_GROUP_COLOR_CACHE[key] = result
            return result
    result = (BORDER, CARD_ROW, TEXT_PRIMARY)
    _BIBLE_GROUP_COLOR_CACHE[key] = result
    return result

# ── Category colors — same lightness/chroma, different hue. Only for
# labels/icons/dots, NEVER as a full card background (spec is explicit). ───
SLOT_COLORS = {
    "inno": "#888dec", "video": "#6198ee", "audio": "#12b382",
    "versetto": "#de7949", "lezione": "#5aae5f", "presentazione": "#00b1ba",
    "timer": "#e38d3d", "documento": "#8f9298", "preghiera": "#ee7c90",
    "testo": "#cb86db", "qrcode": "#8f9298", "campana": "#e38d3d",
    "immagine": "#e6c229", "altro": "#8f9298",
}

# ── Bible book canonical groups — one muted color per group, for the book
# grid's "wall of identical pills" problem. Ranges are *local* indices within
# books[:39] (AT) / books[39:] (NT), as split by ui.app._render_book_grid —
# verified against the real bibles/*.db canonical order (Genesi..Malachia,
# Matteo..Apocalisse), not by book name (fragile). Never a full-color fill —
# only pill text/border, same restraint as SLOT_COLORS elsewhere.
BIBLE_BOOK_GROUPS = {
    "AT": [
        (0, 4, "Pentateuco", "#d16161"),
        (5, 16, "Libri storici", "#d1a461"),
        (17, 21, "Libri poetici", "#bbd161"),
        (22, 26, "Profeti maggiori", "#77d161"),
        (27, 38, "Profeti minori", "#61d18e"),
    ],
    "NT": [
        (0, 3, "Vangeli", "#61d1d1"),
        (4, 4, "Atti", "#618ed1"),
        (5, 17, "Epistole paoline", "#7761d1"),
        (18, 25, "Epistole generali", "#bb61d1"),
        (26, 26, "Apocalisse", "#d161a4"),
    ],
}

# ── Prayer "motivo" colors — auto-assigned by hashing the reason text into
# this fixed palette, until the user overrides one via the color swatch in
# the add/edit-prayer modal (override persisted in
# settings["prayer_reason_colors"], keyed by lowercased reason text).
PRAYER_REASON_PALETTE = [
    "#22c55e", "#eab308", "#3b82f6", "#ec4899", "#8b5cf6",
    "#f97316", "#14b8a6", "#ef4444",
]


def prayer_reason_color(reason: str, overrides: dict) -> str:
    key = (reason or "").strip().lower()
    if not key:
        return TEXT_TERTIARY[1]
    custom = (overrides or {}).get(key)
    if custom:
        return custom
    idx = sum(ord(c) for c in key) % len(PRAYER_REASON_PALETTE)
    return PRAYER_REASON_PALETTE[idx]


def readable_text_for(hex_bg: str) -> str:
    """Black or white, whichever reads better on a given (possibly
    user-picked, unconstrained) background hex — needed for the prayer
    reason color swatch button, unlike the app's other color swatches which
    only ever sit on a couple of known, pre-chosen default colors."""
    r, g, b = (int(hex_bg[i:i + 2], 16) for i in (1, 3, 5))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#111111" if luminance > 0.6 else "#ffffff"

# ── Typography ──────────────────────────────────────────────────────────────
# Tk font "weight" only distinguishes normal/bold (no 500/600 granularity
# without bundling separate named font families per weight) — 400/500 map to
# "normal", 600/700 map to "bold". Family falls back to the Tk default
# silently if "Inter" isn't installed (see assets/fonts/LEGGIMI.txt).
FONT_FAMILY = "Inter"
_FONT_CACHE = {}


def _font(size: int, weight: str = "normal") -> ctk.CTkFont:
    key = (size, weight)
    f = _FONT_CACHE.get(key)
    if f is None:
        f = ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
        _FONT_CACHE[key] = f
    return f


def font_title() -> ctk.CTkFont:
    """Screen title — 28/700."""
    return _font(28, "bold")


def font_section(size: int = 18, bold: bool = True) -> ctk.CTkFont:
    """Section/card title — 16-24, 600-700."""
    return _font(size, "bold" if bold else "normal")


def font_body(size: int = 14, bold: bool = False) -> ctk.CTkFont:
    """Regular interface text — 14-15, 400-500."""
    return _font(size, "bold" if bold else "normal")


def font_label(size: int = 11) -> ctk.CTkFont:
    """Uppercase category/section label — 10-11, 700."""
    return _font(size, "bold")


# ── Icons ────────────────────────────────────────────────────────────────
# PNGs rasterized (true alpha transparency) from design/Redesign.dc.html's
# inline SVGs — one file per (name, color-variant) pair, since CTkImage can't
# recolor at runtime. "muted" is theme-dependent (a different gray in light
# vs dark mode) so it's stored as two files and wired into CTkImage's native
# light_image/dark_image swap; other variants (white, a category color, etc.)
# are theme-invariant, so the same file serves both. Returns None (never
# raises) if an icon hasn't been generated yet, so callers can fall back to a
# text glyph.
_ICON_CACHE = {}


def icon(name: str, variant: str = "muted", size: int = 18):
    key = (name, variant, size)
    img = _ICON_CACHE.get(key)
    if img is not None:
        return img
    try:
        if variant == "muted":
            light_p = os.path.join(_ICONS_DIR, f"{name}-muted-light.png")
            dark_p = os.path.join(_ICONS_DIR, f"{name}-muted-dark.png")
            if not (os.path.isfile(light_p) and os.path.isfile(dark_p)):
                return None
            img = ctk.CTkImage(light_image=Image.open(light_p),
                               dark_image=Image.open(dark_p), size=(size, size))
        else:
            path = os.path.join(_ICONS_DIR, f"{name}-{variant}.png")
            if not os.path.isfile(path):
                return None
            pil_img = Image.open(path)
            img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(size, size))
    except Exception:
        return None
    _ICON_CACHE[key] = img
    return img

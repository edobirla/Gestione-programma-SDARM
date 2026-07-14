"""Full-screen projection window (goes on the projector / second screen).

This is intentionally a real separate window: it is the output shown to the
congregation. In-app editing popups are NOT windows (see app._show_modal).

Supports: solid/image background + centered text, a centered foreground image
(QR), a full-screen cover image, and a slideshow of images (rendered PDF pages).
"""
import os
import tkinter as tk

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def list_monitors():
    """Return list of dicts {x,y,width,height,primary}. Empty if unavailable."""
    try:
        from screeninfo import get_monitors
        out = []
        for m in get_monitors():
            out.append({"x": m.x, "y": m.y, "width": m.width, "height": m.height,
                        "primary": bool(getattr(m, "is_primary", False))})
        return out
    except Exception:
        return []


def secondary_monitor():
    """Best guess for the projector monitor (first non-primary)."""
    mons = list_monitors()
    for m in mons:
        if not m["primary"]:
            return m
    return mons[0] if mons else None


class ProjectionWindow(tk.Toplevel):
    def __init__(self, master, screen_index: int = 1, on_slide_change=None, on_close=None,
                 on_nav=None, on_quick=None):
        super().__init__(master)
        self.title("Proiezione")
        self.configure(bg="black")
        self._photo = None
        self._bg_photo = None
        self._on_slide_change = on_slide_change  # called with (index) after any slide change
        self._on_close = on_close                # called when window is closed via Esc or X
        # This window lives on the second screen and can end up with OS keyboard
        # focus (e.g. right after being raised/topmost'd). If on_nav is given,
        # arrow/page keys delegate to it (the app's own next/prev dispatcher,
        # which knows about every projection mode) instead of this window's own
        # next_slide()/prev_slide(), which only understand image/text slideshows
        # and silently no-op for other modes (e.g. a single projected verse).
        self._on_nav = on_nav
        self._on_quick = on_quick  # called with "black"/"background"/"freeze" (Ctrl+1/2/3)

        self._bg_color = "#0b132b"
        self._text_color = "#ffffff"
        self._ref_color = "#ffffff"
        self._secondary_color = None
        self._bg_image_path = ""
        self._top_text = ""
        self._main_text = ""
        self._main_font_px = 120
        self._top_font_px = 48
        self._font_family = "Helvetica"
        self._text_box = None
        self._ref_box = None
        self._ref_font_family = "Helvetica"
        self._text_max_size = None
        self._ref_max_size = None
        self._text_template_path = ""
        self._secondary_scale = 0.045
        self._secondary_bold = False
        self._secondary_italic = False
        self._mode = "text"            # text | image | slides | textslides | table | lesson
        self._fg_image_path = ""
        self._lesson_template_path = ""
        self._lesson_boxes = {}
        self._lesson_header_text = ""
        self._lesson_date_text = ""
        self._lesson_photo_path = ""
        self._lesson_letter = ""
        self._lesson_question = ""
        self._lesson_verse_text = ""
        self._lesson_header_color = "#ffffff"
        self._lesson_question_color = "#ffffff"
        self._lesson_letter_color = "#ffffff"
        self._lesson_date_color = "#ffffff"
        self._lesson_verse_color = "#ffffff"
        self._lesson_header_max_size = None
        self._lesson_date_max_size = None
        self._lesson_question_max_size = None
        self._lesson_verse_max_size = None
        self._lesson_testo_text = ""
        self._lesson_testo_color = "#ffffff"
        self._lesson_testo_max_size = None
        self._lesson_riferimento_text = ""
        self._lesson_riferimento_color = "#ffffff"
        self._lesson_riferimento_max_size = None
        self._slides = []              # list of PIL images
        self._text_slides = []         # list of strings
        self._table_rows = []          # list of (name, motivo) — table mode
        self._slide_idx = 0
        self._video_img = None
        # Overlay sits on top of whatever _mode is currently showing, without
        # disturbing it — None | "black" | "background" | "freeze". This is
        # what lets black/background/freeze be undone back to the exact
        # underlying content.
        self._overlay = None
        self._overlay_bg_path = ""

        self._cached_size = None  # set in _place_on_projector before winfo_width() works
        self._screen_index = screen_index

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg="black")
        self.canvas.pack(fill="both", expand=True)
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Right>", lambda e: self._nav(1))
        self.bind("<Left>", lambda e: self._nav(-1))
        self.bind("<Next>", lambda e: self._nav(1))
        self.bind("<Prior>", lambda e: self._nav(-1))
        self.bind("<Control-Key-1>", lambda e: self._quick("black"))
        self.bind("<Control-Key-2>", lambda e: self._quick("background"))
        self.bind("<Control-Key-3>", lambda e: self._quick("freeze"))

        self._place_on_projector()

    # ── placement (Sidecar / extended display aware) ───────────────────────────
    def _place_on_projector(self):
        # Honor the explicitly configured monitor (Impostazioni → Generale →
        # "Schermo di proiezione" — same list/order as list_monitors()) when
        # it exists and isn't the primary; otherwise fall back to the original
        # first-non-primary heuristic. On a typical 2-screen setup the default
        # index (1) and the heuristic pick the same monitor, so nothing
        # changes — the setting only matters with 3+ screens or unusual
        # monitor ordering, where it previously did nothing at all.
        mons = list_monitors()
        mon = None
        if 0 <= self._screen_index < len(mons) and not mons[self._screen_index]["primary"]:
            mon = mons[self._screen_index]
        if mon is None:
            mon = secondary_monitor()
        try:
            if mon and not mon["primary"]:
                w, h = mon["width"], mon["height"]
                self._cached_size = (w, h)
                self.geometry(f"{w}x{h}+{mon['x']}+{mon['y']}")
                self.update_idletasks()
                # borderless full-cover on that monitor
                self.overrideredirect(True)
                self.lift()
                self.after(200, lambda: self.attributes("-topmost", True))
            else:
                # single screen: just fullscreen on primary
                self.update_idletasks()
                self.attributes("-fullscreen", True)
        except Exception:
            try:
                self.attributes("-fullscreen", True)
            except Exception:
                pass

    # ── public API ─────────────────────────────────────────────────────────────
    def set_background(self, color: str = None, image_path: str = None):
        if color:
            self._bg_color = color
        if image_path is not None:
            self._bg_image_path = image_path
        self._redraw()

    def set_text_color(self, color: str):
        self._text_color = color
        self._redraw()

    def set_ref_color(self, color: str):
        """Color for the Bible reference box only (e.g. 'Genesi 1:1') —
        independent from the main verse text color."""
        self._ref_color = color
        self._redraw()

    def show_text(self, main: str, secondary: str = "", secondary_pos: str = "top",
                  autofit: bool = True, fixed_font: int = None, font_family: str = None,
                  text_box: tuple = None, ref_box: tuple = None, ref_font_family: str = None,
                  secondary_scale: float = 0.045, secondary_bold: bool = False,
                  secondary_italic: bool = False, secondary_color: str = None,
                  text_max_size: int = None, ref_max_size: int = None,
                  template_path: str = None):
        """Show centered text. If autofit, the main text is scaled to always fit
        the screen on one page. `secondary` (e.g. a verse reference or a prayer
        request's motivo) is drawn either relative to the main text block
        (`secondary_pos`: 'top'|'bottom' — used by the timer's caption and by
        prayer requests) or, if `ref_box`/`text_box` are given, autofit inside
        that (x, y, w, h) box (0..1 fractions of the screen) — like a Word text
        box the user can freely move and resize; used for Bible verses, where
        `text_box` is the main verse text's box and `ref_box` the reference's.
        `font_family` overrides the default Helvetica for the main text;
        `ref_font_family` does the same for the secondary text (defaults to
        `font_family`). `secondary_scale` controls the secondary text's size as
        a fraction of screen height when not using `ref_box` (bigger for
        prayer-request captions than for a plain caption). `text_max_size`/
        `ref_max_size` (px, or None/0 for no cap) clamp the box autofit so it
        never grows past a manually chosen size, even if the box itself is
        large — this is on top of, not instead of, the box-based autofit.
        `template_path`, if given together with `text_box`/`ref_box`, composites
        onto that template image (fit to screen, never cropped) instead of the
        plain color/image background — same convention as show_lesson_graphic:
        the boxes become fractions of the TEMPLATE's own pixel size rather than
        the screen. Falls back to the plain background when unset/missing."""
        self._mode = "text"
        self._main_text = main or ""
        self._secondary = secondary or ""
        self._secondary_pos = secondary_pos
        self._autofit = autofit
        self._fixed_font = fixed_font
        self._font_family = font_family or "Helvetica"
        self._text_box = text_box
        self._ref_box = ref_box
        self._ref_font_family = ref_font_family or self._font_family
        self._text_max_size = text_max_size or None
        self._ref_max_size = ref_max_size or None
        self._text_template_path = template_path or ""
        self._secondary_scale = secondary_scale
        self._secondary_bold = secondary_bold
        self._secondary_italic = secondary_italic
        self._secondary_color = secondary_color
        self._redraw()

    def show_lesson_graphic(self, template_path: str, boxes: dict, header_text: str = "",
                            date_text: str = "", photo_path: str = "", letter: str = "",
                            question_text: str = "", verse_text: str = "",
                            header_color: str = "#ffffff", question_color: str = "#ffffff",
                            letter_color: str = None, date_color: str = None,
                            verse_color: str = None, header_max_size: int = None,
                            date_max_size: int = None, question_max_size: int = None,
                            verse_max_size: int = None, testo_text: str = "",
                            testo_color: str = None, testo_max_size: int = None,
                            riferimento_text: str = "", riferimento_color: str = None,
                            riferimento_max_size: int = None, font_family: str = None):
        """Project the lesson question over a themed template instead of a
        plain background — the template is scaled to fill the screen without
        ever being cropped (see _fit_contain), and `boxes` (dict with
        "header"/"date"/"photo"/"question" — the domanda shape — or
        "header"/"date"/"testo"/"riferimento" — the nota/versetto_lezione
        shape — keys, each an (x, y, w, h) 0..1 fraction box relative to the
        TEMPLATE's own pixel size, not the screen) says where each element
        goes on top of it; a profile only needs to supply the box keys it
        actually uses, everything else is silently skipped. The photo is
        cropped to fill its box (it's a decorative slot in a fixed frame,
        unlike a full QR/Immagine slide, which must never be cropped).
        `letter_color`/`date_color`/`verse_color` each independently override
        the "a."/"b." marker, the date badge, and the verse-citation line
        under the question — falling back to `header_color` when not given.
        `testo_color`/`riferimento_color` do the same for the nota/
        versetto_lezione shape, also falling back to `header_color`.
        `*_max_size` (px, or None/0 for no cap) clamp each element's box
        autofit the same way `show_text`'s do. `font_family`, if given,
        overrides whatever the last `show_text` call happened to leave in
        `self._font_family` — pass it explicitly rather than relying on that
        stale cross-call state."""
        self._mode = "lesson"
        self._lesson_template_path = template_path or ""
        self._lesson_boxes = boxes or {}
        self._lesson_header_text = header_text or ""
        self._lesson_date_text = date_text or ""
        self._lesson_photo_path = photo_path or ""
        self._lesson_letter = letter or ""
        self._lesson_question = question_text or ""
        self._lesson_verse_text = verse_text or ""
        self._lesson_header_color = header_color or "#ffffff"
        self._lesson_question_color = question_color or "#ffffff"
        self._lesson_letter_color = letter_color or self._lesson_header_color
        self._lesson_date_color = date_color or self._lesson_header_color
        self._lesson_verse_color = verse_color or self._lesson_header_color
        self._lesson_header_max_size = header_max_size or None
        self._lesson_date_max_size = date_max_size or None
        self._lesson_question_max_size = question_max_size or None
        self._lesson_verse_max_size = verse_max_size or None
        self._lesson_testo_text = testo_text or ""
        self._lesson_testo_color = testo_color or self._lesson_header_color
        self._lesson_testo_max_size = testo_max_size or None
        self._lesson_riferimento_text = riferimento_text or ""
        self._lesson_riferimento_color = riferimento_color or self._lesson_header_color
        self._lesson_riferimento_max_size = riferimento_max_size or None
        if font_family:
            self._font_family = font_family
        self._redraw()

    def show_table(self, rows):
        """Project a two-column table (name, motivo) — e.g. the full prayer
        request list — autofit so it always stays readable regardless of row
        count. Each row is (name, reason) or (name, reason, reason_color) —
        the color lets each prayer's motivo project in its own color."""
        self._mode = "table"
        norm = []
        for row in (rows or []):
            if len(row) == 3:
                n, r, rc = row
            else:
                n, r = row
                rc = None
            if n:
                norm.append((n, r, rc))
        self._table_rows = norm
        self._redraw()

    def show_image(self, image_path: str, caption: str = ""):
        """Show a photo as large as possible without ever cropping it —
        used for both the offering slide and the generic Immagine slot,
        which must stay fully visible (never cut off) and never shrunk
        smaller than the screen allows, whatever their native aspect ratio."""
        self._mode = "image"
        self._fg_image_path = image_path
        self._caption = caption or ""
        self._redraw()

    def show_slides(self, pil_images, start: int = 0):
        self._mode = "slides"
        self._slides = pil_images or []
        self._text_slides = []
        self._slide_idx = max(0, min(start, len(self._slides) - 1)) if self._slides else 0
        self._redraw()

    def show_black(self):
        """Toggle a black overlay over whatever is currently projected —
        pressing it again restores the underlying content exactly."""
        self._overlay = None if self._overlay == "black" else "black"
        self._redraw()

    def show_background(self, path: str):
        """Toggle a full-screen background image overlay over whatever is
        currently projected — pressing it again restores the underlying
        content."""
        self._overlay_bg_path = path
        self._overlay = None if self._overlay == "background" else "background"
        self._redraw()

    def freeze(self):
        """Stop updating the display entirely, leaving whatever is currently
        drawn exactly as-is until unfreeze() (video frames included)."""
        self._overlay = "freeze"

    def unfreeze(self):
        self._overlay = None
        self._redraw()

    def toggle_freeze(self):
        self.unfreeze() if self._overlay == "freeze" else self.freeze()

    def clear_overlay(self):
        """Called when real new content is about to be shown, so a stale
        black/background/freeze from a previous item never hides it."""
        self._overlay = None

    @property
    def overlay(self):
        return self._overlay

    def show_video(self):
        self._mode = "video"
        self._video_img = None
        self._video_canvas_item = None   # reuse canvas item to avoid per-frame flicker
        self._redraw()

    def draw_video_frame(self, pil_image):
        """Blit a decoded video frame (called ~30×/s by the app)."""
        if not self.winfo_exists() or self._mode != "video" or self._overlay:
            return
        if not _HAS_PIL:
            return
        c = self.canvas
        w, h = self._size()
        img = _fit_contain(pil_image, w, h)
        self._photo = ImageTk.PhotoImage(img)
        if self._video_canvas_item and c.find_withtag(self._video_canvas_item):
            # Update existing item in-place — no delete/create → no black flash
            c.itemconfigure(self._video_canvas_item, image=self._photo)
        else:
            c.delete("all")
            c.configure(bg="black")
            self._video_canvas_item = c.create_image(
                w // 2, h // 2, anchor="center", image=self._photo)
        self._video_img = pil_image
        c.update_idletasks()  # force Tk to flush the canvas on macOS

    def show_text_slides(self, texts, start: int = 0):
        """Project a list of text pages (e.g. hymn verses) — navigable & autofit."""
        self._mode = "textslides"
        self._text_slides = [t for t in texts if t.strip()] or [""]
        self._slides = []
        self._slide_idx = max(0, min(start, len(self._text_slides) - 1))
        self._redraw()

    def _nav(self, direction: int):
        """Route a Right/Left/PageDown/PageUp press to the app's dispatcher if
        given, else fall back to this window's own slideshow navigation."""
        if self._on_nav:
            self._on_nav(direction)
        elif direction > 0:
            self.next_slide()
        else:
            self.prev_slide()

    def _quick(self, cmd: str):
        """Route a Ctrl+1/2/3 press (black/background/freeze) to the app's
        dispatcher if given, else handle it locally."""
        if self._on_quick:
            self._on_quick(cmd)
        elif cmd == "black":
            self.show_black()
        elif cmd == "freeze":
            self.toggle_freeze()

    def next_slide(self):
        if self._slide_idx < self.slide_count - 1:
            self._slide_idx += 1
            self._redraw()
            if self._on_slide_change:
                self._on_slide_change(self._slide_idx)

    def prev_slide(self):
        if self._slide_idx > 0:
            self._slide_idx -= 1
            self._redraw()
            if self._on_slide_change:
                self._on_slide_change(self._slide_idx)

    @property
    def slide_index(self):
        return self._slide_idx

    @property
    def slide_count(self):
        if self._mode == "textslides":
            return len(self._text_slides)
        return len(self._slides)

    def close(self):
        cb = self._on_close
        self._on_close = None  # clear before calling to avoid re-entry
        try:
            self.destroy()
        except Exception:
            pass
        if cb:
            try:
                cb()
            except Exception:
                pass

    # ── rendering ───────────────────────────────────────────────────────────────
    def _size(self):
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            # Window not yet realized — use geometry set by _place_on_projector
            if self._cached_size:
                return self._cached_size
            w = self.winfo_screenwidth()
            h = self.winfo_screenheight()
        return max(w, 1), max(h, 1)

    def _redraw(self):
        if not self.winfo_exists():
            return
        if self._overlay == "freeze":
            return  # leave the canvas exactly as it already is
        c = self.canvas
        c.delete("all")
        w, h = self._size()

        if self._overlay == "black":
            c.configure(bg="black")
            return

        if self._overlay == "background":
            c.configure(bg="black")
            if self._overlay_bg_path and _HAS_PIL and os.path.isfile(self._overlay_bg_path):
                try:
                    src = Image.open(self._overlay_bg_path).convert("RGBA")
                    fitted = _fit_contain(src, w, h)
                    canvas_img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
                    ox, oy = (w - fitted.width) // 2, (h - fitted.height) // 2
                    canvas_img.paste(fitted, (ox, oy), fitted)
                    self._photo = ImageTk.PhotoImage(canvas_img.convert("RGB"))
                    c.create_image(0, 0, anchor="nw", image=self._photo)
                except Exception:
                    pass
            return

        if self._mode == "video":
            c.configure(bg="black")
            # After deleting all items, force draw_video_frame to recreate the canvas item
            self._video_canvas_item = None
            if self._video_img is not None and _HAS_PIL:
                img = _fit_contain(self._video_img, w, h)
                self._photo = ImageTk.PhotoImage(img)
                self._video_canvas_item = c.create_image(
                    w // 2, h // 2, anchor="center", image=self._photo)
            return

        if self._mode == "slides" and self._slides and _HAS_PIL:
            img = _fit_contain(self._slides[self._slide_idx], w, h)
            self._photo = ImageTk.PhotoImage(img)
            c.configure(bg="black")
            c.create_image(w // 2, h // 2, anchor="center", image=self._photo)
            return

        if self._mode == "textslides" and self._text_slides:
            # background then autofit text page
            if self._bg_image_path and _HAS_PIL and os.path.isfile(self._bg_image_path):
                try:
                    bgimg = _fit_cover(Image.open(self._bg_image_path).convert("RGB"), w, h)
                    self._bg_photo = ImageTk.PhotoImage(bgimg)
                    c.create_image(0, 0, anchor="nw", image=self._bg_photo)
                except Exception:
                    c.configure(bg=self._bg_color)
                    c.create_rectangle(0, 0, w, h, fill=self._bg_color, outline="")
            else:
                c.configure(bg=self._bg_color)
                c.create_rectangle(0, 0, w, h, fill=self._bg_color, outline="")
            self._main_text = self._text_slides[self._slide_idx]
            self._secondary = ""
            self._autofit = True
            self._fixed_font = None
            self._font_family = "Helvetica"
            self._text_box = None
            self._ref_box = None
            self._draw_text(c, w, h)
            return

        if self._mode == "lesson" and self._lesson_template_path and _HAS_PIL \
                and os.path.isfile(self._lesson_template_path):
            c.configure(bg="black")
            try:
                tmpl = Image.open(self._lesson_template_path).convert("RGB")
            except Exception:
                tmpl = None
            if tmpl is not None:
                fitted = _fit_contain(tmpl, w, h)
                tw, th = fitted.size
                tx, ty = (w - tw) // 2, (h - th) // 2
                boxes = self._lesson_boxes or {}

                photo_box = boxes.get("photo")
                if self._lesson_photo_path and photo_box and os.path.isfile(self._lesson_photo_path):
                    bx, by, bw, bh = photo_box
                    pw, ph = max(1, int(bw * tw)), max(1, int(bh * th))
                    try:
                        photo = _fit_cover(Image.open(self._lesson_photo_path).convert("RGB"), pw, ph)
                        fitted.paste(photo, (int(bx * tw), int(by * th)))
                    except Exception:
                        pass

                self._photo = ImageTk.PhotoImage(fitted)
                c.create_image(tx, ty, anchor="nw", image=self._photo)

                def to_screen(frac_box):
                    bx, by, bw, bh = frac_box
                    return ((tx + bx * tw) / w, (ty + by * th) / h, bw * tw / w, bh * th / h)

                if boxes.get("header") and self._lesson_header_text:
                    self._draw_text_in_box(c, w, h, self._lesson_header_text, self._font_family,
                                           to_screen(boxes["header"]), weight="bold",
                                           color=self._lesson_header_color,
                                           max_size=self._lesson_header_max_size)
                if boxes.get("date") and self._lesson_date_text:
                    self._draw_text_in_box(c, w, h, self._lesson_date_text, self._font_family,
                                           to_screen(boxes["date"]), weight="bold",
                                           color=self._lesson_date_color,
                                           max_size=self._lesson_date_max_size)
                if boxes.get("question") and self._lesson_question:
                    qx, qy, qw, qh = boxes["question"]
                    if self._lesson_verse_text:
                        q_h, gap, v_h = qh * 0.66, qh * 0.05, qh * 0.29
                        question_sub = (qx, qy, qw, q_h)
                        verse_sub = (qx, qy + q_h + gap, qw, v_h)
                    else:
                        question_sub, verse_sub = (qx, qy, qw, qh), None
                    lead = f"{self._lesson_letter}." if self._lesson_letter else ""
                    qtext = f"{lead}  {self._lesson_question}" if lead else self._lesson_question
                    self._draw_text_in_box(c, w, h, qtext, self._font_family,
                                           to_screen(question_sub), weight="bold",
                                           color=self._lesson_question_color,
                                           lead_text=lead, lead_color=self._lesson_letter_color,
                                           max_size=self._lesson_question_max_size)
                    if verse_sub:
                        self._draw_text_in_box(c, w, h, self._lesson_verse_text, self._font_family,
                                               to_screen(verse_sub), weight="normal", slant="italic",
                                               color=self._lesson_verse_color,
                                               max_size=self._lesson_verse_max_size)
                if boxes.get("testo") and self._lesson_testo_text:
                    self._draw_text_in_box(c, w, h, self._lesson_testo_text, self._font_family,
                                           to_screen(boxes["testo"]), weight="bold",
                                           color=self._lesson_testo_color,
                                           max_size=self._lesson_testo_max_size)
                if boxes.get("riferimento") and self._lesson_riferimento_text:
                    self._draw_text_in_box(c, w, h, self._lesson_riferimento_text, self._font_family,
                                           to_screen(boxes["riferimento"]), weight="normal",
                                           slant="italic", color=self._lesson_riferimento_color,
                                           max_size=self._lesson_riferimento_max_size)
                return

        if self._mode == "text" and self._text_template_path and _HAS_PIL \
                and os.path.isfile(self._text_template_path) \
                and (self._text_box is not None or self._ref_box is not None):
            # A "graphic profile" for plain text_box/ref_box content (Bible
            # verses, lezione note, lezione-cited verse) — same template
            # compositing convention as the "lesson" branch above, so a
            # profile with no template configured falls straight through to
            # the ordinary plain-background rendering below unaffected.
            c.configure(bg="black")
            try:
                tmpl = Image.open(self._text_template_path).convert("RGB")
            except Exception:
                tmpl = None
            if tmpl is not None:
                fitted = _fit_contain(tmpl, w, h)
                tw, th = fitted.size
                tx, ty = (w - tw) // 2, (h - th) // 2
                self._photo = ImageTk.PhotoImage(fitted)
                c.create_image(tx, ty, anchor="nw", image=self._photo)

                def to_screen(frac_box):
                    bx, by, bw, bh = frac_box
                    return ((tx + bx * tw) / w, (ty + by * th) / h, bw * tw / w, bh * th / h)

                family = getattr(self, "_font_family", "Helvetica") or "Helvetica"
                ref_family = getattr(self, "_ref_font_family", family) or family
                if self._text_box is not None and self._main_text:
                    self._draw_text_in_box(c, w, h, self._main_text, family, to_screen(self._text_box),
                                           weight="bold", max_size=self._text_max_size)
                if self._secondary and self._ref_box is not None:
                    sec_bold = getattr(self, "_secondary_bold", False)
                    sec_italic = getattr(self, "_secondary_italic", False)
                    self._draw_text_in_box(c, w, h, self._secondary, ref_family, to_screen(self._ref_box),
                                           weight=("bold" if sec_bold else "normal"),
                                           slant=("italic" if sec_italic else "roman"),
                                           color=getattr(self, "_ref_color", None),
                                           max_size=self._ref_max_size)
                return

        # background (color or image)
        if self._bg_image_path and _HAS_PIL and os.path.isfile(self._bg_image_path):
            try:
                img = _fit_cover(Image.open(self._bg_image_path).convert("RGB"), w, h)
                self._bg_photo = ImageTk.PhotoImage(img)
                c.create_image(0, 0, anchor="nw", image=self._bg_photo)
            except Exception:
                c.create_rectangle(0, 0, w, h, fill=self._bg_color, outline="")
        else:
            c.configure(bg=self._bg_color)
            c.create_rectangle(0, 0, w, h, fill=self._bg_color, outline="")

        if self._mode == "image" and self._fg_image_path and _HAS_PIL \
                and os.path.isfile(self._fg_image_path):
            fg = _fit_contain(Image.open(self._fg_image_path).convert("RGBA"), w, h)
            self._photo = ImageTk.PhotoImage(fg)
            c.create_image(w // 2, h // 2, anchor="center", image=self._photo)
            cap = getattr(self, "_caption", "")
            if cap:
                c.create_text(w // 2, 40, text=cap, fill=self._text_color,
                              font=("Helvetica", self._top_font_px), anchor="n")
            return

        if self._mode == "table":
            self._draw_table(c, w, h)
            return

        self._draw_text(c, w, h)

    def _draw_text(self, c, w, h):
        import tkinter.font as tkfont
        main = getattr(self, "_main_text", "")
        secondary = getattr(self, "_secondary", "")
        text_box = getattr(self, "_text_box", None)
        ref_box = getattr(self, "_ref_box", None)
        family = getattr(self, "_font_family", "Helvetica") or "Helvetica"
        ref_family = getattr(self, "_ref_font_family", family) or family

        if text_box is not None:
            # Box mode (Bible verses): main text always autofits inside its
            # own user-resizable box — like a Word text box — independent of
            # whatever box the reference is in, so the two never collide.
            self._draw_text_in_box(c, w, h, main, family, text_box, weight="bold",
                                   max_size=getattr(self, "_text_max_size", None))
        else:
            self._draw_text_legacy(c, w, h)

        if secondary and ref_box is not None:
            sec_bold = getattr(self, "_secondary_bold", False)
            sec_italic = getattr(self, "_secondary_italic", False)
            self._draw_text_in_box(c, w, h, secondary, ref_family, ref_box,
                                   weight=("bold" if sec_bold else "normal"),
                                   slant=("italic" if sec_italic else "roman"),
                                   color=getattr(self, "_ref_color", None),
                                   max_size=getattr(self, "_ref_max_size", None))
        elif secondary and text_box is None:
            self._draw_secondary_legacy(c, w, h)

    def _draw_text_in_box(self, c, w, h, text, family, box, weight="bold", slant="roman",
                          color=None, lead_text="", lead_color=None, max_size=None):
        """Autofit `text` (wrapped, centered) inside a (x, y, w, h) box given
        as 0..1 fractions of the screen — the box is the single source of
        truth for size, so dragging/resizing it in the settings preview
        changes the font size exactly the same way it will on the real
        projection. `color` overrides the main text color (used for the
        Bible reference box, which has its own independent color).
        `lead_text`/`lead_color` draw a leading substring (the lezione
        question's "a."/"b." marker) in its own color — it always lands at
        the very start of the wrapped text's first line, so only that line
        needs splitting into two colored runs. `max_size` (px, or None for no
        cap) clamps the autofit so the box can be large without the text
        growing arbitrarily big — e.g. a short Bible reference in a wide box."""
        import tkinter.font as tkfont
        if not text:
            return
        bx, by, bw, bh = box
        px, py = int(bx * w), int(by * h)
        pw, ph = max(1, int(bw * w)), max(1, int(bh * h))
        size, lines = _fit_text(text, pw, ph, tkfont, family=family, weight=weight, slant=slant,
                                max_size=max_size)
        f = tkfont.Font(family=family, size=size, weight=weight, slant=slant)
        line_h = f.metrics("linespace")
        block_h = line_h * len(lines)
        cx, cy = px + pw // 2, py + ph // 2
        y = cy - block_h // 2 + line_h // 2
        fill = color or self._text_color
        for i, ln in enumerate(lines):
            if i == 0 and lead_text and lead_color and ln.startswith(lead_text):
                rest = ln[len(lead_text):]
                lead_w, rest_w = f.measure(lead_text), f.measure(rest)
                x0 = cx - (lead_w + rest_w) // 2
                c.create_text(x0, y, text=lead_text, fill=lead_color, font=f, anchor="w")
                c.create_text(x0 + lead_w, y, text=rest, fill=fill, font=f, anchor="w")
            else:
                c.create_text(cx, y, text=ln, fill=fill, font=f, anchor="center")
            y += line_h

    def _draw_text_legacy(self, c, w, h):
        """Pre-box-mode rendering: autofit/fixed main text, centered, with a
        secondary caption positioned above/below it. Still used by the timer
        countdown and hymn text slides, neither of which use a resizable box."""
        import tkinter.font as tkfont
        main = getattr(self, "_main_text", "")
        secondary = getattr(self, "_secondary", "")
        sec_pos = getattr(self, "_secondary_pos", "top")
        autofit = getattr(self, "_autofit", True)
        fixed = getattr(self, "_fixed_font", None)
        family = getattr(self, "_font_family", "Helvetica") or "Helvetica"
        sec_scale = getattr(self, "_secondary_scale", 0.045)

        max_w = int(w * 0.86)
        sec_size = max(14, int(h * sec_scale))
        sec_h = (sec_size + 24) if secondary else 0
        avail_h = int(h * 0.80) - sec_h

        if fixed:
            size = fixed
            lines = _wrap(main, tkfont.Font(family=family, size=size, weight="bold"), max_w)
        elif autofit and main:
            size, lines = _fit_text(main, max_w, avail_h, tkfont, family=family)
        else:
            size = getattr(self, "_main_font_px", 80)
            lines = _wrap(main, tkfont.Font(family=family, size=size, weight="bold"), max_w)

        f = tkfont.Font(family=family, size=size, weight="bold")
        line_h = f.metrics("linespace")
        block_h = line_h * len(lines)

        cy = h // 2
        if secondary and sec_pos == "top":
            main_cy = cy + sec_h // 2
            self._sec_y = main_cy - block_h // 2 - sec_size
        elif secondary and sec_pos == "bottom":
            main_cy = cy - sec_h // 2
            self._sec_y = main_cy + block_h // 2 + sec_size
        else:
            main_cy = cy
            self._sec_y = None

        y = main_cy - block_h // 2 + line_h // 2
        for ln in lines:
            c.create_text(w // 2, y, text=ln, fill=self._text_color, font=f, anchor="center")
            y += line_h

    def _draw_secondary_legacy(self, c, w, h):
        import tkinter.font as tkfont
        secondary = getattr(self, "_secondary", "")
        sec_y = getattr(self, "_sec_y", None)
        if sec_y is None:
            return
        family = getattr(self, "_ref_font_family", None) or getattr(self, "_font_family", "Helvetica")
        sec_scale = getattr(self, "_secondary_scale", 0.045)
        sec_size = max(14, int(h * sec_scale))
        sec_bold = getattr(self, "_secondary_bold", False)
        sec_italic = getattr(self, "_secondary_italic", False)
        sf = tkfont.Font(family=family, size=sec_size,
                         weight=("bold" if sec_bold else "normal"),
                         slant=("italic" if sec_italic else "roman"))
        fill = getattr(self, "_secondary_color", None) or self._text_color
        c.create_text(w // 2, sec_y, text=secondary, fill=fill,
                      font=sf, anchor="center")

    def _draw_table(self, c, w, h):
        import tkinter.font as tkfont
        rows = getattr(self, "_table_rows", [])
        if not rows:
            return
        family = getattr(self, "_font_family", "Helvetica") or "Helvetica"
        max_w = int(w * 0.86)
        max_h = int(h * 0.80)
        # Name is bold, motivo is italic (not bold) — mirrors the single
        # prayer-request projection's styling.
        size, name_w, gap = _fit_table(rows, max_w, max_h, tkfont, family=family)
        name_font = tkfont.Font(family=family, size=size, weight="bold")
        reason_font = tkfont.Font(family=family, size=size, slant="italic")
        line_h = max(name_font.metrics("linespace"), reason_font.metrics("linespace"))
        total_h = line_h * len(rows)
        reason_w = max((reason_font.measure(r) for _n, r, _c in rows if r), default=0)
        table_w = name_w + (gap if reason_w else 0) + reason_w

        x0 = w // 2 - table_w // 2
        y = h // 2 - total_h // 2 + line_h // 2
        for name, reason, reason_color in rows:
            c.create_text(x0, y, text=name, fill=self._text_color, font=name_font, anchor="w")
            if reason:
                c.create_text(x0 + name_w + gap, y, text=reason, fill=(reason_color or self._text_color),
                              font=reason_font, anchor="w")
            y += line_h


def _fit_cover(img, w, h):
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh))
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _fit_contain(img, w, h):
    iw, ih = img.size
    scale = min(w / iw, h / ih)
    return img.resize((max(1, int(iw * scale)), max(1, int(ih * scale))))


def _wrap(text, font, max_w):
    """Wrap text into lines that fit max_w pixels, honoring explicit newlines."""
    lines = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        words = para.split(" ")
        cur = ""
        for word in words:
            trial = (cur + " " + word).strip()
            if font.measure(trial) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
    return lines


def _fit_text(text, max_w, max_h, tkfont, family="Helvetica", weight="bold", slant="roman",
              max_size=None):
    """Binary-search the largest font size (given weight/slant) whose wrapped
    text fits max_w×max_h. `max_size`, if given, caps the search from above —
    used to keep a manually-chosen maximum even when the box itself is large
    (e.g. a short Bible reference in a wide box would otherwise autofit to a
    huge font)."""
    lo, hi = 10, 400
    if max_size:
        hi = min(hi, int(max_size))
        lo = min(lo, hi)
    best = lo
    best_lines = [text]
    while lo <= hi:
        mid = (lo + hi) // 2
        f = tkfont.Font(family=family, size=mid, weight=weight, slant=slant)
        lines = _wrap(text, f, max_w)
        line_h = f.metrics("linespace")
        total_h = line_h * len(lines)
        widest = max((f.measure(ln) for ln in lines), default=0)
        if total_h <= max_h and widest <= max_w:
            best, best_lines = mid, lines
            lo = mid + 1
        else:
            hi = mid - 1
    return best, best_lines


def _fit_table(rows, max_w, max_h, tkfont, family="Helvetica"):
    """Binary-search the largest font size where a two-column (name bold,
    motivo italic) table — one row per line, no wrapping — fits max_w×max_h.
    Width/height are strictly monotonic in font size here (no wrapping), so
    binary search is safe."""
    lo, hi, best = 12, 200, 12
    best_name_w, best_gap = 0, 30
    while lo <= hi:
        mid = (lo + hi) // 2
        nf = tkfont.Font(family=family, size=mid, weight="bold")
        rf = tkfont.Font(family=family, size=mid, slant="italic")
        name_w = max((nf.measure(n) for n, _r, _c in rows), default=0)
        reason_w = max((rf.measure(r) for _n, r, _c in rows if r), default=0)
        gap = max(30, mid)
        line_h = max(nf.metrics("linespace"), rf.metrics("linespace"))
        total_h = line_h * len(rows)
        total_w = name_w + (gap if reason_w else 0) + reason_w
        if total_w <= max_w and total_h <= max_h:
            best, best_name_w, best_gap = mid, name_w, gap
            lo = mid + 1
        else:
            hi = mid - 1
    return best, best_name_w, best_gap

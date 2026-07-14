# Handoff — Programma Servizio (SDA church service manager)

> Generated on 2026-06-30 (evening) — resume in a new Claude Code session.
> Working language with the user: **Italian**. Code/comments mostly Italian. This file is English.

---

## 🎯 Goal

Desktop app (Mac + Windows) to run a full Seventh-day Adventist weekly service from one control panel.
The operator sits at the back of the hall, prepares the program the same morning, and during the
service projects hymns, Bible verses, presentations (PDF/PPTX), videos, a break countdown timer,
background music, a bell, and an offering QR — all onto a **second screen** (iPad via Sidecar now;
in church will be a normal TV monitor).

"Done" = the operator never has to touch the projected screen; everything (incl. slide advance,
video transport, audio) is controlled from the app, and projection looks professional.

Packaging (PyInstaller .app + Windows .exe) comes **last**, after all features are stable.

---

## 📍 Current State

This session focused entirely on **left-panel UI polish** (section headers + slot/card rows in the
scaletta list). That work is finished and user-approved. A new round of work was scoped via brain
dump at the end of the session (see Next Steps) but **not started yet**.

**Working (confirmed, this session and earlier):**
- Section headers in the scaletta panel: long names now wrap to multiple lines instead of truncating
  (`_auto_wrap_label` helper + grid layout in `_render_section`). Rename/delete (✎✕) controls
  properly show on hover and hide on mouse-leave (fixed via `_maybe_hide` rewrite using
  `winfo_containing` + ancestor walk, replacing an unreliable rectangle-bounds check).
- Slot rows (Inno, Versetto, QR Offerta, Timer, Lezione, etc.) redesigned as a 2-zone "card":
  top bar with projected-indicator dot (●/○) + type label (left-aligned, dot first) + ✎✕ on hover,
  a separator line, then the full value text wrapping to multiple lines and reaching the full card
  width. Matches a mockup screenshot the user approved ("è perfetto"). See `_render_slot_row` in
  `ui/app.py` for the full implementation.
- Top-left corner of slot cards is properly rounded now (removed an invisible 1×1 placed drag-handle
  widget that was breaking `corner_radius` clipping; drag is now bound directly to the `top`/`body`
  container frame instead).
- Removed the green background that was applied to "lezione" slots (`LESSON_BG` branch deleted) —
  user didn't want/expect it.
- Drag-and-drop of files into slots (tkinterdnd2)
- In-app video projection with frames on ProjectionWindow canvas — **but see new bug below, video
  projection currently shows a black screen, needs investigation.**
- PPTX rendered via Keynote AppleScript → PNG cache → slides projected as images — **user now wants
  this whole approach replaced, see Next Steps #5.**
- Live slide counter pill, Right/Left arrow slide advance, resizable panels (see caveat below),
  cursor fixes, picker banner, Azzera scaletta button, Esc-to-close projection, cancel download,
  right panel contextual cards, black screen mode.

**Not working / known bugs (reported by user this session, not yet investigated):**
1. **Collapsed section drag bug**: if a section is collapsed (chiuso/ritirato — only the header
   visible, slots hidden), and the user drags it to reorder, ALL sections expand back open during/after
   the drag. Should stay collapsed. Likely the drag/reorder code calls something that re-renders
   sections with a reset "expanded" state instead of preserving the per-section expand flag.
2. **Panel resize doesn't reflow proportionally**: dragging the left/center divider does resize, but
   it leaves "strisce" (empty strips/bands) on the sides instead of having the center content widen
   or narrow proportionally to fill the new panel width. Needs the inner content (not just the outer
   frame) to recompute its layout on resize.
3. **Video projection shows black screen**: clicking "Proietta video" results in a black screen on the
   projection window, nothing renders. Not yet diagnosed — could be a regression from prior session's
   video work, or environment-specific (file format, codec, frame conversion). Needs a fresh repro.

---

## 📁 Relevant Files

| File | Role / Status |
|------|--------------|
| `main.py` | Entry point — unchanged |
| `ui/app.py` | **~2800+ lines.** All UI + logic. This session: `_render_section`, `_render_slot_row`, `_maybe_hide`, new `_auto_wrap_label` helper. |
| `ui/projection.py` | ProjectionWindow — `on_close`, `show_black()`, mode `"black"`. Video black-screen bug likely lives here or in `core/video.py`. |
| `core/render.py` | `render_pptx()` via Keynote AppleScript + PNG cache — **slated for removal/replacement, see Next Steps #5.** |
| `core/audio.py` | MusicPlayer + PlaylistChannel + AudioManager — unchanged |
| `core/video.py` | VideoPlayer (ffpyplayer) — unchanged this session, but implicated in the black-screen bug |
| `core/database.py` | PPTX scan + JSON cache — unchanged |
| `core/bible.py` | BibleLibrary over SQLite — unchanged |
| `core/schedule.py` | Schedule/Section/Slot data model — unchanged |
| `config/settings.json` | Live settings; `databases` points to `ppt` & `pptx nuovi` folders |
| `bibles/it_LND.db` | Italian Bible (La Nuova Diodati) |
| `file test/` | Test assets: `ppt/` (550 hymns), `pptx nuovi/` (15), PDF, PPTX, DOCX |

---

## ❌ Failed Attempts / Hard-won Knowledge

### Section header text truncation
- First attempt: shrink-to-fit font sizing (`_auto_shrink_label`). User rejected — preferred wrapping.
- **Fixed:** replaced with `_auto_wrap_label(lbl)` which binds `<Configure>` to update `wraplength`
  to the label's actual pixel width, with a cached-last-value guard to prevent infinite reflow loops.

### Infinite `<Configure>` loop freezing the app
- Wraplength-update callbacks without a "did the width actually change" guard re-triggered themselves
  forever, freezing the whole Tk app ("rimane bloccato").
- **Fixed:** always check `w != _last[0]` (or `_wc[0]`) before calling `.configure(wraplength=...)`.

### Section name wrapping mid-word too early
- The always-packed `sacts` (rename/delete) frame reserved ~52px even when buttons were invisible
  (`text=""`), squeezing the label's available width and causing "PREGHE / RA" style breaks.
- **Fixed:** converted `_render_section` header to a grid layout; `sacts` is only `grid()`-ed in on
  hover and `grid_remove()`-d on leave, so it doesn't reserve space when hidden.

### Rename/delete buttons stuck visible after mouse-out
- Old `_maybe_hide` did rectangle/bounds math against widget geometry — unreliable with CTkFrame's
  internal padding/layout, buttons stayed visible after the cursor left.
- **Fixed:** `_maybe_hide` now uses `winfo_containing(x, y)` and walks `.master` ancestry to check if
  the pointer is still inside the relevant wrapper widget.

### `place()` overlay for hover buttons
- Tried overlaying ✎✕ buttons via `place()` on top of other widgets with `fg_color="transparent"`.
- **Failed:** rendered as a solid white/gray opaque box instead of being transparent — abandoned in
  favor of grid-based show/hide (`grid()` / `grid_remove()`).

### Slot title text wraplength miscalculated
- Several iterations computed wraplength from the wrong source width (label's own pre-layout width,
  or a hardcoded offset subtraction), causing severe over-wrapping (text broke into many short lines
  with large empty space on the right).
- **Fixed:** dedicated `title_row` container frame; bind its own `<Configure>` width directly to the
  label's `wraplength` (no offset subtraction needed since `title_row` has no competing siblings).

### Drag-handle widget breaking rounded corners
- A 1×1 invisible "⠿" handle label placed via `.place(x=0, y=0)` sat inside the rounded-corner clip
  region of the parent `CTkFrame(corner_radius=6)` and broke the top-left corner rounding.
- **Fixed:** removed the placed handle entirely; drag-start is now bound directly to the `top`/`body`
  container frame's `<ButtonPress-1>`.

### (Carried over from earlier sessions — still valid, not re-tested this session)
- PowerPoint AppleScript PNG export fails due to `as` keyword collision → switched to Keynote.
  **NOTE: user now wants to drop Keynote entirely, see Next Steps #5 — this whole approach may
  become obsolete.**
- Keynote PPTX import timing race — poll-based wait + cache cleanup on failure.
- `winfo_width()` returns 1 before window realized on ProjectionWindow — cached size fallback.
- Video frame flicker — fixed via `itemconfigure` in-place update instead of delete+recreate.
  **NOTE: this fix may be unrelated to the new black-screen bug — re-verify from scratch.**
- `text_color="transparent"` crashes CTkButton — use `text=""` to hide instead.
- `CTkFrame.configure(width=nw)` doesn't trigger grid relayout — also needs
  `grid_columnconfigure(col, minsize=nw)` + `update_idletasks()`. **NOTE: per bug #2 above, this fix
  is incomplete — it resizes the frame but doesn't reflow inner content proportionally.**

---

## ✅ Working Solutions (keep these)

- **In-app modals** via transparent overlay frame (`_open_modal`) — never use `Toplevel` for editing popups.
- **DB cache** in `core/database.py` (filename → mtime in `config/db_cache/`).
- **PPTX cache** in `config/pptx_cache/{md5(abspath+mtime)[:20]}/` — Keynote re-export only on file change
  (likely to be replaced, see Next Steps #5).
- **Audio:** `music` = seekable single stream (pygame.mixer.music); pause music = Sound channel.
- **Bibles as bundled SQLite** + `tools/convert_bib.py` for new languages.
- **Accent-insensitive search** via `core/textutil.normalize`.
- **Projection auto-fit text** (binary-search font size) for verses/free text.
- **`_proj_pill_prefix`** attribute: set before projecting hymn/PDF so slide counter shows correct title.
- **`on_slide_change` callback** from ProjectionWindow → `_update_slide_label()` for real-time pill update.
- **`_dl_cancel` flag** checked in yt_dlp progress hook to abort downloads cleanly.
- **`_auto_wrap_label(lbl)` helper** (top of `ui/app.py`, near `_fmt_time`): binds a label so its
  `wraplength` tracks its real pixel width, with a loop guard. Reuse this pattern anywhere else text
  needs to wrap instead of truncate.
- **Grid-based hover show/hide** for contextual controls (`grid()` / `grid_remove()`), NOT `pack()`
  with conditional packing and NOT `place()` overlays — both caused bugs this session.

---

## 🔧 Dependencies & Setup

```bash
cd "/Users/edoardo/Desktop/programma inni"
python3 main.py
```

- Python 3.12 (python.org arm64 build). customtkinter **6.0.0**.
- All deps in `requirements.txt`: customtkinter, python-pptx, python-docx, pygame, mutagen, Pillow, qrcode, yt-dlp, imageio-ffmpeg, pymupdf, screeninfo, tkinterdnd2, certifi, ffpyplayer.
- Keynote currently required for PPTX→PNG rendering (macOS only) — **may be removed, see Next Steps #5.**
- **Close Python before editing** — user has 16GB RAM and multiple Python windows eat it fast.

---

## ➡️ Next Steps (priority order — from this session's brain dump)

1. **Fix collapsed-section drag bug**: dragging a collapsed section (header-only view) currently
   re-expands ALL sections. Find the reorder/drag-drop logic (likely in `_drag_start` /
   `_drag_motion` / `_drag_drop` or wherever `_render_sections()` gets called mid-drag) and make sure
   it doesn't reset each section's expand/collapse state. Preserve whatever flag tracks
   collapsed-vs-expanded per section through the whole drag operation.

2. **Fix proportional panel resize**: dragging the left/center divider resizes the outer frame but
   leaves empty "strisce" (stripes) at the sides instead of the inner content reflowing to fill the
   new width proportionally. Investigate the inner content's geometry manager (probably needs
   `weight=1` columns/rows recomputed, or the content frame itself needs a resize/redraw call
   triggered alongside the outer frame's `grid_columnconfigure(minsize=...)`).

3. **Redesign bottom-of-left-panel action buttons** — replace the current "Scalette salvate" button
   with several smaller, cleaner, distinct buttons:
   - "Salva scaletta" (save current schedule)
   - one to load/pick a previously saved schedule ("mettere una scaletta salvata")
   - "Aggiungi programma" (add a new section/program)
   - Also restyle "Azzera" (the clear/reset button) to match: smaller, cleaner, more elegant.
   - Overall goal: a more minimal, polished look for this whole bottom action area of the left panel
     — not "tutto più piccolo, più pulito" as an afterthought, this is the explicit design brief.
   (This folds in / supersedes the old "Point 11 — Scalette salvate discoverability" item.)

4. **Center panel**: improve layout/disposition (no specifics yet — user said "migliorare la
   disposizione", to be detailed together next time). Also expect "altri bug che scopriremo più avanti
   testando" (more bugs to be found via testing) — treat the center panel as needing a fresh pass.

5. **Drop Keynote dependency for hymn projection**: instead of converting PPTX → PNG via Keynote and
   projecting static images, the user wants hymns to launch **PowerPoint directly** (or Keynote, but
   driven live, not via an export step) and be controllable for slide advance from inside the app —
   either by controlling the external PowerPoint/Keynote app via AppleScript, or by some other means
   that avoids the current export-then-project-as-image pipeline. This is a meaningful architecture
   change to `core/render.py` and however slides are advanced today (`on_slide_change`, Right/Left
   arrow handling). Needs design discussion before implementing — figure out exactly how "controllare
   le slide da dentro il programma" should work (keyboard simulation to the external app? AppleScript
   `next slide`? something else?).

6. **In-app video picker + drag-and-drop**: when choosing a video to project, the user wants to pick
   it from inside the app's own UI (e.g. browse a YouTube-downloaded library) instead of having to
   open Finder and browse to a file. Should also support dragging a video file (e.g. from the Desktop)
   directly into the app to add it. Likely extends the existing `_pick_file_for` / drag-and-drop
   (tkinterdnd2) machinery already used elsewhere for slots.

7. **Fix video projection black screen**: see bug #3 in Current State above — needs a repro session
   and investigation in `ui/projection.py` / `core/video.py`.

8. **Point 6 — live center preview** (carried over, still blocked): user said they'd send a screenshot
   of the desired layout before this is implemented. Skip until provided.

9. **Point 16 — Packaging** (last, carried over): PyInstaller `.app` (Mac) + `.exe`/installer
   (Windows). Bundle `bibles/`, ffmpeg, tkdnd. Test on Windows. Handle the Keynote/PowerPoint
   dependency gracefully on non-Mac once #5 above is resolved.

---

## ⚠️ Gotchas / Traps

- **Close Python before editing code** — user has 16GB RAM. Always `pkill -f "python.*main"` before
  starting a work session and immediately after testing.
- **macOS case-insensitive FS**: `HANDOFF.md` and `handoff.md` are the same file.
- **Don't reintroduce `Toplevel`** for editing popups — use `_open_modal`.
- **`cursor="hand2"`** was replaced with `"pointinghand"` — don't revert.
- **`text_color="transparent"`** crashes CTkButton — use `text=""` to hide button labels.
- **Don't use `place()` for hover overlays** — caused an opaque white-box rendering bug this session;
  use grid `grid()`/`grid_remove()` instead.
- **Don't compute wraplength without a "value changed" guard** — causes infinite `<Configure>` loops
  that freeze the whole app.
- **`acts.pack(side="right")` must come BEFORE `lbl.pack()`** in slot rows where `pack()` is still
  used — otherwise `expand=True` on `lbl` takes all space and `acts` gets zero.
- **`on_close` re-entry guard**: `ProjectionWindow.close()` clears `_on_close = None` before calling
  it. Don't remove this.
- **Projection on single monitor** (no Sidecar): falls back to `-fullscreen True` on primary,
  covering the app window. Use `_stop_projection` / "Togli proiezione" to get back.
- **`_dl_cancel`** is an instance attribute initialized in `_view_media()` — use
  `getattr(self, "_dl_cancel", False)` if accessed before that view is visited.
- **Smoke tests** live in the scratchpad (session-specific path), NOT in the repo. Recreate if needed.
- **Reset `config/settings.json`** after smoke tests — tests dirty it.
- **No automated tests exist** for `ui/app.py` — verification method used is
  `python3 -c "import ast; ast.parse(open('ui/app.py').read()); print('OK')"` after every edit, plus
  manual launch + user screenshots. Keep using this pattern.

---

## 💬 Notes

- User is on macOS with 16GB RAM. iPad via Sidecar = secondary monitor now; in church will be a TV.
- The user values: professional visuals, minimalist/elegant UI (no colorful emojis, no clutter),
  everything controllable from the app — this applies strongly to the upcoming left-panel button
  cleanup (Next Steps #3) and the PowerPoint/Keynote rework (#5).
- Romanian & Spanish bibles to be added later via `tools/convert_bib.py`.
- Lesson JSON format still provisional.
- Offering QR image is configured once in Settings → Offerta.
- Right panel "⬛ Nero" button: shows `show_black()` on projection without stopping session. Previous
  mode is NOT remembered — resuming requires re-clicking the hymn/item. If "resume from black" is
  needed later, save previous mode before blanking and restore on second press.
- This session's left-panel redesign (section headers + slot cards) is considered DONE and approved
  by the user ("è perfetto") — don't revisit unless a new bug is reported.

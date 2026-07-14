# Handoff — Programma Servizio (SDA church service manager)

> Generated on 2026-07-01 (later same day as the previous handoff) — resume in a new Claude Code session.
> Working language with the user: **Italian**. Code/comments mostly Italian. This file is English.
> The user is on macOS but **everything built must also work identically on Windows** — keep this
> in mind for every change, not just ones that touch external processes.
> This session ran **autonomously** (no live screen access) — see "Testing methodology" below for
> what that means for verification confidence on each item.

---

## 🎯 Goal

Desktop app (Mac + Windows) to run a full Seventh-day Adventist weekly service from one control panel.
The operator sits at the back of the hall, prepares the program the same morning, and during the
service projects hymns, Bible verses, presentations (PDF/PPTX), videos, a break countdown timer,
background music, a bell, and an offering QR — all onto a **second screen** (iPad via Sidecar now;
in church will be a normal TV monitor).

"Done" = the operator never has to touch the projected screen; everything (incl. slide advance,
video transport, audio) is controlled from the app, and projection looks professional.

Packaging (PyInstaller .app + Windows .exe) comes **last, after everything else** — see Next Steps.

---

## 📍 Current State

This session closed out the 5 items left from the previous handoff (rename target, panel resize,
center panel header, PowerPoint-live projection replacing Keynote, in-app media library), found and
fixed a real bug in the PowerPoint feature the user hit immediately after "done", and made one small
follow-up UX fix to hymn navigation. Two previously-open items (old #6, #7) were explicitly cancelled
by the user this session; packaging (old #8) is deferred to the very end — **do not propose it again
until everything else is finished.**

**Working (this session, tested — see "Testing methodology" for what "tested" means here):**

- **Slot rename targets the title/value, not the type label.** `core/schedule.py`'s `Slot.label()`
  now checks `self.data.get("title")` first (a user-set custom override) before falling back to
  `display_name`/the type default. `ui/app.py`'s `_slot_value()` (line 762) applies that same
  override on top of `_derived_slot_value()` (line 776, the old logic renamed) — critically, a
  custom title does **not** change the `filled` flag, so a *named-but-still-empty* inno slot still
  opens the picker on click instead of being treated as assigned. `_rename_slot()` (line 1190) now
  writes to `slot.data["title"]` instead of `display_name`, dialog label changed to "Titolo:".
  8 unit checks pass (custom title shown, blank title ignored, filled-flag independence, roundtrip
  through `to_dict`/`from_dict`).

- **Panel resize — root cause found, not the same as previously suspected.** The three fixes from
  the *previous* session (deferred rebuild, `update_idletasks()` ordering, cold-start refresh) were
  real but insufficient — the actual bug was that **`_left_panel`/`_right_panel` only had
  `grid_propagate(False)`, never `pack_propagate(False)`.** Their children are `pack()`-managed, so
  without `pack_propagate(False)` the panel silently ignores `configure(width=…)` entirely and
  shrink-wraps to content — this is why dragging the divider looked like it "did nothing" a lot of
  the time, independent of the geometry-timing bugs found earlier. Fixed by adding
  `self._left_panel.pack_propagate(False)` / `self._right_panel.pack_propagate(False)` right after
  `grid_propagate(False)` in `_view_scaletta()`. Once that was in place, the heavy
  `_build_program_list()`/`_build_right_panel()` rebuild-on-release was no longer needed — the
  `CTkScrollableFrame` reflows live with **zero empty band** during the drag itself, so
  `_resize_left_end`/`_resize_right_end` (lines 1898/1906) were simplified to just
  `update_idletasks()` + immediately persist the new width to `config/settings.json` via `cfg.save()`
  (previously only saved on clean app exit). Also removed the confirmed-dead
  `outer._frame.columnconfigure(...)` try/except from `_resize_left`/`_resize_right` (documented as
  dead in the previous handoff; now actually deleted, not just noted). **Verified with real pixel
  measurements** (not just "does it look right"): resized left panel through 440/190/300/560/170 and
  right panel through 430/200/350, `winfo_width()` tracked the target within 1-2px every time, and
  the gap between the scrollable frame's canvas and its inner content frame was 0 in every case,
  including at cold start with a non-default saved width.

- **Center panel header redesigned.** New eyebrow row (colored dot matching `SLOT_COLORS` + type name
  in caps) above a larger auto-wrapping title, then a divider line, in `_render_center()` (line 1218).
  Empty-state (no slot selected) now shows an icon + two-line hint instead of one plain label.
  Renders without error for all 13 slot types in both empty and filled variants (scripted check).
  **⚠️ Not visually confirmed** — see Testing methodology. If the user reports it looks off, this is
  the first place to check with a real screenshot.

- **Keynote removed entirely; hymns/PPTX now project via a real, live-controlled PowerPoint show.**
  This was "old Next Step #4". `core/render.py` stripped down to just `render_pdf()` — all Keynote
  AppleScript export code, the PPTX PNG cache, and `can_render_as_slides()` are gone (PDFs still
  render in-app as before; nothing else used those PPTX functions, confirmed via grep before
  deleting). `core/projector.py` was rewritten:
  - `present_powerpoint(path)` — opens the file and starts PowerPoint's real slideshow
    (`run slide show slide show settings of active presentation` via AppleScript on macOS;
    `powerpnt.exe /s` on Windows). Returns `True`/`False`.
  - `powerpoint_next()` / `powerpoint_prev()` / `powerpoint_end()` — drive or stop the *running* show
    from the app (`go to next/previous slide` / `exit slide show` on the live `slide show view` via
    AppleScript on macOS; best-effort PowerPoint COM on Windows, silently no-ops without `pywin32`).
  - The old `open_presentation`/`project_hymn` API is gone; `open_file_external` is unchanged.
  In `ui/app.py`: `_detail_inno` no longer has an "Apri in PowerPoint" button — only **"Proietta"**
  and "Cambia inno" remain, per explicit user instruction. `_present_pptx(path, title="")`
  (line 3007) replaces the old `_project_pptx` — it closes any in-app `ProjectionWindow` first, calls
  `projector.present_powerpoint()`, and on success sets `self._proj_mode = "external"` and updates the
  status pill with a "(PowerPoint)" suffix. `_project_hymn()` now calls `_present_pptx()` when the
  hymn has a pptx path, falling back to in-app text slides only if it doesn't. `_slide_next()` /
  `_slide_prev()` check `self._proj_mode == "external"` first and route to
  `projector.powerpoint_next()`/`powerpoint_prev()` instead of the in-app `ProjectionWindow`; the
  `<Right>`/`<Left>` arrow-key bindings were extended to also fire in `"external"` mode.
  `_stop_projection()` calls `projector.powerpoint_end()` first when in external mode, before closing
  anything else — so "Togli proiezione" now actually ends the PowerPoint show, not just the app's own
  window.
  **Verified against the real, installed PowerPoint.sdef** (not guessed): dumped the actual scripting
  dictionary and confirmed `run slide show`, `go to next slide`, `go to previous slide`, and
  `exit slide show` all exist with the signatures used; all four generated AppleScript strings compile
  via `osacompile` (syntax + term resolution, without executing); and a live end-to-end run against a
  real hymn `.pptx` file actually started a slideshow window, advanced/rewound it, and ended it
  cleanly (`osascript` returncode 0 throughout, `slide show windows` count went 0→1→0). Any stray test
  presentations opened in the user's own already-running PowerPoint were closed again afterward
  without quitting the app itself.
  **⚠️ Not verified: which physical monitor the show appears on.** That depends entirely on
  PowerPoint's own "Set Up Show → Monitor" setting (which PowerPoint remembers per-machine) — the
  script launches the show correctly, but this session had no second monitor to confirm placement on.
  **The user must configure this once** in PowerPoint: *Slide Show tab → Set Up Slide Show → Monitor*
  → pick the secondary display, and decide whether "Use Presenter View" should be on or off.
  **First-run note for the user:** the very first click on "Proietta" may trigger a macOS system
  dialog — *"Python vuole controllare Microsoft PowerPoint"* — the user needs to click Allow/OK. This
  is expected OS behavior for AppleScript automation, not a bug.

- **Bug found and fixed after initially reporting this feature as "done": relative file paths hang
  PowerPoint.** The user reported "mi dà errore quando clicco proietta" immediately after the above.
  Root cause: the schedule stores hymn/PPTX paths **relative** to the app folder (e.g.
  `"file test/ppt/017 - Te Lodiamo, O Signor.pptx"`), but AppleScript's `open POSIX file "..."`
  requires an **absolute** path. With a relative path, PowerPoint doesn't error cleanly — it opens a
  native "file not found"-style dialog and hangs there, so the `osascript` call blocks until timeout
  (reproduced directly: `subprocess.TimeoutExpired` after 60s with the exact relative path from the
  live schedule). **Fixed** in `core/projector.py`'s `present_powerpoint()`: the very first thing it
  does now is `file_path = os.path.abspath(file_path)`. Re-verified with the same relative path from
  the real schedule: the generated AppleScript now contains the absolute path, and (separately) the
  absolute-path script was already proven to launch cleanly. **This is exactly the kind of bug that
  only shows up with real, previously-saved data** (relative paths came from how `_pick_file_for`/
  `_set_slot_file` and the hymn DB store paths, unrelated to anything touched this session) — worth
  remembering if any other feature reads `slot.data["path"]`/hymn paths and passes them to something
  path-sensitive outside Python (AppleScript, COM, a native dialog, etc.).

- **In-app media library for video/audio slots** ("old Next Step #5"). New in `ui/app.py`:
  `_VIDEO_EXTS`/`_AUDIO_EXTS` constants; `_media_library_files(exts)` (line 1548) scans
  `youtube_folder`, `background_music_folder`, and `~/Downloads`, dedupes by `os.path.realpath`, sorts
  newest-`mtime`-first, and only lists files that exist *right now* (so a file mid-transcode in the
  system temp dir structurally can't appear — this was the whole point of the original ask);
  `_open_media_library(slot, exts, title, browse_types)` (line 1579) is a modal listing those files
  with a "Scegli" button per row, plus a "Sfoglia sul computer…" fallback to the native picker.
  `_detail_video`'s "Scegli video" and `_detail_audio`'s "Scegli file audio" now open this library
  instead of going straight to the native file dialog. Also added `_register_drop(frame, slot)` to
  `_detail_audio`, which was missing before — audio slots didn't support drag-and-drop until now.
  Tested: newest-first ordering (with a controlled tmp-folder fixture), extension filtering (video vs
  audio lists don't cross-contaminate), modal opens without error, choosing a file assigns it to the
  slot correctly.

- **Follow-up UX fix (not from the original numbered list, came up during PowerPoint testing this
  session): clicking the sidebar "♪ Inni" icon no longer opens the hymn library directly.** The user
  wanted hymn browsing to only be reachable in the context of a slot to assign into — via "Scegli
  inno"/"Cambia inno" in the center panel (which calls `_start_picker`, unchanged). In `_build_ui()`,
  the "inni" nav button's command was changed to a new `_nav_inni_click()` method (line 477): if the
  app isn't already on Scaletta, it navigates there instead of to the library; if already on
  Scaletta, it's a no-op. Crucially, `_start_picker("inno", slot)` calls `self._nav("inni")` directly
  (bypassing the button's command entirely), so the actual assignment flow is completely unaffected —
  verified with 13 checks: clicking the icon from Bibbia/Media redirects to Scaletta (not Inni), while
  the full "Scegli inno" → picker banner → assign → cancel round-trip still works exactly as before.

- All previously-working features from earlier sessions (drag-and-drop file slots, collapsed-section
  drag fix, bottom-panel button redesign, video projection with AV1 auto-transcode-on-download,
  picker banner, Azzera, Esc-to-close projection, cancel download, right panel contextual cards, black
  screen mode) — unchanged, not re-tested this session except where noted above.

**Cancelled by the user this session (do not re-propose, do not implement):**
- Old Next Step #6 — auto-fix already-downloaded AV1 video files (only new downloads get
  auto-transcoded; existing files on disk are not retroactively checked). **Cancelled.**
- Old Next Step #7 — live center panel preview (was blocked on the user sending a screenshot of the
  desired layout; never arrived). **Cancelled.**

**Deferred to the very end (still valid, but don't bring it up until everything else is done):**
- Packaging (PyInstaller `.app` + Windows `.exe`) — see Next Steps, last item. **The user explicitly
  asked not to have this re-proposed in every summary — only mention it once everything else on the
  list is finished, or if the user asks directly.**

**Not working / known bugs (not investigated this session):**
- None newly reported beyond what's captured above.

---

## 📁 Relevant Files

| File | Role / Status |
|------|--------------|
| `main.py` | Entry point — unchanged |
| `ui/app.py` | **~3310 lines.** All UI + logic. This session: `_slot_value`/`_derived_slot_value` split (line 762/776), `_rename_slot` (1190) writes `data["title"]`, `_render_center` header redesign (1218), `_media_library_files`/`_open_media_library` (1548/1579), `_detail_video`/`_detail_audio` wired to the library, `_resize_left_end`/`_resize_right_end` simplified (1898/1906) + `pack_propagate(False)` added in `_view_scaletta`, `_detail_inno` lost its "Apri in PowerPoint" button, `_present_pptx` (3007) replaces `_project_pptx`, `_project_hymn`/`_slide_next`/`_slide_prev`/`_stop_projection` updated for `"external"` proj mode, `_nav_inni_click` (477) added. |
| `core/schedule.py` | `Slot.label()` now honors a custom `data["title"]` override before `display_name`/type default. Everything else unchanged. |
| `core/projector.py` | **Rewritten this session.** No longer opens/exports via Keynote. `present_powerpoint()`, `powerpoint_next()`, `powerpoint_prev()`, `powerpoint_end()` drive a real PowerPoint slideshow (AppleScript on macOS, best-effort COM on Windows). `open_file_external` unchanged. Old `open_presentation`/`project_hymn` removed. |
| `core/render.py` | **Stripped down** to just `render_pdf()`. All Keynote/PPTX-export code removed (was ~100 lines, now 24). |
| `ui/projection.py` | ProjectionWindow — unchanged this session. Still used for in-app slides/verses/timer/video/black screen; no longer used for PPTX (that's now external PowerPoint). |
| `core/video.py` | VideoPlayer + AV1 codec probe/transcode — unchanged this session. |
| `core/audio.py` | MusicPlayer + PlaylistChannel + AudioManager — unchanged |
| `core/database.py` | PPTX scan + JSON cache — unchanged. **Note:** hymn paths here are stored **relative** to the app folder (root cause of this session's PowerPoint bug) — keep this in mind for any new feature that hands a `slot.data["path"]`/hymn `file_path` to something outside Python. |
| `core/bible.py` | BibleLibrary over SQLite — unchanged |
| `config/settings.json` | Live settings. `left_panel_width`/`right_panel_width` were dirtied to many test values during resize verification; **confirmed restored to the user's real values (302/412)** at the end of this session. |
| `bibles/it_LND.db` | Italian Bible (La Nuova Diodati) |
| `file test/` | Test assets: `ppt/` (550 hymns), `pptx nuovi/` (15), PDF, PPTX, DOCX — the real PowerPoint scripting was tested against files in here. |

---

## ❌ Failed Attempts / Hard-won Knowledge

### Panel resize: the previous session's three fixes were real but not the actual root cause
- The deferred-rebuild, `update_idletasks()`-ordering, and cold-start-refresh fixes from the previous
  session were all genuine bugs and are still correct/in place. But none of them mattered until
  `pack_propagate(False)` was added — without it, `configure(width=…)` on the panel is a no-op, full
  stop, regardless of any rebuild timing. **Lesson: when a widget's `configure(width=...)` doesn't
  seem to stick no matter what triggers the rebuild, check `pack_propagate`/`grid_propagate` on that
  widget *before* chasing timing/ordering bugs in the code that calls `configure`.** This would have
  saved the entire previous session's resize-debugging effort if checked first.

### Relative paths + AppleScript = silent hang, not a clean error
- `open POSIX file "relative/path.pptx"` in AppleScript does not raise a scripting error — PowerPoint
  itself opens a native "can't find the file" dialog and blocks, so from the calling Python process
  it just looks like `osascript` hanging until timeout (confirmed: `subprocess.TimeoutExpired` at
  60s). No stderr, no returncode — you have to actually wait out the timeout or inspect PowerPoint's
  window state to notice anything is wrong. **Lesson: always `os.path.abspath()` any path handed to
  AppleScript's `POSIX file`, even if the path looks like it "should" be relative-to-cwd — the calling
  app's cwd is not guaranteed to be what you expect once it's driving another application via IPC.**

### (Carried over from earlier sessions — still valid, not re-tested this session)
- PowerPoint AppleScript PNG export fails due to `as` keyword collision — **moot now**, Keynote/export
  approach is gone entirely; hymns launch PowerPoint's real slideshow instead.
- Keynote PPTX import timing race — **moot now**, same reason.
- `winfo_width()` returns 1 before window realized on ProjectionWindow — cached size fallback still
  in place, unaffected by this session's changes.
- Video frame flicker — fixed via `itemconfigure` in-place update instead of delete+recreate, still
  in place.
- `text_color="transparent"` crashes CTkButton — use `text=""` to hide instead. Still true.
- `CTkFrame.configure(width=nw)` doesn't trigger grid relayout on its own — needs
  `grid_columnconfigure(col, minsize=nw)` **and** (this session's finding) `pack_propagate(False)` if
  the frame's own children are `pack()`-managed, **and** `update_idletasks()` called after any code
  that reads `winfo_width()`, not just after the configure call.

---

## ✅ Working Solutions (keep these)

- **In-app modals** via transparent overlay frame (`_open_modal`) — never use `Toplevel` for editing
  popups. Reused for the new media library modal this session, worked fine at a larger size (600×520).
- **DB cache** in `core/database.py` (filename → mtime in `config/db_cache/`).
- **Audio:** `music` = seekable single stream (pygame.mixer.music); pause music = Sound channel.
- **Bibles as bundled SQLite** + `tools/convert_bib.py` for new languages.
- **Accent-insensitive search** via `core/textutil.normalize`.
- **Projection auto-fit text** (binary-search font size) for verses/free text.
- **`_proj_pill_prefix`** attribute: set before projecting hymn/PDF so slide counter shows correct
  title. Not used for the new `"external"` PowerPoint mode — that mode sets the pill text directly.
- **`self._proj_mode` as a string tag** (`"slides"`, `"verse"`, `"video"`, `"timer"`, `"cover"`, and
  now `"external"`) — the cleanest way found so far to make shared controls (arrow keys, stop button)
  branch correctly per projection type without a bigger state-machine refactor. Reuse this pattern for
  any new projection mode (e.g. the "prayer requests" / "announcement slide" features noted below).
- **`_dl_cancel` flag** checked in yt_dlp progress hook to abort downloads cleanly.
- **`_auto_wrap_label(lbl)` helper** — binds a label so its `wraplength` tracks its real pixel width,
  with a loop guard. Reused this session for the new center-panel title.
- **Grid-based hover show/hide** for contextual controls (`grid()`/`grid_remove()`), NOT `pack()` with
  conditional packing and NOT `place()` overlays.
- **Per-section/per-instance UI-only state in a dict on `self`, keyed by stable id** — the right
  pattern any time a widget's visual/interaction state needs to survive a `destroy()`+rebuild cycle,
  but should NOT be persisted to the schedule data model.
- **A custom user override stored in `slot.data[...]` (not `display_name`) that only changes the
  *displayed text*, never the `filled`/assigned status** — the pattern used this session for the
  rename fix (`data["title"]`). Reuse this shape for any future "let the user relabel something
  without touching whether it's actually configured" need.
- **`pack_propagate(False)` on any fixed-width `CTkFrame`/`tkinter.Frame` whose children are
  `pack()`-managed** — `grid_propagate(False)` alone does nothing for pack-managed children. Check
  both whenever a frame's configured width isn't sticking.
- **Verifying an AppleScript against the real installed app's `.sdef` before writing/trusting it**:
  `sdef "/Applications/X.app" 2>/dev/null` (or reading the `.sdef` XML directly under
  `Contents/Resources/`) gives the actual command names, parameter types, and result types — far more
  reliable than guessing AppleScript syntax from memory. `osacompile -o /dev/null -e '...'` then
  compiles a script (checking syntax **and** term resolution against the target app) without
  executing it — a fast, side-effect-free way to validate AppleScript before running it for real.
  Reuse both for any future AppleScript work (Windows COM equivalent: check the app's type library /
  `win32com.client.gencache` if it ever needs the same rigor).
- **`probe_video_codec()` / `needs_transcode()` / `transcode_to_h264()`** in `core/video.py` — unchanged
  this session, still the pattern to reuse for any "is this media file actually playable" check.
- **Windows console-flash guard**: `creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0`.
  Reused in the new `core/projector.py`.

---

## 🔧 Dependencies & Setup

```bash
cd "/Users/edoardo/Desktop/programma inni"
python3 main.py
```

- Python 3.12 (python.org arm64 build). customtkinter **6.0.0**.
- All deps in `requirements.txt`: customtkinter, python-pptx, python-docx, pygame, mutagen, Pillow,
  qrcode, yt-dlp, imageio-ffmpeg, pymupdf, screeninfo, tkinterdnd2, certifi, ffpyplayer.
- **Keynote is no longer used or required** — this session's biggest dependency change. PPTX/hymn
  projection now requires **Microsoft PowerPoint** to be installed (already was, for editing) and,
  on macOS, the user granting the Apple Events automation permission on first use (see "first-run
  note" above).
- **Close Python before editing** — user has 16GB RAM and multiple Python windows eat it fast. Verify
  with `ps aux | grep main.py` after `pkill`, don't assume it worked (this bit the previous session
  more than once).
- **Everything must work identically on Windows** — the user has stated this repeatedly. Before
  adding any new subprocess/external-tool call, OS-specific path handling, or platform-only library,
  check `core/projector.py`'s `sys.platform` branching pattern (now covers Mac AppleScript / Windows
  COM+`/s` flag / Linux LibreOffice fallback) and follow it. **The Windows PowerPoint-control path
  (COM via `pywin32`) has not been tested at all this session** — it's written defensively (silently
  returns `False`/no-ops if `pywin32` isn't installed) but a Windows test pass would be valuable before
  relying on it in front of the actual congregation.

---

## ➡️ Next Steps (priority order)

### New feature requests from this session's brain-dump (not started — design + implement from scratch)

These came directly from the user, described as things to add to the app. **Read the architectural
note (item 5 below) before starting on 1–4** — it changes how they should be built.

1. **Comandi rapidi di proiezione**: schermo nero, mostra logo, freeze (congela l'immagine
   proiettata corrente). Must be available both as **keyboard shortcuts** and as **visible buttons in
   the UI**. Must act **instantly** on the video output **without changing the selected element in the
   scaletta** (i.e. these are overlay/transport actions, not navigation — the underlying slot
   selection and center-panel state should be untouched when one of these fires). `show_black()` /
   `_proj_black()` already exist as a partial building block (right panel "⬛ Nero" button) but note
   the existing caveat: it doesn't remember the previous mode, so resuming after black currently
   requires re-clicking the item — that gap likely needs closing for "freeze" to make sense as a
   distinct action from black (freeze implies you can un-freeze back to where you were; black implies
   you deliberately blank until you pick something new). "Mostra logo" needs a logo image configured
   somewhere (Settings, similar to the existing offering-image pattern) — doesn't seem to exist yet,
   check `core/settings.py`/`_view_settings` before assuming it does.

2. **Slide annuncio al volo**: a quick text editor to compose and immediately project an announcement
   slide, with no file prep — background/logo consistent with the rest of the projection look (reuse
   `verse_bg_color`/`verse_bg_image`/`verse_text_color` settings or a dedicated new set, TBD with the
   user). The existing `_detail_testo`/`_project_text_block` free-text slot is the closest existing
   analog — worth reviewing whether this is a variant of that (a global always-available action, not
   tied to a schedule slot) or a genuinely new codepath.

3. **Richieste di preghiera**: a persistent (survives across sessions — needs its own storage, not
   just in-memory) section to enter names/reasons, with the ability to project them as a slide, either
   one at a time or as a full list. No existing analog in the codebase — this is new data (a new
   settings key or its own small JSON store) plus new UI plus new projection rendering.

4. **Controllo remoto da telefono/tablet**: a local-network web interface mirroring the main
   commands — scaletta forward/back, the new quick commands (nero/logo/freeze), and start/stop for the
   existing timer. This is the biggest architectural addition — likely a small local HTTP server (e.g.
   `http.server`/Flask-equivalent, TBD) run alongside the Tk app, exposing a minimal API the phone
   browser hits. Needs a design pass with the user before implementation: what to expose, auth/access
   (anyone on the same Wi-Fi could otherwise drive the projector), and how it talks to the running Tk
   app (likely needs to run on a background thread and marshal calls back onto the Tk main thread via
   `self.after(...)`, mirroring how `_download_youtube`'s background thread already does this via
   `_safe_after`).

5. **Architectural note from the user — read this before starting 1–4**: define a single
   **"elemento proiettabile"** (projectable element) abstraction — hymn, verse, PPTX, PDF, video,
   audio, announcement, prayer request — so that both the scaletta and the new remote control can
   operate on all of them uniformly, instead of each new type growing its own bespoke
   `_project_X()`/`_detail_X()` pair the way slot types do today. **This is a design decision to make
   before building 1–4 individually** — retrofitting a shared abstraction after four more ad-hoc
   projectable types exist would cost much more than designing it in from the start. Needs a real
   design conversation with the user (what the abstraction's interface looks like, whether existing
   slot types get migrated onto it or only new ones use it) rather than a unilateral implementation
   choice — flag this explicitly next session before writing code.

### Carried over from before this session

6. **Re-test the PowerPoint monitor placement on the real church/Sidecar setup.** The AppleScript is
   proven correct in isolation; whether the show lands on the secondary display depends on
   PowerPoint's own remembered "Set Up Slide Show → Monitor" setting. Walk the user through setting
   this once, then confirm "Proietta" on a real hymn actually appears on the second screen and
   PagSù/PagGiù/"Togli proiezione" control it correctly from the app.

7. **Windows-test the new PowerPoint control path.** `powerpoint_next/_prev/_end` on Windows go
   through `pywin32`'s `GetActiveObject("PowerPoint.Application")` and silently no-op if that's not
   available — this has never been run on an actual Windows machine. Also re-confirm `powerpnt.exe /s`
   launches correctly there.

8. **Visually confirm the center-panel header redesign** (see Current State) with a real screenshot —
   this session could only confirm it renders without error, not that it looks right.

9. **Packaging** (last, only after everything above — do not re-propose this each session, only
   mention when everything else is done or if the user asks directly): PyInstaller `.app` (Mac) +
   `.exe`/installer (Windows). Bundle `bibles/`, ffmpeg, tkdnd. Test on Windows. **Now also needs to
   handle Microsoft PowerPoint being a hard external dependency** (no more optional Keynote fallback)
   — decide what the app should do/show if PowerPoint isn't installed on the target machine. Also
   still needs `imageio_ffmpeg`'s binary verified inside a frozen Windows build (carried over,
   untested in a frozen build).

---

## ⚠️ Gotchas / Traps

- **Everything must work identically on Windows** — see Dependencies & Setup above.
- **Close Python before editing code**; verify with `ps aux | grep main.py` after `pkill`, don't
  assume it worked.
- **macOS case-insensitive FS**: `HANDOFF.md` and `handoff.md` are the same file.
- **Don't reintroduce `Toplevel`** for editing popups — use `_open_modal`.
- **`cursor="hand2"`** was replaced with `"pointinghand"` — don't revert.
- **`text_color="transparent"`** crashes CTkButton — use `text=""` to hide button labels.
- **Don't use `place()` for hover overlays** — caused an opaque white-box rendering bug; use grid
  `grid()`/`grid_remove()` instead.
- **Don't compute wraplength without a "value changed" guard** — causes infinite `<Configure>` loops
  that freeze the whole app.
- **`on_close` re-entry guard**: `ProjectionWindow.close()` clears `_on_close = None` before calling
  it. Don't remove this.
- **Projection on single monitor** (no Sidecar): falls back to `-fullscreen True` on primary. Use
  `_stop_projection` to get back — now also ends any external PowerPoint show, see Current State.
- **Hymn/PPTX paths in the schedule and hymn DB are stored *relative* to the app folder.** Anything
  that hands one of these to a path-sensitive external system (AppleScript, COM, a native OS dialog,
  another process's cwd) must `os.path.abspath()` it first — this was the exact bug found and fixed
  this session in `core/projector.py`. If a future feature reads `slot.data["path"]` or a hymn's
  `file_path` and passes it somewhere outside plain Python file I/O, check this first.
- **`pack_propagate(False)` vs `grid_propagate(False)`**: they are independent and only affect the
  matching geometry manager. A frame with `pack()`-managed children needs `pack_propagate(False)` for
  a configured `width=` to stick — `grid_propagate(False)` alone silently does nothing for it. This
  was the real root cause of the panel-resize bug this session; check this first for any future
  "configure(width=...) isn't sticking" report.
- **`self._proj_mode` now includes `"external"`** (PowerPoint driving its own fullscreen window,
  separate from the app's `ProjectionWindow`) — any code that branches on `_proj_mode` for
  "is something currently projected" / "should arrow keys do something" needs to account for this
  value, not just `"slides"`/`"verse"`/`"video"`/`"timer"`/`"cover"`.
- **No automated tests exist** for `ui/app.py`. Verification this session used: (a)
  `python3 -c "import ast; ast.parse(...)"` after every edit, (b) headless Tk instantiation
  (`from ui.app import App; App(); app.update_idletasks()`) with scripted checks against real widget
  geometry/state — this works fine without a display and was the primary verification method this
  session since screen access wasn't available, (c) for the PowerPoint feature specifically:
  `sdef`/reading the real `.sdef` XML to get exact command signatures, `osacompile -o /dev/null -e
  '...'` to compile-check AppleScript without running it, and real `subprocess`/`osascript` calls
  against the actually-installed PowerPoint (with cleanup of any stray opened presentations
  afterward, careful never to quit an app the user already had open). **Reuse all of these for
  similar work** — they're faster and more reliable than screenshots for logic/state verification, but
  note the next point.
- **This session had no live screen/computer-use access** (autonomous run, no user present to approve
  the permission dialog; macOS also blocks Python's own `screencapture` under normal privacy
  settings). This means **anything purely visual — the center-panel header's actual on-screen look,
  and PowerPoint's presentation actually appearing on the correct physical monitor — could not be
  confirmed by looking at it**, only by confirming the code runs without error and produces the
  expected internal state. Flag this explicitly to the user for those two items; don't assume "tested"
  means "seen" for this session's work.
- **Reset `config/settings.json`** after smoke tests — resize tests in particular dirty
  `left_panel_width`/`right_panel_width` on every run now (they're saved immediately on drag-release,
  not just on clean exit, since this session's simplification). **Confirmed restored to 302/412**
  (the user's real values) at the end of this session — re-check this if a future session's tests
  leave different values and it's not obviously the user's own real usage.

---

## 💬 Notes

- User is on macOS with 16GB RAM. iPad via Sidecar = secondary monitor now; in church will be a TV.
- **Windows parity is a hard requirement** — re-confirm this mindset every session.
- The user values: professional visuals, minimalist/elegant UI (no colorful emojis, no clutter),
  everything controllable from the app, the operator never touching the projected screen.
- Romanian & Spanish bibles to be added later via `tools/convert_bib.py`.
- Lesson JSON format still provisional.
- Offering QR image is configured once in Settings → Offerta.
- The user's test schedule (config/settings.json) still has hymn/video/presentation slots pointing
  into `file test/` and `~/Downloads` — useful as ready-made real test data for the new PowerPoint
  and media-library features if either needs revisiting (both already exercised against these files
  this session).
- **Cancelled features (old #6, #7) should not be re-suggested** — the user was explicit about this.
  If the AV1-already-downloaded-files gap or a center-panel live preview come up again, treat it as a
  *new* request, not a resumption of the old one.
- **Packaging (old #8, now Next Step #9) should not be mentioned in summaries until everything else is
  done**, per explicit user instruction — only bring it up once the rest of the list (including the
  four new brain-dumped features) is finished, or if the user asks about it directly.

# Handoff — Gestione programma SDARM (ex "Programma Servizio", SDA church service manager)

> Generated on 2026-07-07 — resume in a new Claude Code session.
> Working language with the user: **Italian**. Code/comments in English. This file is English.
> The user is on macOS but **everything built must also work identically on Windows**.

---

## 🎯 Goal

A Python/customtkinter desktop app that runs a full Seventh-day Adventist church
service from one control panel, projecting to a second screen (hymns, Bible
verses, lesson questions, timers, prayer requests, media, images, offering
slide...). The app is mature and in daily real use by the user.

---

## 📍 Current State

**Round 8 (latest): Windows build finally succeeded — real crash-on-launch
bug found and fixed: `cursor="pointinghand"` is macOS-only.** After round 7's
fixes the Windows build completed and the .exe launched, but crashed
immediately: `_tkinter.TclError: bad cursor spec "pointinghand"` in
`App._build_ui` (ui/app.py, the very first `_circle()` call in the nav
rail). Root cause: **`"pointinghand"` is a cursor NAME macOS's Tk/Aqua port
adds on top of the standard portable cursor set — it does not exist on
Windows or X11 Tk at all**, so any widget configured with it raises
TclError the instant it's created. This is a real, should-have-been-caught
cross-platform bug from the original review (missed because Tk only
validates a cursor spec at set-time, and every prior verification ran on
macOS, where it's valid). Found and fixed by `grep -rn 'cursor=' ui/`: **11
occurrences, all in `ui/app.py`**, all replaced with `"hand2"` — one of
Tk's standard portable cursor names (works identically on macOS, Windows,
and Linux). The other custom cursor names already in use (`sb_h_double_arrow`
for resize dividers, `fleur` for drag handles, `arrow`) were checked too and
are already portable — no changes needed there.
Verified: headless smoke test on macOS after the fix (all 6 views navigate
without error), macOS package rebuilt. **Not yet re-verified on the user's
Windows PC** — ask them to re-run `build_windows.bat` (which will re-pull
the fixed source automatically if they're running from a synced project
copy) or otherwise get this fix onto the Windows machine and relaunch.

**Round 7: the round-5 download link itself was wrong — Python 3.12
no longer ships a Windows installer at all.** The user reported the
python.org release page for 3.12.3 now redirects/shows "replaced by
3.12.13". Checked live via browser: python.org confirms **Python 3.12 has
been in "security fixes only" mode since 3.12.10 — source-only, no Windows
installer at all** (3.12.13, March 2026, explicitly says "No installers").
Checked python.org's Windows downloads index: **only 3.13.x and 3.14.x
currently ship Windows installers** (3.13.14 as of 2026-07). Checked
PyPI directly for pygame 2.6.1's file list: it has `cp313-win_amd64` wheels
(confirms 3.13 works) but no `cp314` wheel at all (confirms round 5's
finding) and no Windows-ARM64-tagged wheel of any kind (reinforces why x64,
not ARM64, is the only safe choice even on ARM hardware — pygame would need
a from-source build on native Windows-ARM64 Python too).
**Fix: switched the recommended/preferred version from 3.12 to 3.13
everywhere** — `packaging/find_python.ps1` preference order is now
3.13 > 3.12 > 3.11 (3.12/3.11 still matched if already installed locally,
just no longer what the docs tell people to go download), `build_windows.
bat`'s error message and `packaging/LEGGIMI.md` both now point at
**https://www.python.org/downloads/windows/** (the durable, evergreen
index page) with instructions to find "Python 3.13.x" and pick "Windows
installer (64-bit)" — deliberately NOT a specific patch-version release
page URL again, since that's exactly what went stale twice now (round 5's
link, and 3.12 losing installers entirely). **Not yet re-verified on the
user's real Windows-ARM machine** — ask them to install Python 3.13 (64-bit)
per the updated instructions and re-run `build_windows.bat`.

**Round 6: Windows build machine turned out to be ARM64 — architecture
fix, verified only via regex sanity-check, not on real hardware at the time.** After the round-5 Python-version
fix, the user's next pip run showed a completely harmless warning (pip
scripts not on PATH) whose real content was a path:
`...\Python\Python313-arm64\...` — the Windows PC running the build is
Windows-on-ARM (Snapdragon/Copilot+), and the user confirmed the built app
needs to run on OTHER (almost certainly Intel/AMD) church PCs, not just this
one. This matters because **an ARM64-compiled PyInstaller build only runs on
ARM64 Windows** — x64 builds run everywhere (natively on Intel/AMD, via
emulation on ARM), so x64 is the only architecture that's safe to ship
broadly, regardless of which machine does the building.
Fix: new `packaging/find_python.ps1` (called from `build_windows.bat`)
parses `py -0p` for a non-ARM64 3.11–3.13 interpreter (preferring 3.12 >
3.13 > 3.11), falling back to a plain `python` on PATH only if that one is
itself x64 (and not the Microsoft Store's WindowsApps alias stub, which
would hang/no-op on `-c`). If nothing qualifies, prints the same clear
install-link message as round 5, now also explicitly warning **not** to
pick "Windows installer (ARM64)" even on this ARM machine.
Verified: the regex/path-extraction logic was sanity-checked with Python's
`re` (equivalent syntax to the .NET regex PowerShell uses) against both a
"only ARM64 installed" sample and an "ARM64 + x64 with a space in the path
(Program Files)" sample — both resolved correctly. **The .ps1/.bat pair
itself has NOT been run on a real Windows machine this round** (no
Windows/PowerShell available in this environment) — ask the user to
re-run `build_windows.bat` after installing the x64 Python 3.12 and confirm
it now reports the x64 interpreter, not the ARM64 one.

**Round 5: Windows build failed — Python 3.14 has no pygame wheel yet.**
The user's first real `build_windows.bat` run on a Windows PC failed deep
inside `pip install -r requirements.txt`: pygame has no prebuilt wheel for
Python 3.14 (very new), so pip fell back to compiling it from source, which
then failed on a missing MSVC compiler (`ModuleNotFoundError: distutils.
msvccompiler` — removed in modern Python, and no Visual Studio installed,
which is normal/expected on an end-user PC). Not fixable by changing
requirements.txt (no version pin makes wheels exist that don't). Fixed in
`build_windows.bat`: before installing anything, it now probes for a
compatible interpreter (3.11–3.13) via the `py` launcher (`py -3.12`,
`-3.13`, `-3.11` in that order) and falls back to a plain `python` on PATH
only if that one is itself in range; if none found, it prints a direct
download link to Python 3.12 and stops cleanly instead of failing mid-build.
The whole script now runs through a `%PY%` variable instead of hardcoded
`python`. `packaging/LEGGIMI.md` also now links Python 3.12 directly (not
python.org's homepage, which serves whatever is newest — 3.14 today) with an
explicit warning not to grab the newest version. **Not yet re-verified on a
real Windows PC this round** (only reasoned through the batch syntax) — ask
the user to re-run `build_windows.bat` and confirm.

**Round 4: icon "contorno grigio" — fixed & verified in the Dock.**
On macOS 26+ every app icon is masked into the system squircle and any icon
that doesn't fill the whole square gets a gray backing plate — the SDARM
logo (rounded square with transparent corners) looked framed. Fix in
`packaging/generate_icon.py full_square()`: every not-fully-opaque pixel
(transparent corners AND the logo's anti-aliased edge, which otherwise left
a faint darker ring) becomes solid logo-blue → uniform edge-to-edge square;
macOS rounds the corners itself. Windows .ico deliberately keeps the
original rounded-square (Windows doesn't mask). Rebuilt + verified via
Dock-zoom screenshot.

**Round 3: "data e ora non si vedono" — fixed & verified on screen.**
The user's first real launch of the packaged app showed the scaletta header
date clipped and the clock entirely invisible: at the fresh-install default
`left_panel_width` (240px) the 28px-bold date label pushed the clock (packed
after it) out of the panel. Never seen in daily use because the user's own
panel is 414px wide. Fix in `_build_program_list`: the clock is now packed
FIRST (side=right, so pack always allocates its space), the date label packs
`fill="x", expand=True` with `_auto_wrap_label` (wraps to two lines instead
of clipping). Verified from source at 240px (clock mapped inside panel, date
wraps) AND visually on the rebuilt packaged app via computer-use screenshot.
Also this round: `build_mac.sh` rewritten to run the ENTIRE build in a
`mktemp -d` dir — iCloud broke it a second way (`rm -rf dist` fails with
"Directory not empty" because iCloud recreates files mid-delete). See Failed
Attempts.

**Round 2: official branding.** The user provided the official SDARM
logo (wing over open book, blue rounded square — kept as
`assets/app_icon_source.png`; original in `~/Downloads/church-app-icon-1024.png`)
and renamed the app **"Gestione programma SDARM"**. Applied everywhere: window
title, `ui/tutorial.py` welcome page, `core/paths.py` APP_NAME (frozen user-data
folder is now `.../Gestione programma SDARM/`), PyInstaller spec (bundle name +
id `org.sdarm.gestioneprogramma`), build scripts, installer.iss, LEGGIMI.md.
`packaging/generate_icon.py` now converts the official logo (macOS .icns gets
Apple ~80% margins; Windows .ico stays full-bleed). **Rebuilt, ad-hoc signed,
DMG regenerated, first-run re-verified** (scratch HOME: app alive, data +
5 seed bibles in `Application Support/Gestione programma SDARM`). Artifacts:
`dist/Gestione programma SDARM.app` (252 MB) + `.dmg` (122 MB).

**Round 1: full review + productization pass**, explicitly requested:
review everything, fix without changing behavior, add a first-run tutorial,
package for macOS AND Windows (bundling ONLY the bibles — hymns/sounds/music/
lesson/templates are configured by each user). All done and verified.

**Review fixes (all verified live):**
- **CPU leak fixed**: `_refresh_now_playing` and `_tick_clock` accumulated one
  extra `after()` polling loop per panel rebuild (the old loop's exists-check
  passed against the NEW widget). Now both cancel the pending tick before
  scheduling (`_schedule_np_refresh`, `_clock_after_id`).
- **No-audio-device crash fixed**: `core/audio.py _ensure_mixer()` now records
  failure instead of raising — app runs silently on PCs with no sound device.
  Also sets `PYGAME_HIDE_SUPPORT_PROMPT`.
- **"Schermo di proiezione" setting now honored**: `ProjectionWindow._place_on_projector`
  uses the configured monitor index when valid & non-primary, else the old
  first-non-primary heuristic (identical behavior on the user's 2-screen setup).
- **"Qualità predefinita" YouTube setting now honored** (720p/1080p caps via
  yt-dlp format string; default unchanged).
- `_ask_confirm` grew a `confirm_text` param ("Carica modello" now says
  "Sostituisci", not "Elimina").
- Template names sanitized for Windows-illegal filename chars.
- `_qcmd_icon` and `_media_library_files` no longer crash on missing files.
- `_show_image_thumb` downsizes before CTkImage (was pinning full-res photos in RAM).
- Windows: bundled Inter font now registered at startup via
  `AddFontResourceExW` (FR_PRIVATE) in `ui/theme.py`.
- Dead code removed: `ui/settings_window.py` (never imported), `config/pptx_cache/`.
- `requirements.txt`: added `pywin32; sys_platform == "win32"` (PowerPoint COM
  control on Windows — was silently no-op without it).
- `tools/__init__.py` added (regular package → reliable PyInstaller bundling).

**New: `core/paths.py`** — single source of truth for where data lives.
From source: identical to before (project `config/`, `bibles/`). Frozen
(PyInstaller): user data in `~/Library/Application Support/Programma Servizio`
(mac) / `%APPDATA%\Programma Servizio` (win); bundled bibles seeded into the
user dir on first run (so in-app .bib import keeps working). Wired into
`core/settings.py`, `core/prayers.py`, `core/database.py` (db_cache),
`core/bible.py`, `ui/app.py _templates_dir`.

**New: first-run tutorial** (`ui/tutorial.py`, mockup approved by the user
before implementation) — 7-page welcome card overlay (Benvenuto, Scaletta,
Inni, Bibbia, Lezione, Proiezione, Pronti!), app visual language, page dots,
Salta/Indietro/Avanti, ← → / Esc keyboard nav. Triggered once via new setting
`tutorial_seen` (marked seen immediately on first show, so a crash can't
re-trigger it); re-openable from **Impostazioni → Generale → "Rivedi il
tutorial"**. Root key bindings were refactored into `App._bind_global_keys()`
so the overlay can borrow and restore them. **`tutorial_seen` was deliberately
reset to `false` in the user's real settings.json** after testing — the user
will see the tutorial once at their next launch; that is intended.

**New: packaging** (`packaging/`):
- `ProgrammaServizio.spec` — shared PyInstaller spec (onedir, windowed).
  Bundles ONLY: app code+deps, `assets/`, `bibles/*.db`. `collect_all` for
  customtkinter/tkinterdnd2/imageio_ffmpeg/ffpyplayer. No personal data
  (verified: no settings/prayers/hymn folders in the bundle).
- `build_mac.sh` — deps → icon → PyInstaller → **xattr -cr + ad-hoc codesign**
  (required: iCloud/Desktop xattrs break codesign, and Apple Silicon refuses
  unsigned binaries) → DMG with /Applications symlink.
  **Built and verified this session**: `dist/Programma Servizio.app` (251 MB),
  `dist/Programma Servizio.dmg` (122 MB). First-run tested with scratch HOME:
  launches, tutorial appears, settings + seeded bibles written to the user dir.
- `build_windows.bat` — one double-click on any Windows PC with Python
  installed: pip deps → PyInstaller → zip; also builds a real Setup.exe via
  `installer.iss` if Inno Setup 6 is present (optional).
- `generate_icon.py` — creates `assets/app_icon.{png,ico,icns}` (navy rounded
  square, gold beamed notes + open book). Already generated.
- `LEGGIMI.md` — Italian build instructions incl. Gatekeeper/SmartScreen notes.

**Verified this session:** headless tutorial walkthrough (open→7 pages→close→
reopen→persist) on scratch settings; live app from source with REAL settings
(550 hymns load, 5 bible languages, all 6 views + all 10 settings categories
render, clean close); packaged app first-run on scratch HOME.

**Not working / not yet started:** nothing outstanding known. The Windows
build itself still needs to be RUN on a real Windows PC (PyInstaller cannot
cross-compile) — everything is scripted and documented in `packaging/LEGGIMI.md`.

---

## 📁 Relevant Files

| File | Role / Status |
|------|--------------|
| `core/paths.py` | NEW — resource vs user-data dirs, frozen-aware, bible seeding. |
| `ui/tutorial.py` | NEW — 7-page first-run/tutorial overlay. |
| `packaging/*` | NEW — spec, mac/win build scripts, icon generator, Inno Setup script, LEGGIMI.md. |
| `ui/app.py` | Fixes: `_schedule_np_refresh`, `_clock_after_id`, `_bind_global_keys()` (refactor), `_maybe_show_tutorial`/`_show_tutorial`, youtube quality wiring, `_ask_confirm(confirm_text=)`, thumb RAM fix, guards. Settings → Generale gained the Tutorial section. |
| `core/audio.py` | Mixer init is now fail-safe; pygame banner silenced. |
| `ui/projection.py` | `_place_on_projector` honors `projection_screen` when valid/non-primary. |
| `ui/theme.py` | `_register_bundled_fonts()` — Windows-only private Inter registration. |
| `core/settings.py` | New key `tutorial_seen` (default False). SETTINGS_PATH now via paths.config_dir() — still a module attr (headless tests keep monkey-patching it). |
| `config/settings.json` | User's real live data. `tutorial_seen` intentionally left `false` (see above). |
| `dist/` | Built .app + .dmg from this session (rebuild any time with build_mac.sh). |

---

## ❌ Failed Attempts / Bugs Found This Session

### Duplicate `after()` polling loops (perf, found by review)
- Every `_build_right_panel`/`_build_program_list` rebuild started ANOTHER
  700ms/1s polling loop; old loops never died because their exists-check
  evaluated the (reassigned) `self._np_box`/`self._clock_lbl`.
- **Lesson: an `after()` loop guarded by "does my widget still exist" does NOT
  die when the widget is rebuilt and the attribute reassigned — cancel the
  pending id before scheduling anew.**

### codesign fails on iCloud-synced folders — TWICE, differently
- First build: `codesign` errored with "resource fork ... detritus not
  allowed" — Desktop files carry extended attributes. `xattr -cr` + re-sign
  fixed it manually.
- Second build (round 2): the SAME fix scripted inside build_mac.sh failed
  anyway — **iCloud re-adds xattrs in real time while the build runs**, so
  cleaning inside `dist/` (on Desktop = iCloud) is a race you can lose.
- Round 3 added a THIRD iCloud failure: `rm -rf build dist` at the start of
  the build dies with "rm: Directory not empty" (iCloud recreates entries
  mid-delete), aborting the script under `set -e`.
- Definitive fix (now in build_mac.sh): the ENTIRE build — PyInstaller
  workpath/distpath, xattr cleanup, ad-hoc `codesign --deep`, DMG creation —
  runs in a `mktemp -d` dir outside iCloud; only the final .app and .dmg are
  copied back into dist/ (with tolerant `rm ... || true` cleanup). Without an
  ad-hoc signature the app won't launch on Apple Silicon.
- **Lesson: never run any build step inside an iCloud-synced folder** — treat
  the project dir as source-only, /tmp as the build area.

### `_ensure_mixer` could crash startup
- `pygame.mixer.init()` raises on machines with no audio device;
  `AudioManager.__init__` called it unguarded → app would die at launch on
  such PCs (plausible on Windows projector-only machines).

---

## ✅ Working Solutions (key decisions worth preserving)

- **Paths policy**: from source nothing moved; frozen apps write per-user.
  Never bundle personal data; bundle ONLY bibles + assets (user's explicit
  choice — hymns/sounds/music/lesson/templates are per-user config).
- **Tutorial pattern**: full-root overlay (covers nav rail deliberately),
  `tutorial_seen` set immediately on first show, root keybindings borrowed via
  `App._bind_global_keys()` refactor.
- **Mockup-first worked again**: the tutorial mockup was approved before a
  line of implementation (user preference on record in memory).
- **The whole session's Q&A**: Windows build = script for a Windows PC (no
  GitHub Actions); installer is distributable (starts clean); tutorial =
  paged window. Recorded here so future sessions don't re-ask.

---

## 🔧 Dependencies & Setup

```bash
pip install -r requirements.txt   # + access-parser (soft), pywin32 (win only)
python3 main.py
```

Packaging: see `packaging/LEGGIMI.md` (mac: `bash packaging/build_mac.sh`;
win: double-click `packaging\build_windows.bat` on a Windows PC).

`config/settings.json` and `bibles/*.db` are the user's real data — back them
up (or use a scratch copy with `core.settings.SETTINGS_PATH` monkey-patched
*before* `import ui.app`) for any exploratory testing.

---

## ➡️ Next Steps

1. **User sees the tutorial at next launch** (tutorial_seen=false on purpose).
2. **Run `packaging\build_windows.bat` on a real Windows PC** and sanity-test
   the produced app there (PowerPoint control, DnD, fonts, audio).
3. Optional trims if ever asked: the bundle ships two ffmpeg copies
   (imageio_ffmpeg + ffpyplayer's libs, ~100 MB combined) — could drop
   imageio_ffmpeg by pointing yt-dlp at ffpyplayer's binaries, but it's
   invasive; not attempted on purpose.

Low-priority observations carried over from previous sessions:
- `domanda` is the last profile on flat-key color/size mechanism.
- `_graphic_profile_editor` box preview shows outlines only, no sample text.
- `versetto_bibbia`'s "Font riferimento" only applies in the no-template path.

---

## ⚠️ Gotchas / Traps

- **`tutorial_seen` in the user's real settings is `false` ON PURPOSE** —
  don't "fix" it; the user is meant to see the tutorial once.
- **Frozen vs source paths**: all writable data goes through `core/paths.py`.
  Adding a new writable file? Put it under `config_dir()` — never next to
  `__file__`.
- **After() loops**: always keep/cancel the pending id (see Failed Attempts).
- **build_mac.sh must keep the xattr+codesign step** — removing it breaks
  Apple Silicon launches.
- **Two dicts key slot types** — `SLOT_LABELS` (ui/app.py) and
  `_default_name` (core/schedule.py). Keep in sync manually.
- **`Slot.label()` priority**: `data["title"]` → `display_name` → `_default_name`.
- **A graphic profile's box coords are fractions of the TEMPLATE's pixel size**;
  `verse_text_box`/`verse_ref_box` are screen-fraction boxes.
- **Profiles via `self._graphic_profile(name)`** — never reach into settings dict.
- **`self._lesson_verse_ctx` staleness** — non-lezione verse projections must
  clear it; readers must use the full match condition.
- **Never call `_render_center()` right after `_nav(...)`**.
- **Always restart the live app process to test code changes**; check
  `ps aux | grep -i main.py` for processes the user started themselves.
- **`config/settings.json` is live data** — scratch copies for tests.

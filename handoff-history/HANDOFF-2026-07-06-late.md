# Handoff — Programma Servizio (SDA church service manager)

> Generated on 2026-07-06 — resume in a new Claude Code session.
> Working language with the user: **Italian**. Code/comments in English. This file is English.
> The user is on macOS but **everything built must also work identically on Windows**.

---

## 🎯 Goal

A Python/customtkinter desktop app that runs a full Seventh-day Adventist church
service from one control panel, projecting to a second screen (hymns, Bible
verses, lesson questions, timers, prayer requests, media, images, offering
slide...). The app is mature and in daily real use by the user — most work at
this point is refinement, bug fixes, and adding customization on top of an
already-working feature set, not new architecture from scratch.

---

## 📍 Current State

This has been one very long session across 4 rounds, each triggered by the user
actually using the previous round's work for real and coming back with concrete
corrections: previous handoff's 6 Next Steps shipped → user configured all 4
graphic profiles for real, came back with fixes (round 2) → user used those in
real schedule/lezione browsing, came back with 4 more asks incl. 2 bugs (round
3) → user kept using it, came back with 4 more asks incl. 1 more bug + 1 latent
data bug (round 4, this one). Everything below is implemented and verified,
headlessly and on the live app, unless flagged otherwise.

**Round 4 (latest) — verified working:**
- **Removed the redundant slot-detail header.** `_render_center()` already
  shows an eyebrow (colored dot + category, e.g. "INNO") + big title (`slot.label()`)
  before dispatching to any `_detail_*` function — but nearly every
  `_detail_*` function ALSO called a shared `_cat_badge(frame, type, title)`
  helper that rendered the exact same category+title pattern a second time,
  right below the first. Removed all ~13 call sites (predica, campana,
  video, inno ×2, versetto ×2, timer, presentazione, documento, testo,
  qrcode, immagine, audio) and deleted `_cat_badge` itself (zero callers
  left). The two "nothing assigned yet" cases (inno/versetto) and
  preghiere's live count were converted to plain informational labels
  instead of being deleted outright, since that specific text wasn't a
  duplicate of the outer header.
- **Fixed a real, separate bug this surfaced: `_default_name()` (core/schedule.py)
  had no `"immagine"` entry**, so a freshly-created Immagine slot's
  `display_name` silently became the generic `"Elemento"` fallback instead
  of `"Immagine"` — visible in the user's own screenshot. Fixed the dict,
  AND added a one-time fix-up in `Slot.from_dict` that clears an
  already-saved `display_name == "Elemento"` on an `"immagine"`-type slot
  (so existing slots created before this fix self-heal on next load,
  instead of keeping the wrong cached name forever — a real rename via
  `data["title"]` is untouched, `label()` checks that first).
- **Font family is now customizable per lezione profile too** — `domanda`
  gets a flat `lesson_font_family` setting (falls back to the shared
  `verse_font_family` when unset, exactly like its existing color/size
  settings), `nota`/`versetto_lezione` each get their own nested
  `font_family` inside `lesson_graphic_profiles[name]` (via new
  `_profile_font_family`/`_set_profile_font_family`, mirroring
  `_profile_color`/`_profile_max_size`). New shared `_font_family_picker`
  helper (get/set callables, live-styled dropdown via `_style_font_dropdown`)
  replaces the two hand-rolled font pickers in the Bibbia tab and backs all
  3 new ones — one visual pattern, 4 call sites total (2 Bibbia + domanda +
  nota/versetto_lezione). `versetto_bibbia` was deliberately NOT touched —
  it already had its own two flat settings (`verse_font_family`/
  `verse_ref_font_family`) from round 3.
- **Question numbering is now a setting, not hardcoded.** The "a."/"b."
  marker before each domanda's question text was `chr(ord('a') +
  day_index)`, unconditionally. The user's actual quarterly source material
  numbers its questions `1. 2. 3.` instead — **this is NOT recorded in the
  lesson JSON schema** (confirmed by reading `core/lesson.py` — every
  quarterly uses the identical file shape regardless of whether its
  printed questions happen to be lettered or numbered), so it's a new
  settings toggle instead of a JSON field: `lesson_question_numbering`
  (`"letters"` default | `"numbers"`), segmented button in Impostazioni →
  Lezione → Domanda → "Numerazione domande", read by new
  `_lesson_question_marker(dom)` helper. **Currently set to `"numbers"`**
  on the user's real settings (they described their current quarterly as
  numbered) — this is a global app setting, not per-lesson-file, so it'll
  need flipping back if/when they load a lettered quarterly again.
- **New "immagine" slot-type icon**, recreated from a reference screenshot
  the user attached (found on their Desktop by filename/timestamp matching —
  the 3 images in their message were screenshots taken 19:03–19:07 today,
  not files with paths mentioned in chat): a square-ish frame + hollow
  circle "sun" + double-peak mountain zigzag, in olive-green `#709F3C`
  (color-sampled from their reference), replacing the previous gold Feather-
  style icon built earlier this session. `SLOT_COLORS["immagine"]`
  (`#e6c229`, used for the category dot/label text elsewhere) was
  deliberately left untouched — only the icon glyph was asked about.
- **Fixed: wrong graphic when stepping through a schedule "versetto" slot**
  (a real, reproducible bug — see Failed Attempts). `_project_verse_data`
  now clears `self._lesson_verse_ctx` whenever `profile != "lezione"`;
  `_verse_step` computes `in_lesson_ctx` once and reuses it consistently for
  both the stepping-mode branch and the final profile selection, instead of
  checking `if ctx` alone in one of the two places.

**Round 3 — still current:**
- Lesson photo is per-lezione (`lesson_photos`, keyed by `data_sabato`
  alone), not per-day-of-week (was `lesson_day_photos`, migrated
  automatically — see `core/settings.py` `load()`). Helpers:
  `_lesson_photo`/`_set_lesson_photo`/`_pick_lesson_photo`.
- Bibbia settings tab consolidated to the same per-profile pattern as
  Lezione's nota/versetto_lezione: "Colori testo" + "Carattere" + "Dimensione
  massima testo" + "Template e riquadri", all backed by `versetto_bibbia`'s
  own nested `colors`/`max_sizes` (font stayed on 2 flat settings, see
  round 4 above). Old "Aspetto proiezione versetti"/draggable-preview
  sections and their now-dead helper methods were deleted.
- Font-family dropdowns preview each name in its own typeface, via
  `_style_font_dropdown` reaching into `CTkOptionMenu`'s internal
  `_dropdown_menu` (a real `tkinter.Menu`, which supports per-entry fonts
  natively) and calling `entryconfigure(i, font=(name, size))`.

**Round 2 — still current:**
- 4 independent graphic profiles (`domanda`, `nota`, `versetto_lezione`,
  `versetto_bibbia`), each an optional template image + box layout, migrated
  from the old flat `lesson_bg_template`/`lesson_*_box` keys.
  `nota`/`versetto_lezione`/`versetto_bibbia` (as of round 3) each have
  their own independent `colors`/`max_sizes` nested in the profile dict;
  `domanda` alone still uses the older flat `lesson_*` keys (nobody's asked
  to change that one, so it wasn't touched).
- `nota`/`versetto_lezione` show header/date (day title + date badge) when
  templated; `nota` has NO riferimento box at all (removed per explicit
  request — a note has no reference of its own).
- `App.__init__` eagerly creates `_bib_tab`/`_bib_search`/`_lang_extra`
  (previously lazy, causing a silent citation-projection failure the very
  first time a lezione verse was clicked before ever visiting the Bibbia tab).

**Resolved during this round:** the `versetto_bibbia` template file that went
missing earlier this session (`.../Template Chiesa - Versetto Minimal_JPG
(1)/...`) — the user re-saved it themselves at a new path (without the "(1)")
and re-picked it via "Carica template" while this session was still going;
`config/settings.json` already pointed at the corrected path by the time this
was checked, and a live projection of Genesi 1:1 confirmed the template now
renders correctly. No action needed.

**Resolved during this round:** the immagine icon question — the user's 3
attached images turned out to be actual screenshot files on their Desktop
(`Acquisizione schermata 06.07.2026 alle 19.0{3,5,7}...png`, found by
timestamp), not just inline chat images with no path — read directly, one
was the reference icon (confirmed via "usa la foto che ti ho mandato"). See
Current State for what was built from it.

**Not working / not yet started:** nothing else outstanding identified.

---

## 📁 Relevant Files

| File | Role / Status |
|------|--------------|
| `ui/app.py` | Round 4: `_default_name` fix-up lives in `core/schedule.py` not here; `_font_family_picker` (new shared helper), `_profile_font_family`/`_set_profile_font_family`, `_lesson_question_marker`, all `_cat_badge` call sites removed + the method itself deleted. Round 3: `_lesson_photo`/`_set_lesson_photo`/`_pick_lesson_photo`, `_style_font_dropdown`, Bibbia tab consolidated. Round 2: `_lesson_header_date`, `_show_lesson_profile_text`, `_profile_color`/`_set_profile_color`/`_profile_max_size`/`_set_profile_max_size`, `_NOTA_BOX_DEFS`/`_VERSETTO_LEZIONE_BOX_DEFS`/`_VERSE_GRAPHIC_BOX_DEFS`. `App.__init__` eagerly creates `_bib_tab`/`_bib_search`/`_lang_extra`. |
| `core/schedule.py` | `_default_name` now includes `"immagine": "Immagine"`; `Slot.from_dict` clears a stale `display_name == "Elemento"` on immagine-type slots on load. |
| `ui/projection.py` | Unchanged since round 2's `show_lesson_graphic` (`testo_text`/`testo_color`/`testo_max_size`/`riferimento_*`/`font_family` params) — still the single mechanism behind all 4 profiles' templated rendering. |
| `core/settings.py` | New this round: `lesson_font_family` (flat, domanda's own), `lesson_question_numbering` (`"letters"`\|`"numbers"`). `lesson_photos` (round 3, renamed+migrated from `lesson_day_photos`). `lesson_graphic_profiles` schema unchanged at the top level — `colors`/`max_sizes`/`font_family` are all optional nested keys within a profile, no migration needed for those. |
| `config/settings.json` | The user's real, live settings. `lesson_question_numbering` is currently `"numbers"` (set live this session, matches their current quarterly). `versetto_bibbia`'s template path is stale (file missing) — still recorded, not cleared. |

---

## ❌ Failed Attempts / Bugs Found This Session

### Round 4: `_default_name` missing an "immagine" entry
- **What/Fix:** `names.get(slot_type, "Elemento")` in `core/schedule.py`
  silently fell through to `"Elemento"` for `"immagine"` since the dict
  never had that key — added it. Also added a load-time fix-up for
  already-saved slots with the stale name baked in (see Current State).
- **How it surfaced:** the user's own screenshot of the redundant-header
  issue happened to show this bug too ("● IMMAGINE" / "Elemento").
- **Lesson: two visually-adjacent, textually-similar dicts (`SLOT_LABELS` in
  ui/app.py vs. `_default_name`'s `names` in core/schedule.py) drifted out
  of sync** — one had every slot type, the other was missing one. When a
  slot-type list changes, grep for ALL dicts keyed by slot type, not just
  the one you remember editing.

### Round 3: wrong graphic when stepping through a "versetto" schedule slot
- **What/Fix:** `_verse_step`'s profile selection checked `if ctx` alone
  instead of the same book/chapter-match condition used to decide the
  stepping mode, so a stale `self._lesson_verse_ctx` from an unrelated
  earlier lezione citation leaked that profile onto later Bibbia verse
  stepping. Fixed by computing `in_lesson_ctx` once and reusing it for both
  decisions, and by clearing the ctx in `_project_verse_data` whenever
  `profile != "lezione"`.
- **Lesson: when two different call paths can set/read the same
  session-scoped "context" flag, every path that should invalidate it must
  actually do so.**

### Round 2: lazy StringVar init crashed the lezione-citation projection flow
- **What/Fix:** `_bib_tab`/`_bib_search`/`_lang_extra` were only ever created
  lazily inside the Bibbia view's own builder — moved eager into `App.__init__`.
- **Lesson: any state read unconditionally by a function reachable from
  multiple entry points must be initialized eagerly, not lazily in whichever
  view happens to "usually" run first.**

### Round 2: missed a stale reference after the settings migration
- **What/Fix:** `self._settings.get("lesson_bg_template", "")` left behind
  after migrating to `lesson_graphic_profiles` — hid the day-photo picker.
- **Lesson: after any settings-schema migration/rename, grep the exact old
  key name across the ENTIRE file, one more time, right at the end.**

### `left_click` blocked by a stray full-screen "Hex" overlay (recurring risk)
- An installed color-picker utility can leave an invisible full-screen
  capture window active, blocking every computer-use click at the OS level
  while invisible in screenshots. If clicks start failing with "would land
  on X, which is not in the allowed applications" for an app that isn't
  even visible, ask the user to check for/close a stray overlay rather than
  retrying blindly or requesting access to X.

---

## ✅ Working Solutions (key decisions worth preserving)

- **The pattern for adding an independent per-profile setting** (colors,
  max-sizes, and now font_family) is: a pair of methods `_profile_X`/
  `_set_profile_X` reading/writing a key nested in
  `self._settings["lesson_graphic_profiles"][name]`, a shared UI-building
  helper that takes `get_value`/`set_value` callables (`_max_size_slider`,
  `_font_family_picker`) so the SAME widget-building code serves both flat
  settings (Bibbia's shared ones, domanda) and nested per-profile ones
  (nota/versetto_lezione) without duplication. Follow this exact shape if a
  5th customization axis is ever requested.
- **Not every "shared setting, configure once" design survives the user
  actually using every context for real** — this is now the THIRD time
  this session a "let's share this to keep it simple" decision (colors,
  then implicitly font family) got reversed once real usage revealed a
  context with no visible control of its own. Don't be surprised if this
  happens again; it's a pattern for this project, not a one-off mistake.
- **`_cat_badge` being called from ~13 places for 8 years' worth of
  `_detail_*` functions didn't make it load-bearing** — it was pure
  visual duplication with the header `_render_center()` already draws
  unconditionally. When the user says something is "redundant," check
  whether it's ACTUALLY duplicated information (safe to delete outright)
  or just visually-similar-but-distinct information (preghiere's live
  count, the "nothing assigned" messages) that should survive in a
  simpler form instead of disappearing.
- **A lesson JSON schema question should usually be answered "check the
  code, not the file"** — `core/lesson.py`'s docstring already documents
  both supported question schemas in full; when the user asks "is this
  already in the JSON," read that file's `_normalize_domanda`/
  `flatten_domande` before assuming a new field is needed. Here, the
  letter-vs-number question turned out to be entirely a rendering choice
  (`chr(ord('a')+day_index)`), not a JSON limitation — a settings toggle
  was the right fix, not a schema change.

---

## 🔧 Dependencies & Setup

```bash
pip install -r requirements.txt   # includes access-parser (soft dependency,
                                   # only needed for the in-app .bib import)
python3 main.py
```

No other setup. `config/settings.json` and `bibles/*.db` are the user's real
data — back them up (or copy to a scratch dir) before any exploratory testing.

---

## ➡️ Next Steps

None currently queued — both items open at the start of this round (the
immagine icon, the missing versetto_bibbia template) were resolved by the end
of it. **Ask the user what they want next** — this project moves in short,
user-directed increments, consistently triggered by the user using the
previous round's work for real (this has now happened 3 times in a row).

Low-priority, non-blocking observations, only worth picking up if asked:
- `domanda` is the last profile still on the flat-key color/size mechanism —
  trivial to bring in line with the other three if ever asked.
- `_graphic_profile_editor`'s box preview still shows colored outline boxes
  + a label only, no live sample text.
- `versetto_bibbia`'s "Font riferimento" picker (verse_ref_font_family) only
  actually applies in the no-template plain-background path — the templated
  path (`show_lesson_graphic`) uses a single `font_family` for every box, so
  the reference always renders in the SAME font as the main text once a
  template is configured. Pre-existing since round 3, not yet complained
  about, but worth knowing if the user ever asks why the reference font
  picker "doesn't seem to do anything" with a template loaded.

---

## ⚠️ Gotchas / Traps

- **Two different dicts key the same concept by slot type** —
  `SLOT_LABELS` (ui/app.py) and `_default_name`'s `names` (core/schedule.py).
  Keep them in sync manually; nothing enforces it, as the missing
  `"immagine"` entry proved.
- **`Slot.label()` priority: `data["title"]` (real user rename) → `display_name`
  (auto-computed once at creation, persisted) → `_default_name(slot_type)`
  (current, code-side default).** A slot created before a `_default_name`
  fix keeps its stale `display_name` forever unless something explicitly
  clears it — fixing the dict alone does NOT retroactively fix existing data.
- **After any settings-schema migration/rename, grep the OLD key name
  across the entire file, one more time, right before calling the work done.**
- **A graphic profile's box coordinates are fractions of the TEMPLATE's own
  pixel size, not the screen.** `verse_text_box`/`verse_ref_box` (the
  no-template plain-background fallback) are screen-fraction boxes.
- **A profile is looked up via `self._graphic_profile(name)`** — always go
  through that helper (or the `_set_graphic_profile_*`/`_set_profile_*`
  setters), never reach into `self._settings["lesson_graphic_profiles"]` directly.
- **Colors/max-sizes/font come from TWO different places depending on the
  profile** — `domanda` reads shared flat `lesson_*` settings; `nota`,
  `versetto_lezione`, and `versetto_bibbia` (colors/sizes only — font stays
  on its own 2 flat settings) read their own nested values.
- **`self._lesson_verse_ctx` can be stale from an unrelated earlier action**
  — any code path projecting a Bible verse that ISN'T explicitly a lezione
  citation must actively clear it; any code reading it to decide behavior
  must use the full match condition, never just truthiness.
- **`lesson_question_numbering` is a single global setting, not per-lesson-file**
  — if the user loads a quarterly with the other numbering convention,
  they need to flip the toggle in Impostazioni → Lezione → Domanda manually.
- **Any state read unconditionally by a function reachable from multiple
  entry points must be initialized eagerly (in `__init__`), not lazily.**
- **Never call `_render_center()` right after `_nav(...)`** — throws `bad
  window path name` on the freshly-destroyed widget tree.
- **Always restart the live app process to test code changes** — verify the
  old process is actually dead (`ps aux | grep -i main.py`) first. This
  session, the user ALSO restarted the app themselves from a terminal at
  least once mid-session — check for an existing process before assuming
  yours is the only one running.
- **`config/settings.json` is the user's real, live data.** Every headless
  test uses a scratch copy (`core.settings.SETTINGS_PATH` monkey-patched
  *before* `import ui.app`). Real template file paths on the user's Desktop
  can go stale — `os.path.isfile()` before trusting a recorded path.

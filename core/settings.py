import json
import os

from core.paths import config_dir

# Module-level (not a function) on purpose: headless tests monkey-patch this
# before importing ui.app — see HANDOFF.md.
SETTINGS_PATH = os.path.join(config_dir(), "settings.json")

DEFAULTS = {
    "databases": [],
    "last_database": "",
    "theme": "dark",
    "appearance_mode": "System",
    "max_history": 100,
    "hymn_history": [],
    "verse_history": [],
    "schedule": [],
    "background_music_folder": "",
    "background_music_mode": "shuffle",
    "bell_sound": "",
    "projection_screen": 1,
    "timer_warning_enabled": True,
    "timer_warning_seconds": 60,
    "timer_warning_sound": "",
    "timer_default_minutes": 10,
    # Timer projection look
    "timer_bg_color": "#0b132b",
    "timer_bg_image": "",
    "timer_text_color": "#ffffff",
    "timer_text": "Il programma riprenderà tra",
    # Bible/verse projection look (separate from the timer). Both the main
    # text and the reference live in their own freely movable/resizable box
    # (x, y, w, h — all 0..1 fractions of screen size, like a Word text box);
    # the font autofits to whatever size the box is dragged to. Defaults leave
    # a real gap between the two boxes so the reference never looks stuck to
    # the verse text.
    "verse_bg_color": "#0b132b",
    "verse_bg_image": "",
    "verse_text_color": "#ffffff",
    "verse_font_family": "Helvetica",
    "verse_text_box": [0.07, 0.10, 0.86, 0.55],
    "verse_ref_box": [0.25, 0.78, 0.50, 0.08],
    "verse_ref_font_family": "Helvetica",
    # Manual max-size caps (px, 0 = nessun limite) on top of the box-based
    # autofit above — verse_ref defaults to a real cap because the reference
    # box is wide/short enough that autofit alone made it render too big.
    "verse_text_max_size": 0,
    "verse_ref_max_size": 40,
    # Bible
    "bible_languages_selected": [],   # lang codes chosen for projection
    "bible_versions": {},             # lang -> active version short
    # Offering (QR) — chosen once in settings, projected full-screen
    "offering_image": "",
    # Background image for the "Sfondo" quick command — full-screen overlay
    "background_image": "",
    # Lesson (Scuola del Sabato) — auto-detect today's lesson from a JSON file
    "lesson_file": "",
    "lesson_override_index": -1,   # -1 = automatic by date
    # How each day's questions are numbered on the projected domanda graphic
    # (the "a."/"b." or "1."/"2." marker before the question text) — some
    # quarterlies' source material uses letters, others numbers; this isn't
    # recorded in the lesson JSON itself (every quarterly uses the same file
    # schema regardless), so it's a settings toggle the user flips per
    # quarterly rather than something to encode per-file.
    "lesson_question_numbering": "letters",   # "letters" (a, b, c) | "numbers" (1, 2, 3)
    # Lesson themed graphics — one profile per projection context, each a
    # static template (swapped by hand once per trimestre) + its own named
    # boxes (x, y, w, h — fractions of the TEMPLATE's own pixel size, not the
    # screen, so they stay correct however the template ends up scaled/
    # letterboxed). Keyed by profile name:
    #   "domanda"          — boxes: header/date/photo/question (the lezione
    #                         question card; existing behavior, was flat keys)
    #   "nota"             — boxes: testo/riferimento (the lezione note)
    #   "versetto_lezione" — boxes: testo/riferimento (a verse cited from
    #                         inside a lezione question)
    #   "versetto_bibbia"  — boxes: testo/riferimento (a verse projected from
    #                         the Bibbia section itself)
    # A profile with no "template" set (the default, {}) means: fall back to
    # the plain-background rendering that already exists for that context —
    # colors/fonts/max-sizes are NOT part of a profile, they keep coming from
    # the shared verse_*/lesson_* settings above regardless of which template
    # (if any) is active, so the user never has to set them twice.
    "lesson_graphic_profiles": {},
    # Manual max-size caps (px, 0 = nessun limite) on top of each box's own
    # autofit, same mechanism/rationale as verse_ref_max_size above.
    "lesson_header_max_size": 0,
    "lesson_date_max_size": 0,
    "lesson_question_max_size": 0,
    "lesson_verse_max_size": 0,
    # Independent colors for the "a."/"b." letter, the date badge, and the
    # verse-citation line under the question — "" means "use
    # lesson_header_color" (today's behavior, so existing settings files
    # render identically until the user picks a different color for one).
    "lesson_letter_color": "",
    "lesson_date_color": "",
    "lesson_verse_color": "",
    # "" = fall back to the shared verse_font_family (today's behavior) —
    # lets the user give the domanda graphic its own font independently of
    # nota/versetto_lezione (which use their own nested per-profile
    # font_family instead, see _profile_font_family in ui/app.py) and of
    # versetto_bibbia (which keeps the original shared verse_font_family/
    # verse_ref_font_family, untouched).
    "lesson_font_family": "",
    # One photo per lezione (keyed by data_sabato) — shared by every day/
    # question within that lezione, without touching the source JSON.
    "lesson_photos": {},
    "youtube_folder": "",
    "window_geometry": "1280x720",
    "left_panel_width": 240,
    "right_panel_width": 240,
    # First-run welcome walkthrough (ui/tutorial.py) — shown once at the very
    # first startup, then re-openable from Impostazioni → Generale.
    "tutorial_seen": False,
}


def load() -> dict:
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = dict(DEFAULTS)
            result.update(data)
            # one-time migration: the quick-command "logo" setting was renamed
            # to "sfondo" (background_image) — carry over any value already
            # configured under the old key, then drop the old key for good.
            if "logo_image" in result:
                if not result.get("background_image"):
                    result["background_image"] = result["logo_image"]
                del result["logo_image"]
            # one-time migration chain: verse reference position used to be a
            # fixed 'top'/'bottom' choice, then a freely draggable point
            # (x/y), and is now a freely draggable AND resizable box
            # (x/y/w/h) — each step below only fires if the next-gen key
            # isn't already present, so re-running this is a no-op.
            if "verse_ref_position" in result:
                if "verse_ref_x" not in data and "verse_ref_box" not in data:
                    result["verse_ref_x"] = 0.5
                    result["verse_ref_y"] = 0.10 if result["verse_ref_position"] == "top" else 0.90
                del result["verse_ref_position"]
            if "verse_ref_x" in result or "verse_ref_y" in result:
                if "verse_ref_box" not in data:
                    rx, ry = result.pop("verse_ref_x", 0.5), result.pop("verse_ref_y", 0.90)
                    bw, bh = 0.50, 0.08
                    result["verse_ref_box"] = [max(0.0, min(1 - bw, rx - bw / 2)),
                                               max(0.0, min(1 - bh, ry - bh / 2)), bw, bh]
                else:
                    result.pop("verse_ref_x", None)
                    result.pop("verse_ref_y", None)
            # one-time migration: the lezione question's template+boxes used
            # to live in flat lesson_bg_template/lesson_<key>_box settings —
            # now every projection context has its own named profile in
            # lesson_graphic_profiles, so the old flat values become the
            # "domanda" profile (only if that dict hasn't already been
            # written, so re-running this is a no-op).
            if "lesson_graphic_profiles" not in data and (
                    "lesson_bg_template" in data or any(
                        f"lesson_{k}_box" in data for k in
                        ("header", "date", "photo", "question"))):
                boxes = {}
                for key in ("header", "date", "photo", "question"):
                    box = result.pop(f"lesson_{key}_box", None)
                    if box is not None:
                        boxes[key] = box
                result["lesson_graphic_profiles"] = {"domanda": {
                    "template": result.pop("lesson_bg_template", ""),
                    "boxes": boxes,
                }}
            else:
                for key in ("header", "date", "photo", "question"):
                    result.pop(f"lesson_{key}_box", None)
                result.pop("lesson_bg_template", None)
            # one-time migration: the day photo picker used to keep one photo
            # per (data_sabato, day_position) — now it's one photo per whole
            # lezione (data_sabato alone), since the user found per-day
            # photos more granular than wanted. Picks the lowest day
            # position's photo per lezione as a reasonable carry-over rather
            # than silently discarding what was already configured.
            if "lesson_day_photos" in data and "lesson_photos" not in data:
                photos = {}
                for sabato, by_pos in (result.pop("lesson_day_photos", None) or {}).items():
                    if isinstance(by_pos, dict) and by_pos:
                        first_pos = min(by_pos, key=lambda p: int(p))
                        photos[sabato] = by_pos[first_pos]
                    elif isinstance(by_pos, str):
                        photos[sabato] = by_pos
                result["lesson_photos"] = photos
            else:
                result.pop("lesson_day_photos", None)
            return result
        except Exception:
            pass
    return dict(DEFAULTS)


def save(settings: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

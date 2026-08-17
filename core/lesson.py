"""Lesson loading + 'today' detection.

The loader is permissive: it accepts a top-level list of lessons, or a dict
with a "lessons" list. Each lesson may define its date window via either:
  - "date" / "data_sabato": "YYYY-MM-DD"   (single day)
  - "date_start"/"date_end": "YYYY-MM-DD"  (inclusive range)
and any other fields (title, hymns, verses, ...), passed through untouched.

Two question schemas are supported and normalized by flatten_domande():
  - simple: a flat "domande" list directly on the lesson, each item having
    "domanda"/"testo" (question), "versetto"/"versetti" (str or list), "note"
    (str).
  - Lezionario quarterly format: questions nested under a daily "giorni" list
    (each day: "giorno", "titolo_giorno", "domande"), each question having
    "testo", "versetti" (list of reference strings), "nota_egw".
"""
import json
import os
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any


def _parse(d: str) -> Optional[date]:
    if not d:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(d.strip(), fmt).date()
        except ValueError:
            continue
    return None


class LessonSet:
    def __init__(self, lessons: List[Dict[str, Any]], source: str = ""):
        self.lessons = lessons
        self.source = source

    @classmethod
    def load(cls, path: str) -> "LessonSet":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            lessons = data.get("lessons", [])
        elif isinstance(data, list):
            lessons = data
        else:
            lessons = []
        return cls([l for l in lessons if isinstance(l, dict)], source=path)

    def find_for(self, day: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """The lesson in force on `day`.

        A quarterly lesson is dated by "data_sabato", the Sabbath on which it
        is *discussed* — the six daily sections (Domenica…Venerdì) are studied
        during the week that LEADS UP to it. So a lesson is current for the
        whole Sunday→Saturday window ending on its data_sabato, not on that
        one Saturday alone (which is why "lezione automatica" only ever found
        a lesson on Saturdays before). "date"/"date_start"/"date_end" keep
        their old exact-day / explicit-range meaning."""
        day = day or date.today()
        for les in self.lessons:
            single = _parse(les.get("date") or "")
            if single and single == day:
                return les
            sabato = _parse(les.get("data_sabato") or "")
            if sabato and sabato - timedelta(days=6) <= day <= sabato:
                return les
            ds = _parse(les.get("date_start", ""))
            de = _parse(les.get("date_end", ""))
            if ds and de and ds <= day <= de:
                return les
            if ds and not de and ds == day:
                return les
        return None

    def titles(self) -> List[str]:
        out = []
        for i, les in enumerate(self.lessons):
            t = les.get("title") or les.get("titolo") or f"Lezione {i + 1}"
            out.append(t)
        return out

    def get(self, index: int) -> Optional[Dict[str, Any]]:
        if 0 <= index < len(self.lessons):
            return self.lessons[index]
        return None


def day_date(lesson: Dict[str, Any], dom: Dict[str, Any]) -> Optional[date]:
    """Calendar date of the day `dom` belongs to.

    data_sabato is the Sabbath on which the lesson is DISCUSSED; the six
    daily sections are studied in the week before it, so Domenica
    (day_position 1) is data_sabato - 6 and Venerdì (6) is data_sabato - 1.
    None when the lesson has no date or the domanda has no day grouping."""
    sabato = _parse(lesson.get("data_sabato") or lesson.get("date") or "")
    pos = dom.get("day_position", 0)
    if not sabato or not pos:
        return None
    return sabato - timedelta(days=7 - pos)


def _normalize_domanda(d: Dict[str, Any], day: str, day_title: str,
                       day_position: int) -> Dict[str, Any]:
    question = d.get("testo") or d.get("domanda") or ""
    verses_raw = d.get("versetti")
    if verses_raw is None:
        v = d.get("versetto")
        verses = [v] if v else []
    elif isinstance(verses_raw, list):
        verses = [str(v) for v in verses_raw if v]
    else:
        verses = [str(verses_raw)]
    note = d.get("nota_egw") or d.get("note") or ""
    return {"day": day, "day_title": day_title, "day_position": day_position,
            "question": question, "verses": verses, "note": note}


def flatten_domande(lesson: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize a lesson's questions into one flat, ordered list regardless
    of whether they're nested under daily "giorni" (Lezionario quarterly
    format) or given directly as a flat "domande" list on the lesson.
    Each item: {"day", "day_title", "day_position", "question",
    "verses" (list[str]), "note", "day_index", "day_count"} — day_index/
    day_count number each question relative to its own day (e.g. 1/3 for
    Sunday), not the lesson's total. day_position is the 1-based index of
    the day within "giorni" (Sunday=1, Monday=2, ...) — used (instead of the
    "giorno" name, which real Lezionario files have been seen to mislabel/
    duplicate) to compute the day's calendar date from "data_sabato" and to
    key per-day photo assignments, so a mislabeled day name can't collide
    with another day's.
    """
    out: List[Dict[str, Any]] = []
    giorni = lesson.get("giorni")
    if isinstance(giorni, list) and giorni:
        for day_position, g in enumerate(giorni, start=1):
            if not isinstance(g, dict):
                continue
            day = g.get("giorno", "")
            day_title = g.get("titolo_giorno", "")
            day_domande = [d for d in g.get("domande", []) if isinstance(d, dict)]
            for day_idx, d in enumerate(day_domande):
                item = _normalize_domanda(d, day, day_title, day_position)
                item["day_index"] = day_idx
                item["day_count"] = len(day_domande)
                out.append(item)
    else:
        flat = [d for d in lesson.get("domande", []) if isinstance(d, dict)]
        for day_idx, d in enumerate(flat):
            item = _normalize_domanda(d, "", "", 0)
            item["day_index"] = day_idx
            item["day_count"] = len(flat)
            out.append(item)
    return out

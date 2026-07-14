"""Parse Italian Bible reference strings (as found in lesson-quarterly JSON
files) into (book, chapter, verse) lookups against the app's Bible database.

Handles the patterns actually seen in real Lezionario exports:
  - "Esodo 34:6, 7"                -> book Esodo, chapter 34, verses [6, 7]
  - "1 Giovanni 4:9–12"            -> numbered books, en-dash ranges
  - "Efesini 6:12-18"              -> ASCII-hyphen ranges
  - "Giona 4:2 (ultima parte)"     -> trailing parenthetical annotation, kept
                                       aside but ignored for lookup
  - "10:16"                        -> bare chapter:verse, inherits the book of
                                       the PREVIOUS reference in the same list
  - "Che cosa ... Matteo 14:28–31" -> stray leading text before a valid ref

Anything that doesn't match a known book name (directly, or by inheriting the
previous reference's book) is returned unresolved — never guessed — so the
caller can fall back to showing the raw citation text instead of a wrong verse.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from core.textutil import normalize

# Common Italian citation forms that don't match the DB's canonical book name
# verbatim (e.g. quarterlies say "Salmo 23" for an individual psalm, while the
# book itself is named "Salmi" in the Bible database).
_ALIASES = {
    "salmo": "salmi",
}


def _verse_list(spec: str) -> List[int]:
    out: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(range(a, b + 1))
            continue
        m2 = re.match(r"^(\d+)$", part)
        if m2:
            out.append(int(m2.group(1)))
    seen = set()
    result = []
    for v in out:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def parse_references(refs: List[str], books: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
    """books: [(book_num, book_name), ...] from BibleLibrary.books(lang)."""
    by_norm = sorted(((normalize(name), num, name) for num, name in books),
                      key=lambda t: -len(t[0]))
    name_to_book = {n: (num, name) for n, num, name in by_norm}
    for alias, canonical in _ALIASES.items():
        if canonical in name_to_book and alias not in name_to_book:
            name_to_book[alias] = name_to_book[canonical]
    book_alt = "|".join(re.escape(n) for n in
                         sorted(name_to_book, key=len, reverse=True))
    book_re = re.compile(r"\b(" + book_alt + r")\s+(\d+)\s*:\s*([\d,\s\-–]+)")
    bare_re = re.compile(r"^\s*(\d+)\s*:\s*([\d,\s\-–]+)")

    out: List[Dict[str, Any]] = []
    last_book: Optional[Tuple[int, str]] = None
    for raw in refs:
        annotation = ""
        cleaned = raw
        m_ann = re.search(r"\(([^)]*)\)\s*$", raw)
        if m_ann:
            annotation = m_ann.group(1)
            cleaned = raw[:m_ann.start()].strip()
        norm_cleaned = normalize(cleaned)

        m = book_re.search(norm_cleaned)
        if m:
            book_num, book_name = name_to_book[m.group(1)]
            chapter = int(m.group(2))
            verses = _verse_list(m.group(3))
            last_book = (book_num, book_name)
            out.append({"raw": raw, "annotation": annotation, "resolved": bool(verses),
                        "book": book_num, "book_name": book_name,
                        "chapter": chapter, "verses": verses})
            continue

        m2 = bare_re.match(norm_cleaned)
        if m2 and last_book:
            chapter = int(m2.group(1))
            verses = _verse_list(m2.group(2))
            out.append({"raw": raw, "annotation": annotation, "resolved": bool(verses),
                        "book": last_book[0], "book_name": last_book[1],
                        "chapter": chapter, "verses": verses})
            continue

        out.append({"raw": raw, "annotation": annotation, "resolved": False,
                    "book": None, "book_name": None, "chapter": None, "verses": []})
    return out

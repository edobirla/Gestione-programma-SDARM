"""Bible library — reads bundled SQLite bibles from <app>/bibles/*.db.

Each .db is produced by tools/convert_bib.py from a BibleShow .bib file and is
fully self-contained (verses + book structure + metadata). At runtime NO external
tool (mdbtools, access-parser) is required.

A .db represents one *version* in one *language*. Multiple versions can coexist
for the same language (e.g. it_LND, it_CEI); the user picks the active one per
language in the settings.
"""
import os
import sqlite3
from typing import List, Tuple, Dict, Optional

from core.paths import bibles_dir

BIBLES_DIR = bibles_dir()

LANGUAGE_LABELS = {
    "it": "Italiano", "ro": "Română", "es": "Español",
    "en": "English", "fr": "Français", "pt": "Português",
}


class BibleVersion:
    def __init__(self, path: str):
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        meta = dict(self._conn.execute("SELECT key, value FROM meta").fetchall())
        self.code = meta.get("code", "xx")
        self.language = meta.get("language", "")
        self.short = meta.get("version_short", os.path.basename(path))
        self.full = meta.get("version_full", self.short)

    def books(self) -> List[Tuple[int, str]]:
        rows = self._conn.execute(
            "SELECT num, list_title FROM books ORDER BY position").fetchall()
        return [(r[0], r[1]) for r in rows]

    def book_name(self, num: int) -> str:
        r = self._conn.execute(
            "SELECT list_title FROM books WHERE num=?", (num,)).fetchone()
        return r[0] if r else f"Libro {num}"

    def chapters(self, book: int) -> List[int]:
        rows = self._conn.execute(
            "SELECT DISTINCT chapter FROM verses WHERE book=? ORDER BY chapter",
            (book,)).fetchall()
        return [r[0] for r in rows]

    def verses(self, book: int, chapter: int) -> List[Tuple[int, str]]:
        rows = self._conn.execute(
            "SELECT verse, scripture FROM verses WHERE book=? AND chapter=? ORDER BY verse",
            (book, chapter)).fetchall()
        return [(r[0], r[1]) for r in rows]

    def get_verse(self, book: int, chapter: int, verse: int) -> Optional[str]:
        r = self._conn.execute(
            "SELECT scripture FROM verses WHERE book=? AND chapter=? AND verse=?",
            (book, chapter, verse)).fetchone()
        return r[0] if r else None

    def _ensure_search_index(self):
        if getattr(self, "_search_index", None) is not None:
            return
        from core.textutil import normalize
        rows = self._conn.execute(
            "SELECT book, chapter, verse, scripture FROM verses").fetchall()
        self._search_index = [(r[0], r[1], r[2], r[3], normalize(r[3])) for r in rows]

    def search(self, query: str, limit: int = 80) -> List[Tuple[int, int, int, str]]:
        from core.textutil import normalize
        q = normalize(query)
        if not q:
            return []
        self._ensure_search_index()
        out = []
        for book, chap, vnum, text, norm in self._search_index:
            if q in norm:
                out.append((book, chap, vnum, text))
                if len(out) >= limit:
                    break
        return out

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


class BibleLibrary:
    """Scans the bibles/ folder and exposes available languages/versions."""

    def __init__(self, bibles_dir: str = BIBLES_DIR):
        self.dir = bibles_dir
        # versions[lang] = { short: BibleVersion }
        self._versions: Dict[str, Dict[str, BibleVersion]] = {}
        self._active: Dict[str, str] = {}   # lang -> selected version short
        self.reload()

    def reload(self):
        for langmap in self._versions.values():
            for v in langmap.values():
                v.close()
        self._versions = {}
        if not os.path.isdir(self.dir):
            return
        for fname in sorted(os.listdir(self.dir)):
            if not fname.lower().endswith(".db"):
                continue
            try:
                ver = BibleVersion(os.path.join(self.dir, fname))
            except Exception as e:
                print(f"[Bible] skip {fname}: {e}")
                continue
            self._versions.setdefault(ver.code, {})[ver.short] = ver
        # default active version = first available per language
        for lang, langmap in self._versions.items():
            if lang not in self._active or self._active[lang] not in langmap:
                self._active[lang] = next(iter(langmap))

    # ── availability ────────────────────────────────────────────────────────
    @property
    def ready(self) -> bool:
        return bool(self._versions)

    def languages(self) -> List[str]:
        """Available language codes, ordered by LANGUAGE_LABELS preference."""
        order = list(LANGUAGE_LABELS.keys())
        return sorted(self._versions.keys(),
                      key=lambda c: order.index(c) if c in order else 99)

    def language_label(self, code: str) -> str:
        return LANGUAGE_LABELS.get(code, code.upper())

    def versions(self, lang: str) -> List[Tuple[str, str]]:
        """Returns [(short, full), ...] for a language."""
        return [(v.short, v.full) for v in self._versions.get(lang, {}).values()]

    def has_multiple_versions(self, lang: str) -> bool:
        return len(self._versions.get(lang, {})) > 1

    # ── active version selection ──────────────────────────────────────────────
    def set_active_version(self, lang: str, short: str):
        if lang in self._versions and short in self._versions[lang]:
            self._active[lang] = short

    def active_version_short(self, lang: str) -> Optional[str]:
        return self._active.get(lang)

    def load_active_from_settings(self, mapping: Dict[str, str]):
        for lang, short in (mapping or {}).items():
            self.set_active_version(lang, short)

    def active_mapping(self) -> Dict[str, str]:
        return dict(self._active)

    def _ver(self, lang: str) -> Optional[BibleVersion]:
        langmap = self._versions.get(lang)
        if not langmap:
            return None
        return langmap.get(self._active.get(lang)) or next(iter(langmap.values()))

    # ── data access (uses active version of the language) ─────────────────────
    def books(self, lang: str) -> List[Tuple[int, str]]:
        v = self._ver(lang)
        return v.books() if v else []

    def book_name(self, lang: str, num: int) -> str:
        v = self._ver(lang)
        return v.book_name(num) if v else f"Libro {num}"

    def chapters(self, lang: str, book: int) -> List[int]:
        v = self._ver(lang)
        return v.chapters(book) if v else []

    def verses(self, lang: str, book: int, chapter: int) -> List[Tuple[int, str]]:
        v = self._ver(lang)
        return v.verses(book, chapter) if v else []

    def get_verse(self, lang: str, book: int, chapter: int, verse: int) -> Optional[str]:
        v = self._ver(lang)
        return v.get_verse(book, chapter, verse) if v else None

    def search(self, lang: str, query: str, limit: int = 80):
        v = self._ver(lang)
        return v.search(query, limit) if v else []

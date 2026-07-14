from datetime import date, datetime
from typing import List


class HymnEntry:
    def __init__(self, number: str, title: str, path: str,
                 section_name: str = "", slot_name: str = "",
                 date_str: str = "", time_str: str = ""):
        self.number = number
        self.title = title
        self.path = path
        self.section_name = section_name
        self.slot_name = slot_name
        self.date_str = date_str or date.today().isoformat()
        # HH:MM — added for the redesigned "Usato oggi, 09:14" cronologia
        # rows; blank for entries saved before this field existed, which the
        # UI treats gracefully (just omits the time).
        self.time_str = time_str or datetime.now().strftime("%H:%M")

    @classmethod
    def from_dict(cls, d: dict) -> "HymnEntry":
        return cls(
            number=d.get("number", "?"),
            title=d.get("title", "?"),
            path=d.get("path", ""),
            section_name=d.get("section_name", ""),
            slot_name=d.get("slot_name", ""),
            date_str=d.get("date_str", ""),
            time_str=d.get("time_str", ""),
        )

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "title": self.title,
            "path": self.path,
            "section_name": self.section_name,
            "slot_name": self.slot_name,
            "date_str": self.date_str,
            "time_str": self.time_str,
        }

    @property
    def display(self) -> str:
        return f"{self.number} — {self.title}"


class VerseEntry:
    def __init__(self, book: str, chapter: int, verse: int,
                 text_it: str = "", text_ro: str = "",
                 section_name: str = "", date_str: str = "", time_str: str = ""):
        self.book = book
        self.chapter = chapter
        self.verse = verse
        self.text_it = text_it
        self.text_ro = text_ro
        self.section_name = section_name
        self.date_str = date_str or date.today().isoformat()
        self.time_str = time_str or datetime.now().strftime("%H:%M")

    @property
    def ref(self) -> str:
        return f"{self.book} {self.chapter}:{self.verse}"

    @classmethod
    def from_dict(cls, d: dict) -> "VerseEntry":
        return cls(
            book=d.get("book", ""),
            chapter=d.get("chapter", 1),
            verse=d.get("verse", 1),
            text_it=d.get("text_it", ""),
            text_ro=d.get("text_ro", ""),
            section_name=d.get("section_name", ""),
            date_str=d.get("date_str", ""),
            time_str=d.get("time_str", ""),
        )

    def to_dict(self) -> dict:
        return {
            "book": self.book,
            "chapter": self.chapter,
            "verse": self.verse,
            "text_it": self.text_it,
            "text_ro": self.text_ro,
            "section_name": self.section_name,
            "date_str": self.date_str,
            "time_str": self.time_str,
        }


class History:
    def __init__(self, max_items: int = 100):
        self._max = max_items
        self.hymns: List[HymnEntry] = []
        self.verses: List[VerseEntry] = []

    def add_hymn(self, number: str, title: str, path: str,
                 section_name: str = "", slot_name: str = ""):
        entry = HymnEntry(number, title, path, section_name, slot_name)
        self.hymns.insert(0, entry)
        self.hymns = self.hymns[:self._max]

    def add_verse(self, book: str, chapter: int, verse: int,
                  text_it: str = "", text_ro: str = "", section_name: str = ""):
        entry = VerseEntry(book, chapter, verse, text_it, text_ro, section_name)
        self.verses.insert(0, entry)
        self.verses = self.verses[:self._max]

    def load_from_dicts(self, hymns_data: list, verses_data: list):
        self.hymns = [HymnEntry.from_dict(d) for d in hymns_data if isinstance(d, dict)]
        self.verses = [VerseEntry.from_dict(d) for d in verses_data if isinstance(d, dict)]

    def hymns_to_dicts(self) -> list:
        return [e.to_dict() for e in self.hymns]

    def verses_to_dicts(self) -> list:
        return [e.to_dict() for e in self.verses]

    def clear_hymns(self):
        self.hymns.clear()

    def clear_verses(self):
        self.verses.clear()

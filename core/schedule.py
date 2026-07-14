"""Data model for the weekly service schedule."""
from __future__ import annotations
from typing import List, Optional, Dict, Any
import uuid


SLOT_TYPES = [
    "inno",
    "versetto",
    "lezione",
    "predica",
    "presentazione",
    "timer",
    "audio",
    "video",
    "documento",
    "qrcode",
    "immagine",
    "testo",
    "campana",
    "preghiera",
    "altro",
]


class Slot:
    def __init__(self, slot_type: str = "altro", display_name: str = "",
                 data: Optional[Dict[str, Any]] = None, slot_id: Optional[str] = None):
        self.id = slot_id or str(uuid.uuid4())
        self.slot_type = slot_type
        self.display_name = display_name or _default_name(slot_type)
        self.data: Dict[str, Any] = data or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slot_type": self.slot_type,
            "display_name": self.display_name,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Slot":
        slot_type = d.get("slot_type", "altro")
        display_name = d.get("display_name", "")
        # One-time fix-up: "immagine" slots created before _default_name had
        # an entry for that type got the generic "Elemento" fallback baked
        # into their saved display_name — clear it so label() recomputes the
        # correct "Immagine" default instead of keeping the stale wrong name
        # forever (a real user rename lives in data["title"], untouched here).
        if slot_type == "immagine" and display_name == "Elemento":
            display_name = ""
        return cls(
            slot_type=slot_type,
            display_name=display_name,
            data=d.get("data", {}),
            slot_id=d.get("id"),
        )

    def label(self) -> str:
        # A user-set custom title (from the slot's ✎/double-click rename) wins
        # over both the auto display_name and the type default.
        custom = (self.data.get("title") or "").strip()
        if custom:
            return custom
        if self.display_name:
            return self.display_name
        return _default_name(self.slot_type)


class Section:
    def __init__(self, name: str = "Sezione", slots: Optional[List[Slot]] = None,
                 section_id: Optional[str] = None):
        self.id = section_id or str(uuid.uuid4())
        self.name = name
        self.slots: List[Slot] = slots or []

    def add_slot(self, slot: Slot, index: Optional[int] = None):
        if index is None:
            self.slots.append(slot)
        else:
            self.slots.insert(index, slot)

    def remove_slot(self, slot_id: str) -> bool:
        before = len(self.slots)
        self.slots = [s for s in self.slots if s.id != slot_id]
        return len(self.slots) < before

    def move_slot(self, slot_id: str, delta: int):
        idx = next((i for i, s in enumerate(self.slots) if s.id == slot_id), None)
        if idx is None:
            return
        new_idx = max(0, min(len(self.slots) - 1, idx + delta))
        slot = self.slots.pop(idx)
        self.slots.insert(new_idx, slot)

    def get_slot(self, slot_id: str) -> Optional[Slot]:
        return next((s for s in self.slots if s.id == slot_id), None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slots": [s.to_dict() for s in self.slots],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Section":
        slots = [Slot.from_dict(sd) for sd in d.get("slots", [])]
        return cls(
            name=d.get("name", "Sezione"),
            slots=slots,
            section_id=d.get("id"),
        )


class Schedule:
    def __init__(self, sections: Optional[List[Section]] = None):
        self.sections: List[Section] = sections or []

    def add_section(self, name: str = "Nuova sezione", index: Optional[int] = None) -> Section:
        sec = Section(name=name)
        if index is None:
            self.sections.append(sec)
        else:
            self.sections.insert(index, sec)
        return sec

    def remove_section(self, section_id: str) -> bool:
        before = len(self.sections)
        self.sections = [s for s in self.sections if s.id != section_id]
        return len(self.sections) < before

    def move_section(self, section_id: str, delta: int):
        idx = next((i for i, s in enumerate(self.sections) if s.id == section_id), None)
        if idx is None:
            return
        new_idx = max(0, min(len(self.sections) - 1, idx + delta))
        sec = self.sections.pop(idx)
        self.sections.insert(new_idx, sec)

    def get_section(self, section_id: str) -> Optional[Section]:
        return next((s for s in self.sections if s.id == section_id), None)

    def find_slot(self, slot_id: str) -> Optional[tuple]:
        """Returns (section, slot) or None."""
        for sec in self.sections:
            slot = sec.get_slot(slot_id)
            if slot:
                return (sec, slot)
        return None

    def to_list(self) -> list:
        return [s.to_dict() for s in self.sections]

    @classmethod
    def from_list(cls, data: list) -> "Schedule":
        sections = [Section.from_dict(d) for d in data if isinstance(d, dict)]
        return cls(sections=sections)

    @classmethod
    def default(cls) -> "Schedule":
        sched = cls()
        for name in ["Scuola del Sabato", "Culto", "Pausa", "Pomeriggio"]:
            sched.add_section(name)
        return sched


def _default_name(slot_type: str) -> str:
    names = {
        "inno": "Inno",
        "versetto": "Versetto",
        "lezione": "Lezione",
        "predica": "Predica",
        "presentazione": "Presentazione",
        "timer": "Timer",
        "audio": "Audio",
        "video": "Video",
        "documento": "Documento",
        "qrcode": "QR Offerta",
        "immagine": "Immagine",
        "testo": "Testo",
        "campana": "Campana",
        "preghiera": "Preghiere",
        "altro": "Elemento",
    }
    return names.get(slot_type, "Elemento")

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Hymn:
    number: str          # es. "001", "025"
    title: str           # es. "Lode a Dio"
    file_path: str       # percorso assoluto al .pptx
    slides_text: List[str] = field(default_factory=list)
    audio_path: Optional[str] = None  # percorso al file audio, se presente

    @property
    def has_audio(self) -> bool:
        return self.audio_path is not None

    @property
    def full_text(self) -> str:
        return "\n\n".join(self.slides_text)

    @property
    def display_name(self) -> str:
        return f"{self.number} – {self.title}"

    def matches(self, query: str) -> bool:
        from core.textutil import normalize
        q = normalize(query)
        if not q:
            return True
        return (
            q in normalize(self.number)
            or q in normalize(self.title)
            or q in normalize(self.full_text)
        )

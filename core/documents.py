"""Document helpers: Word/text extraction (for projection) and QR generation."""
import os
from typing import List


def read_text_blocks(path: str) -> List[str]:
    """Return a list of text 'blocks' (stanzas) suitable for slide-by-slide projection.

    Blocks are separated by blank lines. Works for .docx and plain .txt.
    """
    ext = os.path.splitext(path)[1].lower()
    lines: List[str] = []
    if ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(path)
            lines = [p.text.rstrip() for p in doc.paragraphs]
        except Exception:
            return []
    else:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = [ln.rstrip() for ln in f.readlines()]
        except Exception:
            return []

    blocks: List[str] = []
    current: List[str] = []
    for ln in lines:
        if ln.strip():
            current.append(ln.strip())
        else:
            if current:
                blocks.append("\n".join(current))
                current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def generate_qr(data: str, out_path: str) -> str:
    """Generate a QR code PNG for `data`, save to out_path, return the path."""
    import qrcode
    img = qrcode.make(data)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path)
    return out_path

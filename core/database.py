import os
import re
import json
import hashlib
from typing import List, Callable, Optional
from pptx import Presentation
from core.hymn import Hymn

from core.paths import config_dir

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac")

_CACHE_DIR = os.path.join(config_dir(), "db_cache")


def _cache_path(folder: str) -> str:
    h = hashlib.md5(os.path.abspath(folder).encode("utf-8")).hexdigest()[:16]
    return os.path.join(_CACHE_DIR, h + ".json")


def _folder_signature(folder: str) -> dict:
    """Map of pptx filename → mtime, to detect changes."""
    sig = {}
    for f in os.listdir(folder):
        if f.lower().endswith(".pptx") and not f.startswith("~"):
            try:
                sig[f] = os.path.getmtime(os.path.join(folder, f))
            except OSError:
                sig[f] = 0
    return sig


def _find_audio(pptx_path: str) -> Optional[str]:
    """Cerca un file audio con lo stesso nome base del PPTX nella stessa cartella."""
    base = os.path.splitext(pptx_path)[0]
    for ext in AUDIO_EXTENSIONS:
        candidate = base + ext
        if os.path.isfile(candidate):
            return candidate
    return None


def _extract_number_title(filename: str):
    """Estrae numero e titolo dal nome file. Es: '025 - Gioia nel Signore.pptx'"""
    name = os.path.splitext(filename)[0]
    # Prova pattern: "NNN - Titolo" o "NNN_Titolo" o "NNN Titolo"
    match = re.match(r'^(\d+)\s*[-_]?\s*(.+)$', name)
    if match:
        return match.group(1).zfill(3), match.group(2).strip()
    return name, name


def _read_pptx_text(path: str) -> List[str]:
    """Legge il testo di ogni slide del PPTX."""
    try:
        prs = Presentation(path)
        slides_text = []
        for slide in prs.slides:
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        line = "".join(run.text for run in para.runs).strip()
                        if line:
                            texts.append(line)
            if texts:
                slides_text.append("\n".join(texts))
        return slides_text
    except Exception:
        return []


def _load_cache(folder: str) -> Optional[List[Hymn]]:
    """Return cached hymns if the cache matches the folder's current files."""
    path = _cache_path(folder)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("signature") != _folder_signature(folder):
            return None
        hymns = []
        for d in data.get("hymns", []):
            hymns.append(Hymn(number=d["number"], title=d["title"],
                              file_path=d["file_path"], slides_text=d.get("slides_text", []),
                              audio_path=d.get("audio_path")))
        return hymns
    except Exception:
        return None


def _save_cache(folder: str, hymns: List[Hymn]):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    data = {
        "signature": _folder_signature(folder),
        "hymns": [
            {"number": h.number, "title": h.title, "file_path": h.file_path,
             "slides_text": h.slides_text, "audio_path": h.audio_path}
            for h in hymns
        ],
    }
    try:
        with open(_cache_path(folder), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def load_database(
    folder: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[Hymn]:
    """
    Carica tutti i file .pptx da una cartella e costruisce l'indice.
    Usa una cache (config/db_cache) per evitare di ri-parsare i PPTX ad ogni avvio:
    il parsing avviene solo se i file sono cambiati.
    """
    if not folder or not os.path.isdir(folder):
        return []

    cached = _load_cache(folder)
    if cached is not None:
        if progress_callback:
            progress_callback(len(cached), len(cached), "")
        return cached

    files = sorted([
        f for f in os.listdir(folder)
        if f.lower().endswith(".pptx") and not f.startswith("~")
    ])

    hymns = []
    total = len(files)
    for i, filename in enumerate(files):
        if progress_callback:
            progress_callback(i, total, filename)
        path = os.path.join(folder, filename)
        number, title = _extract_number_title(filename)
        slides = _read_pptx_text(path)
        audio = _find_audio(path)
        hymns.append(Hymn(number=number, title=title, file_path=path, slides_text=slides, audio_path=audio))

    if progress_callback:
        progress_callback(total, total, "")

    _save_cache(folder, hymns)
    return hymns


def get_database_folders(root: str) -> List[str]:
    """Restituisce le sottocartelle (o la cartella root stessa) che contengono PPTX."""
    if not root or not os.path.isdir(root):
        return []
    # Se la cartella root contiene direttamente PPTX, è già un database
    entries = []
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if os.path.isdir(full):
            has_pptx = any(f.lower().endswith(".pptx") for f in os.listdir(full))
            if has_pptx:
                entries.append(full)
    # Se nessuna sottocartella ha PPTX, prova la root stessa
    if not entries:
        has_pptx = any(f.lower().endswith(".pptx") for f in os.listdir(root))
        if has_pptx:
            entries.append(root)
    return entries

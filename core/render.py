"""Render document pages to images for in-app projection.

PPTX/PPT are no longer rendered here — hymns and presentations are projected by
driving the real PowerPoint slideshow (see core/projector.py). Only PDFs are
rasterised in-app.
"""
from typing import List


def render_pdf(path: str, dpi: int = 150) -> List["PIL.Image.Image"]:
    """Render every page of a PDF to a list of PIL images."""
    import fitz  # PyMuPDF
    from PIL import Image
    images = []
    doc = fitz.open(path)
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            images.append(img.convert("RGB"))
    finally:
        doc.close()
    return images

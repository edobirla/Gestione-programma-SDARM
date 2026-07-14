"""Generate the app icon (PNG master + .icns for macOS + .ico for Windows)
from the official SDARM logo (assets/app_icon_source.png — wing over open
book on a blue rounded square, provided by the user on 2026-07-07).

    python3 packaging/generate_icon.py
"""
import os
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
SOURCE = os.path.join(ASSETS, "app_icon_source.png")


def load_source() -> Image.Image:
    if not os.path.isfile(SOURCE):
        raise SystemExit(f"manca il logo sorgente: {SOURCE}")
    return Image.open(SOURCE).convert("RGBA")


def full_square(img: Image.Image, canvas: int = 1024) -> Image.Image:
    """macOS 26+ masks every app icon into the system squircle and puts a
    gray/white backing plate behind any icon that doesn't fill the whole
    square — which made the logo look framed ("contorno grigio"). Fix: turn
    every not-fully-opaque pixel (the transparent corners AND the logo's
    anti-aliased rounded-rect edge, whose stray RGB values would otherwise
    leave a faint darker ring) into solid logo-blue. Result: a uniform
    edge-to-edge blue square with the white glyph; macOS rounds the corners
    itself, so the icon arrives whole, with no plate and no seam."""
    blue = img.getpixel((canvas // 2, 30))  # sampled from the logo's flat edge
    out = img.copy()
    alpha = out.split()[3]
    not_opaque = alpha.point(lambda v: 255 if v < 255 else 0)
    solid = Image.new("RGBA", out.size, blue)
    out.paste(solid, (0, 0), not_opaque)
    return out


def main():
    src = load_source()

    # PNG master (as provided, near full-bleed)
    png_path = os.path.join(ASSETS, "app_icon.png")
    src.save(png_path)
    print("scritto", png_path)

    # Windows .ico — full-bleed is the Windows convention
    ico_path = os.path.join(ASSETS, "app_icon.ico")
    src.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                              (64, 64), (128, 128), (256, 256)])
    print("scritto", ico_path)

    # macOS .icns via iconutil — full square (see full_square docstring)
    if sys.platform == "darwin":
        mac_master = full_square(src)
        iconset = os.path.join(ASSETS, "app_icon.iconset")
        os.makedirs(iconset, exist_ok=True)
        for pts in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = pts * scale
                name = f"icon_{pts}x{pts}" + ("@2x" if scale == 2 else "") + ".png"
                mac_master.resize((px, px), Image.LANCZOS).save(os.path.join(iconset, name))
        icns_path = os.path.join(ASSETS, "app_icon.icns")
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns_path], check=True)
        import shutil
        shutil.rmtree(iconset, ignore_errors=True)
        print("scritto", icns_path)


if __name__ == "__main__":
    main()

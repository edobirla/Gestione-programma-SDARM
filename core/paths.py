"""Where the app reads bundled resources and writes user data.

Running from source (the historical layout): everything lives inside the
project folder itself — config/, bibles/ — exactly as it always has, so a
development checkout keeps behaving identically and the user's live data is
untouched.

Running frozen (a PyInstaller-built .app/.exe): the bundle is read-only, so
anything the app WRITES (settings, caches, saved scalette, imported bibles)
moves to the platform's per-user data folder:
  macOS   → ~/Library/Application Support/Gestione programma SDARM
  Windows → %APPDATA%\\Gestione programma SDARM
  Linux   → $XDG_DATA_HOME (or ~/.local/share)/Gestione programma SDARM
Bundled read-only resources (assets/, the seed bibles) are read from inside
the bundle; the seed bibles are copied into the user folder on first run so
the in-app ".bib import" can keep writing new versions next to them.
"""
import os
import shutil
import sys

APP_NAME = "Gestione programma SDARM"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> str:
    """Root of read-only bundled files (bibles seed, assets). Frozen: the
    PyInstaller extraction dir; from source: the project folder itself."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_data_root() -> str:
    """Root of everything the app writes. From source this is the project
    folder itself — identical to the pre-paths.py behavior."""
    if not is_frozen():
        return resource_root()
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP_NAME)


def config_dir() -> str:
    d = os.path.join(user_data_root(), "config")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def bibles_dir() -> str:
    """The folder the app reads bibles from — and writes new .bib imports
    to. Frozen: the per-user copy, seeded once from the bundled bibles (new
    bundled bibles in a future update are also picked up, existing user
    files are never overwritten)."""
    if not is_frozen():
        return os.path.join(resource_root(), "bibles")
    d = os.path.join(user_data_root(), "bibles")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return d
    bundled = os.path.join(resource_root(), "bibles")
    if os.path.isdir(bundled):
        for f in os.listdir(bundled):
            if not f.lower().endswith(".db"):
                continue
            target = os.path.join(d, f)
            if not os.path.isfile(target):
                try:
                    shutil.copy2(os.path.join(bundled, f), target)
                except OSError:
                    pass
    return d

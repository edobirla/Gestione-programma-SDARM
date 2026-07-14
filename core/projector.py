"""Drive Microsoft PowerPoint's slideshow from the app.

Hymns/presentations are projected by launching PowerPoint's real slideshow on
the external display (no Keynote, no PNG export). The show lands on whichever
monitor PowerPoint is configured for — PowerPoint remembers the Monitor and
"Use Presenter View" settings, so the operator sets them once.

Slide advance and ending the show are driven from the app so the operator never
has to touch the projected screen:
  * macOS  → AppleScript (verified against PowerPoint.sdef).
  * Windows→ PowerPoint COM (best-effort; no-op if pywin32 is missing).
"""
import sys
import subprocess
import os

_PP_MAC = "Microsoft PowerPoint"

# Launching a console-mode exe from a windowed app briefly flashes a console
# window on Windows unless this flag is set. No-op / never referenced elsewhere.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _osascript(script: str, timeout: int = 60) -> bool:
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


def _mac_present_script(path: str) -> str:
    p = path.replace("\\", "\\\\").replace('"', '\\"')
    return (
        'tell application "Microsoft PowerPoint"\n'
        '    activate\n'
        f'    open POSIX file "{p}"\n'
        '    run slide show slide show settings of active presentation\n'
        'end tell'
    )


def _mac_show_cmd(cmd: str) -> bool:
    """Run a command against the currently-running slideshow's view."""
    return _osascript(
        'tell application "Microsoft PowerPoint"\n'
        f'    {cmd} (slide show view of slide show window 1)\n'
        'end tell', timeout=15)


def _win_show_action(action: str) -> bool:
    """Best-effort control of a running show on Windows via COM. Needs pywin32;
    no-op otherwise (the operator can still use a presenter remote/keyboard)."""
    try:
        import win32com.client  # type: ignore
        app = win32com.client.GetActiveObject("PowerPoint.Application")
        view = app.SlideShowWindows(1).View
        {"Next": view.Next, "Previous": view.Previous, "Exit": view.Exit}[action]()
        return True
    except Exception:
        return False


def present_powerpoint(file_path: str) -> bool:
    """Open the file in PowerPoint and start its slideshow. Returns True if
    launched. The target monitor is whatever PowerPoint is set to use."""
    if not file_path or not os.path.isfile(file_path):
        return False
    # The schedule stores paths relative to the app's folder, but AppleScript's
    # `POSIX file` (and a clean launch on Windows) need an absolute path — a
    # relative one makes PowerPoint hang on a "file not found" dialog.
    file_path = os.path.abspath(file_path)

    if sys.platform == "win32":
        # /s launches straight into the slideshow using PowerPoint's settings.
        try:
            subprocess.Popen(["powerpnt.exe", "/s", file_path])
            return True
        except FileNotFoundError:
            try:
                os.startfile(file_path)  # type: ignore[attr-defined]
                return True
            except Exception:
                return False

    if sys.platform == "darwin":
        if _osascript(_mac_present_script(file_path)):
            return True
        # Fallback: at least open the file in PowerPoint (edit mode).
        try:
            subprocess.Popen(["open", "-a", _PP_MAC, file_path])
            return True
        except Exception:
            return False

    # Linux fallback
    try:
        subprocess.Popen(["libreoffice", "--impress", "--show", file_path])
        return True
    except Exception:
        return False


def powerpoint_next() -> bool:
    if sys.platform == "darwin":
        return _mac_show_cmd("go to next slide")
    if sys.platform == "win32":
        return _win_show_action("Next")
    return False


def powerpoint_prev() -> bool:
    if sys.platform == "darwin":
        return _mac_show_cmd("go to previous slide")
    if sys.platform == "win32":
        return _win_show_action("Previous")
    return False


def powerpoint_end() -> bool:
    if sys.platform == "darwin":
        return _mac_show_cmd("exit slide show")
    if sys.platform == "win32":
        return _win_show_action("Exit")
    return False


def open_file_external(file_path: str):
    """Open any file (PDF, Word, ...) with the OS default application."""
    if not file_path or not os.path.isfile(file_path):
        return
    if sys.platform == "win32":
        os.startfile(file_path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", file_path])
    else:
        subprocess.Popen(["xdg-open", file_path])

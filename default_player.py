"""Register / unregister Quiet Player with Windows as a video player.

Windows 10/11 do not let an app make itself the default silently. What an app
*can* do is register itself (per user, no admin needed) so it shows up in
"Open with" and in Settings > Apps > Default apps. The user then makes the
final choice there. Everything here lives under HKEY_CURRENT_USER and is
removed again by unregister().
"""

import os
import sys

APP_NAME = "Quiet Player"
PROG_ID = "QuietPlayer.Video"
APP_KEY = r"Software\QuietPlayer"
CAPS_KEY = APP_KEY + r"\Capabilities"
CLASSES = "Software\\Classes\\"
REGISTERED_APPS = r"Software\RegisteredApplications"

SHCNE_ASSOCCHANGED = 0x08000000


def launch_command():
    """Command line Windows runs to open a file: '"<exe>" ["<script>"] "%1"'."""
    if getattr(sys, "frozen", False):        # installed QuietPlayer.exe
        return f'"{sys.executable}" "%1"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):                  # no console window flashing up
        exe = pyw
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quiet_player.py")
    return f'"{exe}" "{script}" "%1"'


def _icon():
    """File-type icon: the .exe's own icon, or quiet_player.ico when run from source."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}",0'
    ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quiet_player.ico")
    if os.path.exists(ico):
        return f'"{ico}",0'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return f'"{pyw if os.path.exists(pyw) else exe}",0'


def _set(winreg, path, name, value):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _delete_tree(winreg, path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(winreg, path + "\\" + sub)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


def _delete_value(winreg, path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass


def _notify_shell():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, 0, None, None)
    except Exception:
        pass


def register(exts):
    """Register for the given extensions (e.g. ['.mp4', '.mkv']). Windows only."""
    import winreg
    prog = CLASSES + PROG_ID
    _set(winreg, prog, "", f"Video file ({APP_NAME})")
    _set(winreg, prog + r"\DefaultIcon", "", _icon())
    _set(winreg, prog + r"\shell", "", "open")
    _set(winreg, prog + r"\shell\open", "FriendlyAppName", APP_NAME)
    _set(winreg, prog + r"\shell\open\command", "", launch_command())

    _set(winreg, CAPS_KEY, "ApplicationName", APP_NAME)
    _set(winreg, CAPS_KEY, "ApplicationDescription",
         "Video player with a control bar that stays out of the way.")
    for ext in exts:
        _set(winreg, CAPS_KEY + r"\FileAssociations", ext, PROG_ID)
        # Adds Quiet Player to this extension's "Open with" list. Does NOT
        # change the current default; the user picks that in Settings.
        _set(winreg, CLASSES + ext + r"\OpenWithProgids", PROG_ID, "")
    _set(winreg, REGISTERED_APPS, APP_NAME, CAPS_KEY)
    _notify_shell()


def unregister(exts):
    """Remove everything register() added. Other apps' settings are untouched."""
    import winreg
    for ext in exts:
        _delete_value(winreg, CLASSES + ext + r"\OpenWithProgids", PROG_ID)
    _delete_value(winreg, REGISTERED_APPS, APP_NAME)
    _delete_tree(winreg, APP_KEY)
    _delete_tree(winreg, CLASSES + PROG_ID)
    _notify_shell()


def is_registered():
    """True if any registration exists, even one pointing at an old Python/script
    path, so "Remove" stays available to clean it up."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTERED_APPS) as k:
            winreg.QueryValueEx(k, APP_NAME)
        return True
    except (ImportError, OSError):
        pass
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLASSES + PROG_ID).Close()
        return True
    except OSError:
        return False


def open_default_apps_settings():
    """Open Settings > Default apps. The registeredAppUser parameter is meant to jump
    to Quiet Player's own page, but Windows 11 25H2 (build 26200) ignores it and
    shows the Default apps list, so the message tells the user to search there."""
    uri = "ms-settings:defaultapps?registeredAppUser=" + APP_NAME.replace(" ", "%20")
    try:
        os.startfile(uri)
    except (AttributeError, OSError):
        try:
            os.startfile("ms-settings:defaultapps")
        except (AttributeError, OSError):
            pass

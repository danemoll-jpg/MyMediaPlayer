"""Updates and self-install for the packaged Quiet Player (QuietPlayer.exe).

How an update happens (nothing is ever shown unless the user asks from the
⋯ menu):
  1. At most once a day the player fetches update-catalog.json from the latest
     GitHub release of danemoll-jpg/quiet-player-releases. The catalog is
     signed (RSA-PKCS1-SHA256) with the publisher's key; the public half is
     pinned below, so a catalog that doesn't verify is ignored.
  2. If it names a newer version, the ZIP is downloaded, checked against the
     size and SHA-256 in the signed catalog, and unpacked next to the app
     folder as "<app folder>.update".
  3. When the player closes, a hidden PowerShell step waits for it to exit,
     renames the app folder to "<app folder>.previous" and "<app
     folder>.update" into its place. If anything holds the folder, nothing
     changes and it tries again on the next close. The new version deletes
     ".previous" when it starts.

No Qt in here: quiet_player.py does the UI side.
"""

import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

APP_VERSION = "1.0.1"
PRODUCT = "quiet-player"
RELEASES_REPO = "danemoll-jpg/quiet-player-releases"
CATALOG_URL = f"https://github.com/{RELEASES_REPO}/releases/latest/download/update-catalog.json"
CHECK_EVERY_S = 20 * 3600       # automatic checks: at most this often
ZIP_APP_FOLDER = "QuietPlayer"  # the app's folder inside the release ZIP
EXE_NAME = "QuietPlayer.exe"
MARKER = "quietplayer-update.json"   # written into "<app>.update" once it is complete

# The publisher's public key (Builds: PublisherPrivate/quiet-player-signing.pem).
KEY_ID = "bc28e96ac31c548df76dbb14952f826aee528060b3531d87901e371a643e1ec9"
_MODULUS = int(
    "b769ab4c42fa6aa49990ac8f15a970cc8c86efbdc0f9cdff36fc8d58b2533c769eccd802"
    "547820ecaf1f97c271d97006fa57ebcb33887171248bd4d859dfb27e0a0c0acebdb41af3"
    "e61560ab5aa147366580fdf6b253c18be6df06984288b17474bb067f98ca3b4eb311693c"
    "b8c39861b272a305e0f1a24637e80eec5a2c61a1e8a84ad7c9a090f3519ff677b59fefc5"
    "520150357a8b3d53827564fdfbb60ebe674aa3d5d3eec6db4f219bbd6df9ceb9692189f3"
    "6f17d2f72eb16de323f3cc941ed819a8f66fc894601cf9c46132295f753f8fc7c8c4c6dd"
    "05a781febbce850a642db75b3f8a8f0568544c9f62eb280ffbb0b0333810e7b7f8b74c90"
    "2ecdc4246d41c26bbcdb2e6199d6deac932a6d77321413f37ebc2a4dd299d7da9a8af956"
    "d4834cf92550a9f85b1570ac85bd8f243445d45ddde93b32984ef99d7bc9a6576c14fca7"
    "a5434c1942be09df9bed2cc3a05a433a0ab785988ed72957f3b440a6c4efd6e26a6ffb48"
    "61287e979d6664ff815e6135323a00a7b49e9c75a1050579", 16)
_EXPONENT = 65537
_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")

FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "QuietPlayer")
LOG_FILE = os.path.join(DATA_DIR, "update.log")
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                           "Programs", "QuietPlayer")
SHORTCUT = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                        "Microsoft", "Windows", "Start Menu", "Programs", "Quiet Player.lnk")
CREATE_NO_WINDOW = 0x08000000


class UpdateError(Exception):
    pass


def log(msg):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 200_000:
            os.replace(LOG_FILE, LOG_FILE + ".old")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {APP_VERSION} {msg}\n")
    except OSError:
        pass


def version_tuple(v):
    try:
        return tuple(int(p) for p in str(v).split("."))
    except ValueError:
        return ()


def is_newer(v, than=APP_VERSION):
    a, b = version_tuple(v), version_tuple(than)
    return bool(a) and a > b


# --- signed catalog ------------------------------------------------------------
def verify_signature(data, signature):
    """RSA PKCS#1 v1.5 with SHA-256 against the pinned key (exact encoding match)."""
    k = (_MODULUS.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= _MODULUS:
        return False
    em = pow(s, _EXPONENT, _MODULUS).to_bytes(k, "big")
    t = _SHA256_PREFIX + hashlib.sha256(data).digest()
    expected = b"\x00\x01" + b"\xff" * (k - 3 - len(t)) + b"\x00" + t
    return hmac.compare_digest(em, expected)


def catalog_url():
    return os.environ.get("QUIET_PLAYER_CATALOG") or CATALOG_URL   # override for tests only


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": f"QuietPlayer/{APP_VERSION}"})
    return urllib.request.urlopen(req, timeout=timeout)


def parse_catalog(raw):
    """Return the verified payload dict, or raise UpdateError."""
    try:
        outer = json.loads(raw)
        signed = base64.b64decode(outer["signed"], validate=True)
        sig = base64.b64decode(outer["signature"], validate=True)
    except (ValueError, KeyError, TypeError) as e:
        raise UpdateError(f"catalog unreadable: {e}")
    if outer.get("keyId") != KEY_ID or not verify_signature(signed, sig):
        raise UpdateError("catalog signature does not verify")
    try:
        p = json.loads(signed)
        pkg = p["package"]
        ok = (p.get("product") == PRODUCT and version_tuple(p["version"])
              and isinstance(pkg["url"], str) and int(pkg["size"]) > 0
              and len(pkg["sha256"]) == 64)
    except (ValueError, KeyError, TypeError):
        ok = False
    if not ok:
        raise UpdateError("catalog payload malformed")
    return p


def fetch_catalog(timeout=20):
    with _open(catalog_url(), timeout) as r:
        raw = r.read(1_000_000)
    return parse_catalog(raw)


# --- staging -------------------------------------------------------------------
def update_dir(app_dir=APP_DIR):
    return app_dir.rstrip("\\/") + ".update"


def previous_dir(app_dir=APP_DIR):
    return app_dir.rstrip("\\/") + ".previous"


def can_self_update(app_dir=APP_DIR):
    """Only the packaged app updates itself, and only where it can write next to itself."""
    if not FROZEN and not os.environ.get("QUIET_PLAYER_TEST_SOURCE_UPDATE"):
        return False
    parent = os.path.dirname(app_dir.rstrip("\\/"))
    return bool(parent) and os.access(parent, os.W_OK) and os.access(app_dir, os.W_OK)


def staged_version(app_dir=APP_DIR):
    """Version waiting in '<app>.update' if it is complete, else None."""
    d = update_dir(app_dir)
    try:
        with open(os.path.join(d, MARKER), encoding="utf-8") as f:
            v = json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return v if os.path.isfile(os.path.join(d, EXE_NAME)) else None


def _rmtree(path):
    if os.path.lexists(path):
        shutil.rmtree(path, ignore_errors=True)
    return not os.path.lexists(path)


def _download(url, dest, size, sha256, progress=None):
    h = hashlib.sha256()
    got = 0
    with _open(url, 60) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            got += len(chunk)
            if got > size:
                raise UpdateError("download larger than the catalog says")
            h.update(chunk)
            f.write(chunk)
            if progress:
                progress(got, size)
    if got != size:
        raise UpdateError(f"download incomplete ({got} of {size} bytes)")
    if not hmac.compare_digest(h.hexdigest(), sha256.lower()):
        raise UpdateError("download checksum does not match")


def _extract_app(zpath, dest):
    """Unpack ZIP_APP_FOLDER/* from the ZIP into dest (refusing unsafe paths)."""
    prefix = ZIP_APP_FOLDER + "/"
    root = os.path.abspath(dest)
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if not name.startswith(prefix) or name == prefix:
                continue
            rel = name[len(prefix):]
            target = os.path.abspath(os.path.join(root, *rel.split("/")))
            if not target.startswith(root + os.sep):
                raise UpdateError(f"unsafe path in ZIP: {name}")
            if name.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)
    if not os.path.isfile(os.path.join(dest, EXE_NAME)):
        raise UpdateError(f"ZIP has no {ZIP_APP_FOLDER}/{EXE_NAME}")


def stage(payload, app_dir=APP_DIR, progress=None):
    """Download and unpack payload's version as '<app>.update'. Runs off the UI thread."""
    version = payload["version"]
    pkg = payload["package"]
    if staged_version(app_dir) == version:
        return
    dl_dir = os.path.join(DATA_DIR, "download")
    os.makedirs(dl_dir, exist_ok=True)
    zpath = os.path.join(dl_dir, f"QuietPlayer-{version}.zip")
    tmp = app_dir.rstrip("\\/") + ".update-tmp"
    try:
        log(f"downloading {version} from {pkg['url']}")
        _download(pkg["url"], zpath + ".part", int(pkg["size"]), pkg["sha256"], progress)
        os.replace(zpath + ".part", zpath)
        if not _rmtree(tmp):
            raise UpdateError(f"cannot clear {tmp}")
        _extract_app(zpath, tmp)
        with open(os.path.join(tmp, MARKER), "w", encoding="utf-8") as f:
            json.dump({"version": version, "from": APP_VERSION,
                       "sha256": pkg["sha256"]}, f)
        if not _rmtree(update_dir(app_dir)):
            raise UpdateError(f"cannot clear {update_dir(app_dir)}")
        os.rename(tmp, update_dir(app_dir))
        log(f"staged {version} in {update_dir(app_dir)}")
    except Exception:
        _rmtree(tmp)
        raise
    finally:
        for p in (zpath, zpath + ".part"):
            try:
                os.remove(p)
            except OSError:
                pass


def check_and_stage(app_dir=APP_DIR, progress=None, on_found=None):
    """Returns (latest_version, staged: bool). Raises on network / verify errors."""
    payload = fetch_catalog()
    latest = payload["version"]
    if not is_newer(latest):
        log(f"checked: {latest} is the latest")
        return latest, False
    if on_found:
        on_found(latest)
    if not can_self_update(app_dir):
        log(f"checked: {latest} available, but this copy can't update itself")
        return latest, False
    stage(payload, app_dir, progress)
    return latest, True


def cleanup_on_start(app_dir=APP_DIR):
    """Remove what a finished update left: '.previous', and a staged version that
    isn't newer than this one (e.g. after install.bat put a newer build in place)."""
    if not can_self_update(app_dir):
        return
    if os.path.lexists(previous_dir(app_dir)):
        if _rmtree(previous_dir(app_dir)):
            log(f"started after update; removed {previous_dir(app_dir)}")
    v = staged_version(app_dir)
    if os.path.lexists(update_dir(app_dir)) and (v is None or not is_newer(v)):
        _rmtree(update_dir(app_dir))
    _rmtree(app_dir.rstrip("\\/") + ".update-tmp")


# --- swap after exit -----------------------------------------------------------
_SWAP_PS1 = r"""
param([int]$ProcId, [string]$App, [string]$Log)
$ErrorActionPreference = 'Stop'
$new = "$App.update"; $old = "$App.previous"; $leaf = Split-Path -Leaf $App
function Say($m) { try { Add-Content -LiteralPath $Log -Encoding UTF8 -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " swap: $m") } catch {} }
function Retry([scriptblock]$b) {
  for ($i = 0; $i -lt 20; $i++) { try { & $b; return $true } catch { Start-Sleep -Milliseconds 250 } }
  return $false
}
try { Wait-Process -Id $ProcId -Timeout 60 -ErrorAction SilentlyContinue } catch {}
Start-Sleep -Milliseconds 300
if (-not (Test-Path -LiteralPath "$new\QuietPlayer.exe")) { Say "nothing staged"; exit 1 }
if (Test-Path -LiteralPath $old) {
  if (-not (Retry { Remove-Item -LiteralPath $old -Recurse -Force })) { Say "cannot remove $old"; exit 2 }
}
if (-not (Retry { Rename-Item -LiteralPath $App -NewName (Split-Path -Leaf $old) })) {
  Say "app folder in use; trying again next time"; exit 3
}
if (-not (Retry { Rename-Item -LiteralPath $new -NewName $leaf })) {
  $null = Retry { Rename-Item -LiteralPath $old -NewName $leaf }
  Say "could not move the new version in; put the old one back"; exit 4
}
Remove-Item -LiteralPath "$App\quietplayer-update.json" -Force -ErrorAction SilentlyContinue
Say "installed"
exit 0
"""


def apply_on_exit(app_dir=APP_DIR):
    """Called as the player closes: start the hidden swap if an update is staged."""
    v = staged_version(app_dir)
    if not (v and is_newer(v) and can_self_update(app_dir)):
        return False
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        script = os.path.join(DATA_DIR, "apply-update.ps1")
        with open(script, "w", encoding="utf-8-sig") as f:
            f.write(_SWAP_PS1)
        ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                          "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        subprocess.Popen(
            [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", script,
             "-ProcId", str(os.getpid()), "-App", app_dir.rstrip("\\/"), "-Log", LOG_FILE],
            creationflags=CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True, cwd=DATA_DIR,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"closing: installing {v}")
        return True
    except OSError as e:
        log(f"could not start the swap: {e}")
        return False


# --- self-install (from the downloaded ZIP) ------------------------------------
def _unblock(folder):
    """Remove the 'downloaded from the internet' mark, or Windows would warn
    every time a video opens the installed player."""
    for dirpath, _dirs, files in os.walk(folder):
        for name in files:
            try:
                os.remove(os.path.join(dirpath, name) + ":Zone.Identifier")
            except OSError:
                pass


def _make_shortcut(target):
    os.makedirs(os.path.dirname(SHORTCUT), exist_ok=True)
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    cmd = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:QP_LNK);"
           "$s.TargetPath = $env:QP_EXE; $s.WorkingDirectory = (Split-Path $env:QP_EXE);"
           "$s.IconLocation = $env:QP_EXE + ',0'; $s.Description = 'Quiet Player'; $s.Save()")
    env = dict(os.environ, QP_LNK=SHORTCUT, QP_EXE=target)
    subprocess.run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-Command", cmd], env=env, check=True, creationflags=CREATE_NO_WINDOW,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install(src_dir=APP_DIR, dest_dir=None, shortcut=True, register=True):
    """Copy this app folder to dest_dir (default %LOCALAPPDATA%\\Programs\\QuietPlayer),
    add a Start menu shortcut and register for "Open with". Returns the installed exe.
    Raises UpdateError with a message for the user."""
    dest_dir = os.path.abspath(dest_dir or INSTALL_DIR).rstrip("\\/")
    src_dir = os.path.abspath(src_dir).rstrip("\\/")
    exe = os.path.join(dest_dir, EXE_NAME)
    if os.path.normcase(src_dir) != os.path.normcase(dest_dir):
        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
        new, old = dest_dir + ".update", dest_dir + ".previous"
        if not (_rmtree(new) and _rmtree(old)):
            raise UpdateError(f"Couldn't clear {new} or {old}.")
        shutil.copytree(src_dir, new, ignore=shutil.ignore_patterns(MARKER))
        if os.path.exists(dest_dir):
            try:
                os.rename(dest_dir, old)
            except OSError:
                _rmtree(new)
                raise UpdateError("Quiet Player is open. Close it, then run the installer again.")
        os.rename(new, dest_dir)
        _rmtree(old)
    _unblock(dest_dir)
    if register:
        r = subprocess.run([exe, "--register"], creationflags=CREATE_NO_WINDOW)
        if r.returncode != 0:
            raise UpdateError("Registering with Windows failed.")
    if shortcut:
        try:
            _make_shortcut(exe)
        except (OSError, subprocess.CalledProcessError):
            raise UpdateError("Creating the Start menu shortcut failed.")
    log(f"installed {APP_VERSION} to {dest_dir}")
    return exe

"""Build, sign and publish a Quiet Player release (publisher only).

  python release.py build [--base-url URL] [--notes TEXT]
      Builds QuietPlayer.exe (same PyInstaller settings as install.bat), packs
      release\\<version>\\QuietPlayer-<version>.zip and writes the signed
      update-catalog.json beside it. The version is updater.APP_VERSION.
      --base-url: where the ZIP will be served (default: the GitHub release).

  python release.py publish --confirm-repository danemoll-jpg/quiet-player-releases
      Uploads release\\<version>\\ as GitHub release v<version>, marked Latest
      (every installed copy then updates to it). Add --not-latest to upload
      without making it Latest (then: gh release edit v<version> --latest).
      --version X publishes the earlier build in release\\X instead.

The signing key is PublisherPrivate\\quiet-player-signing.pem (git-ignored).
Never delete, print or replace it: installed copies only trust that key.
"""

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile

import updater

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(ROOT, "PublisherPrivate", "quiet-player-signing.pem")
GH_CANDIDATES = [shutil.which("gh") or "",
                 r"C:\Users\danmo\Racer\Builds\PublisherTools\gh-2.101.0\bin\gh.exe"]
VERSION = updater.APP_VERSION
OUT = os.path.join(ROOT, "release", VERSION)
ZIP_NAME = f"QuietPlayer-{VERSION}.zip"

INSTALL_BAT = """@echo off
rem Installs Quiet Player for this Windows user (no admin needed).
start "" "%~dp0QuietPlayer\\QuietPlayer.exe" --install
"""

README = """Quiet Player {version}
==================

A Windows video player for local files whose control bar stays out of the
way: it never covers the video, hides instantly, and only comes back when you
press Tab or middle-click the video.

Install
-------
1. Extract this ZIP anywhere (right-click > Extract All).
2. Double-click "Install Quiet Player.bat".
   Windows may say "Windows protected your PC" because the app isn't signed
   by a big publisher: click "More info", then "Run anyway".
3. It installs to %LOCALAPPDATA%\\Programs\\QuietPlayer, adds Quiet Player to
   the Start menu and offers to make it your default video player.
   After that you can delete the extracted folder.

Updates
-------
Quiet Player keeps itself up to date. About once a day it checks for a new
version in the background, downloads it, and installs it the next time you
close the player. Nothing pops up. To check now: ... (bottom right of the
control bar) > Check for updates. Updates are signed; a download that doesn't
match the signature is thrown away.

Keys
----
Space play/pause, Left/Right 10 s, Shift+Left/Right 60 s, Up/Down volume,
M mute, F fullscreen, N/P next/previous video in the folder, S subtitles,
A audio track, Tab show/hide the control bar. Full list: ... > Keyboard shortcuts.

Uninstall
---------
... > Remove Quiet Player from Windows, close the player, then delete
%LOCALAPPDATA%\\Programs\\QuietPlayer and the Quiet Player Start menu shortcut.
Your resume positions and settings are in %APPDATA%\\QuietPlayer.

Licences: QuietPlayer\\LICENSES\\THIRD-PARTY-NOTICES.txt
Source: https://github.com/danemoll-jpg/MyMediaPlayer
"""


def run(cmd, **kw):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True, **kw)


def build_exe(work):
    dll = os.path.join(ROOT, "libmpv-2.dll")
    if not os.path.isfile(dll):
        sys.exit("libmpv-2.dll is missing (see TODO.md for where it comes from).")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
         "--windowed", "--name", "QuietPlayer", "--icon", os.path.join(ROOT, "quiet_player.ico"),
         "--contents-directory", ".",
         "--exclude-module", "PIL", "--exclude-module", "numpy", "--exclude-module", "tkinter",
         "--add-binary", f"{dll};.",
         "--add-data", f"{os.path.join(ROOT, 'quiet_player.ico')};.",
         "--specpath", work, "--workpath", work, "--distpath", os.path.join(work, "dist"),
         os.path.join(ROOT, "quiet_player.py")])
    app = os.path.join(work, "dist", "QuietPlayer")
    if not os.path.isfile(os.path.join(app, "QuietPlayer.exe")):
        sys.exit("Build produced no QuietPlayer.exe.")
    shutil.copytree(os.path.join(ROOT, "licenses"), os.path.join(app, "LICENSES"))
    return app


def make_zip(app, zpath):
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _dirs, files in os.walk(app):
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, app).replace(os.sep, "/")
                z.write(full, f"{updater.ZIP_APP_FOLDER}/{rel}")
        z.writestr("Install Quiet Player.bat", INSTALL_BAT.replace("\n", "\r\n"))
        z.writestr("README.txt", README.format(version=VERSION).replace("\n", "\r\n"))


def sign(data):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    with open(KEY_FILE, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    if key.public_key().public_numbers().n != updater._MODULUS:
        sys.exit("The signing key doesn't match the key pinned in updater.py.")
    sig = key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    if not updater.verify_signature(data, sig):
        sys.exit("Signature self-check failed.")
    return sig


def cmd_build(args):
    if not os.path.isfile(KEY_FILE):
        sys.exit(f"Signing key missing: {KEY_FILE}")
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    work = os.path.join(ROOT, "build", "release")
    shutil.rmtree(work, ignore_errors=True)
    app = build_exe(work)
    zpath = os.path.join(OUT, ZIP_NAME)
    make_zip(app, zpath)
    h = hashlib.sha256()
    with open(zpath, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    base = args.base_url or f"https://github.com/{updater.RELEASES_REPO}/releases/download/v{VERSION}/"
    payload = {
        "product": updater.PRODUCT,
        "version": VERSION,
        "published": time.strftime("%Y-%m-%d"),
        "notes": args.notes or "",
        "package": {"url": base.rstrip("/") + "/" + ZIP_NAME,
                    "size": os.path.getsize(zpath), "sha256": h.hexdigest()},
    }
    data = json.dumps(payload, indent=1).encode("utf-8")
    catalog = {"format": 1, "keyId": updater.KEY_ID,
               "signed": base64.b64encode(data).decode("ascii"),
               "signature": base64.b64encode(sign(data)).decode("ascii")}
    with open(os.path.join(OUT, "update-catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=1)
    updater.parse_catalog(json.dumps(catalog))      # what the app will do with it
    with open(os.path.join(OUT, "notes.md"), "w", encoding="utf-8") as f:
        f.write(f"Quiet Player {VERSION}\n\n{args.notes or ''}\n\n"
                f"**Download:** {ZIP_NAME} below. Extract it and double-click "
                "`Install Quiet Player.bat`. Installed copies update themselves.\n")
    print(f"\n{zpath}\n  {os.path.getsize(zpath) / 1e6:.1f} MB, sha256 {h.hexdigest()}"
          f"\n  url {payload['package']['url']}")


def gh():
    for c in GH_CANDIDATES:
        if c and os.path.isfile(c):
            return c
    sys.exit("gh (GitHub CLI) not found.")


def cmd_publish(args):
    if args.confirm_repository != updater.RELEASES_REPO:
        sys.exit(f"Pass --confirm-repository {updater.RELEASES_REPO} to publish.")
    version = args.version or VERSION
    out = os.path.join(ROOT, "release", version)
    zpath = os.path.join(out, f"QuietPlayer-{version}.zip")
    catalog = os.path.join(out, "update-catalog.json")
    with open(catalog, encoding="utf-8") as f:
        payload = updater.parse_catalog(f.read())
    if payload["version"] != version or not payload["package"]["url"].startswith(
            f"https://github.com/{updater.RELEASES_REPO}/releases/download/v{version}/"):
        sys.exit("The catalog was built for a different version or URL; run build again.")
    cmd = [gh(), "release", "create", f"v{version}", zpath, catalog,
           "--repo", updater.RELEASES_REPO, "--title", f"Quiet Player {version}",
           "--notes-file", os.path.join(out, "notes.md")]
    cmd.append("--latest=false" if args.not_latest else "--latest")
    run(cmd)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--base-url")
    b.add_argument("--notes")
    p = sub.add_parser("publish")
    p.add_argument("--confirm-repository", required=True)
    p.add_argument("--not-latest", action="store_true")
    p.add_argument("--version", help="an earlier build in release/<version> (default: APP_VERSION)")
    args = ap.parse_args()
    {"build": cmd_build, "publish": cmd_publish}[args.cmd](args)


if __name__ == "__main__":
    main()

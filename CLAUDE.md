# Project Context & Rules — Quiet Player

## Location
- Project repo: `C:\Users\danmo\MyMediaPlayer`
- `TODO.md` and `CLAUDE.md` live at the repo root.

## Tech Stack
- Windows 11 desktop app for playing local video files.
- Python 3.11+, PySide6 (Qt) for the window and control bar.
- python-mpv (libmpv) for playback, embedded into a Qt widget via `wid`.
- Requires `libmpv-2.dll` next to the script or on PATH.

## Code Style & Architecture
- The whole point of this app is an unobtrusive control bar. The rules below
  are requirements, not preferences:
  - The control bar never overlays the video. It lives in its own strip
    below the video; the video resizes when the bar is shown or hidden.
  - The bar never appears on its own. Only `Tab` or middle-click on the video
    shows it. Mouse movement, hover, pause, file load, end of file and
    fullscreen changes must not show it.
  - Hiding is instant (no animation).
- mpv's own UI and input are fully disabled (`osc=no`, `osd-level=0`,
  `input-default-bindings=no`, `input-vo-keyboard=no`, `input-cursor=no`).
  The app owns all input.
- Keyboard shortcuts are handled at the window level so focus on a bar widget
  can never hijack Space or the arrow keys.
- Never bind anything to mouse side buttons (owner has them disabled).
- Keep it small: `quiet_player.py` is the app; `default_player.py` holds the
  Windows registry code for "make default" (HKCU only, never touch other
  apps' associations). `make_icon.py` draws `quiet_player.ico`;
  `install.bat` builds the .exe and installs it. `updater.py` holds
  `APP_VERSION`, the signed-catalog check, download, swap-on-close and
  `--install` (no Qt in it); `release.py` builds, signs and publishes.
- Updates are silent: automatic checks never show anything (no dialog, no
  corner text, never the bar). Only the ⋯ menu's "Check for updates"
  reports, via the corner text. A staged update installs after the player
  closes, never while it runs.

## Commands
```
pip install PySide6 python-mpv pyinstaller pillow
python quiet_player.py [optional path to video]   # run from source (dev)
install.bat                    # build + install to %LOCALAPPDATA%\Programs\QuietPlayer
QuietPlayer.exe --register     # point QuietPlayer.Video at this exe, no window
QuietPlayer.exe --install      # what the ZIP's "Install Quiet Player.bat" runs
```

Publishing a new version (public, so only when the owner asks):
```
# bump APP_VERSION in updater.py and commit, then:
python release.py build --notes "What changed."      # -> release\<version>\
python release.py publish --confirm-repository danemoll-jpg/quiet-player-releases
```
Every installed copy (the owner's included) picks it up within a day and
installs it on close. Releases live in `danemoll-jpg/quiet-player-releases`
(gh: `C:\Users\danmo\Racer\Builds\PublisherTools\gh-2.101.0\bin\gh.exe`).
The signing key `PublisherPrivate\quiet-player-signing.pem` is git-ignored:
never delete, print or replace it (installed copies only trust that key).
Test an update with `QUIET_PLAYER_CATALOG=<a release's update-catalog.json
URL>` (plus `QUIET_PLAYER_CHECK_DELAY_MS`), scratch `APPDATA`/`LOCALAPPDATA`,
and `--install --install-to <dir> --no-register --no-shortcut --quiet`.
Download card: `C:\Users\danmo\game-hub\games.js` (`quiet-player`).

## Where things stand
**Before starting any work, commit any uncommitted changes** (planning
updates to `TODO.md`/`CLAUDE.md` are often dropped into the repo between
sessions). Then check `TODO.md` for the current objective. Never drop this
rule when rewriting this file.

Rounds 1–4 are complete and the installed .exe is the owner's default
video player (ProgID `QuietPlayer.Video`; keep it, never unregister).
Round 5 (speed, frame step, mute, remembered volume, recent files,
shortcuts dialog) and Round 6 (public download that keeps itself up to
date; 1.0.1 published) are built and tested; they are finished once the
owner runs `install.bat` from Explorer (see `TODO.md`). No next round is
planned yet. Updates reach the owner's PC by him
double-clicking `install.bat` in Explorer: registry writes from a Claude Code
session are virtualized and never reach Explorer. For each round, report a
status for every numbered item individually, and batch the round into one
set of changes.

- **Registry writes from a Claude Code session never reach the real
  registry.** They go to a private copy that only the session's own
  processes see, so in-session `reg query`, PowerShell and
  `AssocQueryString` will happily show your writes. File writes are real. To
  see what Windows really has, read it from a process Explorer starts (e.g.
  a probe `.bat` double-clicked in a test Explorer window that runs
  `reg query` into a file). Any real registration change (`install.bat`,
  `--register`) has to be run by the owner from Explorer.

- Real-input tests (SendInput) must check, before every click or key, that
  the target window belongs to the test, and abort otherwise. The owner's
  other windows may be in front.
- Never click "Set default" in Settings or otherwise change the owner's real
  file associations during tests. Use a throwaway extension mapped to
  `QuietPlayer.Video` instead.

- `libmpv-2.dll` sits next to the script and is git-ignored, so a fresh clone
  needs it re-downloaded (source noted in `TODO.md`).
- The corner indicator uses mpv `show-text` with level 0. Apart from the
  video, it and subtitles are the only things mpv draws.
- Resume positions live in `%APPDATA%\QuietPlayer\positions.json`. Tests
  should point `APPDATA` at a scratch folder so the owner's file isn't
  touched.
- The owner's default-app choice lives in
  `FileExts\<ext>\UserChoiceLatest\ProgId` on this Windows build (25H2).
  The older `UserChoice` key is stale and not what Windows uses.
- In batch files, call Windows tools by full path
  (`%SystemRoot%\System32\find.exe` etc.): Git's GNU `find` can come first
  on PATH.

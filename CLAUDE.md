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
  apps' associations).

## Commands
```
pip install PySide6 python-mpv
python quiet_player.py [optional path to video]
```

## Where things stand
**Before starting any work, commit any uncommitted changes** (planning
updates to `TODO.md`/`CLAUDE.md` are often dropped into the repo between
sessions). Then check `TODO.md` for the current objective. Never drop this
rule when rewriting this file.

Rounds 1, 2 and 3 are complete, verified on the owner's PC, and committed.
No new round is set yet; check `TODO.md` for the next objective. For each
round, report a status for every numbered item individually, and batch the
round into one set of changes.

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

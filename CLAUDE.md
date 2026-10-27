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
- Keep it small: a single main module is fine until it clearly isn't.

## Commands
```
pip install PySide6 python-mpv
python quiet_player.py [optional path to video]
```

## Where things stand
**Always check `TODO.md` for the current objective before starting work.**

Round 1 (first working player) is complete: everything lives in
`quiet_player.py`. The next round isn't defined yet; see Next Steps in
`TODO.md`. For each round, report a status for every numbered item
individually, and batch the round into one set of changes.

- `libmpv-2.dll` sits next to the script and is git-ignored, so a fresh clone
  needs it re-downloaded (source noted in `TODO.md`).
- The corner indicator uses mpv `show-text` with level 0. It is the only
  thing mpv draws apart from the video.

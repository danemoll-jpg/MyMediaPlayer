# Active Development Plan — Quiet Player

A small Windows desktop video player for local files whose control bar stays
out of the way: it never covers the video, hides instantly, and only comes back
when explicitly asked to.

## Completed Tasks

None yet.

## Current Objective (Focus Area)

**Round 1 — first working player.** Build all of the items below in one round,
then report back with an explicit status for EACH numbered item
(done / not done / deferred, and why). Do not mark the round complete if any
item was skipped.

1. **App skeleton + playback engine.** Windows desktop app using Python,
   PySide6 and python-mpv (libmpv embedded in a Qt widget). Disable all of
   mpv's built-in UI and input: `osc=no`, `osd-level=0`,
   `input-default-bindings=no`, `input-vo-keyboard=no`, `input-cursor=no`.
   All controls and shortcuts are handled by the app, not by mpv.

2. **Opening files.** Three ways: drag-and-drop a file onto the window,
   `Ctrl+O` file dialog, and a file path passed on the command line (so
   Windows "Open with" works). Must play common local formats: MP4, MKV, AVI,
   MOV, WMV, WebM, including HEVC/H.265.

3. **Control bar placement — never covers the video.** The bar sits in its own
   strip below the video area, never overlaid on it. When the bar is shown,
   the video area shrinks to fit above it; when hidden, the video uses the
   full window/screen. Same rule in fullscreen. Bar contents: play/pause,
   skip back, skip ahead, seek slider, current time / duration, volume.
   Keep it thin (roughly 40px).

4. **Hiding — instant.** The toggle key (`Tab`) hides the bar immediately.
   Left-clicking on the video while the bar is visible also hides it.
   No fade or animation.

5. **Never reappears on its own.** The bar must NOT show on mouse movement,
   hover, pause, opening a file, end of file, or entering/leaving fullscreen.
   Its visible/hidden state persists until the user toggles it. Only two
   things show it: the `Tab` key, or middle-click on the video.
   Do NOT use mouse side buttons (back/forward) for anything — the owner has
   them disabled.

6. **Keyboard shortcuts — work whether the bar is shown or hidden.**
   - `Space` — play/pause
   - `←` / `→` — skip back / ahead 10 seconds
   - `Shift+←` / `Shift+→` — skip back / ahead 60 seconds
   - `↑` / `↓` — volume up / down
   - `F` or double-click on video — toggle fullscreen
   - `Esc` — exit fullscreen
   - `Tab` — show/hide control bar
   - `Ctrl+O` — open file
   Keyboard focus must not get stuck on a bar widget (e.g. Space pressing a
   focused button instead of play/pause, or arrows moving the slider instead
   of skipping). Shortcuts are handled at the window level.

7. **Minimal feedback while the bar is hidden.** When a shortcut is used with
   the bar hidden, show a tiny text indicator in a corner ("+10s", "−60s",
   "⏸", "▶", "Vol 70%") for about 0.5 seconds, then remove it. Make it easy
   to turn off with a single constant/setting at the top of the code.

8. **Verification before reporting.** Test on the real Windows 11 PC with at
   least one MP4 and one MKV (HEVC if available). Specifically confirm:
   middle-click and left-click on the video actually reach the app (see the
   embedding note under Technical Notes), and the bar never appears after
   mouse movement, pausing, or opening a new file.

## Next Steps (Do Not Start Yet)

- **Remember last position per file / resume playback** — useful, but not
  part of the core ask; deferred until round 1 is confirmed working.
- **Playlist / next-previous file in folder** — deferred, same reason.
- **Subtitle and audio-track selection shortcuts** — deferred; mpv supports
  both, so this is a small add later.
- **Configurable key bindings** — deferred; hard-coded defaults first.
- **Packaging as a standalone .exe (PyInstaller) and registering as an
  "Open with" option** — deferred until the player itself is right.

## Technical Notes / Blockers

- **Project location:** `C:\Users\danmo\MyMediaPlayer` (repo root holds
  `TODO.md` and `CLAUDE.md`).
- **Owner's setup:** Windows 11 Pro, Dell XPS 8930, GTX 1660 Ti. Mouse side
  buttons are disabled — never bind anything to them.
- **libmpv dependency:** python-mpv needs `libmpv-2.dll` (from an mpv
  "dev" build for Windows) placed next to the script or on PATH.
- **Embedding risk to check first:** when libmpv renders into a native child
  window (`wid`), Windows may deliver mouse clicks to that child window instead
  of the Qt widget, so click/middle-click/double-click on the video may never
  reach the app. `input-cursor=no` is intended to prevent mpv from handling
  them, but confirm early. If clicks still don't arrive, fall back to a
  transparent Qt overlay widget above the video that captures mouse input
  only (it must draw nothing visible).
- **Design decision (RESOLVED):** the bar never overlays the video. In
  fullscreen this means the video shrinks slightly when the bar is shown.
  That trade-off was chosen deliberately.

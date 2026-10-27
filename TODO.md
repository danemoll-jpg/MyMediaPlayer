# Active Development Plan — Quiet Player

A small Windows desktop video player for local files whose control bar stays
out of the way: it never covers the video, hides instantly, and only comes back
when explicitly asked to.

## Completed Tasks

**Round 1 — first working player (2026-10-27).** All eight items done in
`quiet_player.py`. Verified on the owner's PC with real OS-level mouse/keyboard
input (SendInput), 43/43 checks passing on 3 consecutive runs: H.264 MP4,
HEVC MKV (d3d11va hardware decode), MOV. Results per item:

1. Done — PySide6 + python-mpv, libmpv embedded via `wid`; osc/osd/input all off.
2. Done — drag-and-drop, `Ctrl+O`, command-line path. Note: the drop test fed
   the window's drop handler directly; a real Explorer drag was not automated
   (worth one manual try).
3. Done — 40px strip below the video in a layout; video resizes, incl. fullscreen.
4. Done — Tab and left-click on video hide instantly (`setVisible(False)`).
5. Done — show only via Tab / middle-click; side buttons ignored. Tested
   against mouse move, hover, pause, file open, EOF, fullscreen in/out.
6. Done — app-level event filter; all bar widgets are `NoFocus`.
7. Done — `SHOW_INDICATOR` at top of file; text drawn by mpv's OSD renderer via
   `show-text ... level 0` (mpv's own OSD stays off with `osd-level=0`).
8. Done — see above. Embedding risk did NOT materialise: with
   `input-cursor=no`, left/middle/double-clicks on the video reach Qt without
   any overlay or workaround.

Launch behaviour: the bar starts visible on app launch (only), so a fresh
window isn't a blank black box. After that, only the user changes it.

**Round 2 — resume, folder navigation, subtitles/audio (2026-10-27).** All
five items done in `quiet_player.py`. Verified on the owner's PC with real
OS-level keyboard input (SendInput) and real process restarts, using
synthetic test media made with ffmpeg (no real multi-track MKV was used):

1. Done — `PositionStore` writes `%APPDATA%\QuietPlayer\positions.json`
   (normcased full path keys, 500 most recent, atomic write). Saves on close,
   on opening another file, and every 10 s. Under 30 s / last 5% / last 60 s
   clears the entry. Resume uses mpv's per-file `start=` option; indicator
   "Resumed 12:34". `Home` → start, indicator "Start". Tested: resume after a
   full restart, after a simulated crash (lost ≤10 s), under-30s rule (Home
   then switch), last-60s rule (180 s file), 95% rule (25 min file, 70 s from
   the end), close-time save, 500 cap.
2. Done — `N`/`P`, extensions from `VIDEO_EXTS` (now shared with the `Ctrl+O`
   filter, case-insensitive), natural sort, no wrap ("Last file" /
   "First file"). `AUTO_NEXT = False` constant; tested both values. Tested
   through 12 numbered episodes + `Extra.MKV`, with `.srt`/`.txt` files
   ignored, and resume through N/P.
3. Done — `S` cycles subs including "off"; `A` cycles audio. **Decision:**
   audio does not cycle through "off" (muting is what volume is for). Labels:
   track title, else language name via QLocale ("jpn" → "Japanese"), else
   "Track N". External `movie.srt` / `movie.en.srt` load via `sub-auto=exact`;
   mpv auto-selects an external sub when present. Subtitles render with
   `osd-level=0` (confirmed in mpv's own window screenshot).
4. Done — `indicate(text, always=False, ms=...)`; `always=True` for resume,
   Start, file name, First/Last file, sub/audio. File name on N/P shows 1.5 s
   (`FILE_INDICATOR_MS`), with "Resumed …" as a second line when it resumes.
   Volume indicator still suppressed while the bar is visible.
5. Done — 46 checks, all passing in their final runs (resume 20, N/P 14,
   tracks 11, Explorer drag 1). The resume and N/P runs came before the
   external-sub label fix, which only touches track labels. The bar never appeared from any Round 2 action
   (polled every 20 ms). A real Explorer → player drag (actual mouse,
   UI Automation to find the item) opened the file.

## Current Objective (Focus Area)

**Round 3 — open files from the app, and "make Quiet Player my default".**
The code for items 1–4 was written overnight by the planning session (Claude
in the owner's chat), NOT by the coding agent, and has **not been run on
Windows**: the planning session had no PySide6/libmpv available. It passed a
syntax check, a stand-in smoke test of the new code paths, and a registry
test against a simulated `winreg`. The coding agent's job this round is item
5: verify on the real PC, fix whatever is broken, and report per item.
Rule from Round 1 still applies: nothing here may make the bar appear on its
own.

1. **Visible ways to open a file from inside the app.**
   - 📂 button at the left of the control bar (= `Ctrl+O`).
   - Before any file is open, the video area shows "Click here or press
     Ctrl+O to open a video (or drag one onto this window)", and a left-click
     there opens the file dialog (once a file is open, left-click goes back to
     hiding the bar).
   - The dialog starts in the current file's folder, or else the last folder
     used (saved in `%APPDATA%\QuietPlayer\settings.json`).

2. **⋯ menu at the right end of the bar:** "Open a video…",
   "Make Quiet Player my default video player…", and (only once registered)
   "Remove Quiet Player from Windows".

3. **Default player registration** (`default_player.py`, per user, HKCU
   only, no admin). Registers ProgID `QuietPlayer.Video`, Capabilities,
   `RegisteredApplications` and `OpenWithProgids` for every extension in
   `VIDEO_EXTS`. Launch command is `pythonw.exe "…\quiet_player.py" "%1"`
   (or the .exe itself once packaged). Windows 10/11 don't let apps take the
   default silently, so after registering, a message explains the last step
   and Settings opens on `ms-settings:defaultapps?registeredAppUser=Quiet%20Player`
   where the owner clicks "Set default". "Remove" deletes only what
   `register()` added — other apps' entries are never touched.

4. **One window only.** Opening a video while Quiet Player is already running
   (e.g. double-clicking in Explorer once it's the default) hands the file to
   the existing window via `QLocalServer`/`QLocalSocket` and brings it to the
   front, instead of opening a second player. Launching with no file just
   focuses the existing window.

5. **Verification on the real PC (coding agent).** Report done / not done /
   fixed for each:
   - App starts; 📂 and ⋯ show on the bar; the empty-state text renders
     before a file is open and disappears once mpv draws; click-to-open works.
   - Dialog remembers the folder across restarts.
   - ⋯ menu opens just above its button (it is positioned by hand —
     `_menu_offset`) and Space/arrows don't trigger player shortcuts while it
     is open.
   - Make default → Settings opens on Quiet Player's page; after choosing it,
     double-clicking an .mp4 and an .mkv in Explorer opens Quiet Player with
     no console window, and "Open with" shows the name "Quiet Player" (not
     "Python"). If Settings ignores `registeredAppUser`, say so.
   - With the player open, double-click a second video: same window, new
     file, no second window, bar state unchanged.
   - Remove from Windows → Quiet Player disappears from Open with / Default
     apps; VLC/Films & TV associations are unchanged.
   - The bar never appears from any Round 3 action.

## Next Steps (Do Not Start Yet)

- **Configurable key bindings** — deferred; hard-coded defaults first.
- **Packaging as a standalone .exe (PyInstaller)** — deferred. Registration
  already works without it (via pythonw). After packaging, run "Make Quiet
  Player my default" again so Windows points at the .exe.
- **App icon** — the registration currently borrows Python's icon.

## Technical Notes / Blockers

- **Project location:** `C:\Users\danmo\MyMediaPlayer` (repo root holds
  `TODO.md` and `CLAUDE.md`).
- **Owner's setup:** Windows 11 Pro, Dell XPS 8930, GTX 1660 Ti. Mouse side
  buttons are disabled — never bind anything to them.
- **libmpv dependency:** python-mpv needs `libmpv-2.dll` (from an mpv
  "dev" build for Windows) placed next to the script or on PATH. Installed
  from shinchiro/mpv-winbuild-cmake release 20261021
  (`mpv-dev-x86_64-20261021-git-e471496c56.7z`); git-ignored.
- **Python:** this PC runs Python 3.14 with PySide6 6.12.0, python-mpv 1.0.8.
- **Display:** 150%+ scaling, 1280x720 logical. The window sizes itself to
  80% of the available screen so the bar is never off-screen.
- **Embedding risk to check first:** when libmpv renders into a native child
  window (`wid`), Windows may deliver mouse clicks to that child window instead
  of the Qt widget, so click/middle-click/double-click on the video may never
  reach the app. `input-cursor=no` is intended to prevent mpv from handling
  them, but confirm early. If clicks still don't arrive, fall back to a
  transparent Qt overlay widget above the video that captures mouse input
  only (it must draw nothing visible).
  **Checked 2026-10-27: not needed.** Clicks reach the Qt widget as-is.
- **Design decision (RESOLVED):** the bar never overlays the video. In
  fullscreen this means the video shrinks slightly when the bar is shown.
  That trade-off was chosen deliberately.
- **mpv quirks found in Round 2:** external subtitle tracks get a fake
  `title` equal to the filename suffix (`de.srt`, `srt`), so `track_label`
  ignores titles on external tracks. mpv events arrive on its own thread;
  `MpvEvents` (Qt signals) hands them to the GUI thread.
- **Testing notes:** Qt `grabWindow` and plain screen grabs return black (or
  whatever window is in front) for the mpv surface; use mpv's
  `screenshot-to-file <path> window` to see what it actually draws. Keyboard
  tests use SendInput, so typing on the PC during a run causes false
  failures. The Round 2 test harness lived in a session scratch folder and is
  not in the repo.
- **Design decision (RESOLVED 2026-10-27):** the bar is visible when the app
  first opens. Owner confirmed this is what he wants. After launch, only the
  user changes its visibility.

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

**Round 3 — open files from the app, "make Quiet Player my default", one
window (2026-10-27).** Code for items 1–4 was written by the planning session
without Windows; the coding agent verified it on the owner's PC (item 5) with
real OS input (SendInput) and synthetic ffmpeg media, `APPDATA` pointed at a
scratch folder. 66 checks, all passing in their final runs. Two bugs fixed,
one Windows limitation found:

1. Done — 📂 leftmost, ⋯ rightmost. Empty-state hint renders on screen (screen
   grab); after load mpv's child window covers the whole video area. Clicking
   the empty area opens the native Open dialog; with a file open, left-click
   hides the bar instead. Dialog starts in the current file's folder (Ctrl+O,
   📂), else `last_dir` from `settings.json`. Remembered across two restarts
   (checked in the dialog's own address bar, not just the argument).
2. Done — menu sits exactly above ⋯, right edges aligned (measured 0–1 px).
   Space, ←, →, Shift+→, ↑, ↓ in the open menu don't touch pause, position or
   volume (the menu takes them; ↑/↓ move its highlight). Esc closes it, bar
   stays; Space works again afterwards. "Remove…" shows only while registered.
3. Fixed — registration writes everything listed (all 14 extensions), shell
   reports the friendly name "Quiet Player" (`AssocQueryString`), Default
   apps lists Quiet Player, launch is `pythonw.exe` with no console.
   **Settings ignores `registeredAppUser`** on Windows 11 25H2 (build 26200),
   with `%20`, a raw space, or a no-space name: it opens the Default apps
   list. Fix: the message now says to search "Quiet Player" under "Set
   defaults for applications". Also fixed: `is_registered()` compared the
   command with the current Python path, so "Remove" would vanish (leaving a
   stale registration) if Python moved; it now checks the keys exist.
   Remove → keys gone, Quiet Player gone from Default apps, and a full
   before/after diff of HKCU for all 14 extensions (Classes, FileExts incl.
   UserChoice, RegisteredApplications) is empty, so VLC / Media Player are
   unchanged.
   **Not done (deliberately):** clicking "Set default" in Settings and then a
   real Explorer double-click on .mp4/.mkv. That would replace the owner's
   real defaults (currently the Media Player app), which "Remove" cannot
   restore. Instead a throwaway `.qptest` type was pointed at
   `QuietPlayer.Video` and opened with the shell's default verb (what a
   double-click does), and real .mp4/.mkv were opened through the
   `QuietPlayer.Video` verb; both ran the registered command correctly. The
   "Open with" dialog itself was not screenshotted.
4. Fixed — file handoff worked, but the running window did **not** come to
   the front (Windows foreground lock; only the taskbar button would flash).
   Fix: the second launch calls `AllowSetForegroundWindow(ASFW_ANY)` before
   handing over. Verified from a foreground stand-in for Explorer: same
   window, new file, one window, player in front, bar state unchanged with
   the bar both hidden and shown. No-file launch focuses the existing window.
5. Done — this report. The bar never appeared from any Round 3 action (polled
   every 20 ms through Ctrl+O, the dialog, file loads and handoffs).

Testing notes from Round 3: test input is now guarded — before every click
or key the harness checks that the window under the cursor / in focus
belongs to the test, and aborts otherwise (one early run clicked into the
owner's browser before this guard existed). A background process cannot
raise another app's window, so Explorer was not driven directly. Test
harnesses that run without Qt must call `SetProcessDpiAwarenessContext(-4)`
or their coordinates won't match UI Automation at 150%+ scaling.

## Current Objective (Focus Area)

**Round 4 — a real installed app: .exe, icon, Start menu.** Build all of the
items below in one round, then report back with an explicit status for EACH
numbered item (done / not done / deferred, and why). Do not mark the round
complete if any item was skipped.

**Critical:** the owner has ALREADY made Quiet Player his default video
player (Settings > Default apps, 2026-10-27), and Windows stores that choice
against the ProgID `QuietPlayer.Video`. Keep that ProgID name exactly. Never
call `unregister()` / "Remove", and never remove-and-re-add while testing:
that silently drops his defaults. Re-registering in place (`register()`
overwriting the command) is safe and is how the switch to the .exe happens.

1. **Icon (owner chose option "B", 2026-10-27).** A rounded square in deep
   blue (#1f3a5f) with a large plain white play triangle, centred, nothing
   else. Corner radius about 19% of the size, small transparent margin. Must
   read clearly at 16×16. Generate it with a small script
   (`make_icon.py`, Pillow) into `quiet_player.ico` with sizes 16, 24, 32,
   48, 64, 128, 256, and commit both. Use it for the window/taskbar icon
   (`setWindowIcon`), the .exe, the Start menu shortcut, and the file-type
   icon (`DefaultIcon` → `"<exe>",0`).

2. **Package as an .exe with PyInstaller, one-folder mode** (not one-file:
   one-file unpacks ~120 MB to a temp folder on every launch, which would
   make opening a video slow). Windowed, no console. Bundle `libmpv-2.dll`.
   Fix any frozen-mode paths (the DLL lookup in `quiet_player.py` uses
   `__file__`; when frozen use the .exe's folder). Output:
   `dist\QuietPlayer\QuietPlayer.exe`. `build\` and `dist\` are git-ignored.

3. **Install to a fixed location** outside the repo:
   `%LOCALAPPDATA%\Programs\QuietPlayer\`. Rebuilding or moving the repo must
   never break double-clicking videos again. Add a Start menu shortcut
   "Quiet Player" (`%APPDATA%\Microsoft\Windows\Start Menu\Programs`) with
   the icon. No desktop shortcut.

4. **Switch the existing registration to the .exe, in place.** Add a
   `--register` command-line flag that calls `register()` silently and exits
   (no window, no Settings page). After installing, run the installed
   `QuietPlayer.exe --register`. Then confirm, without touching Settings or
   UserChoice: the `QuietPlayer.Video` command now points at the installed
   .exe; `.mp4` and `.mkv` UserChoice still say `QuietPlayer.Video`; a real
   Explorer double-click on an .mp4 and an .mkv opens the installed .exe
   (allowed this round, since it changes no associations); Explorer shows
   the new icon on video files (may need a shell refresh).

5. **One-step update script: `install.bat`** in the repo. It builds with
   PyInstaller, closes a running Quiet Player if there is one (or tells the
   owner to close it and stops), copies `dist\QuietPlayer` to the install
   folder, runs `--register`, and refreshes the Start menu shortcut. This is
   how every future round gets onto the owner's PC. Running it twice in a
   row must be safe.

6. **Retire `Start Quiet Player.bat`.** It was a stop-gap added from the
   planning session (2026-10-27) because double-clicking the .py flashed and
   closed. Delete it once the installed .exe works. Running from source
   (`python quiet_player.py`) must still work for development.

7. **Verification before reporting** on the real PC: the installed .exe
   launches from the Start menu with the new icon in the taskbar; startup
   time from double-click to video is noted (old vs new, roughly); resume
   positions, `settings.json` and every Round 1–3 behaviour still work from
   the .exe (spot-check, not a full retest); single-window hand-off works
   between two .exe launches; `install.bat` run twice in a row works; and
   the owner's defaults were never changed or removed.

## Next Steps (Do Not Start Yet)

- **Configurable key bindings** — deferred; hard-coded defaults first.

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

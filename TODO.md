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

**Round 4 — a real installed app: .exe, icon, Start menu. COMPLETE
(2026-10-27).** The coding agent built and tested items 1–3 and 5–7; item 4
was blocked by registry virtualization (below). The owner then ran
`install.bat` from Explorer himself, and confirmed double-clicking a video
opens the installed .exe with the new icon. The per-item notes below are
the agent's report from before that final step.

**Critical (unchanged):** the owner's defaults are stored against the ProgID
`QuietPlayer.Video` (in `UserChoiceLatest\ProgId` on this build; the older
`UserChoice` key still names the Media Player app and is NOT what Windows
uses). Keep that ProgID. Never call `unregister()` / "Remove", and never
remove-and-re-add. Re-registering in place (`register()` overwriting the
command) is safe.

**Blocker found: registry writes from a Claude Code session are virtualized.**
The session runs under the Claude desktop app's package, and its HKCU
registry writes land in a private copy. The session's own processes then
read back its writes, but Explorer and every other app see the real,
unchanged registry. File writes are real (the installed exe and the Start
menu shortcut exist for Explorer). How this showed up: after
`QuietPlayer.exe --register`, `AssocQueryString`, `reg query` and PowerShell
(even unsandboxed) all showed the .exe command. But a real Explorer
double-click on .mp4/.mkv still started `pythonw.exe quiet_player.py`, even
from a fresh `explorer /separate` process, and a `.bat` started by Explorer
read the old command. To see the real registry from a session, have Explorer
launch a probe (`.bat` double-clicked in a test Explorer window) that runs
`reg query` into a file. Don't trust the session's own reads. The session's
private copy now holds the .exe registration. It's harmless, but it makes
in-session reads look "done". Don't try to delete it from the session:
deleting the ProgID is exactly what must never happen to the real one.

Per-item status (2026-10-27):

1. **Done, apart from the file-type icon.** `make_icon.py` (Pillow, 4x
   supersampled per size, vertical edge snapped to the pixel grid) writes
   `quiet_player.ico` at 16, 24, 32, 48, 64, 128 and 256 px; checked at 16 px
   on light and dark. Used for the window/taskbar (`app.setWindowIcon`), the
   .exe (`--icon`) and the Start menu shortcut, all checked by screenshot.
   `register()` now writes `DefaultIcon` = `"<exe>",0` when frozen (from
   source: the repo's .ico). Not in effect yet: the real `DefaultIcon` is
   still pythonw's, same blocker as item 4.
2. **Done.** PyInstaller 6.22.3, one-folder, windowed, built by `install.bat`.
   `--contents-directory .` puts libmpv-2.dll and the rest beside the exe;
   `quiet_player.py` uses the exe's folder when `sys.frozen`. PIL, numpy and
   tkinter are excluded (python-mpv only wants them for raw screenshots):
   279 MB down to 239 MB, of which 121 MB is libmpv. Output
   `dist\QuietPlayer\QuietPlayer.exe`; `build\`, `dist\` git-ignored (the
   spec file is generated into `build\`).
3. **Done.** Installed to `%LOCALAPPDATA%\Programs\QuietPlayer\` (robocopy
   /MIR). Shortcut `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Quiet
   Player.lnk` with the exe's icon. No desktop shortcut. Both confirmed
   visible to Explorer.
4. **Not done (blocked).** `--register` added: it calls `register()` and exits
   with no window and no Settings page (exit code 1 on failure). It ran, but
   its writes were virtualized (see blocker). Real state, read through
   Explorer: the command and `DefaultIcon` still point at
   `pythonw.exe` + `C:\Users\danmo\MyMediaPlayer\quiet_player.py`, so
   double-clicking still runs from source. All 14 extensions'
   `UserChoiceLatest` still say `QuietPlayer.Video`. Real Explorer
   double-clicks on .mp4 and .mkv were done: they open Quiet Player, but from
   source, not the exe.
5. **Done.** `install.bat`: finds Python, checks PySide6/python-mpv and
   libmpv-2.dll, installs PyInstaller if missing, builds, closes a running
   QuietPlayer.exe with a normal close (no /F, so it saves its position;
   waits up to ~10 s, else tells the owner to close it and stops), copies,
   runs `--register`, and rewrites the shortcut. Tested twice in a row, the
   first run with the exe playing: it closed the player (position saved) and
   both runs exited 0, about 65–90 s each. Two bugs found and fixed: plain
   `find` resolved to Git's GNU find, so a running player went undetected
   (Windows tools are now called by full System32 path); and robocopy's
   default retries (1,000,000 × 30 s) hung on the locked exe (now
   `/R:2 /W:1`). CRLF is enforced via `.gitattributes`.
6. **Done.** `Start Quiet Player.bat` deleted (nothing referenced it; the
   real registration calls pythonw directly). Running from source still
   works (4/4 launches in the timing test).
7. **Partly done.** On the owner's PC, against the installed exe, with
   `APPDATA` pointed at a scratch folder and guarded input. Passed:
   - Start menu shortcut opens the installed exe (launched the way the Start
     menu does, via ShellExecute of the .lnk; the Start menu UI itself was
     not clicked). New icon in the taskbar and title bar.
   - Startup to window with the file loading, warm, median of 3: source
     1.55 s, exe 1.50 s (no real difference). The first exe launch after an
     install was ~6.5 s (cold disk cache).
   - Resume from the stored position; the 30 s / last-60 s rules.
   - `settings.json`: Open dialog starts in `last_dir`, which is rewritten
     after choosing a file.
   - Tab, middle-click and left-click bar behaviour; mouse movement does not
     show the bar.
   - F / Esc fullscreen; Space pause; → seek; N next file (with resume).
   - Single-window hand-off between two exe launches: the second exits, the
     same window takes the file and stays in front.
   - `install.bat` run twice in a row works.
   - Defaults never changed (checked through Explorer).

   Not passed: a real Explorer double-click opening the *exe*, and Explorer
   showing the new file icon. Both are blocked on item 4.

#### To finish Round 4 (done by the owner, 2026-10-27)

1. Owner: double-click `install.bat` in the repo folder (in Explorer, not
   from a Claude session) and wait for "Quiet Player is installed". This
   rebuilds and runs the real `--register`.
2. Then verify through Explorer (not with in-session reads): the
   `QuietPlayer.Video` command and `DefaultIcon` point at the installed exe;
   all 14 `UserChoiceLatest\ProgId` still say `QuietPlayer.Video`; a real
   double-click on .mp4 and .mkv starts `QuietPlayer.exe` (parent explorer);
   video files show the new icon (`ie4uinit -show` if not).
3. If all pass, Round 4 is complete.

## Current Objective (Focus Area)

**Round 5 — speed, frame stepping, mute, remembered volume, recent files.**
Build all of the items below in one round, then report back with an explicit
status for EACH numbered item (done / not done / deferred, and why). Do not
mark the round complete if any item was skipped. All earlier rules still
apply: nothing may make the control bar appear on its own, shortcuts work
with the bar shown or hidden, and bar widgets never take keyboard focus.
Quiet Player is the owner's default player: keep ProgID `QuietPlayer.Video`,
never unregister.

New keys don't clash with existing ones (Space, arrows, Shift+arrows, ↑/↓,
F, Esc, Tab, Ctrl+O, Home, N, P, S, A).

1. **Playback speed.** `]` faster, `[` slower, stepping through 0.5×,
   0.75×, 1×, 1.25×, 1.5×, 1.75×, 2× (stop at the ends). `Backspace` resets
   to 1×. Audio pitch stays normal (mpv's default `audio-pitch-correction`;
   confirm it isn't off). Indicator "Speed 1.25×" shown even with the bar
   visible, since the bar doesn't show speed. Speed carries over to the next
   file in the same session (useful for a talky series with N), and is not
   remembered after closing the app. When a file opens at a speed other than
   1×, add "Speed 1.5×" to its open indicator so it's never a surprise.

2. **Frame-by-frame.** `.` steps one frame forward, `,` one frame back
   (mpv `frame-step` / `frame-back-step`). Stepping pauses playback if it
   was playing. Holding the key repeats. No indicator (the frame itself is
   the feedback).

3. **Mute.** `M` toggles mute (mpv `mute`, separate from volume, so
   unmuting returns to the same level). The bar's volume icon shows 🔇 while
   muted. Indicator "Muted" / "Unmuted" follows the Round 1 rule (only while
   the bar is hidden), since the bar shows it. Clicking the volume icon on
   the bar also toggles mute. Changing volume with ↑/↓ while muted unmutes.

4. **Remember volume.** Save the volume level in
   `%APPDATA%\QuietPlayer\settings.json` when it changes (debounced, e.g.
   1 s after the last change) and on close; start at the saved level
   instead of 70%. Mute is NOT remembered: the app always starts unmuted.

5. **Recent files.** A "Recent" submenu in the ⋯ menu with the 10 most
   recently opened files (file name only, full path as tooltip), newest
   first, then a separator and "Clear list". Files that no longer exist are
   left out of the menu. Stored in `settings.json`. Opening any file by any
   route (dialog, drag-drop, double-click in Explorer, N/P, Recent) moves it
   to the top. Choosing a recent file follows the Round 2 resume rule.

6. **Help line.** Update the tooltips and the ⋯ menu so the new keys are
   discoverable: add a "Keyboard shortcuts" item in the ⋯ menu that shows a
   small dialog listing every shortcut. Keys must not trigger player actions
   while that dialog is open.

7. **Install and verify.** Build with `install.bat` for testing, but the
   owner must run `install.bat` from Explorer himself at the end (registry
   writes from a session are virtualized; see Round 4). Test from source and
   from the built exe with `APPDATA` pointed at a scratch folder: each speed
   step and both ends, Backspace, pitch sounds normal (check with a tone or
   speech file), speed carries to the next file, frame step both directions
   while playing and paused, mute via M, icon and click, ↑ unmutes, volume
   restored after restart, mute not restored, Recent order/missing-file/
   Clear list, the shortcuts dialog, and the bar never appears from any
   Round 5 action.

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

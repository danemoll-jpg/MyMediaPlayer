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

**No round defined yet.** Pick from Next Steps when the owner says so.
Round 2 spec kept below for reference.

**Round 2 — resume, folder navigation, subtitles/audio.** Build all of the
items below in one round, then report back with an explicit status for EACH
numbered item (done / not done / deferred, and why). Do not mark the round
complete if any item was skipped. All Round 1 rules still apply — in
particular, nothing in this round may make the control bar appear on its own.

1. **Resume where you left off.** Remember the playback position per file and
   resume there the next time that file is opened (any way: drag-drop,
   `Ctrl+O`, command line, next/previous).
   - Store positions in a small JSON file at
     `%APPDATA%\QuietPlayer\positions.json`, keyed by the file's full
     normalized path. Keep only the 500 most recently played entries.
   - Save the current position when the app closes, when another file is
     opened, and every ~10 seconds during playback (so a crash loses little).
   - Don't save (and clear any saved entry) if the position is under 30
     seconds, or within the last 5% or last 60 seconds of the file — that
     counts as "not really started" or "finished".
   - On resume, show the indicator "Resumed 12:34".
   - `Home` jumps back to the start of the current file (indicator
     "Start").

2. **Next / previous file in the same folder.** `N` opens the next video file
   in the current file's folder, `P` the previous one.
   - Only video extensions (same list as the `Ctrl+O` filter).
   - Natural sort order, so "Episode 2" comes before "Episode 10".
   - No wrap-around: at either end show the indicator "Last file" /
     "First file" and do nothing.
   - The new file follows item 1's resume rule, and the current file's
     position is saved before switching.
   - Add a constant `AUTO_NEXT = False` at the top of the code. When `True`,
     reaching the end of a file opens the next one automatically. Default
     stays off (current behaviour: stop on the last frame).

3. **Subtitle and audio-track shortcuts.**
   - `S` cycles subtitle tracks, including "off". Indicator shows the result,
     e.g. "Subs: English" / "Subs: off" (use the track title or language;
     fall back to "Track 2").
   - `A` cycles audio tracks the same way: "Audio: Japanese".
   - External subtitle files next to the video with the same name
     (e.g. `movie.srt`, `movie.en.srt`) load automatically.
   - Subtitles themselves are rendered by mpv as normal; `osd-level=0` must
     not hide them.

4. **Indicator rule update.** For actions whose result does NOT show on the
   control bar (resume, Start, next/previous file name, First/Last file,
   subtitle and audio track changes), show the indicator even while the bar
   is visible. All other indicators keep the Round 1 rule (only while the bar
   is hidden). `SHOW_INDICATOR = False` still turns every indicator off. When
   switching files with N/P, show the new file name for ~1.5 seconds instead
   of 0.5.

5. **Verification before reporting.** Test on the real PC:
   - Resume across a full app restart, plus the under-30s and near-the-end
     rules.
   - N/P through a folder with at least 10 numbered files to prove natural
     sort, and the First/Last file ends.
   - `S` and `A` on an MKV with more than one subtitle and audio track if
     available (say so if no such file was found), plus an external `.srt`.
   - Confirm the control bar never appears from any Round 2 action.
   - Do one real drag from File Explorer (left over from Round 1).

## Next Steps (Do Not Start Yet)

- **Configurable key bindings** — deferred; hard-coded defaults first.
- **Packaging as a standalone .exe (PyInstaller) and registering as an
  "Open with" option** — deferred until the player itself is right.

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

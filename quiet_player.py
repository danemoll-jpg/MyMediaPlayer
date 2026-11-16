"""Quiet Player — a local video player whose control bar stays out of the way.

The bar lives in its own strip below the video (never overlaid), hides
instantly, and only comes back on Tab or middle-click on the video.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time

# Settings -------------------------------------------------------------------
SHOW_INDICATOR = True        # tiny corner text for shortcuts (False turns every indicator off)
INDICATOR_MS = 500
FILE_INDICATOR_MS = 1500     # file name shown when switching with N/P
AUTO_NEXT = False            # at end of file, open the next one in the folder
BAR_HEIGHT = 40
SKIP_SMALL = 10              # seconds (arrows)
SKIP_LARGE = 60              # seconds (Shift+arrows)
VOLUME_STEP = 5
DEFAULT_VOLUME = 70          # first run only; after that the last level is remembered
SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)   # ] and [ step through these
RECENT_SHOWN = 10            # files in the Recent menu
RECENT_KEPT = 20             # stored, so missing files don't shrink the menu

PLAY_GLYPH = "▶︎"
PAUSE_GLYPH = "⏸︎"
VOLUME_GLYPH = "🔊︎"
MUTED_GLYPH = "🔇︎"

VIDEO_EXTS = (".mp4", ".m4v", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".ts",
              ".m2ts", ".mpg", ".mpeg", ".3gp", ".ogv")
VIDEO_FILTER = "Videos (" + " ".join("*" + e for e in VIDEO_EXTS) + ");;All files (*)"

# Resume positions
POSITIONS_FILE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                              "QuietPlayer", "positions.json")
POSITIONS_MAX = 500
SAVE_EVERY_MS = 10_000
RESUME_MIN = 30              # seconds: below this counts as "not really started"
FINISHED_FRACTION = 0.95     # past 95% ...
FINISHED_TAIL = 60           # ... or within the last 60 s counts as "finished"

# Small app settings (last folder used in the Open dialog)
SETTINGS_FILE = os.path.join(os.path.dirname(POSITIONS_FILE), "settings.json")

# Only one window: opening a video while the player runs hands it to that window.
INSTANCE_NAME = "QuietPlayer-" + (os.environ.get("USERNAME") or os.environ.get("USER") or "user")

# Shown by "Keyboard shortcuts" in the ⋯ menu (keep in step with _shortcut_for).
SHORTCUTS = (
    ("Space", "Play / pause"),
    ("← / →", f"Back / ahead {SKIP_SMALL} s"),
    ("Shift+← / →", f"Back / ahead {SKIP_LARGE} s"),
    ("Home", "Back to the start"),
    (". / ,", "Next / previous frame (pauses)"),
    ("] / [", "Faster / slower"),
    ("Backspace", "Normal speed"),
    ("↑ / ↓", "Volume up / down"),
    ("M", "Mute / unmute"),
    ("N / P", "Next / previous video in the folder"),
    ("S", "Subtitles (cycles, including off)"),
    ("A", "Audio track"),
    ("F, double-click", "Fullscreen"),
    ("Esc", "Leave fullscreen"),
    ("Tab", "Show / hide the control bar"),
    ("Middle-click", "Show the control bar"),
    ("Click on the video", "Hide the control bar"),
    ("Ctrl+O", "Open a video"),
)

DEFAULT_APP_STEPS = (
    "Windows doesn't let apps make themselves the default, so Settings "
    "will open next on Default apps. Under \"Set defaults for applications\", "
    "search for Quiet Player, open it and click \"Set default\" at the top "
    "(or pick it for each file type you want).\n\n"
    "Another way: right-click any video, Open with > Choose another app > "
    "Quiet Player, and tick \"Always\".")

EMPTY_HINT = "Click here or press Ctrl+O to open a video\n(or drag one onto this window)"

# libmpv-2.dll and the icon sit next to this script, or next to QuietPlayer.exe
# when packaged (PyInstaller one-folder build with its contents beside the .exe).
FROZEN = getattr(sys, "frozen", False)
_here = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
ICON_FILE = os.path.join(_here, "quiet_player.ico")
os.environ["PATH"] = _here + os.pathsep + os.environ.get("PATH", "")
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(_here)

import mpv
from PySide6.QtCore import QEvent, QLocale, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPainter
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSlider, QStyle, QVBoxLayout, QWidget)

import default_player
import updater

def fmt_time(t):
    if t is None or t < 0:
        return "--:--"
    t = int(t)
    h, m, s = t // 3600, t % 3600 // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def norm_path(path):
    return os.path.normcase(os.path.abspath(path))


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, SETTINGS_FILE)
    except OSError:
        pass


def fmt_speed(s):
    return f"{s:g}×"


def natural_key(name):
    """'Episode 2' sorts before 'Episode 10'."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name.casefold())]


def folder_videos(path):
    """Video files in path's folder, naturally sorted (path itself always included)."""
    folder, base = os.path.split(os.path.abspath(path))
    try:
        names = [n for n in os.listdir(folder)
                 if n.lower().endswith(VIDEO_EXTS) and os.path.isfile(os.path.join(folder, n))]
    except OSError:
        names = []
    if base not in names:
        names.append(base)
    names.sort(key=lambda n: (natural_key(n), n))
    return [os.path.join(folder, n) for n in names]


def track_label(t):
    # mpv titles external files with their filename suffix ("en.srt"); skip that.
    if t.get("title") and not t.get("external"):
        return t["title"]
    lang = t.get("lang")
    if lang:
        code = QLocale.codeToLanguage(lang)
        return QLocale.languageToString(code) if code != QLocale.AnyLanguage else lang
    return f"Track {t.get('id')}"


class PositionStore:
    """Per-file resume positions in a small JSON file, most recently played last."""

    def __init__(self, path=POSITIONS_FILE):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.data = {k: v for k, v in data.items() if isinstance(v, dict) and "pos" in v}
        except (OSError, ValueError, AttributeError):
            self.data = {}

    def get(self, key):
        e = self.data.get(key)
        return e["pos"] if e else None

    def update(self, key, pos, dur):
        """Store pos, or clear the entry if pos counts as 'not started' / 'finished'."""
        finished = pos >= dur * FINISHED_FRACTION or pos >= dur - FINISHED_TAIL
        if pos < RESUME_MIN or finished:
            if self.data.pop(key, None) is not None:
                self._write()
            return
        pos = round(pos, 1)
        was_last = next(reversed(self.data), None) == key
        old = self.data.pop(key, None)
        self.data[key] = {"pos": pos, "t": int(time.time())}
        while len(self.data) > POSITIONS_MAX:
            del self.data[next(iter(self.data))]
        if not (was_last and old and old["pos"] == pos):
            self._write()

    def _write(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=0)
            os.replace(tmp, self.path)
        except OSError:
            pass


class UpdateEvents(QObject):
    """Carries the update thread's results over to the Qt thread."""
    found = Signal(str)                 # newer version, download starting
    done = Signal(str, str, bool)       # kind ('ready', 'latest', 'manual', 'failed'), version, user


class MpvEvents(QObject):
    """Carries mpv's thread callbacks over to the Qt thread."""
    file_loaded = Signal()
    eof = Signal(bool)


class JumpSlider(QSlider):
    """Slider that jumps straight to the clicked position and never takes focus."""

    def __init__(self, on_user_move):
        super().__init__(Qt.Horizontal)
        self.setFocusPolicy(Qt.NoFocus)
        self._on_user_move = on_user_move
        self.dragging = False

    def _value_at(self, x):
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                              int(x), self.width())

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = True
            self.setValue(self._value_at(e.position().x()))
            self._on_user_move(self.value())
            e.accept()

    def mouseMoveEvent(self, e):
        if self.dragging:
            self.setValue(self._value_at(e.position().x()))
            self._on_user_move(self.value())

    def mouseReleaseEvent(self, e):
        self.dragging = False

    def wheelEvent(self, e):
        e.ignore()


class VideoArea(QWidget):
    """Native host window for libmpv. Receives the mouse input for the video."""

    def __init__(self, player_window):
        super().__init__()
        self.pw = player_window
        self.setAttribute(Qt.WA_NativeWindow)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setStyleSheet("background: black;")
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(False)

    def paintEvent(self, e):
        # Only visible before the first file loads; after that mpv draws here.
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        if self.pw.current is None:
            p.setPen(QColor("#888"))
            f = p.font()
            f.setPointSize(13)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, EMPTY_HINT)
        p.end()

    def mousePressEvent(self, e):
        b = e.button()
        if b == Qt.LeftButton:
            if self.pw.current is None:      # nothing open yet: click = Open
                self.pw.open_dialog()
            else:
                self.pw.on_video_left_click()
        elif b == Qt.MiddleButton:
            self.pw.on_video_middle_click()
        # Side buttons (Back/Forward) and anything else: deliberately ignored.
        e.accept()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.pw.toggle_fullscreen()
        e.accept()


class ControlBar(QWidget):
    def __init__(self, pw):
        super().__init__()
        self.setFixedHeight(BAR_HEIGHT)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("""
            QWidget { background: #1c1c1c; color: #ddd; }
            QPushButton { border: none; padding: 0 8px; min-width: 28px;
                          font-family: "Segoe UI Symbol"; font-size: 15px; }
            QPushButton:hover { color: #fff; background: #2c2c2c; }
            QLabel { font-size: 12px; padding: 0 6px; }
            QSlider::groove:horizontal { height: 4px; background: #444; }
            QSlider::sub-page:horizontal { background: #bbb; }
            QSlider::handle:horizontal { width: 10px; margin: -4px 0; background: #eee; border-radius: 5px; }
        """)

        def btn(text, tip, slot):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(slot)
            return b

        self.open = btn("📂︎", "Open a video (Ctrl+O)", pw.open_dialog)
        self.back = btn("⏪︎", f"Back {SKIP_SMALL}s (←)", lambda: pw.seek(-SKIP_SMALL))
        self.play = btn(PLAY_GLYPH, "Play/Pause (Space)", pw.toggle_pause)
        self.fwd = btn("⏩︎", f"Ahead {SKIP_SMALL}s (→)", lambda: pw.seek(SKIP_SMALL))
        self.seek = JumpSlider(pw.seek_to_permille)
        self.seek.setRange(0, 1000)
        self.seek.setToolTip(f"Seek (←/→ {SKIP_SMALL}s, Shift for {SKIP_LARGE}s; "
                             f". and , step one frame)")
        self.time = QLabel("--:-- / --:--")
        self.vol_icon = btn(VOLUME_GLYPH, "Mute (M)", pw.toggle_mute)
        self.vol = JumpSlider(pw.set_volume)
        self.vol.setRange(0, 100)
        self.vol.setFixedWidth(90)
        self.vol.setToolTip("Volume (↑/↓)")
        self.more = btn("⋯", "More: recent files, keyboard shortcuts",
                        lambda: pw.show_menu(self.more))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 10, 0)
        lay.setSpacing(4)
        for w in (self.open, self.back, self.play, self.fwd):
            lay.addWidget(w)
        lay.addWidget(self.seek, 1)
        lay.addWidget(self.time)
        lay.addWidget(self.vol_icon)
        lay.addWidget(self.vol)
        lay.addWidget(self.more)


class PlayerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quiet Player")
        avail = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1100, int(avail.width() * 0.8)), min(680, int(avail.height() * 0.8)))
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)

        central = QWidget()
        central.setStyleSheet("background: black;")
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.video = VideoArea(self)
        self.bar = ControlBar(self)
        lay.addWidget(self.video, 1)
        lay.addWidget(self.bar)
        self.setCentralWidget(central)
        self.bar_visible = True   # only ever changed by the user (Tab / clicks)

        self.mpv = mpv.MPV(
            wid=str(int(self.video.winId())),
            osc=False,
            osd_level=0,
            input_default_bindings=False,
            input_vo_keyboard=False,
            input_cursor=False,
            cursor_autohide="no",
            hwdec="auto-safe",
            keep_open="yes",
            idle="yes",
            osd_font_size=22,
            osd_align_x="left",
            osd_align_y="top",
            osd_margin_x=14,
            osd_margin_y=10,
            osd_border_size=2,
            sub_auto="exact",       # movie.srt, movie.en.srt next to the video
            audio_pitch_correction="yes",   # mpv's default; keeps voices normal at 1.5x
        )

        self.positions = PositionStore()
        self.settings = load_settings()
        vol = self.settings.get("volume")
        if not isinstance(vol, (int, float)) or isinstance(vol, bool):
            vol = DEFAULT_VOLUME
        self.mpv.volume = max(0, min(100, round(vol)))
        self.mpv.mute = False      # mute is never remembered
        self.speed = 1.0           # this session only; carries over to the next file
        self.current = None        # path of the open file
        self.loaded = False        # True once mpv has loaded self.current
        self.resume_from = None    # start position passed to mpv for self.current
        self.announce = None       # file name to show once loaded (N/P)
        self.events = MpvEvents()
        self.events.file_loaded.connect(self.on_file_loaded)
        self.events.eof.connect(self.on_eof)
        self.mpv.register_event_callback(self._mpv_event)
        self.mpv.observe_property("eof-reached", lambda _n, v: self.events.eof.emit(bool(v)))

        self.saver = QTimer(self)
        self.saver.timeout.connect(self.save_position)
        self.saver.start(SAVE_EVERY_MS)

        self.volume_saver = QTimer(self)    # saves the volume 1 s after the last change
        self.volume_saver.setSingleShot(True)
        self.volume_saver.setInterval(1000)
        self.volume_saver.timeout.connect(self.save_volume)

        self.poll = QTimer(self)
        self.poll.timeout.connect(self.refresh)
        self.poll.start(250)

        # Updates: silent unless asked for from the ⋯ menu (see updater.py).
        self.update_busy = False       # a check / download is running
        self.update_user = False       # ... and the user asked for it
        self.update_found = None       # version being downloaded
        self.update_events = UpdateEvents()
        self.update_events.found.connect(self.on_update_found)
        self.update_events.done.connect(self.on_update_done)
        if updater.can_self_update():
            threading.Thread(target=updater.cleanup_on_start, daemon=True).start()
            self.update_timer = QTimer(self)
            self.update_timer.timeout.connect(self.maybe_check_updates)
            QTimer.singleShot(int(os.environ.get("QUIET_PLAYER_CHECK_DELAY_MS", 20_000)),
                              self.maybe_check_updates)
            self.update_timer.start(3600_000)

        QApplication.instance().installEventFilter(self)

    # --- bar visibility (only user actions call these) ----------------------
    def set_bar_visible(self, visible):
        self.bar_visible = visible
        self.bar.setVisible(visible)   # layout gives the space back to the video instantly

    def toggle_bar(self):
        self.set_bar_visible(not self.bar_visible)

    def on_video_left_click(self):
        if self.bar_visible:
            self.set_bar_visible(False)

    def on_video_middle_click(self):
        self.set_bar_visible(True)

    # --- playback -----------------------------------------------------------
    def open_file(self, path, announce=False):
        if not path:
            return
        self.save_position()
        self.loaded = False
        self.current = os.path.abspath(path)
        self.add_recent(self.current)
        self.resume_from = self.positions.get(norm_path(path))
        self.announce = os.path.basename(path) if announce else None
        if self.resume_from is not None:
            self.mpv.loadfile(self.current, start=f"{self.resume_from:.3f}")
        else:
            self.mpv.loadfile(self.current)
        self.mpv.pause = False
        self.setWindowTitle(f"{os.path.basename(path)} — Quiet Player")

    def _mpv_event(self, ev):   # mpv thread
        if ev.event_id.value == mpv.MpvEventID.FILE_LOADED:
            self.events.file_loaded.emit()

    def on_file_loaded(self):
        self.loaded = True
        lines = [self.announce] if self.announce else []
        if self.resume_from is not None:
            lines.append(f"Resumed {fmt_time(self.resume_from)}")
        if self.speed != 1.0:      # never a surprise
            lines.append(f"Speed {fmt_speed(self.speed)}")
        if lines:
            long = self.announce or self.speed != 1.0
            self.indicate("\n".join(lines), always=True,
                          ms=FILE_INDICATOR_MS if long else INDICATOR_MS)
        self.announce = None

    def on_eof(self, reached):
        if reached and AUTO_NEXT and self.loaded:
            self.step_file(1, quiet=True)

    def save_position(self):
        if not (self.current and self.loaded):
            return
        try:
            pos, dur = self.mpv.time_pos, self.mpv.duration
        except Exception:
            return
        if pos is not None and dur:
            self.positions.update(norm_path(self.current), pos, dur)

    def step_file(self, step, quiet=False):
        if not self.current:
            return
        files = folder_videos(self.current)
        keys = [norm_path(f) for f in files]
        i = keys.index(norm_path(self.current)) + step
        if 0 <= i < len(files):
            self.open_file(files[i], announce=True)
        elif not quiet:
            self.indicate("Last file" if step > 0 else "First file", always=True)

    def go_to_start(self):
        if self.mpv.duration is None:
            return
        self.mpv.command("seek", 0, "absolute+exact")
        self.indicate("Start", always=True)

    def cycle_track(self, kind):
        """kind is 'sub' or 'audio'. Subtitles cycle through 'off'; audio doesn't."""
        name = "Subs" if kind == "sub" else "Audio"
        prop = "sid" if kind == "sub" else "aid"
        if not any(t.get("type") == kind for t in self.mpv.track_list or []):
            self.indicate(f"{name}: none", always=True)
            return
        self.mpv.command("cycle", prop)
        if kind == "audio" and self.mpv[prop] in (False, "no"):
            self.mpv.command("cycle", prop)
        sel = next((t for t in self.mpv.track_list or []
                    if t.get("type") == kind and t.get("selected")), None)
        self.indicate(f"{name}: {track_label(sel) if sel else 'off'}", always=True)

    def open_dialog(self):
        start = os.path.dirname(self.current) if self.current else self.settings.get("last_dir", "")
        path, _ = QFileDialog.getOpenFileName(self, "Open video", start, VIDEO_FILTER)
        if path:
            self.settings["last_dir"] = os.path.dirname(os.path.abspath(path))
            save_settings(self.settings)
            self.open_file(path)

    # --- menu / default player ----------------------------------------------
    def show_menu(self, anchor):
        m = QMenu(self)
        m.addAction("Open a video…\tCtrl+O", self.open_dialog)
        recent = m.addMenu("Recent")
        recent.setToolTipsVisible(True)
        files = self.recent_files()
        for path in files:
            a = recent.addAction(os.path.basename(path).replace("&", "&&"),
                                 lambda p=path: self.open_recent(p))
            a.setToolTip(path)
        if not files:
            recent.addAction("(none)").setEnabled(False)
        recent.addSeparator()
        recent.addAction("Clear list", self.clear_recent).setEnabled(bool(self._recent()))
        m.addAction("Keyboard shortcuts…", self.show_shortcuts)
        staged = updater.staged_version() if updater.can_self_update() else None
        if staged and updater.is_newer(staged):
            m.addAction(f"Update {staged} installs when you close").setEnabled(False)
        elif self.update_busy:
            m.addAction(f"Downloading update {self.update_found}…" if self.update_found
                        else "Checking for updates…").setEnabled(False)
        else:
            m.addAction(f"Check for updates (now {updater.APP_VERSION})",
                        lambda: self.check_updates(user=True))
        m.addSeparator()
        if sys.platform == "win32":
            m.addAction("Make Quiet Player my default video player…", self.make_default)
            if default_player.is_registered():
                m.addAction("Remove Quiet Player from Windows", self.remove_from_windows)
        m.exec(anchor.mapToGlobal(anchor.rect().topRight()) - _menu_offset(m))

    def show_shortcuts(self):
        # Modal: while it's open, eventFilter leaves keys to the dialog, not the player.
        d = QDialog(self)
        d.setWindowTitle("Keyboard shortcuts")
        rows = "".join(f"<tr><td style='padding:2px 18px 2px 0'><b>{k}</b></td><td>{v}</td></tr>"
                       for k, v in SHORTCUTS)
        text = QLabel(f"<table>{rows}</table>"
                      f"<p style='color:#888'>Quiet Player {updater.APP_VERSION}</p>")
        text.setTextFormat(Qt.RichText)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(d.reject)
        for b in buttons.buttons():   # so Space can't press Close; Esc or a click closes it
            b.setFocusPolicy(Qt.NoFocus)
            b.setAutoDefault(False)
        lay = QVBoxLayout(d)
        lay.addWidget(text)
        lay.addWidget(buttons)
        d.exec()

    # --- updates (updater.py) -----------------------------------------------
    def maybe_check_updates(self):
        last = self.settings.get("update_checked")
        if not isinstance(last, (int, float)) or time.time() - last >= updater.CHECK_EVERY_S:
            self.check_updates(user=False)

    def check_updates(self, user):
        if self.update_busy:
            return
        self.update_busy, self.update_user, self.update_found = True, user, None
        if user:
            self.indicate("Checking for updates…", always=True, ms=FILE_INDICATOR_MS)
        ev = self.update_events

        def work():
            try:
                latest, staged = updater.check_and_stage(on_found=ev.found.emit)
                kind = "ready" if staged else ("manual" if updater.is_newer(latest) else "latest")
                ev.done.emit(kind, latest, user)
            except Exception as e:      # network, signature, disk: try again later
                updater.log(f"check failed: {e!r}")
                ev.done.emit("failed", "", user)
        threading.Thread(target=work, daemon=True).start()

    def on_update_found(self, version):
        self.update_found = version
        if self.update_user:
            self.indicate(f"Downloading update {version}…", always=True, ms=FILE_INDICATOR_MS)

    def on_update_done(self, kind, version, user):
        self.update_busy = False
        if kind != "failed":
            self.settings["update_checked"] = int(time.time())
            save_settings(self.settings)
        if not user:
            return                      # automatic checks never show anything
        text = {"ready": f"Update {version} installs when you close",
                "latest": f"Up to date ({updater.APP_VERSION})",
                "manual": f"Version {version} is out (this copy can't update itself)",
                "failed": "Couldn't check for updates"}[kind]
        self.indicate(text, always=True, ms=3000)

    # --- recent files -------------------------------------------------------
    def _recent(self):
        r = self.settings.get("recent")
        return [p for p in r if isinstance(p, str)] if isinstance(r, list) else []

    def add_recent(self, path):
        key = norm_path(path)
        r = [path] + [p for p in self._recent() if norm_path(p) != key]
        self.settings["recent"] = r[:RECENT_KEPT]
        save_settings(self.settings)

    def recent_files(self):
        """Newest first; files that no longer exist are left out."""
        return [p for p in self._recent() if os.path.isfile(p)][:RECENT_SHOWN]

    def clear_recent(self):
        self.settings["recent"] = []
        save_settings(self.settings)

    def open_recent(self, path):
        if os.path.isfile(path):
            self.open_file(path)
        else:
            self.indicate("File not found", always=True)

    def make_default(self):
        try:
            default_player.register([e for e in VIDEO_EXTS])
        except OSError as err:
            QMessageBox.warning(self, "Quiet Player", f"Couldn't register with Windows:\n{err}")
            return
        QMessageBox.information(
            self, "Quiet Player",
            "Quiet Player is now registered with Windows as a video player.\n\n"
            + DEFAULT_APP_STEPS)
        default_player.open_default_apps_settings()

    def remove_from_windows(self):
        try:
            default_player.unregister([e for e in VIDEO_EXTS])
        except OSError as err:
            QMessageBox.warning(self, "Quiet Player", f"Couldn't remove it:\n{err}")
            return
        QMessageBox.information(
            self, "Quiet Player",
            "Quiet Player has been removed from Windows' app lists. File types "
            "that used it will go back to asking which app to use.")

    def toggle_pause(self):
        self.mpv.pause = not self.mpv.pause
        self.indicate("⏸" if self.mpv.pause else "▶")

    def seek(self, secs):
        if self.mpv.duration is None:
            return
        self.mpv.command("seek", secs, "relative+exact")
        self.indicate(f"+{secs}s" if secs > 0 else f"−{-secs}s")

    def seek_to_permille(self, v):
        if self.mpv.duration:
            self.mpv.command("seek", v / 10.0, "absolute-percent")

    def set_volume(self, v):
        self.mpv.volume = max(0, min(100, v))
        self.mpv.mute = False      # moving the slider while muted unmutes
        self.volume_saver.start()

    def change_volume(self, delta):
        v = max(0, min(100, round(self.mpv.volume or 0) + delta))
        self.mpv.volume = v
        self.mpv.mute = False      # so does ↑/↓
        self.volume_saver.start()
        self.indicate(f"Vol {v}%")

    def save_volume(self):
        try:
            v = round(self.mpv.volume)
        except Exception:
            return
        if self.settings.get("volume") != v:
            self.settings["volume"] = v
            save_settings(self.settings)

    def toggle_mute(self):
        muted = not self.mpv.mute
        self.mpv.mute = muted
        self.bar.vol_icon.setText(MUTED_GLYPH if muted else VOLUME_GLYPH)
        self.indicate("Muted" if muted else "Unmuted")   # the bar shows it, so only when hidden

    def step_speed(self, step):
        """step is +1 / -1 along SPEEDS (stopping at the ends), or 0 for 1x."""
        if step == 0:
            new = 1.0
        else:
            i = min(range(len(SPEEDS)), key=lambda j: abs(SPEEDS[j] - self.speed))
            new = SPEEDS[max(0, min(len(SPEEDS) - 1, i + step))]
        self.speed = new
        self.mpv.speed = new
        self.indicate(f"Speed {fmt_speed(new)}", always=True)   # the bar doesn't show speed

    def frame_step(self, forward):
        if self.loaded:
            self.mpv.command("frame-step" if forward else "frame-back-step")   # both pause

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def indicate(self, text, always=False, ms=INDICATOR_MS):
        """Brief corner text. Drawn by mpv's OSD renderer at level 0 (mpv's own
        OSD stays off via osd-level=0). Normally only while the bar is hidden;
        always=True is for results the bar doesn't show (files, tracks, resume)."""
        if SHOW_INDICATOR and (always or not self.bar_visible):
            self.mpv.command("show-text", text, ms, 0)

    def refresh(self):
        m = self.mpv
        try:
            pos, dur, paused, vol, muted = m.time_pos, m.duration, m.pause, m.volume, m.mute
        except Exception:
            return
        b = self.bar
        b.play.setText(PLAY_GLYPH if paused or pos is None else PAUSE_GLYPH)
        b.time.setText(f"{fmt_time(pos)} / {fmt_time(dur)}")
        if not b.seek.dragging:
            b.seek.setValue(int(pos / dur * 1000) if pos is not None and dur else 0)
        if vol is not None and not b.vol.dragging:
            b.vol.setValue(round(vol))
        b.vol_icon.setText(MUTED_GLYPH if muted else VOLUME_GLYPH)

    # --- input --------------------------------------------------------------
    def eventFilter(self, obj, ev):
        # Window-level shortcuts: catch keys before any focused widget sees them.
        t = ev.type()
        if t in (QEvent.KeyPress, QEvent.ShortcutOverride) and isinstance(ev, QKeyEvent):
            w = obj if isinstance(obj, QWidget) else None
            if w is not None and w.window() is self and not QApplication.activeModalWidget():
                if t == QEvent.ShortcutOverride:
                    if self._shortcut_for(ev) is not None:
                        ev.accept()
                        return True
                    return False
                action = self._shortcut_for(ev)
                if action is not None:
                    if not ev.isAutoRepeat() or action[1]:
                        action[0]()
                    return True
        return super().eventFilter(obj, ev)

    def _shortcut_for(self, ev):
        """Return (callable, allow_autorepeat) for a key event, or None."""
        k = ev.key()
        mods = ev.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier)
        shift = mods == Qt.ShiftModifier
        none = mods == Qt.NoModifier
        if k == Qt.Key_O and mods == Qt.ControlModifier:
            return (self.open_dialog, False)
        if k in (Qt.Key_Tab, Qt.Key_Backtab) and (none or shift):
            return (self.toggle_bar, False)
        if not (none or shift):
            return None
        if k == Qt.Key_Space and none:
            return (self.toggle_pause, False)
        if k == Qt.Key_Left:
            return (lambda: self.seek(-(SKIP_LARGE if shift else SKIP_SMALL)), True)
        if k == Qt.Key_Right:
            return (lambda: self.seek(SKIP_LARGE if shift else SKIP_SMALL), True)
        if k == Qt.Key_Up and none:
            return (lambda: self.change_volume(VOLUME_STEP), True)
        if k == Qt.Key_Down and none:
            return (lambda: self.change_volume(-VOLUME_STEP), True)
        if k == Qt.Key_F and none:
            return (self.toggle_fullscreen, False)
        if k == Qt.Key_Escape and none:
            return ((lambda: self.isFullScreen() and self.showNormal()), False)
        if k == Qt.Key_Home and none:
            return (self.go_to_start, False)
        if k == Qt.Key_N and none:
            return ((lambda: self.step_file(1)), False)
        if k == Qt.Key_P and none:
            return ((lambda: self.step_file(-1)), False)
        if k == Qt.Key_S and none:
            return ((lambda: self.cycle_track("sub")), False)
        if k == Qt.Key_A and none:
            return ((lambda: self.cycle_track("audio")), False)
        if k == Qt.Key_M and none:
            return (self.toggle_mute, False)
        if k == Qt.Key_BracketRight and none:
            return ((lambda: self.step_speed(1)), True)
        if k == Qt.Key_BracketLeft and none:
            return ((lambda: self.step_speed(-1)), True)
        if k == Qt.Key_Backspace and none:
            return ((lambda: self.step_speed(0)), False)
        if k == Qt.Key_Period and none:
            return ((lambda: self.frame_step(True)), True)
        if k == Qt.Key_Comma and none:
            return ((lambda: self.frame_step(False)), True)
        return None

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.open_file(urls[0].toLocalFile())
            e.acceptProposedAction()

    def receive_from_other_instance(self, path):
        """A second launch (e.g. double-clicking a video) handed us a file."""
        if path:
            self.open_file(path)
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        self.poll.stop()
        self.saver.stop()
        self.save_position()
        self.volume_saver.stop()
        self.save_volume()
        self.mpv.terminate()
        updater.apply_on_exit()        # a staged update replaces the app once we've exited
        super().closeEvent(e)


def _menu_offset(menu):
    """Open the menu just above its button, right-aligned to it."""
    from PySide6.QtCore import QPoint
    size = menu.sizeHint()
    return QPoint(size.width(), size.height())


def hand_to_running_instance(path):
    """If Quiet Player is already open, give it the file and return True."""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_NAME)
    if not sock.waitForConnected(300):
        return False
    if sys.platform == "win32":
        # We were launched by Explorer, which let us take the foreground. Pass that
        # on, or Windows only flashes the running window's taskbar button.
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)   # ASFW_ANY
    sock.write((os.path.abspath(path) if path else "").encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def listen_for_other_instances(window):
    server = QLocalServer(window)
    QLocalServer.removeServer(INSTANCE_NAME)   # clear a stale name after a crash

    def on_connection():
        conn = server.nextPendingConnection()

        done = []

        def read():
            if done:
                return
            done.append(True)
            data = bytes(conn.readAll()).decode("utf-8", "replace").strip()
            conn.deleteLater()
            window.receive_from_other_instance(data)
        conn.disconnected.connect(read)
        if conn.state() == QLocalSocket.UnconnectedState:   # already gone
            read()
    server.newConnection.connect(on_connection)
    server.listen(INSTANCE_NAME)
    return server


def run_installer(args):
    """'Install Quiet Player.bat' in the downloaded ZIP runs QuietPlayer.exe --install.
    Test-only options: --install-to <dir>, --no-shortcut, --no-register, --quiet."""
    dest = args[args.index("--install-to") + 1] if "--install-to" in args else None
    quiet = "--quiet" in args
    try:
        exe = updater.install(dest_dir=dest, shortcut="--no-shortcut" not in args,
                              register="--no-register" not in args)
    except (updater.UpdateError, OSError) as err:
        updater.log(f"install failed: {err}")
        if not quiet:
            QMessageBox.warning(None, "Quiet Player", f"Installing Quiet Player failed.\n\n{err}")
        return 1
    if quiet:
        return 0
    box = QMessageBox(QMessageBox.Information, "Quiet Player",
                      f"Quiet Player {updater.APP_VERSION} is installed, with a shortcut in "
                      "the Start menu. It keeps itself up to date: new versions download "
                      "quietly and install when you close the player.\n\n"
                      "Make it your default video player now?")
    yes = box.addButton("Make it my default…", QMessageBox.AcceptRole)
    box.addButton("Not now", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is yes:
        QMessageBox.information(None, "Quiet Player", DEFAULT_APP_STEPS)
        default_player.open_default_apps_settings()
    subprocess.Popen([exe], close_fds=True)
    return 0


def main():
    if "--register" in sys.argv[1:]:
        # Used by install.bat: point the existing registration at this program,
        # in place (same ProgID, so the user's default-app choices stay). No window.
        try:
            default_player.register(list(VIDEO_EXTS))
        except OSError:
            sys.exit(1)
        sys.exit(0)
    app = QApplication(sys.argv)
    if os.path.exists(ICON_FILE):
        app.setWindowIcon(QIcon(ICON_FILE))
    if "--install" in sys.argv[1:]:
        sys.exit(run_installer(sys.argv[1:]))
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if hand_to_running_instance(path):
        return
    import locale
    locale.setlocale(locale.LC_NUMERIC, "C")   # libmpv requires C numeric locale
    w = PlayerWindow()
    w._server = listen_for_other_instances(w)
    w.show()
    if path:
        w.open_file(path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

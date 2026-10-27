"""Quiet Player — a local video player whose control bar stays out of the way.

The bar lives in its own strip below the video (never overlaid), hides
instantly, and only comes back on Tab or middle-click on the video.
"""

import json
import os
import re
import sys
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

PLAY_GLYPH = "▶︎"
PAUSE_GLYPH = "⏸︎"

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

# libmpv-2.dll may sit next to this script.
_here = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] = _here + os.pathsep + os.environ.get("PATH", "")
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(_here)

import mpv
from PySide6.QtCore import QEvent, QLocale, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                               QMainWindow, QPushButton, QSlider, QStyle,
                               QVBoxLayout, QWidget)

def fmt_time(t):
    if t is None or t < 0:
        return "--:--"
    t = int(t)
    h, m, s = t // 3600, t % 3600 // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def norm_path(path):
    return os.path.normcase(os.path.abspath(path))


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

    def mousePressEvent(self, e):
        b = e.button()
        if b == Qt.LeftButton:
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
            QPushButton, QLabel#icon { border: none; padding: 0 8px; min-width: 28px;
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

        self.back = btn("⏪︎", f"Back {SKIP_SMALL}s (←)", lambda: pw.seek(-SKIP_SMALL))
        self.play = btn(PLAY_GLYPH, "Play/Pause (Space)", pw.toggle_pause)
        self.fwd = btn("⏩︎", f"Ahead {SKIP_SMALL}s (→)", lambda: pw.seek(SKIP_SMALL))
        self.seek = JumpSlider(pw.seek_to_permille)
        self.seek.setRange(0, 1000)
        self.time = QLabel("--:-- / --:--")
        self.vol_icon = QLabel("🔊︎")
        self.vol_icon.setObjectName("icon")
        self.vol = JumpSlider(pw.set_volume)
        self.vol.setRange(0, 100)
        self.vol.setFixedWidth(90)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 10, 0)
        lay.setSpacing(4)
        for w in (self.back, self.play, self.fwd):
            lay.addWidget(w)
        lay.addWidget(self.seek, 1)
        lay.addWidget(self.time)
        lay.addWidget(self.vol_icon)
        lay.addWidget(self.vol)


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
        )
        self.mpv.volume = 70

        self.positions = PositionStore()
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

        self.poll = QTimer(self)
        self.poll.timeout.connect(self.refresh)
        self.poll.start(250)

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
        if lines:
            self.indicate("\n".join(lines), always=True,
                          ms=FILE_INDICATOR_MS if self.announce else INDICATOR_MS)
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
        path, _ = QFileDialog.getOpenFileName(self, "Open video", "", VIDEO_FILTER)
        self.open_file(path)

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

    def change_volume(self, delta):
        v = max(0, min(100, round(self.mpv.volume or 0) + delta))
        self.mpv.volume = v
        self.indicate(f"Vol {v}%")

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
            pos, dur, paused, vol = m.time_pos, m.duration, m.pause, m.volume
        except Exception:
            return
        b = self.bar
        b.play.setText(PLAY_GLYPH if paused or pos is None else PAUSE_GLYPH)
        b.time.setText(f"{fmt_time(pos)} / {fmt_time(dur)}")
        if not b.seek.dragging:
            b.seek.setValue(int(pos / dur * 1000) if pos is not None and dur else 0)
        if vol is not None and not b.vol.dragging:
            b.vol.setValue(round(vol))

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
        return None

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.open_file(urls[0].toLocalFile())
            e.acceptProposedAction()

    def closeEvent(self, e):
        self.poll.stop()
        self.saver.stop()
        self.save_position()
        self.mpv.terminate()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    import locale
    locale.setlocale(locale.LC_NUMERIC, "C")   # libmpv requires C numeric locale
    w = PlayerWindow()
    w.show()
    if len(sys.argv) > 1:
        w.open_file(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

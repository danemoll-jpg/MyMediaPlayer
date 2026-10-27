"""Quiet Player — a local video player whose control bar stays out of the way.

The bar lives in its own strip below the video (never overlaid), hides
instantly, and only comes back on Tab or middle-click on the video.
"""

import os
import sys

# Settings -------------------------------------------------------------------
SHOW_INDICATOR = True        # tiny corner text for shortcuts used while the bar is hidden
INDICATOR_MS = 500
BAR_HEIGHT = 40
SKIP_SMALL = 10              # seconds (arrows)
SKIP_LARGE = 60              # seconds (Shift+arrows)
VOLUME_STEP = 5

PLAY_GLYPH = "▶︎"
PAUSE_GLYPH = "⏸︎"

VIDEO_FILTER = ("Videos (*.mp4 *.m4v *.mkv *.avi *.mov *.wmv *.webm *.flv *.ts "
                "*.m2ts *.mpg *.mpeg *.3gp *.ogv);;All files (*)")

# libmpv-2.dll may sit next to this script.
_here = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] = _here + os.pathsep + os.environ.get("PATH", "")
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(_here)

import mpv
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
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
        )
        self.mpv.volume = 70

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
    def open_file(self, path):
        if not path:
            return
        self.mpv.play(path)
        self.mpv.pause = False
        self.setWindowTitle(f"{os.path.basename(path)} — Quiet Player")

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

    def indicate(self, text):
        """Brief corner text, only while the bar is hidden. Drawn by mpv's OSD
        renderer at level 0 (mpv's own OSD stays off via osd-level=0)."""
        if SHOW_INDICATOR and not self.bar_visible:
            self.mpv.command("show-text", text, INDICATOR_MS, 0)

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

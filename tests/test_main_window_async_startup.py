import time
import threading

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QAction, QCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from iptv_player.main_window import MainWindow
from iptv_player.models import Channel


class SlowMpvProcess:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.ipc = self.FakeIpc()
        self.request_id = 0

    class FakeIpc:
        def __init__(self) -> None:
            self.callbacks = []

        def add_callback(self, callback) -> None:
            self.callbacks.append(callback)

    def start(self, hwnd: int) -> None:
        time.sleep(0.25)
        self.started = True

    def reserve_request_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def load_channel(self, channel, request_id: int | None = None) -> int:
        request_id = request_id if request_id is not None else self.reserve_request_id()

        def report_loaded() -> None:
            time.sleep(0.25)
            for callback in self.ipc.callbacks:
                callback(
                    {
                        "request_id": request_id,
                        "error": "success",
                        "data": {"playlist_entry_id": request_id},
                    }
                )
                callback(
                    {"event": "file-loaded", "playlist_entry_id": request_id}
                )

        threading.Thread(target=report_loaded, daemon=True).start()
        return request_id

    def send_command(self, command, request_id: int | None = None) -> int:
        if command[0] == "loadfile":
            return self.load_channel(Channel(name="Test", url=command[1]), request_id)
        return request_id if request_id is not None else self.reserve_request_id()

    def observe_property(self, property_name: str, observer_id: int) -> int:
        return self.reserve_request_id()

    def stop(self) -> None:
        self.stopped = True


def test_player_startup_playback_and_exit_do_not_block_the_gui_thread(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    fake_process = SlowMpvProcess()
    window = MainWindow(mpv_process=fake_process)
    timer_fired = False

    def mark_timer_fired() -> None:
        nonlocal timer_fired
        timer_fired = True

    window.show()
    QTimer.singleShot(0, mark_timer_fired)
    app.processEvents()

    assert timer_fired
    assert not fake_process.started

    deadline = time.monotonic() + 2
    while not window._mpv_started and time.monotonic() < deadline:
        QTest.qWait(10)

    assert window._mpv_started
    assert fake_process.started

    channel = Channel(name="Test", url="rtsp://example.com/stream")
    window._play_channel(channel)
    timer_fired = False
    QTimer.singleShot(0, mark_timer_fired)
    app.processEvents()
    assert timer_fired

    deadline = time.monotonic() + 2
    while window.current_channel is None and time.monotonic() < deadline:
        QTest.qWait(10)
    assert window.current_channel is not None

    window.channels = [channel]
    window._overlay.update_channels(window.channels)
    cursor_position = window._video_widget.mapToGlobal(QPoint(20, 20))
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: cursor_position))
    window._last_cursor_position = cursor_position - QPoint(1, 0)
    window._check_cursor_position()
    assert not window._overlay.isVisible()

    playlist_position = window._video_widget.mapToGlobal(
        QPoint(window._video_widget.width() - 30, 30)
    )
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: playlist_position))
    window._last_cursor_position = playlist_position - QPoint(1, 0)
    window._check_cursor_position()
    assert window._overlay.isVisible()

    overlay_position = window._overlay.mapToGlobal(QPoint(10, 10))
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: overlay_position))
    window._last_cursor_position = overlay_position - QPoint(1, 0)
    window._check_cursor_position()
    assert window._overlay.isVisible()
    window._hide_overlay_if_cursor_outside()
    assert window._overlay.isVisible()

    away_position = window._video_widget.mapToGlobal(
        QPoint(window._video_widget.width() // 2, window._video_widget.height() // 2)
    )
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: away_position))
    window._last_cursor_position = away_position - QPoint(1, 0)
    window._check_cursor_position()
    assert not window._overlay.isVisible()

    exit_action = next(action for action in window.findChildren(QAction) if action.text() == "E&xit")
    exit_action.trigger()
    deadline = time.monotonic() + 2
    while window.isVisible() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert fake_process.stopped
    assert not window.isVisible()

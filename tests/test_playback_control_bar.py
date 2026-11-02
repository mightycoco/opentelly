from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from iptv_player.main_window import MainWindow
from iptv_player.playback_control_bar import PlaybackControlBar


def test_playback_control_bar_updates_states_and_emits_actions() -> None:
    app = QApplication.instance() or QApplication([])
    parent = QMainWindow()
    video_widget = QWidget(parent)
    parent.setCentralWidget(video_widget)
    parent.resize(1280, 720)
    parent.show()
    controls = PlaybackControlBar(parent)

    controls.position_overlay()
    expected_position = video_widget.mapToGlobal(
        QPoint(18, video_widget.height() - controls.height() - 18)
    )
    assert controls.pos() == expected_position

    previous = QSignalSpy(controls.previous_requested)
    stop_play = QSignalSpy(controls.stop_play_requested)
    mute = QSignalSpy(controls.mute_toggled)
    next_channel = QSignalSpy(controls.next_requested)
    controls.previous_button.click()
    controls.stop_play_button.click()
    controls.mute_button.click()
    controls.next_button.click()

    assert previous.count() == 1
    assert stop_play.count() == 1
    assert mute.count() == 1
    assert mute.at(0)[0] is True
    assert next_channel.count() == 1
    assert controls.is_muted
    assert controls.mute_button.toolTip() == "Unmute"

    controls.set_muted(False)
    controls.set_playback_stopped(True)
    assert not controls.is_muted
    assert controls.mute_button.toolTip() == "Mute"
    assert controls.stop_play_button.toolTip() == "Play"
    controls.close()
    parent.close()


def test_main_window_shows_controls_only_in_bottom_left_hover_area(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1280, 720)
    window.show()
    app.processEvents()

    bottom_left = window._video_widget.mapToGlobal(
        QPoint(20, window._video_widget.height() - 20)
    )
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: bottom_left))
    window._last_cursor_position = bottom_left - QPoint(1, 0)
    window._check_cursor_position()
    assert window._playback_controls.isVisible()

    center = window._video_widget.mapToGlobal(
        QPoint(window._video_widget.width() // 2, window._video_widget.height() // 2)
    )
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: center))
    window._last_cursor_position = center - QPoint(1, 0)
    window._check_cursor_position()
    assert not window._playback_controls.isVisible()
    window.close()

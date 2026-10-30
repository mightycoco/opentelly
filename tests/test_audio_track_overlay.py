from PySide6.QtCore import QPoint
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from iptv_player.audio_track_overlay import AudioTrackOverlay
from iptv_player.models import AudioTrack


def test_audio_overlay_only_shows_for_multiple_tracks_and_marks_selection() -> None:
    app = QApplication.instance() or QApplication([])
    parent = QMainWindow()
    video_widget = QWidget(parent)
    parent.setCentralWidget(video_widget)
    parent.resize(1280, 720)
    parent.show()
    overlay = AudioTrackOverlay(parent)

    overlay.update_tracks([AudioTrack(track_id=1, selected=True)])
    app.processEvents()
    assert not overlay.isVisible()

    overlay.update_tracks(
        [
            AudioTrack(track_id=1, title="English", selected=True),
            AudioTrack(track_id=2, title="Deutsch"),
        ]
    )
    app.processEvents()

    assert overlay.isVisible()
    assert overlay.isWindow()
    actions = overlay._menu.actions()
    assert [action.text() for action in actions] == ["English", "Deutsch"]
    assert not actions[0].icon().isNull()
    assert actions[0].isChecked()
    assert actions[1].icon().isNull()
    expected_position = video_widget.mapToGlobal(
        QPoint(
            video_widget.width() - overlay.width() - 18,
            video_widget.height() - overlay.height() - 18,
        )
    )
    assert overlay.pos() == expected_position

    selected_tracks = QSignalSpy(overlay.track_selected)
    actions[1].trigger()
    assert selected_tracks.count() == 1
    assert selected_tracks.at(0)[0] == 2

    overlay.update_tracks([])
    assert not overlay.isVisible()
    overlay.close()
    parent.close()

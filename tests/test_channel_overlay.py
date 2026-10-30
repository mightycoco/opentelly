from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from iptv_player.channel_overlay import ChannelOverlay
from iptv_player.models import Channel


def test_overlay_shows_channel_list_using_widget_item_count() -> None:
    app = QApplication.instance() or QApplication([])
    parent = QMainWindow()
    video_widget = QWidget(parent)
    parent.setCentralWidget(video_widget)
    parent.resize(1280, 720)
    parent.show()
    overlay = ChannelOverlay(parent)
    overlay.update_channels(
        [
            Channel(name="Channel One", url="rtsp://example.com/one"),
            Channel(name="Channel Two", url="rtsp://example.com/two"),
        ]
    )

    overlay.show_overlay()
    app.processEvents()

    assert overlay.isVisible()
    assert overlay.isWindow()
    assert overlay.list_widget.count() == 2
    assert overlay.height() == 300
    expected_position = video_widget.mapToGlobal(
        QPoint(video_widget.width() - overlay.width() - 18, 18)
    )
    assert overlay.pos() == expected_position
    assert overlay.parentWidget() is parent

    overlay.update_favourites(
        [Channel(name="Channel Two", url="rtsp://example.com/two")]
    )
    overlay.favourites_button.click()
    assert overlay.showing_favourites
    assert overlay.list_widget.count() == 1
    assert overlay.list_widget.item(0).text() == "Channel Two"
    overlay.playlist_button.click()
    assert not overlay.showing_favourites
    assert overlay.list_widget.count() == 2

    overlay.close()
    parent.close()

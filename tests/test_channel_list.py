from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from iptv_player.channel_list import ChannelListWidget
from iptv_player.models import Channel
from iptv_player.preferences import channel_key


def test_channel_list_marks_favourites_with_a_star_icon() -> None:
    app = QApplication.instance() or QApplication([])
    channels = [
        Channel(name="Favourite", url="rtsp://example.com/favourite"),
        Channel(name="Regular", url="rtsp://example.com/regular"),
    ]
    widget = ChannelListWidget()

    widget.populate(channels, {channel_key(channels[0])})

    assert widget.count() == 2
    assert not widget.item(0).icon().isNull()
    assert widget.item(0).data(Qt.UserRole) == channels[0]
    assert not widget.item(1).icon().isNull()
    toggled = QSignalSpy(widget.favourite_toggle_requested)
    widget.resize(300, 160)
    widget.show()
    app.processEvents()
    item_rect = widget.visualItemRect(widget.item(1))
    QTest.mouseClick(
        widget.viewport(),
        Qt.LeftButton,
        pos=QPoint(item_rect.left() + 10, item_rect.center().y()),
    )
    assert toggled.count() == 1
    assert toggled.at(0)[0] == channels[1]
    widget.close()

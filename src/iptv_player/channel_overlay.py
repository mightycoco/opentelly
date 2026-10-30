from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from iptv_player.channel_list import ChannelListWidget
from iptv_player.models import Channel
from iptv_player.preferences import channel_key


class ChannelOverlay(QWidget):
    """Overlay panel displaying the current channel list."""

    favourite_toggle_requested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.list_widget = ChannelListWidget(self)
        self.list_widget.setFixedWidth(340)
        self.list_widget.favourite_toggle_requested.connect(
            self.favourite_toggle_requested
        )
        self.playlist_button = QPushButton("Playlist", self)
        self.favourites_button = QPushButton("Favourites", self)
        self.playlist_button.setObjectName("playlist_button")
        self.favourites_button.setObjectName("favourites_button")
        for button in (self.playlist_button, self.favourites_button):
            button.setCheckable(True)
        self.playlist_button.setChecked(True)
        self.playlist_button.clicked.connect(self.show_playlist)
        self.favourites_button.clicked.connect(self.show_favourites)
        header = QHBoxLayout()
        header.addWidget(self.playlist_button)
        header.addWidget(self.favourites_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self.list_widget)
        self.resize(340, 420)
        self._channels: list[Channel] = []
        self._favourites: list[Channel] = []
        self._showing_favourites = False
        self.hide()

    def update_channels(
        self,
        channels: list[Channel],
        favourites: list[Channel] | None = None,
    ) -> None:
        self._channels = channels
        if favourites is not None:
            self._favourites = favourites
        self._populate_current_list()

    def update_favourites(self, favourites: list[Channel]) -> None:
        self._favourites = favourites
        self._populate_current_list()

    def show_playlist(self) -> None:
        self._showing_favourites = False
        self.playlist_button.setChecked(True)
        self.favourites_button.setChecked(False)
        self._populate_current_list()

    def show_favourites(self) -> None:
        self._showing_favourites = True
        self.playlist_button.setChecked(False)
        self.favourites_button.setChecked(True)
        self._populate_current_list()

    @property
    def showing_favourites(self) -> bool:
        return self._showing_favourites

    def _populate_current_list(self) -> None:
        channels = self._favourites if self._showing_favourites else self._channels
        favourite_keys = {channel_key(channel) for channel in self._favourites}
        self.list_widget.populate(channels, favourite_keys)

    def show_overlay(self) -> None:
        if self.parentWidget() is None:
            return
        self.position_overlay()
        self.raise_()
        self.show()

    def position_overlay(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        video_widget = parent.centralWidget()
        if video_widget is None:
            return
        panel_height = min(
            500,
            max(300, self.list_widget.count() * 38 + 42),
            max(1, video_widget.height() - 36),
        )
        self.resize(340, panel_height)
        position = video_widget.mapToGlobal(
            QPoint(video_widget.width() - self.width() - 18, 18)
        )
        self.move(position)

    def hide_overlay(self) -> None:
        self.hide()

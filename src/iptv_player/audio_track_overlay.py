from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from iptv_player.models import AudioTrack


class AudioTrackOverlay(QWidget):
    """Bottom-right control for selecting the current audio stream."""

    track_selected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._audio_icon = QApplication.style().standardIcon(QStyle.SP_MediaVolume)
        self._button = QToolButton(self)
        self._button.setObjectName("audio_track_button")
        self._button.setIcon(self._audio_icon)
        self._button.setToolTip("Select audio track")
        self._button.setAccessibleName("Select audio track")
        self._button.setIconSize(QSize(24, 24))
        self._button.setStyleSheet(
            "QToolButton { background: rgba(235, 235, 235, 220);"
            " border: 1px solid rgba(0, 0, 0, 100); border-radius: 6px; padding: 8px; }"
            " QToolButton:hover { background: rgba(255, 255, 255, 240); }"
        )
        self._button.setPopupMode(QToolButton.InstantPopup)
        self._menu = QMenu(self._button)
        self._button.setMenu(self._menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._button)
        self._tracks: list[AudioTrack] = []
        self.resize(48, 44)
        self.hide()

    def update_tracks(self, tracks: list[AudioTrack]) -> None:
        self._tracks = tracks
        self._menu.clear()
        for track in tracks:
            action = self._menu.addAction(
                self._audio_icon if track.selected else QIcon(),
                track.label,
            )
            action.setCheckable(True)
            action.setChecked(track.selected)
            action.setData(track.track_id)
            action.triggered.connect(
                lambda checked=False, selected_action=action: self._select_track(
                    selected_action
                )
            )

        if len(tracks) > 1:
            self.raise_()
            self.show()
            self.position_overlay()
        else:
            self.hide()

    def _select_track(self, action) -> None:
        track_id = action.data()
        if isinstance(track_id, int):
            self.track_selected.emit(track_id)

    def position_overlay(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        video_widget = parent.centralWidget()
        if video_widget is None:
            return
        position = video_widget.mapToGlobal(
            QPoint(
                video_widget.width() - self.width() - 18,
                video_widget.height() - self.height() - 18,
            )
        )
        self.move(position)

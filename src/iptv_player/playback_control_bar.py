from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QStyle, QToolButton, QWidget


class PlaybackControlBar(QWidget):
    """Bottom-left playback controls displayed over the video."""

    previous_requested = Signal()
    stop_play_requested = Signal()
    mute_toggled = Signal(bool)
    next_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(
            "PlaybackControlBar { background: rgba(25, 25, 25, 210);"
            " border: 1px solid rgba(255, 255, 255, 90); border-radius: 6px; }"
        )
        self._style = QApplication.style()
        self._muted = False
        self.previous_button = self._create_button(
            "previous_button",
            "Previous channel",
            QStyle.StandardPixmap.SP_MediaSkipBackward,
        )
        self.stop_play_button = self._create_button(
            "stop_play_button",
            "Stop playback",
            QStyle.StandardPixmap.SP_MediaStop,
        )
        self.mute_button = self._create_button(
            "mute_button",
            "Mute",
            QStyle.StandardPixmap.SP_MediaVolume,
        )
        self.next_button = self._create_button(
            "next_button",
            "Next channel",
            QStyle.StandardPixmap.SP_MediaSkipForward,
        )
        self.previous_button.clicked.connect(self.previous_requested)
        self.stop_play_button.clicked.connect(self.stop_play_requested)
        self.mute_button.clicked.connect(self._toggle_mute)
        self.next_button.clicked.connect(self.next_requested)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        for button in (
            self.previous_button,
            self.stop_play_button,
            self.mute_button,
            self.next_button,
        ):
            layout.addWidget(button)
        self.adjustSize()
        self.hide()

    def _create_button(
        self,
        name: str,
        description: str,
        icon: QStyle.StandardPixmap,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(name)
        button.setAccessibleName(description)
        button.setToolTip(description)
        button.setIcon(self._style.standardIcon(icon))
        button.setIconSize(QSize(22, 22))
        button.setFixedSize(40, 40)
        button.setStyleSheet(
            "QToolButton { color: white; background: rgba(235, 235, 235, 220);"
            " border: 1px solid rgba(0, 0, 0, 100); border-radius: 5px; }"
            " QToolButton:hover { background: rgba(255, 255, 255, 245); }"
            " QToolButton:disabled { background: rgba(110, 110, 110, 150); }"
        )
        return button

    @property
    def is_muted(self) -> bool:
        return self._muted

    def set_playback_stopped(self, stopped: bool) -> None:
        description = "Play" if stopped else "Stop playback"
        icon = (
            QStyle.StandardPixmap.SP_MediaPlay
            if stopped
            else QStyle.StandardPixmap.SP_MediaStop
        )
        self.stop_play_button.setAccessibleName(description)
        self.stop_play_button.setToolTip(description)
        self.stop_play_button.setIcon(self._style.standardIcon(icon))

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        description = "Unmute" if muted else "Mute"
        icon = (
            QStyle.StandardPixmap.SP_MediaVolumeMuted
            if muted
            else QStyle.StandardPixmap.SP_MediaVolume
        )
        self.mute_button.setAccessibleName(description)
        self.mute_button.setToolTip(description)
        self.mute_button.setIcon(self._style.standardIcon(icon))

    def set_navigation_enabled(self, enabled: bool) -> None:
        self.previous_button.setEnabled(enabled)
        self.next_button.setEnabled(enabled)

    def set_playback_enabled(self, enabled: bool) -> None:
        self.stop_play_button.setEnabled(enabled)
        self.mute_button.setEnabled(enabled)

    def position_overlay(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        video_widget = parent.centralWidget()
        if video_widget is None:
            return
        position = video_widget.mapToGlobal(
            QPoint(18, video_widget.height() - self.height() - 18)
        )
        self.move(position)

    def _toggle_mute(self) -> None:
        self.set_muted(not self._muted)
        self.mute_toggled.emit(self._muted)

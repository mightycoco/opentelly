from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


class VideoWidget(QWidget):
    """Host widget used to embed the mpv video output."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("video_widget")
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background: black;")

    def native_window_handle(self) -> int:
        handle = self.winId()
        if handle == 0:
            raise RuntimeError("The native widget handle is not available yet")
        return int(handle)

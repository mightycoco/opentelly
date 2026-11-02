from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from iptv_player.player.backend import MpvBackend


class MpvRenderWidget(QOpenGLWidget):
    """OpenGL surface rendered by libmpv."""

    request_render_update = Signal()

    def __init__(self, backend: MpvBackend, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backend = backend
        self.setObjectName("video_widget")
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background: black;")
        self.request_render_update.connect(self.update)

    def paintGL(self) -> None:
        self._backend.render(
            self.defaultFramebufferObject(),
            int(self.width() * self.devicePixelRatio()),
            int(self.height() * self.devicePixelRatio()),
        )

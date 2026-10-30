from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QMenu

from iptv_player.models import Channel
from iptv_player.preferences import channel_key


class ChannelListWidget(QListWidget):
    """Simple list of channels for the overlay."""

    favourite_toggle_requested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("channel_list")
        self.setAlternatingRowColors(True)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._favourite_keys: set[str] = set()
        self.setStyleSheet(
            """
            QListWidget { background: rgba(15, 15, 15, 180); color: white; border: 1px solid rgba(255,255,255,80); }
            QListWidget::item { padding: 10px; }
            QListWidget::item:selected { background: rgba(76, 175, 80, 180); color: white; }
            """
        )

    def populate(
        self,
        channels: list[Channel],
        favourites: set[str] | None = None,
    ) -> None:
        self.clear()
        favourite_keys = favourites or set()
        self._favourite_keys = favourite_keys
        for channel in channels:
            is_favourite = channel_key(channel) in favourite_keys
            icon = self._favourite_icon(is_favourite)
            item = QListWidgetItem(icon, channel.name or channel.url)
            item.setToolTip(
                "Click the star or right-click to remove from favourites."
                if is_favourite
                else "Click the star or right-click to add to favourites."
            )
            item.setData(Qt.ItemDataRole.UserRole, channel)
            self.addItem(item)

    @staticmethod
    def _favourite_icon(favourite: bool) -> QIcon:
        size = 18
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        points = []
        for index in range(10):
            radius = 8 if index % 2 == 0 else 3.5
            angle = -math.pi / 2 + index * math.pi / 5
            points.append(
                QPointF(size / 2 + math.cos(angle) * radius, size / 2 + math.sin(angle) * radius)
            )
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        path.closeSubpath()
        if favourite:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ffd54f"))
        else:
            painter.setPen(QColor("#ffd54f"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()
        return QIcon(pixmap)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if item is not None and self.visualItemRect(item).left() + 30 >= event.position().x():
                channel = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(channel, Channel):
                    self.favourite_toggle_requested.emit(channel)
                    event.accept()
                    return
        super().mouseReleaseEvent(event)

    def _show_context_menu(self, position) -> None:
        item = self.itemAt(position)
        if item is None:
            return
        channel = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(channel, Channel):
            return
        menu = QMenu(self)
        action = menu.addAction(
            "Remove from favourites"
            if channel_key(channel) in self._favourite_keys
            else "Add to favourites"
        )
        action.triggered.connect(
            lambda checked=False: self.favourite_toggle_requested.emit(channel)
        )
        menu.exec(self.mapToGlobal(position))

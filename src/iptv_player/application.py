from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from iptv_player.main_window import MainWindow


class IPTVApplication(QApplication):
    """Qt application entry point."""

    def __init__(self, argv: list[str] | None = None) -> None:
        arguments = argv or sys.argv
        super().__init__(arguments)
        playlist_path = next((arg for arg in arguments[1:] if not arg.startswith("-")), None)
        self.main_window = MainWindow(playlist_path=playlist_path)

    def run(self) -> int:
        if self.main_window.saved_window_state is None:
            self.main_window.showMaximized()
        else:
            self.main_window.show()
        return self.exec()

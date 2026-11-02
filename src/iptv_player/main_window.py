from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
from typing import cast

from PySide6.QtCore import QEvent, QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMenu, QMessageBox, QStatusBar

from iptv_player.audio_track_overlay import AudioTrackOverlay
from iptv_player.channel_overlay import ChannelOverlay
from iptv_player.models import AudioTrack, Channel
from iptv_player.player.backend import MpvBackend
from iptv_player.player.factory import create_mpv_backend
from iptv_player.player.worker import MpvWorker
from iptv_player.playback_control_bar import PlaybackControlBar
from iptv_player.preferences import PlayerPreferences, channel_key
from iptv_player.playlist.m3u_parser import parse_m3u_playlist
from iptv_player.settings import MpvSettings
from iptv_player.render_video_widget import MpvRenderWidget
from iptv_player.video_widget import VideoWidget

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    start_player_requested = Signal(object)
    load_channel_requested = Signal(object)
    stop_player_requested = Signal()

    def __init__(
        self,
        playlist_path: str | Path | None = None,
        mpv_process: MpvBackend | None = None,
        preferences: PlayerPreferences | None = None,
    ) -> None:
        super().__init__()
        self._preferences = preferences or PlayerPreferences()
        self._mpv_settings = MpvSettings()
        self._mpv = mpv_process or create_mpv_backend(self._mpv_settings)
        self.channels: list[Channel] = []
        self._favourites = self._preferences.favourites()
        self.current_channel: Channel | None = None
        self._playlist_path = Path(playlist_path) if playlist_path else None
        self._initial_channel: Channel | None = None
        if self._mpv.requires_render_widget:
            self._video_widget = MpvRenderWidget(self._mpv, self)
        else:
            self._video_widget = VideoWidget(self)
        self._overlay = ChannelOverlay(self)
        self._overlay.list_widget.itemClicked.connect(self._on_channel_selected)
        self._overlay.favourite_toggle_requested.connect(self._toggle_favourite)
        self._overlay.update_channels([], self._favourites)
        self._audio_overlay = AudioTrackOverlay(self)
        self._audio_overlay.track_selected.connect(self._on_audio_track_selected)
        self._playback_controls = PlaybackControlBar(self)
        self._playback_controls.previous_requested.connect(self._play_previous_channel)
        self._playback_controls.stop_play_requested.connect(self._toggle_playback_stopped)
        self._playback_controls.mute_toggled.connect(self._set_muted)
        self._playback_controls.next_requested.connect(self._play_next_channel)
        self.setCentralWidget(self._video_widget)
        self.setWindowTitle("Open Telly")
        self.resize(1280, 720)
        self.setMouseTracking(True)
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._setup_menu()
        self._restore_window_preferences()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_overlay_if_cursor_outside)
        self._channel_load_timer = QTimer(self)
        self._channel_load_timer.setSingleShot(True)
        self._channel_load_timer.setInterval(30000)
        self._channel_load_timer.timeout.connect(self._on_channel_load_timeout)
        self._player_worker = MpvWorker(self._mpv)
        self.start_player_requested.connect(self._player_worker.start)
        self.load_channel_requested.connect(self._player_worker.load_channel)
        self.stop_player_requested.connect(self._player_worker.stop)
        queued_connection = Qt.ConnectionType.QueuedConnection
        self._player_worker.ready.connect(self._on_player_ready, queued_connection)
        self._player_worker.startup_failed.connect(self._on_player_startup_failed, queued_connection)
        self._player_worker.channel_loaded.connect(self._on_channel_loaded, queued_connection)
        self._player_worker.channel_failed.connect(self._on_channel_failed, queued_connection)
        self._player_worker.audio_tracks_changed.connect(
            self._on_audio_tracks_changed,
            queued_connection,
        )
        self._player_worker.audio_tracks_snapshot.connect(
            self._on_audio_tracks_snapshot,
            queued_connection,
        )
        self._player_worker.stream_title_changed.connect(
            self._on_stream_title_changed,
            queued_connection,
        )
        self._player_worker.audio_selection_failed.connect(
            self._on_audio_selection_failed,
            queued_connection,
        )
        self._player_worker.playback_control_failed.connect(
            self._on_playback_control_failed,
            queued_connection,
        )
        self._player_worker.stopped.connect(self._on_player_stopped, queued_connection)
        self._mpv_started = False
        self._mpv_starting = False
        self._pending_channel: Channel | None = None
        self._loading_channel: Channel | None = None
        self._stream_title = ""
        self._playback_stopped = False
        self._muted = False
        self._shutdown_requested = False
        self._shutdown_complete = False
        self._audio_restore_attempted = False
        self._available_audio_tracks: list[AudioTrack] = []
        self._pinned = self._preferences.is_pinned()
        self._last_cursor_position: QPoint | None = None
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(100)
        self._cursor_timer.timeout.connect(self._check_cursor_position)
        self._cursor_timer.start()
        self._update_playback_control_state()

        if self._playlist_path and self._playlist_path.exists():
            self.load_playlist(self._playlist_path)

    def _setup_menu(self) -> None:
        file_menu = QMenu("&File", self)
        self.menuBar().addMenu(file_menu)

        open_action = QAction("&Open playlist...", self)
        open_action.triggered.connect(self._open_playlist_dialog)
        file_menu.addAction(open_action)

        maximize_action = QAction("&Maximize", self)
        maximize_action.triggered.connect(self.showMaximized)
        file_menu.addAction(maximize_action)

        fullscreen_action = QAction("&Full screen", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        file_menu.addAction(fullscreen_action)

        window_menu = QMenu("&Window", self)
        self.menuBar().addMenu(window_menu)
        self._pin_action = QAction("Always on &top", self)
        self._pin_action.setCheckable(True)
        self._pin_action.setChecked(self._preferences.is_pinned())
        self._pin_action.toggled.connect(self._set_pinned)
        window_menu.addAction(self._pin_action)

        file_menu.addSeparator()
        quit_action = QAction("E&xit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _restore_window_preferences(self) -> None:
        geometry = self._preferences.window_geometry()
        if geometry:
            self.restoreGeometry(geometry)

        state = self._preferences.window_state()
        state_flags = {
            "maximized": Qt.WindowState.WindowMaximized,
            "minimized": Qt.WindowState.WindowMinimized,
            "fullscreen": Qt.WindowState.WindowFullScreen,
        }
        if state in state_flags:
            self.setWindowState(state_flags[state])
        elif state == "normal":
            self.setWindowState(Qt.WindowState.WindowNoState)

    @property
    def saved_window_state(self) -> str | None:
        return self._preferences.window_state()

    def _set_pinned(self, pinned: bool) -> None:
        self._pinned = pinned
        self._preferences.save_pinned(pinned)
        if not self.isVisible():
            return
        if os.name == "nt":
            hwnd = int(self.winId())
            insert_after = -1 if pinned else -2
            flags = 0x0001 | 0x0002 | 0x0010
            set_window_pos = ctypes.windll.user32.SetWindowPos
            set_window_pos.argtypes = (
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            )
            set_window_pos.restype = ctypes.c_bool
            if not set_window_pos(
                ctypes.c_void_p(hwnd),
                ctypes.c_void_p(insert_after),
                0,
                0,
                0,
                0,
                flags,
            ):
                error = ctypes.WinError()
                logger.error("Unable to change window pin state: %s", error)
                self._pin_action.blockSignals(True)
                self._pin_action.setChecked(not pinned)
                self._pin_action.blockSignals(False)
                self._pinned = not pinned
                self._preferences.save_pinned(not pinned)
                self._status_bar.showMessage(f"Unable to pin window: {error}", 10000)

    def _save_window_preferences(self) -> None:
        if not self.isMinimized() and not self.isMaximized() and not self.isFullScreen():
            self._preferences.save_window_geometry(memoryview(self.saveGeometry().data()).tobytes())
        if self.isMinimized():
            state = "minimized"
        elif self.isMaximized():
            state = "maximized"
        elif self.isFullScreen():
            state = "fullscreen"
        else:
            state = "normal"
        self._preferences.save_window_state(state)
        self._preferences.save_pinned(self._pinned)
        self._preferences.sync()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _open_playlist_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open playlist",
            str(Path.home()),
            "M3U files (*.m3u *.m3u8 *.txt);;All files (*)",
        )
        if path:
            self.load_playlist(path)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._last_cursor_position = QCursor.pos()
        if self._pinned and os.name == "nt":
            QTimer.singleShot(0, lambda: self._set_pinned(True))
        if not self._mpv_started:
            self._start_mpv()
        if self.channels and self.current_channel is None:
            self._play_channel(self._initial_channel or self.channels[0])

    def _start_mpv(self) -> bool:
        if self._mpv_started or self._mpv_starting:
            return True

        hwnd = None
        if not self._mpv.requires_render_widget:
            try:
                hwnd = cast(VideoWidget, self._video_widget).native_window_handle()
            except RuntimeError as exc:
                logger.exception("Unable to get the video widget handle")
                QMessageBox.critical(self, "Playback error", str(exc))
                return False

        self._mpv_starting = True
        self._status_bar.showMessage("Starting libmpv..." if self._mpv.requires_render_widget else "Starting mpv...")
        self.start_player_requested.emit(hwnd)
        return True

    def _on_player_ready(self) -> None:
        try:
            if self._mpv.requires_render_widget:
                self._mpv.attach_renderer(self._video_widget)
        except Exception as exc:
            self._mpv_starting = False
            logger.exception("Unable to initialize libmpv rendering")
            QMessageBox.critical(
                self,
                "Playback error",
                f"Unable to initialize video rendering: {exc}",
            )
            self.stop_player_requested.emit()
            return
        self._mpv_starting = False
        self._mpv_started = True
        self._update_playback_control_state()
        self._status_bar.showMessage("Player ready", 2000)
        if self._pending_channel is not None:
            channel = self._pending_channel
            self._pending_channel = None
            self._play_channel(channel)

    def _on_player_startup_failed(self, error: str) -> None:
        self._mpv_starting = False
        self._mpv_started = False
        QMessageBox.critical(self, "Playback error", f"Unable to start mpv: {error}")

    def _on_channel_loaded(self, channel: Channel) -> None:
        self._channel_load_timer.stop()
        self._loading_channel = None
        self.current_channel = channel
        self._playback_stopped = False
        self._playback_controls.set_playback_stopped(False)
        self._update_playback_control_state()
        self._audio_restore_attempted = False
        if self._playlist_path:
            self._preferences.save_resume_channel(self._playlist_path, channel)
            self._preferences.sync()
        self._status_bar.showMessage(
            self._playback_status_message(),
            0 if self._stream_title else 2000,
        )

    def _on_stream_title_changed(self, title: str) -> None:
        self._stream_title = title
        if self.current_channel is not None and self._loading_channel is None:
            self._status_bar.showMessage(self._playback_status_message())

    def _playback_status_message(self) -> str:
        if self.current_channel is None:
            return ""
        message = f"Playing: {self.current_channel.name}"
        if self._stream_title:
            message += f" — {self._stream_title}"
        return message

    def _on_channel_failed(self, error: str) -> None:
        self._channel_load_timer.stop()
        self._loading_channel = None
        self._update_playback_control_state()
        logger.error("%s", error)
        self._status_bar.showMessage(error, 15000)

    def _on_audio_track_selected(self, track_id: int) -> None:
        channel = self._loading_channel or self.current_channel
        if channel is not None:
            self._preferences.save_audio_track_id(channel, track_id)
            self._preferences.sync()
        self._audio_restore_attempted = True
        self._player_worker.select_audio_track(track_id)

    def _on_audio_tracks_changed(self, tracks: list[AudioTrack]) -> None:
        self._audio_overlay.update_tracks(tracks)

    def _on_audio_tracks_snapshot(self, tracks: list[AudioTrack]) -> None:
        self._audio_overlay.update_tracks(tracks)
        self._available_audio_tracks = tracks
        channel = self._loading_channel or self.current_channel
        if channel is not None:
            self._apply_audio_preference(channel)

    def _apply_audio_preference(self, channel: Channel) -> None:
        tracks = self._available_audio_tracks
        if not tracks:
            return
        selected_track = next((track for track in tracks if track.selected), None)
        preferred_track_id = self._preferences.audio_track_id(channel)
        if (
            not self._audio_restore_attempted
            and preferred_track_id is not None
        ):
            self._audio_restore_attempted = True
            preferred_track = next(
                (track for track in tracks if track.track_id == preferred_track_id),
                None,
            )
            if preferred_track is not None and not preferred_track.selected:
                self._player_worker.select_audio_track(preferred_track_id)
            return

        if selected_track is not None and preferred_track_id is None:
            self._preferences.save_audio_track_id(channel, selected_track.track_id)
            self._preferences.sync()

    def _on_audio_selection_failed(self, error: str) -> None:
        logger.error("%s", error)
        self._status_bar.showMessage(error, 15000)

    def _on_channel_load_timeout(self) -> None:
        channel_name = self._loading_channel.name if self._loading_channel else "channel"
        self._loading_channel = None
        self._update_playback_control_state()
        message = f"Timed out while loading {channel_name}. Check the stream and RTSP transport."
        logger.error("%s", message)
        self._status_bar.showMessage(message, 15000)

    def load_playlist(self, playlist_path: str | Path) -> None:
        path = Path(playlist_path)
        if not path.exists():
            raise FileNotFoundError(f"Playlist file not found: {path}")

        self._playlist_path = path
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                self.channels = parse_m3u_playlist(handle.read())
        except UnicodeDecodeError:
            with path.open("r", encoding="latin-1", newline="") as handle:
                self.channels = parse_m3u_playlist(handle.read())

        resume_key = self._preferences.resume_channel_key(path)
        self._initial_channel = next(
            (channel for channel in self.channels if channel_key(channel) == resume_key),
            self.channels[0] if self.channels else None,
        )
        self._overlay.update_channels(self.channels, self._favourites)
        self._update_playback_control_state()
        self._status_bar.showMessage(f"Loaded {len(self.channels)} channel(s)", 2500)
        if self.channels and self.isVisible():
            self._play_channel(self._initial_channel or self.channels[0])

    def _toggle_favourite(self, channel: Channel) -> None:
        channel_id = channel_key(channel)
        existing_index = next(
            (
                index
                for index, favourite in enumerate(self._favourites)
                if channel_key(favourite) == channel_id
            ),
            None,
        )
        if existing_index is None:
            self._favourites.append(channel)
        else:
            self._favourites.pop(existing_index)
        self._preferences.save_favourites(self._favourites)
        self._preferences.sync()
        self._overlay.update_channels(self.channels, self._favourites)

    def _play_channel(self, channel: Channel) -> None:
        self._audio_restore_attempted = False
        self._available_audio_tracks = []
        self._stream_title = ""
        self._playback_stopped = False
        self._playback_controls.set_playback_stopped(False)
        self._pending_channel = channel
        self._update_playback_control_state()
        if not self._mpv_started:
            if not self._start_mpv():
                self._pending_channel = None
            return
        if self._shutdown_requested:
            return
        self._pending_channel = None
        self._loading_channel = channel
        self.load_channel_requested.emit(channel)
        self._channel_load_timer.start()
        self._status_bar.showMessage(f"Loading: {channel.name}")

    def _play_previous_channel(self) -> None:
        self._navigate_playlist(-1)

    def _play_next_channel(self) -> None:
        self._navigate_playlist(1)

    def _navigate_playlist(self, offset: int) -> None:
        if not self.channels:
            return
        selected_channel = self._loading_channel or self.current_channel
        selected_index = next(
            (
                index
                for index, channel in enumerate(self.channels)
                if selected_channel is not None
                and channel_key(channel) == channel_key(selected_channel)
            ),
            None,
        )
        if selected_index is None:
            selected_index = -1 if offset > 0 else 0
        channel = self.channels[(selected_index + offset) % len(self.channels)]
        self._play_channel(channel)

    def _toggle_playback_stopped(self) -> None:
        if self._playback_stopped:
            channel = self._loading_channel or self.current_channel
            if channel is not None:
                self._play_channel(channel)
            return
        if self.current_channel is None or not self._mpv_started:
            return
        self._playback_stopped = True
        self._playback_controls.set_playback_stopped(True)
        self._player_worker.stop_playback()

    def _set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._player_worker.set_muted(muted)

    def _on_playback_control_failed(
        self,
        operation: str,
        value: object,
        error: str,
    ) -> None:
        logger.error("%s", error)
        self._status_bar.showMessage(error, 15000)
        if operation == "stopped" and self._playback_stopped is value:
            self._playback_stopped = not self._playback_stopped
            self._playback_controls.set_playback_stopped(self._playback_stopped)
        elif operation == "muted" and self._playback_controls.is_muted is value:
            self._muted = not self._muted
            self._playback_controls.set_muted(self._muted)

    def _update_playback_control_state(self) -> None:
        self._playback_controls.set_navigation_enabled(bool(self.channels))
        self._playback_controls.set_playback_enabled(
            self._mpv_started
            and (self.current_channel is not None or self._loading_channel is not None)
        )

    def mouseMoveEvent(self, event) -> None:
        self._show_channels_for_mouse_movement()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)

    def _check_cursor_position(self) -> None:
        if not self.isVisible() or self._shutdown_requested:
            return

        cursor_position = QCursor.pos()
        if cursor_position == self._last_cursor_position:
            return
        self._last_cursor_position = cursor_position

        video_position = self._video_widget.mapFromGlobal(cursor_position)
        cursor_in_video = self._video_widget.rect().contains(video_position)
        cursor_in_controls = (
            self._playback_controls.isVisible()
            and self._playback_controls.geometry().contains(cursor_position)
        )
        if cursor_in_video:
            if self._playlist_hover_area().contains(video_position):
                self._show_channels_for_mouse_movement()
            else:
                self._hide_timer.stop()
                self._overlay.hide_overlay()
        control_hover_area = QRect(
            0,
            self._video_widget.height() - 96,
            self._playback_controls.width() + 36,
            96,
        )
        if cursor_in_video and control_hover_area.contains(video_position):
            self._playback_controls.position_overlay()
            self._playback_controls.raise_()
            self._playback_controls.show()
        elif not cursor_in_controls:
            self._playback_controls.hide()

        if cursor_in_video:
            return
        if self._overlay.isVisible() and self._overlay.geometry().contains(cursor_position):
            self._hide_timer.stop()
        else:
            self._hide_timer.stop()
            self._overlay.hide_overlay()

    def _hide_overlay_if_cursor_outside(self) -> None:
        cursor_position = QCursor.pos()
        if not self._overlay.geometry().contains(cursor_position):
            self._overlay.hide_overlay()

    def _show_channels_for_mouse_movement(self) -> None:
        if (not self.channels and not self._favourites) or self._shutdown_requested:
            return
        if not self._playlist_hover_area().contains(
            self._video_widget.mapFromGlobal(QCursor.pos())
        ):
            return
        self._overlay.show_overlay()
        self._hide_timer.start(1500)

    def _playlist_hover_area(self) -> QRect:
        self._overlay.position_overlay()
        overlay_position = self._video_widget.mapFromGlobal(
            self._overlay.geometry().topLeft()
        )
        return QRect(overlay_position, self._overlay.size())

    def resizeEvent(self, event) -> None:
        if self._overlay.isVisible():
            self._overlay.position_overlay()
        if self._audio_overlay.isVisible():
            self._audio_overlay.position_overlay()
        if self._playback_controls.isVisible():
            self._playback_controls.position_overlay()
        super().resizeEvent(event)

    def closeEvent(self, event) -> None:
        if self._player_worker.is_running and not self._shutdown_complete:
            event.ignore()
            if not self._shutdown_requested:
                self._shutdown_requested = True
                self._cursor_timer.stop()
                self._hide_timer.stop()
                self._audio_overlay.hide()
                self._playback_controls.hide()
                try:
                    if self._mpv.requires_render_widget:
                        self._mpv.detach_renderer(self._video_widget)
                except Exception:
                    logger.exception("Failed to detach the libmpv renderer during shutdown")
                self.stop_player_requested.emit()
            return
        self._save_window_preferences()
        super().closeEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "_preferences"):
            state = (
                "minimized"
                if self.isMinimized()
                else "maximized"
                if self.isMaximized()
                else "fullscreen"
                if self.isFullScreen()
                else "normal"
            )
            self._preferences.save_window_state(state)
            self._preferences.sync()

    def _on_player_stopped(self) -> None:
        self._shutdown_complete = True
        if self._shutdown_requested:
            QTimer.singleShot(0, self.close)

    def _on_channel_selected(self, item) -> None:
        channel = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(channel, Channel):
            self._play_channel(channel)
            self._overlay.hide_overlay()

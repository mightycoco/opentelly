from __future__ import annotations

import logging
import queue
import threading

from PySide6.QtCore import QObject, Qt, Signal, Slot

from iptv_player.models import AudioTrack, Channel
from iptv_player.player.mpv_process import MpvProcess

logger = logging.getLogger(__name__)


class MpvWorker(QObject):
    """Runs mpv startup and shutdown off the GUI thread."""

    ready = Signal()
    startup_failed = Signal(str)
    channel_loaded = Signal(object)
    channel_failed = Signal(str)
    audio_tracks_changed = Signal(object)
    audio_tracks_snapshot = Signal(object)
    stream_title_changed = Signal(str)
    audio_selection_failed = Signal(str)
    playback_control_failed = Signal(str, object, str)
    stopped = Signal()
    mpv_message = Signal(dict)
    _command_failed = Signal(int, str)
    _stop_complete = Signal()

    def __init__(self, process: MpvProcess) -> None:
        super().__init__()
        self._process = process
        self._pending_channel: Channel | None = None
        self._pending_request_id: int | None = None
        self._channels_by_request_id: dict[int, Channel] = {}
        self._channels_by_playlist_id: dict[int, tuple[int, Channel]] = {}
        self._state_lock = threading.Lock()
        self._lifecycle_thread: threading.Thread | None = None
        self._command_thread: threading.Thread | None = None
        self._command_queue: queue.Queue[tuple[int, list[str | int]] | None] = queue.Queue()
        self._audio_request_ids: set[int] = set()
        self._track_query_request_ids: set[int] = set()
        self._control_request_ids: dict[int, tuple[str, object, str]] = {}
        self._stream_title = ""
        self._started = False
        self._starting = False
        self._stopping = False
        self._shutdown_requested = False
        self.mpv_message.connect(self._handle_mpv_message, Qt.QueuedConnection)
        self._command_failed.connect(self._on_command_failed, Qt.QueuedConnection)
        self._stop_complete.connect(self._finish_stop, Qt.QueuedConnection)

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._started or self._starting or self._stopping

    @Slot(int)
    def start(self, hwnd: int) -> None:
        with self._state_lock:
            if self._started or self._starting or self._shutdown_requested:
                return
            self._starting = True
            self._lifecycle_thread = threading.Thread(
                target=self._start_process,
                args=(hwnd,),
                name="mpv-startup",
                daemon=True,
            )
            self._lifecycle_thread.start()

    def _start_process(self, hwnd: int) -> None:
        try:
            self._process.ipc.add_callback(self.mpv_message.emit)
            self._process.start(hwnd)
            self._process.observe_property("track-list", 1)
            self._process.observe_property("metadata", 2)
        except Exception as exc:
            logger.exception("Failed to start mpv")
            try:
                self._process.stop()
            except Exception:
                logger.exception("Failed to clean up mpv after startup failure")
            with self._state_lock:
                self._starting = False
            self.startup_failed.emit(str(exc))
        else:
            with self._state_lock:
                self._starting = False
                self._started = not self._shutdown_requested
                should_emit_ready = self._started
            if should_emit_ready:
                self._command_thread = threading.Thread(
                    target=self._send_channel_commands,
                    name="mpv-command-sender",
                    daemon=True,
                )
                self._command_thread.start()
                self.ready.emit()

    @Slot(object)
    def load_channel(self, channel: Channel) -> None:
        with self._state_lock:
            if not self._started or self._shutdown_requested:
                self.channel_failed.emit("mpv is not ready to load a channel")
                return

        try:
            request_id = self._process.reserve_request_id()
        except Exception as exc:
            logger.exception("Failed to reserve an mpv request for %s", channel.name)
            self.channel_failed.emit(f"Unable to queue {channel.name}: {exc}")
            return

        self._pending_channel = channel
        self._pending_request_id = request_id
        self._stream_title = ""
        self.stream_title_changed.emit("")
        self._channels_by_request_id[request_id] = channel
        self._track_query_request_ids.clear()
        self.audio_tracks_changed.emit([])
        self._command_queue.put(
            (request_id, ["loadfile", channel.url, "replace"])
        )

    @Slot(int)
    def select_audio_track(self, track_id: int) -> None:
        with self._state_lock:
            if not self._started or self._shutdown_requested:
                self.audio_selection_failed.emit("mpv is not ready to change audio tracks")
                return

        try:
            request_id = self._process.reserve_request_id()
        except Exception as exc:
            logger.exception("Failed to reserve an mpv request for audio track %s", track_id)
            self.audio_selection_failed.emit(f"Unable to select audio track: {exc}")
            return

        self._audio_request_ids.add(request_id)
        self._command_queue.put((request_id, ["set_property", "aid", track_id]))

    @Slot()
    def stop_playback(self) -> None:
        self._queue_control_command(["stop"], "stopped", True, "stop playback")

    @Slot(bool)
    def set_muted(self, muted: bool) -> None:
        action = "mute" if muted else "unmute"
        self._queue_control_command(
            ["set_property", "mute", muted],
            "muted",
            muted,
            action,
        )

    def _queue_control_command(
        self,
        command: list[str | int],
        operation: str,
        value: object,
        description: str,
    ) -> None:
        with self._state_lock:
            if not self._started or self._shutdown_requested:
                self.playback_control_failed.emit(
                    operation,
                    value,
                    f"mpv is not ready to {description}",
                )
                return

        try:
            request_id = self._process.reserve_request_id()
        except Exception as exc:
            logger.exception("Failed to reserve an mpv request to %s", description)
            self.playback_control_failed.emit(
                operation,
                value,
                f"Unable to {description}: {exc}",
            )
            return

        self._control_request_ids[request_id] = (operation, value, description)
        self._command_queue.put((request_id, command))

    def _send_channel_commands(self) -> None:
        while True:
            command = self._command_queue.get()
            if command is None:
                return
            request_id, mpv_command = command
            try:
                self._process.send_command(mpv_command, request_id)
            except Exception as exc:
                logger.exception("Failed to send mpv command %s", mpv_command)
                self._command_failed.emit(request_id, str(exc))

    @Slot(int, str)
    def _on_command_failed(self, request_id: int, error: str) -> None:
        control = self._control_request_ids.pop(request_id, None)
        if control is not None:
            operation, value, description = control
            self.playback_control_failed.emit(
                operation,
                value,
                f"Could not {description}: {error}",
            )
        elif request_id in self._audio_request_ids:
            self._audio_request_ids.discard(request_id)
            self.audio_selection_failed.emit(f"Could not select audio track: {error}")
        else:
            self._fail_pending_request(
                request_id,
                f"Could not send channel change to mpv: {error}",
            )

    @Slot(dict)
    def _handle_mpv_message(self, message: dict) -> None:
        request_id = message.get("request_id")
        if request_id in self._channels_by_request_id:
            channel = self._channels_by_request_id[request_id]
            error = message.get("error")
            if message.get("event") == "ipc-write-error":
                self._channels_by_request_id.pop(request_id, None)
                self._fail_pending_request(request_id, f"Could not send channel change to mpv: {error}")
                return
            if error and error != "success":
                self._channels_by_request_id.pop(request_id, None)
                self._fail_pending_request(request_id, f"mpv rejected {channel.name}: {error}")
                return
            data = message.get("data")
            if isinstance(data, dict) and isinstance(data.get("playlist_entry_id"), int):
                self._channels_by_playlist_id[data["playlist_entry_id"]] = (request_id, channel)
        elif request_id in self._audio_request_ids:
            error = message.get("error")
            if error:
                self._audio_request_ids.discard(request_id)
                if error == "success":
                    self._refresh_audio_tracks()
                else:
                    self.audio_selection_failed.emit(
                        f"mpv could not select the audio track: {error}"
                    )
        elif request_id in self._track_query_request_ids:
            self._track_query_request_ids.discard(request_id)
            if message.get("error") == "success":
                self.audio_tracks_snapshot.emit(self._parse_audio_tracks(message.get("data")))

        if request_id in self._control_request_ids:
            operation, value, description = self._control_request_ids.pop(request_id)
            error = message.get("error")
            if error and error != "success":
                self.playback_control_failed.emit(
                    operation,
                    value,
                    f"Could not {description}: {error}",
                )

        event = message.get("event")
        if event == "property-change" and message.get("name") == "track-list":
            tracks = self._parse_audio_tracks(message.get("data"))
            self.audio_tracks_changed.emit(tracks)
        elif event == "property-change" and message.get("name") == "metadata":
            title = self._parse_stream_title(message.get("data"))
            if title != self._stream_title:
                self._stream_title = title
                self.stream_title_changed.emit(title)
        elif event == "file-loaded":
            playlist_entry_id = message.get("playlist_entry_id")
            if playlist_entry_id is None:
                request_id = self._pending_request_id
                channel = self._channels_by_request_id.get(request_id)
                entry = (request_id, channel) if request_id is not None and channel is not None else None
            else:
                entry = self._channels_by_playlist_id.pop(playlist_entry_id, None)
            if entry is not None:
                self._complete_pending_request(*entry)
        elif event == "end-file":
            entry = self._channels_by_playlist_id.pop(message.get("playlist_entry_id"), None)
            if message.get("reason") == "error" and entry is not None:
                details = (
                    message.get("error")
                    or message.get("file_error")
                    or "stream could not be opened"
                )
                self._fail_pending_request(entry[0], f"Unable to play {entry[1].name}: {details}")

    @staticmethod
    def _parse_stream_title(data: object) -> str:
        if not isinstance(data, dict):
            return ""

        metadata = {
            key.casefold(): value.strip()
            for key, value in data.items()
            if isinstance(key, str) and isinstance(value, str) and value.strip()
        }
        return metadata.get("icy-title") or metadata.get("title") or ""

    @staticmethod
    def _parse_audio_tracks(data: object) -> list[AudioTrack]:
        if not isinstance(data, list):
            return []

        tracks: list[AudioTrack] = []
        for item in data:
            if not isinstance(item, dict) or item.get("type") != "audio":
                continue
            track_id = item.get("id")
            if type(track_id) is not int:
                continue
            tracks.append(
                AudioTrack(
                    track_id=track_id,
                    title=item.get("title") if isinstance(item.get("title"), str) else None,
                    language=item.get("lang") if isinstance(item.get("lang"), str) else None,
                    codec=item.get("codec") if isinstance(item.get("codec"), str) else None,
                    selected=item.get("selected") is True,
                )
            )
        return tracks

    def _complete_pending_request(self, request_id: int, channel: Channel) -> None:
        self._channels_by_request_id.pop(request_id, None)
        stale_entry_ids = [
            entry_id
            for entry_id, (entry_request_id, _) in self._channels_by_playlist_id.items()
            if entry_request_id == request_id
        ]
        for entry_id in stale_entry_ids:
            self._channels_by_playlist_id.pop(entry_id, None)
        if request_id != self._pending_request_id:
            return
        self._pending_channel = None
        self._pending_request_id = None
        self.channel_loaded.emit(channel)
        self._refresh_audio_tracks()

    def _refresh_audio_tracks(self) -> None:
        try:
            request_id = self._process.reserve_request_id()
        except Exception:
            logger.exception("Failed to reserve an mpv request for the audio track list")
            return
        self._track_query_request_ids.add(request_id)
        self._command_queue.put((request_id, ["get_property", "track-list"]))

    def _fail_pending_request(self, request_id: int, error: str) -> None:
        self._channels_by_request_id.pop(request_id, None)
        if request_id != self._pending_request_id:
            return
        self._pending_channel = None
        self._pending_request_id = None
        self.channel_failed.emit(error)

    @Slot()
    def stop(self) -> None:
        with self._state_lock:
            if self._stopping or self._shutdown_requested:
                return
            self._shutdown_requested = True
            self._stopping = True
            self._command_queue.put(None)
            startup_thread = self._lifecycle_thread
            command_thread = self._command_thread
            self._lifecycle_thread = threading.Thread(
                target=self._stop_process,
                args=(startup_thread, command_thread),
                name="mpv-shutdown",
                daemon=True,
            )
            self._lifecycle_thread.start()

    def _stop_process(
        self,
        startup_thread: threading.Thread | None,
        command_thread: threading.Thread | None,
    ) -> None:
        if startup_thread is not None and startup_thread is not threading.current_thread():
            startup_thread.join()
        try:
            self._process.stop()
        except Exception:
            logger.exception("Failed to stop mpv cleanly")
        finally:
            if command_thread is not None and command_thread is not threading.current_thread():
                command_thread.join(timeout=2)
            self._stop_complete.emit()

    @Slot()
    def _finish_stop(self) -> None:
        self._channels_by_request_id.clear()
        self._channels_by_playlist_id.clear()
        self._audio_request_ids.clear()
        self._track_query_request_ids.clear()
        self._control_request_ids.clear()
        self.audio_tracks_changed.emit([])
        self.audio_tracks_snapshot.emit([])
        self._pending_channel = None
        self._pending_request_id = None
        with self._state_lock:
            self._started = False
            self._starting = False
            self._stopping = False
        self.stopped.emit()

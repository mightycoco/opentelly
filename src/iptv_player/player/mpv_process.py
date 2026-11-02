from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections import deque
from typing import Any

from iptv_player.models import Channel
from iptv_player.player.backend import BackendEvent, MpvEventCallback
from iptv_player.player.mpv_ipc import MpvIpcClient
from iptv_player.settings import MpvSettings

logger = logging.getLogger(__name__)


class MpvProcess:
    """Owns the mpv process and its IPC channel."""

    def __init__(self, settings: MpvSettings | None = None) -> None:
        self.settings = settings or MpvSettings()
        self.process: subprocess.Popen[Any] | None = None
        self.ipc = MpvIpcClient(self.settings.ipc_pipe_name)
        self._lock = threading.Lock()
        self._started = False
        self._stderr_lines: deque[str] = deque(maxlen=50)
        self._stderr_thread: threading.Thread | None = None

    def start(self, hwnd: int) -> None:
        with self._lock:
            if self._started and self.process is not None and self.process.poll() is None:
                return
            self._stderr_lines.clear()
            try:
                command = self.settings.build_command(hwnd)
                command[0] = self.settings.resolve_executable()
                self.process = subprocess.Popen(
                    command,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self._stderr_thread = threading.Thread(target=self._capture_stderr, daemon=True)
                self._stderr_thread.start()
                self.ipc.connect(timeout=10)
                self._started = True
            except Exception as exc:
                self.ipc.close()
                self._terminate_process()
                details = "\n".join(self._stderr_lines).strip()
                if details:
                    raise RuntimeError(f"Unable to connect to mpv IPC: {exc}\nmpv output:\n{details}") from exc
                raise RuntimeError(f"Unable to connect to mpv IPC: {exc}") from exc

    def _capture_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr_lines.append(line.rstrip())
            logger.debug("mpv: %s", line.rstrip())

    def reserve_request_id(self) -> int:
        return self.ipc.reserve_request_id()

    def add_callback(self, callback: MpvEventCallback) -> None:
        def dispatch(message: dict[str, Any]) -> None:
            event = BackendEvent.from_ipc_message(message)
            if event is not None:
                callback(event)

        self.ipc.add_callback(dispatch)

    def send_command(self, command: list[str | int], request_id: int | None = None) -> int:
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("mpv is not running")
        return self.ipc.send_command(command, request_id)

    def load_channel(self, channel: Channel, request_id: int | None = None) -> int:
        return self.send_command(["loadfile", channel.url, "replace"], request_id)

    def select_audio_track(self, track_id: int, request_id: int) -> int:
        return self.send_command(["set_property", "aid", track_id], request_id)

    def stop_playback(self, request_id: int) -> int:
        return self.send_command(["stop"], request_id)

    def set_muted(self, muted: bool, request_id: int) -> int:
        return self.send_command(["set_property", "mute", muted], request_id)

    def get_audio_tracks(self, request_id: int) -> int:
        return self.send_command(["get_property", "track-list"], request_id)

    def observe_property(self, property_name: str, observer_id: int) -> int:
        return self.ipc.observe_property(property_name, observer_id)

    def stop(self) -> None:
        self.ipc.stop_reading()
        self._terminate_process()
        self.ipc.close()
        self._started = False

    def _terminate_process(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if self._stderr_thread is not None and self._stderr_thread is not threading.current_thread():
            self._stderr_thread.join(timeout=1)
        self._started = False

    def __enter__(self) -> "MpvProcess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

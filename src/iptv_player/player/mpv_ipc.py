from __future__ import annotations

import json
import logging
import threading
import time
from itertools import count
from typing import Any, Callable

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional Windows dependency
    import pywintypes
    import win32file
    import win32pipe
except ImportError:  # pragma: no cover - tests may run without pywin32
    pywintypes = None
    win32file = None
    win32pipe = None


class MpvIpcClient:
    """Minimal Windows named-pipe JSON IPC client for mpv."""

    def __init__(self, pipe_name: str) -> None:
        self.pipe_name = pipe_name
        self.handle = None
        self._monitor_handle = None
        self._buffer = ""
        self._monitor_thread: threading.Thread | None = None
        self._handle_lock = threading.Lock()
        self._command_handles: set[Any] = set()
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._request_ids = count(1)

    def add_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._callbacks.append(callback)

    def reserve_request_id(self) -> int:
        return next(self._request_ids)

    def connect(self, timeout: float = 10.0) -> None:
        self._buffer = ""
        self._thread = None
        self.handle = self._open_pipe(timeout)

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def observe_property(self, property_name: str, observer_id: int) -> int:
        if win32file is None or win32pipe is None:
            raise RuntimeError("pywin32 is required for Windows named-pipe IPC support")
        with self._handle_lock:
            if self._monitor_handle is not None:
                raise RuntimeError("An mpv property monitor is already connected")

        handle = self._open_pipe(timeout=10)
        try:
            win32pipe.SetNamedPipeHandleState(
                handle,
                win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_NOWAIT,
                None,
                None,
            )
            request_id = self.reserve_request_id()
            payload = json.dumps(
                {
                    "command": ["observe_property", observer_id, property_name],
                    "request_id": request_id,
                },
                ensure_ascii=False,
            ) + "\n"
            win32file.WriteFile(handle, payload.encode("utf-8"))
            with self._handle_lock:
                if self._stop_event is not None and self._stop_event.is_set():
                    raise RuntimeError("IPC client is shutting down")
                self._monitor_handle = handle
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                args=(handle,),
                name="mpv-property-monitor",
                daemon=True,
            )
            self._monitor_thread.start()
            return request_id
        except Exception:
            self._close_handle(handle)
            raise

    def send_command(
        self,
        command: list[str | int],
        request_id: int | None = None,
    ) -> int:
        if win32file is None or win32pipe is None:
            raise RuntimeError("pywin32 is required for Windows named-pipe IPC support")
        if request_id is None:
            request_id = self.reserve_request_id()
        payload = json.dumps(
            {"command": command, "request_id": request_id},
            ensure_ascii=False,
        ) + "\n"
        data = payload.encode("utf-8")
        handle = self._open_pipe(timeout=10)
        with self._handle_lock:
            if self._stop_event is not None and self._stop_event.is_set():
                win32file.CloseHandle(handle)
                raise RuntimeError("IPC client is shutting down")
            self._command_handles.add(handle)

        try:
            win32pipe.SetNamedPipeHandleState(
                handle,
                win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_NOWAIT,
                None,
                None,
            )
            try:
                win32file.WriteFile(handle, data)
            except Exception as exc:  # pragma: no cover - runtime-specific error path
                raise RuntimeError(f"Failed to write command to mpv IPC: {exc}") from exc

            response_buffer = ""
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if self._stop_event is not None and self._stop_event.is_set():
                    raise RuntimeError("IPC client is shutting down")
                try:
                    _, raw_data = win32file.ReadFile(handle, 65536)
                except Exception as exc:
                    error_code = getattr(exc, "winerror", None)
                    if error_code is None and getattr(exc, "args", None):
                        error_code = exc.args[0]
                    if (
                        error_code == 232
                        and (self._stop_event is None or not self._stop_event.is_set())
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                        continue
                    raise RuntimeError(f"Failed to read mpv command response: {exc}") from exc
                if not raw_data:
                    raise RuntimeError("mpv closed the command IPC connection")

                response_buffer += raw_data.decode("utf-8", errors="replace")
                while "\n" in response_buffer:
                    line, response_buffer = response_buffer.split("\n", 1)
                    if not line.strip():
                        continue
                    try:
                        response = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Ignoring non-JSON IPC response: %s", line)
                        continue
                    self._dispatch(response)
                    if response.get("request_id") == request_id:
                        return request_id

            raise TimeoutError(f"mpv did not respond to IPC request {request_id}")
        finally:
            with self._handle_lock:
                self._command_handles.discard(handle)
            self._close_handle(handle)

    def _open_pipe(self, timeout: float):
        if win32file is None or win32pipe is None:
            raise RuntimeError("pywin32 is required for Windows named-pipe IPC support")

        pipe_path = rf"\\.\pipe\{self.pipe_name}"
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"mpv IPC pipe did not become available: {pipe_path}")
            if self._stop_event is not None and self._stop_event.is_set():
                raise RuntimeError("IPC client is shutting down")

            try:
                win32pipe.WaitNamedPipe(pipe_path, max(1, int(remaining * 1000)))
                return win32file.CreateFile(
                    pipe_path,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
            except Exception as exc:
                error_code = getattr(exc, "winerror", None)
                if error_code is None and getattr(exc, "args", None):
                    error_code = exc.args[0]
                if error_code not in (2, 121, 231):
                    raise
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))

    def _read_loop(self) -> None:
        while self._stop_event is not None and not self._stop_event.is_set():
            handle = self.handle
            if handle is None:
                return
            try:
                _, raw_data = win32file.ReadFile(handle, 65536)
            except Exception as exc:  # pragma: no cover - runtime-specific error path
                if self._stop_event is None or not self._stop_event.is_set():
                    logger.warning("IPC pipe read failed: %s", exc)
                self._close_read_handle(handle)
                return

            if not raw_data:
                logger.warning("IPC pipe closed by mpv")
                self._close_read_handle(handle)
                return

            chunk = raw_data.decode("utf-8", errors="replace")
            self._buffer += chunk
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Ignoring non-JSON IPC payload: %s", line)
                    continue
                self._dispatch(payload)

    def _monitor_loop(self, handle) -> None:
        buffer = ""
        while self._stop_event is not None and not self._stop_event.is_set():
            try:
                _, raw_data = win32file.ReadFile(handle, 65536)
            except Exception as exc:  # pragma: no cover - runtime-specific error path
                error_code = getattr(exc, "winerror", None)
                if error_code is None and getattr(exc, "args", None):
                    error_code = exc.args[0]
                if error_code == 232 and not self._stop_event.is_set():
                    time.sleep(0.01)
                    continue
                if not self._stop_event.is_set():
                    logger.warning("IPC property monitor read failed: %s", exc)
                self._close_monitor_handle(handle)
                return

            if not raw_data:
                logger.warning("mpv closed the property monitor pipe")
                self._close_monitor_handle(handle)
                return

            buffer += raw_data.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Ignoring non-JSON IPC payload: %s", line)
                    continue
                self._dispatch(payload)

    def _dispatch(self, payload: dict[str, Any]) -> None:
        for callback in list(self._callbacks):
            try:
                callback(payload)
            except Exception:
                logger.exception("mpv IPC callback failed")

    def close(self) -> None:
        self.stop_reading()
        with self._handle_lock:
            handle = self.handle
            self.handle = None
            monitor_handle = self._monitor_handle
            self._monitor_handle = None
            command_handles = list(self._command_handles)
            self._command_handles.clear()
        if handle is not None:
            self._close_handle(handle)
        if monitor_handle is not None:
            self._close_handle(monitor_handle)
        for command_handle in command_handles:
            self._close_handle(command_handle)
        current_thread = threading.current_thread()
        for thread in (self._thread, self._monitor_thread):
            if thread is not None and thread is not current_thread:
                thread.join(timeout=1)

    def _close_read_handle(self, handle) -> None:
        with self._handle_lock:
            if self.handle is handle:
                self.handle = None
        self._close_handle(handle)

    def _close_monitor_handle(self, handle) -> None:
        with self._handle_lock:
            if self._monitor_handle is handle:
                self._monitor_handle = None
        self._close_handle(handle)

    @staticmethod
    def _close_handle(handle) -> None:
        try:
            win32file.CloseHandle(handle)
        except Exception:
            logger.debug("mpv IPC pipe was already closed")

    def stop_reading(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

    def __enter__(self) -> "MpvIpcClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

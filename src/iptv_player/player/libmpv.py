from __future__ import annotations

import ctypes
import ctypes.util
import itertools
import logging
import os
from pathlib import Path
import threading
from typing import Any

from PySide6.QtGui import QOpenGLContext

from iptv_player.models import Channel
from iptv_player.player.backend import BackendEvent, MpvEventCallback
from iptv_player.settings import MpvSettings

logger = logging.getLogger(__name__)

_MPV_FORMAT_STRING = 1
_MPV_FORMAT_FLAG = 3
_MPV_FORMAT_INT64 = 4
_MPV_FORMAT_NODE = 6

_MPV_EVENT_SHUTDOWN = 1
_MPV_EVENT_GET_PROPERTY_REPLY = 3
_MPV_EVENT_SET_PROPERTY_REPLY = 4
_MPV_EVENT_COMMAND_REPLY = 5
_MPV_EVENT_END_FILE = 7
_MPV_EVENT_FILE_LOADED = 8
_MPV_EVENT_PROPERTY_CHANGE = 22

_MPV_RENDER_PARAM_INVALID = 0
_MPV_RENDER_PARAM_API_TYPE = 1
_MPV_RENDER_PARAM_OPENGL_INIT_PARAMS = 2
_MPV_RENDER_PARAM_OPENGL_FBO = 3
_MPV_RENDER_PARAM_FLIP_Y = 4
_MPV_RENDER_API_OPENGL = b"opengl"


class _MpvNodeUnion(ctypes.Union):
    _fields_ = [
        ("string", ctypes.c_char_p),
        ("flag", ctypes.c_int),
        ("int64", ctypes.c_int64),
        ("double", ctypes.c_double),
        ("list", ctypes.c_void_p),
    ]


class _MpvNode(ctypes.Structure):
    _fields_ = [("u", _MpvNodeUnion), ("format", ctypes.c_int)]


class _MpvNodeList(ctypes.Structure):
    _fields_ = [
        ("num", ctypes.c_int),
        ("values", ctypes.POINTER(_MpvNode)),
        ("keys", ctypes.POINTER(ctypes.c_char_p)),
    ]


class _MpvEvent(ctypes.Structure):
    _fields_ = [
        ("event_id", ctypes.c_int),
        ("error", ctypes.c_int),
        ("reply_userdata", ctypes.c_uint64),
        ("data", ctypes.c_void_p),
    ]


class _MpvEventProperty(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("format", ctypes.c_int),
        ("data", ctypes.c_void_p),
    ]


class _MpvEventEndFile(ctypes.Structure):
    _fields_ = [
        ("reason", ctypes.c_int),
        ("error", ctypes.c_int),
        ("playlist_entry_id", ctypes.c_int),
        ("playlist_insert_id", ctypes.c_int),
        ("playlist_insert_num_entries", ctypes.c_int),
    ]


class _MpvRenderParam(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("data", ctypes.c_void_p)]


class _MpvOpenGLInitParams(ctypes.Structure):
    pass


_GetProcAddress = ctypes.CFUNCTYPE(
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_char_p,
)
_MpvOpenGLInitParams._fields_ = [
    ("get_proc_address", _GetProcAddress),
    ("get_proc_address_ctx", ctypes.c_void_p),
]


class _MpvOpenGLFbo(ctypes.Structure):
    _fields_ = [
        ("fbo", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("internal_format", ctypes.c_int),
    ]


class LibMpvBackend:
    """libmpv backend with rendering delegated to a Qt OpenGL widget."""

    requires_render_widget = True

    def __init__(
        self,
        settings: MpvSettings | None = None,
        library_path: str | None = None,
        library: Any | None = None,
    ) -> None:
        self.settings = settings or MpvSettings()
        self.library_path = library_path or os.environ.get("MPV_LIBRARY")
        self._library = library
        self._handle = ctypes.c_void_p()
        self._render_context = ctypes.c_void_p()
        self._callbacks: list[MpvEventCallback] = []
        self._request_ids = itertools.count(1)
        self._request_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._event_thread: threading.Thread | None = None
        self._get_proc_callback: _GetProcAddress | None = None
        self._render_update_callback: Any | None = None
        self._render_widget: Any | None = None
        self._render_lock = threading.Lock()
        self._initialized = False

    def add_callback(self, callback: MpvEventCallback) -> None:
        self._callbacks.append(callback)

    def start(self, hwnd: int | None = None) -> None:
        if self._initialized:
            return
        if self.settings.rtsp_transport not in {
            "udp",
            "tcp",
            "udp_multicast",
            "http",
            "lavf",
        }:
            raise ValueError(f"Unsupported RTSP transport: {self.settings.rtsp_transport}")
        self._load_library()
        self._configure_functions()
        handle = self._library.mpv_create()
        if not handle:
            raise RuntimeError("libmpv could not create a player handle")
        self._handle = ctypes.c_void_p(handle)
        try:
            options = {
                "config": "no",
                "idle": "yes",
                "keep-open": "yes",
                "vo": "libmpv",
                "audio-display": "no",
                "rtsp-transport": self.settings.rtsp_transport,
                "volume": str(self.settings.volume),
            }
            for name, value in options.items():
                self._check(
                    self._library.mpv_set_option_string(
                        self._handle,
                        name.encode("utf-8"),
                        value.encode("utf-8"),
                    ),
                    f"set mpv option {name}",
                )
            for argument in self.settings.extra_args:
                name, separator, value = argument.lstrip("-").partition("=")
                if not separator or not name:
                    raise ValueError(f"Expected mpv option in name=value form: {argument}")
                self._check(
                    self._library.mpv_set_option_string(
                        self._handle,
                        name.encode("utf-8"),
                        value.encode("utf-8"),
                    ),
                    f"set mpv option {name}",
                )
            self._check(self._library.mpv_initialize(self._handle), "initialize libmpv")
            self._initialized = True
            self._stop_event.clear()
            self._event_thread = threading.Thread(
                target=self._event_loop,
                name="libmpv-events",
                daemon=True,
            )
            self._event_thread.start()
        except Exception:
            self._library.mpv_terminate_destroy(self._handle)
            self._handle = ctypes.c_void_p()
            raise

    def _load_library(self) -> None:
        if self._library is not None:
            return
        candidates = [self.library_path] if self.library_path else []
        if os.name == "nt":
            candidates.extend(("mpv-2.dll", "libmpv-2.dll"))
            try:
                executable = Path(self.settings.resolve_executable())
            except FileNotFoundError:
                executable = None
            if executable is not None:
                candidates.extend(
                    str(executable.with_name(name))
                    for name in ("mpv-2.dll", "libmpv-2.dll")
                )
        else:
            found = ctypes.util.find_library("mpv")
            if found:
                candidates.append(found)
        load = ctypes.WinDLL if os.name == "nt" else ctypes.CDLL
        failures: list[str] = []
        for candidate in candidates:
            if not candidate:
                continue
            try:
                self._library = load(candidate)
                self.library_path = candidate
                return
            except OSError as exc:
                failures.append(f"{candidate}: {exc}")
        details = "; ".join(failures)
        if not details:
            details = "no libmpv library was found on the system"
        raise RuntimeError(
            "Unable to load libmpv. Install the mpv shared library or set "
            f"MPV_LIBRARY to its full path ({details})"
        )

    def _configure_functions(self) -> None:
        signatures = {
            "mpv_create": (ctypes.c_void_p, []),
            "mpv_set_option_string": (
                ctypes.c_int,
                [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p],
            ),
            "mpv_initialize": (ctypes.c_int, [ctypes.c_void_p]),
            "mpv_terminate_destroy": (None, [ctypes.c_void_p]),
            "mpv_error_string": (ctypes.c_char_p, [ctypes.c_int]),
            "mpv_command_async": (
                ctypes.c_int,
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_char_p)],
            ),
            "mpv_set_property_async": (
                ctypes.c_int,
                [
                    ctypes.c_void_p,
                    ctypes.c_uint64,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_void_p,
                ],
            ),
            "mpv_get_property_async": (
                ctypes.c_int,
                [
                    ctypes.c_void_p,
                    ctypes.c_uint64,
                    ctypes.c_char_p,
                    ctypes.c_int,
                ],
            ),
            "mpv_observe_property": (
                ctypes.c_int,
                [
                    ctypes.c_void_p,
                    ctypes.c_uint64,
                    ctypes.c_char_p,
                    ctypes.c_int,
                ],
            ),
            "mpv_wait_event": (
                ctypes.POINTER(_MpvEvent),
                [ctypes.c_void_p, ctypes.c_double],
            ),
            "mpv_render_context_create": (
                ctypes.c_int,
                [
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.c_void_p,
                    ctypes.POINTER(_MpvRenderParam),
                ],
            ),
            "mpv_render_context_set_update_callback": (
                None,
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
            ),
            "mpv_render_context_render": (
                ctypes.c_int,
                [ctypes.c_void_p, ctypes.POINTER(_MpvRenderParam)],
            ),
            "mpv_render_context_free": (None, [ctypes.c_void_p]),
        }
        for name, (restype, argtypes) in signatures.items():
            function = getattr(self._library, name)
            try:
                function.restype = restype
                function.argtypes = argtypes
            except (AttributeError, TypeError):
                if not callable(function):
                    raise TypeError(f"libmpv API symbol {name} is not callable")

    def reserve_request_id(self) -> int:
        with self._request_lock:
            return next(self._request_ids)

    def observe_property(self, property_name: str, observer_id: int) -> int:
        self._require_started()
        return self._check(
            self._library.mpv_observe_property(
                self._handle,
                observer_id,
                property_name.encode("utf-8"),
                _MPV_FORMAT_NODE,
            ),
            f"observe mpv property {property_name}",
        )

    def load_channel(self, channel: Channel, request_id: int) -> int:
        return self._command(request_id, "loadfile", channel.url, "replace")

    def select_audio_track(self, track_id: int, request_id: int) -> int:
        value = ctypes.c_int64(track_id)
        return self._check(
            self._library.mpv_set_property_async(
                self._handle,
                request_id,
                b"aid",
                _MPV_FORMAT_INT64,
                ctypes.cast(ctypes.byref(value), ctypes.c_void_p),
            ),
            "select audio track",
        )

    def stop_playback(self, request_id: int) -> int:
        return self._command(request_id, "stop")

    def set_muted(self, muted: bool, request_id: int) -> int:
        value = ctypes.c_int(int(muted))
        return self._check(
            self._library.mpv_set_property_async(
                self._handle,
                request_id,
                b"mute",
                _MPV_FORMAT_FLAG,
                ctypes.cast(ctypes.byref(value), ctypes.c_void_p),
            ),
            "change mute state",
        )

    def get_audio_tracks(self, request_id: int) -> int:
        return self._check(
            self._library.mpv_get_property_async(
                self._handle,
                request_id,
                b"track-list",
                _MPV_FORMAT_NODE,
            ),
            "get audio tracks",
        )

    def _command(self, request_id: int, *arguments: str) -> int:
        self._require_started()
        encoded = [argument.encode("utf-8") for argument in arguments]
        command = (ctypes.c_char_p * (len(encoded) + 1))(*encoded, None)
        return self._check(
            self._library.mpv_command_async(
                self._handle,
                request_id,
                command,
            ),
            f"execute mpv command {arguments[0]}",
        )

    def _event_loop(self) -> None:
        while not self._stop_event.is_set():
            event_pointer = self._library.mpv_wait_event(self._handle, 0.1)
            if not event_pointer:
                continue
            event = event_pointer.contents
            try:
                normalized = self._normalize_event(event)
                if normalized is not None:
                    for callback in tuple(self._callbacks):
                        callback(normalized)
            except Exception:
                logger.exception("Could not normalize a libmpv event")
            if event.event_id == _MPV_EVENT_SHUTDOWN:
                return

    def _normalize_event(self, event: _MpvEvent) -> BackendEvent | None:
        request_id = int(event.reply_userdata) or None
        if event.event_id in (
            _MPV_EVENT_COMMAND_REPLY,
            _MPV_EVENT_SET_PROPERTY_REPLY,
            _MPV_EVENT_GET_PROPERTY_REPLY,
        ):
            error = "success" if event.error >= 0 else self._error_string(event.error)
            data: object = None
            if event.event_id == _MPV_EVENT_COMMAND_REPLY and event.data:
                data = self._read_node(ctypes.cast(event.data, ctypes.POINTER(_MpvNode)).contents)
            elif event.event_id == _MPV_EVENT_GET_PROPERTY_REPLY and event.data:
                prop = ctypes.cast(
                    event.data,
                    ctypes.POINTER(_MpvEventProperty),
                ).contents
                if prop.data and prop.format == _MPV_FORMAT_NODE:
                    data = self._read_node(
                        ctypes.cast(prop.data, ctypes.POINTER(_MpvNode)).contents
                    )
            return BackendEvent(
                kind="command-reply",
                request_id=request_id,
                error=error,
                data=data,
            )
        if event.event_id == _MPV_EVENT_PROPERTY_CHANGE and event.data:
            prop = ctypes.cast(
                event.data,
                ctypes.POINTER(_MpvEventProperty),
            ).contents
            property_name = prop.name.decode("utf-8", errors="replace") if prop.name else None
            data = None
            if prop.data and prop.format == _MPV_FORMAT_NODE:
                data = self._read_node(
                    ctypes.cast(prop.data, ctypes.POINTER(_MpvNode)).contents
                )
            return BackendEvent(
                kind="property-change",
                request_id=request_id,
                data=data,
                property_name=property_name,
            )
        if event.event_id == _MPV_EVENT_FILE_LOADED:
            return BackendEvent(kind="file-loaded")
        if event.event_id == _MPV_EVENT_END_FILE and event.data:
            details = ctypes.cast(
                event.data,
                ctypes.POINTER(_MpvEventEndFile),
            ).contents
            reasons = {0: "eof", 2: "stop", 3: "quit", 4: "error", 5: "redirect"}
            reason = reasons.get(details.reason, "unknown")
            error = (
                self._error_string(details.error)
                if details.reason == 4 and details.error < 0
                else None
            )
            return BackendEvent(
                kind="end-file",
                playlist_entry_id=details.playlist_entry_id or None,
                reason=reason,
                error=error,
                file_error=error,
            )
        return None

    @classmethod
    def _read_node(cls, node: _MpvNode, depth: int = 0) -> object:
        if depth > 16:
            raise ValueError("libmpv node nesting exceeds the supported depth")
        if node.format == 0:
            return None
        if node.format in (_MPV_FORMAT_STRING, 2):
            return node.u.string.decode("utf-8", errors="replace") if node.u.string else ""
        if node.format == _MPV_FORMAT_FLAG:
            return bool(node.u.flag)
        if node.format == _MPV_FORMAT_INT64:
            return int(node.u.int64)
        if node.format == 5:
            return float(node.u.double)
        if node.format not in (7, 8):
            return None
        if not node.u.list:
            return [] if node.format == 7 else {}
        values = ctypes.cast(
            node.u.list,
            ctypes.POINTER(_MpvNodeList),
        ).contents
        if values.num < 0 or values.num > 10000:
            raise ValueError(f"Invalid libmpv node list size: {values.num}")
        if node.format == 7:
            return [
                cls._read_node(values.values[index], depth + 1)
                for index in range(values.num)
            ]
        result: dict[str, object] = {}
        for index in range(values.num):
            raw_key = values.keys[index] if values.keys else None
            key = raw_key.decode("utf-8", errors="replace") if raw_key else ""
            result[key] = cls._read_node(values.values[index], depth + 1)
        return result

    def attach_renderer(self, widget: Any) -> None:
        self._require_started()
        if self._render_context:
            raise RuntimeError("The libmpv render context is already attached")
        widget.makeCurrent()
        try:
            get_proc_address = _GetProcAddress(self._get_gl_proc_address)
            api_type = ctypes.create_string_buffer(_MPV_RENDER_API_OPENGL)
            init_params = _MpvOpenGLInitParams(get_proc_address, None)
            parameters = (_MpvRenderParam * 3)(
                _MpvRenderParam(
                    _MPV_RENDER_PARAM_API_TYPE,
                    ctypes.cast(api_type, ctypes.c_void_p),
                ),
                _MpvRenderParam(
                    _MPV_RENDER_PARAM_OPENGL_INIT_PARAMS,
                    ctypes.cast(ctypes.pointer(init_params), ctypes.c_void_p),
                ),
                _MpvRenderParam(_MPV_RENDER_PARAM_INVALID, None),
            )
            self._check(
                self._library.mpv_render_context_create(
                    ctypes.byref(self._render_context),
                    self._handle,
                    parameters,
                ),
                "create libmpv OpenGL render context",
            )
            update_callback_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p)

            def request_update(_context: int) -> None:
                widget.request_render_update.emit()

            update_callback = update_callback_type(request_update)
            self._render_update_callback = update_callback
            self._get_proc_callback = get_proc_address
            self._render_widget = widget
            self._library.mpv_render_context_set_update_callback(
                self._render_context,
                ctypes.cast(update_callback, ctypes.c_void_p),
                None,
            )
        except Exception:
            if self._render_context:
                self._library.mpv_render_context_free(self._render_context)
                self._render_context = ctypes.c_void_p()
            raise
        finally:
            widget.doneCurrent()

    @staticmethod
    def _get_gl_proc_address(_context: int, name: bytes) -> int | None:
        context = QOpenGLContext.currentContext()
        if context is None:
            return None
        function = context.getProcAddress(name.decode("ascii"))
        if not function:
            return None
        try:
            return ctypes.cast(function, ctypes.c_void_p).value
        except (TypeError, ctypes.ArgumentError):
            try:
                return int(function)
            except (TypeError, ValueError):
                logger.error("Qt returned an unsupported OpenGL function pointer for %s", name)
                return None

    def render(self, framebuffer: int, width: int, height: int) -> None:
        if not self._render_context:
            return
        with self._render_lock:
            fbo = _MpvOpenGLFbo(framebuffer, max(width, 1), max(height, 1), 0)
            flip_y = ctypes.c_int(1)
            parameters = (_MpvRenderParam * 3)(
                _MpvRenderParam(
                    _MPV_RENDER_PARAM_OPENGL_FBO,
                    ctypes.cast(ctypes.pointer(fbo), ctypes.c_void_p),
                ),
                _MpvRenderParam(
                    _MPV_RENDER_PARAM_FLIP_Y,
                    ctypes.cast(ctypes.pointer(flip_y), ctypes.c_void_p),
                ),
                _MpvRenderParam(_MPV_RENDER_PARAM_INVALID, None),
            )
            result = self._library.mpv_render_context_render(
                self._render_context,
                parameters,
            )
            if result < 0:
                logger.error("libmpv rendering failed: %s", self._error_string(result))

    def detach_renderer(self, widget: Any) -> None:
        if not self._render_context:
            return
        with self._render_lock:
            widget.makeCurrent()
            try:
                self._library.mpv_render_context_set_update_callback(
                    self._render_context,
                    None,
                    None,
                )
                self._library.mpv_render_context_free(self._render_context)
                self._render_context = ctypes.c_void_p()
                self._render_update_callback = None
                self._get_proc_callback = None
                self._render_widget = None
            finally:
                widget.doneCurrent()

    def stop(self) -> None:
        if not self._initialized:
            return
        self._stop_event.set()
        event_thread = self._event_thread
        if event_thread is not None and event_thread is not threading.current_thread():
            event_thread.join(timeout=3)
            if event_thread.is_alive():
                logger.warning("libmpv event thread did not stop before timeout")
        self._library.mpv_terminate_destroy(self._handle)
        self._handle = ctypes.c_void_p()
        self._initialized = False
        self._event_thread = None

    def _require_started(self) -> None:
        if not self._initialized or not self._handle:
            raise RuntimeError("libmpv is not initialized")

    def _check(self, result: int, action: str) -> int:
        if result < 0:
            raise RuntimeError(f"Could not {action}: {self._error_string(result)}")
        return result

    def _error_string(self, error: int) -> str:
        try:
            message = self._library.mpv_error_string(error)
        except Exception:
            return f"libmpv error {error}"
        return message.decode("utf-8", errors="replace") if message else f"libmpv error {error}"

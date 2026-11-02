import ctypes
import time

import pytest

from iptv_player.models import Channel
from iptv_player.player.factory import create_mpv_backend
from iptv_player.player.libmpv import (
    LibMpvBackend,
    _MPV_EVENT_END_FILE,
    _MpvEvent,
    _MpvEventEndFile,
)
from iptv_player.settings import MpvSettings


class FakeFunction:
    def __init__(self, function) -> None:
        self._function = function
        self.restype = None
        self.argtypes = None

    def __call__(self, *args):
        return self._function(*args)


class FakeLibrary:
    def __init__(self) -> None:
        self.options = []
        self.commands = []
        self.properties = []
        self.destroyed = False
        self.render_context = None
        self.update_callback = None
        self.render_calls = []
        self.mpv_create = FakeFunction(lambda: 1234)
        self.mpv_set_option_string = FakeFunction(self._set_option)
        self.mpv_initialize = FakeFunction(lambda handle: 0)
        self.mpv_terminate_destroy = FakeFunction(self._destroy)
        self.mpv_error_string = FakeFunction(lambda error: b"mock error")
        self.mpv_command_async = FakeFunction(self._command)
        self.mpv_set_property_async = FakeFunction(self._set_property)
        self.mpv_get_property_async = FakeFunction(self._get_property)
        self.mpv_observe_property = FakeFunction(self._observe)
        self.mpv_wait_event = FakeFunction(lambda handle, timeout: None)
        self.mpv_render_context_create = FakeFunction(self._create_render_context)
        self.mpv_render_context_set_update_callback = FakeFunction(self._set_update_callback)
        self.mpv_render_context_render = FakeFunction(self._render)
        self.mpv_render_context_free = FakeFunction(self._free_render_context)

    def _set_option(self, handle, name, value) -> int:
        self.options.append((name.decode(), value.decode()))
        return 0

    def _destroy(self, handle) -> None:
        self.destroyed = True

    def _command(self, handle, request_id, arguments) -> int:
        self.commands.append(
            (request_id, [value.decode() for value in arguments if value is not None])
        )
        return 0

    def _set_property(self, handle, request_id, name, value_format, value) -> int:
        value_type = ctypes.c_int if value_format == 3 else ctypes.c_int64
        self.properties.append(
            (
                request_id,
                name.decode(),
                value_format,
                ctypes.cast(value, ctypes.POINTER(value_type)).contents.value,
            )
        )
        return 0

    def _get_property(self, handle, request_id, name, value_format) -> int:
        self.properties.append((request_id, name.decode(), value_format, None))
        return 0

    def _observe(self, handle, observer_id, name, value_format) -> int:
        self.properties.append((observer_id, name.decode(), value_format, "observe"))
        return 0

    def _create_render_context(self, output, handle, params) -> int:
        self.render_context = 5678
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = self.render_context
        return 0

    def _set_update_callback(self, context, callback, data) -> None:
        self.update_callback = callback

    def _render(self, context, params) -> int:
        self.render_calls.append(context.value if isinstance(context, ctypes.c_void_p) else context)
        return 0

    def _free_render_context(self, context) -> None:
        self.render_context = None


def test_libmpv_backend_adapts_playback_operations_and_initializes_render_mode() -> None:
    library = FakeLibrary()
    backend = LibMpvBackend(library=library)
    backend.start()
    backend.observe_property("track-list", 1)
    backend.observe_property("metadata", 2)
    backend.load_channel(
        Channel(name="News", url="rtsp://example.com/news"),
        request_id=10,
    )
    backend.select_audio_track(3, request_id=11)
    backend.set_muted(True, request_id=12)
    backend.get_audio_tracks(request_id=13)
    backend.stop_playback(request_id=14)
    backend.stop()

    assert backend.requires_render_widget
    assert ("vo", "libmpv") in library.options
    assert library.commands == [
        (10, ["loadfile", "rtsp://example.com/news", "replace"]),
        (14, ["stop"]),
    ]
    assert [entry[:3] for entry in library.properties] == [
        (1, "track-list", 6),
        (2, "metadata", 6),
        (11, "aid", 4),
        (12, "mute", 3),
        (13, "track-list", 6),
    ]
    assert library.destroyed


def test_libmpv_backend_reports_missing_library_clearly(monkeypatch) -> None:
    backend = LibMpvBackend()
    monkeypatch.setattr("iptv_player.player.libmpv.ctypes.util.find_library", lambda name: None)
    monkeypatch.setattr("iptv_player.player.libmpv.os.name", "posix")

    with pytest.raises(RuntimeError, match="Install the mpv shared library"):
        backend.start()


def test_windows_loader_discovers_library_in_winget_package(monkeypatch, tmp_path) -> None:
    library_path = (
        tmp_path
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "shinchiro.mpv_test"
        / "mpv-2.dll"
    )
    library_path.parent.mkdir(parents=True)
    library_path.touch()
    library = FakeLibrary()
    monkeypatch.setattr("iptv_player.player.libmpv.os.name", "nt")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def load(candidate: str):
        if candidate == str(library_path):
            return library
        raise OSError(f"not found: {candidate}")

    monkeypatch.setattr(ctypes, "WinDLL", load, raising=False)
    backend = LibMpvBackend(settings=MpvSettings(executable="missing-mpv"))
    backend._load_library()

    assert backend.library_path == str(library_path)
    assert backend._library is library


def test_libmpv_backend_applies_extra_command_line_options() -> None:
    library = FakeLibrary()
    backend = LibMpvBackend(
        settings=MpvSettings(
            extra_args=[
                "--hwdec=auto",
                "--no-cache",
                "--force-window",
                "--profile",
                "fast",
            ]
        ),
        library=library,
    )

    backend.start()
    backend.stop()

    assert library.options[-4:] == [
        ("hwdec", "auto"),
        ("cache", "no"),
        ("force-window", "yes"),
        ("profile", "fast"),
    ]


@pytest.mark.parametrize(
    ("backend_name", "expected_type"),
    [
        ("libmpv", LibMpvBackend),
    ],
)
def test_backend_factory_selects_libmpv_by_default(
    monkeypatch,
    backend_name: str,
    expected_type,
) -> None:
    monkeypatch.setenv("OPEN_TELLY_BACKEND", backend_name)

    assert isinstance(create_mpv_backend(), expected_type)


def test_backend_factory_retains_explicit_process_fallback(monkeypatch) -> None:
    from iptv_player.player.mpv_process import MpvProcess

    monkeypatch.setenv("OPEN_TELLY_BACKEND", "process")
    assert isinstance(create_mpv_backend(), MpvProcess)


def test_event_loop_stops_without_waiting_for_full_poll_interval() -> None:
    library = FakeLibrary()
    backend = LibMpvBackend(library=library)
    backend.start()
    event_thread = backend._event_thread

    started = time.monotonic()
    backend.stop()

    assert event_thread is not None
    assert not event_thread.is_alive()
    assert time.monotonic() - started < 1


def test_end_file_event_preserves_64_bit_playlist_entry_id() -> None:
    library = FakeLibrary()
    backend = LibMpvBackend(library=library)
    playlist_entry_id = 1 << 40
    details = _MpvEventEndFile(0, 0, playlist_entry_id, 0, 0)
    event = _MpvEvent(
        _MPV_EVENT_END_FILE,
        0,
        0,
        ctypes.cast(ctypes.pointer(details), ctypes.c_void_p),
    )

    normalized = backend._normalize_event(event)

    assert normalized is not None
    assert normalized.playlist_entry_id == playlist_entry_id


def test_renderer_context_is_created_rendered_and_freed_on_widget_context() -> None:
    class RenderUpdate:
        def __init__(self) -> None:
            self.emitted = False

        def emit(self) -> None:
            self.emitted = True

    class RenderWidget:
        def __init__(self) -> None:
            self.request_render_update = RenderUpdate()
            self.current = False

        def makeCurrent(self) -> None:
            self.current = True

        def doneCurrent(self) -> None:
            self.current = False

    library = FakeLibrary()
    backend = LibMpvBackend(library=library)
    backend.start()
    widget = RenderWidget()

    backend.attach_renderer(widget)
    assert not widget.current
    assert library.render_context == 5678
    assert library.update_callback is not None
    assert library.mpv_render_context_render.restype is ctypes.c_int
    backend.render(1, 640, 360)
    backend.detach_renderer(widget)
    backend.stop()

    assert library.render_calls == [5678]
    assert library.render_context is None
    assert not widget.current

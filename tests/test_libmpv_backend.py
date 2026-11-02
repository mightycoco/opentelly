import ctypes
import time

import pytest

from iptv_player.models import Channel
from iptv_player.player.factory import create_mpv_backend
from iptv_player.player.libmpv import LibMpvBackend


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
        self.mpv_render_context_create = FakeFunction(lambda *args: 0)
        self.mpv_render_context_set_update_callback = FakeFunction(lambda *args: None)
        self.mpv_render_context_render = FakeFunction(lambda *args: 0)
        self.mpv_render_context_free = FakeFunction(lambda *args: None)

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

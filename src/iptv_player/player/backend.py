from __future__ import annotations

from typing import Any, Callable, Protocol

from iptv_player.models import Channel


MpvMessageCallback = Callable[[dict[str, Any]], None]
BackendCommand = tuple[int, str, object]


class MpvBackend(Protocol):
    """Named playback operations required by the worker from an mpv backend."""

    def add_callback(self, callback: MpvMessageCallback) -> None: ...

    def start(self, hwnd: int) -> None: ...

    def reserve_request_id(self) -> int: ...

    def send_command(
        self,
        command: list[str | int],
        request_id: int | None = None,
    ) -> int: ...

    def observe_property(self, property_name: str, observer_id: int) -> int: ...

    def load_channel(self, channel: Channel, request_id: int) -> int: ...

    def select_audio_track(self, track_id: int, request_id: int) -> int: ...

    def stop_playback(self, request_id: int) -> int: ...

    def set_muted(self, muted: bool, request_id: int) -> int: ...

    def get_audio_tracks(self, request_id: int) -> int: ...

    def stop(self) -> None: ...

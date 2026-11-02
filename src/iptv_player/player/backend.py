from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from iptv_player.models import Channel


BackendEventKind = Literal[
    "command-reply",
    "property-change",
    "file-loaded",
    "end-file",
    "transport-error",
]
BackendCommand = tuple[int, str, object]


@dataclass(frozen=True, slots=True)
class BackendEvent:
    """Backend-neutral event emitted by an mpv implementation."""

    kind: BackendEventKind
    request_id: int | None = None
    error: str | None = None
    data: object = None
    property_name: str | None = None
    playlist_entry_id: int | None = None
    reason: str | None = None
    file_error: str | None = None

    @classmethod
    def from_ipc_message(
        cls,
        message: dict[str, Any],
    ) -> BackendEvent | None:
        event = message.get("event")
        if event == "ipc-write-error":
            kind: BackendEventKind = "transport-error"
        elif event == "property-change":
            kind = "property-change"
        elif event == "file-loaded":
            kind = "file-loaded"
        elif event == "end-file":
            kind = "end-file"
        elif "request_id" in message:
            kind = "command-reply"
        else:
            return None

        request_id = message.get("request_id")
        playlist_entry_id = message.get("playlist_entry_id")
        return cls(
            kind=kind,
            request_id=request_id if type(request_id) is int else None,
            error=message.get("error") if isinstance(message.get("error"), str) else None,
            data=message.get("data"),
            property_name=(
                message.get("name") if isinstance(message.get("name"), str) else None
            ),
            playlist_entry_id=(
                playlist_entry_id if type(playlist_entry_id) is int else None
            ),
            reason=message.get("reason") if isinstance(message.get("reason"), str) else None,
            file_error=(
                message.get("file_error")
                if isinstance(message.get("file_error"), str)
                else None
            ),
        )


MpvEventCallback = Callable[[BackendEvent], None]
class MpvBackend(Protocol):
    """Named playback operations required by the worker from an mpv backend."""

    requires_render_widget: bool

    def add_callback(self, callback: MpvEventCallback) -> None: ...

    def start(self, hwnd: int | None = None) -> None: ...

    def attach_renderer(self, widget: Any) -> None: ...

    def detach_renderer(self, widget: Any) -> None: ...

    def render(self, framebuffer: int, width: int, height: int) -> None: ...

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

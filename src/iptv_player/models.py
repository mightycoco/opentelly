from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class AudioTrack:
    """Represents an audio stream exposed by mpv."""

    track_id: int
    title: str | None = None
    language: str | None = None
    codec: str | None = None
    selected: bool = False

    @property
    def label(self) -> str:
        name = self.title or self.language or f"Audio track {self.track_id}"
        details = [
            value
            for value in (self.language if name != self.language else None, self.codec)
            if value and value.casefold() != name.casefold()
        ]
        return f"{name} ({', '.join(details)})" if details else name


@dataclass(slots=True)
class Channel:
    """Represents a single playlist entry."""

    name: str
    url: str
    channel_id: Optional[str] = None
    group: Optional[str] = None
    logo_url: Optional[str] = None
    position: int = 0

    def __post_init__(self) -> None:
        self.name = (self.name or "").strip()
        self.url = (self.url or "").strip()
        self.channel_id = self.channel_id.strip() if self.channel_id else None
        self.group = self.group.strip() if self.group else None
        self.logo_url = self.logo_url.strip() if self.logo_url else None

    def __str__(self) -> str:
        return self.name or self.url or "<unnamed channel>"

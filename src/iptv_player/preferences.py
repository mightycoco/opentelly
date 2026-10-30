from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QSettings

from iptv_player.models import Channel


def channel_key(channel: Channel) -> str:
    return hashlib.sha256(channel.url.encode("utf-8")).hexdigest()


def playlist_key(playlist_path: str | Path) -> str:
    path = os.path.normcase(str(Path(playlist_path).expanduser().resolve()))
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


class PlayerPreferences:
    """Persistent application preferences backed by Qt settings."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings if settings is not None else QSettings("LMP", "Open Telly")

    def window_geometry(self) -> bytes | None:
        value = self._settings.value("window/geometry")
        return bytes(value) if value is not None else None

    def save_window_geometry(self, geometry: bytes) -> None:
        self._settings.setValue("window/geometry", geometry)

    def window_state(self) -> str | None:
        value = self._settings.value("window/state")
        return str(value) if value else None

    def save_window_state(self, state: str) -> None:
        self._settings.setValue("window/state", state)

    def is_pinned(self) -> bool:
        return bool(self._settings.value("window/pinned", False, type=bool))

    def save_pinned(self, pinned: bool) -> None:
        self._settings.setValue("window/pinned", pinned)

    def resume_channel_key(self, playlist_path: str | Path) -> str | None:
        value = self._settings.value(f"playlists/{playlist_key(playlist_path)}/channel")
        return str(value) if value else None

    def save_resume_channel(self, playlist_path: str | Path, channel: Channel) -> None:
        self._settings.setValue(
            f"playlists/{playlist_key(playlist_path)}/channel",
            channel_key(channel),
        )

    def audio_track_id(self, channel: Channel) -> int | None:
        value = self._settings.value(f"audio/{channel_key(channel)}")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def save_audio_track_id(self, channel: Channel, track_id: int) -> None:
        self._settings.setValue(f"audio/{channel_key(channel)}", track_id)

    def favourites(self) -> list[Channel]:
        raw_value = self._settings.value("favourites/channels", "[]")
        try:
            records = json.loads(str(raw_value))
        except json.JSONDecodeError:
            return []
        if not isinstance(records, list):
            return []
        channels = []
        for record in records:
            if not isinstance(record, dict):
                continue
            name, url = record.get("name"), record.get("url")
            if not isinstance(name, str) or not isinstance(url, str):
                continue
            channels.append(
                Channel(
                    name=name,
                    url=url,
                    channel_id=record.get("channel_id"),
                    group=record.get("group"),
                    logo_url=record.get("logo_url"),
                    position=record.get("position", 0),
                )
            )
        return channels

    def save_favourites(self, channels: list[Channel]) -> None:
        records = [
            {
                "name": channel.name,
                "url": channel.url,
                "channel_id": channel.channel_id,
                "group": channel.group,
                "logo_url": channel.logo_url,
                "position": channel.position,
            }
            for channel in channels
        ]
        self._settings.setValue(
            "favourites/channels",
            json.dumps(records, ensure_ascii=False),
        )

    def sync(self) -> None:
        self._settings.sync()

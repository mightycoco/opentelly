from __future__ import annotations

import logging
import re
from typing import Iterable

from iptv_player.models import Channel

logger = logging.getLogger(__name__)

_EXTINF_PATTERN = re.compile(
    r"^#EXTINF(?::(?P<duration>-?\d+))?(?:\s+(?P<attrs>.*?))?,(?P<title>.*)$",
    re.IGNORECASE,
)
_ATTR_PATTERN = re.compile(r'([A-Za-z0-9_-]+)=(?:"([^"]*)"|([^\s,]+))')


def parse_m3u_playlist(contents: str) -> list[Channel]:
    """Parse an Extended M3U playlist into Channel objects."""

    channels: list[Channel] = []
    pending_name: str | None = None
    pending_group: str | None = None
    pending_channel_id: str | None = None
    pending_logo: str | None = None

    for line_number, raw_line in enumerate(contents.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTM3U"):
            continue
        if line.startswith("#"):
            if not line.upper().startswith("#EXTINF"):
                continue
            match = _EXTINF_PATTERN.match(line)
            if match:
                attrs = match.group("attrs") or ""
                title = (match.group("title") or "").strip()
                parsed_attrs = {
                    name.lower(): value
                    for name, value, _ in _ATTR_PATTERN.findall(attrs)
                    if value is not None
                }
                parsed_attrs.update(
                    {
                        name.lower(): value
                        for name, _, value in _ATTR_PATTERN.findall(attrs)
                        if value is not None and name.lower() not in parsed_attrs
                    }
                )
                pending_name = title or parsed_attrs.get("tvg-name") or parsed_attrs.get("title") or "Unnamed channel"
                pending_group = parsed_attrs.get("group-title") or parsed_attrs.get("group")
                pending_channel_id = parsed_attrs.get("tvg-id")
                pending_logo = parsed_attrs.get("tvg-logo")
            else:
                logger.warning("Ignoring malformed EXTINF directive on line %s: %s", line_number, raw_line)
            continue
        if pending_name is None:
            logger.warning("Skipping orphaned playlist line %s: %s", line_number, raw_line)
            continue

        url = line
        channel = Channel(
            name=pending_name,
            url=url,
            channel_id=pending_channel_id,
            group=pending_group,
            logo_url=pending_logo,
            position=len(channels),
        )
        if not channel.name:
            logger.warning("Skipping malformed channel entry at line %s with empty name", line_number)
            pending_name = None
            pending_group = None
            pending_channel_id = None
            pending_logo = None
            continue
        if not channel.url:
            logger.warning("Skipping malformed channel entry at line %s with empty URL", line_number)
            pending_name = None
            pending_group = None
            pending_channel_id = None
            pending_logo = None
            continue
        channels.append(channel)
        pending_name = None
        pending_group = None
        pending_channel_id = None
        pending_logo = None

    return channels


def parse_m3u_file(path: str | Iterable[str]) -> list[Channel]:
    """Parse a playlist from a file-like or iterable object."""

    if isinstance(path, str):
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            return parse_m3u_playlist(handle.read())

    joined = "\n".join(str(part) for part in path)
    return parse_m3u_playlist(joined)

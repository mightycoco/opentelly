from __future__ import annotations

from iptv_player.models import Channel


def test_channel_model_preserves_values_and_strips_whitespace() -> None:
    channel = Channel(
        name="  Hello World  ",
        url="  rtsp://example.com/stream  ",
        channel_id=" channel-2 ",
        group=" Sports ",
        logo_url=" http://example.com/logo.png ",
        position=4,
    )

    assert channel.name == "Hello World"
    assert channel.url == "rtsp://example.com/stream"
    assert channel.channel_id == "channel-2"
    assert channel.group == "Sports"
    assert channel.logo_url == "http://example.com/logo.png"
    assert str(channel) == "Hello World"

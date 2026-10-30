from __future__ import annotations

from iptv_player.playlist.m3u_parser import parse_m3u_playlist


def test_parse_extended_m3u_playlist() -> None:
    playlist = """#EXTM3U\r\n#EXTINF:-1 tvg-id=\"channel-1\" tvg-name=\"Das Erste HD\" group-title=\"Deutsch\" tvg-logo=\"https://example.com/logo1.png\",Das Erste HD\r\nrtsp://example.com/stream1\r\n#EXTINF:-1,ZDF HD\r\nrtsp://example.com/stream2\r\n"""

    channels = parse_m3u_playlist(playlist)

    assert len(channels) == 2
    assert channels[0].name == "Das Erste HD"
    assert channels[0].url == "rtsp://example.com/stream1"
    assert channels[0].channel_id == "channel-1"
    assert channels[0].group == "Deutsch"
    assert channels[0].logo_url == "https://example.com/logo1.png"
    assert channels[1].name == "ZDF HD"
    assert channels[1].url == "rtsp://example.com/stream2"


def test_parse_playlist_with_utf8_bom_and_blank_lines() -> None:
    playlist = "\ufeff#EXTM3U\n\n#EXTINF:-1,Test Channel\nrtsp://example.com/stream?query=1,2\n\n#EXTINF:-1,Another Channel\nrtsp://example.com/stream2\n"

    channels = parse_m3u_playlist(playlist)

    assert channels[0].name == "Test Channel"
    assert channels[0].url == "rtsp://example.com/stream?query=1,2"
    assert channels[1].name == "Another Channel"


def test_parse_playlist_ignores_invalid_entries() -> None:
    playlist = """#EXTM3U\n#EXTINF:-1,Valid\nrtsp://example.com/ok\n#EXTINF:-1\n#EXTINF:-1,Missing URL\n#EXTINF:-1,Another\nrtsp://example.com/another\n"""

    channels = parse_m3u_playlist(playlist)

    assert [channel.name for channel in channels] == ["Valid", "Another"]
    assert [channel.url for channel in channels] == ["rtsp://example.com/ok", "rtsp://example.com/another"]


def test_vlc_options_are_ignored_without_warnings(caplog) -> None:
    playlist = """#EXTM3U
#EXTINF:-1,Channel One
#EXTVLCOPT:network-caching=1000
rtsp://example.com/stream
"""

    channels = parse_m3u_playlist(playlist)

    assert len(channels) == 1
    assert channels[0].name == "Channel One"
    assert channels[0].url == "rtsp://example.com/stream"
    assert not caplog.records

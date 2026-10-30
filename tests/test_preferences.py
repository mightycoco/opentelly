from PySide6.QtCore import QSettings

from iptv_player.models import Channel
from iptv_player.preferences import PlayerPreferences, channel_key


def test_preferences_persist_window_audio_favourites_and_playlist_resume(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    preferences = PlayerPreferences(settings)
    playlist = tmp_path / "channels.m3u"
    channel = Channel(
        name="News",
        url="rtsp://user:password@example.com/news",
        channel_id="news",
        group="Local",
        position=3,
    )

    preferences.save_window_geometry(b"geometry")
    preferences.save_window_state("maximized")
    preferences.save_pinned(True)
    preferences.save_audio_track_id(channel, 4)
    preferences.save_resume_channel(playlist, channel)
    preferences.save_favourites([channel])
    preferences.sync()

    reloaded = PlayerPreferences(
        QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    )
    assert reloaded.window_geometry() == b"geometry"
    assert reloaded.window_state() == "maximized"
    assert reloaded.is_pinned()
    assert reloaded.audio_track_id(channel) == 4
    assert reloaded.resume_channel_key(playlist) == channel_key(channel)
    assert reloaded.resume_channel_key(tmp_path / "different.m3u") is None
    assert reloaded.favourites() == [channel]


def test_playlist_resume_uses_canonical_path(tmp_path) -> None:
    preferences = PlayerPreferences(
        QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    )
    channel = Channel(name="One", url="rtsp://example.com/one")
    playlist = tmp_path / "channels.m3u"
    preferences.save_resume_channel(playlist, channel)

    assert preferences.resume_channel_key(playlist.parent / "." / playlist.name) == channel_key(
        channel
    )

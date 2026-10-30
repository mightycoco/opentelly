from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from iptv_player.main_window import MainWindow
from iptv_player.models import AudioTrack, Channel
from iptv_player.preferences import PlayerPreferences


def test_window_resumes_the_saved_channel_for_the_loaded_playlist(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    playlist = tmp_path / "channels.m3u"
    playlist.write_text(
        "#EXTM3U\n"
        "#EXTINF:-1,One\nrtsp://example.com/one\n"
        "#EXTINF:-1,Two\nrtsp://example.com/two\n",
        encoding="utf-8",
    )
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    preferences = PlayerPreferences(settings)
    preferences.save_resume_channel(
        playlist,
        Channel(name="Two", url="rtsp://example.com/two"),
    )

    window = MainWindow(playlist_path=playlist, preferences=preferences)

    assert window._initial_channel is not None
    assert window._initial_channel.name == "Two"
    window.close()


def test_window_restores_and_remembers_audio_track_by_channel(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    channel = Channel(name="News", url="rtsp://example.com/news")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    preferences = PlayerPreferences(settings)
    preferences.save_audio_track_id(channel, 2)
    window = MainWindow(preferences=preferences)
    window.current_channel = channel
    requested_tracks = []
    monkeypatch.setattr(
        window._player_worker,
        "select_audio_track",
        requested_tracks.append,
    )

    window._on_audio_tracks_snapshot(
        [
            AudioTrack(track_id=1, title="English", selected=True),
            AudioTrack(track_id=2, title="German"),
        ]
    )

    assert requested_tracks == [2]
    assert preferences.audio_track_id(channel) == 2
    window.close()


def test_window_shows_stream_title_in_status_bar(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(preferences=PlayerPreferences(settings))
    window.current_channel = Channel(name="News", url="rtsp://example.com/news")

    window._on_stream_title_changed("Live bulletin")

    assert window.statusBar().currentMessage() == "Playing: News — Live bulletin"
    window.close()

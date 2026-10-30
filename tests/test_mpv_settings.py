from pathlib import Path

from iptv_player.settings import MpvSettings


def test_mpv_settings_use_supported_options_to_disable_subtitles() -> None:
    command = MpvSettings().build_command(1234)

    assert "--idle=yes" in command
    assert "--sid=no" in command
    assert "--sub-auto=no" in command
    assert "--rtsp-transport=udp" in command
    assert "--demuxer-readahead-secs=1" in command
    assert "--sub-no-ext=yes" not in command
    assert "--rtsp-buffer=1024" not in command


def test_mpv_rtsp_transport_can_be_configured() -> None:
    command = MpvSettings(rtsp_transport="tcp").build_command(1234)

    assert "--rtsp-transport=tcp" in command


def test_mpv_rejects_unknown_rtsp_transport() -> None:
    settings = MpvSettings(rtsp_transport="sctp")

    try:
        settings.build_command(1234)
    except ValueError as exc:
        assert "Unsupported RTSP transport" in str(exc)
    else:
        raise AssertionError("Expected unsupported RTSP transport to be rejected")


def test_resolve_executable_falls_back_to_winget_install(monkeypatch, tmp_path: Path) -> None:
    install_dir = tmp_path / "MPV Player"
    install_dir.mkdir()
    executable = install_dir / "mpv.exe"
    executable.touch()
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setattr("iptv_player.settings.shutil.which", lambda _: None)

    assert MpvSettings().resolve_executable() == str(executable)


def test_resolve_executable_prefers_path(monkeypatch) -> None:
    monkeypatch.setattr(
        "iptv_player.settings.shutil.which",
        lambda executable: r"C:\Tools\mpv.exe",
    )

    assert MpvSettings().resolve_executable() == r"C:\Tools\mpv.exe"


def test_resolve_executable_reports_missing_program() -> None:
    settings = MpvSettings(executable="missing-mpv-executable")

    try:
        settings.resolve_executable()
    except FileNotFoundError as exc:
        assert "Add mpv to PATH" in str(exc)
    else:
        raise AssertionError("Expected a missing executable to be reported")

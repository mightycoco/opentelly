from iptv_player.player.backend import BackendEvent


def test_ipc_messages_are_normalized_into_backend_events() -> None:
    event = BackendEvent.from_ipc_message(
        {
            "event": "property-change",
            "name": "track-list",
            "data": [{"type": "audio", "id": 2}],
        }
    )

    assert event == BackendEvent(
        kind="property-change",
        data=[{"type": "audio", "id": 2}],
        property_name="track-list",
    )


def test_unobserved_mpv_events_do_not_escape_the_backend_adapter() -> None:
    assert BackendEvent.from_ipc_message({"event": "playback-restart"}) is None


def test_ipc_command_errors_and_end_file_details_are_preserved() -> None:
    command_reply = BackendEvent.from_ipc_message(
        {"request_id": 12, "error": "property unavailable"}
    )
    end_file = BackendEvent.from_ipc_message(
        {
            "event": "end-file",
            "reason": "error",
            "playlist_entry_id": 42,
            "file_error": "connection refused",
        }
    )

    assert command_reply is not None
    assert command_reply.kind == "command-reply"
    assert command_reply.request_id == 12
    assert command_reply.error == "property unavailable"
    assert end_file is not None
    assert end_file.kind == "end-file"
    assert end_file.reason == "error"
    assert end_file.playlist_entry_id == 42
    assert end_file.file_error == "connection refused"

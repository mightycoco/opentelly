import threading
import time

from PySide6.QtTest import QSignalSpy

from iptv_player.models import Channel
from iptv_player.player.backend import BackendEvent
from iptv_player.player.worker import MpvWorker


def deliver_message(worker: MpvWorker, message: dict) -> None:
    event = BackendEvent.from_ipc_message(message)
    assert event is not None
    worker._handle_backend_event(event)


class FakeMpvProcess:
    requires_render_widget = False

    def __init__(self) -> None:
        self.callbacks = []
        self.request_id = 16
        self.commands = []

    def add_callback(self, callback) -> None:
        self.callbacks.append(callback)

    def reserve_request_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def load_channel(self, channel: Channel, request_id: int | None = None) -> int:
        return self.send_command(["loadfile", channel.url, "replace"], request_id)

    def select_audio_track(self, track_id: int, request_id: int) -> int:
        return self.send_command(["set_property", "aid", track_id], request_id)

    def stop_playback(self, request_id: int) -> int:
        return self.send_command(["stop"], request_id)

    def set_muted(self, muted: bool, request_id: int) -> int:
        return self.send_command(["set_property", "mute", muted], request_id)

    def get_audio_tracks(self, request_id: int) -> int:
        return self.send_command(["get_property", "track-list"], request_id)

    def send_command(self, command: list[str | int], request_id: int | None = None) -> int:
        self.commands.append((command, request_id))
        return request_id if request_id is not None else self.reserve_request_id()

    def observe_property(self, property_name: str, observer_id: int) -> int:
        return self.reserve_request_id()


def ready_worker(process: FakeMpvProcess) -> MpvWorker:
    worker = MpvWorker(process)
    worker._started = True
    worker._command_thread = threading.Thread(
        target=worker._send_channel_commands,
        daemon=True,
    )
    worker._command_thread.start()
    return worker


def test_worker_waits_for_mpv_file_loaded_before_reporting_success() -> None:
    worker = ready_worker(FakeMpvProcess())
    loaded = QSignalSpy(worker.channel_loaded)
    failed = QSignalSpy(worker.channel_failed)
    channel = Channel(name="Second", url="rtsp://example.com/second")

    worker.load_channel(channel)
    deliver_message(worker,
        {
            "request_id": 17,
            "error": "success",
            "data": {"playlist_entry_id": 23},
        }
    )
    assert loaded.count() == 0

    deliver_message(worker, {"event": "file-loaded"})
    assert loaded.count() == 1
    assert loaded.at(0)[0] == channel
    assert failed.count() == 0


def test_worker_reports_asynchronous_stream_errors() -> None:
    worker = ready_worker(FakeMpvProcess())
    loaded = QSignalSpy(worker.channel_loaded)
    failed = QSignalSpy(worker.channel_failed)

    worker.load_channel(Channel(name="Unavailable", url="rtsp://example.com/missing"))
    deliver_message(worker,
        {
            "request_id": 17,
            "error": "success",
            "data": {"playlist_entry_id": 23},
        }
    )
    deliver_message(worker,
        {
            "event": "end-file",
            "reason": "error",
            "file_error": "connection refused",
            "playlist_entry_id": 23,
        }
    )

    assert loaded.count() == 0
    assert failed.count() == 1
    assert "connection refused" in failed.at(0)[0]


def test_worker_ignores_late_events_from_a_channel_replaced_by_a_newer_request() -> None:
    worker = ready_worker(FakeMpvProcess())
    loaded = QSignalSpy(worker.channel_loaded)
    first = Channel(name="First", url="rtsp://example.com/first")
    second = Channel(name="Second", url="rtsp://example.com/second")

    worker.load_channel(first)
    deliver_message(worker,
        {"request_id": 17, "error": "success", "data": {"playlist_entry_id": 31}}
    )
    worker.load_channel(second)
    deliver_message(worker,
        {"request_id": 18, "error": "success", "data": {"playlist_entry_id": 32}}
    )

    deliver_message(worker, {"event": "file-loaded"})
    assert loaded.count() == 1
    assert loaded.at(0)[0] == second

    worker.load_channel(first)
    third_request_id = worker._pending_request_id
    deliver_message(worker,
        {
            "request_id": third_request_id,
            "error": "success",
            "data": {"playlist_entry_id": 33},
        }
    )
    deliver_message(worker, {"event": "file-loaded", "playlist_entry_id": 33})
    assert loaded.count() == 2
    assert loaded.at(1)[0] == first

    deliver_message(worker, {"event": "file-loaded", "playlist_entry_id": 31})
    assert loaded.count() == 2


def test_worker_does_not_wait_for_a_blocked_ipc_write() -> None:
    send_started = threading.Event()
    release_send = threading.Event()

    class BlockingMpvProcess(FakeMpvProcess):
        def send_command(self, command: list[str | int], request_id: int | None = None) -> int:
            send_started.set()
            release_send.wait(timeout=2)
            return request_id if request_id is not None else self.reserve_request_id()

    worker = ready_worker(BlockingMpvProcess())
    started_at = time.monotonic()
    worker.load_channel(Channel(name="Blocked", url="rtsp://example.com/blocked"))

    assert time.monotonic() - started_at < 0.1
    assert send_started.wait(timeout=1)
    release_send.set()


def test_worker_reports_audio_tracks_and_queues_track_selection() -> None:
    process = FakeMpvProcess()
    worker = ready_worker(process)
    tracks_changed = QSignalSpy(worker.audio_tracks_changed)

    deliver_message(worker,
        {
            "event": "property-change",
            "name": "track-list",
            "data": [
                {"type": "video", "id": 1, "selected": True},
                {
                    "type": "audio",
                    "id": 2,
                    "title": "Original",
                    "lang": "eng",
                    "codec": "aac",
                    "selected": True,
                },
                {"type": "audio", "id": 3, "lang": "deu", "selected": False},
            ],
        }
    )

    assert tracks_changed.count() == 1
    tracks = tracks_changed.at(0)[0]
    assert [(track.track_id, track.label, track.selected) for track in tracks] == [
        (2, "Original (eng, aac)", True),
        (3, "deu", False),
    ]

    worker.select_audio_track(3)
    deadline = time.monotonic() + 1
    while not process.commands and time.monotonic() < deadline:
        time.sleep(0.01)
    assert process.commands[-1][0] == ["set_property", "aid", 3]


def test_worker_reports_stream_titles_from_metadata() -> None:
    worker = ready_worker(FakeMpvProcess())
    titles = QSignalSpy(worker.stream_title_changed)

    deliver_message(worker,
        {
            "event": "property-change",
            "name": "metadata",
            "data": {"TITLE": "  Evening News  "},
        }
    )
    deliver_message(worker,
        {
            "event": "property-change",
            "name": "metadata",
            "data": {"title": "Programme", "ICY-TITLE": "Artist - Track"},
        }
    )
    deliver_message(worker,
        {"event": "property-change", "name": "metadata", "data": {}}
    )

    assert [titles.at(index)[0] for index in range(titles.count())] == [
        "Evening News",
        "Artist - Track",
        "",
    ]


def test_worker_refreshes_track_list_after_audio_selection() -> None:
    process = FakeMpvProcess()
    worker = ready_worker(process)
    worker.select_audio_track(3)
    deadline = time.monotonic() + 1
    while not process.commands and time.monotonic() < deadline:
        time.sleep(0.01)
    selection_request_id = process.commands[-1][1]

    deliver_message(worker,
        {"request_id": selection_request_id, "error": "success"}
    )

    deadline = time.monotonic() + 1
    while len(process.commands) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert process.commands[-1][0] == ["get_property", "track-list"]


def test_worker_queues_stop_and_mute_commands_and_reports_control_errors() -> None:
    process = FakeMpvProcess()
    worker = ready_worker(process)
    failures = QSignalSpy(worker.playback_control_failed)

    worker.stop_playback()
    worker.set_muted(True)
    deadline = time.monotonic() + 1
    while len(process.commands) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert [command for command, _ in process.commands] == [
        ["stop"],
        ["set_property", "mute", True],
    ]
    stop_request_id = process.commands[0][1]
    deliver_message(worker,
        {"request_id": stop_request_id, "error": "command unavailable"}
    )
    assert failures.count() == 1
    assert failures.at(0) == [
        "stopped",
        True,
        "Could not stop playback: command unavailable",
    ]

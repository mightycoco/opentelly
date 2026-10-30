import json
import threading
import time

from iptv_player.player import mpv_ipc


class FakeWin32File:
    GENERIC_READ = 1
    GENERIC_WRITE = 2
    OPEN_EXISTING = 3

    def __init__(self) -> None:
        self.handles = []
        self.writes = []
        self.closed = []
        self.read_counts = {}

    def CreateFile(self, *args):
        handle = object()
        self.handles.append(handle)
        return handle

    def WriteFile(self, handle, data):
        self.writes.append((handle, json.loads(data)))

    def ReadFile(self, handle, size):
        requests = [
            payload for written_handle, payload in self.writes if written_handle is handle
        ]
        read_count = self.read_counts.get(handle, 0)
        if read_count >= len(requests):
            raise FakePipeEmpty()
        request = requests[read_count]
        self.read_counts[handle] = read_count + 1
        response = {
            "request_id": request["request_id"],
            "error": "success",
            "data": {"playlist_entry_id": 41},
        }
        messages = [response]
        if request["command"][0] == "observe_property":
            messages.append(
                {
                    "event": "property-change",
                    "name": request["command"][2],
                    "data": [{"type": "audio", "id": 4, "selected": True}],
                }
            )
        return 0, "".join(json.dumps(message) + "\n" for message in messages).encode()

    def CloseHandle(self, handle):
        self.closed.append(handle)


class FakePipeEmpty(Exception):
    winerror = 232


class FakeWin32Pipe:
    PIPE_READMODE_BYTE = 0
    PIPE_NOWAIT = 1

    def __init__(self) -> None:
        self.opened_path = None

    def WaitNamedPipe(self, path, timeout):
        self.opened_path = path

    def SetNamedPipeHandleState(self, handle, mode, max_collection_count, collect_data_timeout):
        pass


def test_send_command_uses_a_separate_pipe_and_dispatches_its_response(monkeypatch) -> None:
    file_api = FakeWin32File()
    pipe_api = FakeWin32Pipe()
    monkeypatch.setattr(mpv_ipc, "win32file", file_api)
    monkeypatch.setattr(mpv_ipc, "win32pipe", pipe_api)

    client = mpv_ipc.MpvIpcClient("test-pipe")
    client._stop_event = threading.Event()
    messages = []
    client.add_callback(messages.append)

    request_id = client.send_command(["loadfile", "channel.m3u8", "replace"])

    assert pipe_api.opened_path == r"\\.\pipe\test-pipe"
    assert len(file_api.handles) == 1
    assert file_api.writes[0][0] is file_api.handles[0]
    assert file_api.writes[0][1] == {
        "command": ["loadfile", "channel.m3u8", "replace"],
        "request_id": request_id,
    }
    assert messages == [
        {
            "request_id": request_id,
            "error": "success",
            "data": {"playlist_entry_id": 41},
        }
    ]
    assert file_api.closed == [file_api.handles[0]]


def test_observed_property_uses_a_persistent_monitor_connection(monkeypatch) -> None:
    file_api = FakeWin32File()
    pipe_api = FakeWin32Pipe()
    monkeypatch.setattr(mpv_ipc, "win32file", file_api)
    monkeypatch.setattr(mpv_ipc, "win32pipe", pipe_api)

    client = mpv_ipc.MpvIpcClient("test-pipe")
    client._stop_event = threading.Event()
    messages = []
    client.add_callback(messages.append)

    request_id = client.observe_property("track-list", 7)
    deadline = time.monotonic() + 1
    while not any(message.get("event") == "property-change" for message in messages):
        if time.monotonic() >= deadline:
            raise AssertionError("The observed property event was not dispatched")
        time.sleep(0.01)

    assert file_api.writes[0][1] == {
        "command": ["observe_property", 7, "track-list"],
        "request_id": request_id,
    }
    assert messages[-1] == {
        "event": "property-change",
        "name": "track-list",
        "data": [{"type": "audio", "id": 4, "selected": True}],
    }
    assert client._monitor_handle is file_api.handles[0]
    client.close()


def test_multiple_observed_properties_share_a_monitor_connection(monkeypatch) -> None:
    file_api = FakeWin32File()
    pipe_api = FakeWin32Pipe()
    monkeypatch.setattr(mpv_ipc, "win32file", file_api)
    monkeypatch.setattr(mpv_ipc, "win32pipe", pipe_api)

    client = mpv_ipc.MpvIpcClient("test-pipe")
    client._stop_event = threading.Event()
    messages = []
    client.add_callback(messages.append)

    track_request_id = client.observe_property("track-list", 7)
    title_request_id = client.observe_property("metadata", 8)
    deadline = time.monotonic() + 1
    while not any(
        message.get("event") == "property-change" and message.get("name") == "metadata"
        for message in messages
    ):
        if time.monotonic() >= deadline:
            raise AssertionError("The second observed property event was not dispatched")
        time.sleep(0.01)

    assert len(file_api.handles) == 1
    assert [payload for _, payload in file_api.writes] == [
        {
            "command": ["observe_property", 7, "track-list"],
            "request_id": track_request_id,
        },
        {
            "command": ["observe_property", 8, "metadata"],
            "request_id": title_request_id,
        },
    ]
    assert messages[-1]["name"] == "metadata"
    client.close()

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import uuid


@dataclass(slots=True)
class MpvSettings:
    """Centralized mpv configuration."""

    executable: str = "mpv"
    ipc_pipe_name: str = field(default_factory=lambda: f"iptv-mpv-{uuid.uuid4().hex}")
    volume: int = 100
    rtsp_transport: str = "udp"
    extra_args: list[str] = field(default_factory=list)

    def resolve_executable(self) -> str:
        """Find mpv on PATH or in the standard Windows installation folder."""

        executable = self.executable
        resolved = shutil.which(executable)
        if resolved:
            return resolved

        executable_path = Path(executable)
        if executable_path.is_absolute() or "\\" in executable or "/" in executable:
            raise FileNotFoundError(f"Configured mpv executable does not exist: {executable}")

        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        executable_name = executable if executable_path.suffix else f"{executable}.exe"
        winget_install = program_files / "MPV Player" / executable_name
        if winget_install.is_file():
            return str(winget_install)

        raise FileNotFoundError(
            f"Could not find '{executable}' on PATH or at '{winget_install}'. "
            "Add mpv to PATH or configure MpvSettings(executable=...)."
        )

    def build_command(self, hwnd: int) -> list[str]:
        if self.rtsp_transport not in {"udp", "tcp", "udp_multicast", "http", "lavf"}:
            raise ValueError(f"Unsupported RTSP transport: {self.rtsp_transport}")

        command = [
            self.executable,
            f"--wid={hwnd}",
            "--force-window=yes",
            "--keep-open=yes",
            "--no-terminal",
            "--title=IPTV Player",
            f"--input-ipc-server=\\\\.\\pipe\\{self.ipc_pipe_name}",
            "--idle=yes",
            "--sid=no",
            "--sub-auto=no",
            "--cache=yes",
            "--cache-pause=no",
            "--no-config",
            f"--rtsp-transport={self.rtsp_transport}",
            "--demuxer-readahead-secs=1",
            "--network-timeout=15",
            "--audio-display=no",
            f"--volume={self.volume}",
        ]
        command.extend(self.extra_args)
        return command

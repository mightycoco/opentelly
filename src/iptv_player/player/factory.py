from __future__ import annotations

import os

from iptv_player.player.backend import MpvBackend
from iptv_player.player.libmpv import LibMpvBackend
from iptv_player.player.mpv_process import MpvProcess
from iptv_player.settings import MpvSettings


def create_mpv_backend(settings: MpvSettings | None = None) -> MpvBackend:
    backend_name = os.environ.get("OPEN_TELLY_BACKEND", "libmpv").casefold()
    if backend_name == "libmpv":
        return LibMpvBackend(settings)
    if backend_name == "process":
        return MpvProcess(settings)
    raise ValueError(
        "OPEN_TELLY_BACKEND must be 'libmpv' or 'process', "
        f"not {backend_name!r}"
    )

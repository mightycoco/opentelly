from __future__ import annotations

import os
import logging

from iptv_player.player.backend import MpvBackend
from iptv_player.player.libmpv import LibMpvBackend
from iptv_player.player.mpv_process import MpvProcess
from iptv_player.settings import MpvSettings

logger = logging.getLogger(__name__)


def create_mpv_backend(settings: MpvSettings | None = None) -> MpvBackend:
    backend_name = os.environ.get("OPEN_TELLY_BACKEND", "auto").casefold()
    if backend_name == "auto":
        backend = LibMpvBackend(settings)
        try:
            backend.load_library()
        except RuntimeError as exc:
            logger.warning(
                "libmpv is unavailable; using the mpv process backend instead: %s",
                exc,
            )
            return MpvProcess(settings)
        return backend
    if backend_name == "libmpv":
        return LibMpvBackend(settings)
    if backend_name == "process":
        return MpvProcess(settings)
    raise ValueError(
        "OPEN_TELLY_BACKEND must be 'auto', 'libmpv', or 'process', "
        f"not {backend_name!r}"
    )

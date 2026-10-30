from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from iptv_player.application import IPTVApplication


def main() -> int:
    app = IPTVApplication(sys.argv)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())

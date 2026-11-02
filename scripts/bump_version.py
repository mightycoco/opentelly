from __future__ import annotations

import argparse
from pathlib import Path
import re


VERSION_FILE = Path(__file__).resolve().parents[1] / "src" / "iptv_player" / "__init__.py"
VERSION_PATTERN = re.compile(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)


def bump_version(increment: str, version_file: Path = VERSION_FILE) -> str:
    if increment not in {"major", "minor", "patch"}:
        raise ValueError(f"Unsupported version increment: {increment}")

    source = version_file.read_text(encoding="utf-8")
    matches = list(VERSION_PATTERN.finditer(source))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one semantic version in {version_file}")

    match = matches[0]
    major, minor, patch = (int(value) for value in match.groups())
    if increment == "major":
        major, minor, patch = major + 1, 0, 0
    elif increment == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1

    version = f"{major}.{minor}.{patch}"
    updated = VERSION_PATTERN.sub(f'__version__ = "{version}"', source, count=1)
    version_file.write_text(updated, encoding="utf-8")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description="Increment the Open Telly app version.")
    parser.add_argument("increment", choices=("patch", "minor", "major"))
    args = parser.parse_args()
    print(bump_version(args.increment))


if __name__ == "__main__":
    main()

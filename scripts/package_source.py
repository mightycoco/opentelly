from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ITEMS = (
    "README.md",
    "requirements.txt",
    "main.py",
    "src",
    "tests",
    "scripts",
    "docs",
)
REQUIRED_RUNTIME_FILES = (
    Path("licenses/THIRD_PARTY_NOTICES.md"),
    Path("licenses/BUILD-PROVENANCE.txt"),
    Path("licenses/mpv/Copyright"),
    Path("licenses/mpv/LICENSE.LGPL"),
    Path("licenses/ffmpeg/COPYING.LGPLv3"),
    Path("licenses/source/mpv-source.zip"),
    Path("licenses/source/ffmpeg-source.zip"),
    Path("licenses/source/mpv-build-scripts-source.zip"),
)


def build_source_distribution(
    runtime_directory: Path,
    output_path: Path,
    version: str,
    project_root: Path = ROOT,
) -> Path:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"Expected a semantic version, got {version!r}")
    runtime_directory = runtime_directory.resolve()
    missing_runtime_files = [
        path.as_posix()
        for path in REQUIRED_RUNTIME_FILES
        if not (runtime_directory / path).is_file()
    ]
    if missing_runtime_files:
        raise FileNotFoundError(
            "The mpv runtime bundle is incomplete: "
            + ", ".join(missing_runtime_files)
        )
    if not any(
        path.is_file()
        for library_name in ("mpv-2.dll", "libmpv-2.dll")
        for path in runtime_directory.rglob(library_name)
    ):
        raise FileNotFoundError(
            "The mpv runtime bundle does not contain mpv-2.dll or libmpv-2.dll"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="opentelly-package-") as temporary:
        package_root = Path(temporary) / "OpenTelly"
        package_root.mkdir()
        for item in SOURCE_ITEMS:
            source = project_root / item
            destination = package_root / item
            if source.is_dir():
                shutil.copytree(
                    source,
                    destination,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
                )
            elif source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            else:
                raise FileNotFoundError(f"Required source item is missing: {source}")

        shutil.copytree(runtime_directory, package_root / "runtime")
        (package_root / "VERSION.txt").write_bytes(f"{version}\n".encode("ascii"))
        with zipfile.ZipFile(
            output_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for path in sorted(package_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(package_root.parent))

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a source ZIP with a validated libmpv runtime and notices."
    )
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    result = build_source_distribution(
        runtime_directory=args.runtime_dir,
        output_path=args.output,
        version=args.version,
    )
    print(result)


if __name__ == "__main__":
    main()

from pathlib import Path
import zipfile

import pytest

from scripts.package_source import build_source_distribution


def create_source_tree(root: Path) -> None:
    for path in (
        "README.md",
        "requirements.txt",
        "main.py",
        "src/__init__.py",
        "tests/test_example.py",
        "scripts/build.py",
        "docs/guide.md",
    ):
        file_path = root / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("test\n", encoding="utf-8")


def create_runtime_tree(root: Path, library_name: str = "libmpv-2.dll") -> None:
    (root / "bin").mkdir(parents=True)
    (root / "bin" / library_name).write_bytes(b"test dll")
    for path in (
        "licenses/THIRD_PARTY_NOTICES.md",
        "licenses/BUILD-PROVENANCE.txt",
        "licenses/mpv/Copyright",
        "licenses/mpv/LICENSE.LGPL",
        "licenses/ffmpeg/COPYING.LGPLv3",
        "licenses/source/mpv-source.zip",
        "licenses/source/ffmpeg-source.zip",
        "licenses/source/mpv-build-scripts-source.zip",
    ):
        file_path = root / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("license/source\n", encoding="utf-8")


def test_source_distribution_includes_runtime_and_licensing_material(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    runtime_root = tmp_path / "runtime"
    output = tmp_path / "dist" / "OpenTelly-1.2.3-source.zip"
    create_source_tree(project_root)
    create_runtime_tree(runtime_root)

    build_source_distribution(runtime_root, output, "1.2.3", project_root)

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "OpenTelly/VERSION.txt" in names
        assert "OpenTelly/README.md" in names
        assert "OpenTelly/runtime/bin/libmpv-2.dll" in names
        assert "OpenTelly/runtime/licenses/THIRD_PARTY_NOTICES.md" in names
        assert "OpenTelly/runtime/licenses/source/mpv-source.zip" in names
        assert archive.read("OpenTelly/VERSION.txt") == b"1.2.3\n"


def test_source_distribution_requires_shared_library_and_license_sources(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    runtime_root = tmp_path / "runtime"
    create_source_tree(project_root)
    create_runtime_tree(runtime_root)
    (runtime_root / "bin" / "libmpv-2.dll").unlink()

    with pytest.raises(FileNotFoundError, match="does not contain"):
        build_source_distribution(
            runtime_root,
            tmp_path / "out.zip",
            "1.2.3",
            project_root,
        )


def test_source_distribution_rejects_non_semver_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="semantic version"):
        build_source_distribution(
            tmp_path / "runtime",
            tmp_path / "out.zip",
            "not-a-version",
            tmp_path / "project",
        )

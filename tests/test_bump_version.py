import pytest

from scripts.bump_version import bump_version


@pytest.mark.parametrize(
    ("increment", "expected"),
    [
        ("patch", "0.1.1"),
        ("minor", "0.2.0"),
        ("major", "1.0.0"),
    ],
)
def test_bump_version_updates_the_package_version(
    tmp_path,
    increment: str,
    expected: str,
) -> None:
    version_file = tmp_path / "__init__.py"
    version_file.write_text(
        '"""Open Telly package."""\n__version__ = "0.1.0"\n',
        encoding="utf-8",
    )

    assert bump_version(increment, version_file) == expected
    assert f'__version__ = "{expected}"' in version_file.read_text(encoding="utf-8")


def test_bump_version_rejects_invalid_version_source_without_changing_it(
    tmp_path,
) -> None:
    version_file = tmp_path / "__init__.py"
    original = '__version__ = "development"\n'
    version_file.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="semantic version"):
        bump_version("patch", version_file)

    assert version_file.read_text(encoding="utf-8") == original

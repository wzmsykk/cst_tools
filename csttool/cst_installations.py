"""Discovery and validation of locally installed CST backends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import string
from typing import Iterable


CST_EXECUTABLE_NAME = "CST DESIGN ENVIRONMENT.exe"
_VERSION_PATTERN = re.compile(r"CST Studio Suite\s+(\d{4})", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CstInstallation:
    version: int
    executable: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable", Path(self.executable).resolve())
        if self.version < 2015:
            raise ValueError("CST version must be 2015 or newer")

    @property
    def display_name(self) -> str:
        return f"CST Studio Suite {self.version}"


def infer_cst_version(executable: str | Path) -> int | None:
    match = _VERSION_PATTERN.search(str(executable))
    return int(match.group(1)) if match else None


def validate_cst_installation(
    version: int | str,
    executable: str | Path,
) -> CstInstallation:
    path = Path(executable).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"CST executable does not exist: {path}")
    if path.name.casefold() != CST_EXECUTABLE_NAME.casefold():
        raise ValueError(f"expected {CST_EXECUTABLE_NAME}, got {path.name}")
    version = int(version)
    inferred = infer_cst_version(path)
    if inferred is not None and inferred != version:
        raise ValueError(
            f"configured CST version {version} does not match path version {inferred}"
        )
    return CstInstallation(version=version, executable=path)


def default_search_roots() -> tuple[Path, ...]:
    roots = []
    for drive in string.ascii_uppercase[2:]:
        for program_dir in ("Program Files", "Program Files (x86)"):
            roots.append(Path(f"{drive}:/{program_dir}"))
    return tuple(roots)


def discover_cst_installations(
    *,
    search_roots: Iterable[str | Path] | None = None,
    configured: tuple[int | str, str | Path] | None = None,
) -> tuple[CstInstallation, ...]:
    """Return all valid CST installations, newest first."""

    installations: dict[str, CstInstallation] = {}

    def add(version, executable) -> None:
        try:
            installation = validate_cst_installation(version, executable)
        except (FileNotFoundError, OSError, TypeError, ValueError):
            return
        key = str(installation.executable).casefold()
        installations[key] = installation

    if configured and configured[0] and configured[1]:
        add(configured[0], configured[1])

    for root_value in search_roots or default_search_roots():
        root = Path(root_value)
        try:
            suites = root.glob("CST Studio Suite *") if root.is_dir() else ()
            for suite in suites:
                executable = suite / CST_EXECUTABLE_NAME
                version = infer_cst_version(executable)
                if version is not None:
                    add(version, executable)
        except OSError:
            continue

    return tuple(
        sorted(
            installations.values(),
            key=lambda item: (item.version, str(item.executable).casefold()),
            reverse=True,
        )
    )

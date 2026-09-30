"""Read result artifacts independently of VBA code generation."""

from pathlib import Path


def read_key_values(path) -> dict[str, str] | None:
    source = Path(path)
    if not source.exists():
        return None
    lines = [line.strip() for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {lines[index]: lines[index + 1] for index in range(0, len(lines) - 1, 2)}


def read_scalar(path) -> float:
    values = read_key_values(path)
    if values is None:
        raise FileNotFoundError(path)
    return float(values["value"])


def read_all_modes(path) -> dict[str, float]:
    values = read_key_values(path)
    if values is None:
        raise FileNotFoundError(path)
    return {key: float(value) for key, value in values.items() if "ModeIndex" in key}


def read_native_0d(path):
    with Path(path).open("r") as source:
        first_line = source.readline()
    return float(first_line) if first_line else None


def read_mode_recognition(directory):
    # Optional legacy feature: keep utils unchanged and load it only on demand.
    from utils.mode_util_sample import allModesResult

    return allModesResult(directory)

"""Mesh convergence analysis for scalar CST post-processing results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path
from typing import Callable, Mapping


@dataclass(frozen=True, slots=True)
class MeshConvergenceSettings:
    enabled: bool = False
    start: int = 10
    stop: int = 30
    step: int = 5
    tolerance: float = 0.01
    consecutive: int = 2

    def __post_init__(self):
        if self.start < 1 or self.stop < self.start or self.step < 1:
            raise ValueError("Mesh 收敛范围必须是递增的正整数")
        if not 0 < self.tolerance < 1:
            raise ValueError("Mesh 收敛容差必须在 0 和 1 之间")
        if self.consecutive < 1:
            raise ValueError("Mesh 连续稳定次数必须为正整数")

    @property
    def levels(self) -> tuple[int, ...]:
        values = list(range(self.start, self.stop + 1, self.step))
        if values[-1] != self.stop:
            values.append(self.stop)
        return tuple(values)


@dataclass(frozen=True, slots=True)
class MeshConvergencePoint:
    cells_per_wavelength: int
    values: Mapping[str, float]
    relative_changes: Mapping[str, float]
    maximum_relative_change: float | None
    stable: bool


@dataclass(frozen=True, slots=True)
class MeshConvergenceReport:
    settings: MeshConvergenceSettings
    points: tuple[MeshConvergencePoint, ...]
    converged: bool
    recommended_cells_per_wavelength: int | None

    def write(self, directory: str | Path) -> tuple[Path, Path]:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / "mesh_convergence.json"
        csv_path = directory / "mesh_convergence.csv"
        json_path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        names = sorted({name for point in self.points for name in point.values})
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=(
                    ["cells_per_wavelength", "maximum_relative_change", "stable"]
                    + names
                    + [f"relative_change:{name}" for name in names]
                ),
            )
            writer.writeheader()
            for point in self.points:
                row = {
                    "cells_per_wavelength": point.cells_per_wavelength,
                    "maximum_relative_change": point.maximum_relative_change,
                    "stable": point.stable,
                }
                row.update(point.values)
                row.update(
                    {
                        f"relative_change:{name}": point.relative_changes.get(name)
                        for name in names
                    }
                )
                writer.writerow(row)
        return json_path, csv_path


class MeshConvergenceAnalyzer:
    def __init__(self, settings: MeshConvergenceSettings):
        self.settings = settings

    @staticmethod
    def _relative_change(previous: float, current: float) -> float:
        scale = max(abs(previous), abs(current), 1e-30)
        return abs(current - previous) / scale

    def run(
        self, evaluate: Callable[[int], Mapping[str, float]]
    ) -> MeshConvergenceReport:
        points = []
        previous = None
        stable_count = 0
        recommendation = None
        for level in self.settings.levels:
            values = {name: float(value) for name, value in evaluate(level).items()}
            if not values or not all(math.isfinite(value) for value in values.values()):
                raise ValueError(f"Mesh {level} 的后处理结果为空或不是有限数")
            if previous is None:
                changes = {}
                maximum = None
                stable = False
            else:
                if values.keys() != previous.keys():
                    raise ValueError("不同 Mesh 级别返回的后处理结果名称不一致")
                changes = {
                    name: self._relative_change(previous[name], value)
                    for name, value in values.items()
                }
                maximum = max(changes.values())
                stable = maximum <= self.settings.tolerance
            stable_count = stable_count + 1 if stable else 0
            points.append(
                MeshConvergencePoint(level, values, changes, maximum, stable)
            )
            previous = values
            if stable_count >= self.settings.consecutive:
                recommendation = level
                break
        return MeshConvergenceReport(
            self.settings,
            tuple(points),
            recommendation is not None,
            recommendation,
        )


def scalar_postprocess_values(result: Mapping) -> dict[str, float]:
    """Flatten one-mode worker output into named scalar convergence metrics."""
    postprocess = result.get("PostProcessResult")
    if not isinstance(postprocess, list):
        raise ValueError("CST 收敛任务未返回后处理列表")
    values = {}
    for item in postprocess:
        name = item.get("resultName")
        value = item.get("value")
        if isinstance(value, dict):
            if len(value) != 1:
                raise ValueError(f"后处理 {name!r} 不是单模标量结果")
            value = next(iter(value.values()))
        if not isinstance(name, str) or not name or isinstance(value, bool):
            raise ValueError("收敛分析只支持具名标量后处理结果")
        values[name] = float(value)
    return values

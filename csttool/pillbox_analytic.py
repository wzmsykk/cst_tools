"""Analytic Pillbox reference model and a manager-driven radius search."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .cstmanager import SimulationTask


SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
TM010_FIRST_BESSEL_ROOT = 2.404_825_557_695_773


def tm010_frequency_mhz(radius_mm: float) -> float:
    """Return the ideal vacuum cylindrical-cavity TM010 frequency."""
    radius_mm = float(radius_mm)
    if not math.isfinite(radius_mm) or radius_mm <= 0:
        raise ValueError("Pillbox radius must be a positive finite value")
    return (
        SPEED_OF_LIGHT_M_PER_S
        * TM010_FIRST_BESSEL_ROOT
        / (2.0 * math.pi * radius_mm * 1_000.0)
    )


def tm010_radius_mm(frequency_mhz: float) -> float:
    """Return the ideal radius corresponding to a TM010 frequency."""
    frequency_mhz = float(frequency_mhz)
    if not math.isfinite(frequency_mhz) or frequency_mhz <= 0:
        raise ValueError("Pillbox frequency must be a positive finite value")
    return (
        SPEED_OF_LIGHT_M_PER_S
        * TM010_FIRST_BESSEL_ROOT
        / (2.0 * math.pi * frequency_mhz * 1_000.0)
    )


@dataclass(frozen=True, slots=True)
class PillboxSample:
    radius_mm: float
    frequency_mhz: float
    target_error_mhz: float


@dataclass(frozen=True, slots=True)
class PillboxOptimizationResult:
    best: PillboxSample
    iterations: int
    evaluations: int


class PillboxRadiusBatchOptimizer:
    """Narrow a radius bracket using independent manager batch tasks."""

    def __init__(
        self,
        manager: Any,
        *,
        target_frequency_mhz: float,
        radius_bounds_mm: tuple[float, float],
        samples_per_iteration: int = 9,
        max_iterations: int = 6,
        frequency_tolerance_mhz: float = 0.01,
        task_retry_count: int = 1,
    ) -> None:
        lower, upper = map(float, radius_bounds_mm)
        if not 0 < lower < upper:
            raise ValueError("radius bounds must be positive and increasing")
        if samples_per_iteration < 3:
            raise ValueError("samples_per_iteration must be at least 3")
        if max_iterations < 1 or frequency_tolerance_mhz <= 0:
            raise ValueError("iteration limit and tolerance must be positive")
        if task_retry_count < 0:
            raise ValueError("task_retry_count must be non-negative")
        self.manager = manager
        self.target = float(target_frequency_mhz)
        if not math.isfinite(self.target) or self.target <= 0:
            raise ValueError("target frequency must be positive and finite")
        self.lower = lower
        self.upper = upper
        self.samples_per_iteration = int(samples_per_iteration)
        self.max_iterations = int(max_iterations)
        self.tolerance = float(frequency_tolerance_mhz)
        self.task_retry_count = int(task_retry_count)

    def optimize(self) -> PillboxOptimizationResult:
        lower = self.lower
        upper = self.upper
        best: PillboxSample | None = None
        evaluations = 0

        for iteration in range(1, self.max_iterations + 1):
            step = (upper - lower) / (self.samples_per_iteration - 1)
            radii = [lower + index * step for index in range(self.samples_per_iteration)]
            tasks = [
                SimulationTask(
                    params={"R": radius},
                    job_name=f"pillbox-r-{radius:.9f}",
                    retry_count=self.task_retry_count,
                )
                for radius in radii
            ]
            results = self.manager.run_batch(tasks)
            if len(results) != len(tasks):
                raise RuntimeError("Pillbox batch returned an unexpected result count")
            samples = [
                self._sample(radius, result)
                for radius, result in zip(radii, results, strict=True)
            ]
            evaluations += len(samples)
            candidate = min(samples, key=lambda item: item.target_error_mhz)
            if best is None or candidate.target_error_mhz < best.target_error_mhz:
                best = candidate
            if best.target_error_mhz <= self.tolerance:
                return PillboxOptimizationResult(best, iteration, evaluations)

            best_index = samples.index(candidate)
            left_index = max(0, best_index - 1)
            right_index = min(len(samples) - 1, best_index + 1)
            if left_index == right_index:
                raise RuntimeError("Pillbox search cannot narrow the radius bracket")
            lower = samples[left_index].radius_mm
            upper = samples[right_index].radius_mm

        assert best is not None
        return PillboxOptimizationResult(best, self.max_iterations, evaluations)

    def _sample(self, radius: float, result: dict[str, Any]) -> PillboxSample:
        if result.get("TaskStatus") != "Success":
            raise RuntimeError(result.get("FailureReport") or "Pillbox task failed")
        postprocess = result.get("PostProcessResult")
        if not isinstance(postprocess, list):
            raise ValueError("Pillbox task returned no postprocess result list")
        frequency_values = [
            item.get("value")
            for item in postprocess
            if str(item.get("resultName", "")).casefold() == "frequency"
        ]
        if len(frequency_values) != 1:
            raise ValueError("Pillbox task must return exactly one frequency")
        frequency = float(frequency_values[0])
        if not math.isfinite(frequency) or frequency <= 0:
            raise ValueError("Pillbox task returned an invalid frequency")
        return PillboxSample(radius, frequency, abs(frequency - self.target))

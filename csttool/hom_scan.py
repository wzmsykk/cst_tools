"""Bounded single-mode interval scanner for HOM eigenmode searches."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
from typing import Callable, Iterable


class ScanConfigurationError(ValueError):
    pass


class IncompleteScanError(RuntimeError):
    def __init__(self, report: "ScanReport"):
        self.report = report
        failed = ", ".join(f"[{item.lo}, {item.hi}]" for item in report.failed)
        super().__init__(f"HOM scan has failed intervals: {failed}")


@dataclass(frozen=True, slots=True, order=True)
class ScanInterval:
    lo: float
    hi: float


@dataclass(frozen=True, slots=True)
class ScanPolicy:
    start: float
    initial_stop: float
    stop: float
    window_width: float = 50.0
    requested_modes: int = 1
    frequency_abs_tol: float = 1e-6
    frequency_rel_tol: float = 1e-9
    max_interval_attempts: int = 2
    max_solver_calls: int = 10000

    def __post_init__(self) -> None:
        finite = (
            self.start,
            self.initial_stop,
            self.stop,
            self.window_width,
            self.frequency_abs_tol,
        )
        if not all(math.isfinite(value) for value in finite):
            raise ScanConfigurationError("scan frequencies must be finite")
        if not self.start < self.initial_stop <= self.stop:
            raise ScanConfigurationError("expected start < initial_stop <= stop")
        if self.window_width <= 0 or self.frequency_abs_tol <= 0:
            raise ScanConfigurationError("window width and tolerance must be positive")
        if self.requested_modes != 1:
            raise ScanConfigurationError("single-mode scan requires requested_modes == 1")
        if self.max_interval_attempts < 1 or self.max_solver_calls < 1:
            raise ScanConfigurationError("scan safety limits must be positive")

    def initial_intervals(self) -> list[ScanInterval]:
        return [ScanInterval(self.start, self.initial_stop)]


@dataclass(frozen=True, slots=True)
class SolveRequest:
    interval: ScanInterval
    solve_lo: float
    solve_hi: float
    requested_modes: int


@dataclass(frozen=True, slots=True)
class ModeResult:
    mode_index: int
    frequency: float
    values: dict[str, float]


@dataclass(slots=True)
class ScanReport:
    modes: list[ModeResult] = field(default_factory=list)
    completed: list[ScanInterval] = field(default_factory=list)
    empty: list[ScanInterval] = field(default_factory=list)
    failed: list[ScanInterval] = field(default_factory=list)
    failure_reasons: dict[str, str] = field(default_factory=dict)
    solver_calls: int = 0


CheckpointCallback = Callable[[ScanReport, list[ScanInterval]], None]
SolveCallback = Callable[[SolveRequest], Iterable[ModeResult]]


class AdaptiveHomScanner:
    """Scan a narrow interval for one mode, then continue above that mode."""

    def __init__(self, policy: ScanPolicy):
        self.policy = policy

    def run(
        self,
        solve: SolveCallback,
        *,
        pending: Iterable[ScanInterval] | None = None,
        report: ScanReport | None = None,
        checkpoint: CheckpointCallback | None = None,
    ) -> ScanReport:
        report = report or ScanReport()
        queue = list(pending if pending is not None else self.policy.initial_intervals())

        while queue:
            interval = queue.pop(0)
            if not interval.lo < interval.hi:
                raise ScanConfigurationError("scan interval did not make progress")

            modes = None
            last_error = None
            for _attempt in range(self.policy.max_interval_attempts):
                if report.solver_calls >= self.policy.max_solver_calls:
                    report.failed.append(interval)
                    self._checkpoint(checkpoint, report, queue)
                    raise IncompleteScanError(report)
                report.solver_calls += 1
                request = SolveRequest(interval, interval.lo, interval.hi, 1)
                try:
                    modes = self._validate_modes(solve(request))
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    modes = None
                    continue
                break

            if modes is None:
                report.failed.append(interval)
                report.failure_reasons[self._interval_key(interval)] = (
                    last_error or "unknown solver failure"
                )
                self._checkpoint(checkpoint, report, queue)
                continue

            if modes:
                mode = modes[0]
                if self._already_accepted(report.modes, mode.frequency):
                    report.failed.append(interval)
                    report.failure_reasons[self._interval_key(interval)] = (
                        "solver returned an already accepted frequency; "
                        "possible degenerate mode or boundary stall"
                    )
                    self._checkpoint(checkpoint, report, queue)
                    continue
                if not self._inside(interval, mode.frequency):
                    report.failed.append(interval)
                    report.failure_reasons[self._interval_key(interval)] = (
                        f"returned frequency {mode.frequency} is outside the solve interval"
                    )
                    self._checkpoint(checkpoint, report, queue)
                    continue
                report.modes.append(mode)
                report.modes.sort(key=lambda item: item.frequency)
                next_lo = max(
                    math.nextafter(mode.frequency, math.inf),
                    mode.frequency + self.policy.frequency_abs_tol,
                )
            else:
                report.empty.append(interval)
                next_lo = interval.hi

            report.completed.append(interval)
            if next_lo < self.policy.stop:
                next_hi = min(next_lo + self.policy.window_width, self.policy.stop)
                if next_hi <= next_lo:
                    raise ScanConfigurationError("scan interval did not make progress")
                queue.insert(0, ScanInterval(next_lo, next_hi))
            self._checkpoint(checkpoint, report, queue)

        if report.failed:
            raise IncompleteScanError(report)
        return report

    def _inside(self, interval: ScanInterval, frequency: float) -> bool:
        return (
            interval.lo <= frequency <= interval.hi
            or math.isclose(
                frequency,
                interval.lo,
                abs_tol=self.policy.frequency_abs_tol,
                rel_tol=self.policy.frequency_rel_tol,
            )
            or math.isclose(
                frequency,
                interval.hi,
                abs_tol=self.policy.frequency_abs_tol,
                rel_tol=self.policy.frequency_rel_tol,
            )
        )

    def _already_accepted(self, modes: list[ModeResult], frequency: float) -> bool:
        return any(
            math.isclose(
                item.frequency,
                frequency,
                abs_tol=self.policy.frequency_abs_tol,
                rel_tol=self.policy.frequency_rel_tol,
            )
            for item in modes
        )

    @staticmethod
    def _interval_key(interval: ScanInterval) -> str:
        return f"{interval.lo:.17g}:{interval.hi:.17g}"

    @staticmethod
    def _validate_modes(modes: Iterable[ModeResult]) -> list[ModeResult]:
        validated = list(modes)
        if len(validated) > 1:
            raise ValueError("single-mode solve returned more than one mode")
        for mode in validated:
            if mode.mode_index < 1 or not math.isfinite(mode.frequency):
                raise ValueError("invalid mode identity or frequency")
            if not mode.values or any(
                not math.isfinite(value) for value in mode.values.values()
            ):
                raise ValueError("mode result is incomplete or non-finite")
        return validated

    @staticmethod
    def _checkpoint(
        callback: CheckpointCallback | None,
        report: ScanReport,
        pending: list[ScanInterval],
    ) -> None:
        if callback is not None:
            callback(report, list(pending))


class ScanCheckpointStore:
    SCHEMA_VERSION = 2

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(
        self,
        policy: ScanPolicy,
        project_fingerprint: dict,
        report: ScanReport,
        pending: list[ScanInterval],
    ) -> None:
        document = {
            "schemaVersion": self.SCHEMA_VERSION,
            "policy": asdict(policy),
            "projectFingerprint": project_fingerprint,
            "pending": [asdict(item) for item in pending],
            "report": {
                "modes": [asdict(item) for item in report.modes],
                "completed": [asdict(item) for item in report.completed],
                "empty": [asdict(item) for item in report.empty],
                "failed": [asdict(item) for item in report.failed],
                "failure_reasons": report.failure_reasons,
                "solver_calls": report.solver_calls,
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def load(self, policy: ScanPolicy, project_fingerprint: dict):
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if document.get("schemaVersion") != self.SCHEMA_VERSION:
            raise ScanConfigurationError("unsupported HOM checkpoint version")
        if document.get("policy") != asdict(policy):
            raise ScanConfigurationError("checkpoint scan policy does not match")
        if document.get("projectFingerprint") != project_fingerprint:
            raise ScanConfigurationError("checkpoint project does not match")
        raw = document["report"]
        report = ScanReport(
            modes=[ModeResult(**item) for item in raw["modes"]],
            completed=[ScanInterval(**item) for item in raw["completed"]],
            empty=[ScanInterval(**item) for item in raw["empty"]],
            failed=[ScanInterval(**item) for item in raw["failed"]],
            failure_reasons=dict(raw.get("failure_reasons", {})),
            solver_calls=raw["solver_calls"],
        )
        pending = [ScanInterval(**item) for item in document["pending"]]
        return report, pending

"""Bounded single-mode interval scanner for HOM eigenmode searches."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import logging
import os
from pathlib import Path
from typing import Callable, Iterable


class ScanConfigurationError(ValueError):
    pass


class RecoverableSolveError(RuntimeError):
    """Actual solver failure, not malformed output, communication or shutdown."""


class IncompleteScanError(RuntimeError):
    def __init__(self, report: "ScanReport"):
        self.report = report
        failed = "; ".join(
            f"[{item.lo}, {item.hi}]: "
            + report.failure_reasons.get(f"{item.lo:.17g}:{item.hi:.17g}", "unknown failure")
            for item in report.failed
        )
        super().__init__(f"HOM scan has failed intervals: {failed}")


class ScanInterrupted(RuntimeError):
    def __init__(self, report: "ScanReport", pending: list["ScanInterval"]):
        self.report = report
        self.pending = pending
        super().__init__("HOM scan stopped at a recoverable checkpoint")


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
    failure_recovery: bool = False
    base_mesh_cells: int | None = None
    mesh_retry_factor: float = 1.5
    max_probe_expansions: int = 3

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
        if not math.isfinite(self.mesh_retry_factor) or self.mesh_retry_factor <= 1:
            raise ScanConfigurationError("mesh retry factor must exceed one")
        if self.base_mesh_cells is not None and (type(self.base_mesh_cells) is not int or self.base_mesh_cells < 1):
            raise ScanConfigurationError("base mesh cells must be positive")
        if type(self.max_probe_expansions) is not int or not 1 <= self.max_probe_expansions <= 8:
            raise ScanConfigurationError("probe expansions must be between one and eight")
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
    mesh_cells: int | None = None
    recovery_phase: str = "normal"


@dataclass(frozen=True, slots=True)
class ModeResult:
    mode_index: int
    frequency: float
    values: dict[str, float]
    project_snapshot: str | None = None
    task_name: str = ""
    task_id: str = ""
    mesh_cells_per_wavelength: int | None = None


@dataclass(slots=True)
class ScanReport:
    modes: list[ModeResult] = field(default_factory=list)
    completed: list[ScanInterval] = field(default_factory=list)
    empty: list[ScanInterval] = field(default_factory=list)
    failed: list[ScanInterval] = field(default_factory=list)
    failure_reasons: dict[str, str] = field(default_factory=dict)
    solver_calls: int = 0
    adopted_task_ids: list[str] = field(default_factory=list)
    probed: list[ScanInterval] = field(default_factory=list)
    active_mesh_cells: int | None = None
    recovery_states: dict = field(default_factory=dict)
    recovery_events: list[dict] = field(default_factory=list)


class TaskModeResults(list):
    """A successful solver task, including one yielding no modes."""
    def __init__(self, modes, task_id=''):
        super().__init__(modes)
        self.task_id = task_id


CheckpointCallback = Callable[[ScanReport, list[ScanInterval]], None]
SolveCallback = Callable[[SolveRequest], Iterable[ModeResult]]


class AdaptiveHomScanner:
    """Scan a narrow interval for one mode, then continue above that mode."""

    def __init__(self, policy: ScanPolicy, logger=None):
        self.policy = policy
        self.logger = logger or logging.getLogger(__name__)

    def run(
        self,
        solve: SolveCallback,
        *,
        pending: Iterable[ScanInterval] | None = None,
        report: ScanReport | None = None,
        checkpoint: CheckpointCallback | None = None,
        should_stop: Callable[[], bool] | None = None,
        bounded_intervals: bool = False,
    ) -> ScanReport:
        report = report or ScanReport()
        queue = list(pending if pending is not None else self.policy.initial_intervals())

        limits = [item.hi if bounded_intervals else self.policy.stop for item in queue]
        while queue:
            if should_stop is not None and should_stop():
                self._checkpoint(checkpoint, report, queue)
                raise ScanInterrupted(report, list(queue))
            interval = queue.pop(0)
            scan_limit = limits.pop(0)
            # Persist the in-flight interval before any solver side effect.
            self._checkpoint(checkpoint, report, [interval] + queue)
            if not interval.lo < interval.hi:
                raise ScanConfigurationError("scan interval did not make progress")

            modes = None
            last_error = None
            recovery_key = self._interval_key(interval)
            recovering = self.policy.failure_recovery and recovery_key in report.recovery_states
            for _attempt in range(self.policy.max_interval_attempts):
                if should_stop is not None and should_stop():
                    pending_intervals = [interval] + queue
                    self._checkpoint(checkpoint, report, pending_intervals)
                    raise ScanInterrupted(report, pending_intervals)
                if recovering:
                    modes, task_id, interval, last_error = self._recover_interval(
                        interval, solve, report, queue, checkpoint, should_stop)
                    break
                if report.solver_calls >= self.policy.max_solver_calls:
                    report.failed.append(interval)
                    report.failure_reasons[self._interval_key(interval)] = "solver call limit reached"
                    self._checkpoint(checkpoint, report, queue)
                    raise IncompleteScanError(report)
                report.solver_calls += 1
                request = SolveRequest(interval, interval.lo, interval.hi, 1,
                    self.policy.base_mesh_cells if self.policy.failure_recovery else None)
                self._checkpoint(checkpoint, report, [interval] + queue)
                try:
                    returned = solve(request)
                    task_id = getattr(returned, 'task_id', '')
                    modes = self._validate_modes(returned)
                    report.active_mesh_cells = request.mesh_cells
                except Exception as exc:
                    if should_stop is not None and should_stop():
                        pending_intervals = [interval] + queue
                        self._checkpoint(checkpoint, report, pending_intervals)
                        raise ScanInterrupted(report, pending_intervals) from exc
                    if self.policy.failure_recovery and isinstance(exc, RecoverableSolveError):
                        modes, task_id, interval, last_error = self._recover_interval(
                            interval, solve, report, queue, checkpoint, should_stop)
                        break
                    last_error = f"{type(exc).__name__}: {exc}"
                    self.logger.warning(
                        "HOM_SOLVE_INVALID_RESULT 区间=[%.12g, %.12g] MHz 尝试=%d/%d 原因=%s",
                        interval.lo, interval.hi, _attempt + 1,
                        self.policy.max_interval_attempts, last_error,
                    )
                    modes = None
                    continue
                for candidate in modes:
                    self.logger.info(
                        "HOM_SOLVE_RESULT 区间=[%.12g, %.12g] MHz 返回频率=%.12g MHz 后处理={%s}",
                        interval.lo, interval.hi, candidate.frequency,
                        self._format_results(candidate),
                    )
                if modes and self._already_accepted(report.modes, modes[0].frequency):
                    last_error = "solver returned an already accepted frequency; possible degenerate mode or boundary stall"
                    modes = None
                    continue
                if modes and not self._at_or_above_lower_bound(interval, modes[0].frequency):
                    frequency = modes[0].frequency
                    last_error = f"returned frequency {frequency} is below the search lower bound {interval.lo}"
                    modes = None
                    continue
                if modes and modes[0].frequency > interval.hi:
                    frequency = modes[0].frequency
                    last_error = f"returned frequency {frequency} is outside the solve interval; expanded-window confirmation required"
                    modes = None
                    if _attempt + 1 < self.policy.max_interval_attempts:
                        expanded_hi = max(
                            interval.hi + self.policy.window_width,
                            frequency + self.policy.window_width,
                        )
                        self.logger.info(
                            "HOM_WINDOW_EXPAND 首次返回频率=%.12g MHz 超出窗口=[%.12g, %.12g] MHz；扩大上限至 %.12g MHz 重算，结果待确认 重试=%d/%d",
                            frequency, interval.lo, interval.hi, expanded_hi,
                            _attempt + 2, self.policy.max_interval_attempts,
                        )
                        interval = ScanInterval(interval.lo, expanded_hi)
                    continue
                break

            if modes is None:
                report.failed.append(interval)
                report.failure_reasons[self._interval_key(interval)] = (
                    last_error or "unknown solver failure"
                )
                self.logger.warning(
                    "HOM_FAILED_INTERVAL lo=%.12g hi=%.12g attempts=%d reason=%s；记录未确认区间，继续向后扫描",
                    interval.lo, interval.hi, self.policy.max_interval_attempts,
                    report.failure_reasons[self._interval_key(interval)],
                )
                next_lo = interval.hi

            elif modes:
                mode = modes[0]
                if mode.frequency > self.policy.stop:
                    self.logger.info(
                        "HOM_SCAN_LIMIT_REACHED 下一模式频率=%.12g MHz 已超过扫描上限=%.12g MHz，正常结束",
                        mode.frequency, self.policy.stop,
                    )
                    next_lo = self.policy.stop
                else:
                    report.modes.append(mode)
                    report.modes.sort(key=lambda item: item.frequency)
                    self.logger.info(
                        "HOM_MODE_ACCEPTED 扫描模态=%d 求解器模态=%d 频率=%.12g MHz 后处理={%s} 任务=%s task_id=%s 存档=%s",
                        report.modes.index(mode) + 1, mode.mode_index, mode.frequency,
                        self._format_results(mode), mode.task_name or "未记录",
                        mode.task_id or "未记录", mode.project_snapshot or "未记录",
                    )
                    next_lo = max(
                        math.nextafter(mode.frequency, math.inf),
                        mode.frequency + self.policy.frequency_abs_tol,
                    )
            else:
                report.empty.append(interval)
                self.logger.info("HOM_INTERVAL_EMPTY 区间=[%.12g, %.12g] MHz 无模态", interval.lo, interval.hi)
                next_lo = interval.hi

            if modes is not None:
                report.completed.append(interval)
                if task_id and task_id not in report.adopted_task_ids:
                    report.adopted_task_ids.append(task_id)
            if next_lo < scan_limit:
                next_hi = min(next_lo + self.policy.window_width, scan_limit)
                if next_hi <= next_lo:
                    raise ScanConfigurationError("scan interval did not make progress")
                queue.insert(0, ScanInterval(next_lo, next_hi))
                limits.insert(0, scan_limit)
            self._checkpoint(checkpoint, report, queue)

            if should_stop is not None and should_stop():
                raise ScanInterrupted(report, list(queue))

        return report

    def _recover_interval(self, original, solve, report, queue, checkpoint, should_stop):
        key = self._interval_key(original)
        state = report.recovery_states.setdefault(key, {
            'phase': 'mesh' if self.policy.base_mesh_cells is not None else 'probe', 'level': 1})
        if (not isinstance(state, dict) or not isinstance(state.get('phase'), str) or state.get('phase') not in {'mesh', 'probe', 'confirm'}
                or type(state.get('level')) is not int
                or not 1 <= state['level'] <= self.policy.max_probe_expansions + (state.get('phase') == 'probe')):
            raise ScanConfigurationError('invalid recovery checkpoint phase or level')
        if state['phase'] == 'mesh' and self.policy.base_mesh_cells is None:
            raise ScanConfigurationError('mesh recovery requires a known fixed baseline density')
        if state['phase'] == 'confirm':
            try:
                candidate = ModeResult(**state['candidate'])
                self._validate_modes([candidate])
                upper = state['probe_hi']
                if not math.isfinite(upper) or not original.lo <= candidate.frequency <= upper:
                    raise ValueError('candidate outside probe bounds')
            except (KeyError, TypeError, ValueError) as exc:
                raise ScanConfigurationError('invalid recovery candidate evidence') from exc
        error = state.get('last_error', 'recovery exhausted')
        while state['level'] <= self.policy.max_probe_expansions:
            if should_stop is not None and should_stop():
                self._checkpoint(checkpoint, report, [original] + queue)
                raise ScanInterrupted(report, [original] + queue)
            if report.solver_calls >= self.policy.max_solver_calls:
                report.failed.append(original)
                report.failure_reasons[key] = 'solver call limit reached during recovery'
                self._checkpoint(checkpoint, report, queue)
                raise IncompleteScanError(report)
            phase = state['phase']
            base = self.policy.base_mesh_cells
            lo, hi = original.lo, original.hi
            if phase == 'mesh':
                cells = max(base + 1, math.ceil(base * self.policy.mesh_retry_factor))
            else:
                cells = base  # Restore original density before probing/confirmation.
                hi = original.lo + (original.hi - original.lo) * 2 ** state['level']
                if phase == 'confirm':
                    frequency = state['candidate']['frequency']
                    lo = max(original.lo, frequency - self.policy.window_width / 2)
                    hi = lo + self.policy.window_width
            request = SolveRequest(original, lo, hi, 1, cells, phase)
            if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
                error = 'invalid or overflowing recovery frequency bounds'
                break
            report.solver_calls += 1
            self._checkpoint(checkpoint, report, [original] + queue)
            self.logger.info('HOM_RECOVERY_STEP phase=%s original=[%g,%g] solve=[%g,%g] cell=%s level=%s',
                             phase, original.lo, original.hi, lo, hi, cells, state['level'],
                             extra={'event': 'HOM_RECOVERY_STEP', 'phase': 'hom-recovery',
                                    'recovery_phase': phase, 'solve_lo': lo, 'solve_hi': hi,
                                    'mesh_cells': cells, 'probe_level': state['level']})
            try:
                returned = solve(request)
                task_id = getattr(returned, 'task_id', '')
                modes = self._validate_modes(returned)
                if modes:
                    frequency = modes[0].frequency
                    if frequency > hi:
                        raise RecoverableSolveError('next mode lies above recovery probe upper bound')
                    if frequency < lo or self._already_accepted(report.modes, frequency):
                        raise ValueError('recovery result is below bounds or already accepted')
                if phase == 'confirm' and not modes:
                    raise ValueError('narrow confirmation did not reproduce a mode')
            except (ScanInterrupted, IncompleteScanError):
                raise
            except Exception as exc:
                if should_stop is not None and should_stop():
                    self._checkpoint(checkpoint, report, [original] + queue)
                    raise ScanInterrupted(report, [original] + queue) from exc
                error = f'{type(exc).__name__}: {exc}'
                state['last_error'] = error
                self.logger.warning('HOM恢复步骤失败 | step=%s lo=%g hi=%g reason=%s', phase, lo, hi, error,
                    extra={'event': 'HOM_RECOVERY_FAILED', 'phase': 'hom-recovery', 'recovery_phase': phase,
                           'solve_lo': lo, 'solve_hi': hi, 'mesh_cells': cells, 'reason': error})
                report.recovery_events.append(dict(interval=asdict(original), phase=phase,
                    lo=lo, hi=hi, mesh_cells=cells, outcome='failed', reason=error))
                # Communication/invalid postprocessing cannot prove emptiness.
                if not isinstance(exc, RecoverableSolveError):
                    break
                state['phase'] = 'probe'
                if phase != 'mesh':
                    state['level'] += 1
                state.pop('candidate', None)
                self._checkpoint(checkpoint, report, [original] + queue)
                continue
            self.logger.info('HOM恢复步骤结果已核验 | step=%s task=%s modes=%s', phase, task_id,
                [m.frequency for m in modes], extra={'event': 'HOM_RECOVERY_RESULT', 'phase': 'hom-recovery',
                'recovery_phase': phase, 'task_id': task_id, 'mesh_cells': cells,
                'frequencies': [m.frequency for m in modes]})
            report.active_mesh_cells = cells
            if phase == 'probe':
                report.probed.append(ScanInterval(lo, hi))
            report.recovery_events.append(dict(interval=asdict(original), phase=phase,
                lo=lo, hi=hi, mesh_cells=cells, outcome='success', task_id=task_id,
                frequencies=[m.frequency for m in modes]))
            if phase == 'mesh' and not modes:
                # Emptiness on a different density is not an empty baseline window.
                if task_id and task_id not in report.adopted_task_ids:
                    report.adopted_task_ids.append(task_id)
                state['phase'] = 'probe'
                self._checkpoint(checkpoint, report, [original] + queue)
                continue
            if phase == 'probe' and modes:
                # Consume the successful probe as evidence, never as a final mode.
                if task_id and task_id not in report.adopted_task_ids:
                    report.adopted_task_ids.append(task_id)
                state.update(phase='confirm', candidate=asdict(modes[0]), probe_hi=hi)
                self._checkpoint(checkpoint, report, [original] + queue)
                continue
            effective = original
            if phase == 'confirm':
                candidate = state['candidate']['frequency']
                if abs(modes[0].frequency - candidate) > max(self.policy.frequency_abs_tol,
                                                           .05 * abs(candidate)):
                    error = 'narrow confirmation differs from probe by more than five percent'
                    break
                if candidate > original.hi and modes[0].frequency > original.hi:
                    report.empty.append(original)
                    self.logger.info('原区间按扩窗首模与窄窗确认结果判空 | lo=%g hi=%g next=%g',
                        original.lo, original.hi, modes[0].frequency,
                        extra={'event': 'HOM_RECOVERY_EMPTY', 'phase': 'hom-recovery',
                               'lo': original.lo, 'hi': original.hi, 'next_frequency': modes[0].frequency})
                    report.recovery_events.append(dict(interval=asdict(original), phase='empty-inferred',
                        outcome='confirmed', evidence='successful-lowest-mode-probe-and-narrow-confirmation',
                        probe_frequency=candidate, frequency=modes[0].frequency))
                effective = ScanInterval(original.lo, state['probe_hi'])
            report.recovery_states.pop(key, None)
            return modes, task_id, effective, None
        report.recovery_states.pop(key, None)
        return None, '', original, error

    @staticmethod
    def _format_results(mode: ModeResult) -> str:
        return ", ".join(f"{key}={value:.12g}" for key, value in mode.values.items())

    def _at_or_above_lower_bound(self, interval: ScanInterval, frequency: float) -> bool:
        return (
            frequency >= interval.lo
            or math.isclose(
                frequency,
                interval.lo,
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
            if mode.mode_index < 1:
                raise ValueError("invalid mode identity")
            if not math.isfinite(mode.frequency):
                raise ValueError("mode frequency is non-finite")
            if mode.frequency <= 0:
                raise ValueError(
                    f"invalid mode frequency {mode.frequency}: expected a positive frequency; "
                    "mode or postprocess result may be unavailable"
                )
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
    SCHEMA_VERSION = 4

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.pending_bounded = False

    def save(
        self,
        policy: ScanPolicy,
        project_fingerprint: dict,
        report: ScanReport,
        pending: list[ScanInterval],
        snapshot_path: str | Path | None = None,
        bounded_intervals: bool = False,
    ) -> None:
        snapshot = self._encode_snapshot(snapshot_path)
        document = {
            "coverage": {
                "confirmed_frontier": (min([item.lo for item in pending + report.failed])
                     if pending or report.failed else min(policy.stop,
                        max([item.hi for item in report.completed], default=policy.start))),
                "calculated_upper": max([item.hi for item in report.completed + report.probed], default=policy.start),
            },
            "schemaVersion": self.SCHEMA_VERSION,
            "policy": asdict(policy),
            "projectFingerprint": project_fingerprint,
            "pending": [asdict(item) for item in pending],
            "pendingBounded": bounded_intervals,
            "confirmedSnapshot": snapshot,
            "report": {
                "modes": [asdict(item) for item in report.modes],
                "completed": [asdict(item) for item in report.completed],
                "empty": [asdict(item) for item in report.empty],
                "probed": [asdict(item) for item in report.probed],
                "failed": [asdict(item) for item in report.failed],
                "failure_reasons": report.failure_reasons,
                "solver_calls": report.solver_calls,
                "adopted_task_ids": report.adopted_task_ids,
                "active_mesh_cells": report.active_mesh_cells,
                "recovery_states": report.recovery_states,
                "recovery_events": report.recovery_events,
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from .configuration import write_json_atomic
        write_json_atomic(self.path, document)

    def _encode_snapshot(self, snapshot_path: str | Path | None):
        if snapshot_path is None:
            return None
        path = Path(snapshot_path).resolve()
        if not path.is_file() or path.stat().st_size == 0:
            raise ScanConfigurationError(
                f"confirmed CST snapshot is unavailable: {path}"
            )
        return {
            "path": os.path.relpath(path, self.path.parent.resolve()),
            "size": path.stat().st_size,
            "sha256": self._sha256(path),
        }

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _load_document(self, policy: ScanPolicy, project_fingerprint: dict):
        from .configuration import read_json
        document = read_json(self.path)
        if document.get("schemaVersion") not in (3, self.SCHEMA_VERSION):
            raise ScanConfigurationError("unsupported HOM checkpoint version")
        stored_policy = dict(document.get("policy") or {})
        # Old v3 checkpoints did not carry the new recovery controls; preserve
        # their scan bounds/identity while filling only these additive fields.
        if document.get('schemaVersion') == 3:
            for name in ('failure_recovery', 'base_mesh_cells', 'mesh_retry_factor', 'max_probe_expansions'):
                stored_policy.setdefault(name, getattr(policy, name))
        if stored_policy != asdict(policy):
            raise ScanConfigurationError("checkpoint scan policy does not match")
        if document.get("projectFingerprint") != project_fingerprint:
            raise ScanConfigurationError("checkpoint project does not match")
        self.pending_bounded = document.get("pendingBounded", False)
        if type(self.pending_bounded) is not bool:
            raise ScanConfigurationError("invalid pendingBounded checkpoint flag")
        raw = document["report"]
        if document.get('schemaVersion') == self.SCHEMA_VERSION:
            if not isinstance(raw, dict) or not {'recovery_states', 'recovery_events', 'probed',
                                                'active_mesh_cells'}.issubset(raw):
                raise ScanConfigurationError('incomplete recovery checkpoint')
        report = ScanReport(
            modes=[ModeResult(**item) for item in raw["modes"]],
            completed=[ScanInterval(**item) for item in raw["completed"]],
            empty=[ScanInterval(**item) for item in raw["empty"]],
            probed=[ScanInterval(**item) for item in raw.get("probed", [])],
            failed=[ScanInterval(**item) for item in raw["failed"]],
            failure_reasons=dict(raw.get("failure_reasons", {})),
            solver_calls=raw["solver_calls"],
            adopted_task_ids=list(raw.get('adopted_task_ids', [])),
            active_mesh_cells=raw.get('active_mesh_cells'),
            recovery_states=dict(raw.get('recovery_states', {})),
            recovery_events=list(raw.get('recovery_events', [])),
        )
        pending = [ScanInterval(**item) for item in document["pending"]]
        return document, report, pending

    def load(self, policy: ScanPolicy, project_fingerprint: dict):
        _, report, pending = self._load_document(policy, project_fingerprint)
        return report, pending

    def load_with_snapshot(self, policy: ScanPolicy, project_fingerprint: dict):
        document, report, pending = self._load_document(policy, project_fingerprint)
        record = document.get("confirmedSnapshot")
        if record is None:
            return report, pending, None
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ScanConfigurationError("checkpoint snapshot metadata is invalid")
        snapshot = (self.path.parent / record["path"]).resolve()
        if (
            not snapshot.is_file()
            or snapshot.stat().st_size != record.get("size")
            or self._sha256(snapshot) != record.get("sha256")
        ):
            raise ScanConfigurationError(
                f"checkpoint CST snapshot is missing or changed: {snapshot}"
            )
        return report, pending, snapshot

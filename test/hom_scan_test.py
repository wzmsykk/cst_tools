import json
import logging
from pathlib import Path

import pandas as pd
import pytest

from csttool.hom_scan import (
    AdaptiveHomScanner,
    IncompleteScanError,
    ScanInterrupted,
    ModeResult,
    ScanCheckpointStore,
    ScanInterval,
    ScanPolicy,
    ScanReport,
)
from csttool.myAlgorithm_pop import myAlg01


def mode(frequency):
    return ModeResult(1, frequency, {"frequency": frequency, "Q-factor": 1.0})


def test_scan_requests_one_mode_and_advances_just_above_each_result():
    policy = ScanPolicy(0, 10, 30, window_width=10)
    physical_modes = [4.0, 9.0, 21.0]
    requests = []

    def solve(request):
        requests.append(request)
        found = [
            frequency
            for frequency in physical_modes
            if request.solve_lo <= frequency <= request.solve_hi
        ]
        return [mode(found[0])] if found else []

    report = AdaptiveHomScanner(policy).run(solve)

    assert [item.frequency for item in report.modes] == physical_modes
    assert all(request.requested_modes == 1 for request in requests)
    assert requests[1].solve_lo > 4.0
    assert requests[1].solve_lo == pytest.approx(4.000001)
    assert requests[2].solve_lo > 9.0


def test_empty_interval_advances_by_one_narrow_window():
    policy = ScanPolicy(0, 5, 15, window_width=5)
    requests = []

    def solve(request):
        requests.append((request.solve_lo, request.solve_hi))
        return []

    report = AdaptiveHomScanner(policy).run(solve)

    assert requests == [(0, 5), (5, 10), (10, 15)]
    assert report.empty == [
        ScanInterval(0, 5),
        ScanInterval(5, 10),
        ScanInterval(10, 15),
    ]


def test_multi_mode_result_is_rejected_instead_of_silently_truncated():
    policy = ScanPolicy(0, 10, 10, max_interval_attempts=1)

    with pytest.raises(IncompleteScanError) as captured:
        AdaptiveHomScanner(policy).run(lambda _request: [mode(2), mode(3)])

    assert "more than one mode" in next(
        iter(captured.value.report.failure_reasons.values())
    )


def test_repeated_boundary_frequency_fails_as_possible_degeneracy():
    policy = ScanPolicy(0, 10, 20, window_width=10, max_interval_attempts=1)

    with pytest.raises(IncompleteScanError) as captured:
        AdaptiveHomScanner(policy).run(lambda _request: [mode(5)])

    assert captured.value.report.solver_calls == 2
    assert "degenerate" in next(iter(captured.value.report.failure_reasons.values()))


def test_retry_is_bounded_and_failure_reason_is_preserved():
    policy = ScanPolicy(0, 10, 10, max_interval_attempts=2)
    calls = 0

    def solve(_request):
        nonlocal calls
        calls += 1
        raise RuntimeError("CST unavailable")

    with pytest.raises(IncompleteScanError) as captured:
        AdaptiveHomScanner(policy).run(solve)

    assert calls == 2
    assert captured.value.report.solver_calls == 2
    assert "CST unavailable" in next(
        iter(captured.value.report.failure_reasons.values())
    )


def test_checkpoint_is_atomic_and_rejects_changed_policy(tmp_path):
    path = tmp_path / "checkpoint.json"
    store = ScanCheckpointStore(path)
    policy = ScanPolicy(0, 10, 20)
    report = ScanReport(
        modes=[mode(5)],
        completed=[ScanInterval(0, 10)],
        solver_calls=1,
    )
    fingerprint = {"path": "model.cst", "size": 10}

    store.save(policy, fingerprint, report, [ScanInterval(5.000001, 15.000001)])
    restored, pending = store.load(policy, fingerprint)

    assert json.loads(path.read_text(encoding="utf-8"))["schemaVersion"] == 3
    assert restored.modes == report.modes
    assert pending == [ScanInterval(5.000001, 15.000001)]
    assert not path.with_suffix(".json.tmp").exists()
    with pytest.raises(ValueError, match="policy"):
        store.load(ScanPolicy(0, 10, 30), fingerprint)


def test_checkpoint_restores_only_an_unchanged_confirmed_snapshot(tmp_path):
    path = tmp_path / "checkpoint.json"
    snapshot = tmp_path / "result" / "task-8" / "project.cst"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"confirmed-mode-8")
    store = ScanCheckpointStore(path)
    policy = ScanPolicy(0, 10, 20)
    report = ScanReport(modes=[mode(5)], solver_calls=1)
    fingerprint = {"path": "model.cst", "size": 10}

    store.save(policy, fingerprint, report, [], snapshot_path=snapshot)
    restored, pending, restored_snapshot = store.load_with_snapshot(
        policy, fingerprint
    )

    assert restored.modes == report.modes
    assert pending == []
    assert restored_snapshot == snapshot.resolve()

    changed = bytearray(snapshot.read_bytes())
    changed[0] ^= 0x01
    snapshot.write_bytes(changed)
    with pytest.raises(ValueError, match="missing or changed"):
        store.load_with_snapshot(policy, fingerprint)


def test_schema_two_checkpoint_remains_readable_without_snapshot(tmp_path):
    path = tmp_path / "checkpoint.json"
    store = ScanCheckpointStore(path)
    policy = ScanPolicy(0, 10, 20)
    report = ScanReport(modes=[mode(5)], solver_calls=1)
    fingerprint = {"path": "model.cst", "size": 10}
    store.save(policy, fingerprint, report, [])
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schemaVersion"] = 2
    document.pop("confirmedSnapshot")
    path.write_text(json.dumps(document), encoding="utf-8")

    restored, pending, snapshot = store.load_with_snapshot(policy, fingerprint)

    assert restored.modes == report.modes
    assert pending == []
    assert snapshot is None


def test_policy_rejects_multi_mode_requests():
    with pytest.raises(ValueError, match="requested_modes"):
        ScanPolicy(0, 10, 20, requested_modes=2)


def test_algorithm_reads_single_mode_postprocess_results():
    algorithm = myAlg01()
    raw = [
        {
            "resultName": "frequency",
            "value": 100.0,
            "params": {"iModeNumber": 1},
        },
        {
            "resultName": "Q-factor",
            "value": 10.0,
            "params": {"iModeNumber": 1},
        },
    ]

    modes = algorithm._extract_scan_modes(raw)

    assert [(item.mode_index, item.frequency) for item in modes] == [(1, 100.0)]
    assert modes[0].values["Q-factor"] == 10.0


def test_algorithm_requires_mode_one_non_all_postprocess_configuration():
    algorithm = myAlg01()
    algorithm.validate_postprocess_settings(
        [
            {
                "resultName": "frequency",
                "method": "Frequency",
                "params": {"iModeNumber": 1},
            },
            {
                "resultName": "q",
                "method": "Q_Factor",
                "params": {"iModeNumber": 1},
            },
        ]
    )
    with pytest.raises(ValueError, match="_All"):
        algorithm.validate_postprocess_settings(
            [
                {
                    "resultName": "frequency",
                    "method": "Frequency_All",
                    "params": {},
                }
            ]
        )
    with pytest.raises(ValueError, match="iModeNumber=1"):
        algorithm.validate_postprocess_settings(
            [
                {
                    "resultName": "frequency",
                    "method": "Frequency",
                    "params": {"iModeNumber": 2},
                }
            ]
        )


class ScanManager:
    def __init__(self, root):
        self.currProjectDir = root
        self.cstProjPath = root / "model.cst"
        self.cstProjPath.write_bytes(b"fake-cst-project")
        self.logger = logging.getLogger("hom-scan-integration-test")
        self.result_dir = root / "result"
        self.result_dir.mkdir()
        self.tasks = []
        self.physical_modes = [105.0, 114.0]
        self.confirmed_snapshot = None
        self.restored_snapshot = None

    def getResultDir(self):
        return self.result_dir

    def execute(self, task):
        self.tasks.append(task)
        lo = task.params["fmin"]
        hi = task.params["fmax"]
        found = [item for item in self.physical_modes if lo <= item <= hi]
        postprocess = []
        if found:
            postprocess = [
                {
                    "resultName": "frequency",
                    "value": found[0],
                    "params": {"iModeNumber": 1},
                },
                {
                    "resultName": "Q-factor",
                    "value": 10.0,
                    "params": {"iModeNumber": 1},
                },
            ]
        return {"TaskStatus": "Success", "PostProcessResult": postprocess}

    def run_batch(self, tasks):
        return [self.execute(task) for task in tasks]

    def get_confirmed_snapshot(self):
        return self.confirmed_snapshot

    def restore_project_snapshot(self, snapshot):
        self.restored_snapshot = Path(snapshot).resolve()
        self.confirmed_snapshot = self.restored_snapshot

    def stop(self):
        pass


def test_production_algorithm_writes_results_and_checkpoint(tmp_path):
    manager = ScanManager(tmp_path)
    algorithm = myAlg01(manager=manager, params=[])
    algorithm.setCSTParams([])
    algorithm.setEditableAttrs(
        {"fmin": 100, "fmax": 110, "endfreq": 120, "cflag": 0}
    )

    report = algorithm.start()

    assert [item.frequency for item in report.modes] == [105.0, 114.0]
    assert all(task.params["nmodes"] == 1 for task in manager.tasks)
    assert manager.tasks[1].params["fmax"] - manager.tasks[1].params["fmin"] == 10
    result_path = tmp_path / "save" / "csv" / "hom_scan_results.csv"
    assert list(pd.read_csv(result_path)["mode"]) == [1, 2]
    assert list(pd.read_csv(result_path)["solverMode"]) == [1, 1]
    assert (tmp_path / "save" / "csv" / "hom_scan_checkpoint.json").exists()


def test_production_algorithm_restores_confirmed_snapshot_before_resume(tmp_path):
    manager = ScanManager(tmp_path)
    manager.physical_modes = [114.0]
    snapshot = tmp_path / "result" / "mode-8" / "project.cst"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"confirmed-mode-8")
    algorithm = myAlg01(manager=manager, params=[])
    algorithm.setCSTParams([])
    algorithm.setEditableAttrs(
        {"fmin": 100, "fmax": 110, "endfreq": 120, "cflag": 1}
    )
    checkpoint = ScanCheckpointStore(
        tmp_path / "save" / "csv" / "hom_scan_checkpoint.json"
    )
    checkpoint.save(
        algorithm._scan_policy(),
        algorithm._project_fingerprint(),
        ScanReport(
            modes=[mode(105.0)],
            completed=[ScanInterval(100.0, 110.0)],
            solver_calls=1,
        ),
        [ScanInterval(105.000001, 115.000001)],
        snapshot_path=snapshot,
    )

    report = algorithm.start()

    assert manager.restored_snapshot == snapshot.resolve()
    assert [item.frequency for item in report.modes] == [105.0, 114.0]


def test_scanner_stops_between_solves_and_preserves_pending_interval():
    policy = ScanPolicy(start=100, initial_stop=110, stop=130, window_width=10)
    stop = False

    def solve(_request):
        nonlocal stop
        stop = True
        return [mode(105)]

    with pytest.raises(ScanInterrupted) as raised:
        AdaptiveHomScanner(policy).run(solve, should_stop=lambda: stop)

    assert [item.frequency for item in raised.value.report.modes] == [105]
    assert raised.value.pending == [ScanInterval(105.000001, 115.000001)]

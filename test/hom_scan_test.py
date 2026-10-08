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


def test_returned_frequency_above_window_is_recomputed_before_acceptance(caplog):
    policy = ScanPolicy(774.079327547941, 824.079327547941, 900, window_width=50)
    returned = 833.416152639007
    requests = []

    def solve(request):
        requests.append(request)
        return [mode(returned)] if request.solve_lo < returned else []

    with caplog.at_level(logging.INFO):
        report = AdaptiveHomScanner(policy).run(solve)
    assert [item.frequency for item in report.modes] == [returned]
    assert requests[1].solve_lo == requests[0].solve_lo
    assert requests[0].solve_hi < returned < requests[1].solve_hi
    assert all(request.solve_hi <= policy.stop for request in requests)
    assert requests[2].solve_hi - requests[2].solve_lo == pytest.approx(50)
    assert "HOM_WINDOW_EXPAND" in caplog.text
    assert caplog.text.count("HOM_MODE_ACCEPTED") == 1


def test_next_mode_above_global_stop_ends_normally(caplog):
    with caplog.at_level(logging.INFO):
        report = AdaptiveHomScanner(ScanPolicy(0, 10, 20)).run(lambda request: [mode(21)])
    assert report.solver_calls == 2
    assert not report.modes
    assert not report.failed
    assert "HOM_SCAN_LIMIT_REACHED" in caplog.text
    assert "HOM_MODE_ACCEPTED" not in caplog.text


def test_frequency_below_lower_bound_fails_with_reason():
    report = AdaptiveHomScanner(ScanPolicy(5, 10, 20)).run(lambda request: [mode(4)])
    assert report.solver_calls == 4
    assert not report.modes
    assert not report.empty
    assert len(report.failed) == 2
    assert all("below the search lower bound" in reason for reason in report.failure_reasons.values())


@pytest.mark.parametrize("frequency", [-1.0, 0.0])
def test_invalid_frequency_is_not_treated_as_out_of_window_or_empty(frequency, caplog):
    with caplog.at_level(logging.WARNING):
        report = AdaptiveHomScanner(ScanPolicy(1499.6944519768, 1549.6944519768, 1549.6944519768)).run(
            lambda request: [mode(frequency)]
        )
    assert report.solver_calls == 2
    assert not report.modes
    assert not report.empty
    assert "HOM_SOLVE_INVALID_RESULT" in caplog.text
    assert "invalid mode frequency" in next(iter(report.failure_reasons.values()))
    assert "below the search lower bound" not in caplog.text


def test_invalid_frequency_retry_can_recover_without_skipping_interval():
    requests = []

    def solve(request):
        requests.append(request)
        if len(requests) == 1:
            return [mode(-1)]
        return [mode(5)] if request.solve_lo < 5 else []

    report = AdaptiveHomScanner(ScanPolicy(0, 10, 10)).run(solve)
    assert requests[0] == requests[1]
    assert [item.frequency for item in report.modes] == [5]
    assert not report.failed


def test_exhausted_invalid_results_are_recorded_and_later_modes_are_scanned(caplog):
    requests = []
    checkpoints = []

    def solve(request):
        requests.append((request.solve_lo, request.solve_hi))
        if request.solve_lo == 100:
            return [mode(-1)]
        return [mode(115)] if request.solve_lo < 115 else []

    with caplog.at_level(logging.WARNING):
        report = AdaptiveHomScanner(ScanPolicy(100, 110, 120, window_width=10)).run(
            solve, checkpoint=lambda report, pending: checkpoints.append(list(pending))
        )
    assert requests[:3] == [(100, 110), (100, 110), (110, 120)]
    assert report.failed == [ScanInterval(100, 110)]
    assert [item.frequency for item in report.modes] == [115]
    assert checkpoints[0] == [ScanInterval(110, 120)]
    assert checkpoints[-1] == []
    assert ScanInterval(100, 110) not in report.empty + report.completed
    assert "HOM_FAILED_INTERVAL" in caplog.text


def test_repeated_window_overshoot_is_bounded():
    calls = []

    def solve(request):
        calls.append(request)
        return [mode(request.solve_hi + 1)]

    report = AdaptiveHomScanner(ScanPolicy(0, 10, 20)).run(solve)
    assert len(calls) == report.solver_calls == 2
    assert report.failed == [calls[-1].interval]
    assert not report.modes
    assert "confirmation required" in next(iter(report.failure_reasons.values()))


def test_window_retry_uses_only_recomputed_frequency_values_and_snapshot():
    first = ModeResult(1, 15.0, {"frequency": 15.0, "Q-factor": 10}, project_snapshot="first.cst")
    confirmed = ModeResult(1, 14.9, {"frequency": 14.9, "Q-factor": 20}, project_snapshot="confirmed.cst")
    calls = []

    def solve(request):
        calls.append(request)
        if len(calls) == 1:
            return [first]
        return [confirmed] if request.solve_lo < confirmed.frequency else []

    report = AdaptiveHomScanner(ScanPolicy(0, 10, 20)).run(solve)
    assert report.modes == [confirmed]
    assert calls[2].solve_lo == pytest.approx(14.900001)
    assert report.modes[0].values["Q-factor"] == 20
    assert report.modes[0].project_snapshot == "confirmed.cst"


def test_scan_logs_confirmed_frequency_results_and_archive(caplog):
    result = ModeResult(1, 5.0, {"frequency": 5.0, "R_divide_Q": 1.23e-7, "Q-factor": 757.065},
                        project_snapshot="result/hom/snapshot.cst", task_name="hom_0_10", task_id="task-1")
    with caplog.at_level(logging.INFO):
        AdaptiveHomScanner(ScanPolicy(0, 10, 10)).run(
            lambda request: [result] if request.solve_lo < 5 else []
        )
    accepted = next(record.message for record in caplog.records if "HOM_MODE_ACCEPTED" in record.message)
    assert "频率=5 MHz" in accepted
    assert "R_divide_Q=1.23e-07" in accepted
    assert "Q-factor=757.065" in accepted
    assert "任务=hom_0_10" in accepted
    assert "存档=result/hom/snapshot.cst" in accepted
    assert "HOM_INTERVAL_EMPTY" in caplog.text


def test_stop_before_confirmation_keeps_expanded_window_pending():
    stopped = False

    def solve(request):
        nonlocal stopped
        stopped = True
        return [mode(15)]

    with pytest.raises(ScanInterrupted) as captured:
        AdaptiveHomScanner(ScanPolicy(0, 10, 20)).run(solve, should_stop=lambda: stopped)
    assert captured.value.report.solver_calls == 1
    assert not captured.value.report.modes
    assert captured.value.pending[0].lo == 0
    assert captured.value.pending[0].hi > 15


def test_multi_mode_result_is_rejected_instead_of_silently_truncated():
    policy = ScanPolicy(0, 10, 10, max_interval_attempts=1)

    report = AdaptiveHomScanner(policy).run(lambda _request: [mode(2), mode(3)])

    assert "more than one mode" in next(
        iter(report.failure_reasons.values())
    )


def test_repeated_boundary_frequency_fails_as_possible_degeneracy():
    policy = ScanPolicy(0, 10, 20, window_width=10, max_interval_attempts=1)

    report = AdaptiveHomScanner(policy).run(lambda _request: [mode(5)])

    assert report.solver_calls == 3
    assert "degenerate" in next(iter(report.failure_reasons.values()))


def test_retry_is_bounded_and_failure_reason_is_preserved():
    policy = ScanPolicy(0, 10, 10, max_interval_attempts=2)
    calls = 0

    def solve(_request):
        nonlocal calls
        calls += 1
        raise RuntimeError("CST unavailable")

    report = AdaptiveHomScanner(policy).run(solve)

    assert calls == 2
    assert report.solver_calls == 2
    assert "CST unavailable" in next(
        iter(report.failure_reasons.values())
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


def test_old_checkpoint_schema_is_rejected(tmp_path):
    path = tmp_path / "checkpoint.json"
    store = ScanCheckpointStore(path)
    policy = ScanPolicy(0, 10, 20)
    report = ScanReport(modes=[mode(5)], solver_calls=1)
    fingerprint = {"path": "model.cst", "size": 10}
    store.save(policy, fingerprint, report, [])
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schemaVersion"] = 1
    document.pop("confirmedSnapshot")
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported HOM checkpoint version"):
        store.load_with_snapshot(policy, fingerprint)


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
        from csttool.configuration import GlobalSettings
        self.global_settings = GlobalSettings()
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
        {"fmin": 100, "fmax": 110, "endfreq": 120}
    )

    report = algorithm.start()

    assert [item.frequency for item in report.modes] == [105.0, 114.0]
    assert all(task.params["nmodes"] == 1 for task in manager.tasks)
    assert all("accuracy" not in task.params for task in manager.tasks)
    assert all("cell" not in task.params for task in manager.tasks)
    assert manager.tasks[1].params["fmax"] - manager.tasks[1].params["fmin"] == 10
    result_path = tmp_path / "save" / "csv" / "hom_scan_results.csv"
    assert list(pd.read_csv(result_path)["mode"]) == [1, 2]
    assert list(pd.read_csv(result_path)["solverMode"]) == [1, 1]
    assert (tmp_path / "save" / "csv" / "hom_scan_checkpoint.json").exists()


def test_scan_results_and_checkpoint_keep_per_mode_archive_mapping(tmp_path):
    class ArchiveManager(ScanManager):
        def execute(self, task):
            result = super().execute(task)
            snapshot = self.result_dir / task.job_name / f"{task.job_name}.cst"
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(task.job_name.encode("ascii"))
            result.update({"ProjectSnapshot": str(snapshot), "RunName": task.job_name, "TaskID": str(len(self.tasks))})
            return result

    manager = ArchiveManager(tmp_path)
    algorithm = myAlg01(manager=manager, params=[])
    algorithm.setCSTParams([])
    algorithm.setEditableAttrs({"fmin": 100, "fmax": 110, "endfreq": 120})
    report = algorithm.start()
    destination = tmp_path / "save" / "csv" / "hom_scan_results.csv"
    rows = pd.read_csv(destination, dtype={"taskId": str})
    assert rows["frequency"].tolist() == [105.0, 114.0]
    for row, mode in zip(rows.to_dict("records"), report.modes):
        snapshot = tmp_path / row["projectSnapshot"]
        assert snapshot.read_bytes() == row["taskName"].encode("ascii")
        assert row["taskId"] == mode.task_id
        assert snapshot.parent == tmp_path / row["resultDirectory"]
    checkpoint = ScanCheckpointStore(destination.with_name("hom_scan_checkpoint.json"))
    restored, pending = checkpoint.load(algorithm._scan_policy(), algorithm._project_fingerprint())
    assert pending == []
    assert restored.modes == report.modes
    assert destination.with_name("hom_scan_results_README.txt").exists()


def test_production_algorithm_records_fixed_mesh_without_runtime_mutation(tmp_path):
    manager = ScanManager(tmp_path)
    algorithm = myAlg01(manager=manager, params=[])
    algorithm.setCSTParams([])
    algorithm.setEditableAttrs(
        {
            "fmin": 100,
            "fmax": 110,
            "endfreq": 110,
            "mesh_cells_per_wavelength": 28,
        }
    )

    algorithm.start()

    assert "accuracy" not in manager.tasks[0].params
    assert "cell" not in manager.tasks[0].params
    manifest = json.loads(
        (tmp_path / "save" / "csv" / "scan_manifest.json").read_text()
    )
    assert manifest["mesh_cells_per_wavelength"] == 28


def test_production_algorithm_restores_confirmed_snapshot_before_resume(tmp_path):
    manager = ScanManager(tmp_path)
    manager.physical_modes = [114.0]
    snapshot = tmp_path / "result" / "mode-8" / "project.cst"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"confirmed-mode-8")
    algorithm = myAlg01(manager=manager, params=[])
    algorithm.setCSTParams([])
    algorithm.setEditableAttrs(
        {"fmin": 100, "fmax": 110, "endfreq": 120}
    )
    algorithm.set_resume(True)
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

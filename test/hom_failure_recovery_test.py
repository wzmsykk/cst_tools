import json
import pytest

from csttool.hom_scan import (AdaptiveHomScanner, ScanPolicy, ScanInterval, ModeResult,
    TaskModeResults, RecoverableSolveError, ScanInterrupted, ScanCheckpointStore, IncompleteScanError)


def mode(frequency):
    return ModeResult(1, frequency, {'frequency': frequency, 'R/Q_x': 2.0})


def test_production_missing_postprocess_cannot_establish_empty_interval():
    from csttool.hom_scan_algorithm import HomScanAlgorithm
    algorithm = HomScanAlgorithm(manager=None, params=[])
    with pytest.raises(ValueError, match='cannot establish an empty interval'):
        algorithm._extract_scan_modes([])


def policy(**kwargs):
    return ScanPolicy(0, 5, 10, window_width=5, failure_recovery=True,
                      base_mesh_cells=4, **kwargs)


def test_mesh_then_base_probe_then_narrow_confirmation_marks_original_empty():
    requests = []
    def solve(request):
        requests.append(request)
        if request.recovery_phase in {'normal', 'mesh'} and request.interval.lo == 0:
            raise RecoverableSolveError('iterations exhausted')
        return TaskModeResults([mode(8)] if request.solve_lo <= 8 <= request.solve_hi else [],
                               task_id='task-' + str(len(requests)))
    report = AdaptiveHomScanner(policy()).run(solve)
    assert [r.recovery_phase for r in requests] == ['normal', 'mesh', 'probe', 'confirm', 'normal']
    assert [r.mesh_cells for r in requests] == [4, 6, 4, 4, 4]
    assert requests[2].solve_lo == 0 and requests[2].solve_hi == 10
    assert requests[3].solve_hi - requests[3].solve_lo == 5
    assert [m.frequency for m in report.modes] == [8]
    assert ScanInterval(0, 5) in report.empty
    assert any(e['phase'] == 'empty-inferred' for e in report.recovery_events)
    assert not report.failed and report.active_mesh_cells == 4
    assert report.adopted_task_ids.count('task-3') == 1  # Probe consumed, not a duplicate mode.


def test_mesh_retry_success_returns_to_base_density():
    calls = []
    def solve(request):
        calls.append(request)
        if len(calls) == 1:
            raise RecoverableSolveError('solver failed')
        return [mode(3)] if request.solve_lo <= 3 <= request.solve_hi else []
    report = AdaptiveHomScanner(policy()).run(solve)
    assert [r.mesh_cells for r in calls[:3]] == [4, 6, 4]
    assert [m.frequency for m in report.modes] == [3]
    assert not report.failed


def test_failed_probes_do_not_prove_empty_or_cover_failed_interval():
    def solve(request):
        if request.interval.lo == 0:
            raise RecoverableSolveError('nonconvergence')
        return []
    report = AdaptiveHomScanner(policy()).run(solve)
    assert report.failed == [ScanInterval(0, 5)]
    assert ScanInterval(0, 5) not in report.empty + report.completed
    assert report.solver_calls == 6  # normal + mesh + three probes + next narrow.


def test_empty_successful_probe_only_marks_original_window_empty():
    def solve(request):
        if request.interval.lo == 0 and request.recovery_phase in {'normal', 'mesh'}:
            raise RecoverableSolveError('solver failed')
        return []
    report = AdaptiveHomScanner(policy()).run(solve)
    assert report.empty == [ScanInterval(0, 5), ScanInterval(5, 10)]
    assert not report.modes and not report.failed


def test_protocol_or_invalid_result_does_not_turn_into_empty_probe():
    phases = []
    def solve(request):
        phases.append(request.recovery_phase)
        if request.interval.lo != 0:
            return []
        if request.recovery_phase == 'normal':
            raise RecoverableSolveError('solver failed')
        raise RuntimeError('ACK_PENDING')
    report = AdaptiveHomScanner(policy()).run(solve)
    assert phases[:2] == ['normal', 'mesh']
    assert 'probe' not in phases
    assert ScanInterval(0, 5) in report.failed and ScanInterval(0, 5) not in report.empty


def test_interruption_after_probe_resumes_confirmation_without_repeating_probe(tmp_path):
    store = ScanCheckpointStore(tmp_path / 'checkpoint.json')
    stopped = [False]
    calls = []
    def solve(request):
        calls.append(request.recovery_phase)
        if request.recovery_phase in {'normal', 'mesh'} and request.interval.lo == 0:
            raise RecoverableSolveError('solver failed')
        if request.recovery_phase == 'probe':
            stopped[0] = True
            return TaskModeResults([mode(8)], 'probe-id')
        return [mode(8)] if request.solve_lo <= 8 <= request.solve_hi else []
    save = lambda report, pending: store.save(policy(), {}, report, pending)
    with pytest.raises(ScanInterrupted):
        AdaptiveHomScanner(policy()).run(solve, checkpoint=save, should_stop=lambda: stopped[0])
    document, report, pending = store._load_document(policy(), {})
    assert not report.modes and document['coverage']['confirmed_frontier'] == 0
    assert document['coverage']['calculated_upper'] == 10
    assert report.recovery_states['0:5']['phase'] == 'confirm'
    stopped[0] = False
    report = AdaptiveHomScanner(policy()).run(solve, report=report, pending=pending, checkpoint=save)
    assert calls.count('probe') == 1 and calls[3] == 'confirm'
    assert [m.frequency for m in report.modes] == [8]
    assert report.adopted_task_ids.count('probe-id') == 1


def test_recovery_call_limit_is_persisted_and_not_empty():
    reports = []
    with pytest.raises(IncompleteScanError) as caught:
        AdaptiveHomScanner(policy(max_solver_calls=2)).run(
            lambda r: (_ for _ in ()).throw(RecoverableSolveError('failed')),
            checkpoint=lambda report, pending: reports.append(report.solver_calls))
    assert caught.value.report.solver_calls == 2
    assert not caught.value.report.empty and 2 in reports


def test_legacy_checkpoint_migration_only_adds_recovery_fields(tmp_path):
    from csttool.hom_scan import ScanReport
    store = ScanCheckpointStore(tmp_path / 'checkpoint.json')
    store.save(policy(), {'identity': 'same'}, ScanReport(), [ScanInterval(0, 5)])
    original = json.loads(store.path.read_text())
    original['schemaVersion'] = 3
    for key in ('failure_recovery', 'base_mesh_cells', 'mesh_retry_factor', 'max_probe_expansions'):
        original['policy'].pop(key)
    store.path.write_text(json.dumps(original))
    report, pending = store.load(policy(), {'identity': 'same'})
    assert not report.modes and pending == [ScanInterval(0, 5)]
    with pytest.raises(Exception, match='project does not match'):
        store.load(policy(), {'identity': 'different'})


def test_production_adapter_restores_cell_after_fine_success(tmp_path):
    from test.hom_scan_test import ScanManager
    from csttool.hom_scan_algorithm import HomScanAlgorithm
    class Manager(ScanManager):
        first = True
        def execute(self, task):
            if self.first:
                self.first = False
                self.tasks.append(task)
                return {'TaskStatus': 'Failure', 'FailureReport': 'SOLVER_FAILED: iterations'}
            return super().execute(task)
    manager = Manager(tmp_path)
    manager.physical_modes = [105.0, 114.0, 120.0]
    algorithm = HomScanAlgorithm(manager=manager, params=[])
    algorithm.set_cst_parameters([])
    algorithm.set_editable_attributes({'fmin': 100, 'fmax': 110, 'endfreq': 120,
                                      'mesh_cells_per_wavelength': 4})
    report = algorithm.start()
    assert [t.params.get('cell') for t in manager.tasks] == [None, 6, 4, None]
    assert [m.mesh_cells_per_wavelength for m in report.modes] == [6, 4, 4]
    assert all(t.retire_failed_session and t.retry_count == 0 for t in manager.tasks)


def test_mesh_overshoot_is_probed_and_not_accepted_directly():
    phases = []
    def solve(request):
        phases.append(request.recovery_phase)
        if len(phases) == 1:
            raise RecoverableSolveError('failed')
        return [mode(8)] if request.solve_lo <= 8 else []
    report = AdaptiveHomScanner(policy()).run(solve)
    assert phases[:4] == ['normal', 'mesh', 'probe', 'confirm']
    assert [m.frequency for m in report.modes] == [8]


def test_corrupt_recovery_stage_fails_before_any_solver():
    from csttool.hom_scan import ScanReport, ScanConfigurationError
    report = ScanReport(recovery_states={'0:5': {'phase': 'invented', 'level': 1}})
    with pytest.raises(ScanConfigurationError, match='invalid recovery'):
        AdaptiveHomScanner(policy()).run(lambda _: pytest.fail('must not solve'), report=report)


def test_refined_empty_checkpoint_remembers_density_for_resume(tmp_path):
    store = ScanCheckpointStore(tmp_path / 'checkpoint.json')
    stop = [False]
    def solve(request):
        if request.recovery_phase == 'normal':
            raise RecoverableSolveError('failed')
        stop[0] = True
        return []
    with pytest.raises(ScanInterrupted):
        AdaptiveHomScanner(policy()).run(solve, should_stop=lambda: stop[0],
            checkpoint=lambda r, p: store.save(policy(), {}, r, p))
    report, pending = store.load(policy(), {})
    assert not report.modes and report.active_mesh_cells == 6
    assert pending == [ScanInterval(0, 5)]
    assert not report.empty and report.recovery_states['0:5']['phase'] == 'probe'


def test_v4_checkpoint_missing_recovery_fields_is_rejected(tmp_path):
    from csttool.hom_scan import ScanReport, ScanConfigurationError
    store = ScanCheckpointStore(tmp_path / 'checkpoint.json')
    store.save(policy(), {}, ScanReport(), [ScanInterval(0, 5)])
    document = json.loads(store.path.read_text())
    document['report'].pop('recovery_states')
    store.path.write_text(json.dumps(document))
    before = store.path.read_bytes()
    with pytest.raises(ScanConfigurationError, match='incomplete recovery'):
        store.load(policy(), {})
    assert store.path.read_bytes() == before


def test_rotating_workers_restore_every_slot_after_temporary_mesh(tmp_path):
    from test.hom_scan_test import ScanManager
    from csttool.hom_scan_algorithm import HomScanAlgorithm
    class Manager(ScanManager):
        maxParallelTasks = 2
        def __init__(self, root):
            super().__init__(root)
            self.densities = [4, 4]
        def execute(self, task):
            slot = len(self.tasks) % 2
            self.densities[slot] = task.params.get('cell', self.densities[slot])
            if not self.tasks:
                self.tasks.append(task)
                return {'TaskStatus': 'Failure', 'FailureReport': 'SOLVER_FAILED: iterations'}
            return super().execute(task)
    manager = Manager(tmp_path)
    manager.physical_modes = [105.0, 114.0, 120.0]
    algorithm = HomScanAlgorithm(manager=manager, params=[])
    algorithm.set_cst_parameters([])
    algorithm.set_editable_attributes({'fmin': 100, 'fmax': 110, 'endfreq': 120,
                                      'mesh_cells_per_wavelength': 4})
    algorithm.start()
    assert [t.params.get('cell') for t in manager.tasks] == [None, 6, 4, 4]
    assert manager.densities == [4, 4]


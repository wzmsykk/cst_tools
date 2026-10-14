import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from csttool.hom_scan import AdaptiveHomScanner, ScanPolicy, ScanInterval, ScanReport, ScanCheckpointStore, ScanInterrupted
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.runtime_protocol import FileProtocol


def test_stop_request_does_not_wait_for_active_task_lock(tmp_path):
    worker = object.__new__(ManagedCSTWorker)
    worker._lock = threading.Lock()
    worker.protocol = FileProtocol(tmp_path/'protocol')
    worker.session_id = '11111111-1111-4111-8111-111111111111'
    with worker._lock:
        thread = threading.Thread(target=worker.request_stop)
        thread.start()
        thread.join(timeout=1)
        assert not thread.is_alive()
    assert (tmp_path/'protocol/stop.request').is_file()


def test_empty_intervals_advance_computed_coverage_without_modes(tmp_path):
    policy = ScanPolicy(100,110,130,window_width=10)
    store = ScanCheckpointStore(tmp_path/'checkpoint.json')
    stopped = [False]
    calls = []
    def solve(request):
        calls.append(request.interval)
        stopped[0] = True
        return []
    with pytest.raises(ScanInterrupted):
        AdaptiveHomScanner(policy).run(solve, should_stop=lambda:stopped[0],
            checkpoint=lambda report,pending:store.save(policy,{},report,pending))
    saved = json.loads(store.path.read_text())
    assert saved['coverage']['confirmed_frontier'] == 110
    assert saved['coverage']['calculated_upper'] == 110
    report,pending = store.load(policy,{})
    assert report.modes == []
    resumed = []
    AdaptiveHomScanner(policy).run(lambda request:resumed.append(request.interval) or [],report=report,pending=pending)
    assert resumed[0].lo == 110
    assert ScanInterval(100,110) not in resumed


def test_mid_task_stop_preserves_current_interval_not_failed_or_skipped(tmp_path):
    policy = ScanPolicy(100,110,130,window_width=10)
    stopped = [False]
    saved = []
    def solve(request):
        assert saved[-1] == [ScanInterval(100,110)]
        stopped[0] = True
        raise RuntimeError('STOP_REQUESTED')
    with pytest.raises(ScanInterrupted) as captured:
        AdaptiveHomScanner(policy).run(solve, should_stop=lambda:stopped[0],
                                      checkpoint=lambda report,pending:saved.append(pending))
    assert captured.value.pending[0] == ScanInterval(100,110)
    assert not captured.value.report.failed


def test_failed_gap_limits_frontier_even_if_later_windows_completed(tmp_path):
    policy = ScanPolicy(100,110,140,window_width=10)
    store = ScanCheckpointStore(tmp_path/'checkpoint.json')
    report = ScanReport(completed=[ScanInterval(100,110),ScanInterval(120,130)],
                        empty=[ScanInterval(120,130)], failed=[ScanInterval(110,120)])
    store.save(policy,{},report,[ScanInterval(130,140)])
    coverage = json.loads(store.path.read_text())['coverage']
    assert coverage == {'confirmed_frontier':110,'calculated_upper':130}


def test_existing_scan_checkpoint_refuses_non_resume_without_overwriting(tmp_path):
    from test.hom_scan_test import ScanManager
    from csttool.hom_scan_algorithm import HomScanAlgorithm
    manager = ScanManager(tmp_path)
    algorithm = HomScanAlgorithm(manager=manager,params=[])
    algorithm.set_cst_parameters([])
    algorithm.set_editable_attributes({'fmin':100,'fmax':110,'endfreq':110})
    algorithm.start()
    checkpoint = tmp_path/'save/csv/hom_scan_checkpoint.json'
    before = checkpoint.read_bytes()
    task_count = len(manager.tasks)
    with pytest.raises(RuntimeError,match='禁止从头覆盖'):
        algorithm.start()
    assert checkpoint.read_bytes() == before
    assert len(manager.tasks) == task_count


def test_managed_vba_checks_boundaries_and_retains_interrupted_solver_results():
    root = Path(__file__).parents[1]
    macro = (root/'data/runtime_managed_worker_v1_main.vb').read_text(encoding='utf-8')
    for stage in ('before-parameters','parameters','before-rebuild','after-rebuild','before-solver','after-solver','before-flush'):
        assert f'CSTPMW_CheckStop "{stage}"' in macro
    assert 'Backup outFullDir & "interrupted-project.cst"' in macro
    assert 'modelNeedsRecovery = False' in macro[macro.index('If activeTaskSolveReady Then'):]
    from csttool.postprocess_cst import CstPostProcessor
    generator = CstPostProcessor()
    generator.configure([{'method':'Frequency','resultName':'frequency','params':{'iModeNumber':1}}])
    generated = ''.join(generator.render_vb(cooperative_stop=True))
    assert 'CSTPMW_CheckStop "postprocess-item"' in generated
    assert 'CSTPMW_CheckStop' not in ''.join(generator.render_vb())


def test_manager_broadcasts_stop_to_existing_workers_once(tmp_path):
    import logging
    import queue
    from csttool.cstmanager import CSTManager, ManagerState
    manager = object.__new__(CSTManager)
    manager._state_lock = threading.RLock()
    manager._state = ManagerState.IDLE
    manager._task_queue = queue.Queue()
    manager._task_queue.put('queued')
    manager.currProjectDir = tmp_path
    manager.logger = logging.getLogger('stop-broadcast')
    calls = []
    manager._slots = [SimpleNamespace(worker=SimpleNamespace(request_stop=lambda:calls.append('stop')))]
    manager.request_stop()
    manager.request_stop()
    assert calls == ['stop']
    assert manager._task_queue.empty()


@pytest.mark.parametrize('filename', ['hom_scan_checkpoint.json', 'scan_manifest.json'])
def test_backend_rejects_restart_before_manager_or_preprocessing(tmp_path, filename):
    from test.application_backend_test import make_backend
    from csttool.application_backend import BackendPreparationError
    checkpoint = tmp_path/'save/csv'/filename
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('preserved-checkpoint')
    backend, _, project, _, manager_calls = make_backend()
    backend.select_project_directory(str(tmp_path))
    backend.select_cst_file('model.cst')
    backend.initialize_run(False,1)
    with pytest.raises(BackendPreparationError,match='禁止从头覆盖'):
        backend.prepare_run()
    assert not manager_calls
    assert not project.ready
    assert checkpoint.read_text() == 'preserved-checkpoint'

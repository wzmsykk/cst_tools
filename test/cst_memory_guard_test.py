from types import SimpleNamespace

import pytest
import psutil

from csttool.cst_memory_guard import MemoryGuardPolicy, SustainedMemoryGuard
from csttool.managed_cstworker import ManagedWorkerShutdownError
from csttool.cst_memory_guard import MemorySamplingError, owned_process_memory
from test.managed_cstworker_test import build_worker_shell


def policy():
    return MemoryGuardPolicy(minimum_bytes=80, sustained_seconds=10,
                             stalled_seconds=10, sample_seconds=1)


def test_guard_requires_extreme_growth_and_sustained_stall():
    guard = SustainedMemoryGuard(policy())
    assert not guard.observe(0, 10, 100, 0)
    assert not guard.observe(2400, 30, 100, 0)  # Long solve alone is allowed.
    assert not guard.observe(2401, 95, 100, 0)
    assert not guard.observe(2410, 95, 100, 0)
    assert guard.observe(2411, 95, 100, 0)


def test_progress_or_pressure_recovery_prevents_cleanup():
    guard = SustainedMemoryGuard(policy())
    guard.observe(0, 10, 100, 0)
    guard.observe(1, 95, 100, 0)
    assert not guard.observe(12, 95, 100, 1)
    assert not guard.observe(15, 30, 100, 1)
    assert not guard.observe(25, 95, 100, 1)
    assert guard.observe(35, 95, 100, 1)


@pytest.mark.parametrize('failed_stop', [False, True])
def test_memory_cleanup_tries_standard_stop_before_emergency(tmp_path, monkeypatch, failed_stop):
    worker = build_worker_shell(tmp_path)
    worker._process = SimpleNamespace(pid=123)
    worker.log_path = tmp_path / 'cst.log'
    guard = SustainedMemoryGuard(policy())
    guard.observe(0, 10, 100, None)
    guard.observe(1, 95, 100, None)
    calls = []
    monkeypatch.setattr('csttool.managed_cstworker.owned_process_memory', lambda _: (95, 100))
    monkeypatch.setattr(worker, '_diagnose_failure', lambda phase: calls.append(phase))
    def stop():
        calls.append('stop')
        if failed_stop:
            raise ManagedWorkerShutdownError('unresponsive')
        return True
    monkeypatch.setattr(worker, 'stop', stop)
    monkeypatch.setattr(worker, 'emergency_terminate', lambda: calls.append('emergency'))
    with pytest.raises(RuntimeError, match='CST_MEMORY_GUARD'):
        worker._check_memory_guard(SimpleNamespace(task_id='task'), guard, 12)
    assert calls == ['memory-guard', 'stop'] + (['emergency'] if failed_stop else [])


def test_completion_prevents_memory_cleanup(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker._process = SimpleNamespace(pid=123)
    worker.log_path = tmp_path / 'cst.log'
    worker.completion_path.parent.mkdir()
    worker.completion_path.write_text('completion', encoding='utf-8')
    guard = SustainedMemoryGuard(policy())
    guard.observe(0, 10, 100, None)
    guard.observe(1, 95, 100, None)
    monkeypatch.setattr('csttool.managed_cstworker.owned_process_memory', lambda _: (95, 100))
    monkeypatch.setattr(worker, 'stop', lambda: pytest.fail('must not stop completed task'))
    worker._check_memory_guard(SimpleNamespace(task_id='task'), guard, 12)


def test_access_error_breaks_sustained_pressure_evidence(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker._process = SimpleNamespace(pid=123)
    guard = SustainedMemoryGuard(policy())
    guard.high_since = 1
    def denied(_):
        raise psutil.AccessDenied(pid=123)
    monkeypatch.setattr('csttool.managed_cstworker.owned_process_memory', denied)
    worker._check_memory_guard(SimpleNamespace(task_id='task'), guard, 12)
    assert guard.high_since is None


def test_sampler_counts_only_owned_root_and_descendants(monkeypatch):
    child = SimpleNamespace(pid=2, memory_info=lambda: SimpleNamespace(private=20, rss=40))
    root = SimpleNamespace(pid=1, children=lambda recursive: [child],
                           memory_info=lambda: SimpleNamespace(private=10, rss=30))
    monkeypatch.setattr('csttool.cst_memory_guard.psutil.Process', lambda pid: root if pid == 1 else pytest.fail('unowned process'))
    monkeypatch.setattr('csttool.cst_memory_guard.psutil.virtual_memory', lambda: SimpleNamespace(total=100))
    assert owned_process_memory(SimpleNamespace(pid=1, poll=lambda: None)) == (30, 100)


def test_default_worker_rotation_is_six_tasks():
    import inspect
    from csttool.cstmanager import CSTManager
    assert inspect.signature(CSTManager).parameters['max_jobs_per_worker'].default == 6

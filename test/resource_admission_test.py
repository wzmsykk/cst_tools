from types import SimpleNamespace
import pytest
from csttool.resource_admission import ResourceAdmission, ResourceBudget, ResourceAdmissionError


def test_budget_rejects_overcommit_and_releases_after_exception(monkeypatch):
    monkeypatch.setattr('csttool.resource_admission.psutil.cpu_count', lambda: 4)
    monkeypatch.setattr('csttool.resource_admission.psutil.virtual_memory', lambda: SimpleNamespace(available=100))
    admission = ResourceAdmission(ResourceBudget(estimated_threads=2, estimated_memory_bytes=40, free_headroom_bytes=10))
    admission.check(2)
    with pytest.raises(ResourceAdmissionError):
        admission.check(3)
    with pytest.raises(RuntimeError):
        with admission.reservation():
            assert admission.active == 1
            raise RuntimeError('task failed')
    assert admission.active == 0


def test_memory_drop_rejects_new_task(monkeypatch):
    monkeypatch.setattr('csttool.resource_admission.psutil.cpu_count', lambda: 4)
    monkeypatch.setattr('csttool.resource_admission.psutil.virtual_memory', lambda: SimpleNamespace(available=5))
    with pytest.raises(ResourceAdmissionError):
        ResourceAdmission(ResourceBudget(1, 10, 0)).check(1)


def test_drain_failure_does_not_start_replacement_worker(tmp_path):
    from csttool.cstmanager import CSTManager, SimulationTask
    from test.cstmanager_test import FakeGlobalConfig, FakeProjectConfig
    created = []
    class Worker:
        ID = '0'
        stops = 0
        def run_task(self, name, *, params):
            return {'TaskStatus': 'Success', 'PostProcessResult': []}
        def stop(self):
            self.stops += 1
            if self.stops == 1:
                raise RuntimeError('CST still alive')
    def factory(*args):
        created.append(Worker())
        return created[-1]
    manager = CSTManager(FakeGlobalConfig(tmp_path), FakeProjectConfig(tmp_path), [],
                         maxTask=1, worker_factory=factory, max_jobs_per_worker=1)
    try:
        with pytest.raises(RuntimeError, match='drain failed'):
            manager.run_batch([SimulationTask({}, 'one'), SimulationTask({}, 'two')])
        assert len(created) == 1
    finally:
        manager.stop()

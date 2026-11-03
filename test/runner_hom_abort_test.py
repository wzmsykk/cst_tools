"""HOM durable adoption faults with synthetic fields; real Runner evidence is separate."""
import json
from pathlib import Path
import logging
import pytest
from csttool.configuration import read_json, write_json_atomic
from csttool.hom_scan_algorithm import HomScanAlgorithm
from csttool.checkpoint_adoption import mark_adopted, reconcile_checkpoint_adoptions
from csttool.result_reconciliation import file_hash
from csttool.run_store import RunStore
from csttool.runtime_protocol import new_session_id
from test.support import validate_runner_hom_abort as probe


class ControllerCrash(BaseException):
    """Bypass normal exception cleanup, without claiming an OS process crash."""


class ReceiptManager:
    """Native peer substitute; use production scanner/checkpoint/RunStore adoption."""
    def __init__(self, project, point):
        from csttool.configuration import GlobalSettings
        self.currProjectDir = project
        self.cstProjPath = project / 'processed.cst';self.cstProjPath.write_bytes(b'synthetic baseline')
        self.global_settings = GlobalSettings()
        self.logger = logging.getLogger('hom-adoption-fault')
        self.run_store = RunStore(project, project / 'logs/run')
        self.cache = {};self.actual_calls = [];self.receipts = {}
        self.snapshot = None;self.point = point;self.fired = False
    def execute(self, task):
        key = json.dumps([task.job_name, task.params], sort_keys=True)
        if key in self.cache:return self.cache[key]
        self.actual_calls.append(key)
        if len(self.actual_calls) == 1:
            return dict(TaskStatus='Failure', FailureReport='SOLVER_FAILED: synthetic aborted peer')
        task_id, session = new_session_id(), new_session_id()
        workspace = self.run_store.directory / 'workers/0' / session
        snapshot = self.currProjectDir / 'result' / task_id / 'project.cst'
        snapshot.parent.mkdir(parents=True);snapshot.write_bytes(b'synthetic result, not a native solve')
        frequency = 105. if task.params['fmin'] < 105 else 114.
        values = [dict(resultName=name, value=value, params=dict(iModeNumber=1))
                  for name,value in [('frequency', frequency), ('rq', 4.)]]
        receipt = workspace / 'received' / (task_id + '.json')
        write_json_atomic(receipt, dict(task_id=task_id, session_id=session, workspace=str(workspace),
            status='Success', phase='acknowledged', job=task.job_name, parameters=task.params,
            postprocess=values, snapshot=str(snapshot), snapshot_sha256=file_hash(snapshot)))
        for event in ('submitted','received','acknowledged'):self.run_store.event(task_id, event)
        result = dict(TaskStatus='Success', TaskID=task_id, RunName=task.job_name, RunParameters=task.params,
                      PostProcessResult=values, ProjectSnapshot=str(snapshot), ReceiptPath=str(receipt))
        self.snapshot = snapshot;self.receipts[task_id] = receipt;self.cache[key] = result
        if self.point == 'received' and not self.fired:
            self.fired = True;raise ControllerCrash('after durable receipt, before algorithm return')
        return result
    def get_confirmed_snapshot(self):return self.snapshot
    def restore_project_snapshot(self, snapshot):self.snapshot = Path(snapshot)
    def adopt_result(self, task):
        if self.point == 'checkpoint' and not self.fired:
            assert probe.confirmed(self.currProjectDir, task)
            self.fired = True;raise ControllerCrash('checkpoint before adoption')
        mark_adopted(self.receipts[task], self.run_store, task)


def algorithm(manager, resume=False):
    value = HomScanAlgorithm(manager, [])
    value.set_cst_parameters([])
    value.set_editable_attributes(dict(fmin=100, fmax=110, endfreq=110, mesh_cells_per_wavelength=8))
    value.resume_requested = resume
    return value


@pytest.mark.parametrize('point', ['received','checkpoint','journal','receipt'])
def test_aborted_hom_repair_and_resume_adopt_once_without_replaying_received_task(tmp_path, monkeypatch, point):
    manager = ReceiptManager(tmp_path, point)
    if point in ('journal','receipt'):
        import csttool.run_store as store
        import csttool.checkpoint_adoption as adopter
        module = store if point == 'journal' else adopter
        original = module.write_json_atomic
        def write(path, value):
            target = (Path(path).name == 'attempt.json' and value.get('event') == 'algorithm_adopted'
                      if point == 'journal' else value.get('phase') == 'algorithm_adopted')
            if target and not manager.fired:
                manager.fired = True;raise ControllerCrash(point)
            return original(path, value)
        monkeypatch.setattr(module, 'write_json_atomic', write)
    with pytest.raises(ControllerCrash):algorithm(manager).start()
    target = next(iter(manager.receipts))
    receipt = manager.receipts[target]
    frozen_snapshot = file_hash(read_json(receipt)['snapshot'])
    saved = file_hash(probe.checkpoint(tmp_path))
    before_calls = list(manager.actual_calls)
    repaired = reconcile_checkpoint_adoptions(tmp_path)
    assert repaired == ([] if point == 'received' else [target])
    stable = probe.marker_hashes(tmp_path)
    reconcile_checkpoint_adoptions(tmp_path)
    assert probe.marker_hashes(tmp_path) == stable
    assert file_hash(probe.checkpoint(tmp_path)) == saved
    assert manager.actual_calls == before_calls
    report = algorithm(manager, resume=True).start()
    assert target in report.adopted_task_ids
    assert [m.frequency for m in report.modes] == [105.]
    assert report.modes[0].values['rq'] == 4.
    assert file_hash(read_json(receipt)['snapshot']) == frozen_snapshot
    probe.adoption(tmp_path, report.adopted_task_ids)
    assert len(manager.actual_calls) == len(set(manager.actual_calls)), 'no synthetic native call replay'
    assert read_json(receipt)['phase'] == 'algorithm_adopted'
    calls = list(manager.actual_calls)
    algorithm(manager, resume=True).start()
    assert manager.actual_calls == calls
    probe.adoption(tmp_path, report.adopted_task_ids)


def test_gate_requires_task_in_confirmed_modes(tmp_path):
    assert not probe.confirmed(tmp_path, 'candidate')
    write_json_atomic(probe.checkpoint(tmp_path), dict(report=dict(modes=[dict(task_id='confirmed')])))
    assert not probe.confirmed(tmp_path, 'candidate')
    assert probe.confirmed(tmp_path, 'confirmed')


@pytest.mark.parametrize('point, index, count', [('received','acknowledged',0),
    ('checkpoint','acknowledged',0),('journal','acknowledged',1),('receipt','algorithm_adopted',1)])
def test_fault_boundary_refuses_wrong_adoption_timing(point, index, count):
    valid = dict(receipt='acknowledged',indexes=[index],events=[count])
    probe.validate_boundary(point, valid)
    with pytest.raises(AssertionError):probe.validate_boundary(point, {**valid,'events':[count+1]})


def test_suite_failure_after_one_pass_must_not_report_whole_matrix_passed(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import csttool.acceptance_session as acceptance
    from test.support import validate_public_faults as faults
    executable = tmp_path/'cst.exe';executable.touch()
    (tmp_path/'artifacts').mkdir()
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    monkeypatch.setattr(probe, 'uuid4', lambda:SimpleNamespace(hex='suite'))
    monkeypatch.setattr(probe.sys, 'argv', ['probe','--run-cst','--case','all','--cst-exe',str(executable)])
    monkeypatch.setattr(probe.shutil,'disk_usage',lambda _:SimpleNamespace(free=3*1024**3))
    monkeypatch.setattr(acceptance,'exclusive_probe',lambda _:nullcontext())
    monkeypatch.setattr(acceptance,'cst_processes',lambda:[])
    monkeypatch.setattr(faults,'cleanup_case',lambda *args:0)
    def run(project, executable, case):
        if case == 'received':raise OSError('synthetic suite interruption')
        project.mkdir()
        return dict(passed=True,case=case,remaining_cst=[])
    monkeypatch.setattr(probe,'run_case',run)
    with pytest.raises(OSError):probe.main()
    summary = read_json(tmp_path/'artifacts/runner-hom-abort-suite/report.json')
    assert summary['passed'] is False

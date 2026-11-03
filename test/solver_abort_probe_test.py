"""Offline fault-driver contracts, not real solver-return acceptance."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test.support import validate_solver_abort as probe


def project(path, *, running=True, outcome=True):
    calls = []
    def abort():
        calls.append('abort')
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    return SimpleNamespace(filename=lambda: str(path),
        modeler=SimpleNamespace(is_solver_running=lambda: running, abort_solver=abort)), calls


def make_session(tmp_path):
    (tmp_path / 'lifecycle.log').write_text('stage=solver-start; calling EigenmodeSolver.Start\n', encoding='utf-8')
    identity = dict(pid=123, create_time=456., executable='owned.exe', project=str(tmp_path / 'worker-input.cst'))
    closed = []
    def verify(value):
        assert value == identity
        return SimpleNamespace(CloseHandle=lambda handle: closed.append(handle)), 'owned-handle'
    return identity, closed, verify


def test_abort_once_after_native_running_and_persist_intent_before_effect(tmp_path):
    identity, closed, verify = make_session(tmp_path)
    value, calls = project(identity['project'])
    original = value.modeler.abort_solver
    def effect():
        assert json.loads((tmp_path / 'abort-intent.json').read_text())['attempt'] == 1
        return original()
    value.modeler.abort_solver = effect
    assert probe.abort_when_running(value, tmp_path, identity, verify=verify) is True
    assert calls == ['abort'] and closed == ['owned-handle']
    assert json.loads((tmp_path / 'abort-result.json').read_text()) == dict(returned=True, attempt=1)


def test_lost_abort_response_is_unknown_and_not_retried(tmp_path):
    identity, closed, verify = make_session(tmp_path)
    value, calls = project(identity['project'], outcome=RuntimeError('response lost'))
    with pytest.raises(RuntimeError, match='response lost'):
        probe.abort_when_running(value, tmp_path, identity, verify=verify)
    assert calls == ['abort'] and closed == ['owned-handle']
    assert (tmp_path / 'abort-intent.json').exists() and not (tmp_path / 'abort-result.json').exists()
    with pytest.raises(RuntimeError, match='already reserved'):
        probe.abort_when_running(value, tmp_path, identity, verify=verify)
    assert calls == ['abort']


def test_concurrent_bridge_reservation_wins_without_second_effect(tmp_path):
    identity, closed, verify = make_session(tmp_path)
    value, calls = project(identity['project'])
    def competing_verify(value):
        (tmp_path / 'abort-intent.json').write_text('{"attempt":1}')
        return verify(value)
    with pytest.raises(FileExistsError):
        probe.abort_when_running(value, tmp_path, identity, verify=competing_verify)
    assert not calls and closed == ['owned-handle']


def test_wrong_project_has_no_native_abort(tmp_path):
    identity, closed, verify = make_session(tmp_path)
    value, calls = project(tmp_path / 'unrelated.cst')
    with pytest.raises(ValueError, match='project path mismatch'):
        probe.abort_when_running(value, tmp_path, identity, verify=verify)
    assert not calls and closed == ['owned-handle']
    assert not (tmp_path / 'abort-intent.json').exists()


@pytest.mark.parametrize('reason', ['native PID reused', 'native executable mismatch', 'access denied'])
def test_unconfirmed_process_identity_never_aborts(tmp_path, reason):
    identity, _, _ = make_session(tmp_path)
    value, calls = project(identity['project'])
    def verify(_):
        raise ValueError(reason)
    with pytest.raises(ValueError, match=reason):
        probe.abort_when_running(value, tmp_path, identity, verify=verify)
    assert not calls and not (tmp_path / 'abort-intent.json').exists()


def test_no_trigger_expires_without_native_abort(tmp_path):
    identity, _, verify = make_session(tmp_path)
    value, calls = project(identity['project'], running=False)
    ticks = iter([0, 0, 91])
    with pytest.raises(RuntimeError, match='trigger not observed'):
        probe.abort_when_running(value, tmp_path, identity, verify=verify,
                                 clock=lambda: next(ticks), pause=lambda _: None)
    assert not calls and not (tmp_path / 'abort-intent.json').exists()


def test_production_run_uses_explicit_central_lifecycle_path(tmp_path):
    identity, closed, verify = make_session(tmp_path)
    observed = tmp_path / 'central' / 'lifecycle.log';observed.parent.mkdir()
    (tmp_path / 'lifecycle.log').replace(observed)
    value, calls = project(identity['project'])
    probe.abort_when_running(value, tmp_path, identity, verify=verify, lifecycle_path=observed)
    assert calls == ['abort'] and closed == ['owned-handle']


def test_cancel_before_trigger_does_not_abort(tmp_path):
    identity, _, verify = make_session(tmp_path)
    value, calls = project(identity['project'])
    (tmp_path / 'cancel-bridge').touch()
    with pytest.raises(RuntimeError, match='cancelled before abort'):
        probe.abort_when_running(value, tmp_path, identity, verify=verify)
    assert not calls


def test_foreign_parent_bridge_rejected_before_connect(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    root = tmp_path / 'artifacts/session';root.mkdir(parents=True)
    intent = root / 'bridge-intent.json'
    intent.write_text(json.dumps(dict(parent_pid=-1)))
    with pytest.raises(ValueError, match='parent mismatch'):
        probe.bridge(intent)


def test_cli_foreign_bridge_path_does_not_write_failure_outside_artifacts(tmp_path, monkeypatch):
    intent = tmp_path / 'foreign-intent.json';intent.write_text('{}')
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    monkeypatch.setattr(probe.sys, 'argv', ['probe', '--bridge', str(intent)])
    with pytest.raises(SystemExit) as error:
        probe.main()
    assert error.value.code == 2
    assert not (tmp_path / 'bridge-failure.json').exists()


def test_unverified_launcher_rejected_without_searching_other_processes(tmp_path):
    worker = SimpleNamespace(root=tmp_path, _process=SimpleNamespace(pid=123))
    with pytest.raises(ValueError, match='launcher ownership not confirmed'):
        probe.owned_environment(worker)


def test_driver_checks_both_nested_project_closures_and_two_solver_calls(tmp_path, monkeypatch):
    from dataclasses import dataclass
    import shutil
    import csttool.acceptance_session as acceptance
    import csttool.managed_cstworker as managed
    import csttool.project_session_recovery as recovery
    from test.support import validate_hom_recovery_native as fixture
    from test.support import validate_public_faults as faults
    source = tmp_path / 'source.cst';source.write_bytes(b'unchanged expressions')
    root = tmp_path / 'case';root.mkdir()
    class Preprocessor:
        def __init__(self, *args):pass
        def preprocess(self, source, output, *args, **kwargs):shutil.copyfile(source, output)
    class Worker:
        def __init__(self, identity, config):
            self.identity = identity
            self.root = Path(config['taskFileDir']) / 'session'
            self.root.mkdir(parents=True)
            self.project_path = self.root / 'worker-input.cst'
        def run_task(self, name, **kwargs):
            (self.root / 'lifecycle.log').write_text('calling EigenmodeSolver.Start')
            if self.identity == '0':
                return dict(TaskStatus='Failure', PostProcessResult=None, ProjectSnapshot=None,
                            FailureReport='SOLVER_FAILED: solver-result failed: no results')
            return dict(TaskStatus='Success', ProjectSnapshot='confirmed.cst')
    class Helper:
        def __init__(self, command, **kwargs):
            directory = Path(command[-1]).parent
            probe.write(directory / 'bridge-ready.json', {})
            probe.write(directory / 'abort-result.json', dict(returned=True, attempt=1))
        def poll(self):return 0
        def wait(self, **kwargs):return 0
    @dataclass
    class Closed:
        standard_closed: bool = True
    visited = []
    def discover(path):
        visited.append(path)
        return [SimpleNamespace(closure=Closed())]
    monkeypatch.setattr(managed, 'ManagedCSTWorker', Worker)
    monkeypatch.setattr(fixture, 'FixturePreprocessor', Preprocessor)
    monkeypatch.setattr(fixture, 'stop', lambda *args, **kwargs: None)
    monkeypatch.setattr(acceptance, 'cst_processes', lambda: [])
    monkeypatch.setattr(faults, 'cleanup_case', lambda *args: 0)
    monkeypatch.setattr(recovery, 'discover_managed_sessions', discover)
    monkeypatch.setattr(probe, 'owned_environment', lambda worker: dict(project=str(worker.project_path)))
    monkeypatch.setattr(probe.subprocess, 'Popen', Helper)
    result = probe.run(tmp_path / 'CST.exe', source, root)
    assert result['passed'] and result['solver_calls'] == 2
    assert visited == [root / 'aborted', root / 'replacement']
    assert result['classification'] == 'start-return-1-without-results'


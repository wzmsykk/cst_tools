import pytest
from csttool.configuration import write_json_atomic,read_json
from csttool.definition_sessions import definition_session_facts,recover_definition_sessions
from csttool.lifecycle_diagnostics import project_lifecycle
from csttool.recovery_control import RecoveryPaused


@pytest.fixture(autouse=True)
def isolate_process_inventory(monkeypatch):
    monkeypatch.setattr('csttool.acceptance_session.task_project_processes',lambda path:iter(()))


def session(tmp_path,**fields):
    path=tmp_path/'control/definitions/doc/rev/verification-one/saved/session-status.json'
    write_json_atomic(path,dict(exit_confirmed=False,**fields))
    return path


def test_confirmed_exit_is_visible_in_project_and_gui(tmp_path):
    path=session(tmp_path,exit_code=0)
    write_json_atomic(path,dict(exit_confirmed=True,exit_code=0))
    facts=project_lifecycle(tmp_path)
    assert facts['session_count']==1 and not facts['recovery_required']
    from GUI.lifecycle_display import lifecycle_lines
    assert any('G03定义验证' in x for x in lifecycle_lines(dict(lifecycle=facts)))


def test_missing_identity_blocks_recovery_and_shutdown(tmp_path):
    session(tmp_path)
    assert project_lifecycle(tmp_path)['session_safety']=='unknown'
    with pytest.raises(RuntimeError,match='ownership unknown'):recover_definition_sessions(tmp_path)
    from csttool.runner import verify_shutdown_safety
    with pytest.raises(ValueError,match='safety unresolved'):verify_shutdown_safety(tmp_path)


def test_dead_or_reused_pid_reconciles_without_granting_ready(tmp_path,monkeypatch):
    path=session(tmp_path,owned=[dict(pid=123,create_time=10)])
    class Other:
        def create_time(self):return 20
        def is_running(self):raise AssertionError('reused PID must not be waited')
    monkeypatch.setattr('csttool.definition_sessions.psutil.Process',lambda pid:Other())
    assert definition_session_facts(tmp_path)[0]['needs_recovery']
    recover_definition_sessions(tmp_path)
    report=read_json(path)
    assert report['disposition']=='abandoned-dead' and 'exit_code' not in report
    assert not definition_session_facts(tmp_path)[0]['standard_closed']
    assert not definition_session_facts(tmp_path)[0]['needs_recovery']


def test_live_wait_is_bounded_and_pause_preserves_evidence(tmp_path,monkeypatch):
    path=session(tmp_path,owned=[dict(pid=123,create_time=10)])
    class Live:
        def create_time(self):return 10
        def is_running(self):return True
    monkeypatch.setattr('csttool.definition_sessions.psutil.Process',lambda pid:Live())
    with pytest.raises(TimeoutError):recover_definition_sessions(tmp_path,timeout=0)
    assert not read_json(path)['exit_confirmed']
    def pause():raise RecoveryPaused('pause')
    with pytest.raises(RecoveryPaused):recover_definition_sessions(tmp_path,pause_check=pause)


def test_normal_closed_failure_needs_disposition_not_success(tmp_path):
    path=session(tmp_path,exit_code=1)
    write_json_atomic(path,dict(exit_confirmed=True,exit_code=1))
    recover_definition_sessions(tmp_path)
    item=definition_session_facts(tmp_path)[0]
    assert not item['standard_closed'] and not item['needs_recovery']


def test_prior_producer_exit_code_from_persisted_phase_journal(tmp_path):
    path=session(tmp_path)
    write_json_atomic(path,dict(exit_confirmed=True))
    write_json_atomic(path.parent.parent/'verification.json',dict(sessions=[dict(phase='saved',exit_confirmed=True,exit_code=0)]))
    assert definition_session_facts(tmp_path)[0]['standard_closed']


def test_same_project_path_process_blocks_even_if_launcher_is_gone(tmp_path,monkeypatch):
    session(tmp_path,owned=[dict(pid=123,create_time=10)])
    class Reused:
        def create_time(self):return 20
    monkeypatch.setattr('csttool.definition_sessions.psutil.Process',lambda pid:Reused())
    monkeypatch.setattr('csttool.acceptance_session.task_project_processes',lambda path:iter([object()]))
    assert definition_session_facts(tmp_path)[0]['process_state']=='running'


def test_probe_wait_never_tracks_reused_launcher(tmp_path,monkeypatch):
    from csttool.acceptance_session import wait_probe
    class Unrelated:
        pid=123
        def create_time(self):return 20
        def children(self,**kwargs):raise AssertionError('must not enumerate unrelated PID descendants')
    class Launcher:
        pid=123
        def poll(self):return 0
    monkeypatch.setattr('csttool.acceptance_session.psutil.Process',lambda pid:Unrelated())
    monkeypatch.setattr('csttool.acceptance_session.cst_processes',lambda:[])
    report=wait_probe(Launcher(),tmp_path,expected_launcher_identity=(123,10))
    assert report['exit_confirmed'] and report['owned']==[]


def test_bootstrap_is_displayed_as_new_project_not_frozen_g03(tmp_path):
    path=tmp_path/'control/definitions/doc/rev/verification-bootstrap/created/session-status.json'
    write_json_atomic(path,dict(exit_confirmed=True,exit_code=0))
    facts=project_lifecycle(tmp_path)
    assert facts['sessions'][0]['model_state']=='saved-empty-project'
    from GUI.lifecycle_display import lifecycle_lines
    assert any('G02工程创建' in line for line in lifecycle_lines(dict(lifecycle=facts)))


@pytest.mark.parametrize('level',[0,1,3])
def test_nested_geometry_verification_is_never_missed_by_any_guard(tmp_path,level):
    from csttool.definition_verifier import assert_definition_sessions_closed
    directory=tmp_path/'control/definitions/doc/operation/verification-edit/saved'
    for i in range(level+1):directory=directory/('verification-managed-'+str(i))/'saved'
    path=directory/'session-status.json';write_json_atomic(path,dict(exit_confirmed=False))
    assert len(definition_session_facts(tmp_path))==1
    assert project_lifecycle(tmp_path)['session_safety']=='unknown'
    with pytest.raises(ValueError,match='exit unconfirmed'):
        assert_definition_sessions_closed(tmp_path/'control/definitions')
    with pytest.raises(RuntimeError,match='ownership unknown'):recover_definition_sessions(tmp_path)
    write_json_atomic(path,dict(exit_confirmed=True,exit_code=0))
    assert_definition_sessions_closed(tmp_path/'control/definitions')
    assert not project_lifecycle(tmp_path)['recovery_required']


@pytest.mark.parametrize('report',[[],None,dict(exit_confirmed=True,exit_code=False)])
def test_malformed_or_boolean_exit_code_is_not_standard_close(tmp_path,report):
    path=session(tmp_path);write_json_atomic(path,report)
    facts=definition_session_facts(tmp_path)[0]
    assert not facts['standard_closed'] and facts['needs_recovery']
    if not isinstance(report,dict):
        from csttool.definition_verifier import assert_definition_sessions_closed
        with pytest.raises(ValueError):assert_definition_sessions_closed(tmp_path/'control/definitions')

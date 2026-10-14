import subprocess
import sys

import pytest

from csttool import acceptance_session as session


def test_exclusive_probe_rejects_competitor_and_releases(tmp_path, monkeypatch):
    monkeypatch.setattr(session, 'cst_processes', lambda: [])
    with session.exclusive_probe(tmp_path):
        with pytest.raises((RuntimeError, OSError)):
            with session.exclusive_probe(tmp_path):
                pass
    with session.exclusive_probe(tmp_path):
        pass


def test_existing_cst_is_not_touched(tmp_path, monkeypatch):
    monkeypatch.setattr(session, 'cst_processes', lambda: [{'pid': 123}])
    with pytest.raises(RuntimeError, match='not idle'):
        with session.exclusive_probe(tmp_path):
            pass


def test_exit_confirmed(tmp_path, monkeypatch):
    monkeypatch.setattr(session, 'cst_processes', lambda: [])
    process = subprocess.Popen([sys.executable, '-c', 'pass'])
    result = session.wait_probe(process, tmp_path, stage_timeout=10)
    assert result['exit_confirmed']


def test_stall_does_not_kill(tmp_path, monkeypatch):
    monkeypatch.setattr(session, 'cst_processes', lambda: [])
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])
    try:
        with pytest.raises(RuntimeError, match='retained'):
            session.wait_probe(process, tmp_path, stage_timeout=0.1)
        assert process.poll() is None
    finally:
        # Python test fixture only; never a CST process.
        process.terminate()
        process.wait()


def test_late_child_is_not_competitor_but_unrelated_process_remains(tmp_path, monkeypatch):
    from types import SimpleNamespace
    tick = {'value': 0}
    child = SimpleNamespace(pid=2, create_time=lambda:2., is_running=lambda:tick['value']<3)
    def children(recursive):
        tick['value'] += 1
        return [child] if tick['value']>=2 else []
    root = SimpleNamespace(pid=1, create_time=lambda:1., children=children,
                           is_running=lambda:tick['value']<3)
    monkeypatch.setattr(session.psutil,'Process',lambda pid:root)
    monkeypatch.setattr(session,'cst_processes',lambda:[
        {'pid':2,'create_time':2.,'name':'CST child'},
        {'pid':9,'create_time':9.,'name':'CST unrelated'}])
    monkeypatch.setattr(session.time,'sleep',lambda seconds:None)
    launcher = SimpleNamespace(pid=1,poll=lambda:0 if tick['value']>=3 else None)
    result = session.wait_probe(launcher,tmp_path)
    assert result['exit_confirmed']
    assert [p['pid'] for p in result['foreign_processes']]==[9]


def test_long_rebuild_is_not_total_timeout_but_completion_exit_is_bounded(tmp_path, monkeypatch):
    from types import SimpleNamespace
    clock = {'value': 0.}
    root = SimpleNamespace(pid=1, create_time=lambda:1., children=lambda recursive:[],
                           is_running=lambda:True)
    monkeypatch.setattr(session.psutil, 'Process', lambda pid:root)
    monkeypatch.setattr(session, 'cst_processes', lambda:[])
    monkeypatch.setattr(session.time, 'monotonic', lambda:clock['value'])
    def advance(seconds):
        clock['value'] += 200
        if clock['value'] >= 600:
            (tmp_path / 'completion.txt').write_text('SUCCESS')
    monkeypatch.setattr(session.time, 'sleep', advance)
    (tmp_path / 'stage.txt').write_text('rebuild')
    launcher = SimpleNamespace(pid=1, poll=lambda:None)
    with pytest.raises(RuntimeError, match='exit-unconfirmed'):
        session.wait_probe(launcher, tmp_path, stage_timeout=180, exit_timeout=60,
                           completion_names=('completion.txt',), unbounded_stages=('rebuild',))
    assert clock['value'] >= 800


@pytest.mark.parametrize('current_time,expected_foreign', [(9., []), (10., [9])])
def test_preexisting_instance_is_ignored_but_recycled_pid_is_not(tmp_path, monkeypatch, current_time, expected_foreign):
    from types import SimpleNamespace
    baseline = [{'pid':9, 'create_time':9., 'name':'independent CST'}]
    root = SimpleNamespace(pid=1, create_time=lambda:1., children=lambda recursive:[], is_running=lambda:False)
    monkeypatch.setattr(session.psutil, 'Process', lambda pid:root)
    monkeypatch.setattr(session, 'cst_processes', lambda:[dict(baseline[0], create_time=current_time)])
    result = session.wait_probe(SimpleNamespace(pid=1, poll=lambda:0), tmp_path,
                                preexisting_processes=baseline)
    assert result['exit_confirmed']
    assert result['preexisting_processes'] == baseline
    assert [p['pid'] for p in result['foreign_processes']] == expected_foreign


def test_exited_unknown_process_does_not_remain_in_foreign_list(tmp_path, monkeypatch):
    from types import SimpleNamespace
    tick = {'value':0}
    def children(recursive):
        tick['value'] += 1
        return []
    root = SimpleNamespace(pid=1, create_time=lambda:1., children=children,
                           is_running=lambda:tick['value']<2)
    monkeypatch.setattr(session.psutil, 'Process', lambda pid:root)
    monkeypatch.setattr(session, 'cst_processes', lambda:[{'pid':9, 'create_time':9.}]
                        if tick['value']==1 else [])
    monkeypatch.setattr(session.time, 'sleep', lambda seconds:None)
    result = session.wait_probe(SimpleNamespace(pid=1, poll=lambda:0 if tick['value']>=2 else None), tmp_path)
    assert result['foreign_processes'] == []


def test_preexisting_instance_does_not_hide_owned_child_exit_timeout(tmp_path, monkeypatch):
    from types import SimpleNamespace
    clock = {'value':0.}
    child = SimpleNamespace(pid=2, create_time=lambda:2., is_running=lambda:True)
    root = SimpleNamespace(pid=1, create_time=lambda:1., children=lambda recursive:[child], is_running=lambda:False)
    monkeypatch.setattr(session.psutil, 'Process', lambda pid:root)
    monkeypatch.setattr(session, 'cst_processes', lambda:[{'pid':9, 'create_time':9.}])
    monkeypatch.setattr(session.time, 'monotonic', lambda:clock['value'])
    monkeypatch.setattr(session.time, 'sleep', lambda seconds:clock.update(value=clock['value']+1))
    (tmp_path / 'completed.txt').write_text('SUCCESS')
    with pytest.raises(RuntimeError, match='exit-unconfirmed'):
        session.wait_probe(SimpleNamespace(pid=1, poll=lambda:0), tmp_path, exit_timeout=1,
                           preexisting_processes=[{'pid':9, 'create_time':9.}])


def test_task_scoped_monitor_ignores_inaccessible_other_user(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root = SimpleNamespace(pid=1, create_time=lambda:1., children=lambda recursive:[], is_running=lambda:False)
    monkeypatch.setattr(session.psutil, 'Process', lambda pid:root)
    monkeypatch.setattr(session, 'task_project_processes', lambda project:[])
    def inaccessible():
        raise session.psutil.AccessDenied(99)
    monkeypatch.setattr(session, 'cst_processes', inaccessible)
    result = session.wait_probe(SimpleNamespace(pid=1, poll=lambda:0), tmp_path, task_project=tmp_path/'copy.cst')
    assert result['exit_confirmed']
    assert result['ownership_scope'] == 'task-project'


def test_exact_project_argument_association_not_substring_or_user(tmp_path, monkeypatch):
    from types import SimpleNamespace
    target = str(tmp_path/'copy.cst')
    match = SimpleNamespace(name=lambda:'CST DESIGN ENVIRONMENT.exe', cmdline=lambda:['cst.exe','-b',target])
    other = SimpleNamespace(name=lambda:'CST DESIGN ENVIRONMENT.exe', cmdline=lambda:['cst.exe','-b',target+'.other'])
    def denied():
        raise session.psutil.AccessDenied(99)
    hidden = SimpleNamespace(name=denied, cmdline=denied)
    monkeypatch.setattr(session.psutil, 'process_iter', lambda attrs:[other,hidden,match])
    assert list(session.task_project_processes(target)) == [match]


def test_project_linked_orphan_still_prevents_exit(tmp_path, monkeypatch):
    from types import SimpleNamespace
    clock = {'value':0.}
    related = SimpleNamespace(pid=2, create_time=lambda:2., children=lambda recursive:[], is_running=lambda:True)
    root = SimpleNamespace(pid=1, create_time=lambda:1., children=lambda recursive:[], is_running=lambda:False)
    monkeypatch.setattr(session.psutil, 'Process', lambda pid:root)
    monkeypatch.setattr(session, 'task_project_processes', lambda project:[related])
    monkeypatch.setattr(session, 'cst_processes', lambda:[{'pid':99,'create_time':99.}])
    monkeypatch.setattr(session.time, 'monotonic', lambda:clock['value'])
    monkeypatch.setattr(session.time, 'sleep', lambda seconds:clock.update(value=clock['value']+1))
    (tmp_path/'completed.txt').write_text('SUCCESS')
    with pytest.raises(RuntimeError, match='exit-unconfirmed'):
        session.wait_probe(SimpleNamespace(pid=1,poll=lambda:0), tmp_path, exit_timeout=1, task_project=tmp_path/'copy.cst')

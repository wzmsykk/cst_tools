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

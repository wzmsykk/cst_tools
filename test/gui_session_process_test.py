"""Reopen actual GUI processes and restore state; no calculation is auto-submitted."""
import os
from pathlib import Path
import subprocess
import sys
import pytest
from GUI.session_store import GuiSessionStore
from csttool.configuration import read_json, write_json_atomic
from csttool.runner_client import RunnerClient
from test.exit_process_test import wait

ROOT = Path(__file__).resolve().parents[1]


def observe(project, session, name):
    with (project.parent / (name + '.log')).open('wb') as output:
        child = subprocess.Popen([sys.executable,str(ROOT/'test/support/exit_gui_probe.py'),
            '--project',str(project),'--choice','detach','--restore-session',str(session.path)],
            cwd=ROOT,env=dict(os.environ,QT_QPA_PLATFORM='offscreen'),stdout=output,stderr=subprocess.STDOUT)
    assert child.wait(timeout=30)==0, (project.parent/(name+'.log')).read_text(errors='replace')
    result=read_json(project/'gui-exit-probe.json')
    assert result['controller_closed'] and result['project']==str(project.resolve())
    return result


def test_two_gui_processes_attach_same_running_runner_without_new_start(tmp_path):
    project=tmp_path/'project'; project.mkdir()
    session=GuiSessionStore(tmp_path/'gui-session.json'); session.remember(project)
    with (tmp_path/'runner.log').open('wb') as output:
        runner=subprocess.Popen([sys.executable,'-m','csttool.runner','--project',str(project),'--fake'],
                                cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
    client=RunnerClient(project)
    try:
        original=wait(client.status)
        client.command('claim'); started=client.command('start',{'algorithm':{'fake_delay':1}})
        client.command('release')
        wait(lambda: client.status()['state']=='RUNNING')
        first=observe(project,session,'first-gui'); second=observe(project,session,'second-gui')
        for result in (first,second):
            assert result['runner_status']['instance_id']==original['instance_id']
            assert result['runner_status']['run_id']==started['run_id']
        commands=[read_json(path)['command']['operation'] for path in (project/'control/commands').glob('*.json')]
        assert commands.count('start')==1 and 'recover' not in commands
        assert runner.poll() is None
    finally:
        client.connect(launch=False); client.command('claim')
        status=client.status()
        if status['state'] in {'PREPARING','RUNNING','STOPPING'}:
            client.command('stop',run_id=status['run_id']); wait(lambda:not client.status()['execution_active'])
        client.shutdown_and_wait(run_id=client.status()['run_id']); runner.wait(timeout=10)


def test_gui_reopen_starts_only_state_service_and_restores_disk_history(tmp_path):
    project=tmp_path/'project'; project.mkdir()
    session=GuiSessionStore(tmp_path/'gui-session.json'); session.remember(project)
    directory=project/'logs/previous'; directory.mkdir(parents=True)
    (directory/'application.jsonl').write_text('{"message":"previous disk event","level":"INFO"}\n')
    write_json_atomic(project/'control/status.json',dict(state='INTERRUPTED',run_id='saved-run',
        log_directory=str(directory),coverage={'confirmed_frontier':812.5},mode_count=4))
    client=RunnerClient(project)
    try:
        result=observe(project,session,'offline-gui')
        assert result['runner_status']['run_id']=='saved-run'
        assert result['runner_status']['coverage']['confirmed_frontier']==812.5
        assert 'previous disk event' in result['log_messages']
        operations=[read_json(path)['command']['operation'] for path in (project/'control/commands').glob('*.json')]
        assert not set(operations)&{'start','recover'}
        assert not (project/'temp').exists()
    finally:
        client.connect(launch=False); client.shutdown_and_wait(run_id=client.status()['run_id'])

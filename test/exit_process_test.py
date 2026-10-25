"""Real GUI/Runner Python processes and Windows cwd release, explicitly no CST."""
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import pytest
from csttool.configuration import read_json
from csttool.runner_client import RunnerClient

ROOT = Path(__file__).resolve().parents[1]


def wait(predicate, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            value = predicate()
            if value: return value
        except (OSError, ValueError): pass
        time.sleep(.025)
    raise AssertionError('process acceptance timed out')


@pytest.mark.parametrize('scenario', ['idle', 'running', 'failed', 'detach', 'lost-response', 'console'])
def test_gui_exit_releases_owned_processes_and_directory(tmp_path, scenario):
    release, project = tmp_path / 'release', tmp_path / 'project'
    release.mkdir(); project.mkdir()
    shutil.copytree(ROOT / 'data', release / 'data')  # Minimal real release resources.
    moved = tmp_path / 'released-directory'
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1')
    with (tmp_path / 'runner.log').open('wb') as output:
        runner = subprocess.Popen([sys.executable, '-m', 'csttool.runner', '--project', str(project), '--fake'],
                                  cwd=release, env=env, stdout=output, stderr=subprocess.STDOUT)
    client = RunnerClient(project)
    gui = None
    try:
        wait(client.status)
        if os.name == 'nt':
            with pytest.raises(OSError) as held: release.rename(moved)
            assert held.value.winerror in (5, 32)  # Nonempty directory can otherwise be renamed.
        if scenario in {'running', 'failed'}:
            client.command('claim')
            if scenario == 'failed':
                payload = dict(kind='standard', tasks=[dict(job='invalid-radius', parameters={'R': 'not-a-number'})])
            else:
                payload = {'algorithm': {'fake_delay': 1}}
            client.command('start', payload)
            wait(lambda: client.status()['state'] == ('FAILED' if scenario == 'failed' else 'RUNNING'))
            client.command('release')
        command = [sys.executable, str(ROOT / 'test/support/exit_gui_probe.py'), '--project', str(project),
                   '--choice', 'detach' if scenario == 'detach' else 'stop']
        if scenario == 'lost-response': command.append('--lost-shutdown-response')
        if scenario == 'console':
            if os.name != 'nt': pytest.skip('Windows cmd.exe launcher')
            command = ['cmd.exe', '/d', '/c', subprocess.list2cmdline(command)]
        with (tmp_path / 'gui.log').open('wb') as output:
            gui = subprocess.Popen(command, cwd=release, env=env, stdout=output, stderr=subprocess.STDOUT)
        assert gui.wait(timeout=30) == 0, (tmp_path / 'gui.log').read_text(errors='replace')
        report = read_json(project / 'gui-exit-probe.json')
        assert report['controller_closed'] and report['gui_resources_closed'] and not report['timed_out']
        if scenario == 'detach':
            assert runner.poll() is None and not report['runner_stopped']
            if os.name == 'nt':
                with pytest.raises(OSError): release.rename(moved)
            client.connect(launch=False); client.command('claim'); client.shutdown_and_wait()
        else:
            assert report['runner_stopped']
        assert runner.wait(timeout=10) == 0
        release.rename(moved)  # GUI and Runner cwd handles must both have gone away.
        shutil.rmtree(moved)
    finally:
        if gui is not None and gui.poll() is None:
            gui.wait(timeout=30)  # Probe deadline uses cooperative detach, never kill.
        if runner.poll() is None:
            client.connect(launch=False); client.command('claim')
            status = client.status()
            if status['state'] in {'PREPARING', 'RUNNING', 'STOPPING'}:
                client.command('stop', run_id=status['run_id'])
                wait(lambda: not client.status()['execution_active'])
            client.shutdown_and_wait(run_id=client.status()['run_id'])
            runner.wait(timeout=10)

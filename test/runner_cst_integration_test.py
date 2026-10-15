"""Serial Pillbox copy acceptance through the production independent Runner."""
import hashlib
import math
from pathlib import Path
import time
import pytest
from csttool.configuration import read_json, write_json_atomic
from csttool.runner_client import RunnerClient

pytestmark = pytest.mark.integration


def test_production_runner_standard_pillbox_and_safe_exit(cst_executable, tmp_path):
    source = Path(__file__).parent / 'data/Pillbox/Pillbox.cst'
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    project = tmp_path / 'runner-pillbox'
    client = RunnerClient(project)
    client.connect()
    client.command('claim')
    payload = {'kind': 'standard', 'resume': False, 'worker_count': 1,
        'source_project': str(source.resolve()),
        'installation': {'version': 2022, 'executable': str(cst_executable)},
        'algorithm': {'fmin': 500, 'fmax': 800, 'endfreq': 800, 'mesh_cells_per_wavelength': 8},
        'postprocess': [{'resultName': 'frequency', 'method': 'Frequency', 'params': {'iModeNumber': 1}}],
        'tasks': [{'job': 'pillbox-mode-1', 'parameters': {'nmodes': 1, 'fmin': 500, 'fmax': 800}}]}
    client.command('start', payload)
    status = None
    try:
        # No fixed solve timeout: wait while the production Runner reports active work.
        while True:
            status = client.status()
            if status['state'] not in {'PREPARING', 'RUNNING', 'STOPPING', 'RECOVERING'}:
                break
            time.sleep(1)
        assert status['state'] == 'COMPLETED', status
        checkpoint = read_json(project / 'save/standard_batch_checkpoint.json')
        assert checkpoint['pending_index'] == 1
        result = checkpoint['results'][0]
        assert result['TaskStatus'] == 'Success'
        frequency = result['PostProcessResult'][0]['value']
        assert math.isfinite(frequency) and 500 <= frequency <= 800
        assert status['session_safety'] == 'confirmed-closed'
        assert status['artifacts'][0]['sha256'] == hashlib.sha256(
            (project / 'save/standard_batch_checkpoint.json').read_bytes()).hexdigest()
    finally:
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        write_json_atomic(tmp_path / 'runner-cst-report.json', {'status': status, 'source_sha256': before,
            'source_unchanged': True, 'project': str(project), 'forced_cst_cleanup': False})
        if status and status['state'] == 'RECOVERY_REQUIRED':
            client.command('recover')
            while client.status()['state'] == 'RECOVERING':
                time.sleep(1)
        latest = client.status()
        if latest['state'] not in {'RECOVERY_REQUIRED', 'PREPARING', 'RUNNING', 'STOPPING', 'RECOVERING'}:
            # Terminal status may precede executor disposal by one scheduling tick.
            for _ in range(20):
                try:
                    client.command('shutdown')
                    break
                except RuntimeError:
                    time.sleep(.1)


def test_runner_standard_stop_resume_preserves_accepted_task(cst_executable, tmp_path):
    source = (Path(__file__).parent / 'data/Pillbox/Pillbox.cst').resolve()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    project = tmp_path / 'runner-resume'
    client = RunnerClient(project)
    client.connect()
    client.command('claim')
    payload = {'kind': 'standard', 'resume': False, 'worker_count': 1,
        'source_project': str(source),
        'installation': {'version': 2022, 'executable': str(cst_executable)},
        'algorithm': {'fmin': 400, 'fmax': 800, 'endfreq': 800, 'mesh_cells_per_wavelength': 8},
        'postprocess': [{'resultName': 'frequency', 'method': 'Frequency', 'params': {'iModeNumber': 1}}],
        'tasks': [{'job': f'pillbox-R-{radius}', 'parameters': {'R': radius, 'nmodes': 1, 'fmin': 400, 'fmax': 800}}
                  for radius in (229, 220)]}
    accepted = client.command('start', payload)
    status = None
    report = {'source_sha256': before, 'forced_cst_cleanup': False}
    try:
        while True:
            status = client.status()
            if status.get('completed_tasks', 0) >= 1 or status['state'] not in {'PREPARING', 'RUNNING'}:
                break
            time.sleep(.1)
        assert status.get('completed_tasks', 0) >= 1, status
        original = read_json(project / 'save/standard_batch_checkpoint.json')['results'][0]
        client.command('stop', run_id=accepted['run_id'])
        while client.status()['state'] in {'PREPARING', 'RUNNING', 'STOPPING'}:
            time.sleep(.2)
        stopped = client.status()
        assert stopped['state'] == 'INTERRUPTED', stopped
        assert stopped['session_safety'] == 'confirmed-closed'
        report['stopped'] = stopped
        client.command('start', {**payload, 'resume': True})
        while client.status()['state'] in {'PREPARING', 'RUNNING', 'STOPPING'}:
            time.sleep(.5)
        status = client.status()
        assert status['state'] == 'COMPLETED', status
        checkpoint = read_json(project / 'save/standard_batch_checkpoint.json')
        assert checkpoint['pending_index'] == 2
        assert checkpoint['results'][0]['TaskID'] == original['TaskID'], 'accepted first task must not be replayed'
        assert len(checkpoint['results']) == 2
        report['first_task_preserved'] = True
        report['final'] = status
    finally:
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        write_json_atomic(tmp_path / 'runner-resume-report.json', report)
        status = client.status()
        if status['state'] == 'RECOVERY_REQUIRED':
            client.command('recover')
            while client.status()['state'] == 'RECOVERING':
                time.sleep(.5)
        if client.status()['state'] not in {'RECOVERY_REQUIRED', 'PREPARING', 'RUNNING', 'STOPPING', 'RECOVERING'}:
            for _ in range(20):
                try:
                    client.command('shutdown')
                    break
                except RuntimeError:
                    time.sleep(.1)

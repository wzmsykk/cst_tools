"""Kill only owned Python test controllers; never terminate CST."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.configuration import read_json, write_json_atomic
from csttool.result_reconciliation import file_hash

POINTS = ('gui-exit', 'runner-solver', 'runner-completion', 'runner-received', 'runner-archive', 'runner-checkpoint')
MARKER_POINTS = ('runner-checkpoint', 'runner-adoption-journal', 'runner-adoption-receipt')


def gate(project):
    (project / 'crash.entered').write_text('entered')
    while not (project / 'crash.release').exists():
        time.sleep(.01)


def second(worker):
    context = worker.root / 'task-context.json'
    return context.exists() and read_json(context).get('job') == 'second'


def runner_child(project, point):
    import csttool.managed_cstworker as module
    if point == 'runner-completion':
        original = module.ManagedCSTWorker._wait_completion
        def wait(self, task):
            result = original(self, task)
            if second(self): gate(project)
            return result
        module.ManagedCSTWorker._wait_completion = wait
    if point == 'runner-received':
        original = module.publish_ack_idempotently
        def ack(path, value):
            root = Path(path).parent.parent
            if read_json(root / 'task-context.json').get('job') == 'second': gate(project)
            return original(path, value)
        module.publish_ack_idempotently = ack
    if point == 'runner-archive':
        original = module.ManagedCSTWorker._name_result_archive
        def archive(self, *args):
            result = original(self, *args)
            if second(self): gate(project)
            return result
        module.ManagedCSTWorker._name_result_archive = archive
    if point == 'runner-checkpoint':
        from csttool.cstmanager import CSTManager
        original = CSTManager.adopt_result
        def adopt(self, task_id):
            receipt = self._received_paths.get(task_id)
            if receipt and read_json(receipt).get('job') == 'second': gate(project)
            return original(self, task_id)
        CSTManager.adopt_result = adopt
    if point == 'runner-adoption-journal':
        import csttool.run_store as store_module
        original = store_module.write_json_atomic
        def index_write(path, value):
            if (Path(path).name == 'attempt.json' and value.get('event') == 'algorithm_adopted'
                    and value.get('job') == 'second'): gate(project)
            return original(path, value)
        store_module.write_json_atomic = index_write
    if point == 'runner-adoption-receipt':
        import csttool.checkpoint_adoption as adoption_module
        original = adoption_module.write_json_atomic
        def receipt_write(path, value):
            if value.get('phase') == 'algorithm_adopted' and value.get('job') == 'second': gate(project)
            return original(path, value)
        adoption_module.write_json_atomic = receipt_write
    from csttool.runner import serve
    serve(project)


def gui_child(project):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PyQt5.QtWidgets import QApplication
    from GUI.main_window import MainWindow
    from GUI.runner_backend import RunnerBackend
    app = QApplication([])
    backend = RunnerBackend()
    backend.select_project_directory(str(project))
    window = MainWindow(engine=backend)
    window.controller.snapshot_changed.connect(lambda status: write_json_atomic(project / 'gui-observed.json',
        dict(status, observer_pid=os.getpid())))
    app.exec_()


def spawn(project, role, point):
    log = (project / (role + '-' + uuid4().hex[:6] + '.log')).open('wb')
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--child', role,
        '--project', str(project), '--point', point], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    log.close()
    return process


def wait(predicate, *, timeout=120, peer=None):
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        value = predicate()
        if value: return value
        if peer is not None and peer.poll() is not None: raise RuntimeError('owned controller exited before checkpoint')
        if deadline is not None and time.monotonic() > deadline: raise TimeoutError('controller checkpoint not reached')
        time.sleep(.02)


def marker_state(project, result):
    task = result['TaskID']
    receipt = read_json(result['ReceiptPath'])
    indexes = list(project.glob('logs/*/tasks/' + task + '/attempt.json'))
    assert len(indexes) == 1
    directory = indexes[0].parents[2]
    events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]
    return dict(receipt=receipt['phase'], index=read_json(indexes[0])['event'],
        adopted_events=sum(e.get('task_id') == task and e.get('event') == 'algorithm_adopted' for e in events))


def marker_hashes(project):
    cp = read_json(project / 'save/standard_batch_checkpoint.json')
    ids = {r['TaskID'] for r in cp['results']}
    paths = {Path(r['ReceiptPath']) for r in cp['results']}
    for path in project.glob('logs/*/tasks/*/attempt.json'):
        if path.parent.name in ids:
            paths.add(path); paths.add(path.parents[2] / 'events.jsonl')
    return {str(path): file_hash(path) for path in paths}


def run_case(project, executable, point):
    from csttool.runner_client import RunnerClient
    from csttool.acceptance_session import cst_processes
    source = ROOT / 'test/data/Pillbox/Pillbox.cst'
    before = file_hash(source)
    project.mkdir(parents=True)
    report = dict(point=point, original_sha256=before, passed=False)
    runner = spawn(project, 'runner', point)
    gui = None
    client = RunnerClient(project)
    checkpoint = project / 'save/standard_batch_checkpoint.json'
    payload = dict(kind='standard', resume=False, worker_count=1, source_project=str(source),
        installation=dict(version=2022, executable=str(executable)),
        algorithm=dict(fmin=400, fmax=800, endfreq=800, mesh_cells_per_wavelength=8),
        postprocess=[dict(resultName='frequency', method='Frequency', params=dict(iModeNumber=1))],
        tasks=[dict(job=job, parameters=dict(R=radius, nmodes=1, fmin=400, fmax=800))
               for job, radius in [('first', 229), ('second', 220)]])
    def connect():
        try: return client.connect(launch=False)
        except (OSError, ValueError, RuntimeError): return None
    def terminal():
        status = client.status()
        return status if (status['state'] not in {'PREPARING','RUNNING','STOPPING','RECOVERING'}
                          and not status.get('execution_active')) else None
    try:
        initial = wait(connect, peer=runner)
        report['initial_instance'] = initial['instance_id']
        client.command('claim')
        if point == 'gui-exit':
            gui = spawn(project, 'gui', point)
            wait(lambda: (project / 'gui-observed.json').exists(), peer=gui)
        client.command('start', payload)
        # No total solver timeout. Wait for the first durable, adopted result.
        wait(lambda: checkpoint.exists() and read_json(checkpoint)['pending_index'] >= 1,
             timeout=None, peer=runner)
        first = read_json(checkpoint)['results'][0]
        first_hash = file_hash(first['ProjectSnapshot'])
        report['first_task_id'] = first['TaskID']
        report['first_snapshot_sha256'] = first_hash
        first_fields = {str(path): file_hash(path) for path in
                        Path(first['ProjectSnapshot']).with_suffix('').glob('Result/*.m3t')}
        report['first_fields_sha256'] = first_fields
        if point == 'runner-solver':
            def in_solver():
                for context in project.glob('temp/worker_*/*/task-context.json'):
                    if read_json(context).get('job') != 'second': continue
                    logs = list(project.glob('logs/*/workers/*/' + context.parent.name + '/lifecycle.log'))
                    text = logs[0].read_text() if logs else ''
                    if text.count('calling EigenmodeSolver.Start') == 2 and text.count('returned=') == 1:
                        return True
                return False
            wait(in_solver, timeout=None, peer=runner)
        elif point != 'gui-exit':
            wait(lambda: (project / 'crash.entered').exists(), timeout=None, peer=runner)
        if point in MARKER_POINTS:
            cp = read_json(checkpoint)
            assert cp['pending_index'] == 2
            report['checkpoint_before_exit'] = file_hash(checkpoint)
            report['marker_before_exit'] = marker_state(project, cp['results'][1])
            expected = {'runner-checkpoint': ('acknowledged', 'acknowledged', 0),
                        'runner-adoption-journal': ('acknowledged', 'acknowledged', 1),
                        'runner-adoption-receipt': ('acknowledged', 'algorithm_adopted', 1)}[point]
            assert tuple(report['marker_before_exit'][key] for key in ('receipt','index','adopted_events')) == expected
        if point == 'gui-exit':
            gui.kill(); gui.wait(timeout=10)  # owned GUI Python only
            gui = spawn(project, 'gui', point)
            status = wait(terminal, timeout=None, peer=runner)
            assert status['instance_id'] == report['initial_instance']
            wait(lambda: (read_json(project / 'gui-observed.json').get('state') == 'COMPLETED'
                          and read_json(project / 'gui-observed.json').get('observer_pid') == gui.pid), peer=gui)
            report['gui_reconnected_same_runner'] = True
            report['gui_observation'] = read_json(project / 'gui-observed.json')
        else:
            report['killed_runner_pid'] = runner.pid
            runner.kill(); runner.wait(timeout=10)  # never CST or its process tree
            # Let orphan CST finish before recovery requests cooperative shutdown.
            if point in {'runner-solver', 'runner-completion', 'runner-received'}:
                wait(lambda: any(project.glob('temp/worker_*/*/protocol/current.completion')), timeout=None)
            (project / 'crash.release').write_text('release')
            client = RunnerClient(project)
            runner = spawn(project, 'runner', 'restart-no-injection')
            restarted = wait(connect, peer=runner)
            assert restarted['instance_id'] != report['initial_instance']
            assert restarted['state'] == 'RECOVERY_REQUIRED', restarted
            client.command('claim')
            client.command('recover')
            recovered = wait(terminal, timeout=None, peer=runner)
            report['recovered'] = recovered
            assert recovered['state'] == 'IDLE', recovered
            if point in MARKER_POINTS:
                assert marker_state(project, read_json(checkpoint)['results'][1]) == dict(
                    receipt='algorithm_adopted', index='algorithm_adopted', adopted_events=1)
                before_markers = marker_hashes(project)
                client.command('claim'); client.command('recover')
                again = wait(terminal, timeout=None, peer=runner)
                assert again['state'] == 'IDLE', again
                assert marker_hashes(project) == before_markers
                assert file_hash(checkpoint) == report['checkpoint_before_exit']
                from csttool.result_reconciliation import find_received_result
                receipt = read_json(read_json(checkpoint)['results'][1]['ReceiptPath'])
                assert find_received_result([project / 'logs', project / 'temp'], receipt['job'],
                    receipt['parameters'], receipt['execution_fingerprint']) is None
                report['marker_repair_idempotent'] = True
            client.command('claim')
            client.command('start', {**payload, 'resume': True})
            status = wait(terminal, timeout=None, peer=runner)
        report['final'] = status
        assert status['state'] == 'COMPLETED', status
        final = read_json(checkpoint)
        assert final['pending_index'] == 2 and len(final['results']) == 2
        if point in MARKER_POINTS:
            assert file_hash(checkpoint) == report['checkpoint_before_exit']
            report['marker_final'] = marker_state(project, final['results'][1])
        assert final['results'][0]['TaskID'] == first['TaskID']
        assert file_hash(final['results'][0]['ProjectSnapshot']) == first_hash
        assert all(Path(path).is_file() and file_hash(path) == digest for path, digest in first_fields.items())
        report['final_task_ids'] = [result['TaskID'] for result in final['results']]
        logs = list(project.glob('logs/*/workers/*/*/lifecycle.log'))
        report['solver_calls'] = sum(path.read_text().count('calling EigenmodeSolver.Start') for path in logs)
        assert report['solver_calls'] == 2, report
        report['passed'] = True
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if gui is not None and gui.poll() is None:
            gui.kill(); gui.wait(timeout=10)  # exact owned, disposable GUI process
        report['original_unchanged'] = file_hash(source) == before
        report['cst_processes_after'] = cst_processes()
        write_json_atomic(project / 'acceptance-report.json', report)
        if runner.poll() is None:
            try:
                if client.status()['state'] not in {'PREPARING','RUNNING','STOPPING','RECOVERING','RECOVERY_REQUIRED'}:
                    client.shutdown_and_wait(timeout=15)
                    runner.wait(timeout=15)
            except Exception as exc:
                print('RUNNER_CLEANUP_PENDING=' + str(exc), flush=True)
        print('REPORT=' + str(project / 'acceptance-report.json'), flush=True)


def verify_reports(roots, output):
    summary = {}
    for root in roots:
        for path in root.rglob('acceptance-report.json'):
            report = read_json(path)
            if not report.get('passed'): continue
            point = report['point']
            assert point not in summary, 'select one passed report per case'
            project = path.parent
            checkpoint = read_json(project / 'save/standard_batch_checkpoint.json')
            results = checkpoint['results']
            assert checkpoint['pending_index'] == 2 and len(results) == 2
            assert results[0]['TaskID'] == report['first_task_id']
            assert file_hash(results[0]['ProjectSnapshot']) == report['first_snapshot_sha256']
            fields = report.get('first_fields_sha256', {})
            assert all(file_hash(name) == digest for name, digest in fields.items())
            contexts = [read_json(p) for p in project.glob('temp/worker_*/*/task-context.json')]
            assert {c['task_id'] for c in contexts if c.get('job') == 'second'} == {results[1]['TaskID']}
            for result in results:
                receipt = read_json(result['ReceiptPath'])
                assert receipt['task_id'] == result['TaskID'] and receipt['status'] == 'Success'
                assert file_hash(result['ProjectSnapshot']) == receipt['snapshot_sha256']
            logs = project.glob('logs/*/workers/*/*/lifecycle.log')
            calls = sum(p.read_text().count('calling EigenmodeSolver.Start') for p in logs)
            assert calls == report['solver_calls'] == 2
            assert report['original_unchanged'] and not report['cst_processes_after']
            if point == 'runner-archive':
                assert read_json(results[1]['ReceiptPath']).get('archive_reconciled_from')
            if point == 'gui-exit':
                observed = read_json(project / 'gui-observed.json')
                assert observed['instance_id'] == report['initial_instance']
                assert observed['state'] == 'COMPLETED' and observed.get('observer_pid')
            summary[point] = dict(report=str(path), task_ids=[r['TaskID'] for r in results],
                solver_calls=calls, first_snapshot_sha256=report['first_snapshot_sha256'],
                first_fields_checked=len(fields), second_receipt_phase=read_json(results[1]['ReceiptPath'])['phase'])
    assert set(summary) == set(POINTS), set(POINTS) - set(summary)
    write_json_atomic(output, dict(passed=True, cases=summary))
    return summary


def verify_adoption_reports(root, output):
    summary = {}
    for point in MARKER_POINTS:
        project = root / point
        report = read_json(project / 'acceptance-report.json')
        checkpoint = project / 'save/standard_batch_checkpoint.json'
        assert report['passed'] and report['marker_repair_idempotent']
        assert file_hash(checkpoint) == report['checkpoint_before_exit']
        results = read_json(checkpoint)['results']
        assert len(results) == 2 and results[0]['TaskID'] == report['first_task_id']
        assert file_hash(results[0]['ProjectSnapshot']) == report['first_snapshot_sha256']
        assert all(file_hash(path) == digest for path, digest in report['first_fields_sha256'].items())
        state = marker_state(project, results[1])
        assert state == dict(receipt='algorithm_adopted', index='algorithm_adopted', adopted_events=1)
        for result in results:
            receipt = read_json(result['ReceiptPath'])
            assert receipt['task_id'] == result['TaskID']
            assert file_hash(result['ProjectSnapshot']) == receipt['snapshot_sha256']
        calls = sum(path.read_text().count('calling EigenmodeSolver.Start')
                    for path in project.glob('logs/*/workers/*/*/lifecycle.log'))
        assert calls == report['solver_calls'] == 2
        assert report['original_unchanged'] and not report['cst_processes_after']
        summary[point] = dict(before=report['marker_before_exit'], after=state, solver_calls=calls,
            checkpoint_sha256=file_hash(checkpoint), task_ids=[r['TaskID'] for r in results])
    write_json_atomic(output, dict(passed=True, cases=summary))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', choices=['runner','gui'])
    parser.add_argument('--project', type=Path)
    parser.add_argument('--cst-exe', type=Path)
    parser.add_argument('--verify-root', type=Path, action='append')
    parser.add_argument('--verification-output', type=Path)
    parser.add_argument('--verify-adoption-root', type=Path)
    parser.add_argument('--point', choices=POINTS + MARKER_POINTS[1:] + ('all', 'adoption-cases', 'runner-cases', 'runner-tail', 'restart-no-injection'), default='all')
    args = parser.parse_args()
    if args.verify_adoption_root:
        if not args.verification_output: parser.error('--verification-output is required')
        return verify_adoption_reports(args.verify_adoption_root, args.verification_output)
    if args.verify_root:
        if not args.verification_output: parser.error('--verification-output is required')
        return verify_reports(args.verify_root, args.verification_output)
    if args.child:
        if args.project is None: parser.error('--project is required for a child')
        return runner_child(args.project, args.point) if args.child == 'runner' else gui_child(args.project)
    if args.cst_exe is None: parser.error('--cst-exe is required for real execution')
    from csttool.acceptance_session import exclusive_probe, cst_processes
    with exclusive_probe(ROOT):
        root = ROOT / 'artifacts' / ('controller-exit-l5-' + uuid4().hex[:8])
        points = {'all': POINTS, 'adoption-cases': MARKER_POINTS, 'runner-cases': POINTS[1:], 'runner-tail': POINTS[3:]}.get(args.point, (args.point,))
        for point in points:
            assert not cst_processes()
            print('POINT_BEGIN=' + point, flush=True)
            run_case(root / point, args.cst_exe.resolve(), point)


if __name__ == '__main__':
    main()

"""Real serial Pillbox HOM interruption acceptance; kill only owned Python Runner."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.configuration import read_json, write_json_atomic
from csttool.result_reconciliation import file_hash
from test.support.validate_controller_exit_l5 import wait, gate

POINTS = ('checkpoint', 'received', 'solver')


def checkpoint(project):
    return project / 'save/csv/hom_scan_checkpoint.json'


def armed(project):
    path = checkpoint(project)
    return path.exists() and bool(read_json(path)['report']['adopted_task_ids'])


def runner_child(project, point):
    import csttool.managed_cstworker as module
    if point == 'checkpoint':
        from csttool.cstmanager import CSTManager
        original = CSTManager.adopt_result
        def adopt(self, task_id):
            if armed(project):
                gate(project)
            return original(self, task_id)
        CSTManager.adopt_result = adopt
    if point == 'received':
        original = module.publish_ack_idempotently
        def ack(path, value):
            if armed(project):
                gate(project)
            return original(path, value)
        module.publish_ack_idempotently = ack
    from csttool.runner import serve
    serve(project)


def spawn(project, point):
    with (project / ('runner-' + uuid4().hex[:6] + '.log')).open('wb') as log:
        return subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
            '--child', '--project', str(project), '--point', point], cwd=ROOT,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def solver_calls(project):
    return sum(p.read_text().count('calling EigenmodeSolver.Start')
               for p in project.glob('logs/*/workers/*/*/lifecycle.log'))


def evidence(project, document):
    paths = set()
    for mode in document['report']['modes']:
        snapshot = project / mode['project_snapshot']
        paths.add(snapshot)
        fields = list(snapshot.with_suffix('').glob('Result/*.m3t'))
        assert fields, 'native fields missing: ' + str(snapshot)
        paths.update(fields)
    return {str(p): file_hash(p) for p in paths}


def adoption(project, ids):
    result = {}
    for task in ids:
        receipts = list(project.glob('logs/*/workers/*/*/received/' + task + '.json'))
        assert len(receipts) == 1, receipts
        assert read_json(receipts[0])['phase'] == 'algorithm_adopted'
        events = []
        for index in project.glob('logs/*/tasks/' + task + '/attempt.json'):
            assert read_json(index)['event'] == 'algorithm_adopted'
            rows = [json.loads(line) for line in (index.parents[2] / 'events.jsonl').read_text().splitlines()]
            count = sum(r.get('task_id') == task and r.get('event') == 'algorithm_adopted' for r in rows)
            assert count == 1, (task, count)
            events.append(count)
        assert events
        result[task] = events
    return result


def submissions(project):
    rows = []
    for path in sorted(project.glob('logs/*/events.jsonl')):
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    return [row for row in rows if row.get('event') == 'submitted']


def equivalent_numbers(actual, expected):
    """Independent solves can differ in final floating-point digits (MHz)."""
    import math
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(equivalent_numbers(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(equivalent_numbers(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, (float, int)) and isinstance(expected, (float, int)):
        return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)
    return actual == expected


def verify_reports(root):
    import csv
    from csttool.project_session_recovery import discover_managed_sessions
    reports = {p.parent.name: read_json(p) for p in root.glob('*/acceptance-report.json')}
    baseline = reports['baseline']
    assert baseline['passed'] and baseline['original_unchanged']
    expected = [r['parameters'] for r in submissions(root / 'baseline')]
    for point in POINTS:
        report = reports[point]
        assert report['passed'] and report['original_unchanged']
        assert not report['cst_processes_after']
        sessions = discover_managed_sessions(root / point)
        assert all(record.process_alive is False and not record.needs_recovery for record in sessions)
        assert sum(Path(p).suffix == '.m3t' for p in report['result_hashes']) >= 4
        assert all(file_hash(Path(p)) == digest for p, digest in report['result_hashes'].items())
        adoption(root / point, report['final']['report']['adopted_task_ids'])
        with (root / point / 'save/csv/hom_scan_results.csv').open(encoding='utf-8-sig', newline='') as stream:
            csv_rows = list(csv.DictReader(stream))
        modes = report['final']['report']['modes']
        assert [row['taskId'] for row in csv_rows] == [mode['task_id'] for mode in modes]
        assert len({row['taskId'] for row in csv_rows}) == len(csv_rows)  # nmodes=1 only
        assert equivalent_numbers([float(row['frequency']) for row in csv_rows], [mode['frequency'] for mode in modes])
        submitted = submissions(root / point)
        assert all(row['parameters']['nmodes'] == 1 for row in submitted)
        assert equivalent_numbers([r['parameters'] for r in submitted], expected)
        assert len({r['task_id'] for r in submitted}) == len(submitted)
        assert report['solver_calls'] == baseline['solver_calls'] == len(submitted)
        assert equivalent_numbers(report['final']['coverage'], baseline['final']['coverage'])
        assert equivalent_numbers([m['frequency'] for m in report['final']['report']['modes']], [m['frequency'] for m in baseline['final']['report']['modes']])
    result = dict(passed=True, cases=list(reports), solver_calls_per_case=baseline['solver_calls'],
                  submitted_parameters=expected, coverage=baseline['final']['coverage'],
                  recovery_cases={point: dict(solver_calls=reports[point]['solver_calls'],
                    coverage_before=reports[point]['before']['coverage'],
                    coverage_after=reports[point]['final']['coverage'],
                    final_session_safety=reports[point]['final_status']['session_safety'],
                    adopted_task_ids=reports[point]['final']['report']['adopted_task_ids'],
                    retained_native_fields=sum(Path(p).suffix == '.m3t' for p in reports[point]['result_hashes']))
                    for point in POINTS})
    write_json_atomic(root / 'verification.json', result)
    return result


def run_case(project, executable, point):
    from csttool.runner_client import RunnerClient
    from csttool.acceptance_session import cst_processes
    project.mkdir(parents=True)
    source = ROOT / 'test/data/Pillbox/Pillbox.cst'
    report = dict(point=point, passed=False, original_sha256=file_hash(source))
    payload = dict(kind='hom', resume=False, worker_count=1, source_project=str(source),
        installation=dict(version=2022, executable=str(executable)),
        algorithm=dict(fmin=480, fmax=530, endfreq=530, mesh_cells_per_wavelength=8),
        postprocess=[dict(resultName='frequency', method='Frequency', params=dict(iModeNumber=1))])
    runner = spawn(project, point)
    client = RunnerClient(project)
    def connect():
        try: return client.connect(launch=False)
        except (OSError, RuntimeError, ValueError): return None
    def terminal():
        value = client.status()
        return value if value['state'] not in {'PREPARING','RUNNING','STOPPING','RECOVERING'} and not value.get('execution_active') else None
    def running_wait(predicate):
        def checked():
            value = predicate()
            if value: return value
            status = terminal()
            if status is not None:
                raise RuntimeError('run ended before injection: ' + str(status))
            return None
        return wait(checked, timeout=None, peer=runner)
    try:
        wait(connect, peer=runner)
        client.command('claim'); client.command('start', payload)
        if point == 'baseline':
            status = wait(terminal, timeout=None, peer=runner)
            final = read_json(checkpoint(project))
            assert status['state'] == 'COMPLETED', status
            assert not final['pending'] and not final['report']['failed']
            report.update(final_status=status, final=final, solver_calls=solver_calls(project), passed=True)
            return
        if point == 'solver':
            def in_solver():
                if not armed(project): return False
                for path in project.glob('logs/*/workers/*/*/lifecycle.log'):
                    text = path.read_text()
                    if text.count('calling EigenmodeSolver.Start') >= 2 and text.count('calling EigenmodeSolver.Start') > text.count('returned='):
                        return True
                return False
            running_wait(in_solver)
        else:
            running_wait(lambda: (project / 'crash.entered').exists())
        old = read_json(checkpoint(project))
        assert old['report']['modes'] and old['pending'], old
        report.update(before=old, result_hashes=evidence(project, old), solver_calls_at_exit=solver_calls(project))
        old_hash = file_hash(checkpoint(project))
        runner.kill(); runner.wait(timeout=10)  # exact disposable Runner; never CST
        if point == 'solver':
            wait(lambda: any(project.glob('temp/worker_*/*/protocol/current.completion')), timeout=None)
        (project / 'crash.release').write_text('release')
        runner = spawn(project, 'restart')
        client = RunnerClient(project)
        restarted = wait(connect, peer=runner)
        assert restarted['state'] == 'RECOVERY_REQUIRED', restarted
        client.command('claim'); client.command('recover')
        recovered = wait(terminal, timeout=None, peer=runner)
        assert recovered['state'] == 'IDLE', recovered
        assert file_hash(checkpoint(project)) == old_hash
        report['adoption_after_recover'] = adoption(project, old['report']['adopted_task_ids'])
        before_again = solver_calls(project)
        client.command('claim'); client.command('recover')
        assert wait(terminal, timeout=None, peer=runner)['state'] == 'IDLE'
        assert solver_calls(project) == before_again and file_hash(checkpoint(project)) == old_hash
        client.command('claim'); client.command('start', {**payload, 'resume': True})
        final_status = wait(terminal, timeout=None, peer=runner)
        final = read_json(checkpoint(project))
        report.update(final_status=final_status, final=final, solver_calls=solver_calls(project))
        assert final_status['state'] == 'COMPLETED', final_status
        assert not final['pending'] and not final['report']['failed']
        assert final['coverage']['confirmed_frontier'] >= old['coverage']['confirmed_frontier']
        assert final['coverage']['calculated_upper'] >= old['coverage']['calculated_upper']
        assert all(mode in final['report']['modes'] for mode in old['report']['modes'])
        ids = final['report']['adopted_task_ids']
        assert len(ids) == len(set(ids))
        assert report['solver_calls'] == final['report']['solver_calls'], report
        assert all(file_hash(Path(p)) == digest for p, digest in report['result_hashes'].items())
        report['adoption_final'] = adoption(project, ids)
        report['passed'] = True
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        report['original_unchanged'] = file_hash(source) == report['original_sha256']
        if runner.poll() is None:
            try:
                state = wait(terminal, timeout=30, peer=runner)
                if state['state'] != 'RECOVERY_REQUIRED':
                    client.shutdown_and_wait(timeout=20); runner.wait(timeout=20)
            except Exception as exc: report['cleanup_pending'] = str(exc)
        report['cst_processes_after'] = cst_processes()
        write_json_atomic(project / 'acceptance-report.json', report)
        print('REPORT=' + str(project / 'acceptance-report.json'), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--cst-exe', type=Path)
    parser.add_argument('--verify-root', type=Path)
    parser.add_argument('--point', default='all', choices=POINTS + ('all','restart','baseline'))
    args = parser.parse_args()
    if args.verify_root: return verify_reports(args.verify_root)
    if args.child: return runner_child(args.project, args.point)
    if not args.cst_exe: parser.error('--cst-exe required')
    from csttool.acceptance_session import exclusive_probe, cst_processes
    import shutil
    assert shutil.disk_usage(ROOT).free > 2 * 1024**3
    with exclusive_probe(ROOT):
        root = ROOT / 'artifacts' / ('hom-exit-l5-' + uuid4().hex[:8])
        for point in ('baseline',) + POINTS if args.point == 'all' else (args.point,):
            assert not cst_processes()
            print('POINT_BEGIN=' + point, flush=True)
            run_case(root / point, args.cst_exe.resolve(), point)
        if args.point == 'all': verify_reports(root)


if __name__ == '__main__':
    main()

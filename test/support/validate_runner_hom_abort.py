"""Production Runner/HOM abort, crash, recovery and adoption on serial copies."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.configuration import read_json, write_json_atomic
from csttool.result_reconciliation import file_hash
from test.support.validate_controller_exit_l5 import wait, gate
from test.support.validate_hom_exit_l5 import checkpoint, solver_calls, evidence, adoption
from test.support import validate_solver_abort as abort_probe

CASES = ('baseline', 'received', 'checkpoint', 'journal', 'receipt')


def confirmed(project, task):
    path = checkpoint(project)
    return path.exists() and any(mode.get('task_id') == task for mode in read_json(path)['report']['modes'])


def fault_gate(project, case, task):
    write_json_atomic(project / 'fault-boundary.json', dict(case=case, task_id=task))
    gate(project)


def runner_child(project, case):
    import csttool.managed_cstworker as managed
    original = managed.ManagedCSTWorker.run_task
    def run_task(self, name, *, params):
        write_json_atomic(self.root / ('source-' + uuid4().hex + '.json'),
            dict(source=str(self.source_project), sha256=file_hash(self.source_project), parameters=dict(params)))
        reservation = project / 'abort-reserved.json'
        if reservation.exists():
            return original(self, name, params=params)
        with reservation.open('x', encoding='utf-8') as stream:
            json.dump(dict(session=str(self.root), runner_pid=os.getpid()), stream)
        identity = abort_probe.owned_environment(self)
        intent = self.root / 'bridge-intent.json'
        abort_probe.write(intent, dict(parent_pid=os.getpid(), identity=identity,
            python_libraries=str(self.executable.parent / 'AMD64/python_cst_libraries'),
            lifecycle_path=str(self.observation_root / 'lifecycle.log')))
        with (self.root / 'bridge.log').open('wb') as log:
            helper = subprocess.Popen([str(self.executable.parent / 'AMD64/python/python.exe'),
                str(Path(abort_probe.__file__).resolve()), '--bridge', str(intent)],
                stdout=log, stderr=subprocess.STDOUT)
            try:
                try:
                    abort_probe.wait_ready(helper, self.root)
                    result = dict(original(self, name, params=params))
                finally:
                    abort_probe.finish_bridge(helper, self.root)
                response = read_json(self.root / 'abort-result.json')
                if response.get('returned') is not True:raise RuntimeError('official abort not confirmed')
            except Exception as error:
                write_json_atomic(project / 'injection-failed.json', dict(error=str(error), session=str(self.root)))
                self.request_stop()
                raise
        write_json_atomic(project / 'abort-observed.json', dict(session=str(self.root), result=result,
            response=response))
        return result
    managed.ManagedCSTWorker.run_task = run_task
    from csttool.cstmanager import CSTManager
    original_adopt = CSTManager.adopt_result
    def adopted(self, task):
        if case == 'checkpoint' and confirmed(project, task):fault_gate(project, case, task)
        result = original_adopt(self, task)
        if confirmed(project, task):
            # Bound this lifecycle acceptance at its first adopted physical result.
            # Do not change frequency tolerances to conceal small-grid mode drift.
            write_json_atomic(project / 'pause-after-adopt.json', dict(task_id=task))
            self.request_stop()
        return result
    CSTManager.adopt_result = adopted
    if case == 'received':
        archive = managed.ManagedCSTWorker._name_result_archive
        def archived(self, *args):
            result = archive(self, *args)
            if (project / 'abort-observed.json').exists():
                task = read_json(self.root / 'task-context.json')['task_id']
                fault_gate(project, case, task)
            return result
        managed.ManagedCSTWorker._name_result_archive = archived
    if case in ('journal', 'receipt'):
        import csttool.run_store as store
        import csttool.checkpoint_adoption as adopter
        module = store if case == 'journal' else adopter
        original_write = module.write_json_atomic
        def written(path, value):
            task = value.get('task_id')
            target = (Path(path).name == 'attempt.json' and value.get('event') == 'algorithm_adopted'
                      if case == 'journal' else value.get('phase') == 'algorithm_adopted')
            if target and task and confirmed(project, task):fault_gate(project, case, task)
            return original_write(path, value)
        module.write_json_atomic = written
    from csttool.runner import serve
    serve(project)


def spawn(project, case):
    with (project / ('runner-' + uuid4().hex[:6] + '.log')).open('wb') as log:
        return subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--child',
            '--project', str(project), '--case', case], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def task_markers(project, task):
    paths = list(project.glob('logs/*/workers/*/*/received/' + task + '.json'))
    assert len(paths) == 1, paths
    indexes = list(project.glob('logs/*/tasks/' + task + '/attempt.json'))
    return dict(receipt=read_json(paths[0])['phase'], indexes=[read_json(p)['event'] for p in indexes],
        events=[sum(row.get('event') == 'algorithm_adopted' and row.get('task_id') == task
                    for row in map(json.loads, (p.parents[2] / 'events.jsonl').read_text(encoding='utf-8').splitlines()))
                for p in indexes])


def validate_boundary(case, markers):
    expected = {'received':('acknowledged','acknowledged',0),
                'checkpoint':('acknowledged','acknowledged',0),
                'journal':('acknowledged','acknowledged',1),
                'receipt':('acknowledged','algorithm_adopted',1)}[case]
    assert markers == dict(receipt=expected[0], indexes=[expected[1]], events=[expected[2]]), markers


def received_evidence(project, task):
    receipt, = project.glob('logs/*/workers/*/*/received/' + task + '.json')
    snapshot = Path(read_json(receipt)['snapshot'])
    if not snapshot.exists():
        indexes = [p for p in project.glob('result/**/task_result.json') if read_json(p).get('taskId') == task]
        assert len(indexes) == 1
        index = read_json(indexes[0]);name = index['projectSnapshot']
        assert Path(name).name == name
        snapshot = indexes[0].parent / name
    assert file_hash(snapshot) == read_json(receipt)['snapshot_sha256']
    fields = list(snapshot.with_suffix('').glob('Result/*.m3t'))
    assert fields
    return {str(p):file_hash(p) for p in [snapshot, *fields]}


def marker_hashes(project):
    return {str(p):file_hash(p) for pattern in ('logs/*/workers/*/*/received/*.json',
        'logs/*/tasks/*/attempt.json', 'logs/*/events.jsonl') for p in project.glob(pattern)}


def run_case(project, executable, case):
    from csttool.runner_client import RunnerClient
    from csttool.acceptance_session import cst_processes
    from csttool.project_session_recovery import discover_managed_sessions
    source = ROOT / 'test/data/Pillbox/Pillbox.cst'
    project.mkdir(parents=True)
    report = dict(passed=False, case=case, source_sha256=file_hash(source), driver_sha256=file_hash(__file__),
        production_hashes={name:file_hash(ROOT / name) for name in ('csttool/checkpoint_adoption.py',
            'csttool/hom_scan_algorithm.py','csttool/cstmanager.py','test/support/validate_solver_abort.py')})
    payload = dict(kind='hom', resume=False, worker_count=1, source_project=str(source),
        installation=dict(version=2022, executable=str(executable)),
        algorithm=dict(fmin=480, fmax=530, endfreq=530, mesh_cells_per_wavelength=8),
        postprocess=[dict(resultName='frequency', method='Frequency', params=dict(iModeNumber=1)),
                     dict(resultName='rq', method='R_over_Q', params=dict(iModeNumber=1, axis='z', xoffset=0, yoffset=0, zoffset=0))])
    runner = spawn(project, case)
    client = RunnerClient(project)
    injection_stop = False
    def connect():
        try:return client.connect(launch=False)
        except (OSError, RuntimeError, ValueError):return None
    def terminal():
        nonlocal injection_stop
        value = client.status()
        if ((project / 'injection-failed.json').exists() and not injection_stop
                and value['state'] in {'PREPARING','RUNNING'}):
            client.command('stop', run_id=value['run_id']);injection_stop = True
        return value if value['state'] not in {'PREPARING','RUNNING','STOPPING','RECOVERING'} and not value.get('execution_active') else None
    def boundary():
        if (project / 'crash.entered').exists():return True
        state = terminal()
        if state:raise RuntimeError('Runner ended before fault boundary: ' + str(state))
        return False
    try:
        wait(connect, peer=runner)
        client.command('claim');client.command('start', payload)
        if case != 'baseline':
            wait(boundary, timeout=None, peer=runner)
            task = read_json(project / 'fault-boundary.json')['task_id']
            before = read_json(checkpoint(project))
            report.update(before=before, target_task=task, marker_before=task_markers(project, task),
                          result_hashes=evidence(project, before), calls_before_exit=solver_calls(project))
            validate_boundary(case, report['marker_before'])
            report['target_hashes'] = received_evidence(project, task)
            saved_checkpoint = file_hash(checkpoint(project))
            runner.kill();runner.wait(timeout=10)  # Exact owned Python Runner only; never its descendants.
            (project / 'crash.release').write_text('release')
            runner = spawn(project, 'restart')
            client = RunnerClient(project)
            assert wait(connect, peer=runner)['state'] == 'RECOVERY_REQUIRED'
            client.command('claim');client.command('recover')
            report['recovered'] = wait(terminal, timeout=None, peer=runner)
            assert report['recovered']['state'] == 'IDLE', report
            assert file_hash(checkpoint(project)) == saved_checkpoint
            assert solver_calls(project) == report['calls_before_exit']
            if case != 'received':adoption(project, [task])
            stable = marker_hashes(project)
            client.command('claim');client.command('recover')
            assert wait(terminal, timeout=None, peer=runner)['state'] == 'IDLE'
            assert marker_hashes(project) == stable and file_hash(checkpoint(project)) == saved_checkpoint
            client.command('claim');client.command('start', {**payload, 'resume':True})
        final_status = wait(terminal, timeout=None, peer=runner)
        final = read_json(checkpoint(project))
        report.update(final_status=final_status, final=final, solver_calls=solver_calls(project))
        assert report['solver_calls'] == 2, 'one aborted solve and one recovered solve only'
        assert final_status['state'] == 'INTERRUPTED', final_status
        assert final['report']['modes'] and final['pending'] and not final['report']['failed']
        ids = final['report']['adopted_task_ids']
        assert len(ids) == len(set(ids))
        report['adoption'] = adoption(project, ids)
        if case != 'baseline':
            assert report['target_task'] in ids, 'received result must be adopted under its original task ID'
            assert all(m in final['report']['modes'] for m in report['before']['report']['modes'])
            assert final['coverage']['confirmed_frontier'] >= report['before']['coverage']['confirmed_frontier']
            assert final['coverage']['calculated_upper'] >= report['before']['coverage']['calculated_upper']
            assert all(file_hash(path) == value for path,value in report['result_hashes'].items())
            assert all(file_hash(path) == value for path,value in report['target_hashes'].items())
        aborted = read_json(project / 'abort-observed.json')
        assert aborted['response']['returned'] is True and aborted['result']['TaskStatus'] == 'Failure'
        assert not aborted['result'].get('ProjectSnapshot') and not aborted['result'].get('PostProcessResult')
        report['abort'] = aborted
        assert aborted['result']['TaskID'] not in ids
        prepared = project / 'processed.cst'
        first_success = next(project.glob('logs/*/workers/*/*/received/' + ids[0] + '.json'))
        workspace = Path(read_json(first_success)['workspace'])
        provenance = [read_json(p) for p in workspace.glob('source-*.json')]
        assert any(Path(p['source']).resolve() == prepared.resolve() and p['sha256'] == file_hash(prepared) for p in provenance), provenance
        report['replacement_from_processed'] = True
        report['result_hashes_final'] = evidence(project, final)
        # Resume stops on re-adopting the confirmed record, before another solve.
        # This is a paused-scan lifecycle test, not complete 480--530 MHz enumeration.
        calls = solver_calls(project)
        csv_hash = file_hash(project / 'save/csv/hom_scan_results.csv')
        client.command('claim');client.command('start', {**payload, 'resume':True})
        assert wait(terminal, timeout=None, peer=runner)['state'] == 'INTERRUPTED'
        paused = read_json(checkpoint(project))
        assert solver_calls(project) == calls and paused['report']['modes'] == final['report']['modes']
        assert paused['coverage'] == final['coverage']
        assert file_hash(project / 'save/csv/hom_scan_results.csv') == csv_hash
        # New run overviews can change; task IDs and per-store adoption multiplicity cannot.
        adoption(project, ids)
        report['paused_resume_no_solver_replay'] = True
        report['closures'] = [asdict(s.closure) for s in discover_managed_sessions(project)]
        assert all(s.process_alive is False and not s.needs_recovery for s in discover_managed_sessions(project)), report
        assert file_hash(source) == report['source_sha256']
        report['passed'] = True
    except BaseException as error:
        report['error'] = '{}: {}'.format(type(error).__name__, error)
        raise
    finally:
        if runner.poll() is None:
            try:
                state = wait(terminal, timeout=30, peer=runner)
                if state['state'] != 'RECOVERY_REQUIRED':
                    client.shutdown_and_wait(timeout=20);runner.wait(timeout=20)
            except Exception as error:report['runner_cleanup_pending'] = str(error)
        report['remaining_cst'] = cst_processes()
        report['source_unchanged'] = file_hash(source) == report['source_sha256']
        write_json_atomic(project / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', type=Path)
    parser.add_argument('--run-cst', action='store_true')
    parser.add_argument('--case', choices=CASES + ('all','restart'), default='all')
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--project', type=Path)
    args = parser.parse_args()
    if args.child:
        project = args.project.resolve(strict=True)
        if not project.is_relative_to(ROOT / 'artifacts'):parser.error('child outside artifacts')
        return runner_child(project, args.case)
    if not args.run_cst or not args.cst_exe:parser.error('--run-cst and --cst-exe required')
    if args.case == 'restart':parser.error('restart is internal to child')
    from csttool.acceptance_session import exclusive_probe, cst_processes
    from test.support.validate_public_faults import cleanup_case
    assert shutil.disk_usage(ROOT).free > 2 * 1024**3
    with exclusive_probe(ROOT):
        root = ROOT / 'artifacts' / ('runner-hom-abort-' + uuid4().hex[:8]);root.mkdir()
        print('RUNNER_HOM_ABORT_ROOT=' + str(root), flush=True)
        reports = []
        requested = CASES if args.case == 'all' else (args.case,)
        summary = dict(passed=False, state='running', requested_cases=list(requested), cases=reports)
        write_json_atomic(root / 'report.json', summary)
        try:
            for case in requested:
                assert not cst_processes()
                result = run_case(root / case, args.cst_exe.resolve(strict=True), case)
                assert result['passed'] and not result['remaining_cst']
                result['cleaned_companions'] = cleanup_case(root / case, ROOT / 'test/data/Pillbox/Pillbox.cst')
                write_json_atomic(root / case / 'report.json', result)
                reports.append(result)
                write_json_atomic(root / 'report.json', summary)
                print('CASE_COMPLETE=' + case, flush=True)
            summary.update(passed=True, state='completed')
        except BaseException as error:
            summary.update(passed=False, state='failed', failed_case=case,
                           error='{}: {}'.format(type(error).__name__, error))
            raise
        finally:
            write_json_atomic(root / 'report.json', summary)


if __name__ == '__main__':main()

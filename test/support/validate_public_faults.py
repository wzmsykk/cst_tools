"""Serial owned-CST fault supervision. Default is a read-only plan, never solve."""
import argparse
from dataclasses import asdict
import hashlib
import os
import shutil
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.acceptance_session import exclusive_probe, cst_processes
from csttool.application_service import ApplicationService
from csttool.configuration import read_json, write_json_atomic
from csttool.execution_contract import StopIntent
from csttool.project_session_recovery import discover_managed_sessions
from test.support.validate_stop_ack_l5 import CASES, run_timing

PUBLIC = ('controller-before-publication', 'controller-before-adoption-receipt', 'solver-rejection')
ALL = CASES + PUBLIC


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cleanup_case(root, source):
    """Only after serial closure checks; retain small models and member/hash evidence."""
    from csttool.saved_project_source import read_saved_source
    root = root.resolve(strict=True)
    assert root.is_relative_to(ROOT/'artifacts') and not cst_processes()
    removed = []
    for model in root.rglob('*.cst'):
        assert model.resolve() != source.resolve()
        companion = model.with_suffix('')
        if not companion.is_dir(): continue
        target = companion.resolve(strict=True)
        assert target.is_relative_to(root) and not target.is_symlink()
        tracked = subprocess.check_output(['git','ls-files','--',str(target)],cwd=ROOT,text=True)
        assert not tracked.strip(), 'never remove tracked evidence'
        saved = read_saved_source(model, scope='root')
        members = model.parent/(model.name+'.members'); members.mkdir(exist_ok=True)
        for name, raw in saved.members.items():
            if name.endswith(('Parameters.json','Model.mod','Model.run','simulationproperties.json')):
                out=members/name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
        files=[dict(path=str(p.relative_to(target)),bytes=p.stat().st_size,sha256=digest(p))
               for p in target.rglob('*') if p.is_file()]
        shutil.rmtree(target)
        removed.append(dict(path=str(target),model_sha256=digest(model),files=files))
    write_json_atomic(root/'cleanup.json',dict(removed=removed,fields_require_regeneration=True))
    return len(removed)


def public_case(root, source, exe, case):
    """A child owns the service; only this test process may abruptly self-exit."""
    import csttool.application_service as module
    service = ApplicationService(root, 'public-fault', installations={'local': exe})
    definition = service.stage_definition('pillbox', source, 'local')
    service.verify_definition('pillbox', definition['definition_revision'])
    payload = dict(kind='simulation', document_id='pillbox', definition_revision=definition['definition_revision'])
    write_json_atomic(root/'case-intent.json', dict(case=case, payload=payload, source_sha256=digest(source)))
    original = module.write_json_atomic
    def fault(path, value):
        if case == 'controller-before-publication' and Path(path).name == 'simulation-result.json':
            write_json_atomic(root/'injected.json', dict(case=case, pid=os.getpid(), boundary='before-result-write'))
            os._exit(91)
        return original(path, value)
    module.write_json_atomic = fault
    if case == 'controller-before-adoption-receipt':
        import csttool.checkpoint_adoption as adoption
        original_receipt = adoption.write_json_atomic
        def receipt_fault(path, value):
            if value.get('phase') == 'algorithm_adopted':
                write_json_atomic(root/'injected.json', dict(case=case, pid=os.getpid(), boundary='before-adoption-receipt'))
                os._exit(91)
            return original_receipt(path, value)
        adoption.write_json_atomic = receipt_fault
    if case == 'solver-rejection':
        from csttool.managed_cstworker import ManagedCSTWorker
        class OpenBoundaryWorker(ManagedCSTWorker):
            def _build_macro(self):
                super()._build_macro()
                text = self.macro_path.read_text(encoding='ascii')
                anchor = '            stage = "solver-config"'
                assert text.count(anchor) == 1
                text = text.replace(anchor, anchor + '\n            If Not AddToHistory("fault probe", "Boundary.Xmax ""open""") Then Err.Raise 2991\n            If Boundary.GetXmax <> "open" Then Err.Raise 2992\n')
                self.macro_path.write_text(text, encoding='ascii')
                self.batch_script_path.write_text(text, encoding='ascii')
        service.worker_factory = OpenBoundaryWorker
        execution = service.execute_simulation(payload, run_id='fault', stop=StopIntent(), update=lambda **kw: None)
        try:
            execution.run(payload)
        except Exception as error:
            write_json_atomic(root/'solver-failure.json', dict(type=type(error).__name__, error=str(error),
                safety=execution.session_safety(), recovery=execution.recovery_required()))
            assert getattr(error, 'code', None) == 'SOLVER_FAILED', 'original solver failure was masked'
        else:
            raise AssertionError('solver rejection was not observed')
        assert execution.session_safety() == 'confirmed-closed'
        assert not (root/'control/runs/fault/simulation-result.json').exists()
        # New worker from the immutable preprocessed definition, no failed snapshot reuse.
        service.worker_factory = None
        service.execute_simulation(payload, run_id='recovered', stop=StopIntent(), update=lambda **kw: None).run(payload)
        service.get_simulation_results('recovered')
        write_json_atomic(root/'injected.json', dict(case=case, recovery='new-worker-from-definition'))
        return
    service.execute_simulation(payload, run_id='fault', stop=StopIntent(), update=lambda **kw: None).run(payload)
    raise AssertionError('controller exit injection missed')


def reconcile_public(root, exe, case, code):
    if case != 'solver-rejection':
        assert code == 91 and read_json(root/'injected.json')['case'] == case
        closure = read_json(root/'control/runs/fault/simulation-closure.json')
        assert closure['standard_closed'] is True
        service = ApplicationService(root, 'public-fault', installations={'local': exe})
        first = service.reconcile_simulation('fault')
        journal = root/'control/runs/fault/events.jsonl'; before = journal.read_bytes()
        assert service.reconcile_simulation('fault') == first
        assert journal.read_bytes() == before
    else:
        assert code == 0 and (root/'solver-failure.json').exists()
        assert 'SOLVER_FAILED' in read_json(root/'solver-failure.json')['error']
    logs = list((root/'control/runs').glob('*/workers/*/*/lifecycle.log'))
    calls = sum(p.read_text(encoding='utf-8').count('calling EigenmodeSolver.Start') for p in logs)
    assert calls == (2 if case == 'solver-rejection' else 1), calls
    sessions = discover_managed_sessions(root)
    assert sessions and all(s.closure.standard_closed for s in sessions)
    return dict(passed=True, case=case, solver_calls=calls, controller_exit=code,
                solver_returns=[line for p in logs for line in p.read_text(encoding='utf-8').splitlines() if 'returned=' in line],
                injected=read_json(root/'injected.json'), closures=[asdict(s.closure) for s in sessions])


def supervise(root, source, exe, cases, *, launch=subprocess.Popen, processes=cst_processes, keep_raw=False):
    report = dict(passed=False, source_sha256=digest(source), cases=[], real_cst=True,
                  driver_sha256=digest(__file__))
    try:
        for case in cases:
            assert not processes(), 'CST still active; do not start another case'
            directory = root/case; directory.mkdir()
            assert shutil.disk_usage(root).free > 1024**3, 'less than 1GiB free'
            write_json_atomic(directory/'parent-intent.json', dict(parent_pid=os.getpid(), case=case,
                source=str(source), source_sha256=digest(source), executable=str(exe)))
            write_json_atomic(root/'progress.json', dict(case=case, state='running'))
            args = [sys.executable, str(Path(__file__).resolve()), '--child', case, '--root', str(directory),
                    '--source', str(source), '--cst-exe', str(exe), '--run-cst']
            with (directory/'controller.log').open('wb') as log:
                child = launch(args, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
                # No total solver timeout. Startup/ACK/exit have their own production bounds.
                code = child.wait()
            assert not processes(), 'child ended but CST remains; preserve evidence and stop'
            if case in PUBLIC:
                value = reconcile_public(directory, exe, case, code)
            else:
                assert code == 0
                value = read_json(directory/'report.json')
                assert value['passed'] and value['close']['standard_closed']
            assert digest(source) == report['source_sha256'], 'source changed'
            report['cases'].append(dict(case=case, report=value))
            write_json_atomic(root/'report.json', report)
            if not keep_raw:
                report['cases'][-1]['cleaned_companions'] = cleanup_case(directory, source)
        report['passed'] = True
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['remaining_cst'] = processes()
        write_json_atomic(root/'report.json', report)
        write_json_atomic(root/'progress.json', dict(state='completed' if report['passed'] else 'blocked'))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path)
    parser.add_argument('--cst-exe', type=Path)
    parser.add_argument('--run-cst', action='store_true')
    parser.add_argument('--case', action='append', choices=ALL)
    parser.add_argument('--child', choices=ALL)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--keep-raw', action='store_true')
    args = parser.parse_args()
    if not args.run_cst:
        print('PLAN ONLY: ' + ', '.join(args.case or ALL)); return
    if not args.source or not args.cst_exe: parser.error('--source and --cst-exe required')
    source = args.source.resolve(strict=True); exe = args.cst_exe.resolve(strict=True)
    if args.child:
        if not args.root: parser.error('child requires --root')
        directory = args.root.resolve(strict=True)
        if not directory.is_relative_to(ROOT/'artifacts'): parser.error('child root outside artifacts')
        owner = read_json(directory/'parent-intent.json')
        if (owner['parent_pid'] != os.getppid() or owner['case'] != args.child
                or owner['source_sha256'] != digest(source) or owner['executable'] != str(exe)):
            parser.error('child supervision identity mismatch')
        # The parent holds the exclusive probe lock across all child sessions.
        if args.child in PUBLIC: public_case(args.root.resolve(), source, exe, args.child)
        else: run_timing(exe, source, args.root.resolve(), args.child, fmin=500, fmax=2000)
        return
    if args.root: parser.error('--root is internal to child supervision')
    with exclusive_probe(ROOT):
        root = ROOT/'artifacts'/('public-native-faults-'+uuid4().hex[:8]); root.mkdir()
        print('FAULT_ROOT='+str(root), flush=True)
        supervise(root, source, exe, args.case or ALL, keep_raw=args.keep_raw)


if __name__ == '__main__': main()

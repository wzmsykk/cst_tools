"""Serial real-CST copy acceptance; no force termination or original edits."""
import argparse
from dataclasses import asdict
from pathlib import Path
import sys
from uuid import uuid4
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.acceptance_session import exclusive_probe, cst_processes
from csttool.configuration import write_json_atomic
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.managed_cstworker import ManagedWorkerShutdownError
from csttool.result_reconciliation import file_hash
from test.managed_hom_ten_modes_fault_resume_integration_test import _config


class CloseFaultWorker(ManagedCSTWorker):
    fault = None

    def _build_macro(self):
        super()._build_macro()
        source = self.macro_path.read_text(encoding='ascii')
        anchors = {
            'restore': ('        CSTPMW_RestoreGoodParameters', '        Err.Raise vbObjectError + 2901, "L5 injected fault", "restore entry exception"'),
            'rebuild': ('        If Not Rebuild Then Err.Raise vbObjectError + 2401', '        StoreParameter "nmodes", "0"'),
            'save': ('    Save\n', '    Err.Raise vbObjectError + 2902, "L5 injected fault", "save entry exception"'),
        }
        if self.fault in anchors:
            anchor, injected = anchors[self.fault]
            assert source.count(anchor) == 1, anchor
            source = source.replace(anchor, injected + '\n' + anchor)
        self.macro_path.write_text(source, encoding='ascii', newline='\n')
        self.batch_script_path.write_text(source, encoding='ascii', newline='\n')


class PostprocessFaultWorker(ManagedCSTWorker):
    def _build_macro(self):
        super()._build_macro()
        source = self.macro_path.read_text(encoding='ascii')
        anchor = '            CustomPostProcess'
        assert source.count(anchor) == 1
        source = source.replace(anchor, '            Err.Raise vbObjectError + 2903, "L5 injected fault", "postprocess entry exception"\n' + anchor)
        self.macro_path.write_text(source, encoding='ascii', newline='\n')
        self.batch_script_path.write_text(source, encoding='ascii', newline='\n')


def run_case(executable, source, root, case, fault=None):
    root.mkdir(parents=True, exist_ok=False)
    report = dict(case=case, source=str(source), source_sha256=file_hash(source), passed=False)
    config = _config(root, '0', executable, source)
    config['postProcess'] = [{'resultName': 'frequency', 'method': 'Frequency', 'params': {'iModeNumber': 1}}]
    worker = None
    try:
        cls = ManagedCSTWorker
        if case == 'solver-failure':
            from test.support.validate_solver_failure_recovery import BoundaryProbeWorker
            cls = BoundaryProbeWorker
            config['paramList'].append(dict(name='probe_open_boundary', type='double'))
        if case == 'postprocess-failure':
            cls = PostprocessFaultWorker
        if case == 'close-fault':
            cls = CloseFaultWorker
            cls.fault = fault
            report['fault'] = fault
            report['injection_kind'] = 'runtime-entry-exception' if fault in {'restore', 'save'} else 'invalid-parameter' if fault == 'rebuild' else 'real-filesystem-write-blocker'
        worker = cls('0', config)
        report['session'] = worker.session_id
        if case != 'startup':
            params = dict(nmodes=0 if case in {'rebuild-failure', 'close-fault'} else 1, fmin=500, fmax=800)
            if case == 'solver-failure':
                params['probe_open_boundary'] = 1
            report['result'] = dict(worker.run_task(case, params=params))
            from test.support.validate_solver_failure_recovery import classify
            report['task_classification'] = classify(report['result'])
        if case == 'postprocess-failure':
            fields = [p for p in worker.project_path.with_suffix('').rglob('*')
                      if p.is_file() and p.suffix.lower() in {'.m3d', '.m3t', '.h5', '.hdf5', '.e', '.h'}]
            # Exact field files are discovered and recorded, not inferred from project existence.
            report['field_files_before_close'] = {str(p): file_hash(p) for p in fields}
        if case == 'close-fault':
            blockers = {'backup': Path(str(worker.project_path) + '.recovered.cst'),
                        'receipt': Path(str(worker.project_path) + '.recovery-saved'),
                        'publication': worker.protocol.root / 'close.receipt.tmp',
                        'stop-ack': worker.protocol.root / 'stop.ack'}
            if fault in blockers:
                blockers[fault].mkdir()
            try:
                worker.stop()
                raise AssertionError('fault close unexpectedly accepted')
            except ManagedWorkerShutdownError as exc:
                report['expected_stop_rejection'] = str(exc)
            worker._process.wait(timeout=120)
            from csttool.project_session_recovery import recover_project_sessions
            try:
                recover_project_sessions(root, timeout_per_session=10)
                report['recovery'] = 'reconciled-dead'
            except Exception as exc:
                report['recovery'] = 'blocked-preserved'
                report['recovery_error'] = str(exc)
            from csttool.project_session_recovery import discover_managed_sessions
            report['recovery_closures'] = [asdict(record.closure) for record in discover_managed_sessions(root)]
        else:
            worker.stop()
        report['closure'] = asdict(worker._shutdown_assessment())
        if case != 'close-fault':
            assert report['closure']['standard_closed'], report
        else:
            assert not report['closure']['standard_closed'], report
            assert report['closure']['process_state'] == 'exited', report
        if case == 'success':
            assert report['result']['TaskStatus'] == 'Success', report
            assert report['result']['PostProcessResult'], report
        elif case in {'rebuild-failure', 'solver-failure', 'close-fault', 'postprocess-failure'}:
            assert report['result']['TaskStatus'] == 'Failure', report
            assert worker.retiring, report
            assert not report['result']['ProjectSnapshot'], report
            if case == 'solver-failure':
                assert report['task_classification'] in {'start-return-0', 'start-exception', 'start-return-1-without-results'}, report
        if case == 'postprocess-failure':
            trace = (worker.observation_root / 'lifecycle.log').read_text()
            assert 'returned=1' in trace and 'recovery-rebuild' not in trace, trace
            report['field_files_after_close'] = {str(p): file_hash(p) for p in fields if p.is_file()}
            assert report['field_files_before_close'] and report['field_files_before_close'] == report['field_files_after_close'], report
        report['passed'] = True
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        if worker is not None:
            try:
                worker.stop()
            except Exception as stop_error:
                report['stop_error'] = str(stop_error)
            report['closure'] = asdict(worker._shutdown_assessment())
            if worker._process.poll() is None:
                try:
                    worker._process.wait(timeout=120)
                    report['closure_after_exit'] = asdict(worker._shutdown_assessment())
                except Exception as wait_error:
                    report['wait_error'] = str(wait_error)
        raise
    finally:
        report['source_unchanged'] = file_hash(source) == report['source_sha256']
        report['cst_processes_after'] = cst_processes()
        write_json_atomic(root / 'report.json', report)
        print(f'REPORT={root / "report.json"}', flush=True)


def run_codec(executable, source, root):
    from csttool.close_receipt import decode_close_receipt
    from csttool.close_receipt_contract import prepare_close_receipt_contract, verify_close_receipt_contract
    from csttool.cst_process_env import cst_process_environment
    before = file_hash(source)
    for name in ('startup', 'saved', 'restored', 'failed'):
        assert not cst_processes(), 'previous codec process has not exited'
        receipt = decode_close_receipt((ROOT / 'test/data/close_receipt_v2' / (name + '.txt')).read_text())
        workspace = prepare_close_receipt_contract(root / name, receipt, snapshot=b'x' * receipt.snapshot_bytes)
        model = workspace.root / 'codec-model.cst'
        shutil.copy2(source, model)
        script = model.with_suffix('') / 'Model/3D/Model.run'
        script.parent.mkdir(parents=True)
        shutil.copy2(workspace.macro_path, script)
        report = dict(case=name, source_sha256=before, passed=False)
        try:
            with (workspace.root / 'cst.log').open('wb') as log:
                process = subprocess.Popen([str(executable), '-m', '-b', str(model)], cwd=workspace.root,
                    stdout=log, stderr=subprocess.STDOUT, env=cst_process_environment(),
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                report['pid'] = process.pid
                report['exit_code'] = process.wait(timeout=180)  # codec only, no solve
            verify_close_receipt_contract(workspace, receipt)
            assert report['exit_code'] == 0 and not cst_processes(), report
            report['passed'] = True
        finally:
            report['source_unchanged'] = file_hash(source) == before
            write_json_atomic(workspace.root / 'report.json', report)
            print(f'CODEC_REPORT={workspace.root / "report.json"}', flush=True)


def verify_fault_matrix(root):
    from csttool.configuration import read_json
    from csttool.close_receipt import read_close_receipt
    from csttool.project_session_recovery import discover_managed_sessions
    expected = {'restore': ('restore-parameters', 'CLOSE_RESTORE_FAILED'),
                'rebuild': ('recovery-rebuild', 'CLOSE_REBUILD_FAILED'),
                'backup': ('recovery-snapshot', 'CLOSE_BACKUP_FAILED'),
                'save': ('save', 'CLOSE_SAVE_FAILED'),
                'receipt': ('recovery-receipt', 'CLOSE_RECEIPT_FAILED'),
                'publication': ('close-receipt', None), 'stop-ack': ('stop-ack', 'none')}
    reports = []
    for fault, (stage, code) in expected.items():
        folder = root / fault
        report = read_json(folder / 'report.json')
        assert report['passed'] and report['source_unchanged'], report
        records = discover_managed_sessions(folder)
        assert len(records) == 1 and records[0].process_alive is False, records
        record = records[0]
        trace = (record.root / 'lifecycle.log').read_text()
        assert f'shutdown {stage} failed:' in trace, trace
        if code is None:
            assert not (record.root / 'protocol/close.receipt').exists()
        else:
            receipt = read_close_receipt(record.root, record.session_id)
            assert receipt.error_code == code, receipt
        recovered = record.closure
        assert not recovered.standard_closed
        if fault in {'publication', 'stop-ack'}:
            assert recovered.needs_recovery and report['recovery'] == 'blocked-preserved'
        else:
            assert not recovered.needs_recovery and record.recovery_disposition == 'abandoned-dead'
        reports.append(dict(fault=fault, stage=stage, verified=True, recovery=asdict(recovered)))
    write_json_atomic(root / 'verification.json', dict(cases=reports, passed=True))
    return reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', type=Path)
    parser.add_argument('--verify-root', type=Path)
    parser.add_argument('--source', type=Path, default=ROOT / 'test/data/Pillbox/Pillbox.cst')
    parser.add_argument('--case', choices=['codec', 'prepare', 'startup', 'success', 'rebuild-failure', 'solver-failure', 'postprocess-failure', 'close-fault', 'fault-matrix'], default='startup')
    parser.add_argument('--fault', choices=['restore', 'rebuild', 'backup', 'save', 'receipt', 'publication', 'stop-ack'])
    args = parser.parse_args()
    if args.verify_root:
        verify_fault_matrix(args.verify_root.resolve())
        return
    if args.cst_exe is None:
        parser.error('--cst-exe is required for real execution')
    if args.case == 'close-fault' and args.fault is None:
        parser.error('--case close-fault requires --fault')
    with exclusive_probe(ROOT):
        root = ROOT / 'artifacts' / ('close-l5-' + args.case + '-' + uuid4().hex[:8])
        if args.case == 'codec':
            run_codec(args.cst_exe, args.source.resolve(), root)
        elif args.case == 'fault-matrix':
            root.mkdir()
            for fault in ('restore', 'rebuild', 'backup', 'save', 'receipt', 'publication', 'stop-ack'):
                assert not cst_processes(), 'previous copy has not exited'
                print(f'CASE_BEGIN={fault}', flush=True)
                run_case(args.cst_exe, args.source.resolve(), root / fault, 'close-fault', fault)
        elif args.case == 'prepare':
            from csttool.cst_preprocessor import CstProjectPreprocessor
            before = file_hash(args.source)
            root.mkdir()
            result = CstProjectPreprocessor(args.cst_exe, ROOT / 'data/preprocess_hom_parameters_v1.vb').preprocess(
                args.source, root / 'prepared.cst', root / 'params.json', root / 'temp', mesh_cells_per_wavelength=8)
            write_json_atomic(root / 'report.json', dict(source=str(args.source), source_sha256=before,
                source_unchanged=file_hash(args.source) == before, prepared=str(result.project_path)))
            print(f'PREPARED={result.project_path}', flush=True)
        else:
            run_case(args.cst_exe, args.source.resolve(), root, args.case, args.fault)


if __name__ == '__main__':
    main()

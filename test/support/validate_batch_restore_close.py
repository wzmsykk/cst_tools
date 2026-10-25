"""Serial real WinWrap/CST copy gate; no force termination."""
import sys
import time
import logging
import argparse
from pathlib import Path
from types import SimpleNamespace
from dataclasses import asdict
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.acceptance_session import exclusive_probe, cst_processes
from csttool.configuration import GlobalSettings, ProjectSettings, write_json_atomic
from csttool.cst_preprocessor import CstProjectPreprocessor
from csttool.cstmanager import CSTManager, SimulationTask
from csttool.managed_cstworker import ManagedCSTWorker, ManagedWorkerShutdownError
from csttool.result_reconciliation import file_hash
from csttool.close_receipt import read_close_receipt
from test.managed_hom_ten_modes_fault_resume_integration_test import _config


class FirstWorker(ManagedCSTWorker):
    calls = 0

    def run_task(self, name, *, params):
        self.calls += 1
        if self.calls == 2:
            params = {**params, 'nmodes': 0, 'probe_added': 7,
                      'probe001': 'probe000 + 999'}
        return super().run_task(name, params=params)


SEED = '''
Sub SeedExpressions
    Dim names(0 To 199) As String, values(0 To 199) As String
    Dim i As Long
    For i = 0 To 199
        names(i) = "probe" & Right("000" & CStr(i), 3)
        If i = 0 Then
            values(i) = "2"
        Else
            values(i) = "probe000 + " & CStr(i)
        End If
    Next i
    StoreParameters(names, values)
End Sub
'''


def late_close(executable, base, root):
    """Real macro pause, before Save; no delay or timeout in Solver."""
    class DelayedClose(ManagedCSTWorker):
        def _build_macro(self):
            super()._build_macro()
            macro = self.macro_path.read_text(encoding='ascii')
            anchor = '    Save\n'
            assert macro.count(anchor) == 1
            # Timer midnight wrap is handled; pause bounded to two seconds.
            macro = macro.replace('    Dim failureDetail As String',
                '    Dim failureDetail As String\n    Dim probeStarted As Double\n    Dim probeElapsed As Double')
            macro = macro.replace(anchor, '''    probeStarted = Timer
    Do
        DoEvents
        probeElapsed = Timer - probeStarted
        If probeElapsed < 0 Then probeElapsed = probeElapsed + 86400
    Loop While probeElapsed < 2
''' + anchor)
            self.macro_path.write_text(macro, encoding='ascii')
            self.batch_script_path.write_text(macro, encoding='ascii')

    config = _config(root, 'late', executable, base)
    config['postProcess'] = []
    worker = DelayedClose('late', config)
    worker.STOP_TIMEOUT = 0.3  # Test-only; production default remains 600.
    result = {'session': worker.session_id, 'injection': '2s pause before Save; no Solver call'}
    try:
        for attempt in range(2):
            started = time.monotonic()
            try:
                worker.stop()
                raise AssertionError('injected delayed close unexpectedly met deadline')
            except ManagedWorkerShutdownError:
                result[f'wait_{attempt + 1}'] = time.monotonic() - started
        assert result['wait_2'] < 0.25, result
        deadline = worker._stop_deadline
        worker._process.wait(timeout=60)
        assert worker.stop()
        assert worker._stop_deadline == deadline
        result['closure'] = asdict(worker._shutdown_assessment())
        assert result['closure']['standard_closed']
        result['passed'] = True
        return result
    finally:
        write_json_atomic(root / 'late-close-report.json', result)


def verify_existing(root, executable):
    """Recheck preserved evidence after a reporting-only harness error."""
    import json
    from csttool.session_closure import read_recorded_exit
    from csttool.runtime_protocol import FileProtocol
    report = json.loads((root / 'report.json').read_text(encoding='utf-8'))
    assert not cst_processes()
    assert report['retried_result']['TaskStatus'] == 'Success'
    assert len(report['workers']) == 2
    base = root / 'processed.cst'
    assert all(Path(w['input']) == base for w in report['workers'])
    assert all(w['input_sha256'] == file_hash(base) for w in report['workers'])
    verification = {'reporting_error': report.get('error'), 'closures': []}
    for item in report['workers']:
        session = root / 'temp/worker_0' / item['session']
        receipt = read_close_receipt(session, item['session'])
        # close-verification.json preserves the Popen observation, not guessed exit 0.
        saved = json.loads((session / 'close-verification.json').read_text())
        verification['closures'].append(saved)
        assert saved['assessment']['standard_closed']
        assert read_recorded_exit(session, item['session'], saved['process_id']) is not None
        assert FileProtocol(session / 'protocol').read_stop_ack(item['session']) is not None
        assert receipt.error_code == 'none'
    first_session = root / 'temp/worker_0' / report['workers'][0]['session']
    trace = next(root.glob('logs/*/workers/0/' + first_session.name + '/lifecycle.log')).read_text()
    assert 'stage=restore-batch' in trace and 'stage=restore-verify' in trace
    assert 'removed=1' in trace
    assert 'stage=restore-batch' in trace and 'returned; count=2' in trace
    assert report['failed_worker_closure']['standard_closed']
    first = report['first_result']
    receipt_path = Path(first['ReceiptPath'])
    adopted = json.loads(receipt_path.read_text())
    verification['first_snapshot_sha256'] = file_hash(first['ProjectSnapshot'])
    verification['first_receipt'] = adopted
    assert verification['first_snapshot_sha256'] == adopted['snapshot_sha256']
    if report.get('first_snapshot_sha256'):
        assert verification['first_snapshot_sha256'] == report['first_snapshot_sha256']
    verification['late'] = late_close(executable, base, root / 'late')
    verification['processes_after'] = cst_processes()
    assert not verification['processes_after']
    assert file_hash(report['source']) == report['source_sha256']
    verification['passed'] = True
    write_json_atomic(root / 'verification.json', verification)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cst-exe', type=Path, required=True)
    ap.add_argument('--verify-existing', type=Path)
    args = ap.parse_args()
    if args.verify_existing:
        with exclusive_probe(ROOT):
            verify_existing(args.verify_existing.resolve(), args.cst_exe)
        return
    root = ROOT / 'artifacts' / ('batch-restore-real-' + uuid4().hex[:8])
    root.mkdir()
    print('ACCEPTANCE_ROOT=' + str(root), flush=True)
    original = ROOT / 'test/data/Pillbox/Pillbox.cst'
    before = file_hash(original)
    report = {'source': str(original), 'source_sha256': before, 'passed': False}
    workers = []
    manager = None
    with exclusive_probe(ROOT):
        try:
            template = (ROOT / 'data/preprocess_hom_parameters_v1.vb').read_text(encoding='ascii')
            template = template.replace('    WriteStage "rebuild"',
                                        '    SeedExpressions\n    WriteStage "rebuild"', 1)
            seed = root / 'preprocess-template.vb'
            seed.write_text(template + SEED, encoding='ascii')
            prepared = CstProjectPreprocessor(args.cst_exe, seed).preprocess(
                original, root / 'processed.cst', root / 'params.json',
                root / 'preprocess', mesh_cells_per_wavelength=8)
            base = prepared.project_path
            digest = file_hash(base)
            config = SimpleNamespace(currProjectDir=root,
                settings=ProjectSettings(name='batch-close', cst_filename=Path('processed.cst')),
                get_postprocess_settings=lambda: [{'method': 'Frequency', 'resultName': 'frequency',
                                                   'params': {'iModeNumber': 1}}])
            glob = SimpleNamespace(settings=GlobalSettings().with_cst('2022', str(args.cst_exe)))

            def factory(worker_id, cfg, logger):
                cls = FirstWorker if not workers else ManagedCSTWorker
                worker = cls(worker_id, cfg, logger)
                workers.append(worker)
                report.setdefault('workers', []).append({'session': worker.session_id,
                    'input': str(cfg.project_path), 'input_sha256': file_hash(cfg.project_path)})
                write_json_atomic(root / 'report.json', report)
                return worker

            manager = CSTManager(glob, config, params=list(prepared.parameters),
                                 maxTask=1, worker_factory=factory)
            first = manager.execute(SimulationTask({'nmodes': 1, 'fmin': 480, 'fmax': 530},
                                    'confirmed', continue_from_snapshot=True))
            assert first['TaskStatus'] == 'Success', first
            snapshot = Path(first['ProjectSnapshot'])
            snapshot_hash = file_hash(snapshot)
            report['first_result'] = first
            report['first_snapshot_sha256'] = snapshot_hash
            result = manager.execute(SimulationTask({'nmodes': 1, 'fmin': 480, 'fmax': 530},
                'failure-then-base', retry_count=1, continue_from_snapshot=True))
            report['retried_result'] = result
            assert result['TaskStatus'] == 'Success', result
            assert len(workers) == 2
            assert workers[1].source_project == base.resolve()
            assert report['workers'][1]['input_sha256'] == digest
            assert file_hash(snapshot) == snapshot_hash
            old = workers[0]
            trace = (old.observation_root / 'lifecycle.log').read_text()
            report['failed_worker_closure'] = asdict(old._shutdown_assessment())
            report['failed_worker_receipt'] = asdict(read_close_receipt(old.root, old.session_id))
            assert 'stage=restore-batch' in trace and 'stage=restore-verify' in trace
            assert 'removed=1' in trace, trace
            assert 'returned; count=2' in trace, trace
            assert 'task undo ready; requested=5; changed=3' in trace, trace
            report['confirmed_snapshot_preserved'] = True
            manager.stop()
            manager = None
            report['closures'] = [asdict(w._shutdown_assessment()) for w in workers]
            assert all(c['standard_closed'] for c in report['closures'])
            report['base_unchanged'] = file_hash(base) == digest
            assert report['base_unchanged']
            report['late_close'] = late_close(args.cst_exe, base, root / 'late')
            report['passed'] = True
        except BaseException as error:
            report['error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            if manager is not None:
                try:
                    manager.stop()
                except Exception as error:
                    report['stop_error'] = str(error)
            report['original_unchanged'] = file_hash(original) == before
            report['processes_after'] = cst_processes()
            write_json_atomic(root / 'report.json', report)
    assert report['original_unchanged'] and not report['processes_after']
    print('REAL_BATCH_RESTORE_PASSED', flush=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()

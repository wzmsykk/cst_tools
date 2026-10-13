"""Document-backed incompatible-boundary probe; real Start, never a fake return."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.acceptance_session import exclusive_probe
from csttool.configuration import write_json_atomic
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.result_reconciliation import file_hash
from test.managed_hom_ten_modes_fault_resume_integration_test import _config


class BoundaryProbeWorker(ManagedCSTWorker):
    """Test-only macro addition, not a production fault-injection option."""

    def _build_macro(self):
        super()._build_macro()
        macro = self.macro_path.read_text(encoding='ascii')
        macro = macro.replace('    Dim solverReturn As Long',
                              '    Dim solverReturn As Long\n    Dim originalXmax As String\n    Dim probeOpen As Boolean')
        anchor = "    ' -m -b loads this project"
        assert macro.count(anchor) == 1
        macro = macro.replace(anchor, '    originalXmax = Boundary.GetXmax\n' + anchor)
        anchor = '            stage = "solver-config"'
        assert macro.count(anchor) == 1
        macro = macro.replace(anchor, anchor + '''
            EigenmodeSolver.SetMethodType "Default", "Tet"
            probeOpen = False
            For i = 0 To task.ParameterCount - 1
                If task.Parameters(i).Name = "probe_open_boundary" Then probeOpen = (task.Parameters(i).Value = "1")
            Next i
            If probeOpen Then
                If Not AddToHistory("CSTTools: solver failure probe", "Boundary.Xmax ""open""") Then Err.Raise vbObjectError + 2302, "probe", "Boundary history insertion failed"
                If Boundary.GetXmax <> "open" Then Err.Raise vbObjectError + 2301, "probe", "Open boundary read-back mismatch"
            Else
                If Not AddToHistory("CSTTools: solver failure probe", "Boundary.Xmax """ & originalXmax & """") Then Err.Raise vbObjectError + 2302, "probe", "Boundary history restore failed"
            End If
            CSTPMW_Trace stage, "boundary", "xmax=" & Boundary.GetXmax & "; probeOpen=" & CStr(probeOpen)
''')
        self.macro_path.write_text(macro, encoding='ascii', newline='\n')
        self.batch_script_path.write_text(macro, encoding='ascii', newline='\n')


def classify(result):
    failure = str(result.get('FailureReport') or '')
    if result['TaskStatus'] == 'Success':
        return 'success'
    if 'EigenmodeSolver.Start returned 0' in failure:
        return 'start-return-0'
    if 'solver-start failed:' in failure:
        return 'start-exception'
    if 'solver-result failed:' in failure or 'no eigenmodes are available' in failure:
        return 'start-return-1-without-results'
    if 'rebuild failed:' in failure or 'Rebuild returned False' in failure:
        return 'rebuild-failure'
    if 'parameters failed:' in failure or 'solver-config failed:' in failure:
        return 'parameter-or-configuration-error'
    return 'unclassified-failure'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True, type=Path)
    args = parser.parse_args()
    with exclusive_probe(ROOT):
        root = ROOT / 'artifacts' / ('solver-failure-recovery-' + uuid4().hex[:8])
        root.mkdir(parents=True)
        source = ROOT / 'artifacts/hom-mesh-baseline-de2d6b90/cell-30/prepared.cst'
        before = file_hash(source)
        report = {'source_sha256': before, 'cases': []}
        config = _config(root, '0', args.cst_exe, source)
        config['paramList'].append({'name': 'probe_open_boundary', 'type': 'double'})
        config['postProcess'] = [{'method': 'Frequency', 'resultName': 'frequency',
                                  'params': {'iModeNumber': 1}}]
        worker = None
        print(f'ACCEPTANCE_ROOT={root}', flush=True)
        try:
            worker = BoundaryProbeWorker('0', config)
            for name, count, opened in (('invalid-mode-count', 0, 0),
                                        ('unsupported-open-boundary', 1, 1),
                                        ('restored-boundary', 1, 0)):
                result = dict(worker.run_task(name, params={
                    'nmodes': count, 'probe_open_boundary': opened,
                    'fmin': 513.492631838138, 'fmax': 713.492631838138}))
                kind = classify(result)
                report['cases'].append({'name': name, 'classification': kind, 'result': result})
                write_json_atomic(root / 'report.json', report)
                print(f'CASE_COMPLETE name={name} classification={kind}', flush=True)
                if name == 'invalid-mode-count':
                    assert kind in ('parameter-or-configuration-error', 'rebuild-failure'), result
                elif name == 'unsupported-open-boundary':
                    # Actual setter/rebuild rejection is evidence, not a Start gate pass.
                    assert result['TaskStatus'] == 'Failure', result
                    assert not result['PostProcessResult'] and not result['ProjectSnapshot'], result
                else:
                    assert kind == 'success', result
                    assert float(result['PostProcessResult'][0]['value']) > 0, result
            report['same_worker_recovered'] = True
            report['start_return_0_gate_passed'] = any(
                case['classification'] == 'start-return-0' for case in report['cases'])
        except BaseException as error:
            report['failure'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            try:
                if worker is not None:
                    try:
                        report['stop_returned'] = worker.stop()
                    except Exception as error:
                        report['stop_returned'] = False
                        report['stop_error'] = f'{type(error).__name__}: {error}'
                    report['stop_ack'] = worker.protocol.read_stop_ack(worker.session_id) is not None
                    report['exit_code'] = worker._process.poll()
                    log = worker.log_path.read_text(errors='replace')
                    report['shutdown_errors'] = [token for token in (
                        'Unable to close sheet while a batch job is running',
                        'Expecting an existing scalar var.',
                        'EvaluateInternal CDbl(concaveL)') if token in log]
            finally:
                report['source_unchanged'] = file_hash(source) == before
                write_json_atomic(root / 'report.json', report)
        assert report['stop_returned'] and report['stop_ack'], report
        assert report['exit_code'] == 0 and report['source_unchanged'], report
        assert not report['shutdown_errors'], report
        print('RECOVERY_ACCEPTANCE_PASSED', flush=True)


if __name__ == '__main__':
    main()

"""Serial two-mesh full-cylinder doublet acceptance, without changing originals."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from test.support.validate_pillbox_full_domain import (
    GEOMETRY, RADIUS, LENGTH, prepare_ideal, export_native_support, batch_probe,
)
from test.managed_hom_ten_modes_fault_resume_integration_test import _config
from csttool.acceptance_session import exclusive_probe
from csttool.configuration import write_json_atomic, read_json
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.field_artifacts import SamplingSpec, artifacts_from_result, read_field
from csttool.saved_field_export import export_saved_fields
from csttool.physical_domain import common_quadrature
from csttool.pillbox_reference import tm110_reference
from csttool.mode_matching import MatchPolicy, weighted_overlap, normalized_mac, compare_subspaces
from csttool.result_reconciliation import file_hash


def validate_tracker(root):
    """Real exported fields, CLI sequence and missing-file analysis recovery only."""
    from csttool.vacuum_mode_tracking import (
        VacuumTrackingDomain, VacuumModeTracker, load_tracking_snapshot,
    )
    from dataclasses import asdict
    report = read_json(root / 'report.json')
    domain = VacuumTrackingDomain(GEOMETRY, 'PEC', 'Vacuum', True,
        'prepare/Model.run: PEC background and six electric walls, no symmetry',
        'full cylinder bounding box; native sole Vacuum solid agrees with analytic cylinder',
        '64^3 shared grid; previous 48/64/96 sampling acceptance, see physical-domain-pillbox-acceptance.md')
    descriptors = []
    for entry in report['meshes']:
        run = root / f'mesh-{entry["cell"]}'
        descriptors.append({'snapshot_id': f'cell-{entry["cell"]}',
            'result_file': str(run / 'fields/export-result.json'),
            'support_file': str(run / 'support/support.tsv'),
            'support_sha256': file_hash(run / 'support/support.tsv')})
    reference = load_tracking_snapshot(descriptors[0], domain, base=root)
    candidate = load_tracking_snapshot(descriptors[1], domain, base=root)
    tracker = VacuumModeTracker(reference, domain, MatchPolicy(.9, .05, .99,
                                                             maximum_frequency_change=.01))
    normal = tracker.evaluate(candidate, root / 'tracking/normal.json')
    original = candidate.fields[0].path
    quarantined = original.with_suffix('.h5.quarantined')
    assert not quarantined.exists()
    original.rename(quarantined)
    try:
        missing = tracker.evaluate(candidate, root / 'tracking/missing-file.json')
    finally:
        quarantined.rename(original)
    recovered = tracker.evaluate(candidate, root / 'tracking/recovered.json')
    request = {'domain': asdict(domain), 'policy': asdict(tracker.policy),
        'reference': {**descriptors[0], 'modes': [1, 2]},
        'candidates': [descriptors[1],
            {**descriptors[1], 'snapshot_id': 'missing-member', 'modes': [1]},
            {**descriptors[1], 'snapshot_id': 'swapped-and-recovered', 'modes': [2, 1]}]}
    write_json_atomic(root / 'tracking-request.json', request)
    process = subprocess.run([sys.executable, '-m', 'csttool.vacuum_mode_tracking',
        '--request', str(root / 'tracking-request.json'), '--output', str(root / 'tracking/sequence')],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    sequence = read_json(root / 'tracking/sequence/summary.json')
    passed = (normal['status'] == recovered['status'] == 'matched'
        and missing['status'] == 'unconfirmed' and tracker.reference is reference
        and process.returncode == 2
        and [step['status'] for step in sequence['steps']] == ['matched', 'unconfirmed', 'matched'])
    report['tracker_acceptance'] = {'gate_passed': passed, 'normal': normal,
        'missing_file': missing, 'recovered': recovered, 'sequence': sequence,
        'cli_exit_code': process.returncode, 'cli_stdout': process.stdout,
        'cli_stderr': process.stderr, 'solver_replayed_for_recovery': False,
        'reference_strategy': 'fixed-anchor', 'natural_number_swap_observed': False}
    report['gate_passed'] = report['gate_passed'] and passed
    write_json_atomic(root / 'report.json', report)
    assert passed, report['tracker_acceptance']
    print('TRACKER_GATE_PASSED=True', flush=True)


def compare_pair(reference, candidate, weights, scope):
    policy = MatchPolicy(.9, .05, .99)
    matrices = weighted_overlap(reference, candidate, weights, scope=scope)
    direct = compare_subspaces(matrices, policy)
    swapped = compare_subspaces(
        weighted_overlap(reference, candidate[:, :, ::-1], weights, scope=scope), policy)
    return {'subspace': direct, 'mac': normalized_mac(matrices).tolist(),
            'swapped_subspace': swapped,
            'swap_invariant': bool(np.isclose(direct['minimum_squared_overlap'],
                                             swapped['minimum_squared_overlap'], atol=1e-12, rtol=0))}


def verify_mesh_counts(executable, root):
    root = root.resolve()
    root.relative_to((ROOT / 'artifacts').resolve())
    report = read_json(root / 'report.json')
    for entry in report['meshes']:
        probe = root / f'mesh-{entry["cell"]}' / 'mesh-inventory'
        snapshot = Path(entry['solve']['ProjectSnapshot'])
        before = file_hash(snapshot)
        body = (f'    f=FreeFile\n    Open "{probe / "mesh-cells.txt"}" For Output As #f\n'
                '    Print #f, CStr(Mesh.GetNumberOfMeshCells)\n    Close #f\n')
        batch_probe(executable, snapshot, probe, body)
        entry['native_mesh_cells'] = int((probe / 'mesh-cells.txt').read_text().strip())
        assert entry['native_mesh_cells'] > 0
        assert file_hash(snapshot) == before
        write_json_atomic(root / 'report.json', report)
    report['distinct_mesh_verified'] = report['meshes'][1]['native_mesh_cells'] > report['meshes'][0]['native_mesh_cells']
    report['gate_passed'] = report['gate_passed'] and report['distinct_mesh_verified']
    write_json_atomic(root / 'report.json', report)
    assert report['distinct_mesh_verified'], report
    print(f'MESH_INVENTORY={[e["native_mesh_cells"] for e in report["meshes"]]}', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True, type=Path)
    parser.add_argument('--verify-mesh-root', type=Path,
                        help='Read mesh counts from completed snapshots; never rerun Solver')
    parser.add_argument('--meshes', nargs=2, type=int, default=(8, 10),
                        help='Two increasing cells-per-wavelength values (default: small 8 10)')
    parser.add_argument('--tracking', action='store_true', help='Accept new Tracker/CLI and analysis-only recovery')
    args = parser.parse_args()
    if args.verify_mesh_root:
        verify_mesh_counts(args.cst_exe, args.verify_mesh_root)
        return
    if not 1 <= args.meshes[0] < args.meshes[1]:
        parser.error('--meshes requires two positive increasing values')
    if shutil.disk_usage(ROOT).free < 8 * 1024**3:
        raise RuntimeError('Need at least 8 GiB free')
    root = ROOT / 'artifacts' / ('pillbox-cross-mesh-' + uuid4().hex[:8])
    root.mkdir(parents=True)
    print(f'ACCEPTANCE_ROOT={root}', flush=True)
    source = ROOT / 'test/data/Pillbox/Pillbox.cst'
    before = file_hash(source)
    report = {'geometry': GEOMETRY, 'source_sha256': before, 'meshes': [],
              'physical_identity_confirmed': False, 'policy_calibrated': False}
    spec = SamplingSpec((-RADIUS, RADIUS, -RADIUS, RADIUS, -LENGTH/2, LENGTH/2),
                        (64, 64, 64), 'specified-domain')
    arrays, supports, frequencies = [], [], []
    try:
        prepared = prepare_ideal(args.cst_exe, source, root / 'prepare')
        for mesh in args.meshes:
            run = root / f'mesh-{mesh}'
            config = _config(run / 'solve', '0', args.cst_exe, prepared)
            config['paramList'].append({'name': 'cell', 'type': 'double'})
            config['postProcess'] = [{'method': 'Frequency', 'resultName': f'frequency_{mode}',
                                     'params': {'iModeNumber': mode}} for mode in (1, 2)]
            entry = {'cell': mesh}
            report['meshes'].append(entry)
            worker = None
            with exclusive_probe(ROOT):
                try:
                    worker = ManagedCSTWorker('0', config)
                    result = dict(worker.run_task('ideal-TM110-doublet', params={
                        'nmodes': 2, 'fmin': 780, 'fmax': 850, 'cell': mesh}))
                    entry['solve'] = result
                    assert result['TaskStatus'] == 'Success', result
                finally:
                    if worker is not None:
                        entry['stop_returned'] = worker.stop()
                        entry['stop_ack'] = worker.protocol.read_stop_ack(worker.session_id) is not None
                        entry['exit_code'] = worker._process.poll()
            assert entry['stop_returned'] and entry['stop_ack'] and entry['exit_code'] == 0, entry
            snapshot = Path(result['ProjectSnapshot'])
            entry['snapshot_sha256'] = file_hash(snapshot)
            support = export_native_support(args.cst_exe, snapshot, spec, run / 'support')
            supports.append(support)
            q = common_quadrature([support], ['Vacuum'])
            settings = [{'method': 'ExportModeField', 'resultName': f'E_{mode}',
                         'params': {'iModeNumber': mode, 'field_kind': 'E',
                                    'sampling': spec.to_mapping()}} for mode in (1, 2)]
            export = export_saved_fields(args.cst_exe, snapshot, run / 'fields', settings)
            entry['export'] = export
            assert export['status'] == 'complete', export
            fields = artifacts_from_result(export['result_directory'], export['PostProcessResult'])
            data = np.stack([read_field(f) for f in fields], axis=-1)
            arrays.append(data)
            freq = [float(p['value']) for p in result['PostProcessResult']]
            frequencies.append(freq)
            entry['frequencies_mhz'] = freq
            entry['field_sha256'] = [f.file_sha256 for f in fields]
            entry['quadrature'] = q.to_mapping()
            analytic = tm110_reference(spec.points(), RADIUS, (-LENGTH/2, LENGTH/2))
            entry['analytic_subspace'] = compare_pair(analytic['fields'], data, q.weights_m3, q.scope)['subspace']
            write_json_atomic(root / 'report.json', report)
            print(f'MESH_COMPLETE cell={mesh} frequencies={freq}', flush=True)
        q = common_quadrature(supports, ['Vacuum'])
        report['cross_mesh'] = compare_pair(arrays[0], arrays[1], q.weights_m3, q.scope)
        report['relative_frequency_change'] = float(np.max(
            np.abs(np.sort(frequencies[0])-np.sort(frequencies[1])) / np.sort(frequencies[0])))
        report['gate_passed'] = (report['cross_mesh']['subspace']['status'] == 'matched'
            and report['cross_mesh']['swap_invariant']
            and report['relative_frequency_change'] < .01
            and all(e['analytic_subspace']['status'] == 'matched' for e in report['meshes']))
        report['sampling_note'] = '64^3 common grid; sampling convergence established separately, not repeated here'
        report['mesh_convergence_claim'] = 'two-mesh agreement only; not a three-level solver convergence study'
        print(f'GATE_PASSED={report["gate_passed"]}', flush=True)
        assert report['gate_passed'], report
    except BaseException as error:
        report['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['source_unchanged'] = file_hash(source) == before
        write_json_atomic(root / 'report.json', report)
    assert report['source_unchanged']
    verify_mesh_counts(args.cst_exe, root)
    if args.tracking:
        validate_tracker(root)


if __name__ == '__main__':
    main()

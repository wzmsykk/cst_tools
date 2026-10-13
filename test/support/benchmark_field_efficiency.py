"""Actual CST field access benchmark, without a solver run or source modification."""
import argparse
import csv
from pathlib import Path
import subprocess
import sys
import time
import threading
from uuid import uuid4
import numpy as np
import h5py
import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.configuration import read_json, write_json_atomic
from csttool.cst_process_env import cst_process_environment
from csttool.result_reconciliation import file_hash
from csttool.resource_usage import ResourceUsageRecorder
from csttool.acceptance_session import exclusive_probe, wait_probe


def publish_report(destination, report, resources):
    accepted = (report.get('completion') == 'SUCCESS' and 'failure' not in report
                and report['exit_code'] == 0 and report['session']['exit_confirmed']
                and not report['session']['foreign_processes']
                and report['source_unchanged'] and report['numeric_validation_passed'])
    report['status'] = 'Success' if accepted else 'Incomplete'
    report['resource_summary'] = resources.finish(report['status'])
    write_json_atomic(destination / 'report.json', report)
    print({key:report[key] for key in ('status','completion','exit_code','source_unchanged',
                                      'numeric_validation_passed','cst_process_seconds')},flush=True)
    return 0 if accepted else 1


def main():
    with exclusive_probe(ROOT):
        return run_probe()


def run_probe():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True)
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--public-native-only', action='store_true')
    parser.add_argument('--load-entry', choices=['project', 'application'], default='project')
    parser.add_argument('--exit-strategy', choices=['quit', 'return'], default='return')
    args = parser.parse_args()
    existing=[p.info['pid'] for p in psutil.process_iter(['pid','name'])
              if (p.info.get('name') or '').upper().startswith('CST DESIGN ENVIRONMENT')]
    if existing:
        raise RuntimeError(f'run efficiency probes serially; existing CST pids={existing}')
    evidence = ROOT / 'artifacts/hom-mesh-baseline-de2d6b90/report.json'
    point = next(p for p in read_json(evidence)['points'] if p['cell'] == 30)
    source = Path(point['result']['ProjectSnapshot'])
    original_hash = file_hash(source)
    destination = ROOT / 'artifacts' / ('field-efficiency-' + uuid4().hex[:8])
    destination.mkdir(parents=True)
    copy = destination / 'benchmark.cst'
    template = ('field_public_native.bas' if args.public_native_only else
                'field_native_efficiency.bas' if args.native_only else 'field_efficiency.bas')
    macro = (ROOT / 'test/support' / template).read_text(encoding='ascii')
    macro = macro.replace('%SOURCE%', str(source)).replace('%PROJECT%', str(copy)).replace('%ROOT%', str(destination))
    if args.load_entry == 'application':
        raise ValueError('Application entry disabled: project-bound macro execution is not yet validated; do not mix implicit Project calls')
    if args.exit_strategy == 'return':
        macro = macro.replace('    Quit\n', '    ProbeStage "returning"\n')
    macro_path = destination / 'benchmark.bas'
    macro_path.write_text(macro, encoding='ascii')
    print(f'BENCHMARK_ROOT={destination}', flush=True)
    started = time.perf_counter()
    with (destination / 'cst.log').open('wb') as log:
        process = subprocess.Popen([args.cst_exe, '-m', str(macro_path)],
                                   env=cst_process_environment(), stdout=log, stderr=subprocess.STDOUT)
        resources=ResourceUsageRecorder(destination,'probe',destination.name,'field-efficiency')
        stopped=threading.Event()
        def observe():
            while not stopped.is_set():
                resources.sample(process,force=True)
                stopped.wait(0.5)
        observer=threading.Thread(target=observe,daemon=True)
        observer.start()
        try:
            session = wait_probe(process, destination)
        finally:
            stopped.set();observer.join(timeout=2)
        resource_summary={}
    report = {'source': str(source), 'source_unchanged': file_hash(source) == original_hash,
              'session':session,
              'load_entry':args.load_entry, 'exit_strategy':args.exit_strategy,
              'cst_process_seconds': time.perf_counter() - started, 'exit_code': process.returncode,
              'solver_run': False, 'copy_method': 'CST SaveAs include_results=True; no filesystem companion copy',
              'sample_region_project_units': [-10,10,-10,10,-50,50],
              'scope': 'equal-weight common-point ROI diagnostic, not full-volume quadrature',
              'resource_summary':resource_summary,
              'python': []}
    success = destination / 'completed.txt'
    failure = destination / 'failed.txt'
    if failure.exists():
        report['failure'] = failure.read_text(errors='replace')
    report['completion'] = success.read_text().strip() if success.exists() else None
    if report['completion'] == 'SUCCESS' and not failure.exists():
        with (destination / 'timings.csv').open() as stream:
            report['cst_timings'] = list(csv.DictReader(stream))
        if args.public_native_only:
            report['scope'] = 'common ROI weighted sum: weight=1+x^2/100; route order alternated'
            for row in report['cst_timings']:
                if row['stage']!='public-native':
                    continue
                t=time.perf_counter()
                fields=[]; positions=[]
                for mode in (1,2):
                    path=destination / f"sample-{row['points']}-{row['repeat']}-mode{mode}.h5"
                    with h5py.File(path) as stream:
                        fields.append(stream['E-Field'][...]);positions.append(stream['Position'][...])
                if not np.array_equal(positions[0],positions[1]):
                    raise ValueError('coordinate mismatch')
                w=np.sqrt(1+positions[0]['x']**2/100)
                a,b=[np.column_stack([f[s]['re'].astype(float)+1j*f[s]['im'].astype(float)
                                     for s in ('x','y','z')])*w[:,None] for f in fields]
                actual=np.array([np.vdot(a,a).real,np.vdot(b,b).real,np.vdot(a,b).real,np.vdot(a,b).imag])
                seconds=time.perf_counter()-t
                expected=np.array([float(row[s]) for s in ('norm_a','norm_b','cross_re','cross_im')])
                export=next(float(r['seconds']) for r in report['cst_timings']
                    if r['stage']=='native-hdf5' and r['points']==row['points'] and r['repeat']==row['repeat'])
                report['python'].append({'points':int(row['points']),'repeat':int(row['repeat']),
                    'public_native_seconds':float(row['seconds']), 'hdf_pipeline_seconds':export+seconds,
                    'norm_scaled_error':float(np.max(np.abs(actual-expected))/max(actual[0],actual[1]))})
            report['numeric_validation_passed']=all(r['norm_scaled_error']<=1e-6 for r in report['python'])
            return publish_report(destination, report, resources)
        if args.native_only:
            raw = next(r for r in report['cst_timings'] if r['stage']=='synthetic-raw')
            conjugated = next(r for r in report['cst_timings'] if r['stage']=='synthetic-conjugated')
            report['native_only'] = True
            report['scope'] = 'same native mesh index sum; no volume weights or cross-mesh interpolation'
            report['synthetic_passed'] = (float(raw['cross_re'])==-1 and float(raw['cross_im'])==5
                and float(conjugated['cross_re'])==5 and float(conjugated['cross_im'])==1)
            errors = []
            for rep in (1,2,3):
                native = next(r for r in report['cst_timings'] if r['stage']=='native-total' and int(r['repeat'])==rep)
                reference = next(r for r in report['cst_timings'] if r['stage']=='reference-sum' and int(r['repeat'])==rep)
                expected = np.array([float(reference[k]) for k in ('norm_a','norm_b','cross_re','cross_im')])
                actual = np.array([float(native[k]) for k in ('norm_a','norm_b','cross_re','cross_im')])
                errors.append(float(np.max(np.abs(actual-expected))/max(expected[0],expected[1])))
            report['native_norm_scaled_errors'] = errors
            report['numeric_validation_passed'] = report['synthetic_passed'] and max(errors)<=1e-6
            return publish_report(destination, report, resources)
        for item in report['cst_timings']:
            if item['stage'] != 'vba-sum':
                continue
            prefix = f"sample-{item['points']}-{item['repeat']}"
            path = destination / (prefix + '.csv')
            t = time.perf_counter()
            data = np.loadtxt(path, delimiter=',')
            read_seconds = time.perf_counter() - t
            t = time.perf_counter()
            a = data[:, :3] + 1j * data[:, 3:6]
            b = data[:, 6:9] + 1j * data[:, 9:12]
            conversion_seconds = time.perf_counter() - t
            t = time.perf_counter()
            norm_a, norm_b = np.vdot(a, a).real, np.vdot(b, b).real
            cross = np.vdot(a, b)
            compute_seconds = time.perf_counter() - t
            expected = np.array([float(item[k]) for k in ('norm_a','norm_b','cross_re','cross_im')])
            actual = np.array([norm_a,norm_b,cross.real,cross.imag])
            if not np.isfinite(actual).all() or min(norm_a,norm_b) <= 0:
                raise ValueError('empty or nonfinite sampled fields')
            scale = max(norm_a, norm_b)
            report['python'].append({'points': int(item['points']), 'repeat': int(item['repeat']),
                'read_seconds': read_seconds, 'conversion_seconds': conversion_seconds,
                'compute_seconds': compute_seconds, 'csv_bytes': path.stat().st_size,
                'maximum_norm_scaled_error': float(np.max(np.abs(actual-expected))/scale),
                'mac': float(abs(cross)**2/(norm_a*norm_b)),
                'native_ascii_bytes': sum((destination / (prefix+f'-mode{m}.txt')).stat().st_size for m in (1,2)),
                'native_hdf5_bytes': sum((destination / (prefix+f'-mode{m}.h5')).stat().st_size for m in (1,2))})
            t = time.perf_counter()
            raw_fields, positions = [], []
            for mode in (1,2):
                with h5py.File(destination / (prefix+f'-mode{mode}.h5'), 'r') as stream:
                    raw_fields.append(stream['E-Field'][...])
                    positions.append(stream['Position'][...])
            hdf_read_seconds = time.perf_counter() - t
            if len(raw_fields[0]) != int(item['points']) or not np.array_equal(positions[0], positions[1]):
                raise ValueError('HDF5 point inventory/coordinates mismatch')
            t = time.perf_counter()
            fields = [np.column_stack([field[axis]['re'].astype(np.float64)
                       + 1j*field[axis]['im'].astype(np.float64) for axis in ('x','y','z')])
                      for field in raw_fields]
            hdf_conversion_seconds = time.perf_counter() - t
            t = time.perf_counter()
            hna, hnb = np.vdot(fields[0],fields[0]).real, np.vdot(fields[1],fields[1]).real
            hc = np.vdot(fields[0],fields[1])
            hdf_compute_seconds = time.perf_counter() - t
            row = report['python'][-1]
            row.update({'hdf_read_seconds': hdf_read_seconds,
                        'hdf_conversion_seconds': hdf_conversion_seconds,
                        'hdf_compute_seconds': hdf_compute_seconds,
                        'hdf_field_precision': 'float32 re/im converted to complex128',
                        'hdf_maximum_norm_scaled_error': float(np.max(np.abs(np.array([hna,hnb,hc.real,hc.imag])-expected))/scale),
                        'hdf_mac': float(abs(hc)**2/(hna*hnb)),
                        'hdf_vs_sample_maximum_relative_field_error': float(max(np.max(np.abs(fields[0]-a)), np.max(np.abs(fields[1]-b)))/max(np.max(np.abs(a)),np.max(np.abs(b))))})
    report['numeric_validation_passed'] = bool(report['python']) and all(
        row['maximum_norm_scaled_error'] <= 1e-10
        and row['hdf_maximum_norm_scaled_error'] <= 1e-10
        and row['hdf_vs_sample_maximum_relative_field_error'] <= 1e-10
        for row in report['python'])
    return publish_report(destination, report, resources)


if __name__ == '__main__':
    raise SystemExit(main())

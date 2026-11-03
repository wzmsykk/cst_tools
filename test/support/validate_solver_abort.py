"""Owned-copy, official abort calibration; not a production cancellation service.

The bridge deliberately uses only the CST-bundled Python and stdlib. Neither
process termination nor a synthetic solver return is used to create the fault.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(str(temporary), str(path))


def checked_process(identity):
    """Retain the exact native process handle across connect and abort."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
    handle = kernel.OpenProcess(0x1000, False, identity['pid'])
    if not handle:
        raise OSError(ctypes.get_last_error(), 'cannot verify owned native process')
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            raise OSError(ctypes.get_last_error(), 'GetProcessTimes failed')
        created = ((times[0].dwHighDateTime << 32) + times[0].dwLowDateTime) / 1e7 - 11644473600
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), 'QueryFullProcessImageName failed')
        if abs(created - identity['create_time']) > .001:
            raise ValueError('native PID reused')
        if os.path.normcase(os.path.realpath(buffer.value)) != os.path.normcase(os.path.realpath(identity['executable'])):
            raise ValueError('native executable mismatch')
        return kernel, handle
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def abort_when_running(project, root, identity, *, verify=checked_process, clock=time.monotonic,
                       pause=time.sleep, timeout=90, lifecycle_path=None):
    """One attempt only. A lost response stays unknown, never retried."""
    if (root / 'abort-intent.json').exists():
        raise RuntimeError('abort already reserved; reconcile evidence, never replay')
    started = clock()
    while clock() - started < timeout:
        if (root / 'cancel-bridge').exists():
            raise RuntimeError('bridge cancelled before abort')
        lifecycle = Path(lifecycle_path) if lifecycle_path is not None else root / 'lifecycle.log'
        text = lifecycle.read_text(encoding='utf-8', errors='replace') if lifecycle.exists() else ''
        if 'calling EigenmodeSolver.Start' in text and project.modeler.is_solver_running():
            kernel, handle = verify(identity)
            try:
                if os.path.normcase(os.path.realpath(project.filename())) != os.path.normcase(os.path.realpath(identity['project'])):
                    raise ValueError('connected project path mismatch')
                # Exclusive reservation also blocks two accidentally started bridges.
                # A partial intent after a crash remains unknown and blocks replay.
                with (root / 'abort-intent.json').open('x', encoding='utf-8') as stream:
                    json.dump(dict(identity=identity, trigger='solver-running',
                        lifecycle=text.splitlines()[-8:], attempt=1), stream, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Only this documented method changes the native state.
                value = project.modeler.abort_solver()
                write(root / 'abort-result.json', dict(returned=value, attempt=1))
                return value
            finally:
                kernel.CloseHandle(handle)
        pause(.05)
    raise RuntimeError('abort trigger not observed; no native abort sent')


def bridge(intent_path):
    intent_path = intent_path.resolve(strict=True)
    if ROOT / 'artifacts' not in intent_path.parents:
        raise ValueError('bridge intent outside acceptance artifacts')
    intent = json.loads(intent_path.read_text(encoding='utf-8'))
    if intent['parent_pid'] != os.getppid():
        raise ValueError('bridge parent mismatch')
    root = intent_path.parent
    identity = intent['identity']
    if Path(identity['project']).resolve() != root / 'worker-input.cst':
        raise ValueError('bridge project/session mismatch')
    lifecycle = Path(intent.get('lifecycle_path', root / 'lifecycle.log')).resolve()
    if (ROOT / 'artifacts' not in lifecycle.parents or lifecycle.name != 'lifecycle.log'
            or lifecycle.parent.name != root.name):
        raise ValueError('bridge lifecycle/session mismatch')
    kernel, handle = checked_process(identity)
    try:
        sys.path.insert(0, intent['python_libraries'])
        import cst.interface
        environment = cst.interface.DesignEnvironment.connect(identity['pid'])
        project = environment.get_open_project(identity['project'])
        if Path(project.filename()).resolve() != Path(identity['project']).resolve():
            raise ValueError('connected project mismatch')
        write(root / 'bridge-ready.json', dict(identity=identity, project=project.filename()))
        abort_when_running(project, root, identity, lifecycle_path=lifecycle)
    finally:
        kernel.CloseHandle(handle)


def owned_environment(worker):
    import psutil
    from csttool.process_identity import observe_process_identity
    if observe_process_identity(worker.root, worker._process.pid)[0] != 'matched':
        raise ValueError('launcher ownership not confirmed')
    executable = worker.executable.parent / 'AMD64' / 'CST DESIGN ENVIRONMENT_AMD64.exe'
    peers = [p for p in psutil.Process(worker._process.pid).children(recursive=True)
             if os.path.normcase(os.path.realpath(p.exe())) == os.path.normcase(os.path.realpath(executable))]
    if len(peers) != 1:
        raise ValueError('expected exactly one owned native environment')
    process = peers[0]
    return dict(pid=process.pid, create_time=process.create_time(), executable=process.exe(),
                project=str(worker.project_path.resolve()))


def wait_ready(process, root, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (root / 'bridge-ready.json').exists():
            return
        if process.poll() is not None:
            raise RuntimeError('official bridge failed before dispatch; inspect bridge.log')
        time.sleep(.05)
    raise RuntimeError('official bridge connection timed out; no task dispatched')


def finish_bridge(process, root):
    (root / 'cancel-bridge').touch()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        # A bounded bridge communication failure is not a solver failure.
        # This Popen is the Python bridge only, never the CST launcher/tree.
        process.terminate()
        process.wait(timeout=10)
        raise RuntimeError('Python bridge stopped; native abort outcome may be unknown; no retry')


def run(executable, source, root):
    sys.path.insert(0, str(ROOT))
    import shutil
    from dataclasses import asdict
    from csttool.acceptance_session import cst_processes
    from csttool.managed_cstworker import ManagedCSTWorker
    from csttool.project_session_recovery import discover_managed_sessions
    from test.support.validate_hom_recovery_native import FixturePreprocessor, config, stop
    from test.support.validate_public_faults import digest, cleanup_case
    from test.support.validate_solver_failure_recovery import classify
    assert shutil.disk_usage(root).free > 1024**3
    report = dict(passed=False, source_sha256=digest(source), trigger='solver-running',
                  driver_sha256=digest(Path(__file__)))
    prepared = root / 'processed.cst'
    worker = helper = None
    result = None
    try:
        FixturePreprocessor(executable, ROOT / 'data/preprocess_hom_parameters_v1.vb').preprocess(
            source, prepared, root / 'params.json', root / 'prepare', mesh_cells_per_wavelength=4)
        baseline = digest(prepared)
        worker = ManagedCSTWorker('0', config(root / 'aborted', executable, prepared))
        identity = owned_environment(worker)
        intent = worker.root / 'bridge-intent.json'
        write(intent, dict(parent_pid=os.getpid(), identity=identity,
            python_libraries=str(executable.parent / 'AMD64/python_cst_libraries')))
        with (worker.root / 'bridge.log').open('wb') as log:
            helper = subprocess.Popen([str(executable.parent / 'AMD64/python/python.exe'), str(Path(__file__).resolve()),
                '--bridge', str(intent)], stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_ready(helper, worker.root)
                result = dict(worker.run_task('official-abort', params=dict(nmodes=1, fmin=500, fmax=2000, cell=4)))
            finally:
                finish_bridge(helper, worker.root)
        report['abort_session'] = str(worker.root)
        report['abort_result'] = json.loads((worker.root / 'abort-result.json').read_text(encoding='utf-8'))
        report['classification'] = classify(result)
        report['result'] = result
        assert report['abort_result']['returned'] is True, report
        assert report['classification'] in ('start-return-0', 'start-exception',
                                            'start-return-1-without-results'), report
        assert result['TaskStatus'] == 'Failure' and not result['PostProcessResult'] and not result['ProjectSnapshot'], report
        stop(worker, failed=True)
        worker = None
        assert not cst_processes(), 'native closure unconfirmed; do not start replacement'
        replacement = ManagedCSTWorker('1', config(root / 'replacement', executable, prepared))
        try:
            recovered = dict(replacement.run_task('fresh-recovery', params=dict(nmodes=1, fmin=500, fmax=2000, cell=4)))
            report['recovered'] = recovered
            assert recovered['TaskStatus'] == 'Success' and recovered['ProjectSnapshot'], recovered
        finally:
            stop(replacement, failed=report.get('recovered', {}).get('TaskStatus') == 'Failure')
        sessions = [session for directory in (root / 'aborted', root / 'replacement')
                    for session in discover_managed_sessions(directory)]
        report['closures'] = [asdict(s.closure) for s in sessions]
        assert len(sessions) == 2 and all(s.closure.standard_closed for s in sessions), report
        traces = [path.read_text(encoding='utf-8', errors='replace') for path in root.glob('*/temp/worker_*/*/lifecycle.log')]
        report['solver_calls'] = sum(text.count('calling EigenmodeSolver.Start') for text in traces)
        assert report['solver_calls'] == 2, report
        report['source_unchanged'] = digest(source) == report['source_sha256']
        report['prepared_unchanged'] = digest(prepared) == baseline
        assert report['source_unchanged'] and report['prepared_unchanged']
        report['passed'] = True
    except BaseException as error:
        report['error'] = '{}: {}'.format(type(error).__name__, error)
        raise
    finally:
        try:
            if worker is not None:
                stop(worker, failed=result is not None and result['TaskStatus'] == 'Failure')
        finally:
            report['remaining_cst'] = cst_processes()
            write(root / 'report.json', report)
    report['cleaned_companions'] = cleanup_case(root, source)
    write(root / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--run-cst', action='store_true')
    parser.add_argument('--bridge', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.bridge:
        intent_path = args.bridge.resolve(strict=True)
        if ROOT / 'artifacts' not in intent_path.parents:
            parser.error('bridge intent outside acceptance artifacts')
        try:
            bridge(intent_path)
        except BaseException as error:
            write(intent_path.parent / 'bridge-failure.json', dict(error='{}: {}'.format(type(error).__name__, error),
                outcome='unknown' if (intent_path.parent / 'abort-intent.json').exists() else 'not-sent'))
            raise
        return
    if not args.run_cst or not args.source or not args.cst_exe:
        parser.error('--run-cst, --source and --cst-exe are required')
    sys.path.insert(0, str(ROOT))
    from csttool.acceptance_session import exclusive_probe
    with exclusive_probe(ROOT):
        root = ROOT / 'artifacts' / ('solver-abort-' + uuid4().hex[:8])
        root.mkdir()
        print('ABORT_ROOT=' + str(root), flush=True)
        run(args.cst_exe.resolve(strict=True), args.source.resolve(strict=True), root)


if __name__ == '__main__':
    main()

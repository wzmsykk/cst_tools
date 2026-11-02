"""Explicit, registration-free installed WinWrap NoUI probe; never launches CST.

Only the documented development-installation Initialize token is tried once.
No licence files are read. SyntaxCheck never calls Run/RunThis/RunFile.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
NOUI = "{B20ABC7B-2021-11D6-8F7F-0000861EF01D}"
CODEUNIT = "{B20ABCE9-2021-11D6-8F7F-0000861EF01D}"
TYPELIB = "{B20ABC70-2021-11D6-8F7F-0000861EF01D}"


def save(path, report):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def activate_manifest(directory, install):
    """Map installed classes only within this process's activation context."""
    # SxS resolves root file entries relative to the manifest directory.
    # Test-local binary copies support SxS without modifying the installation.
    # Never copy licence files; these are not release payloads.
    for name in ('WB9ENT64.OCX','wwb9_64.dll'):
        target = directory/name
        if target.exists():
            if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256((install/name).read_bytes()).digest():
                raise ValueError('existing probe binary differs from installation')
        else:
            shutil.copyfile(install/name,target)
    manifest = directory/'noui.manifest'
    manifest.write_text(f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
 <assemblyIdentity type="win32" name="CstTools.WinWrapProbe" version="1.0.0.0" processorArchitecture="amd64"/>
 <file name="WB9ENT64.OCX"><comClass clsid="{NOUI}" threadingModel="Apartment" tlbid="{TYPELIB}"/>
 <typelib tlbid="{TYPELIB}" version="1.0" helpdir=""/></file>
 <file name="wwb9_64.dll"><comClass clsid="{CODEUNIT}" threadingModel="Apartment"/>
 <typelib tlbid="{{B20ABCD0-2021-11D6-8F7F-0000861EF01D}}" version="1.1" helpdir=""/></file>
</assembly>
''', encoding='utf-8')

    class ACTCTX(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.ULONG), ('dwFlags', wintypes.DWORD),
                    ('lpSource', wintypes.LPCWSTR), ('wProcessorArchitecture', wintypes.WORD),
                    ('wLangId', wintypes.WORD), ('lpAssemblyDirectory', wintypes.LPCWSTR),
                    ('lpResourceName', wintypes.LPCWSTR), ('lpApplicationName', wintypes.LPCWSTR),
                    ('hModule', wintypes.HMODULE)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateActCtxW.argtypes = [ctypes.POINTER(ACTCTX)]
    kernel.CreateActCtxW.restype = wintypes.HANDLE
    kernel.ActivateActCtx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t)]
    kernel.ActivateActCtx.restype = wintypes.BOOL
    kernel.DeactivateActCtx.argtypes = [wintypes.DWORD, ctypes.c_size_t]
    kernel.DeactivateActCtx.restype = wintypes.BOOL
    kernel.ReleaseActCtx.argtypes = [wintypes.HANDLE]
    kernel.ReleaseActCtx.restype = None
    context = ACTCTX()
    context.cbSize = ctypes.sizeof(ACTCTX)
    context.dwFlags = 4  # ACTCTX_FLAG_ASSEMBLY_DIRECTORY_VALID
    context.lpSource = str(manifest)
    context.lpAssemblyDirectory = str(directory)
    handle = kernel.CreateActCtxW(ctypes.byref(context))
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    cookie = ctypes.c_size_t()
    if not kernel.ActivateActCtx(handle, ctypes.byref(cookie)):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.ReleaseActCtx(handle)
        raise error
    return kernel, handle, cookie


def cases(marker):
    q = str(marker).replace('"', '""')
    def module(body, declarations=''):
        return '\'#Language "WWB-COM"\nOption Explicit\n'+declarations+'Sub Main\n'+body+'\nEnd Sub\n'
    local = 'Private Function RestoreDoubleParameter(ByVal n As String) As Double\n RestoreDoubleParameter = 2\nEnd Function\nPrivate Sub Zrange(ByVal low As Double, ByVal high As Double)\nEnd Sub\n'
    original = '((-RestoreDoubleParameter("L"))/2), (RestoreDoubleParameter("L")/2)'
    fixed = '0+((-RestoreDoubleParameter("L"))/2), 0+(RestoreDoubleParameter("L")/2)'
    return [
        ('body-not-executed', module(f'Open "{q}" For Output As #1\nPrint #1, "MUST-NOT-RUN"\nClose #1'), 'must-accept'),
        ('obvious-syntax-error', module('Dim x As Long\nx = ('), 'must-reject'),
        ('local-zrange-original', module('Zrange '+original, local), 'calibrate-call-shape'),
        ('local-zrange-fixed', module('Zrange '+fixed, local), 'must-accept'),
        ('local-zrange-call', module('Call Zrange('+original+')', local), 'calibrate-call-shape'),
        ('cst-zrange-original-unbound', module('With Cylinder\n .Zrange '+original+'\nEnd With'), 'no-cst-extension-expected'),
        ('cst-zrange-fixed-unbound', module('With Cylinder\n .Zrange '+fixed+'\nEnd With'), 'no-cst-extension-expected'),
        ('duplicate-declaration', module('Dim x As String\nDim x As Integer'), 'must-reject'),
        ('unicode', module('Dim s As String\ns = "中文"'), 'must-accept'),
    ]


def child(directory, install):
    import pythoncom
    from win32com.client import dynamic
    report = dict(pid=os.getpid(), stages=[], cases=[], initialized=False, shutdown=None, disconnect=None)
    path = directory/'child.json'
    def stage(name):
        report['stages'].append(dict(name=name, time=time.time()))
        save(path, report)
    engine = None
    activation = None
    dll_directory = None
    pythoncom.CoInitialize()
    try:
        dll_directory = os.add_dll_directory(str(install))
        stage('activation-context')
        activation = activate_manifest(directory, install)
        stage('create-inproc-noui')
        dispatch = pythoncom.CoCreateInstance(NOUI, None, pythoncom.CLSCTX_INPROC_SERVER, pythoncom.IID_IDispatch)
        engine = dynamic.Dispatch(dispatch)
        dispatch = None
        stage('ignore-dialogs')
        engine.IgnoreDialogs = True
        stage('initialize-state')
        report['initialized_before'] = bool(engine.IsInitialized())
        if not report['initialized_before']:
            stage('initialize-documented-development-token')
            report['initialize_return'] = engine.Initialize('****-*******-**')
        report['initialized'] = bool(engine.IsInitialized())
        if not report['initialized']:
            report['initialize_diagnostics'] = {}
            for prop in ('ErrorNumber','ErrorText','ErrorSource'):
                try:
                    report['initialize_diagnostics'][prop] = getattr(engine,prop)
                except Exception as error:
                    report['initialize_diagnostics'][prop] = dict(read_error=str(error))
            raise RuntimeError('documented initialization did not initialize object')
        marker = directory/'checked-body-executed.txt'
        for name, source, expectation in cases(marker):
            stage('check-'+name)
            (directory/(name+'.bas')).write_text(source, encoding='utf-8')
            engine.Code = source
            started = time.perf_counter()
            accepted = bool(engine.SyntaxCheck)
            diagnostics = {prop:getattr(engine, prop) for prop in ('ErrorNumber','ErrorLine','ErrorOffset','ErrorText','ErrorSource','ErrorFile')}
            report['cases'].append(dict(name=name, expectation=expectation, accepted=accepted, elapsed_ms=(time.perf_counter()-started)*1000, diagnostics=diagnostics, body_marker_absent=not marker.exists()))
            save(path, report)
        report['body_marker_absent'] = not marker.exists()
    except Exception as error:
        report['error'] = dict(type=type(error).__name__, message=str(error), hresult=getattr(error,'hresult',None))
    finally:
        if engine is not None:
            try:
                stage('shutdown')
                report['shutdown'] = engine.Shutdown()
                if report['shutdown'] == 0:
                    stage('disconnect')
                    report['disconnect'] = bool(engine.Disconnect())
            except Exception as error:
                report['close_error'] = str(error)
            engine = None
            gc.collect()
        if dll_directory is not None:
            dll_directory.close()
        if activation is not None:
            kernel, handle, cookie = activation
            report['activation_context_deactivated'] = bool(kernel.DeactivateActCtx(0,cookie))
            kernel.ReleaseActCtx(handle)
        pythoncom.CoUninitialize()
        stage('child-return')


def evaluate_report(report):
    """Normal helper exit is separate from usable engine and completed checks."""
    result = report.get('child', {})
    rows = result.get('cases', [])
    closed = (report.get('child_normal_exit') is True and result.get('shutdown') == 0
              and result.get('disconnect') is True)
    initialized = result.get('initialized') is True
    required_names = {name for name, _, _ in cases(Path('unused-marker'))}
    present = {row.get('name') for row in rows}
    expected = all(row.get('accepted') is (row['expectation'] == 'must-accept')
                   for row in rows if row.get('expectation') in ('must-accept','must-reject'))
    completed = (closed and initialized and present == required_names and len(rows) == len(required_names)
                 and expected and result.get('body_marker_absent') is True and not report.get('new_cst'))
    return dict(object_close_confirmed=closed, initialized=initialized,
                syntax_checks=len(rows), calibration_complete=completed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', required=True, type=Path)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    install = args.install.resolve(strict=True)
    directory = args.directory.resolve()
    if os.name != 'nt' or not directory.is_relative_to(ROOT/'artifacts'):
        parser.error('Windows and workspace artifacts directory required')
    directory.mkdir(parents=True, exist_ok=True)
    if args.child:
        child(directory, install)
        return
    sys.path.insert(0,str(ROOT))
    from csttool.acceptance_session import cst_processes
    baseline = cst_processes()
    report = dict(activation_mode='manifest-local-copies', baseline_cst=baseline, no_cst_launch_requested=True, child_normal_exit=False,
                  inputs=[dict(name=name,sha256=hashlib.sha256((install/name).read_bytes()).hexdigest()) for name in ('WB9ENT64.OCX','wwb9_64.dll')])
    with (directory/'child.log').open('wb') as log:
        process = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--install',str(install),'--directory',str(directory),'--child'], cwd=directory, stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        report['child_pid'] = process.pid
        save(directory/'report.json',report)
        try:
            report['child_exit_code'] = process.wait(timeout=45)
            report['child_normal_exit'] = process.returncode == 0
        except subprocess.TimeoutExpired:
            report['wait_expired'] = True  # Do not kill or claim normal shutdown.
    report['after_cst'] = cst_processes()
    before_ids = {(r['pid'],r['create_time']) for r in baseline}
    report['new_cst'] = [r for r in report['after_cst'] if (r['pid'],r['create_time']) not in before_ids]
    child_path = directory/'child.json'
    if child_path.exists():
        report['child'] = json.loads(child_path.read_text(encoding='utf-8'))
    report['verification'] = evaluate_report(report)
    save(directory/'report.json',report)
    print(json.dumps(report,ensure_ascii=True,indent=2),flush=True)
    if not report['verification']['calibration_complete']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

"""Explicit saved-result export without Solver.Start, Rebuild or parameter changes."""
import os
from pathlib import Path
import subprocess
import time
from .cst_process_env import cst_process_environment
from .configuration import write_json_atomic
from .postprocess_cst import CstPostProcessor
from .result_reconciliation import file_hash


def prepare_saved_field_export(source, destination, settings):
    source=Path(source).resolve()
    destination=Path(destination).resolve()
    if not source.is_file() or source.suffix.lower()!='.cst':
        raise ValueError('saved CST project required')
    destination.mkdir(parents=True,exist_ok=True)
    if (destination/'copy.cst').exists() or (destination/'export.bas').exists():
        raise FileExistsError('use a fresh export workspace')
    if not settings or any(p.get('method')!='ExportModeField' for p in settings):
        raise ValueError('saved export permits only field artifacts')
    processor=CstPostProcessor()
    processor.configure(settings)
    processor.set_result_directory(destination)
    vb=lambda value:str(value).replace('"','""')
    source_vb=''.join(processor.render_vb())
    macro=f'''\n'#Language "WWB-COM"
Option Explicit
Public outFullDir As String
{source_vb}
Sub Main
    Dim message As String,f As Integer
    On Error GoTo Failed
    OpenFile "{vb(source)}"
    SaveAs "{vb(destination/'copy.cst')}",True
    outFullDir="{vb(str(destination)+os.sep)}"
    CustomPostProcess
    Save
    f=FreeFile
    Open "{vb(destination/'completed.txt')}" For Output As #f
    Print #f,"SUCCESS"
    Close #f
    Quit
    Exit Sub
Failed:
    message=CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    Close
    f=FreeFile
    Open "{vb(destination/'failed.txt')}" For Output As #f
    Print #f,message
    Close #f
    Quit
End Sub
'''
    path=destination/'export.bas'
    path.write_text(macro.lstrip(),encoding='utf-8')
    return path,processor


def export_saved_fields(executable, source, destination, settings):
    source=Path(source)
    destination=Path(destination)
    before=file_hash(source)
    path,processor=prepare_saved_field_export(source,destination,settings)
    started=time.perf_counter()
    options={}
    if os.name=='nt':
        info=subprocess.STARTUPINFO()
        info.dwFlags|=subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow=7
        options={'startupinfo':info,'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
    with (destination/'cst.log').open('wb') as log:
        process=subprocess.Popen([str(executable),'-m',str(path)],env=cst_process_environment(),
                                 stdout=log,stderr=subprocess.STDOUT,**options)
        # No forced kill; marker publication and process exit are both required.
        process.wait()
    marker=destination/'completed.txt'
    result={'source':str(source.resolve()),'source_sha256':before,'source_unchanged':file_hash(source)==before,
            'exit_code':process.returncode,'wall_seconds':time.perf_counter()-started,
            'result_directory':str(destination.resolve()),'solver_run':False,
            'PostProcessResult':processor.read_all_results(),
            'status':'complete' if marker.exists() and marker.read_text().strip()=='SUCCESS' and process.returncode==0 else 'incomplete'}
    if not result['source_unchanged']:
        result['status']='incomplete'
    write_json_atomic(destination/'export-result.json',result)
    return result

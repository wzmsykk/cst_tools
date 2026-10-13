"""Explicit saved-result export without Solver.Start, Rebuild or parameter changes."""
import os
from pathlib import Path
import subprocess
import time
from .cst_process_env import cst_process_environment
from .configuration import write_json_atomic
from .postprocess_cst import CstPostProcessor
from .result_reconciliation import file_hash
from .acceptance_session import exclusive_probe, wait_probe


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
Sub ProbeStage(value As String)
    Dim stageFile As Integer
    stageFile=FreeFile
    Open "{vb(destination/'stage.partial')}" For Output As #stageFile
    Print #stageFile,value
    Close #stageFile
    If Dir("{vb(destination/'stage.txt')}")<>"" Then Kill "{vb(destination/'stage.txt')}"
    Name "{vb(destination/'stage.partial')}" As "{vb(destination/'stage.txt')}"
End Sub
Sub Main
    Dim message As String,f As Integer
    On Error GoTo Failed
    ProbeStage "loading"
    OpenFile "{vb(source)}"
    ProbeStage "loaded"
    SaveAs "{vb(destination/'copy.cst')}",True
    ProbeStage "saved-copy"
    outFullDir="{vb(str(destination)+os.sep)}"
    CustomPostProcess
    ProbeStage "exported"
    Save
    f=FreeFile
    Open "{vb(destination/'completed.txt')}" For Output As #f
    Print #f,"SUCCESS"
    Close #f
    ProbeStage "returning"
    Exit Sub
Failed:
    message=CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    Close
    f=FreeFile
    Open "{vb(destination/'failed.txt')}" For Output As #f
    Print #f,message
    Close #f
    ProbeStage "failed-returning"
End Sub
'''
    path=destination/'export.bas'
    path.write_text(macro.lstrip(),encoding='utf-8')
    return path,processor


def export_saved_fields(executable, source, destination, settings):
    with exclusive_probe(Path(__file__).resolve().parents[1]):
        return _export_saved_fields(executable, source, destination, settings)


def _export_saved_fields(executable, source, destination, settings):
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
        try:
            session = wait_probe(process, destination)
        except Exception as error:
            write_json_atomic(destination/'export-result.json', {
                'status':'incomplete', 'failure':str(error), 'solver_run':False,
                'source':str(source.resolve()), 'source_sha256':before,
                'source_unchanged':file_hash(source)==before,
                'result_directory':str(destination.resolve()),
                'session_status_path':str((destination/'session-status.json').resolve()),
                'exit_code':process.poll(), 'PostProcessResult':[],
            })
            raise
    marker=destination/'completed.txt'
    result={'source':str(source.resolve()),'source_sha256':before,'source_unchanged':file_hash(source)==before,
            'session':session,
            'exit_code':process.returncode,'wall_seconds':time.perf_counter()-started,
            'result_directory':str(destination.resolve()),'solver_run':False,
            'PostProcessResult':processor.read_all_results(),
            'status':'complete' if marker.exists() and marker.read_text().strip()=='SUCCESS' and process.returncode==0 else 'incomplete'}
    if (not result['source_unchanged'] or session['foreign_processes']
            or (destination/'failed.txt').exists()
            or any(not p.get('value') or p['value'].get('status') != 'available'
                   for p in result['PostProcessResult'])):
        result['status']='incomplete'
    write_json_atomic(destination/'export-result.json',result)
    return result

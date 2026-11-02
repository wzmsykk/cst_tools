"""Owner-bound native observation producer and RunStore reconciliation.

No process launch, arbitrary VBA input or private database parsing is exposed here.
The execution owner supplies its approved setup/history and closed-process proof.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from .configuration import write_json_atomic
from .execution_snapshot import (BUILD, ExecutionBinding, ExecutionConfig, ExecutionExpectation,
                                 verify_execution_artifact, read_snapshot_record, is_cst_2022)
from .vb_codec import quote_vb_string

KEYS = ('SolverTypeTet','FrequencyTargetActive','FrequencyTargetValue','AdaptionActiveTet','Modes','MeshType')
NATIVE_VERSION = 'Version 2022.5 - Jun 03 2022'
MODELER_SHA256 = 'a1cb2ec6316592020e81129fa0687343db2c650d82286c79a22ef4e08310db98'


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_capture_installation(executable):
    executable = Path(executable).resolve(strict=True)
    modeler = executable.parent/'AMD64/modeler_AMD64.exe'
    def file_digest(path):
        digest = hashlib.sha256()
        before = path.stat()
        with path.open('rb') as stream:
            while chunk := stream.read(1024*1024):
                digest.update(chunk)
        after = path.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError('installation changed during hashing')
        return digest.hexdigest()
    modeler_hash = file_digest(modeler)
    return dict(executable=str(executable),launcher_sha256=file_digest(executable),
                modeler_sha256=modeler_hash,profile_major='2022')


def _task_root(store, task_id):
    if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',task_id):
        raise ValueError('invalid execution task identity')
    root = (store.directory/'tasks'/task_id/'execution').resolve()
    if not root.is_relative_to(store.project):
        raise ValueError('execution directory escapes owned project')
    return root


def prepare_execution(store, task_id, *, definition_path, model_path, config, setup_history=(),
                      project_id, executable, cst_build='2022', scope='root', definition_revision=None):
    """Freeze intent once before launch, under the existing single-project owner."""
    if not isinstance(config,ExecutionConfig) or not is_cst_2022(cst_build) or scope != 'root':
        raise ValueError('unsupported capture context')
    definition_path,model_path = Path(definition_path).resolve(strict=True),Path(model_path).resolve()
    installation = verify_capture_installation(executable)
    if not model_path.is_relative_to(store.project) or not store.directory.resolve().is_relative_to(store.project):
        raise ValueError('execution artifacts must stay in the owned project')
    if definition_path.stat().st_size > 256*1024*1024:
        raise ValueError('definition budget exceeded')
    definition_hash = _digest(definition_path.read_bytes())
    if model_path.stat().st_size>256*1024*1024 or _digest(model_path.read_bytes())!=definition_hash:
        raise ValueError('fresh model must match frozen definition before setup')
    history = list(setup_history)
    if (len(history)>128 or any(not isinstance(line,str) or len(line)>4096 for line in history)
            or sum(len(line.encode('utf-8')) for line in history)>32*1024):
        raise ValueError('bounded owner setup history required')
    descriptor = dict(definition_sha256=definition_hash,config=asdict(config),setup_history=history)
    configuration_digest = _digest(json.dumps(descriptor,sort_keys=True,separators=(',',':')).encode())
    if definition_revision is not None and (not isinstance(definition_revision,str)
                                           or not re.fullmatch(r'[0-9a-f]{64}',definition_revision)):
        raise ValueError('owner definition revision must be a SHA256 identity')
    revision = definition_revision or configuration_digest
    # Binding validates project/build/scope identities even before a database exists.
    ExecutionBinding(project_id,task_id,revision,'0'*64,cst_build,scope)
    frozen = dict(schema_version=1,task_id=task_id,project_id=project_id,
                  run_id=json.loads((store.directory/'run.json').read_text(encoding='utf-8'))['run_id'],
                  definition_path=str(definition_path),model_path=str(model_path),
                  definition_revision=revision,configuration_digest=configuration_digest,
                  cst_build=cst_build,scope=scope,installation=installation,**descriptor)
    root = _task_root(store,task_id)
    with store.lock:
        root.mkdir(parents=True,exist_ok=True)
        path = root/'intent.json'
        if path.exists():
            previous = read_snapshot_record(path)
            if any(previous.get(key)!=value for key,value in frozen.items()):
                raise ValueError('execution intent conflicts; preserve original attempt')
            frozen = previous
        else:
            frozen.update(nonce=uuid4().hex,created_utc=store._utc())
            write_json_atomic(path,frozen)
        task = root.parent/'attempt.json'
        if not task.exists():
            store.event(task_id,'submitted',job='execution-config',definition_revision=revision)
        elif json.loads(task.read_text(encoding='utf-8')).get('event') != 'submitted':
            raise ValueError('capture cannot rebind a completed task')
    return frozen


def render_capture_runtime(intent, directory):
    """Helpers called in already loaded Model.run, before/after the one Start.

    This returns no Main/Start/OpenFile/Save/Quit. Caller owns the execution chain.
    """
    directory = Path(directory).resolve()
    # WWB Print uses the host code page. This first profile only binds ASCII paths;
    # do not reinterpret unknown ANSI bytes as trustworthy UTF-8 identities.
    directory.as_posix().encode('ascii')
    intent['model_path'].encode('ascii')
    nonce = intent['nonce']
    if not re.fullmatch(r'[0-9a-f]{32}',nonce):
        raise ValueError('invalid owner nonce')
    paths = {phase:quote_vb_string(directory/('native-'+phase+'.tsv')) for phase in ('pre','started','post')}
    queries = '\n'.join(f'    CaptureRow f, "{key}", CaptureValue("{key}")' for key in KEYS)
    pre_queries = '\n'.join(f'    value = CaptureValue("{key}")\n    CaptureRow f, "{key}", value\n    If value <> "MISSING" Then missing = False' for key in KEYS)
    return f'''
Function CaptureValue(key As String) As String
    Dim p As Object, value As String
    On Error GoTo Missing
    Set p = GetOwnProject
    value = p.GetDataBaseValue("objdata\\EigenmodeParameter\\" & key)
    CaptureValue = "OK:" & value
    Exit Function
Missing:
    If Err.Number = -2147418113 And Err.Description = "Data item not found in database." Then
        CaptureValue = "MISSING"
    Else
        CaptureValue = "ERROR:" & CStr(Err.Number) & ":" & Err.Description
    End If
End Function

Sub CaptureRow(f As Integer, key As String, value As String)
    If InStr(value, Chr(9)) > 0 Or InStr(value, Chr(10)) > 0 Or InStr(value, Chr(13)) > 0 Then Err.Raise vbObjectError + 2910, "capture", "invalid capture field"
    Print #f, key & Chr(9) & value
End Sub

Sub CaptureHeader(f As Integer, phase As String)
    CaptureRow f, "format", "CSTEXEC1"
    CaptureRow f, "nonce", "{nonce}"
    CaptureRow f, "phase", phase
    CaptureRow f, "project", GetProjectPath("Project")
    CaptureRow f, "build", GetApplicationVersion()
    CaptureRow f, "solver", GetSolverType()
    CaptureRow f, "length", Units.GetGeometryUnit()
    CaptureRow f, "frequency", Units.GetFrequencyUnit()
End Sub

Sub CaptureBeforeSolver()
    Dim f As Integer, value As String, nativeBuild As String, missing As Boolean
    If Dir("{paths['pre']}") <> "" Or Dir("{paths['started']}") <> "" Or Dir("{paths['post']}") <> "" Then Err.Raise vbObjectError + 2911, "capture", "attempt already has native observations"
    f = FreeFile
    Open "{paths['pre']}" For Output As #f
    CaptureHeader f, "pre"
    missing = True
{pre_queries}
    CaptureRow f, "end", "CSTEXEC1"
    Close #f
    nativeBuild = GetApplicationVersion()
    If Left(nativeBuild, 12) <> "Version 2022" Or GetSolverType() <> "HF Eigenmode" Then Err.Raise vbObjectError + 2913, "capture", "installation or solver identity mismatch"
    If Len(nativeBuild) > 12 Then
        If Mid(nativeBuild, 13, 1) <> "." And Mid(nativeBuild, 13, 1) <> " " Then Err.Raise vbObjectError + 2913, "capture", "installation major version mismatch"
    End If
    If Units.GetGeometryUnit() <> "mm" Or Units.GetFrequencyUnit() <> "MHz" Then Err.Raise vbObjectError + 2914, "capture", "unit identity mismatch"
    If LCase(GetProjectPath("Project")) <> LCase("{quote_vb_string(Path(intent['model_path']).with_suffix(''))}") Then Err.Raise vbObjectError + 2915, "capture", "project identity mismatch"
    If Not missing Then Err.Raise vbObjectError + 2912, "capture", "preexisting or unverified execution database; refuse Start"
    f = FreeFile
    Open "{paths['started']}" For Output As #f
    CaptureHeader f, "started"
    CaptureRow f, "end", "CSTEXEC1"
    Close #f
End Sub

Sub CaptureAfterSolver(solverReturn As Long)
    Dim f As Integer, count As Long
    count = EigenmodeSolver.GetNumberOfModesCalculated
    f = FreeFile
    Open "{paths['post']}" For Output As #f
    CaptureHeader f, "post"
    CaptureRow f, "solver_return", CStr(solverReturn)
    CaptureRow f, "calculated_modes", CStr(count)
{queries}
    CaptureRow f, "end", "CSTEXEC1"
    Close #f
End Sub
'''


def read_native_frame(path, intent, phase):
    path = Path(path)
    with path.open('rb') as stream:
        raw = stream.read(64*1024+1)
    if len(raw)>64*1024:
        raise ValueError('native frame budget exceeded')
    rows = {}
    for line in raw.decode('utf-8').splitlines():
        key,value = line.split('\t',1)
        if key in rows:
            raise ValueError('duplicate native field')
        rows[key] = value
    required = {'format','nonce','phase','project','build','solver','length','frequency','end'}
    required |= set(KEYS) if phase in ('pre','post') else set()
    required |= {'solver_return','calculated_modes'} if phase=='post' else set()
    if set(rows)!=required or not raw.endswith((b'end\tCSTEXEC1\r\n',b'end\tCSTEXEC1\n')):
        raise ValueError('incomplete native frame')
    expected = dict(format='CSTEXEC1',end='CSTEXEC1',nonce=intent['nonce'],phase=phase,
                    solver='HF Eigenmode',length='mm',frequency='MHz')
    if any(rows.get(key)!=value for key,value in expected.items()) or not is_cst_2022(rows['build']):
        raise ValueError('native identity or phase mismatch')
    if os.path.normcase(os.path.normpath(rows['project'])) != os.path.normcase(str(Path(intent['model_path']).with_suffix(''))):
        raise ValueError('native project scope mismatch')
    return rows,_digest(raw)


def finalize_execution(store, task_id, *, observations, closure):
    """Idempotent close-first reconciliation; does not launch/replay a solver."""
    root = _task_root(store,task_id)
    intent = read_snapshot_record(root/'intent.json')
    descriptor={key:intent[key] for key in ('definition_sha256','config','setup_history')}
    if ('configuration_digest' in intent and
            _digest(json.dumps(descriptor,sort_keys=True,separators=(',',':')).encode())!=intent['configuration_digest']):
        raise ValueError('frozen execution configuration changed')
    if json.loads((store.directory/'run.json').read_text(encoding='utf-8'))['run_id']!=intent['run_id']:
        raise ValueError('RunStore run identity changed')
    installation = verify_capture_installation(intent['installation']['executable'])
    if any(installation[key]!=intent['installation'][key] for key in ('executable','modeler_sha256','launcher_sha256')):
        raise ValueError('frozen installation identity changed')
    model = Path(intent['model_path'])
    if (closure.get('exit_confirmed') is not True or closure.get('active_pids')
            or not closure.get('owned') or str(closure.get('task_project')) != str(model)):
        raise ValueError('owned process exit not confirmed')
    rows,signature = {},{}
    for phase in ('pre','started','post'):
        frame,digest = read_native_frame(Path(observations)/('native-'+phase+'.tsv'),intent,phase)
        rows[phase] = frame; signature[phase] = digest
        if phase!='pre' and any(frame[key]!=rows['pre'][key] for key in ('project','build','solver','length','frequency')):
            raise ValueError('native installation changed between capture phases')
        if phase=='pre' and any(frame[key]!='MISSING' for key in KEYS):
            raise ValueError('preexisting database cannot be attributed to this attempt')
    if rows['post']['solver_return'] not in ('0','1') or not re.fullmatch(r'[0-9]+',rows['post']['calculated_modes']):
        raise ValueError('solver outcome missing')
    result_success = rows['post']['solver_return']=='1' and int(rows['post']['calculated_modes'])>0
    values = {}
    for key in KEYS:
        if not rows['post'][key].startswith('OK:'):
            raise ValueError('native post-attempt values missing; preserve observations')
        values[key] = rows['post'][key][3:]
    db = model.with_suffix('')/'Result/Model.db'
    if db.stat().st_size>64*1024*1024:
        raise ValueError('database budget exceeded')
    raw = db.read_bytes()
    if len(raw)>64*1024*1024:
        raise ValueError('database budget exceeded')
    database_hash = _digest(raw)
    captured = root/'native-Model.db'
    if captured.exists():
        if captured.stat().st_size>64*1024*1024 or _digest(captured.read_bytes())!=database_hash:
            raise ValueError('immutable database evidence conflict')
    else:
        staged = None
        try:
            with tempfile.NamedTemporaryFile(dir=root,prefix='capture-',suffix='.tmp',delete=False) as stream:
                staged = Path(stream.name)
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            with store.lock:
                if captured.exists():
                    raise ValueError('another owner published database evidence')
                os.replace(staged,captured)
        finally:
            if staged is not None and staged.exists():
                staged.unlink()
    # Preserve exact observed identity; only the byte-identified calibrated binary
    # maps its short UI label to the previously recorded full build identity.
    actual_build = (BUILD if installation['modeler_sha256']==MODELER_SHA256
                    and rows['post']['build']==NATIVE_VERSION else rows['post']['build'])
    binding = ExecutionBinding(intent['project_id'],task_id,intent['definition_revision'],database_hash,
                               actual_build,intent['scope'])
    finished = datetime.now(timezone.utc).isoformat()
    expected = ExecutionExpectation(binding,ExecutionConfig(**intent['config']),intent['created_utc'],finished,result_success,
                                    definition_sha256=intent['definition_sha256'])
    snapshot = dict(binding=asdict(binding),phase='post-attempt',observed_at=finished,values=values)
    snapshot_path = root/'snapshot.json'
    if snapshot_path.exists():
        previous_snapshot = read_snapshot_record(snapshot_path)
        if any(previous_snapshot.get(key)!=snapshot[key] for key in ('binding','phase','values')):
            raise ValueError('immutable snapshot evidence conflict')
        snapshot = previous_snapshot
    # Hash outside RunStore lock. Check both the owned source and immutable copy.
    report = verify_execution_artifact(expected,snapshot,database_path=db)
    if not report.database_verified:
        raise ValueError('source database changed during capture')
    report = verify_execution_artifact(expected,snapshot,database_path=captured)
    if not report.database_verified:
        raise ValueError('captured database changed during verification')
    receipt = dict(schema_version=1,task_id=task_id,nonce=intent['nonce'],binding=asdict(binding),
                   frame_hashes=signature,status=report.status,reasons=list(report.reasons),
                   result_success=result_success,database_verified=True,exit_confirmed=True,
                   solver_return=int(rows['post']['solver_return']),calculated_modes=int(rows['post']['calculated_modes']),
                   process_exit_code=closure.get('exit_code'),batch_exit_zero=closure.get('exit_code')==0,
                   snapshot_sha256=_digest(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()),
                   publish_ready=False)
    with store.lock:
        if read_snapshot_record(root/'intent.json')!=intent:
            raise ValueError('execution owner intent changed')
        path = root/'receipt.json'
        if path.exists():
            if read_snapshot_record(path)!=receipt:
                raise ValueError('execution receipt conflict; preserve evidence')
        else:
            write_json_atomic(snapshot_path,snapshot)
            write_json_atomic(path,receipt)
        store.artifacts(task_id,execution_receipt=path,execution_snapshot=root/'snapshot.json',execution_database=captured)
    return receipt

"""G03 saved/reopened definition verification; never invokes a solver."""
from decimal import Decimal
import hashlib
from pathlib import Path
import shutil
import subprocess
import psutil
from uuid import uuid4

from .acceptance_session import cst_processes, wait_probe
from .configuration import write_json_atomic, read_json
from .cst_process_env import cst_process_environment
from .execution_snapshot import is_cst_2022
from .native_execution_capture import verify_capture_installation
from .saved_project_source import read_saved_source
from .settings_projection import project_saved_settings, PARAMETERS
from .batch_desktop import BatchDesktopLease, macro_manifest, literal_content


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render_definition_probe(model, directory, nonce, projection=None):
    """Loaded 3D Model.run scope, using documented/calibrated read calls only."""
    def q(path): return literal_content(path)
    macro=f''''#Language "WWB-COM"
Option Explicit
Sub Main
    Dim f As Integer, message As String
    On Error GoTo Failed
    f = FreeFile
    Open "{q(directory / 'stage.txt')}" For Output As #f
    Print #f, "save"
    Close #f
    Save
    f = FreeFile
    Open "{q(directory / 'identity.tsv')}" For Output As #f
    Print #f, "nonce" & Chr(9) & "{nonce}"
    Print #f, "project" & Chr(9) & GetProjectPath("Project")
    Print #f, "build" & Chr(9) & GetApplicationVersion()
    Print #f, "solver" & Chr(9) & GetSolverType()
    Print #f, "length" & Chr(9) & Units.GetGeometryUnit()
    Print #f, "frequency" & Chr(9) & Units.GetFrequencyUnit()
    Print #f, "mesh" & Chr(9) & Mesh.GetMeshType()
    Print #f, "fmin" & Chr(9) & CStr(Solver.GetFmin())
    Print #f, "fmax" & Chr(9) & CStr(Solver.GetFmax())
    Print #f, "end" & Chr(9) & "G03V1"
    Close #f
    f = FreeFile
    Open "{q(directory / 'completed.txt')}" For Output As #f
    Print #f, "{nonce}"
    Close #f
    Exit Sub
Failed:
    message = CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    Close
    f = FreeFile
    Open "{q(directory / 'failed.txt')}" For Output As #f
    Print #f, message
    Close #f
End Sub
'''
    if projection is not None:
        from .definition_geometry import render_geometry_observer
        macro=macro.replace('    Save\n','    Save\n    CSTToolsObserveGeometry\n',1)
        macro+='\n'+render_geometry_observer(projection,directory,nonce)
    return macro


def render_managed_probe(model,directory,nonce,spec):
    from .definition_geometry import render_managed_geometry_observer
    macro=render_definition_probe(model,directory,nonce)
    if 'simulation' not in spec:
        # An empty/default MWS has no eigenmode identity or frequency promise.
        macro='\n'.join(line for line in macro.splitlines() if not any('Print #f, "'+key+'" & Chr(9)' in line
            for key in ('solver','mesh','fmin','fmax')))+'\n'
    macro=macro.replace('    Save\n','    Save\n    CSTToolsObserveGeometry\n',1)
    return macro+'\n'+render_managed_geometry_observer(spec,directory,nonce)


def run_definition_probe(executable, model, directory, macro):
    macro_manifest(directory,macro,purpose='G03 loaded-project readback',sources=[Path(__file__)])
    script = model.with_suffix('') / 'Model/3D/Model.run'
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(macro, encoding='ascii')
    (directory / 'probe.bas').write_text(macro, encoding='ascii')
    baseline = cst_processes()
    options = {}
    if __import__('os').name == 'nt':
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 7
        options['startupinfo'] = startup
    with (directory / 'cst.log').open('wb') as stream:
        lease=BatchDesktopLease(executable,model,directory)
        process = lease.start([str(executable), '-m', '-b', str(model)],stream,**options)
        identity=psutil.Process(process.pid)
        write_json_atomic(directory/'session-status.json',dict(exit_confirmed=False,
            launcher_pid=process.pid,owned=[dict(pid=process.pid,create_time=identity.create_time())],
            model_path=str(model),phase='launch'))
        try:
            session = wait_probe(process, directory, task_project=model,
                                 preexisting_processes=baseline, stage_timeout=180, exit_timeout=60,
                                 on_observation=lambda report:lease.observe(report['owned']),
                                 expected_launcher_identity=(process.pid,identity.create_time()))
        finally:lease.finish()
    session.update(exit_code=process.returncode)
    write_json_atomic(directory/'session-status.json',session)
    return dict(exit_code=process.returncode, exit_confirmed=session['exit_confirmed'])


def assert_definition_sessions_closed(catalog):
    """Do not dispatch another operation while an owned probe remains uncertain."""
    from .definition_sessions import definition_status_paths
    for status in definition_status_paths(catalog):
        report=read_json(status)
        if not isinstance(report,dict) or report.get('exit_confirmed') is not True:
            raise ValueError('G03 prior session exit unconfirmed; reconcile diagnostics before retry')


class NativeDefinitionVerifier:
    """Trusted backend. Staging stays read-only; explicit verify launches copies."""
    verify_on_stage = False
    supports_cancel = True

    def __init__(self, *, runner=None):
        self.runner = runner or run_definition_probe

    def _phases(self,candidate,root,executable,render,proof,cancel_check=None):
        """One shared saved/reopened owned-copy lifecycle for A1 and GEO."""
        previous=candidate
        for phase in ('saved','reopened'):
            if cancel_check:cancel_check()
            directory=root/phase;directory.mkdir();model=directory/'definition.cst'
            shutil.copyfile(previous,model);nonce=uuid4().hex
            write_json_atomic(directory/'session-status.json',dict(exit_confirmed=False,phase=phase))
            result=self.runner(executable,model,directory,render(model,directory,nonce))
            proof['sessions'].append(dict(phase=phase,**result))
            status=read_json(directory/'session-status.json')
            status.update(exit_confirmed=result.get('exit_confirmed') is True,exit_code=result.get('exit_code'))
            write_json_atomic(directory/'session-status.json',status)
            if (result.get('exit_confirmed') is not True or type(result.get('exit_code')) is not int or result['exit_code']!=0
                    or (directory/'failed.txt').exists() or not (directory/'completed.txt').exists()
                    or (directory/'completed.txt').read_text().strip()!=nonce):
                raise ValueError('G03 requires completion and owned standard batch exit')
            yield phase,directory,model,nonce,result
            previous=model

    def verify_geometry(self,candidate,spec,executable,*,cancel_check=None):
        return self._verify_managed(candidate,spec,executable,target='geometry',cancel_check=cancel_check)

    def _verify_managed(self,candidate,spec,executable,*,target,cancel_check=None):
        from .managed_history import verify_saved_program
        from .definition_geometry import verify_managed_geometry_observation
        if target=='simulation':
            from .definition_editing import check_geometry_simulation
            check_geometry_simulation(spec)
        candidate=Path(candidate).resolve(strict=True);str(candidate).encode('ascii')
        source=read_saved_source(candidate,scope='root');expected=verify_saved_program(source,spec)
        installation=verify_capture_installation(executable)
        assert_definition_sessions_closed(candidate.parent)
        root=candidate.parent/('verification-managed-'+uuid4().hex);root.mkdir()
        proof=dict(schema_version=1,status='failed',scope='root',source_sha256=source.sha256,
            validation_target=target,gates=[],diagnostics=str(root),installation=installation,sessions=[],observations=[])
        write_json_atomic(root/'verification.json',proof)
        try:
            render=lambda model,directory,nonce:render_managed_probe(model,directory,nonce,spec)
            for phase,directory,model,nonce,result in self._phases(candidate,root,executable,render,proof,cancel_check):
                rows={}
                for line in (directory/'identity.tsv').read_text(encoding='ascii').splitlines():
                    key,value=line.split('\t')
                    if key in rows:raise ValueError('duplicate GEO identity')
                    rows[key]=value
                keys={'nonce','project','build','length','frequency','end'}
                if 'simulation' in spec:keys|={'solver','mesh','fmin','fmax'}
                if (set(rows)!=keys or rows['nonce']!=nonce or rows['end']!='G03V1' or not is_cst_2022(rows['build'])
                        or rows['length']!='mm' or rows['frequency']!='MHz' or Path(rows['project']).resolve()!=model.with_suffix('').resolve()):
                    raise ValueError('GEO native project/scope/unit identity differs')
                if 'simulation' in spec:
                    if rows['solver']!='HF Eigenmode' or rows['frequency']!='MHz' or rows['mesh']!='Tetrahedral':
                        raise ValueError('GEO native solver identity differs')
                    for key in ('fmin','fmax'):
                        value=Decimal(rows[key]);wanted=Decimal(str(spec['simulation']['frequency_range_mhz']['min' if key=='fmin' else 'max']))
                        if not value.is_finite() or abs(value-wanted)>max(abs(wanted)*Decimal('0.000005'),Decimal('0.000005')):
                            raise ValueError('GEO native frequency readback differs')
                saved=read_saved_source(model,scope='root');observed=verify_saved_program(saved,spec)
                if dict(observed.fields)!=dict(expected.fields) or dict(observed.exact_values)!=dict(expected.exact_values):
                    raise ValueError('GEO saved/reopened projection differs')
                geometry=verify_managed_geometry_observation(directory/'geometry.tsv',spec,model,nonce)
                proof['observations'].append(dict(phase=phase,sha256=saved.sha256,native=rows,geometry=geometry))
            if digest(candidate)!=source.sha256 or verify_capture_installation(executable)!=installation:
                raise ValueError('GEO source/installation changed during verification')
            proof.update(status='verified',gates=['saved-reopened','identity','settings','standard-close'])
            return proof
        except Exception as error:
            proof['error']=type(error).__name__+': '+str(error);raise
        finally:write_json_atomic(root/'verification.json',proof)

    def __call__(self, candidate, projection, executable,*,spec=None,cancel_check=None):
        if spec is not None:return self._verify_managed(candidate,spec,executable,target='simulation',cancel_check=cancel_check)
        candidate = Path(candidate).resolve(strict=True)
        str(candidate).encode('ascii')
        source = read_saved_source(candidate, scope='root')
        expected = project_saved_settings(source)
        if (expected.status != 'resolved' or expected.missing_fields
                or dict(expected.fields) != dict(projection.fields)):
            raise ValueError('G03 requires a complete unchanged root definition')
        installation = verify_capture_installation(executable)
        assert_definition_sessions_closed(candidate.parent)
        root = candidate.parent / ('verification-' + uuid4().hex)
        root.mkdir()
        proof = dict(schema_version=1, status='failed', scope='root',
                     source_sha256=source.sha256, gates=[], diagnostics=str(root),
                     installation=installation, sessions=[])
        write_json_atomic(root/'verification.json', proof)
        try:
            render=lambda model,directory,nonce:render_definition_probe(model,directory,nonce,expected)
            for phase,directory,model,nonce,result in self._phases(candidate,root,executable,render,proof,cancel_check):
                rows = {}
                for line in (directory/'identity.tsv').read_text(encoding='ascii').splitlines():
                    key, value = line.split('\t')
                    if key in rows: raise ValueError('duplicate native identity field')
                    rows[key] = value
                if (set(rows) != {'nonce','project','build','solver','length','frequency','mesh','fmin','fmax','end'}
                        or rows['nonce'] != nonce or rows['end'] != 'G03V1'
                        or Path(rows['project']).resolve() != model.with_suffix('').resolve()
                        or not is_cst_2022(rows['build']) or rows['solver'] != 'HF Eigenmode'
                        or rows['length'] != 'mm' or rows['frequency'] != 'MHz'
                        or rows['mesh'] != 'Tetrahedral'):
                    raise ValueError('G03 native identity mismatch')
                for key in ('fmin','fmax'):
                    actual = Decimal(rows[key])
                    wanted = Decimal(expected.exact_values['solver.frequency_range.' + ('min_mhz' if key=='fmin' else 'max_mhz')])
                    # calibrated native getters expose six significant digits
                    if not actual.is_finite() or abs(actual-wanted) > max(abs(wanted)*Decimal('0.000005'), Decimal('0.000005')):
                        raise ValueError('G03 native frequency mismatch')
                saved = read_saved_source(model, scope='root')
                observed = project_saved_settings(saved)
                if (observed.status != 'resolved' or observed.missing_fields
                        or dict(observed.fields) != dict(expected.fields)
                        or dict(observed.exact_values) != dict(expected.exact_values)
                        or saved.json(PARAMETERS) != source.json(PARAMETERS)):
                    raise ValueError('G03 saved settings or parameter expressions changed')
                from .definition_geometry import verify_geometry_observation
                geometry=verify_geometry_observation(directory/'geometry.tsv',expected,model,nonce)
                proof.setdefault('observations', []).append(dict(phase=phase, sha256=saved.sha256, native=rows,geometry=geometry))
                previous = model
            if digest(candidate) != source.sha256 or verify_capture_installation(executable) != installation:
                raise ValueError('G03 definition or installation changed during verification')
            proof.update(status='verified', gates=['saved-reopened','identity','settings','standard-close'])
            return proof
        except Exception as error:
            proof['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            write_json_atomic(root/'verification.json', proof)

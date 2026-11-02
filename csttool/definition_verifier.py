"""G03 saved/reopened definition verification; never invokes a solver."""
from decimal import Decimal
import hashlib
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from .acceptance_session import cst_processes, wait_probe
from .configuration import write_json_atomic, read_json
from .cst_process_env import cst_process_environment
from .execution_snapshot import is_cst_2022
from .native_execution_capture import verify_capture_installation
from .saved_project_source import read_saved_source
from .settings_projection import project_saved_settings, PARAMETERS
from .vb_codec import quote_vb_string


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render_definition_probe(model, directory, nonce):
    """Loaded 3D Model.run scope, using documented/calibrated read calls only."""
    def q(path): return quote_vb_string(path)
    return f'''#Language "WWB-COM"
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


def run_definition_probe(executable, model, directory, macro):
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
        process = subprocess.Popen([str(executable), '-m', '-b', str(model)],
            stdout=stream, stderr=subprocess.STDOUT, cwd=directory,
            env=cst_process_environment(), **options)
        session = wait_probe(process, directory, task_project=model,
                             preexisting_processes=baseline, stage_timeout=180, exit_timeout=60)
    return dict(exit_code=process.returncode, exit_confirmed=session['exit_confirmed'])


def assert_definition_sessions_closed(catalog):
    """Do not dispatch another operation while an owned probe remains uncertain."""
    for status in Path(catalog).glob('*/*/verification-*/*/session-status.json'):
        if read_json(status).get('exit_confirmed') is not True:
            raise ValueError('G03 prior session exit unconfirmed; reconcile diagnostics before retry')


class NativeDefinitionVerifier:
    """Trusted backend. Staging stays read-only; explicit verify launches copies."""
    verify_on_stage = False

    def __init__(self, *, runner=None):
        self.runner = runner or run_definition_probe

    def __call__(self, candidate, projection, executable):
        candidate = Path(candidate).resolve(strict=True)
        str(candidate).encode('ascii')
        source = read_saved_source(candidate, scope='root')
        expected = project_saved_settings(source)
        if (expected.status != 'resolved' or expected.missing_fields
                or dict(expected.fields) != dict(projection.fields)):
            raise ValueError('G03 requires a complete unchanged root definition')
        installation = verify_capture_installation(executable)
        assert_definition_sessions_closed(candidate.parent.parent.parent)
        root = candidate.parent / ('verification-' + uuid4().hex)
        root.mkdir()
        proof = dict(schema_version=1, status='failed', scope='root',
                     source_sha256=source.sha256, gates=[], diagnostics=str(root),
                     installation=installation, sessions=[])
        write_json_atomic(root/'verification.json', proof)
        try:
            previous = candidate
            for phase in ('saved', 'reopened'):
                directory = root/phase
                directory.mkdir()
                model = directory/'definition.cst'
                shutil.copyfile(previous, model)  # intentionally no external results
                nonce = uuid4().hex
                write_json_atomic(directory/'session-status.json', dict(exit_confirmed=False, phase=phase))
                result = self.runner(executable, model, directory,
                                     render_definition_probe(model, directory, nonce))
                proof['sessions'].append(dict(phase=phase, **result))
                status_path = directory/'session-status.json'
                status = read_json(status_path)
                status.update(exit_confirmed=result.get('exit_confirmed') is True)
                write_json_atomic(status_path, status)
                if (result.get('exit_confirmed') is not True or result.get('exit_code') != 0
                        or (directory/'failed.txt').exists()
                        or (directory/'completed.txt').read_text().strip() != nonce):
                    raise ValueError('G03 requires completion and owned standard batch exit')
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
                proof.setdefault('observations', []).append(dict(phase=phase, sha256=saved.sha256, native=rows))
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

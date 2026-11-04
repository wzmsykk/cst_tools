"""Typed definition drafts and copy-only A1 publication through the shared G03.

Drafts describe intentions, not live CST settings. Only save_project executes
bounded calibrated history; GEO-1 drafts cannot dispatch native code. No caller
VBA, paths, or solver calls are accepted.
"""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from jsonschema import Draft202012Validator
from .configuration import read_json, write_json_atomic
from .project_run_lock import ProjectRunLock
from .saved_project_source import read_saved_source
from .settings_projection import _Arithmetic, project_history, project_saved_settings
from .winwrap_emitter import (String, Number, Boolean, HistoryCall, With, Symbols,
    Variable, Element, SubCall, resize_arrays, GeneratedCodeError, validate_parameter_names, assign_string,
    arithmetic as emit_arithmetic, render_history as emit_history, check_lines)
from .winwrap_checks import (check_history, check_module, definition_map, map_native_error,
                             require_calibration,require_geometry_calibration)
from .geometry_contract import PROFILE as GEOMETRY_PROFILE, apply_changes, project_geometry


SCHEMA = json.loads((Path(__file__).resolve().parents[1]/'data/first_stage_contract.schema.json').read_text(encoding='utf-8'))
EDIT_OPERATIONS = ('apply_model_changes', 'configure_simulation', 'save_project', 'close_project')


def fail(code, reason):
    from .application_service import ServiceError
    raise ServiceError(code, reason)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_edit(payload):
    if not isinstance(payload, dict) or payload.get('kind') != 'definition' or payload.get('operation') not in EDIT_OPERATIONS:
        fail('INVALID_ARGUMENT', 'unknown definition operation')
    args = {k: v for k, v in payload.items() if k not in ('kind', 'operation')}
    schema = {'$defs': SCHEMA['$defs'], '$ref': '#/$defs/'+payload['operation']}
    if next(Draft202012Validator(schema).iter_errors(args), None):
        fail('INVALID_ARGUMENT', 'definition arguments do not match the definition schema')
    # Reject bool-as-number and NaN/Infinity, including nested values.
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError):
        fail('INVALID_ARGUMENT', 'non-finite or non-JSON arguments')


def arithmetic(spec):
    return _Arithmetic([dict(name=k, expr=v['expression']) for k, v in spec['parameters'].items()])


def check_spec(spec, *, complete=False):
    """Cross-field checks use the existing bounded expression evaluator."""
    if 'geometry' in spec:
        project_geometry(spec)
        if complete:
            check_geometry_simulation(spec)
        return
    params = spec['parameters']
    try:
        validate_parameter_names(params)
    except GeneratedCodeError as error:
        fail(error.code, error.reason)
    if len(params) > 128 or len({k.lower() for k in params}) != len(params):
        fail('INVALID_ARGUMENT', 'A1 supports at most 128 case-insensitively unique parameters')
    for name, row in params.items():
        if (len(row['expression']) > 4096 or any(c in row['expression'] for c in '\r\n\x00"')
                or any(ord(c)<32 for c in row['description'])):
            fail('UNSUPPORTED_CAPABILITY', 'bounded single-line arithmetic expressions are required')
        if (any(ord(c)>0xFFFF or 0xD800<=ord(c)<=0xDFFF for c in row['description'])
                or row['description']!=row['description'].strip()):
            fail('UNSUPPORTED_CAPABILITY', 'CST2022 description requires BMP text without edge whitespace; no silent replacement or trimming')
        if name.lower() in ('pi', 'true', 'false', 'e'):
            fail('INVALID_ARGUMENT', 'reserved parameter name')
    numbers = arithmetic(spec)
    for name in params:
        numbers.parameter(name)
    cylinder = spec.get('cylinder')
    if cylinder:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,99}', cylinder['object_id']):
            fail('UNSUPPORTED_CAPABILITY', 'A1 object names start with a letter')
        if cylinder['component_id'] not in spec['components']:
            fail('INVALID_ARGUMENT', 'cylinder component must be declared')
        expressions = cylinder['center'] + cylinder['axial_range'] + [cylinder['outer_radius']]
        for expression in expressions:
            if len(expression) > 4096 or re.search(r'[^A-Za-z0-9_ .+\-*/^()]', expression):
                fail('UNSUPPORTED_CAPABILITY', 'geometry accepts bounded arithmetic only')
            try: names={n.id for n in ast.walk(ast.parse(expression.replace('^','**'),mode='eval')) if isinstance(n,ast.Name)}
            except (SyntaxError,ValueError,RecursionError): fail('INVALID_ARGUMENT','invalid geometry expression')
            for name in names:
                matches = [row for key, row in params.items() if key.lower() == name.lower()]
                if not matches or matches[0]['quantity'] != 'length':
                    fail('INVALID_ARGUMENT', 'geometry parameter must be a declared length')
        center = [numbers.expression(e) for e in cylinder['center']]
        if any(center):
            fail('UNSUPPORTED_CAPABILITY', 'A1 currently requires zero cylinder center')
        if numbers.expression(cylinder['outer_radius']) <= 0 or numbers.expression(cylinder['axial_range'][0]) >= numbers.expression(cylinder['axial_range'][1]):
            fail('INVALID_ARGUMENT', 'invalid cylinder dimensions')
    simulation = spec.get('simulation')
    if simulation:
        bounds = simulation['frequency_range_mhz']
        if not 0 < bounds['min'] < bounds['max'] or simulation['frequency_lower_target_mhz'] != bounds['min']:
            fail('INVALID_ARGUMENT', 'frequency lower target must equal the positive range minimum')
        pps = spec['postprocess']
        if len({p['metric_id'] for p in pps}) != 2 or {p['method_id'] for p in pps} != {'Frequency','R_over_Q'}:
            fail('INVALID_ARGUMENT', 'exactly one Frequency and one R_over_Q with distinct IDs are required')
        rq = next(p for p in pps if p['method_id'] == 'R_over_Q')
        if not cylinder or rq['settings']['integration_line']['axis'] != cylinder['axis']:
            fail('INVALID_ARGUMENT', 'R/Q axis must match the cylinder axis')
    if complete and not all(spec.get(key) for key in ('cylinder','background','boundaries','simulation','postprocess')):
        fail('SETTING_UNVERIFIED', 'complete A1 model and simulation are required before publication')


def check_geometry_simulation(spec):
    """First GEO simulation combination: PEC enclosure, vacuum, Tet/Default/1."""
    if not all(key in spec for key in ('background','boundaries','simulation','postprocess')):
        fail('SETTING_UNVERIFIED','GEO simulation requires explicit background, boundaries, simulation and postprocess')
    for key,definition in (('simulation','Simulation'),('postprocess','PPS')):
        if next(Draft202012Validator({'$defs':SCHEMA['$defs'],'$ref':'#/$defs/'+definition}).iter_errors(spec[key]),None):
            fail('INVALID_ARGUMENT','unsupported GEO '+key)
    projected=project_geometry(spec)
    live=[row for row in projected['objects'].values() if row['state']=='live']
    if not live or any(row['material_id']!='Vacuum' for row in live):
        fail('UNSUPPORTED_CAPABILITY','GEO eigenmode v1 requires live vacuum solids in PEC background')
    sim=spec['simulation'];bounds=sim['frequency_range_mhz']
    if not 0<bounds['min']<bounds['max'] or sim['frequency_lower_target_mhz']!=bounds['min']:
        fail('INVALID_ARGUMENT','frequency target must equal positive window minimum')
    if len({p['metric_id'] for p in spec['postprocess']})!=2 or {p['method_id'] for p in spec['postprocess']}!={'Frequency','R_over_Q'}:
        fail('INVALID_ARGUMENT','GEO v1 requires distinct Frequency and R_over_Q metrics')


def initial_spec(record):
    return deepcopy(record.get('spec', dict(parameters={}, components=[])))


def changed_spec(record, payload):
    spec = initial_spec(record)
    if payload['operation'] == 'apply_model_changes' and payload.get('geometry_profile') == GEOMETRY_PROFILE:
        if 'geometry' not in spec and any(k in spec for k in ('cylinder', 'background', 'boundaries', 'simulation', 'postprocess')):
            fail('DOCUMENT_CONFLICT', 'cannot implicitly convert an A1 definition into geometry-v1')
        return apply_changes(spec, payload)
    if 'geometry' in spec:
        if payload['operation']=='configure_simulation':
            if 'simulation' not in payload or 'postprocess' not in payload:fail('INVALID_ARGUMENT','missing simulation/postprocess')
            spec.update(simulation=deepcopy(payload['simulation']),postprocess=deepcopy(payload['postprocess']))
            check_geometry_simulation(spec)
        elif payload['operation']=='apply_model_changes':
            fail('INVALID_ARGUMENT','geometry-v1 changes require the explicit profile')
        project_geometry(spec)
        return spec
    if payload['operation'] == 'apply_model_changes':
        for change in payload['changes']:
            op = change['op']
            if op == 'set_parameters':
                spec['parameters'].update(deepcopy(change['values']))
            elif op == 'ensure_component':
                if change['component_id'] not in spec['components']:
                    spec['components'].append(change['component_id'])
            elif op == 'create_cylinder':
                if spec.get('cylinder'): fail('DOCUMENT_CONFLICT', 'A1 permits one cylinder; update its parameters')
                spec['cylinder'] = deepcopy(change)
            elif op == 'set_background': spec['background'] = deepcopy(change)
            elif op == 'set_boundaries': spec['boundaries'] = deepcopy(change)
        # Whole change list is validated together, allowing forward parameter references.
    elif payload['operation'] == 'configure_simulation':
        spec.update(simulation=deepcopy(payload['simulation']), postprocess=deepcopy(payload['postprocess']))
    check_spec(spec, complete=payload['operation'] == 'save_project')
    return spec


def render_history(spec):
    """Only generated allowlisted commands; parameter table is deliberately separate."""
    if 'geometry' in spec:
        fail('UNSUPPORTED_CAPABILITY', 'geometry-v1 native history requires GEO-2 calibration')
    check_spec(spec, complete=True)
    c = spec['cylinder']; sim = spec['simulation']
    def call(obj, method, *args): return HistoryCall(obj, method, args)
    def block(obj, rows): return With(obj, tuple(call(obj, method, *args) for method, args in rows))
    def numeric(value): return emit_arithmetic(value, spec['parameters'])
    zero = Number('0')
    nodes = [block('Units', [('Geometry', (String('mm'),)), ('Frequency', (String('MHz'),))]),
             call('project', 'ChangeSolverType', String('HF Eigenmode')),
             block('Background', [('Type', (String('pec'),))] +
                   [(face+'Space', (zero,)) for face in ('Xmin','Xmax','Ymin','Ymax','Zmin','Zmax')]),
             block('Boundary', [(face, (String('electric'),)) for face in ('Xmin','Xmax','Ymin','Ymax','Zmin','Zmax')] +
                   [(a+'symmetry', (String('none'),)) for a in 'XYZ']),
             call('WCS', 'ActivateWCS', String('global'))]
    nodes += [call('Component', 'New', String(name)) for name in spec['components']]
    nodes += [block('Cylinder', [
        ('Reset', ()), ('Name', (String(c['object_id']),)), ('Component', (String(c['component_id']),)),
        ('Material', (String('Vacuum'),)), ('Axis', (String(c['axis']),)),
        ('OuterRadius', (numeric(c['outer_radius']),)), ('InnerRadius', (zero,)),
        ('Xcenter', (zero,)), ('Ycenter', (zero,)), ('Zcenter', (zero,)),
        (c['axis'].upper()+'range', tuple(numeric(e) for e in c['axial_range'])),
        ('Segments', (zero,)), ('Create', ())]),
        call('EigenmodeSolver', 'Reset'),
        call('Solver', 'FrequencyRange', String(str(sim['frequency_range_mhz']['min'])), String(str(sim['frequency_range_mhz']['max']))),
        call('Mesh', 'MeshType', String('Tetrahedral')),
        block('MeshSettings', [('SetMeshType', (String('Tet'),)), ('Set', (String('Version'), Number('1'))),
            ('Set', (String('StepsPerWaveNear'), String(str(sim['mesh']['cells_per_wavelength'])))),
            ('Set', (String('StepsPerWaveFar'), String(str(sim['mesh']['cells_per_wavelength'])))),
            ('Set', (String('CellsPerWavelengthPolicy'), String('cellsperwavelength')))]),
        block('EigenmodeSolver', [('SetMethodType', (String('Default'), String('Tet'))),
            ('SetMeshType', (String('Tetrahedral Mesh'),)),
            ('SetFrequencyTarget', (Boolean(True), String(str(sim['frequency_lower_target_mhz'])))),
            ('SetNumberOfModes', (Number('1'),)), ('SetMeshAdaptationTet', (Boolean(False),)),
            ('SetConsiderLossesInPostprocessingOnly', (Boolean(True),))])]
    history = emit_history(nodes)
    check_history(history)
    projection = project_history(history, [dict(name=k, expr=v['expression']) for k,v in spec['parameters'].items()], scope='root', available_scopes=('root',))
    if projection.status != 'resolved' or projection.missing_fields:
        fail('SETTING_UNVERIFIED', 'generated history failed A1 projection: '+str(projection.reasons))
    return history, projection


def render_edit_macro(directory, spec, nonce):
    """One owned A1/GEO definition template; rendering never dispatches CST."""
    geometry = 'geometry' in spec
    from .history_program import partition
    program = partition(spec)
    q = lambda value: String(str(value)).render()
    params = spec['parameters']
    symbols = Symbols(params)
    for name in ('Main', 'ReportStage', 'CSTToolsBindNewProject', 'CSTToolsProcessId', 'CSTToolsBindingSleep'):
        symbols.reserve(name)
    declarations = ', '.join(symbols.declare(name, kind, array=array) for name, kind, array in (
        ('names', 'String', True), ('expressions', 'String', True), ('history', 'String', False),
        ('f', 'Integer', False), ('message', 'String', False),
        ('CSTToolsCheckCode', 'String', False), ('CSTToolsCheckError', 'ErrObject', False),
        ('CSTToolsStage', 'String', False), ('CSTToolsBlockIndex', 'Integer', False),
        ('CSTToolsLastApplied', 'Integer', False), ('CSTToolsCaption', 'String', False)))
    def assign(target, value): return assign_string(target, value)
    def stage(value): return ['    CSTToolsStage = '+q(value), '    ReportStage CSTToolsStage',
        '    If Dir('+q(directory/'cancel.request')+') <> "" Then Err.Raise vbObjectError + 2996, "definition", "stop requested"']
    setup = ['    CSTToolsBlockIndex = -1', '    CSTToolsLastApplied = -1', '    CSTToolsCaption = ""',
             '    CSTToolsStage = "ownership"']+stage('parameters')
    if params:
        setup += ['    ' + resize_arrays((Variable('names'), Variable('expressions')), len(params))]
        for index,(name,row) in enumerate(params.items()):
            setup += assign(Element('names', index),name)+assign(Element('expressions', index),row['expression'])
        setup += ['    StoreParameters(names, expressions)']
    setup += stage('parameter-descriptions')
    for name,row in params.items():
        setup += assign(Variable('message'),row['description'])+['    ' + SubCall('SetParameterDescription', (String(name), Variable('message'))).render()]
    source = 'GEO' if geometry else 'A1'
    for index,block in enumerate(program):
        setup += ['    CSTToolsBlockIndex = '+str(index),'    CSTToolsCaption = '+q(block['caption'])]
        setup += assign(Variable('history'),block['history'])+stage('history-check')
        setup += [
            '    CSTToolsCheckCode = "\'#Language ""WWB-COM""" & vbCrLf & "Option Explicit" & vbCrLf & "Sub Main" & vbCrLf & history & vbCrLf & "End Sub"',
            '    Set CSTToolsCheckError = MacroCheckThis(CSTToolsCheckCode)',
            '    If Not CSTToolsCheckError Is Nothing Then',
            '        f = FreeFile',
            '        Open '+q(directory/'history-syntax-error.txt')+' For Output As #f',
            '        Print #f, CStr(CSTToolsCheckError.Number)',
            '        Print #f, CSTToolsCheckError.Description',
            '        Print #f, CSTToolsCheckError.Source',
            '        Close #f',
            '        Err.Raise vbObjectError + 2995, '+q(source)+', "GENERATED_CODE_INVALID: history syntax rejected"',
            '    End If']
        setup += stage('history-apply')+[
            '    If Not AddToHistory('+q(block['caption'])+', history) Then Err.Raise vbObjectError + 2992, '+q(source)+', "history rejected"',
            '    CSTToolsLastApplied = '+str(index)]
    setup += stage('rebuild')+['    If Not Rebuild Then Err.Raise vbObjectError + 2993, '+q(source)+', "rebuild failed"']
    setup += stage('save')+['    SaveAs '+q(directory/'definition.cst')+', False',
        '    f = FreeFile','    Open '+q(directory/'completed.txt')+' For Output As #f',
        '    Print #f, '+q(nonce),'    Close #f']
    setup += stage('batch-return')+['    Exit Sub']
    macro = f''''#Language "WWB-COM"
Option Explicit
Sub Main
    Dim {declarations}
    On Error GoTo Failed
'''+ '\n'.join(setup)+f'''
Failed:
    message = CStr(Err.Number) & " " & Err.Description & " source=" & Err.Source
    On Error Resume Next
    Close
    f = FreeFile
    Open {q(directory/'failure-context.tsv')} For Output As #f
    Print #f, "1"
    Print #f, {q(nonce)}
    Print #f, CSTToolsStage
    Print #f, CStr(CSTToolsBlockIndex)
    Print #f, CStr(CSTToolsLastApplied)
    Print #f, CSTToolsCaption
    Close #f
    f = FreeFile
    Open {q(directory/'failed.txt')} For Output As #f
    Print #f, message
    Close #f
End Sub
Private Sub ReportStage(ByVal value As String)
    Dim f As Integer
    f = FreeFile
    Open {q(directory/'stage.txt')} For Output As #f
    Print #f, value
    Close #f
End Sub
'''
    check_lines(macro.splitlines())
    if geometry:
        from .settings_projection import GEOMETRY_PROFILE
        check_module(macro,params,profile=GEOMETRY_PROFILE)
    else: check_module(macro, params)
    return macro


def prepare_candidate_artifacts(directory,spec,nonce):
    """Write a fresh, non-dispatched artifact bundle; never an execution intent."""
    from .settings_projection import PROFILE,GEOMETRY_PROFILE
    directory=Path(directory)
    geometry='geometry' in spec
    macro=render_edit_macro(directory,spec,nonce)
    from .history_program import partition,validate
    from .winwrap_checks import execution_definition_map
    program=partition(spec)
    history='\n'.join(b['history'] for b in program)
    mapping=execution_definition_map(spec,program,macro)
    macro.encode('ascii')
    directory.mkdir(parents=True,exist_ok=False)
    if not geometry:(directory/'history.vb').write_text(history,encoding='ascii')
    write_json_atomic(directory/'history-program.json',program)
    write_json_atomic(directory/'block-contracts.json',validate(program,spec))
    (directory/'edit.bas').write_text(macro,encoding='ascii',newline='\n')
    write_json_atomic(directory/'source-map.json',mapping)
    write_json_atomic(directory/'spec.json',spec)
    descriptor=dict(profile=GEOMETRY_PROFILE if geometry else PROFILE,nonce=nonce,
        spec_sha256=fingerprint(spec),macro_sha256=hashlib.sha256(macro.encode('ascii')).hexdigest(),
        program_sha256=fingerprint(program),native_dispatched=False)
    write_json_atomic(directory/'generation.json',descriptor)
    return dict(directory=directory,model_path=directory/'definition.cst',macro=macro,mapping=mapping,
                program=program,descriptor=descriptor)


def read_failure_context(directory,nonce,program):
    path=Path(directory)/'failure-context.tsv'
    if not path.exists():return None
    if path.stat().st_size>8192:raise ValueError('failure context budget exceeded')
    rows=path.read_text(encoding='ascii').splitlines()
    if len(rows)!=6 or rows[0]!='1' or rows[1]!=nonce:raise ValueError('failure context identity differs')
    phase,index,last,caption=rows[2],int(rows[3]),int(rows[4]),rows[5]
    if phase in ('ownership','parameters','parameter-descriptions'):
        valid=index==last==-1 and caption==''
    elif phase in ('history-check','history-apply'):
        valid=0<=index<len(program) and last==index-1 and caption==program[index]['caption']
    elif phase in ('rebuild','save','batch-return'):
        valid=index==last==len(program)-1 and caption==program[index]['caption']
    else:valid=False
    if not valid:raise ValueError('failure context phase/block facts differ')
    return dict(phase=phase,block_index=index,last_applied=last,caption=caption)


def validate_candidate_completion(bundle,spec,result):
    """Check independent completion/closure and B1 parameter persistence facts.

    Does not verify GEO saved history/geometry and cannot publish a definition.
    """
    directory=bundle['directory'];nonce=bundle['descriptor']['nonce'];context=None;context_error=None
    try:context=read_failure_context(directory,nonce,bundle['program'])
    except (ValueError,OSError) as error:context_error=str(error)
    result=result if isinstance(result,dict) else {}
    syntax=directory/'history-syntax-error.txt'
    if syntax.exists():
        with syntax.open(errors='replace') as stream:raw=stream.read(16384)
        index=context['block_index'] if context and context['phase']=='history-check' and not context_error else None
        diagnostic=map_native_error(raw,bundle['mapping'],block_index=index)
        diagnostic.update(context=context,context_error=context_error,exit_confirmed=result.get('exit_confirmed') is True)
        write_json_atomic(directory/'native-diagnostic.json',diagnostic)
        fail('GENERATED_CODE_INVALID','history syntax rejected; diagnostics='+str(directory))
    failed=directory/'failed.txt';completed=directory/'completed.txt'
    if (context_error or context is not None or result.get('exit_confirmed') is not True
            or type(result.get('exit_code')) is not int or result['exit_code']!=0 or failed.exists()
            or not completed.exists() or completed.stat().st_size>1024 or completed.read_text().strip()!=nonce):
        write_json_atomic(directory/'candidate-diagnostic.json',dict(context=context,context_error=context_error,
            exit_confirmed=result.get('exit_confirmed') is True,exit_code=result.get('exit_code'),
            failed=failed.exists(),completed=completed.exists()))
        failure='no failure receipt'
        if failed.exists():
            with failed.open(errors='replace') as stream:failure=stream.read(4096)
        fail('SETTING_UNVERIFIED','definition edit/standard exit not confirmed; phase='+str(context)+'; native='+failure+'; diagnostics='+str(directory))
    source=read_saved_source(bundle['model_path'],scope='root')
    parameters=source.json('Model/Parameters.json')
    rows=parameters.get('parameters') if isinstance(parameters,dict) else None
    if (not isinstance(rows,list) or len(rows)!=len(spec['parameters']) or any(not isinstance(r,dict) for r in rows)
            or any(not isinstance(r.get('name'),str) for r in rows)
            or len({r['name'] for r in rows})!=len(rows)
            or {r['name']:(r.get('expr'),r.get('descr')) for r in rows}!={k:(v['expression'],v['description']) for k,v in spec['parameters'].items()}):
        fail('SETTING_UNVERIFIED','saved parameter expressions/descriptions differ from the draft; diagnostics='+str(directory))
    return source


def build_candidate(service, parent, spec, operation_id, cancel_check, progress,*,target='simulation'):
    """Owned fresh candidate; GEO additionally requires its independent gate."""
    if 'geometry' in spec:require_geometry_calibration(target)
    from .native_definition_builder import run_new_definition
    from .settings_projection import PROFILE,GEOMETRY_PROFILE as GEO_HISTORY_PROFILE
    directory = service.catalog/parent['document_id']/operation_id/'verification-edit'/'saved'
    nonce=uuid4().hex
    bundle=prepare_candidate_artifacts(directory,spec,nonce)
    model=bundle['model_path'];macro=bundle['macro'];history='\n'.join(b['history'] for b in bundle['program'])
    write_json_atomic(directory/'build-intent.json',dict(backend='owned-new-mws-single-runscript',
        parent_revision=parent['document_revision'],spec_sha256=fingerprint(spec),
        history_sha256=hashlib.sha256(history.encode('ascii')).hexdigest()))
    if progress: progress(dict(stage='definition-edit', reason='参数、历史、重建及保存副本', workspace=str(directory)))
    if cancel_check: cancel_check()
    result = (service.definition_editor or run_new_definition)(service.installations[parent['installation_ref']], model, directory, macro,
        **({'generated_profile':GEO_HISTORY_PROFILE if 'geometry' in spec else PROFILE,'cancel_check':cancel_check} if service.definition_editor is None else {}))
    if isinstance(result,dict) and result.get('exit_confirmed') is True and cancel_check:cancel_check()
    source=validate_candidate_completion(bundle,spec,result)
    if cancel_check: cancel_check()
    if 'geometry' in spec:
        from .managed_history import verify_saved_program
        verify_saved_program(source,spec)
        return model
    expected = render_history(spec)[1]
    observed = project_saved_settings(source)
    if observed.status != 'resolved' or dict(expected.fields) != dict(observed.fields) or dict(expected.exact_values) != dict(observed.exact_values):
        fail('SETTING_UNVERIFIED', 'saved candidate differs from the requested typed history')
    return model


def inspect_typed(service, record, document_id, revision):
    body = {k:v for k,v in record.items() if k != 'document_revision'}
    if (record.get('schema_version') != 2 or record.get('project_id') != service.project_id
            or record.get('document_id') != document_id or record.get('document_revision') != revision or fingerprint(body) != revision
            or record.get('state') not in ('draft','saved','closed')):
        fail('DOCUMENT_INVALID', 'typed document identity or revision differs')
    path = Path(record['model_path']).resolve()
    empty = Path(record['empty_model_path']).resolve()
    from .application_service import _sha
    if (not path.is_relative_to(service.catalog) or _sha(path) != record['source_sha256']
            or not empty.is_relative_to(service.catalog) or _sha(empty) != record['empty_sha256']):
        fail('STALE_DOCUMENT', 'saved model or empty baseline changed')
    geometry = 'geometry' in record['spec']
    check_spec(record['spec'], complete=record['state']=='saved' and (not geometry or record.get('validation_target')=='simulation'))
    if geometry:
        expected = project_geometry(record['spec'])
        if record.get('geometry_projection')!=expected:fail('DOCUMENT_INVALID','GEO declaration projection differs')
        if record.get('geometry_saved') is True:
            proof=record.get('geometry_verification',{})
            from .definition_geometry import geometry_proof_ready
            if (record['state'] not in ('saved','closed') or record.get('validation_target') not in ('geometry','simulation')
                    or not geometry_proof_ready(proof,record['source_sha256'])):
                fail('DOCUMENT_INVALID','GEO native save proof differs')
            from .managed_history import verify_saved_program
            verify_saved_program(read_saved_source(path,scope='root'),record['spec'])
            if record['validation_target']=='geometry' and (record.get('ready') or record.get('definition_revision') is not None):
                fail('DOCUMENT_INVALID','geometry save cannot grant simulation readiness')
        elif (record.get('geometry_saved') is not False or record.get('ready') is not False
                or record.get('definition_revision') is not None or record['state']=='saved'
                or record.get('validation_target') is not None or record.get('geometry_verification') is not None):
            fail('DOCUMENT_INVALID','unverified GEO document cannot claim native save or readiness')
        # Check only the immediate immutable parent, not an unbounded ancestor
        # walk. Reservations are monotone even when creation features disappear.
        parent_revision = record.get('parent_revision')
        if not isinstance(parent_revision,str) or not re.fullmatch(r'[a-f0-9]{64}',parent_revision):
            fail('DOCUMENT_INVALID','invalid geometry parent revision')
        from .execution_snapshot import read_snapshot_record
        parent = read_snapshot_record(service.project/'control/documents'/document_id/(parent_revision+'.json'),max_bytes=1024*1024)
        if (parent.get('document_id')!=document_id or parent.get('project_id')!=service.project_id
                or parent.get('document_revision')!=parent_revision
                or parent.get('schema_version') not in (1,2)
                or (parent.get('schema_version')==2 and fingerprint({k:v for k,v in parent.items() if k!='document_revision'})!=parent_revision)):
            fail('DOCUMENT_INVALID','geometry parent identity differs')
        if parent['schema_version']==1:
            service.inspect_model(document_id,parent_revision)  # Existing empty-document verifier, no parent recursion.
        parent_spec=parent.get('spec',{})
        parent_geometry=parent_spec.get('geometry',{}) if isinstance(parent_spec,dict) else None
        before=parent_geometry.get('identities',{}) if isinstance(parent_geometry,dict) else None
        if not isinstance(before,dict): fail('DOCUMENT_INVALID','invalid parent identity reservations')
        after = record['spec']['geometry']['identities']
        if any(after.get(oid)!=creator for oid,creator in before.items()):
            fail('DOCUMENT_INVALID','geometry identity reservations cannot be removed or reassigned')
    elif record.get('geometry_projection') is not None:
        fail('DOCUMENT_INVALID', 'A1 document cannot carry a geometry-v1 projection')
    if record.get('ready'):
        if record['state'] != 'saved': fail('DOCUMENT_INVALID', 'only a verified saved document can be ready')
        definition = service.inspect_definition(document_id, record['definition_revision'])
        if not definition['ready'] or definition['source_sha256'] != record['source_sha256']:
            fail('SETTING_UNVERIFIED', 'definition verification no longer valid')
    return record


def preflight_edit(service, payload):
    validate_edit(payload)
    parent = service.inspect_model(payload['document_id'], payload['expected_document_revision'])
    current = read_json(service.project/'control/documents'/payload['document_id']/'current.json')
    if current.get('document_revision') != payload['expected_document_revision']:
        fail('STALE_DOCUMENT', 'expected revision is not current')
    if parent.get('state') == 'closed': fail('DOCUMENT_CLOSED', 'closed documents cannot be modified')
    spec = changed_spec(parent, payload)
    if payload['operation'] == 'save_project':
        if 'geometry' in spec:
            if 'validation_target' not in payload:
                fail('INVALID_ARGUMENT', 'geometry-v1 save requires explicit validation_target')
            target=payload['validation_target']
            if target=='simulation':check_geometry_simulation(spec)
            from .history_program import partition
            partition(spec)
            require_geometry_calibration(target)
            if not callable(getattr(service.definition_verifier,'verify_geometry',None)):
                fail('SETTING_UNVERIFIED','GEO native verification backend not registered')
        elif payload.get('validation_target', 'simulation') != 'simulation':
            fail('UNSUPPORTED_CAPABILITY', 'A1 publication uses simulation validation; geometry-only requires GEO-2')
        else:
            render_history(spec)
            require_calibration()
    if payload['operation']=='close_project' and payload['disposition']=='save' and not parent.get('geometry_saved',parent.get('ready')):
        fail('SETTING_UNVERIFIED','save_project must publish a verified definition before close(save)')
    return parent


def edit_document(service, payload, *, operation_id, cancel_check=None, progress=None):
    """One Runner operation. Lost responses are recovered from a commit, never replayed."""
    validate_edit(payload)
    operation = service._run_directory(operation_id)
    geometry_proof=None
    lock = ProjectRunLock(service.project); lock.acquire()
    try:
        intent = operation/'definition-intent.json'
        if intent.exists():
            if read_json(intent)['payload'] != payload: fail('REQUEST_CONFLICT', 'definition operation payload changed')
            if (operation/'definition-result.json').exists(): return service.definition_operation_result(operation_id)
            fail('RUN_RECONCILIATION_REQUIRED', 'existing edit intent must be reconciled, not repeated')
        from .definition_verifier import assert_definition_sessions_closed
        assert_definition_sessions_closed(service.catalog)
        parent = preflight_edit(service,payload)
        spec = changed_spec(parent,payload)
        if payload['operation'] == 'save_project':
            render_edit_macro(service.catalog/parent['document_id']/operation_id/'verification-edit'/'saved', spec, '0'*32)
        if cancel_check: cancel_check()
        write_json_atomic(intent, dict(payload=payload,document_id=parent['document_id']))
        model = None
        if payload['operation'] == 'save_project':
            model = build_candidate(service,parent,spec,operation_id,cancel_check,progress,target=payload.get('validation_target','simulation'))
            if payload.get('validation_target')=='geometry':
                if progress:progress(dict(stage='geometry-verify',reason='几何保存重开与原生观察',workspace=str(model.parent)))
                geometry_proof=service.definition_verifier.verify_geometry(model,spec,service.installations[parent['installation_ref']],
                    **({'cancel_check':cancel_check} if getattr(service.definition_verifier,'supports_cancel',False) else {}))
                from .definition_geometry import geometry_proof_ready
                from .application_service import _sha
                if not geometry_proof_ready(geometry_proof,_sha(model)):fail('SETTING_UNVERIFIED','GEO native verification did not authorize save')
    finally: lock.release()
    # These methods acquire the same non-reentrant project lock individually.
    definition = None
    if model and payload.get('validation_target')!='geometry':
        definition = service.stage_definition(parent['document_id'],model,parent['installation_ref'],postprocess=spec['postprocess'],
            **({'geometry_spec':spec} if 'geometry' in spec else {}))
        if progress: progress(dict(stage='definition-verify',reason='保存重开与设置核验',workspace=str(model.parent)))
        if cancel_check: cancel_check()
        definition = service.verify_definition(parent['document_id'],definition['definition_revision'],cancel_check=cancel_check)
        if not definition['ready']: fail('SETTING_UNVERIFIED', 'G03 did not authorize publication')
        if 'geometry' in spec:geometry_proof=definition['verification']
    lock = ProjectRunLock(service.project); lock.acquire()
    try:
        current = read_json(service.project/'control/documents'/parent['document_id']/'current.json')
        if current['document_revision'] != payload['expected_document_revision']:
            fail('STALE_DOCUMENT','document changed during native verification; candidate retained')
        if cancel_check: cancel_check()
        closing = payload['operation'] == 'close_project'
        if closing and payload['disposition'] == 'save' and not parent.get('geometry_saved',parent.get('ready')):
            fail('SETTING_UNVERIFIED','save_project must publish a verified definition before close(save)')
        state = 'closed' if closing else ('saved' if definition or geometry_proof else 'draft')
        record = dict(schema_version=2,document_id=parent['document_id'],project_id=service.project_id,
            name=parent['name'],installation_ref=parent['installation_ref'],units=parent['units'],
            parent_revision=parent['document_revision'],state=state,ready=bool(definition),spec=spec,
            empty_model_path=parent.get('empty_model_path',parent['model_path']),
            empty_sha256=parent.get('empty_sha256',parent['source_sha256']),
            model_path=str(service._directory(parent['document_id'],definition['definition_revision'])/'definition.cst') if definition else str(model) if geometry_proof else parent['model_path'],
            source_sha256=definition['source_sha256'] if definition else geometry_proof['source_sha256'] if geometry_proof else parent['source_sha256'],
            definition_revision=definition['definition_revision'] if definition else None,
            operation_id=operation_id)
        if 'geometry' in spec:
            retained=closing and parent.get('geometry_saved') is True
            record.update(geometry_projection=project_geometry(spec),geometry_saved=bool(geometry_proof) or retained,
                validation_target=payload.get('validation_target') if geometry_proof else parent.get('validation_target') if retained else None,
                geometry_verification=geometry_proof if geometry_proof else parent.get('geometry_verification') if retained else None)
            if geometry_proof:
                from .application_service import _sha
                if _sha(Path(record['model_path']))!=record['source_sha256']:fail('STALE_DOCUMENT','geometry candidate changed before publication')
        else:
            record.update(geometry_saved=bool(definition) or (closing and bool(parent.get('geometry_saved', parent.get('ready')))),
                          validation_target='simulation' if definition else (parent.get('validation_target') if closing else None))
        record['document_revision'] = fingerprint(record)
        if len(json.dumps(record,ensure_ascii=False,indent=2).encode('utf-8'))>1024*1024:
            fail('RESOURCE_LIMIT','typed document including native proof exceeds 1 MiB')
        target = service.project/'control/documents'/parent['document_id']
        write_json_atomic(target/(record['document_revision']+'.json'),record)
        # A durable commit authorizes recovery to complete the pointer and response.
        write_json_atomic(operation/'definition-commit.json',record)
        write_json_atomic(target/'current.json',dict(document_revision=record['document_revision']))
        write_json_atomic(operation/'definition-result.json',record)
        return record
    finally: lock.release()


def reconcile_edit(service, run_id):
    lock = ProjectRunLock(service.project); lock.acquire()
    try:
        operation = service._run_directory(run_id)
        if (operation/'definition-result.json').exists(): return service.definition_operation_result(run_id)
        intent = read_json(operation/'definition-intent.json'); validate_edit(intent['payload'])
        path = operation/'definition-commit.json'
        if not path.exists(): fail('RUN_RECONCILIATION_REQUIRED', 'uncommitted edit retained; native edit is never repeated')
        commit = read_json(path)
        record = service.inspect_model(intent['document_id'],commit['document_revision'])
        if record.get('operation_id') != run_id or record.get('parent_revision') != intent['payload']['expected_document_revision']:
            fail('DOCUMENT_INVALID','commit does not match operation')
        target = service.project/'control/documents'/record['document_id']/'current.json'
        current = read_json(target)
        if current['document_revision'] == record['parent_revision']:
            write_json_atomic(target,dict(document_revision=record['document_revision']))
        elif current['document_revision'] != record['document_revision']:
            fail('STALE_DOCUMENT','later document exists; recovery will not move pointer backwards')
        write_json_atomic(operation/'definition-result.json',record)
        return record
    finally: lock.release()

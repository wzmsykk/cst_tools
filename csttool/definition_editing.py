"""Typed A1 draft transactions and copy-only publication through the shared G03.

Drafts describe intentions, not live CST settings. Only save_project executes
bounded generated history; no caller VBA, paths, or solver calls are accepted.
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
from .vb_codec import quote_vb_string


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
        fail('INVALID_ARGUMENT', 'definition arguments do not match the frozen A1 schema')
    # Reject bool-as-number and NaN/Infinity, including nested values.
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError):
        fail('INVALID_ARGUMENT', 'non-finite or non-JSON arguments')


def arithmetic(spec):
    return _Arithmetic([dict(name=k, expr=v['expression']) for k, v in spec['parameters'].items()])


def check_spec(spec, *, complete=False):
    """Cross-field checks use the existing bounded expression evaluator."""
    params = spec['parameters']
    if len(params) > 128 or len({k.lower() for k in params}) != len(params):
        fail('INVALID_ARGUMENT', 'A1 supports at most 128 case-insensitively unique parameters')
    for name, row in params.items():
        if (len(row['expression']) > 4096 or any(c in row['expression'] for c in '\r\n\x00"')
                or any(ord(c)<32 for c in row['description'])):
            fail('UNSUPPORTED_CAPABILITY', 'bounded single-line arithmetic expressions are required')
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


def initial_spec(record):
    return deepcopy(record.get('spec', dict(parameters={}, components=[])))


def changed_spec(record, payload):
    spec = initial_spec(record)
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
    check_spec(spec, complete=True)
    c = spec['cylinder']; sim = spec['simulation']
    q = lambda value: '"'+quote_vb_string(value)+'"'
    def numeric(expression):
        # Compile bounded arithmetic into numeric VBA in loaded 3D scope.
        # Parameter references remain in history; never substitute cached values.
        text=expression.replace('^','**').strip()
        names={key.lower():key for key in spec['parameters']}
        def compile_node(node):
            if isinstance(node,ast.Constant) and type(node.value) in (int,float):
                return ast.get_source_segment(text,node)
            if isinstance(node,ast.Name):return 'RestoreDoubleParameter('+q(names[node.id.lower()])+')'
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
                return '('+('+' if isinstance(node.op,ast.UAdd) else '-')+compile_node(node.operand)+')'
            if isinstance(node,ast.BinOp):
                operators={ast.Add:'+',ast.Sub:'-',ast.Mult:'*',ast.Div:'/',ast.Pow:'^'}
                if type(node.op) in operators:return '('+compile_node(node.left)+operators[type(node.op)]+compile_node(node.right)+')'
            fail('UNSUPPORTED_CAPABILITY','arithmetic expression cannot compile to A1 history')
        # A bare multi-argument VBA method cannot start its first argument with
        # '('; WinWrap treats it as the method's argument-list opener. A zero
        # additive prefix keeps the exact expression and unambiguous Sub syntax.
        return '0+'+compile_node(ast.parse(text,mode='eval').body)
    lines = ['With Units', ' .Geometry "mm"', ' .Frequency "MHz"', 'End With',
             'ChangeSolverType "HF Eigenmode"', 'With Background', ' .Type "pec"']
    lines += [' .'+face+'Space 0' for face in ('Xmin','Xmax','Ymin','Ymax','Zmin','Zmax')]
    lines += ['End With', 'With Boundary']
    lines += [' .'+face+' "electric"' for face in ('Xmin','Xmax','Ymin','Ymax','Zmin','Zmax')]
    lines += [' .'+a+'symmetry "none"' for a in 'XYZ']
    lines += ['End With', 'WCS.ActivateWCS "global"']
    lines += ['Component.New '+q(name) for name in spec['components']]
    lines += ['With Cylinder', ' .Reset', ' .Name '+q(c['object_id']), ' .Component '+q(c['component_id']),
              ' .Material "Vacuum"', ' .Axis '+q(c['axis']), ' .OuterRadius '+numeric(c['outer_radius']),
              ' .InnerRadius 0', ' .Xcenter 0', ' .Ycenter 0', ' .Zcenter 0',
              ' .'+c['axis'].upper()+'range '+', '.join(numeric(e) for e in c['axial_range']),
              ' .Segments 0', ' .Create', 'End With', 'EigenmodeSolver.Reset',
              'Solver.FrequencyRange '+q(sim['frequency_range_mhz']['min'])+', '+q(sim['frequency_range_mhz']['max']),
              'Mesh.MeshType "Tetrahedral"', 'With MeshSettings', ' .SetMeshType "Tet"', ' .Set "Version", 1',
              ' .Set "StepsPerWaveNear", '+q(sim['mesh']['cells_per_wavelength']),
              ' .Set "StepsPerWaveFar", '+q(sim['mesh']['cells_per_wavelength']),
              ' .Set "CellsPerWavelengthPolicy", "cellsperwavelength"', 'End With', 'With EigenmodeSolver',
              ' .SetMethodType "Default", "Tet"', ' .SetMeshType "Tetrahedral Mesh"',
              ' .SetFrequencyTarget True, '+q(sim['frequency_lower_target_mhz']), ' .SetNumberOfModes 1',
              ' .SetMeshAdaptationTet False', ' .SetConsiderLossesInPostprocessingOnly True', 'End With']
    history = '\n'.join(lines)
    projection = project_history(history, [dict(name=k, expr=v['expression']) for k,v in spec['parameters'].items()], scope='root', available_scopes=('root',))
    if projection.status != 'resolved' or projection.missing_fields:
        fail('SETTING_UNVERIFIED', 'generated history failed A1 projection: '+str(projection.reasons))
    return history, projection


def render_edit_macro(directory, spec, nonce):
    history, _ = render_history(spec)
    q = lambda value: '"'+quote_vb_string(value)+'"'
    params = spec['parameters']
    def assign(name,value):
        lines=['    '+name+' = ""']
        # Bound physical WinWrap lines even for non-ASCII descriptions/large expressions.
        for row,line in enumerate(value.split('\n')):
            if row:lines.append('    '+name+' = '+name+' & vbCrLf')
            lines += ['    '+name+' = '+name+' & '+q(line[i:i+24]) for i in range(0,len(line),24)]
        return lines
    setup = ['    ReportStage "parameters"']
    if params:
        setup += ['    ReDim names(0 To '+str(len(params)-1)+'), expressions(0 To '+str(len(params)-1)+')']
        for index,(name,row) in enumerate(params.items()):
            setup += assign('names('+str(index)+')',name)+assign('expressions('+str(index)+')',row['expression'])
        setup += ['    StoreParameters(names, expressions)']
    for name,row in params.items():
        setup += assign('message',row['description'])+['    SetParameterDescription '+q(name)+', message']
    setup += assign('history',history)
    return ''''#Language "WWB-COM"
Option Explicit
Sub Main
    Dim names() As String, expressions() As String, history As String, f As Integer, message As String
    On Error GoTo Failed
'''+ '\n'.join(setup)+f'''
    ReportStage "history"
    If Not AddToHistory("CST Tools A1 typed definition", history) Then Err.Raise vbObjectError + 2992, "A1", "history rejected"
    ReportStage "rebuild"
    If Not Rebuild Then Err.Raise vbObjectError + 2993, "A1", "rebuild failed"
    ReportStage "save"
    SaveAs {q(directory/'definition.cst')}, False
    f = FreeFile
    Open {q(directory/'completed.txt')} For Output As #f
    Print #f, {q(nonce)}
    Close #f
    ReportStage "batch-return"
    Exit Sub
Failed:
    message = CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    Close
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


def build_candidate(service, parent, spec, operation_id, cancel_check, progress):
    """Construct only a new A1 candidate, then use the existing G03 verifier."""
    from .native_definition_builder import run_new_definition
    directory = service.catalog/parent['document_id']/operation_id/'verification-edit'/'saved'
    directory.mkdir(parents=True, exist_ok=False)
    model = directory/'definition.cst'
    nonce = uuid4().hex
    history=render_history(spec)[0]
    (directory/'history.vb').write_text(history,encoding='ascii')
    write_json_atomic(directory/'build-intent.json',dict(backend='owned-new-mws-single-runscript',
        parent_revision=parent['document_revision'],spec_sha256=fingerprint(spec),
        history_sha256=hashlib.sha256(history.encode('ascii')).hexdigest()))
    if progress: progress(dict(stage='definition-edit', reason='参数、历史、重建及保存副本', workspace=str(directory)))
    if cancel_check: cancel_check()
    result = (service.definition_editor or run_new_definition)(service.installations[parent['installation_ref']], model, directory, render_edit_macro(directory,spec,nonce))
    if (result.get('exit_confirmed') is not True or result.get('exit_code') != 0 or (directory/'failed.txt').exists()
            or not (directory/'completed.txt').exists() or (directory/'completed.txt').read_text().strip() != nonce):
        failure=(directory/'failed.txt').read_text(errors='replace')[:4096] if (directory/'failed.txt').exists() else 'no failure receipt'
        fail('SETTING_UNVERIFIED', 'definition edit not confirmed; exit_confirmed='+str(result.get('exit_confirmed'))+
             ', exit_code='+str(result.get('exit_code'))+', completion='+str((directory/'completed.txt').exists())+
             ', native='+failure+'; diagnostics='+str(directory))
    if cancel_check: cancel_check()
    source = read_saved_source(model,scope='root')
    expected = render_history(spec)[1]
    observed = project_saved_settings(source)
    if observed.status != 'resolved' or dict(expected.fields) != dict(observed.fields) or dict(expected.exact_values) != dict(observed.exact_values):
        fail('SETTING_UNVERIFIED', 'saved candidate differs from the requested typed history')
    rows = source.json('Model/Parameters.json')['parameters']
    if {r['name']:(r['expr'],r.get('descr')) for r in rows} != {k:(v['expression'],v['description']) for k,v in spec['parameters'].items()}:
        fail('SETTING_UNVERIFIED', 'saved parameter expressions/descriptions differ from the draft')
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
    check_spec(record['spec'], complete=record['state'] == 'saved')
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
    changed_spec(parent, payload)
    if payload['operation']=='close_project' and payload['disposition']=='save' and not parent.get('ready'):
        fail('SETTING_UNVERIFIED','save_project must publish a verified definition before close(save)')
    return parent


def edit_document(service, payload, *, operation_id, cancel_check=None, progress=None):
    """One Runner operation. Lost responses are recovered from a commit, never replayed."""
    validate_edit(payload)
    operation = service._run_directory(operation_id)
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
        if cancel_check: cancel_check()
        write_json_atomic(intent, dict(payload=payload,document_id=parent['document_id']))
        model = None
        if payload['operation'] == 'save_project':
            model = build_candidate(service,parent,spec,operation_id,cancel_check,progress)
    finally: lock.release()
    # These methods acquire the same non-reentrant project lock individually.
    definition = None
    if model:
        definition = service.stage_definition(parent['document_id'],model,parent['installation_ref'],postprocess=spec['postprocess'])
        if progress: progress(dict(stage='definition-verify',reason='保存重开与设置核验',workspace=str(model.parent)))
        if cancel_check: cancel_check()
        definition = service.verify_definition(parent['document_id'],definition['definition_revision'])
        if not definition['ready']: fail('SETTING_UNVERIFIED', 'G03 did not authorize publication')
    lock = ProjectRunLock(service.project); lock.acquire()
    try:
        current = read_json(service.project/'control/documents'/parent['document_id']/'current.json')
        if current['document_revision'] != payload['expected_document_revision']:
            fail('STALE_DOCUMENT','document changed during native verification; candidate retained')
        if cancel_check: cancel_check()
        closing = payload['operation'] == 'close_project'
        if closing and payload['disposition'] == 'save' and not parent.get('ready'):
            fail('SETTING_UNVERIFIED','save_project must publish a verified definition before close(save)')
        state = 'closed' if closing else ('saved' if definition else 'draft')
        record = dict(schema_version=2,document_id=parent['document_id'],project_id=service.project_id,
            name=parent['name'],installation_ref=parent['installation_ref'],units=parent['units'],
            parent_revision=parent['document_revision'],state=state,ready=bool(definition),spec=spec,
            empty_model_path=parent.get('empty_model_path',parent['model_path']),
            empty_sha256=parent.get('empty_sha256',parent['source_sha256']),
            model_path=str(service._directory(parent['document_id'],definition['definition_revision'])/'definition.cst') if definition else parent['model_path'],
            source_sha256=definition['source_sha256'] if definition else parent['source_sha256'],
            definition_revision=definition['definition_revision'] if definition else None,
            operation_id=operation_id)
        record['document_revision'] = fingerprint(record)
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

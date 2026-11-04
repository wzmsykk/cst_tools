"""GEO declaration editing/projection, never a CST observer or geometry kernel.

The immutable Spec is the sole intent. Object lifetimes and native names are
derived on each inspection. No native history is emitted by this module.
"""
import ast
from copy import deepcopy
import hashlib
import json
import re

from .settings_projection import _Arithmetic, ProjectionError, GEOMETRY_PROFILE as HISTORY_PROFILE
from .winwrap_emitter import validate_parameter_names

PROFILE = 'geometry-v1'
MAX_FEATURES = 512
GEOMETRY_OPS = frozenset(('create_brick', 'create_cylinder', 'create_sphere',
                         'translate_solid', 'boolean_solids', 'delete_object'))


def reject(reason, diagnostics=None):
    # Same service error boundary as the existing definition transaction.
    from .application_service import ServiceError
    if diagnostics is None:
        raise ServiceError('INVALID_ARGUMENT', reason)
    # Full structured diagnostics stay available to in-process clients. Existing
    # Runner/HTTP error strings also retain a bounded, machine-readable summary.
    summary = {**diagnostics, 'issues':diagnostics.get('issues', [])[:4],
        'affected_feature_ids':diagnostics.get('affected_feature_ids', [])[:8],
        'affected_selection_ids':diagnostics.get('affected_selection_ids', [])[:8]}
    summary['truncated'] = (len(diagnostics.get('issues', [])) > 4
                            or len(diagnostics.get('affected_feature_ids', [])) > 8
                            or len(diagnostics.get('affected_selection_ids', [])) > 8
                            or diagnostics.get('issues_truncated', False))
    error = ServiceError('INVALID_ARGUMENT', reason+' | geometry_diagnostics='+json.dumps(summary, ensure_ascii=True, separators=(',', ':')))
    error.diagnostics = diagnostics
    raise error


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,99}', value):
        reject('geometry IDs must start with a letter and contain only letters, digits, _ or -')
    return value


def feature_id(payload, index):
    """Stable across preflight/execute/recovery; bound to parent CAS and step."""
    encoded = json.dumps([payload, index], sort_keys=True, allow_nan=False).encode()
    return 'f_' + hashlib.sha256(encoded).hexdigest()[:32]


def native_component_name(component):
    return 'c_'+hashlib.sha256(component.encode()).hexdigest()[:20]


def native_solid_name(component, oid):
    return native_component_name(component)+':s_'+hashlib.sha256(oid.encode()).hexdigest()[:20]


def feature_expressions(feature):
    """Paths of the typed dimensional inputs, shared by dependency/codegen tools."""
    op=feature['op'];result={}
    if op=='create_brick':
        for axis,bounds in feature['bounds_mm'].items():
            result.update({'bounds_mm.'+axis+'['+str(i)+']':e for i,e in enumerate(bounds)})
    else:
        fields={'create_cylinder':('axial_range_mm','transverse_center_mm','inner_radius_mm','outer_radius_mm'),
                'create_sphere':('center_mm','radius_mm'),'translate_solid':('translation_mm',)}.get(op,())
        for field in fields:
            value=feature[field]
            if isinstance(value,list):result.update({field+'['+str(i)+']':e for i,e in enumerate(value)})
            else:result[field]=value
    return result


def apply_changes(spec, payload):
    """Modify an isolated Spec; project_geometry validates the whole final batch."""
    spec = deepcopy(spec)
    spec.setdefault('geometry', dict(profile=PROFILE, features=[], identities={}))
    spec.setdefault('selection_sets', {})
    geometry = spec['geometry']
    for index, change in enumerate(payload['changes']):
        op = change['op']
        if op == 'set_parameters':
            spec['parameters'].update(deepcopy(change['values']))
        elif op == 'ensure_component':
            if change['component_id'] not in spec['components']:
                spec['components'].append(change['component_id'])
        elif op in ('set_background','set_boundaries'):
            spec['background' if op=='set_background' else 'boundaries']=deepcopy(change)
        elif op in GEOMETRY_OPS:
            if op.startswith('create_') and change['component_id'] not in spec['components']:
                reject('component must be declared before solid creation')
            fid = feature_id(payload, index)
            if op.startswith('create_'):
                oid = change['object_id']
                if oid.lower() in {name.lower() for name in geometry['identities']}:
                    reject('object IDs cannot be reused, including removed creation features')
                geometry['identities'][oid] = fid
            geometry['features'].append(dict(feature_id=fid, **deepcopy(change)))
        elif op in ('update_feature', 'remove_feature'):
            matches = [i for i, row in enumerate(geometry['features']) if row['feature_id']==change['feature_id']]
            if not matches:
                reject('feature does not exist: '+change['feature_id'])
            position = matches[0]; original = geometry['features'][position]
            if op == 'remove_feature':
                del geometry['features'][position]
            else:
                replacement = deepcopy(change['replacement'])
                if (replacement['op'] != original['op'] or
                        (original['op'].startswith('create_') and replacement['object_id'] != original['object_id'])):
                    reject('feature operation and created object identity are immutable')
                geometry['features'][position] = dict(feature_id=original['feature_id'], **replacement)
        elif op == 'define_selection_set':
            row = deepcopy(change)
            row['members'] = sorted(row['members'])
            spec['selection_sets'][row.pop('selection_id')] = row
        elif op == 'delete_selection_set':
            if change['selection_id'] not in spec['selection_sets']:
                reject('selection does not exist')
            del spec['selection_sets'][change['selection_id']]
        else:
            reject('operation is not supported by geometry-v1')
    project_geometry(spec)
    return spec


def dependency_report(trace, issues, *, issue_count=None, roots=(), selections=()):
    """Bounded failure facts; transitive consumers are derived, never repaired."""
    affected = set(roots) | {item['feature_id'] for item in issues if item.get('feature_id')}
    selections = set(selections) | {item['selection_id'] for item in issues if item.get('selection_id')}
    for row in trace:
        if row['feature_id'] in affected or affected.intersection(row['depends_on']):
            affected.add(row['feature_id'])
            selections.update(row['selection_consumers'])
    total = len(issues) if issue_count is None else issue_count
    return dict(phase='geometry-declaration', issues=issues[:64], issue_count=total,
        issues_truncated=total>64, affected_feature_ids=[r['feature_id'] for r in trace if r['feature_id'] in affected],
        affected_selection_ids=sorted(selections))


def trace_dependencies(features, sets, identities, params, components):
    """One sequential lifetime projection, shared by state and dependency output."""
    objects, trace, issues = {}, [], []
    issue_count = 0
    invalid_features, invalid_selections = set(), set()
    creators = {r['object_id']:(i,r['feature_id']) for i,r in enumerate(features) if r['op'].startswith('create_')}
    parameter_cache = {}

    def parameter_names(text):
        # All expressions/parameters were already validated by the bounded parser.
        result = set()
        for node in ast.walk(ast.parse(text.replace('^','**').strip(), mode='eval')):
            if isinstance(node,ast.Name):
                name = next(k for k in params if k.lower()==node.id.lower())
                result.add(name)
                if name not in parameter_cache:
                    parameter_cache[name] = parameter_names(params[name]['expression'])
                result.update(parameter_cache[name])
        return result

    def issue(code, *, row=None, field=None, oid=None, sid=None):
        nonlocal issue_count
        issue_count += 1
        if row: invalid_features.add(row['feature_id'])
        if sid: invalid_selections.add(sid)
        if len(issues) < 64:
            issues.append(dict(code=code, feature_id=row['feature_id'] if row else None,
                step_index=row['step_index'] if row else None, input_field=field, object_id=oid,
                selection_id=sid, causal_feature_id=objects.get(oid,{}).get('changed_by',identities.get(oid))))
        if row: row['_invalid'] = True

    for index, feature in enumerate(features):
        fid, op = feature['feature_id'], feature['op']
        row = dict(feature_id=fid, step_index=index, depends_on=[], inputs=[], outputs=[],
                   parameter_names=[], consumers=[], selection_consumers=[])
        trace.append(row)
        input_fields = ('target_id','tool_id') if op=='boolean_solids' else ('target_id',) if op=='translate_solid' else ('object_id',) if op=='delete_object' else ()
        for field in input_fields:
            oid = feature[field]; previous = objects.get(oid)
            row['inputs'].append(dict(object_id=oid, source_feature_id=previous['changed_by'] if previous else identities.get(oid),
                                      state_before=previous['state'] if previous else 'missing'))
            if previous:
                row['depends_on'].append(previous['changed_by'])
            if not previous or previous['state'] != 'live':
                code = ('forward-reference' if oid in creators and creators[oid][0]>=index else
                        'removed-creator' if not previous and oid in identities else
                        previous['state'] if previous else 'missing-object')
                issue(code,row=row,field=field,oid=oid)
        touched = []
        if op.startswith('create_'):
            oid, component = feature['object_id'], feature['component_id']
            if oid in objects: issue('duplicate-object',row=row,field='object_id',oid=oid)
            if component not in components: issue('missing-component',row=row,field='component_id',oid=oid)
            native = native_solid_name(component,oid)
            objects[oid] = dict(state='invalid' if row.get('_invalid') else 'live',component_id=component,
                material_id=feature['material_id'],created_by=fid,changed_by=fid,native_name=native)
            touched = [oid]
        elif op=='boolean_solids':
            target_id, tool_id = feature['target_id'],feature['tool_id']
            if target_id==tool_id: issue('self-boolean',row=row,field='tool_id',oid=tool_id)
            if not row.get('_invalid'):
                if any(objects[target_id][k]!=objects[tool_id][k] for k in ('component_id','material_id')):
                    issue('incompatible-operands',row=row,field='tool_id',oid=tool_id)
            if not row.get('_invalid'):
                objects[target_id]['changed_by'] = fid
                objects[tool_id].update(state='consumed',changed_by=fid)
                touched = [target_id,tool_id]
        elif not row.get('_invalid'):
            oid = feature[input_fields[0]]
            objects[oid].update(changed_by=fid,state='deleted' if op=='delete_object' else 'live')
            touched = [oid]
        if row.get('_invalid') and op in ('translate_solid','boolean_solids','delete_object'):
            # Propagate tainted outputs only for diagnostics. Nothing is published.
            oid = feature[input_fields[0]]
            objects.setdefault(oid,dict(created_by=identities.get(oid)))
            objects[oid].update(state='invalid',changed_by=fid)
            touched = [oid]
        if sum(o['state']=='live' for o in objects.values())>128:
            issue('live-solid-budget',row=row)
        row['outputs'] = [dict(object_id=oid,state=objects[oid]['state']) for oid in touched]
        row['depends_on'] = sorted(set(row['depends_on']))
        # Geometry expressions are validated by project_geometry; avoid parsing an
        # invalid expression here so its error can carry a feature-specific report.
        for text in feature_expressions(feature).values():
            try: row['parameter_names'].extend(parameter_names(text))
            except (SyntaxError,ValueError,RecursionError,StopIteration): pass
        row['parameter_names'] = sorted(set(row['parameter_names']))
    by_id = {r['feature_id']:r for r in trace}
    for row in trace:
        for source in row['depends_on']:
            if source in by_id: by_id[source]['consumers'].append(row['feature_id'])
    for sid, selection in sorted(sets.items()):
        for member in selection['members']:
            obj = objects.get(member)
            if not obj or obj['state']!='live': issue('invalid-selection-member',field='members',oid=member,sid=sid)
            if obj and obj.get('changed_by') in by_id:
                by_id[obj['changed_by']]['selection_consumers'].append(sid)
    for row in trace:
        row.pop('_invalid',None)
        row['selection_consumers'] = sorted(set(row['selection_consumers']))
    return objects,trace,dependency_report(trace,issues,issue_count=issue_count,
        roots=invalid_features,selections=invalid_selections)


def validate_selection_sets(sets):
    if not isinstance(sets,dict) or len(sets)>64 or len({identity(k).lower() for k in sets})!=len(sets):
        reject('at most 64 case-insensitively unique selection sets are supported')
    for row in sets.values():
        if (set(row) != {'op','entity_kind','members'} or row['op']!='define_selection_set'
                or row['entity_kind']!='solid' or not isinstance(row['members'],list)
                or not 1<=len(row['members'])<=128 or any(not isinstance(n,str) for n in row['members'])
                or len(set(row['members']))!=len(row['members'])):
            reject('invalid solid selection set')


class GeometryValueError(ValueError):
    def __init__(self, reason, field):
        super().__init__(reason)
        self.input_field = field


def resolve_feature_values(body, params, numbers):
    """Resolve only typed dimensional inputs; never calculate a Boolean shape."""
    def value(text, field):
        try: return expression(text, params, numbers, length=True)
        except ValueError as error: raise GeometryValueError(str(error),field) from error

    def vector(field):
        return [str(value(e,field+'['+str(i)+']')) for i,e in enumerate(body[field])]

    op = body['op']
    if op=='create_brick':
        result = {}
        for axis,bounds in body['bounds_mm'].items():
            field='bounds_mm.'+axis
            lo,hi=[value(e,field+'['+str(i)+']') for i,e in enumerate(bounds)]
            if lo>=hi: raise GeometryValueError('brick requires min < max on every axis',field)
            result[axis]=[str(lo),str(hi)]
        return result
    if op=='create_cylinder':
        lo,hi=[value(e,'axial_range_mm['+str(i)+']') for i,e in enumerate(body['axial_range_mm'])]
        inner,outer=value(body['inner_radius_mm'],'inner_radius_mm'),value(body['outer_radius_mm'],'outer_radius_mm')
        if lo>=hi: raise GeometryValueError('invalid cylinder range','axial_range_mm')
        if not 0<=inner<outer: raise GeometryValueError('invalid cylinder radii','inner_radius_mm/outer_radius_mm')
        return dict(axis=body['axis'],axial_range_mm=[str(lo),str(hi)],inner_radius_mm=str(inner),
                    outer_radius_mm=str(outer),transverse_center_mm=vector('transverse_center_mm'))
    if op=='create_sphere':
        radius=value(body['radius_mm'],'radius_mm')
        if radius<=0: raise GeometryValueError('sphere radius must be positive','radius_mm')
        return dict(radius_mm=str(radius),center_mm=vector('center_mm'))
    if op=='translate_solid': return dict(translation_mm=vector('translation_mm'))
    if op=='boolean_solids': return dict(result_geometry='unverified')
    return {}


def project_geometry(spec):
    """Resolve declared inputs and lifetimes, not measured shape/volume/topology.

    Exact decimal strings avoid float overflow/precision loss at the JSON boundary.
    The same bounded arithmetic evaluator as A1 is used, with no eval or VBA calls.
    """
    from .definition_editing import SCHEMA
    from jsonschema import Draft202012Validator
    if next(Draft202012Validator({'$defs':SCHEMA['$defs'], '$ref':'#/$defs/GeometrySpec'}).iter_errors(spec), None):
        reject('invalid geometry-v1 Spec; identities are required; A1 and simulation settings cannot be mixed')
    feature_validator = Draft202012Validator({'$defs':SCHEMA['$defs'], '$ref':'#/$defs/GeometryFeature'})
    geometry = spec.get('geometry', {})
    if set(geometry) != {'profile', 'features', 'identities'} or geometry['profile'] != PROFILE:
        reject('unknown geometry profile')
    features = geometry['features']
    if not isinstance(features, list) or len(features) > MAX_FEATURES:
        reject('geometry history budget exceeded')
    params = spec['parameters']
    if len(params) > 128:
        reject('at most 128 parameters are supported')
    name = None
    try:
        validate_parameter_names(params,profile=HISTORY_PROFILE)
        numbers = _Arithmetic([dict(name=k, expr=v['expression']) for k, v in params.items()])
        for name, row in params.items():
            if name.lower() in ('pi', 'true', 'false', 'e'):
                reject('reserved parameter name')
            # No function calls, script, cached-value substitution or non-length
            # transitive dependencies in geometry expressions.
            expression(row['expression'], params, numbers, length=False)
            description = row['description']
            if (description != description.strip() or any(ord(c)<32 or ord(c)>0xFFFF
                    or 0xD800<=ord(c)<=0xDFFF for c in description)):
                reject('parameter descriptions require BMP text without control or edge whitespace')
            numbers.parameter(name)
    except ValueError as error:
        reject('geometry parameter validation failed', dict(phase='geometry-parameters',
            issues=[dict(code='invalid-parameter',input_field='parameters'+('.'+name if name else ''),reason=str(error))],
            issue_count=1, affected_feature_ids=[], affected_selection_ids=[], impact_complete=False))
    components = spec['components']
    if len(components) > 32 or len({identity(c).lower() for c in components}) != len(components):
        reject('at most 32 case-insensitively unique components are supported')
    identities = geometry['identities']
    if len({name.lower() for name in identities}) != len(identities) or len(set(identities.values())) != len(identities):
        reject('identity reservations must be case-insensitively unique and have unique creators')
    projected, feature_ids = [], set()
    validate_selection_sets(spec['selection_sets'])

    for feature in features:
        body = {k:v for k,v in feature.items() if k != 'feature_id'}
        if next(feature_validator.iter_errors(body), None):
            reject('invalid stored geometry feature')
        fid = feature.get('feature_id')
        if not isinstance(fid, str) or not re.fullmatch(r'f_[a-f0-9]{32}', fid) or fid in feature_ids:
            reject('invalid or duplicate feature identity')
        feature_ids.add(fid)
        if body['op'].startswith('create_') and identities.get(body['object_id']) != fid:
            reject('creation feature does not own its reserved object identity')
    active = {row['feature_id']:row for row in features}
    for oid, creator in identities.items():
        if creator in active and (not active[creator]['op'].startswith('create_') or active[creator]['object_id']!=oid):
            reject('identity reservation refers to a different active feature')
    objects, trace, issues = trace_dependencies(features, spec['selection_sets'], identities, params, components)
    if issues['issue_count']:
        reject('geometry dependencies are invalid', issues)

    for feature, dependency in zip(features, trace):
        body = {k:v for k,v in feature.items() if k != 'feature_id'}
        fid = feature['feature_id']
        try:
            resolved = resolve_feature_values(body, params, numbers)
        except GeometryValueError as error:
            issue = dict(code='invalid-feature-values', feature_id=fid, step_index=dependency['step_index'],
                input_field=error.input_field, reason=str(error), parameter_names=dependency['parameter_names'])
            reject('geometry feature values are invalid', dependency_report(trace,[issue]))
        digest = hashlib.sha256(json.dumps(body,sort_keys=True,allow_nan=False).encode()).hexdigest()
        projected.append(dict(**dependency, caption='CST Tools GEO '+fid, op=body['op'], resolved=resolved, content_sha256=digest))
    sets = spec['selection_sets']
    result = dict(profile=PROFILE, scope='root', units='mm', wcs='global', evidence='declaration',
        native_verified=False, native_build_state='unverified', declaration_valid=True,
        native_save_supported=False, simulation_supported=False,
        objects=objects, features=projected, selection_sets={k:sorted(v['members']) for k,v in sorted(sets.items())})
    # Budget the stored representation, not just individual arrays. Reserve half
    # the strict document reader's 1 MiB cap for identity/path/commit metadata.
    envelope = json.dumps(dict(spec=spec,geometry_projection=result), ensure_ascii=False, indent=2)
    if len(envelope.encode('utf-8')) > 512*1024:
        reject('geometry declaration and projection exceed the 512 KiB document budget')
    return result


def expression(text, params, numbers, *, length):
    """Validate transitive quantity references before shared arithmetic evaluation."""
    if not isinstance(text,str) or not 1 <= len(text) <= 4096:
        reject('bounded arithmetic expression required')
    seen = set()
    def check(source, depth=0):
        if depth > 64 or not re.fullmatch(r'[A-Za-z0-9_ .+*/^()\-]+', source) or '**' in source:
            reject('bounded arithmetic only; no functions or script')
        try: tree = ast.parse(source.replace('^','**').strip(), mode='eval')
        except (SyntaxError, ValueError, RecursionError): reject('invalid geometry expression')
        if sum(1 for _ in ast.walk(tree)) > 256:
            reject('geometry expression node budget exceeded')
        for node in ast.walk(tree):
            if isinstance(node, ast.Call): reject('function calls are not geometry expressions')
            if isinstance(node, ast.Name):
                names = [n for n in params if n.lower()==node.id.lower()]
                if not names: reject('geometry references an undeclared parameter')
                name = names[0]
                if length and params[name]['quantity'] != 'length':
                    reject('geometry references must be declared lengths, including dependencies')
                if name not in seen:
                    seen.add(name); check(params[name]['expression'], depth+1)
    check(text)
    try: return numbers.expression(text)
    except ProjectionError as error: reject(str(error))

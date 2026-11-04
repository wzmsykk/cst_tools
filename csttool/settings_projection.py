"""Bounded A1 persisted-settings/GEO program projections; no execution/live proof."""
import ast
from dataclasses import dataclass, field, replace
from decimal import Decimal, DecimalException, localcontext
import hashlib
import re
from types import MappingProxyType

from .saved_project_source import SavedSource, SourceError

HISTORY = 'Model/3D/Model.mod'
PARAMETERS = 'Model/Parameters.json'
PROFILE = 'cst-a1-history-v2'
GEOMETRY_PROFILE = 'cst-geo-history-v1'

# Exact names/arity, not object-wide exemptions. See docs/a1-history-command-profile.md.
COMMAND_ARITIES = MappingProxyType({
    ('project', 'changesolvertype'): 1,
    ('units', 'geometry'): 1, ('units', 'frequency'): 1,
    ('wcs', 'activatewcs'): 1, ('component', 'new'): 1,
    ('background', 'type'): 1,
    **{('background', face+'space'): 1 for face in ('xmin','xmax','ymin','ymax','zmin','zmax')},
    **{('boundary', face): 1 for face in ('xmin','xmax','ymin','ymax','zmin','zmax')},
    **{('boundary', axis+'symmetry'): 1 for axis in 'xyz'},
    ('cylinder', 'reset'): 0, ('cylinder', 'create'): 0,
    **{('cylinder', name): 1 for name in
       ('name','component','material','axis','outerradius','innerradius','segments','xcenter','ycenter','zcenter')},
    **{('cylinder', axis+'range'): 2 for axis in 'xyz'},
    ('solver', 'frequencyrange'): 2, ('mesh', 'meshtype'): 1,
    ('mesh', 'stepsperwavelengthtet'): 1,
    ('meshsettings', 'setmeshtype'): 1, ('meshsettings', 'set'): 2,
    ('eigenmodesolver', 'reset'): 0, ('eigenmodesolver', 'setnumberofmodes'): 1,
    ('eigenmodesolver', 'setmethodtype'): 2, ('eigenmodesolver', 'setmeshtype'): 1,
    ('eigenmodesolver', 'setfrequencytarget'): 2,
    ('eigenmodesolver', 'setmeshadaptationtet'): 1,
    ('eigenmodesolver', 'setmeshadaptationhex'): 1,
    ('eigenmodesolver', 'setconsiderlossesinpostprocessingonly'): 1,
    ('meshadaption3d', 'settype'): 1, ('meshadaption3d', 'minpasses'): 1,
})

# Same registry entry point, separate explicit profile. None of these extra
# commands become valid A1 history or authorize native execution.
GEOMETRY_COMMAND_ARITIES = MappingProxyType({
    **{key:value for key,value in COMMAND_ARITIES.items() if key[0] in ('cylinder','wcs','component','units')},
    **{(obj,method):0 for obj in ('brick','sphere','transform') for method in ('reset',)},
    ('brick','create'):0, ('sphere','create'):0,
    **{(obj,method):1 for obj in ('brick','sphere') for method in ('name','component','material')},
    **{('brick',a+'range'):2 for a in 'xyz'},
    **{('sphere',method):1 for method in ('axis','centerradius','topradius','bottomradius','segments')},
    ('sphere','center'):3,
    **{('solid',method):2 for method in ('add','subtract','intersect')}, ('solid','delete'):1,
    **{('transform',method):1 for method in ('name','usepickedpoints','multipleobjects','groupobjects','repetitions','touch')},
    ('transform','vector'):3, ('transform','transform'):2,
})


def command_arities(profile=PROFILE):
    if profile==PROFILE: return COMMAND_ARITIES
    if profile==GEOMETRY_PROFILE: return GEOMETRY_COMMAND_ARITIES
    raise ValueError('unknown history profile')


def history_call_contract(obj, command, *, profile=PROFILE):
    """Calling card derived from the explicitly selected shared command profile.

    This is an owned 3D-history statement, not a DE method/live getter. Values,
    enums, units, numeric-string forms and order remain checked by projection.
    """
    obj, command = obj.lower(), command.lower()
    arity = command_arities(profile).get((obj, command))
    if arity is None:
        raise ValueError('unknown A1 history command')
    topic = {'brick':'Brick','sphere':'Sphere','solid':'Solid','transform':'Transform',
             'project': 'B03', 'units': 'B09', 'wcs': 'B06', 'component': 'B05',
             'background': 'B07', 'boundary': 'B08', 'cylinder': 'B04',
             'solver': 'B11', 'mesh': 'B10', 'eigenmodesolver': 'B12',
             'meshsettings': 'V05', 'meshadaption3d': 'MeshAdaption3D'}[obj]
    return MappingProxyType(dict(arity=arity, scope='loaded-3D', call_kind='statement',
        argument_rule='typed-expression; command-specific values checked by '+('A1' if profile==PROFILE else 'GEO')+' projection',
        return_use='discarded', persistence='AddToHistory; immediate execution and later replay',
        side_effect='candidate geometry or settings mutation; not transactional',
        version='CST2022 A1 profile' if profile==PROFILE else 'CST2022 GEO offline; native calibration pending', documentation=topic))

IDENTITY_FIELDS = ('units.length', 'units.frequency', 'solver.family')


class ProjectionError(ValueError):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason
        super().__init__(reason)


@dataclass(frozen=True)
class Projection:
    status: str
    fields: object
    origins: object
    reasons: tuple
    source_hash: str
    scope: str
    parser_profile: str = PROFILE
    publish_ready: bool = False
    live_value: None = None
    failure_origin: object = None
    exact_values: object = field(default_factory=lambda: MappingProxyType({}))

    @property
    def missing_fields(self):
        """Missing A1 settings remain explicit even when a partial projection resolves."""
        if self.parser_profile==GEOMETRY_PROFILE:
            return tuple(k for k in ('units.length','units.frequency','wcs.mode','components','geometry.features','geometry.objects') if k not in self.fields)
        required = IDENTITY_FIELDS + ('solver.selected_mesh', 'solver.selected_method', 'solver.requested_modes',
                    'solver.frequency_target.enabled', 'solver.frequency_target.value_mhz',
                    'solver.mesh_adaptation.tet', 'mesh.tet.near', 'mesh.tet.far',
                    'mesh.tet.version', 'mesh.tet.policy', 'mesh.type',
                    'solver.frequency_range.min_mhz', 'solver.frequency_range.max_mhz',
                    'solver.losses_postprocess_only', 'background.type', 'wcs.mode',
                    'geometry.cylinder.name') + tuple(
                        'background.'+face+'_mm' for face in ('xmin','xmax','ymin','ymax','zmin','zmax')) + tuple(
                        'boundary.'+face for face in ('xmin','xmax','ymin','ymax','zmin','zmax')) + tuple(
                        'boundary.'+axis+'symmetry' for axis in 'xyz')
        if self.parser_profile=='cst-geo-eigenmode-history-v1':
            required=tuple(k for k in required if k!='geometry.cylinder.name')+('geometry.features','geometry.objects')
        return tuple(key for key in required if key not in self.fields)


def _fail(status, reason):
    raise ProjectionError(status, reason)


class _Arithmetic:
    """A deliberately small arithmetic language, not Python/VBA evaluation."""
    def __init__(self, rows):
        if not isinstance(rows, list) or len(rows) > 4096:
            _fail('malformed', 'invalid-parameters')
        self.rows, self.values, self.visiting = {}, {}, set()
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get('name'), str)
                    or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', row['name'])
                    or not isinstance(row.get('expr'), str)):
                _fail('malformed', 'invalid-parameters')
            name = row['name'].lower()
            if name in self.rows:
                _fail('malformed', 'duplicate-parameter')
            self.rows[name] = row

    def parameter(self, name):
        name = name.lower()
        if name in self.visiting:
            _fail('unresolved', 'parameter-cycle')
        if name not in self.rows:
            _fail('unresolved', 'missing-parameter')
        if name not in self.values:
            if len(self.visiting) >= 64:
                _fail('rejected', 'expression-budget-exceeded')
            self.visiting.add(name)
            row = self.rows[name]
            value = self.expression(row['expr'])
            cached = row.get('cached_value', row.get('value'))
            if cached is not None:
                try:
                    saved = Decimal(str(cached))
                except DecimalException:
                    _fail('malformed', 'invalid-parameter-cache')
                if not saved.is_finite():
                    _fail('malformed', 'invalid-parameter-cache')
                if saved != value:
                    _fail('stale', 'stale-parameter-cache')
            self.visiting.remove(name)
            self.values[name] = value
        return self.values[name]

    def expression(self, text):
        if len(text) > 4096:
            _fail('rejected', 'expression-budget-exceeded')
        # CST exponentiation is ^; ** and Python-only syntax are not accepted.
        if '**' in text:
            _fail('unsupported', 'unsupported-expression')
        text = text.replace('^', '**').strip()
        try:
            tree = ast.parse(text, mode='eval')
        except (SyntaxError, RecursionError, ValueError):
            _fail('unsupported', 'unsupported-expression')
        if sum(1 for _ in ast.walk(tree)) > 256:
            _fail('rejected', 'expression-budget-exceeded')

        def visit(node, depth=0):
            if depth > 64:
                _fail('rejected', 'expression-budget-exceeded')
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                token = ast.get_source_segment(text, node)
                if not re.fullmatch(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', token):
                    _fail('unsupported', 'unsupported-expression')
                value = Decimal(token)
            elif isinstance(node, ast.Name):
                value = self.parameter(node.id)
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                  and node.func.id.lower() == 'restoredoubleparameter' and not node.keywords
                  and len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
                  and isinstance(node.args[0].value, str)):
                value = self.parameter(node.args[0].value)
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = visit(node.operand, depth+1)
                if isinstance(node.op, ast.USub):
                    value = -value
            elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
                left, right = visit(node.left, depth+1), visit(node.right, depth+1)
                if isinstance(node.op, ast.Add): value = left + right
                elif isinstance(node.op, ast.Sub): value = left - right
                elif isinstance(node.op, ast.Mult): value = left * right
                elif isinstance(node.op, ast.Div): value = left / right
                else:
                    if right != right.to_integral_value() or abs(right) > 32:
                        _fail('unsupported', 'unsupported-expression')
                    value = left ** int(right)
            else:
                _fail('unsupported', 'unsupported-expression')
            if not value.is_finite() or (value and abs(value.adjusted()) > 100):
                _fail('rejected', 'expression-value-out-of-range')
            return value
        try:
            with localcontext() as ctx:
                ctx.prec = 40
                return visit(tree.body)
        except ProjectionError:
            raise
        except (DecimalException, OverflowError, ValueError):
            _fail('unsupported', 'unsupported-expression')


def _split(text, separator):
    """Split outside VBA strings; preserve escaped double quotes."""
    parts, start, quoted, i = [], 0, False, 0
    while i < len(text):
        char = text[i]
        if char == '"':
            if quoted and i+1 < len(text) and text[i+1] == '"':
                i += 2
                continue
            quoted = not quoted
        elif char == separator and not quoted:
            parts.append(text[start:i]); start = i+1
            if separator == "'":
                return parts
        i += 1
    if quoted:
        _fail('malformed', 'unterminated-string')
    return parts + [text[start:]]


def _literal(text):
    text = text.strip()
    if re.fullmatch(r'"(?:[^"]|"")*"', text):
        return text[1:-1].replace('""', '"')
    return text


def _string(text):
    if not re.fullmatch(r'"(?:[^"]|"")*"', text.strip()):
        _fail('unsupported', 'literal-string-required')
    return _literal(text)


def _statements(text):
    pending, first, start, offset, step = '', 0, 0, 0, 0
    for line, raw in enumerate(text.splitlines(keepends=True), 1):
        if raw.lstrip().startswith("'@"):
            step += 1
        clean = _split(raw.rstrip('\r\n'), "'")[0].strip()
        if re.match(r'(?i)^Rem(?:\s|$)', clean):
            clean = ''
        if not pending:
            first, start = line, offset
        offset += len(raw.encode('utf-8'))
        continuation = bool(re.search(r'\s_\s*$', clean))
        pending += (' ' if pending else '') + (clean[:-1].rstrip() if continuation else clean)
        if continuation:
            continue
        for statement in _split(pending, ':'):
            if statement.strip():
                yield statement.strip(), first, line, start, offset, step
        pending = ''
    if pending:
        _fail('malformed', 'unterminated-continuation')


class _ModelProjection:
    """A1 model declarations only; never claims that geometry was actually built."""
    def __init__(self):
        self.components = set()
        self.cylinder = None
        self.created = False
        self.dirty = False

    def consume(self, obj, command, args, fields, put, number, location):
        def exact(value, allowed, reason):
            value = _string(value)
            if value not in allowed:
                _fail('unsupported', reason)
            return value

        if obj == 'units':
            kind, expected = ('length', 'mm') if command == 'geometry' else ('frequency', 'MHz')
            put('units.'+kind, exact(args[0], (expected,), 'a1-unit-unsupported'))
        elif obj == 'project':
            put('solver.family', exact(args[0], ('HF Eigenmode',), 'a1-solver-family-unsupported'))
        elif obj == 'wcs':
            put('wcs.mode', exact(args[0], ('global',), 'a1-wcs-unsupported'))
        elif obj == 'component':
            name = _string(args[0])
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,99}', name):
                _fail('unsupported', 'a1-name-unsupported')
            if self.components:
                _fail('unsupported', 'a1-single-component-only')
            self.components.add(name)
            put('geometry.component', name)
        elif obj == 'background':
            if command == 'type':
                put('background.type', exact(args[0], ('pec',), 'a1-background-unsupported'))
            else:
                value, expression = number(args[0])
                if value != 0:
                    _fail('unsupported', 'a1-padding-unsupported')
                put('background.'+command[:-5]+'_mm', float(value), expression)
        elif obj == 'boundary':
            expected = 'none' if command.endswith('symmetry') else 'electric'
            put('boundary.'+command, exact(args[0], (expected,), 'a1-boundary-unsupported'))
        elif obj == 'cylinder':
            if command == 'reset':
                self.cylinder = {}
                self.dirty = True
            elif self.cylinder is None:
                _fail('unresolved', 'cylinder-reset-required')
            elif command == 'create':
                self._create(fields, put, location)
            else:
                if command in ('name', 'component', 'material', 'axis'):
                    value, expression = _string(args[0]), None
                else:
                    pairs = [number(arg) for arg in args]
                    value = tuple(pair[0] for pair in pairs) if len(args) == 2 else pairs[0][0]
                    expression = tuple(pair[1] for pair in pairs) if len(args) == 2 else pairs[0][1]
                self.cylinder[command] = (value, expression, MappingProxyType(dict(location)))
                self.dirty = True
        elif obj == 'mesh' and command == 'meshtype':
            put('mesh.type', exact(args[0], ('Tetrahedral',), 'a1-mesh-unsupported'))
        elif obj == 'solver':
            values = [number(arg) for arg in args]
            if not 0 < values[0][0] < values[1][0]:
                _fail('malformed', 'invalid-frequency-range')
            put('solver.frequency_range.min_mhz', float(values[0][0]), values[0][1], exact=str(values[0][0]))
            put('solver.frequency_range.max_mhz', float(values[1][0]), values[1][1], exact=str(values[1][0]))
        else:
            return False
        return True

    def _create(self, fields, put, location):
        if self.created:
            _fail('unsupported', 'a1-single-cylinder-only')
        axis = self.cylinder.get('axis', (None,))[0]
        if axis not in ('x', 'y', 'z'):
            _fail('unresolved', 'cylinder-axis-required')
        required = ('name', 'component', 'material', 'outerradius', 'innerradius',
                    'segments', 'xcenter', 'ycenter', 'zcenter', axis+'range')
        if any(key not in self.cylinder for key in required):
            _fail('unresolved', 'cylinder-explicit-settings-required')
        values = {key: row[0] for key, row in self.cylinder.items()}
        if fields.get('wcs.mode') != 'global':
            _fail('unresolved', 'cylinder-global-wcs-required')
        if values['component'] not in self.components:
            _fail('unresolved', 'cylinder-component-missing')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,99}', values['name']):
            _fail('unsupported', 'a1-name-unsupported')
        if values['material'] != 'Vacuum' or values['innerradius'] != 0 or values['segments'] != 0:
            _fail('unsupported', 'a1-cylinder-profile-unsupported')
        if any(values[a+'center'] != 0 for a in 'xyz'):
            _fail('unsupported', 'a1-cylinder-center-unsupported')
        if values['outerradius'] <= 0 or values[axis+'range'][1] <= values[axis+'range'][0]:
            _fail('malformed', 'invalid-cylinder-dimensions')
        if any(a != axis and a+'range' in values for a in 'xyz'):
            _fail('unsupported', 'a1-unused-cylinder-range')
        for key, (value, expression, origin) in self.cylinder.items():
            # Cylinder property is staged until Create; both sites remain evidence.
            if isinstance(value, Decimal):
                value = float(value)
            elif isinstance(value, tuple):
                value = tuple(float(item) for item in value)
            put('geometry.cylinder.'+key, value, expression,
                source=MappingProxyType(dict(property=origin, create=MappingProxyType(dict(location)))))
        self.created, self.dirty = True, False


def project_history(text, parameters, *, scope, available_scopes, source_hash='',
                    member_hash=None, parameter_hash=None, active_solver=None,
                    require_identity=False):
    """Project an explicit history/parameter snapshot (synthetic inputs may use this).

    Production callers use project_saved_settings to bind all inputs to B1 bytes.
    A resolved report means only its listed fields; it is never a ready definition.
    """
    fields, origins, expressions, stack = {}, {}, {}, []
    member_hash = member_hash or ''
    location = {}
    reset, partition, adaptation_policy = False, None, False
    model = _ModelProjection()
    exact_values = {}

    def put(key, value, expr=None, *, source=None, exact=None):
        fields[key] = value
        origins[key] = source if source is not None else MappingProxyType(dict(location))
        if expr is not None:
            expressions[key] = expr
        if exact is not None:
            exact_values[key] = exact

    def number(argument):
        expression = _literal(argument)
        cint = re.fullmatch(r'(?i)CInt\(\s*RestoreDoubleParameter\("([A-Za-z][A-Za-z0-9_]*)"\)\s*\)', expression)
        value = arithmetic.parameter(cint[1]) if cint else arithmetic.expression(expression)
        if cint and value != value.to_integral_value():
            _fail('unsupported', 'nonintegral-cint-input')
        return value, expression

    def boolean(argument):
        value = _literal(argument).lower()
        if value not in ('true', 'false'):
            _fail('unsupported', 'unsupported-boolean')
        return value == 'true'

    try:
        if not scope:
            _fail('rejected', 'scope-required')
        if scope not in available_scopes:
            _fail('rejected', 'unknown-scope')
        if active_solver not in (None, 'HF Eigenmode'):
            _fail('unsupported', 'a1-solver-family-unsupported')
        if not isinstance(text, str) or len(text.encode('utf-8')) > 2*1024*1024:
            _fail('rejected', 'history-budget-exceeded')
        member_hash = member_hash or hashlib.sha256(text.encode('utf-8')).hexdigest()
        arithmetic = _Arithmetic(parameters)
        for count, (statement, first, last, start, end, step) in enumerate(_statements(text)):
            if count >= 20000:
                _fail('rejected', 'statement-budget-exceeded')
            location = dict(member=HISTORY, member_hash=member_hash, parameter_hash=parameter_hash,
                            scope=scope, step=step, line_start=first, line_end=last,
                            byte_start=start, byte_end=end, source_hash=source_hash,
                            statement=statement)
            lower = statement.lower()
            if re.match(r'^(if|elseif|else|for|next|do|loop|while|wend|select|end if)\b', lower):
                _fail('unsupported', 'unsupported-control-flow')
            if re.match(r'^(evaluate|execute|executeglobal)\b', lower):
                _fail('unsupported', 'dynamic-code')
            if lower.startswith('set '):
                _fail('unsupported', 'unknown-object-alias')
            if lower.startswith('with '):
                obj = lower[5:].strip()
                if obj not in {item[0] for item in COMMAND_ARITIES} - {'project'}:
                    _fail('unsupported', 'unknown-object-alias')
                stack.append(obj)
                continue
            if lower == 'end with':
                if not stack:
                    _fail('malformed', 'unbalanced-with')
                stack.pop()
                continue
            if lower.startswith('.'):
                if not stack:
                    _fail('malformed', 'unbalanced-with')
                statement = stack[-1] + statement
            global_project_call = bool(re.match(r'(?i)^ChangeSolverType\s', statement))
            if global_project_call:
                statement = 'Project.'+statement
            match = re.fullmatch(r'([A-Za-z][A-Za-z0-9]*)\.([A-Za-z][A-Za-z0-9]*)(?:\s+(.*))?', statement)
            if not match:
                _fail('unsupported', 'unknown-call-taints-settings')
            obj, command, tail = match[1].lower(), match[2].lower(), match[3]
            if obj == 'project' and not global_project_call:
                _fail('unsupported', 'unknown-object-alias')
            args = [a.strip() for a in _split(tail, ',')] if tail is not None else []
            arity = COMMAND_ARITIES.get((obj, command))
            if arity is None:
                _fail('unsupported', 'unknown-call-taints-settings')
            if len(args) != arity or any(not arg for arg in args):
                _fail('malformed', 'invalid-command-arity')
            if require_identity:
                if obj in ('eigenmodesolver', 'solver', 'mesh', 'meshsettings'):
                    if any(key not in fields for key in IDENTITY_FIELDS):
                        _fail('unresolved', 'history-identity-before-settings-required')
                if obj == 'cylinder' and fields.get('units.length') != 'mm':
                    _fail('unresolved', 'length-unit-before-geometry-required')
                if obj == 'solver' and any(key.startswith('mesh.') for key in fields):
                    _fail('unsupported', 'frequency-range-after-mesh')
                if obj == 'project' and any(key.startswith('solver.') and key != 'solver.family' for key in fields):
                    _fail('unsupported', 'solver-selection-after-settings')
            if model.consume(obj, command, args, fields, put, number, location):
                continue
            if command == 'reset' and obj == 'eigenmodesolver':
                for key in list(fields):
                    owned = (key.startswith('solver.') and key != 'solver.family'
                             and not key.startswith('solver.frequency_range.'))
                    if owned:
                        fields.pop(key); origins.pop(key); expressions.pop(key, None)
                        exact_values.pop(key, None)
                reset = True
            elif obj == 'eigenmodesolver' and command == 'setnumberofmodes' and len(args) == 1:
                value, expression = number(args[0])
                if value != value.to_integral_value() or not 1 <= value <= 2147483647:
                    _fail('malformed', 'noninteger-mode-count')
                put('solver.requested_modes', int(value), expression)
            elif obj == 'eigenmodesolver' and command == 'setmethodtype' and len(args) == 2:
                method, mesh = map(_string, args)
                if (mesh, method) not in (('Hex', 'AKS'), ('Tet', 'Default'), ('Tet', 'General (Lossy)')):
                    _fail('unsupported', 'unknown-method-profile')
                put('solver.method_by_mesh.'+mesh, method)
            elif obj in ('eigenmodesolver', 'meshsettings') and command == 'setmeshtype' and len(args) == 1:
                mesh = _string(args[0])
                if obj == 'meshsettings':
                    if mesh not in ('Tet', 'Hex', 'All', 'Unstr'):
                        _fail('unsupported', 'unknown-mesh-partition')
                    partition = mesh
                else:
                    if mesh not in ('Tetrahedral Mesh', 'Hexahedral Mesh'):
                        _fail('unsupported', 'unknown-solver-mesh')
                    put('solver.selected_mesh', {'Tetrahedral Mesh':'Tet', 'Hexahedral Mesh':'Hex'}[mesh])
            elif obj == 'eigenmodesolver' and command == 'setfrequencytarget' and len(args) == 2:
                enabled = boolean(args[0]); value, expression = number(args[1])
                put('solver.frequency_target.enabled', enabled)
                # The profile is explicitly MHz, not inferred from the parameter name.
                put('solver.frequency_target.value_mhz', float(value), expression, exact=str(value))
            elif obj == 'eigenmodesolver' and command in ('setmeshadaptationtet', 'setmeshadaptationhex') and len(args) == 1:
                put('solver.mesh_adaptation.'+command[-3:], boolean(args[0]))
            elif obj == 'eigenmodesolver' and command == 'setconsiderlossesinpostprocessingonly':
                put('solver.losses_postprocess_only', boolean(args[0]))
            elif obj == 'meshsettings' and command == 'set' and len(args) == 2:
                key = _string(args[0]).lower()
                if partition != 'Tet':
                    _fail('unresolved', 'tet-partition-required')
                names = {'stepsperwavenear':'near', 'stepsperwavefar':'far',
                         'cellsperwavelengthpolicy':'policy', 'version':'version'}
                if key not in names:
                    _fail('unsupported', 'unknown-call-taints-settings')
                if key == 'cellsperwavelengthpolicy':
                    value, expression = _string(args[1]), None
                    if value != 'cellsperwavelength':
                        _fail('unsupported', 'unknown-density-policy')
                else:
                    value, expression = number(args[1])
                    if value <= 0:
                        _fail('malformed', 'invalid-mesh-density')
                    if key == 'version' and value != 1:
                        _fail('unsupported', 'uncalibrated-density-version')
                    value = float(value)
                put('mesh.tet.'+names[key], value, expression)
            elif obj == 'mesh' and command == 'stepsperwavelengthtet' and len(args) == 1:
                value, expression = number(args[0])
                if value <= 0:
                    _fail('malformed', 'invalid-mesh-density')
                put('mesh.tet.legacy', float(value), expression)
            elif obj == 'meshadaption3d' and command in ('settype', 'minpasses') and len(args) == 1:
                if command == 'settype':
                    if _string(args[0]) != 'HighFrequencyTet':
                        _fail('unsupported', 'unknown-adaptation-policy')
                else:
                    value, _ = number(args[0])
                    if value < 1 or value != value.to_integral_value():
                        _fail('malformed', 'invalid-adaptation-passes')
                adaptation_policy = True  # These do not set the solver switch.
            else:
                _fail('unsupported', 'unknown-call-taints-settings')
        if stack:
            _fail('malformed', 'unbalanced-with')
        if model.dirty:
            _fail('unresolved', 'cylinder-create-missing')
        if require_identity and any(key not in fields for key in IDENTITY_FIELDS):
            _fail('unresolved', 'history-identity-missing')
        if 'mesh.tet.legacy' in fields and any('mesh.tet.'+k in fields for k in ('near', 'far', 'policy', 'version')):
            _fail('ambiguous', 'uncalibrated-density-channels')
        selected = fields.get('solver.selected_mesh')
        method_key = 'solver.method_by_mesh.'+selected if selected else ''
        if method_key in fields:
            fields['solver.selected_method'] = fields[method_key]
            origins['solver.selected_method'] = MappingProxyType(dict(
                method=origins[method_key], mesh=origins['solver.selected_mesh']))
        if require_identity and 'solver.frequency_target.value_mhz' in fields:
            target = fields['solver.frequency_target.value_mhz']
            upper = fields.get('solver.frequency_range.max_mhz')
            if target < 0 or (upper is not None and target > upper):
                _fail('malformed', 'invalid-frequency-target')
        if not fields:
            _fail('unresolved', 'reset-defaults-unverified' if reset else
                  'adaptation-switch-missing' if adaptation_policy else 'settings-missing')
        for key, expression in expressions.items():
            fields['expressions.'+key] = expression
            origins['expressions.'+key] = origins[key]
        return Projection('resolved', MappingProxyType(fields), MappingProxyType(origins), (), source_hash, scope,
                          exact_values=MappingProxyType(exact_values))
    except ProjectionError as exc:
        # Unsupported code can mutate any previous setting. Never publish stale fields.
        return Projection(exc.status, MappingProxyType({}), MappingProxyType({}), (exc.reason,), source_hash, scope,
                          failure_origin=MappingProxyType(dict(location)) if location else None)


def project_saved_settings(source: SavedSource, *, encoding=None):
    """B1-bound entry; require same-history units and explicit solver selection.

    Last Solver Type, comments and caller declarations cannot replace these anchors.
    Persisted selection is not a GetSolverType live observation.
    """
    try:
        text = source.text(HISTORY, encoding=encoding)
        rows = source.json(PARAMETERS)
        metadata = source.json('Model/simulationproperties.json')  # present-but-malformed is fatal
        if text is None:
            raise SourceError('unresolved', 'history-missing', HISTORY)
        if rows is None:
            raise SourceError('unresolved', 'parameters-missing', PARAMETERS)
        rows = rows.get('parameters')
        report = project_history(text, rows, scope=source.scope, available_scopes=source.scopes,
                                 source_hash=source.sha256, member_hash=source.member_hashes[HISTORY],
                                 parameter_hash=source.member_hashes[PARAMETERS], require_identity=True)
        if metadata is None and report.status == 'resolved':
            report = replace(report, reasons=report.reasons+('optional-metadata-missing',))
        return report
    except SourceError as exc:
        return Projection(exc.status, MappingProxyType({}), MappingProxyType({}),
                          (exc.reason,), source.sha256, source.scope,
                          failure_origin=MappingProxyType(dict(
                              member=exc.member, scope=source.scope, source_hash=source.sha256,
                              member_hash=source.member_hashes.get(exc.member))))


def geometry_expression_identity(text, parameters):
    """Bounded symbolic identity across user arithmetic and its WWB lowering.

    Only the emitter's argument-safe zero-addition is erased. Parameter calls
    become parameter references; no general algebra or numeric substitution.
    """
    _Arithmetic(parameters).expression(text)
    tree=ast.parse(text.replace('^','**').strip(),mode='eval')
    def visit(node):
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            token=ast.get_source_segment(text.replace('^','**').strip(),node)
            value=format(Decimal(token),'f')
            return ('number',value.rstrip('0').rstrip('.') if '.' in value else value)
        if isinstance(node,ast.Name): return ('parameter',node.id.lower())
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id.lower()=='restoredoubleparameter':
            return ('parameter',node.args[0].value.lower())
        if isinstance(node,ast.UnaryOp): return (type(node.op).__name__,visit(node.operand))
        if isinstance(node,ast.BinOp):
            left,right=visit(node.left),visit(node.right)
            if isinstance(node.op,ast.Add) and left==('number','0'): return right
            return (type(node.op).__name__,left,right)
        _fail('unsupported','unsupported-geometry-expression')
    return visit(tree.body)


def project_geometry_history(blocks, parameters, *, scope, available_scopes, source_hash=''):
    """Project owned GEO block bodies using shared lexical/arithmetic primitives.

    This is not a saved Model.mod block extractor, BRep observer, compiler or
    native calibration. Source strings are never executed. A1 stays independent.
    """
    fields,origins,exact,objects,features={},{},{},{},[]
    location={}; components=[]; names=set(); object_origins={}
    def failure(reason,status='unsupported'): _fail(status,reason)
    try:
        if scope!='root' or scope not in available_scopes: failure('geometry-root-scope-required','rejected')
        if not isinstance(blocks,(list,tuple)) or not 1<=len(blocks)<=513: failure('geometry-block-budget','rejected')
        if (not isinstance(parameters,list) or len(parameters)>128): failure('geometry-parameter-budget','rejected')
        arithmetic=_Arithmetic(parameters)
        for name in arithmetic.rows: arithmetic.parameter(name)
        budget=0; captions=set(); statement_count=0

        def numeric(entry, position, path):
            nonlocal location
            location=entry[2]; text=entry[1][position]
            if text.startswith('"'): failure('geometry-numeric-string-outside-profile')
            value=arithmetic.expression(text)
            exact[path]=geometry_expression_identity(text,parameters)
            origins[path]=MappingProxyType(dict(location))
            return value

        def fixed(entry, number):
            if numeric(entry,0,'fixed')!=number or exact.pop('fixed')!=('number',str(number)):
                failure('geometry-fixed-setting-required')
            origins.pop('fixed',None)

        def string(entry, position=0):
            nonlocal location
            location=entry[2]
            return _string(entry[1][position])

        def live(name):
            if name not in objects or objects[name]['state']!='live': failure('geometry-object-not-live')
            return objects[name]

        for block_index,block in enumerate(blocks):
            location=dict(block_index=block_index,scope=scope,source_hash=source_hash)
            if not isinstance(block,dict) or set(block)!={'caption','history'} or not all(isinstance(v,str) for v in block.values()):
                failure('malformed-geometry-block','malformed')
            caption=block['caption'];text=block['history']
            location['caption']=caption
            if caption in captions: failure('duplicate-history-caption','ambiguous')
            if (block_index==0 and caption!='CST Tools GEO setup') or (block_index and not re.fullmatch(r'CST Tools GEO f_[a-f0-9]{32}',caption)):
                failure('geometry-caption-identity')
            encoded=text.encode('utf-8');body_hash=hashlib.sha256(encoded).hexdigest()
            captions.add(caption);budget+=len(encoded)
            if budget>2*1024*1024: failure('history-budget-exceeded','rejected')
            stack=[];calls=[]
            for statement,first,last,start,end,step in _statements(text):
                statement_count+=1
                location=dict(block_index=block_index,caption=caption,scope=scope,source_hash=source_hash,
                    line_start=first,line_end=last,byte_start=start,byte_end=end,statement=statement,
                    member_hash=body_hash)
                if statement_count>20000: failure('statement-budget-exceeded','rejected')
                if statement.lower().startswith('with '):
                    obj=statement[5:].lower().strip()
                    if stack or obj not in {key[0] for key in GEOMETRY_COMMAND_ARITIES}: failure('geometry-with-object')
                    stack.append(obj);continue
                if statement.lower()=='end with':
                    if not stack: failure('unbalanced-with','malformed')
                    stack.pop();continue
                if statement.startswith('.'):
                    if not stack: failure('unbound-with-member','malformed')
                    statement=stack[-1]+statement
                match=re.fullmatch(r'([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)(?:\s+(.*))?',statement)
                if not match: failure('unknown-geometry-statement')
                obj,method=match[1].lower(),match[2].lower()
                args=[s.strip() for s in _split(match[3],',')] if match[3] else []
                if GEOMETRY_COMMAND_ARITIES.get((obj,method))!=len(args) or any(not a for a in args): failure('unknown-geometry-command-or-arity')
                calls.append((obj,method,(method,args,dict(location))))
            if stack or not calls: failure('incomplete-geometry-block','malformed')
            if block_index==0:
                if [(o,m) for o,m,_ in calls[:3]]!=[('units','geometry'),('units','frequency'),('wcs','activatewcs')]: failure('geometry-setup-order')
                if string(calls[0][2])!='mm' or string(calls[1][2])!='MHz' or string(calls[2][2])!='global': failure('geometry-global-mm-required')
                for obj,method,entry in calls[3:]:
                    if (obj,method)!=('component','new'): failure('geometry-setup-command')
                    name=string(entry)
                    if not re.fullmatch(r'c_[a-f0-9]{20}',name) or name in components: failure('geometry-component-identity')
                    components.append(name)
                if len(components)>32: failure('geometry-component-budget','rejected')
                fields.update({'units.length':'mm','units.frequency':'MHz','wcs.mode':'global','components':tuple(components)})
                origins['units.length']=MappingProxyType(calls[0][2][2]);origins['units.frequency']=MappingProxyType(calls[1][2][2]);origins['wcs.mode']=MappingProxyType(calls[2][2][2])
                origins['components']=tuple(MappingProxyType(entry[2]) for _,_,entry in calls[3:])
                continue
            index=len(features);prefix='geometry.features['+str(index)+'].'
            owner=calls[0][0]; props={}
            if owner in ('brick','cylinder','sphere','transform'):
                end='transform' if owner=='transform' else 'create'
                if calls[0][1]!='reset' or calls[-1][1]!=end or any(o!=owner for o,_,_ in calls): failure('geometry-lifecycle-order')
                for _,method,entry in calls[1:-1]:
                    if method in props: failure('duplicate-geometry-property','ambiguous')
                    props[method]=entry
                def required(keys):
                    if set(props)!=set(keys): failure('geometry-properties-missing-or-extra')
                def num(key,path=None,pos=0): return numeric(props[key],pos,prefix+(path or key))
                def vector(key,path): return [str(num(key,path+'['+str(i)+']',i)) for i in range(len(props[key][1]))]
                if owner=='transform':
                    required(('name','vector','usepickedpoints','multipleobjects','groupobjects','repetitions','touch'))
                    for flag in ('usepickedpoints','multipleobjects','groupobjects','touch'):
                        location=props[flag][2]
                        if props[flag][1]!=['False']: failure('geometry-copy-pick-touch-forbidden')
                    fixed(props['repetitions'],1)
                    if [string(calls[-1][2],i) for i in range(2)]!=['Shape','Translate']: failure('geometry-translation-only')
                    target=string(props['name']);live(target)
                    feature=dict(op='translate_solid',target_name=target,resolved=dict(translation_mm=vector('vector','translation_mm')))
                    object_origins[target]=MappingProxyType(calls[-1][2][2])
                else:
                    common=['name','component','material']
                    if owner=='brick':
                        required(common+[a+'range' for a in 'xyz'])
                        resolved={a:vector(a+'range','bounds_mm.'+a) for a in 'xyz'}
                        if any(Decimal(bounds[0])>=Decimal(bounds[1]) for bounds in resolved.values()): failure('invalid-brick-dimensions','malformed')
                    elif owner=='cylinder':
                        if 'axis' not in props: failure('geometry-axis-missing')
                        axis=string(props['axis'])
                        if axis not in 'xyz' or len(axis)!=1: failure('geometry-axis-unsupported')
                        transverse=[a for a in 'xyz' if a!=axis]
                        required(common+['axis','outerradius','innerradius','segments',axis+'range']+[a+'center' for a in transverse])
                        fixed(props['segments'],0)
                        bounds=vector(axis+'range','axial_range_mm')
                        outer=num('outerradius','outer_radius_mm');inner=num('innerradius','inner_radius_mm')
                        if not 0<=inner<outer or Decimal(bounds[0])>=Decimal(bounds[1]): failure('invalid-cylinder-dimensions','malformed')
                        resolved=dict(axis=axis,axial_range_mm=bounds,outer_radius_mm=str(outer),inner_radius_mm=str(inner),
                            transverse_center_mm=[str(num(a+'center','transverse_center_mm['+str(i)+']')) for i,a in enumerate(transverse)])
                    else:
                        required(common+['axis','centerradius','topradius','bottomradius','center','segments'])
                        if string(props['axis'])!='z': failure('geometry-full-sphere-axis')
                        for key in ('topradius','bottomradius','segments'): fixed(props[key],0)
                        radius=num('centerradius','radius_mm')
                        if radius<=0: failure('invalid-sphere-radius','malformed')
                        resolved=dict(radius_mm=str(radius),center_mm=vector('center','center_mm'))
                    component=string(props['component']);name=string(props['name']);material=string(props['material'])
                    if component not in components or not re.fullmatch(r's_[a-f0-9]{20}',name): failure('geometry-solid-identity')
                    if material not in ('Vacuum','PEC'): failure('geometry-material-unsupported')
                    native=component+':'+name
                    if native in names: failure('geometry-solid-name-reused','ambiguous')
                    names.add(native);objects[native]=dict(state='live',material_id=material)
                    object_origins[native]=MappingProxyType(calls[-1][2][2])
                    feature=dict(op='create_'+owner,native_name=native,material_id=material,resolved=resolved)
            elif owner=='solid' and len(calls)==1:
                _,method,entry=calls[0];location=entry[2]
                target=string(entry);first=live(target)
                if method=='delete':
                    first['state']='deleted';feature=dict(op='delete_object',target_name=target,resolved={})
                    object_origins[target]=MappingProxyType(entry[2])
                elif method in ('add','subtract','intersect'):
                    tool=string(entry,1);second=live(tool)
                    if target==tool or target.split(':')[0]!=tool.split(':')[0] or first['material_id']!=second['material_id']: failure('geometry-boolean-operands')
                    second['state']='consumed'
                    object_origins[target]=MappingProxyType(entry[2]);object_origins[tool]=MappingProxyType(entry[2])
                    feature=dict(op='boolean_solids',target_name=target,tool_name=tool,
                        operation={'add':'union','subtract':'difference','intersect':'intersection'}[method],resolved=dict(result_geometry='unverified'))
                else: failure('geometry-solid-operation')
            else: failure('geometry-block-operation')
            if sum(o['state']=='live' for o in objects.values())>128: failure('geometry-live-solid-budget','rejected')
            features.append(feature);origins[prefix.rstrip('.')]=MappingProxyType(dict(location))
        fields.update({'geometry.features':tuple(features),'geometry.objects':objects})
        origins['geometry.features']=tuple(origins['geometry.features['+str(i)+']'] for i in range(len(features)))
        origins['geometry.objects']=MappingProxyType(object_origins)
        return Projection('resolved',MappingProxyType(fields),MappingProxyType(origins),(),source_hash,scope,
            parser_profile=GEOMETRY_PROFILE,exact_values=MappingProxyType(exact))
    except (ProjectionError,ValueError,TypeError,RecursionError) as error:
        reason=error.reason if isinstance(error,ProjectionError) else 'malformed-geometry-program'
        status=error.status if isinstance(error,ProjectionError) else 'malformed'
        return Projection(status,MappingProxyType({}),MappingProxyType({}),(reason,),source_hash,scope,
            parser_profile=GEOMETRY_PROFILE,failure_origin=MappingProxyType(dict(location)) if location else None)

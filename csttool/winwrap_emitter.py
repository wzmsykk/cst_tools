"""Small WWB-COM emitter for explicitly scoped A1/GEO history, not a compiler.

History commands use settings_projection's sole allowlist. Fixed control-flow
templates remain fixed; caller-provided Basic source is never an expression.
"""
import ast
from dataclasses import dataclass
import re

from .settings_projection import COMMAND_ARITIES, PROFILE, command_arities, history_call_contract, _Arithmetic
from .vb_codec import quote_vb_string


class GeneratedCodeError(ValueError):
    def __init__(self, reason):
        self.code = 'GENERATED_CODE_INVALID'
        self.reason = reason
        super().__init__(self.code + ': ' + reason)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', value):
        raise GeneratedCodeError('invalid identifier: ' + repr(value))
    return value


class Expression:
    def render(self):
        raise NotImplementedError


@dataclass(frozen=True)
class String(Expression):
    value: str

    def render(self):
        if not isinstance(self.value, str) or any(ord(c) < 32 for c in self.value):
            raise GeneratedCodeError('string literal requires a single control-free line')
        return '"' + quote_vb_string(self.value) + '"'


@dataclass(frozen=True)
class Number(Expression):
    token: str

    def render(self):
        if not isinstance(self.token, str) or not re.fullmatch(
                r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', self.token):
            raise GeneratedCodeError('invalid unsigned numeric token')
        return self.token


@dataclass(frozen=True)
class Boolean(Expression):
    value: bool

    def render(self):
        if type(self.value) is not bool:
            raise GeneratedCodeError('Boolean requires bool')
        return 'True' if self.value else 'False'


@dataclass(frozen=True)
class Variable(Expression):
    name: str

    def render(self):
        return identifier(self.name)


@dataclass(frozen=True)
class Property(Expression):
    object: str
    member: str

    def render(self):
        return identifier(self.object) + '.' + identifier(self.member)


@dataclass(frozen=True)
class Element(Expression):
    name: str
    index: int

    def render(self):
        if type(self.index) is not int or self.index < 0:
            raise GeneratedCodeError('invalid array index')
        return identifier(self.name) + '(' + str(self.index) + ')'


def expression(value):
    if not isinstance(value, Expression):
        raise GeneratedCodeError('typed expression required, raw source is forbidden')
    return value.render()


@dataclass(frozen=True)
class Function(Expression):
    name: str
    arguments: tuple = ()

    def render(self):
        return identifier(self.name) + '(' + ', '.join(expression(a) for a in self.arguments) + ')'


@dataclass(frozen=True)
class Unary(Expression):
    operator: str
    operand: Expression

    def render(self):
        if self.operator not in ('+', '-'):
            raise GeneratedCodeError('unsupported unary operator')
        return '(' + self.operator + expression(self.operand) + ')'


@dataclass(frozen=True)
class Binary(Expression):
    left: Expression
    operator: str
    right: Expression

    def render(self):
        if self.operator not in ('+', '-', '*', '/', '^', '&'):
            raise GeneratedCodeError('unsupported binary operator')
        return '(' + expression(self.left) + self.operator + expression(self.right) + ')'


@dataclass(frozen=True)
class Arithmetic(Expression):
    """History expression with parameter references, never substituted values."""
    value: Expression

    def render(self):
        # Retain the calibrated bare-Sub argument shape until Call execution and
        # replay, not just syntax, have independent evidence for all consumers.
        return '0+' + expression(self.value)


def arithmetic(text, parameters):
    """Use the shared bounded arithmetic rules before lowering its AST."""
    _Arithmetic([dict(name=k, expr=v['expression']) for k, v in parameters.items()]).expression(text)
    source = text.replace('^', '**').strip()
    names = {name.casefold(): name for name in parameters}

    def lower(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Number(ast.get_source_segment(source, node))
        if isinstance(node, ast.Name):
            return Function('RestoreDoubleParameter', (String(names[node.id.casefold()]),))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return Unary('+' if isinstance(node.op, ast.UAdd) else '-', lower(node.operand))
        if isinstance(node, ast.BinOp):
            operators = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/', ast.Pow: '^'}
            if type(node.op) in operators:
                return Binary(lower(node.left), operators[type(node.op)], lower(node.right))
        raise GeneratedCodeError('unsupported A1 arithmetic syntax')

    return Arithmetic(lower(ast.parse(source, mode='eval').body))


@dataclass(frozen=True)
class HistoryCall:
    object: str
    method: str
    arguments: tuple = ()

    def render(self, *, within=None, profile=PROFILE):
        identifier(self.object); identifier(self.method)
        try:
            contract = history_call_contract(self.object, self.method, profile=profile)
        except ValueError as error:
            raise GeneratedCodeError('unsupported history command') from error
        if len(self.arguments) != contract['arity']:
            raise GeneratedCodeError('unsupported history command or arity: ' + self.object + '.' + self.method)
        if within is not None and within.casefold() != self.object.casefold():
            raise GeneratedCodeError('With member belongs to another object')
        name = ('.' if within else '' if self.object.lower() == 'project' else self.object + '.') + self.method
        values = [expression(a) for a in self.arguments]
        if values and values[0].startswith('('):
            raise GeneratedCodeError('bare history statement needs an argument-safe expression')
        return name + (' ' + ', '.join(values) if values else '')


@dataclass(frozen=True)
class SubCall:
    """Owned control-template statement; distinct from a return-value expression."""
    name: str
    arguments: tuple = ()

    def render(self):
        values = [expression(a) for a in self.arguments]
        if values and values[0].startswith('('):
            raise GeneratedCodeError('bare statement needs an explicit argument-safe expression')
        return identifier(self.name) + (' ' + ', '.join(values) if values else '')


def resize_arrays(names, size):
    if type(size) is not int or size < 1 or not names:
        raise GeneratedCodeError('positive array size and typed array names required')
    if any(not isinstance(name, Variable) for name in names):
        raise GeneratedCodeError('array declaration needs typed variable names')
    return 'ReDim ' + ', '.join(name.render() + '(0 To ' + str(size-1) + ')' for name in names)


@dataclass(frozen=True)
class With:
    object: str
    calls: tuple

    def render(self, *, profile=PROFILE):
        identifier(self.object)
        if self.object.lower() == 'project' or not self.calls:
            raise GeneratedCodeError('invalid history With object')
        return ['With ' + self.object, *[' ' + c.render(within=self.object,profile=profile) for c in self.calls], 'End With']


def render_history(nodes, *, profile=PROFILE):
    lines = []
    for node in nodes:
        if isinstance(node, With): lines.extend(node.render(profile=profile))
        elif isinstance(node, HistoryCall): lines.append(node.render(profile=profile))
        else: raise GeneratedCodeError('typed history statement required')
    check_lines(lines)
    return '\n'.join(lines)


def check_lines(lines, limit=800):
    """Conservative project budget, not a measured WinWrap language limit."""
    if any('\n' in line or '\r' in line or len(line) > limit for line in lines):
        raise GeneratedCodeError('physical-line-budget exceeded')


# Fixed template globals, local declarations and injected ownership helpers.
# Not advertised as an exhaustive list of all WinWrap/CST reserved names.
TEMPLATE_SYMBOLS = ('Main', 'ReportStage', 'names', 'expressions', 'history', 'f', 'message',
                    'value', 'tick', 'CSTToolsCheckCode', 'CSTToolsCheckError',
                    'CSTToolsBindNewProject', 'CSTToolsProcessId', 'CSTToolsBindingSleep',
                    'CSTToolsStage', 'CSTToolsBlockIndex', 'CSTToolsLastApplied', 'CSTToolsCaption')
EXTERNAL_SYMBOLS = tuple(sorted({obj for obj, _ in COMMAND_ARITIES if obj != 'project'})) + (
    'RestoreDoubleParameter', 'StoreParameters', 'SetParameterDescription', 'AddToHistory',
    'ChangeSolverType', 'MacroCheckThis', 'Rebuild', 'SaveAs', 'FreeFile', 'ChrW', 'Err', 'vbObjectError', 'vbCrLf', 'CStr', 'Dir', 'DoEvents')
KEYWORDS = frozenset(('sub', 'function', 'dim', 'as', 'if', 'then', 'else', 'end', 'with',
                      'for', 'next', 'true', 'false', 'nothing', 'private', 'public', 'call',
                      'option', 'explicit', 'byref', 'byval', 'const', 'select', 'case',
                      'do', 'loop', 'while', 'wend', 'on', 'error', 'goto', 'resume', 'exit',
                      'integer', 'long', 'double', 'string', 'boolean', 'errobject'))


class Symbols:
    def __init__(self, parameters=()):
        self.names = set(KEYWORDS)
        for name in parameters: self.reserve(name)

    def reserve(self, name):
        identifier(name)
        key = name.casefold()
        if key in self.names: raise GeneratedCodeError('identifier conflict: ' + name)
        self.names.add(key)
        return name

    def declare(self, name, kind, *, array=False):
        if kind not in ('String', 'Integer', 'Long', 'Double', 'Boolean', 'ErrObject'):
            raise GeneratedCodeError('unsupported declaration type')
        return self.reserve(name) + ('()' if array else '') + ' As ' + kind


def validate_parameter_names(parameters, *, profile=PROFILE):
    base=(*TEMPLATE_SYMBOLS,*EXTERNAL_SYMBOLS)
    extra={obj for obj,_ in command_arities(profile)}-{'project'}-{name.lower() for name in base}
    symbols = Symbols((*base,*sorted(extra)))
    for name in parameters: symbols.reserve(name)


def assign_string(target, value, *, indent='    '):
    """Keep existing 24-character Unicode-safe chunks, without continuations."""
    if not isinstance(target, (Variable, Element)) or not isinstance(value, str):
        raise GeneratedCodeError('typed assignment target and string required')
    name = target.render()
    lines = [indent + name + ' = ""']
    for row, line in enumerate(value.split('\n')):
        if row: lines.append(indent + name + ' = ' + name + ' & vbCrLf')
        for index in range(0, len(line), 24):
            lines.append(indent + name + ' = ' + name + ' & ' + String(line[index:index+24]).render())
    check_lines(lines)
    return lines

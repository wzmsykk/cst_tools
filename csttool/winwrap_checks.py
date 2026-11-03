"""Independent A1 lexical/structural checks and versioned native gate.

Not a WinWrap compiler: unknown statements are rejected in this fixed profile.
The native gate is a local build contract, not a signature/trust mechanism.
"""
import hashlib
import json
from pathlib import Path
import re

from .settings_projection import COMMAND_ARITIES
from .winwrap_emitter import GeneratedCodeError

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'cst-2022-a1-sub-w23-v1'
SOURCES = ('csttool/definition_editing.py', 'csttool/winwrap_emitter.py',
           'csttool/winwrap_checks.py', 'csttool/settings_projection.py',
           'csttool/vb_codec.py', 'csttool/native_definition_builder.py',
           'data/first_stage_contract.schema.json')


def generator_fingerprint():
    return {name: hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for name in SOURCES}


def invalid(layer, line, reason):
    error = GeneratedCodeError(f'{layer} line {line}: {reason}')
    error.layer, error.line_1based = layer, line
    raise error


def lexical_line(raw, layer, number):
    """Mask escaped string literals, preserving positions for diagnostics."""
    if len(raw) > 800 or any(ord(c) < 32 for c in raw):
        invalid(layer, number, 'physical-line-budget or control character')
    result, depth, i = [], 0, 0
    while i < len(raw):
        char = raw[i]
        if char == "'":
            break
        if char == '"':
            start = i; i += 1
            while i < len(raw):
                if raw[i] == '"':
                    i += 1
                    if i < len(raw) and raw[i] == '"': i += 1; continue
                    break
                i += 1
            else: invalid(layer, number, 'unterminated string')
            result.append('@' + ' '*(i-start-1)); continue
        if char == '(': depth += 1
        if char == ')':
            depth -= 1
            if depth < 0: invalid(layer, number, 'unbalanced parentheses')
        if char == ':': invalid(layer, number, 'multiple statements are outside profile')
        result.append(char); i += 1
    if depth: invalid(layer, number, 'unbalanced parentheses')
    code = ''.join(result).strip()
    if code.endswith('_'): invalid(layer, number, 'continuations are outside generated profile')
    return code


def arguments(code):
    if not code.strip(): return []
    result, start, depth = [], 0, 0
    for index, char in enumerate(code):
        if char == '(': depth += 1
        elif char == ')': depth -= 1
        elif char == ',' and depth == 0:
            result.append(code[start:index].strip()); start = index+1
    return [*result, code[start:].strip()]


def check_history(source):
    """Independent syntax shape; the existing projector checks setting meaning."""
    stack = []; rows = []
    for number, raw in enumerate(source.splitlines(), 1):
        code = lexical_line(raw, 'history', number)
        if not code: continue
        if match := re.fullmatch(r'With ([A-Za-z][A-Za-z0-9_]*)', code, re.I):
            if stack: invalid('history', number, 'nested With is outside profile')
            stack.append(match[1]); continue
        if code.casefold() == 'end with':
            if not stack: invalid('history', number, 'unmatched End With')
            stack.pop(); continue
        match = re.fullmatch(r'(?:(\.?[A-Za-z][A-Za-z0-9_]*)(?:\.([A-Za-z][A-Za-z0-9_]*))?)(?:\s+(.*))?', code)
        if not match: invalid('history', number, 'unknown statement')
        head, member, tail = match.groups()
        if head.startswith('.'):
            if not stack or member: invalid('history', number, 'unbound With member')
            obj, method = stack[-1], head[1:]
        elif member: obj, method = head, member
        else: obj, method = 'project', head
        args = arguments(tail or '')
        if COMMAND_ARITIES.get((obj.lower(), method.lower())) != len(args) or any(not a for a in args):
            invalid('history', number, 'unknown command or argument count')
        if args and args[0].startswith('('):
            invalid('history', number, 'unsafe bare first argument (original Zrange shape)')
        # Inputs are constants/arithmetic and RestoreDoubleParameter/CInt only.
        for arg in args:
            tokens = re.findall(r'[A-Za-z][A-Za-z0-9_]*', re.sub(r'[0-9.]+[eE][+-]?[0-9]+', '0', arg))
            if any(t.casefold() not in {'restoredoubleparameter','cint','true','false'} for t in tokens):
                invalid('history', number, 'unknown expression identifier')
        rows.append(dict(line=number, object=obj, method=method, statement=raw))
    if stack: invalid('history', len(source.splitlines()), 'missing End With')
    if not rows: invalid('history', 1, 'empty history')
    return rows


def check_module(source, parameters=()):
    """Recognize only the generated edit module before ownership injection."""
    if not source.startswith('\'#Language "WWB-COM"\n'):
        invalid('outer-macro', 1, 'WWB-COM language header required')
    procedures, local, current, blocks, options, labels = set(), set(), None, [], 0, set()
    host = {p.casefold() for p in parameters}
    words = {'as','byval','byref','string','integer','double','long','boolean','errobject',
             'true','false','nothing','if','then','not','or','and','end','set','for','output',
             'open','close','print','exit','sub','on','error','goto','resume','next','failed',
             'err','raise','number','description','source','vbobjecterror','vbcrlf','vbtab',
             'cstr','chrw','freefile','addtohistory','rebuild','saveas','storeparameters',
             'setparameterdescription','reportstage','macrocheckthis','is','redim','to'}
    for number, raw in enumerate(source.splitlines(), 1):
        if raw.strip() == 'Failed:':
            if current != 'main' or 'failed' in labels: invalid('outer-macro', number, 'unexpected/duplicate label')
            labels.add('failed')
            continue
        code = lexical_line(raw, 'outer-macro', number)
        if not code: continue
        lower = code.casefold()
        if lower == 'option explicit':
            if current or procedures: invalid('outer-macro',number,'Option outside module header')
            options += 1; continue
        if match := re.fullmatch(r'(?:Private )?Sub (\w+)(?:\((.*)\))?', code, re.I):
            name = match[1].casefold()
            if current or name in procedures or name not in {'main','reportstage'}:
                invalid('outer-macro', number, 'unknown/duplicate/nested procedure')
            procedures.add(name); current=name; local=set()
            declarations = [match[2]] if match[2] else []
        elif lower == 'end sub':
            if not current or blocks: invalid('outer-macro', number, 'unbalanced procedure/block')
            current = None; continue
        else:
            if not current: invalid('outer-macro', number, 'statement outside procedure')
            declarations = arguments(code[4:]) if lower.startswith('dim ') else []
        if declarations:
            for declaration in declarations:
                match = re.fullmatch(r'(?:ByVal |ByRef )?(\w+)(?:\(\))? As (String|Integer|Long|Double|Boolean|ErrObject)', declaration, re.I)
                if not match or match[1].casefold() in local | host:
                    invalid('outer-macro', number, 'invalid/duplicate/host-conflicting declaration')
                local.add(match[1].casefold())
            continue
        if re.match(r'(?:Private )?Sub ', code, re.I): continue
        if lower == 'end if':
            if not blocks: invalid('outer-macro', number, 'unmatched End If')
            blocks.pop(); continue
        if lower.startswith('if '):
            if not re.search(r'\bThen\b', code, re.I): invalid('outer-macro', number, 'If missing Then')
            if lower.endswith(' then'): blocks.append('if')
        elif not re.match(r'(?:On Error (?:GoTo Failed|Resume Next)|Close(?:\s|$)|Print #|Open |Exit Sub$|ReportStage |Err\.Raise |StoreParameters\(|SetParameterDescription |SaveAs |ReDim |(?:Set )?\w+(?:\([0-9]+\))?\s*=)', code, re.I):
            invalid('outer-macro', number, 'unknown statement')
        for token in re.findall(r'[A-Za-z][A-Za-z0-9_]*', code):
            if token.casefold() not in words | local:
                invalid('outer-macro', number, 'unknown identifier: '+token)
    if current or blocks or options != 1 or procedures != {'main','reportstage'} or labels != {'failed'}:
        invalid('outer-macro', len(source.splitlines()), 'missing/duplicate module structure')


def input_field(obj, method):
    obj, method = obj.lower(), method.lower()
    if obj == 'cylinder':
        if method.endswith('range'): return 'cylinder.axial_range'
        return 'cylinder.'+{'outerradius':'outer_radius','name':'object_id','component':'component_id'}.get(method, method)
    return {'units':'units','project':'simulation.solver','background':'background','boundary':'boundaries',
            'component':'components','wcs':'coordinate_system','solver':'simulation.frequency_range_mhz',
            'mesh':'simulation.mesh','meshsettings':'simulation.mesh','eigenmodesolver':'simulation'}.get(obj,obj)


def history_locations(history):
    """Tolerant diagnostic locations, never an acceptance/interpretation result."""
    obj=None; rows=[]
    for number,raw in enumerate(history.splitlines(),1):
        if match:=re.fullmatch(r'\s*With (\w+)\s*',raw,re.I): obj=match[1]; continue
        if raw.strip().casefold()=='end with': obj=None; continue
        match=re.match(r'\s*(?:(\w+)\.)?(\.?\w+)',raw)
        if not match:continue
        owner=match[1] or (obj if match[2].startswith('.') else 'project') or 'unknown'
        method=match[2].lstrip('.')
        rows.append(dict(line=number,object=owner,method=method,statement=raw))
    return rows


def definition_map(spec, history, macro):
    from .winwrap_emitter import assign_string, Variable, Element
    rows=history_locations(history)
    result={'schema_version':1,'history':[{**r,'input_field':input_field(r['object'],r['method']),
        'implementation':'csttool.definition_editing.render_history'} for r in rows], 'outer':[]}
    cursor=0
    def locate(lines, field, history_lines=None):
        nonlocal cursor
        block='\n'.join(lines); position=macro.find(block,cursor)
        if position<0: raise GeneratedCodeError('source map block missing')
        start=macro.count('\n',0,position)+1; cursor=position+len(block)
        result['outer'].append(dict(line_start=start,line_end=start+len(lines)-1,input_field=field,
            history_lines=history_lines,implementation='csttool.definition_editing.render_edit_macro'))
    for index,(name,row) in enumerate(spec['parameters'].items()):
        locate(assign_string(Element('names',index),name),'parameters.'+name+'.name')
        locate(assign_string(Element('expressions',index),row['expression']),'parameters.'+name+'.expression')
    for name,row in spec['parameters'].items(): locate(assign_string(Variable('message'),row['description']),'parameters.'+name+'.description')
    lines=assign_string(Variable('history'),history)
    position=macro.find('\n'.join(lines),cursor)
    if position<0: raise GeneratedCodeError('history source map block missing')
    outer_line=macro.count('\n',0,position)+2
    for number,line in enumerate(history.split('\n'),1):
        count=(len(line)+23)//24 + (1 if number>1 else 0)
        row=next((r for r in result['history'] if r['line']==number),None)
        result['outer'].append(dict(line_start=outer_line,line_end=outer_line+count-1,
            history_lines=[number],input_field=row['input_field'] if row else 'history.block',
            implementation='csttool.definition_editing.render_history'))
        outer_line+=count
    result['history_check_wrapper_lines']=3
    result['hashes']={name:hashlib.sha256(code.encode('ascii')).hexdigest() for name,code in [('history',history),('outer',macro)]}
    return result


def map_native_error(raw, mapping):
    rows=raw.splitlines(); source='\n'.join(rows[2:]).rstrip()
    match=re.fullmatch(r'\[(?P<module>[^\]\r\n]+)#(?P<line>\d+)\] (?P<statement>.*)',source)
    line=int(match['line'])-mapping['history_check_wrapper_lines'] if match else None
    origin=next((r for r in mapping['history'] if r['line']==line),None)
    return dict(layer='history',raw=raw,source=source,wrapped_line_1based=int(match['line']) if match else None,
                history_line_1based=line,origin=origin,column=None)


def check_calibration(record, fingerprint):
    if (not isinstance(record,dict) or record.get('profile')!=PROFILE or record.get('accepted') is not True
            or record.get('sources')!=fingerprint or type(record.get('solver_start_calls')) is not int
            or record.get('solver_start_calls')!=0
            or record.get('axes')!=['x','y','z'] or record.get('standard_closed') is not True):
        raise GeneratedCodeError('native calibration missing/stale; run the owned W3 acceptance, do not retry simulation')


# Capture this checker epoch and reject subsequent disk edits; hot reload is unsupported.
LOADED_SOURCES = generator_fingerprint()


def require_calibration():
    current=generator_fingerprint()
    if current!=LOADED_SOURCES: raise GeneratedCodeError('generator changed in running process; restart after calibration')
    try:
        path=ROOT/'data/winwrap-a1-calibration.json'
        if path.stat().st_size>1024*1024: raise ValueError('calibration budget')
        record=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:
        raise GeneratedCodeError('native calibration unavailable') from error
    check_calibration(record,current)
    try:
        name=record.get('evidence_file','')
        if not re.fullmatch(r'knowledge-base/winwrap-w23-[0-9]{8}\.json',name):
            raise ValueError('invalid calibration evidence location')
        evidence_path=(ROOT/name).resolve()
        if not evidence_path.is_relative_to((ROOT/'knowledge-base').resolve()):
            raise ValueError('evidence escapes knowledge base')
        if evidence_path.stat().st_size>1024*1024: raise ValueError('evidence budget')
        evidence=json.loads(evidence_path.read_text(encoding='utf-8'))['native_acceptance']
        digest=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        if digest!=record.get('evidence_sha256') or evidence['sources']!=current or evidence['accepted'] is not True:
            raise ValueError('evidence mismatch')
    except (OSError,ValueError,KeyError,TypeError) as error:
        raise GeneratedCodeError('native calibration evidence missing/changed') from error
    return record

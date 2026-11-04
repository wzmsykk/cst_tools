"""Independent scoped A1/GEO checks and the versioned A1 native gate.

Not a WinWrap compiler: unknown statements are rejected in this fixed profile.
The native gate is a local build contract, not a signature/trust mechanism.
"""
import hashlib
import json
from pathlib import Path
import re

from .settings_projection import COMMAND_ARITIES, PROFILE as HISTORY_PROFILE, GEOMETRY_PROFILE, command_arities
from .winwrap_emitter import GeneratedCodeError

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'cst-2022-a1-sub-w23-v1'
SOURCES = ('csttool/definition_editing.py', 'csttool/winwrap_emitter.py',
           'csttool/winwrap_checks.py', 'csttool/settings_projection.py',
           'csttool/vb_codec.py', 'csttool/native_definition_builder.py',
           'data/first_stage_contract.schema.json','csttool/geometry_contract.py',
           'csttool/geometry_codegen.py','csttool/history_program.py',
           'csttool/managed_history.py','csttool/definition_geometry.py',
           'csttool/definition_verifier.py','csttool/application_service.py','csttool/result_provenance.py',
           'csttool/definition_sessions.py')


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


def check_history(source, *, profile=HISTORY_PROFILE):
    """Independent syntax shape; the existing projector checks setting meaning."""
    try: commands=command_arities(profile)
    except ValueError: invalid('history',1,'unknown history profile')
    if not isinstance(source,str): invalid('history',1,'history string required')
    try:size=len(source.encode('utf-8'))
    except UnicodeError: invalid('history',1,'invalid UTF-8 history text')
    if size>2*1024*1024:
        invalid('history',1,'history budget exceeded')
    stack = []; rows = []
    for number, raw in enumerate(source.splitlines(), 1):
        code = lexical_line(raw, 'history', number)
        if not code: continue
        if match := re.fullmatch(r'With ([A-Za-z][A-Za-z0-9_]*)', code, re.I):
            if stack: invalid('history', number, 'nested With is outside profile')
            if match[1].lower() not in {key[0] for key in commands} - {'project'}:
                invalid('history',number,'unknown With object')
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
        if commands.get((obj.lower(), method.lower())) != len(args) or any(not a for a in args):
            invalid('history', number, 'unknown command or argument count')
        if args and args[0].startswith('('):
            invalid('history', number, 'unsafe bare first argument (original Zrange shape)')
        # Inputs are constants/arithmetic and RestoreDoubleParameter/CInt only.
        for arg in args:
            tokens = re.findall(r'[A-Za-z][A-Za-z0-9_]*', re.sub(r'[0-9.]+[eE][+-]?[0-9]+', '0', arg))
            if any(t.casefold() not in {'restoredoubleparameter','cint','true','false'} for t in tokens):
                invalid('history', number, 'unknown expression identifier')
        if len(rows)>=20000: invalid('history',number,'statement budget exceeded')
        rows.append(dict(line=number, object=obj, method=method, statement=raw))
    if stack: invalid('history', len(source.splitlines()), 'missing End With')
    if not rows: invalid('history', 1, 'empty history')
    return rows


def check_module(source, parameters=(), *, profile=HISTORY_PROFILE):
    """Recognize only the generated edit module before ownership injection."""
    if profile not in (HISTORY_PROFILE,GEOMETRY_PROFILE): invalid('outer-macro',1,'unknown module profile')
    if not source.startswith('\'#Language "WWB-COM"\n'):
        invalid('outer-macro', 1, 'WWB-COM language header required')
    procedures, local, current, blocks, options, labels = set(), set(), None, [], 0, set()
    host = {p.casefold() for p in parameters}
    words = {'as','byval','byref','string','integer','double','long','boolean','errobject',
             'true','false','nothing','if','then','not','or','and','end','set','for','output',
             'open','close','print','exit','sub','on','error','goto','resume','next','failed',
             'err','raise','number','description','source','vbobjecterror','vbcrlf','vbtab',
             'cstr','chrw','freefile','addtohistory','rebuild','saveas','storeparameters',
             'setparameterdescription','reportstage','macrocheckthis','is','redim','to','dir'}
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
    checks=[m.start() for m in re.finditer(r'Set CSTToolsCheckError = MacroCheckThis\(CSTToolsCheckCode\)',source)]
    guards=[m.start() for m in re.finditer(r'If Not CSTToolsCheckError Is Nothing Then',source)]
    adds=list(re.finditer(r'If Not AddToHistory\("([^"\r\n]+)", history\) Then Err\.Raise',source))
    if not adds or len(checks)!=len(adds) or len(guards)!=len(adds):
        invalid('outer-macro',1,'every history block requires its own check and error guard')
    for index,entry in enumerate(adds):
        if not (checks[index]<guards[index]<entry.start() and (index==0 or adds[index-1].start()<checks[index])):
            invalid('outer-macro',1,'history check/apply order is invalid')
    captions=[entry[1] for entry in adds]
    if profile==HISTORY_PROFILE and captions!=['CST Tools A1 typed definition']:
        expected=['units','solver-family','background','boundaries','wcs']
        if (len(captions)<10 or captions[:5]!=['CST Tools A1 '+s for s in expected]
                or captions[-5:]!=['CST Tools A1 '+s for s in ('geometry-cylinder','solver-context','frequency','mesh-density','modes')]
                or any(not re.fullmatch(r'CST Tools A1 component-[A-Za-z][A-Za-z0-9_-]*',s) for s in captions[5:-5])
                or len(set(captions))!=len(captions)):
            invalid('outer-macro',1,'A1 functional block identities/order differ')
    if profile==GEOMETRY_PROFILE:
        if len(captions)>560 or len(set(captions))!=len(captions):invalid('outer-macro',1,'invalid GEO block identities')
        if captions[0]=='CST Tools GEO setup':
            if any(not re.fullmatch(r'CST Tools GEO f_[a-f0-9]{32}',s) for s in captions[1:]):invalid('outer-macro',1,'invalid GEO identities')
        else:
            if captions[:2]!=['CST Tools GEO units','CST Tools GEO wcs']:invalid('outer-macro',1,'missing GEO environment blocks')
            started=False
            sim_start=next((i for i,c in enumerate(captions) if c.startswith('CST Tools SIM ')),len(captions))
            if sim_start<len(captions) and captions[sim_start:]!=['CST Tools SIM '+s for s in ('solver-family','background','boundaries','solver-context','frequency','mesh-density','modes')]:
                invalid('outer-macro',1,'invalid GEO simulation group order')
            for caption in captions[2:sim_start]:
                if re.fullmatch(r'CST Tools GEO f_[a-f0-9]{32}',caption):started=True
                elif started or not re.fullmatch(r'CST Tools GEO component-c_[a-f0-9]{20}',caption):invalid('outer-macro',1,'invalid GEO functional order')
    stores=[m.start() for m in re.finditer(r'^    StoreParameters\(names, expressions\)$',source,re.M)]
    descriptions=[m.start() for m in re.finditer(r'^    SetParameterDescription ',source,re.M)]
    rebuild=list(re.finditer(r'^    If Not Rebuild Then ',source,re.M))
    save=list(re.finditer(r'^    SaveAs ',source,re.M))
    if (len(stores)>1 or any(pos>checks[0] for pos in stores+descriptions) or
            len(rebuild)!=1 or len(save)!=1 or not adds[-1].start()<rebuild[0].start()<save[0].start()):
        invalid('outer-macro',1,'parameter/history/rebuild/save phase order is invalid')


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


def geometry_definition_map(spec, blocks, macro=None):
    """Bind GEO bodies and assignments; optionally locate the shared full macro."""
    from .geometry_codegen import validate_geometry_history
    from .winwrap_emitter import assign_string, Variable
    validate_geometry_history(spec,blocks)
    result=dict(schema_version=2,profile=GEOMETRY_PROFILE,history=[],outer=[],block_hashes=[],
        history_check_wrapper_lines=3,outer_kind='assign_string fragments; no executable macro',
        spec_sha256=hashlib.sha256(json.dumps(spec,sort_keys=True,allow_nan=False).encode()).hexdigest(),
        program_sha256=hashlib.sha256(json.dumps(blocks,sort_keys=True,allow_nan=False).encode()).hexdigest())
    for block_index,block in enumerate(blocks):
        feature=spec['geometry']['features'][block_index-1] if block_index else None
        prefix='geometry.features['+str(block_index-1)+']' if feature else ''
        positions={r['line']:r for r in history_locations(block['history'])}
        component_index=0; cursor=2
        for line,text in enumerate(block['history'].splitlines(),1):
            entry=positions.get(line,{})
            obj,method=entry.get('object',''),entry.get('method','').lower()
            paths=[]
            if feature:
                field={'name':'object_id' if feature['op'].startswith('create_') else 'target_id',
                    'component':'component_id','material':'material_id','axis':'axis','centerradius':'radius_mm',
                    'center':'center_mm','outerradius':'outer_radius_mm','innerradius':'inner_radius_mm','vector':'translation_mm'}.get(method)
                if method=='axis' and feature['op']!='create_cylinder':field=None  # Fixed full-sphere profile setting.
                if method.endswith('range'):
                    field='bounds_mm.'+method[0] if feature['op']=='create_brick' else 'axial_range_mm'
                if method.endswith('center') and feature['op']=='create_cylinder':
                    transverse=[a for a in 'xyz' if a!=feature['axis']]
                    if method[0] in transverse: field='transverse_center_mm['+str(transverse.index(method[0]))+']'
                if obj.lower()=='solid':
                    paths=[prefix+'.object_id'] if method=='delete' else [prefix+'.target_id',prefix+'.tool_id',prefix+'.operation']
                if not paths:paths=[prefix+('.'+field if field else '')]
            elif obj.lower()=='units':paths=['units.length']
            elif obj.lower()=='wcs':paths=['coordinate_system']
            elif obj.lower()=='component':
                paths=['components['+str(component_index)+']'];component_index+=1
            else:paths=['geometry.setup']
            row=dict(line=line,block_index=block_index,caption=block['caption'],feature_id=feature['feature_id'] if feature else None,
                input_field=paths[0],input_fields=paths,statement=text,object=obj,method=entry.get('method'),
                implementation='csttool.geometry_codegen.render_geometry_history')
            result['history'].append(row)
            count=(len(text)+23)//24+(1 if line>1 else 0)
            result['outer'].append(dict(block_index=block_index,line_start=cursor,line_end=cursor+count-1,
                history_lines=[line],input_field=paths[0],feature_id=row['feature_id'],
                implementation='csttool.winwrap_emitter.assign_string'))
            cursor+=count
        assignment='\n'.join(assign_string(Variable('history'),block['history']))
        result['block_hashes'].append(dict(caption=block['caption'],history_sha256=hashlib.sha256(block['history'].encode('ascii')).hexdigest(),
            assignment_sha256=hashlib.sha256(assignment.encode('ascii')).hexdigest()))
    if macro is not None:
        check_module(macro,spec['parameters'],profile=GEOMETRY_PROFILE)
        fragments=result['outer'];result['assignment_outer']=fragments;result['outer']=[]
        cursor=0
        def locate(lines,field):
            nonlocal cursor
            position=macro.find('\n'.join(lines),cursor)
            if position<0: raise GeneratedCodeError('GEO macro assignment source mismatch')
            first=macro.count('\n',0,position)+1;cursor=position+len('\n'.join(lines))
            result['outer'].append(dict(line_start=first,line_end=first+len(lines)-1,input_field=field,
                history_lines=None,implementation='csttool.definition_editing.render_edit_macro'))
        from .winwrap_emitter import Element
        for index,(name,row) in enumerate(spec['parameters'].items()):
            locate(assign_string(Element('names',index),name),'parameters.'+name+'.name')
            locate(assign_string(Element('expressions',index),row['expression']),'parameters.'+name+'.expression')
        for name,row in spec['parameters'].items():locate(assign_string(Variable('message'),row['description']),'parameters.'+name+'.description')
        for block_index,block in enumerate(blocks):
            assignment='\n'.join(assign_string(Variable('history'),block['history']))
            position=macro.find(assignment,cursor)
            if position<0:raise GeneratedCodeError('GEO macro history assignment source mismatch')
            offset=macro.count('\n',0,position);cursor=position+len(assignment)
            for row in fragments:
                if row['block_index']==block_index:
                    result['outer'].append({**row,'line_start':row['line_start']+offset,'line_end':row['line_end']+offset})
        result['outer_kind']='shared executable definition macro; before ownership injection'
        result['hashes']=dict(outer=hashlib.sha256(macro.encode('ascii')).hexdigest())
    return result


def execution_definition_map(spec,program,macro):
    """Map physical functional blocks/parameters to the complete shared macro."""
    from .history_program import validate
    from .winwrap_emitter import assign_string,Variable,Element
    import json
    # Diagnostic source binding, not permission to run. Preparation validates
    # the typed program separately; trusted calibration must also map rejected
    # inner syntax, just as the existing tolerant history locator does.
    profile=GEOMETRY_PROFILE if 'geometry' in spec else HISTORY_PROFILE
    check_module(macro,spec['parameters'],profile=profile)
    result=dict(schema_version=2,profile=profile,history=[],outer=[],block_hashes=[],
        history_check_wrapper_lines=3,outer_kind='shared executable definition macro; before ownership injection',
        spec_sha256=hashlib.sha256(json.dumps(spec,sort_keys=True,allow_nan=False).encode()).hexdigest(),
        program_sha256=hashlib.sha256(json.dumps(program,sort_keys=True,allow_nan=False).encode()).hexdigest(),
        hashes=dict(outer=hashlib.sha256(macro.encode('ascii')).hexdigest()))
    features={'CST Tools GEO '+f['feature_id']:i for i,f in enumerate(spec.get('geometry',{}).get('features',[]))}
    cursor=0
    def locate(lines,field):
        nonlocal cursor
        text='\n'.join(lines);position=macro.find(text,cursor)
        if position<0:raise GeneratedCodeError('execution macro payload/source map differs')
        first=macro.count('\n',0,position)+1;cursor=position+len(text)
        result['outer'].append(dict(line_start=first,line_end=first+len(lines)-1,input_field=field,
            history_lines=None,implementation='csttool.definition_editing.render_edit_macro'))
        return first
    for i,(name,row) in enumerate(spec['parameters'].items()):
        locate(assign_string(Element('names',i),name),'parameters.'+name+'.name')
        locate(assign_string(Element('expressions',i),row['expression']),'parameters.'+name+'.expression')
    for name,row in spec['parameters'].items():locate(assign_string(Variable('message'),row['description']),'parameters.'+name+'.description')
    for index,block in enumerate(program):
        feature_index=features.get(block['caption']);field='geometry.features['+str(feature_index)+']' if feature_index is not None else block['caption'].removeprefix('CST Tools ').replace(' ','.')
        lines=assign_string(Variable('history'),block['history']);start=locate(lines,field)
        positions={r['line']:r for r in history_locations(block['history'])}
        offset=1
        for line,statement in enumerate(block['history'].splitlines(),1):
            count=(len(statement)+23)//24+(1 if line>1 else 0)
            location=positions.get(line,{})
            row_field=field if 'geometry' in spec else input_field(location.get('object',''),location.get('method',''))
            result['history'].append(dict(block_index=index,caption=block['caption'],line=line,statement=statement,
                feature_id=spec['geometry']['features'][feature_index]['feature_id'] if feature_index is not None else None,
                input_field=row_field,object=location.get('object'),method=location.get('method'),
                implementation='csttool.history_program.partition'))
            result['outer'].append(dict(block_index=index,line_start=start+offset,line_end=start+offset+count-1,
                history_lines=[line],input_field=field,implementation='csttool.winwrap_emitter.assign_string'))
            offset+=count
        result['block_hashes'].append(dict(caption=block['caption'],history_sha256=hashlib.sha256(block['history'].encode('ascii')).hexdigest()))
    return result


def map_native_error(raw, mapping, *, block_index=None):
    rows=raw.splitlines(); source='\n'.join(rows[2:]).rstrip()
    match=re.fullmatch(r'\[(?P<module>[^\]\r\n]+)#(?P<line>\d+)\] (?P<statement>.*)',source)
    line=int(match['line'])-mapping['history_check_wrapper_lines'] if match else None
    geometry=mapping.get('schema_version')==2
    origin=next((r for r in mapping['history'] if r['line']==line and (not geometry or
        (type(block_index) is int and r.get('block_index')==block_index))),None)
    if geometry and origin and origin['statement'].strip()!=match['statement'].strip(): origin=None
    return dict(layer='history',raw=raw,source=source,wrapped_line_1based=int(match['line']) if match else None,
                history_line_1based=line,origin=origin,column=None,
                **(dict(block_index=block_index,mapping_status='mapped' if origin else 'unresolved') if geometry else {}))


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


GEO_NATIVE_PROFILE='cst-2022-managed-geometry-v1'


def require_geometry_calibration(target='geometry'):
    """Independent source/evidence binding; A1 stamps never authorize GEO."""
    if target not in ('geometry','simulation'):raise GeneratedCodeError('unknown GEO validation target')
    current=generator_fingerprint()
    if current!=LOADED_SOURCES:raise GeneratedCodeError('generator changed in running process; restart after calibration')
    try:
        path=ROOT/'data/geometry-calibration.json'
        if path.stat().st_size>1024*1024:raise ValueError('GEO calibration budget')
        record=json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(record,dict) or record.get('profile')!=GEO_NATIVE_PROFILE or record.get('accepted') is not True
                or record.get('sources')!=current or not isinstance(record.get('targets'),list)
                or not all(t in ('geometry','simulation') for t in record['targets']) or target not in record['targets']):
            raise ValueError('GEO calibration missing/stale/target not accepted')
        name=record.get('evidence_file','')
        if not re.fullmatch(r'knowledge-base/geometry-calibration-[0-9]{8}\.json',name):raise ValueError('GEO evidence path')
        evidence_path=ROOT/name
        if evidence_path.stat().st_size>2*1024*1024:raise ValueError('GEO evidence budget')
        evidence=json.loads(evidence_path.read_text(encoding='utf-8'))
        digest=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        if not isinstance(evidence,dict):raise ValueError('GEO evidence object required')
        cases=evidence.get('cases',{})
        if not isinstance(cases,dict) or any(not isinstance(c,dict) for c in cases.values()):raise ValueError('GEO case objects required')
        if (digest!=record.get('evidence_sha256') or evidence.get('sources')!=current
                or any(cases.get(key,{}).get('status')!='verified' for key in ('C1','C2','C3','C4','C5','C6','C7'))
                or (target=='simulation' and cases.get('GEO-4',{}).get('status')!='verified')):
            raise ValueError('GEO source/evidence/matrix differs')
        return record
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise GeneratedCodeError('GEO native calibration unavailable: '+str(error)) from error

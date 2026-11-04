"""Owned history block partition/ownership on the existing emitters and projectors.

No native calls, imported-history editing, scheduling or independent model state.
"""
import re
from .settings_projection import PROFILE, GEOMETRY_PROFILE, _statements, _split, _string
from .winwrap_checks import check_history
from .winwrap_emitter import GeneratedCodeError


def units(text):
    """Split a generated body into complete top-level With/statement units."""
    result=[];current=[];inside=False
    for line in text.splitlines():
        code=line.strip()
        if not code:continue
        if code.lower().startswith('with '):
            if inside:raise GeneratedCodeError('nested history context')
            inside=True;current=[line]
        elif code.lower()=='end with':
            if not inside:raise GeneratedCodeError('unbound history context')
            current.append(line);result.append('\n'.join(current));current=[];inside=False
        elif inside:current.append(line)
        else:result.append(line)
    if inside:raise GeneratedCodeError('unterminated history context')
    return result


def calls(text):
    owner=None
    for statement,*_ in _statements(text):
        if statement.lower().startswith('with '):owner=statement[5:].lower();continue
        if statement.lower()=='end with':owner=None;continue
        if statement.startswith('.'):
            if owner is None:raise GeneratedCodeError('unbound block member')
            statement=owner+statement
        match=re.fullmatch(r'([A-Za-z][A-Za-z0-9_]*)(?:\.([A-Za-z][A-Za-z0-9_]*))?\s*(.*)',statement)
        if not match:raise GeneratedCodeError('invalid history command')
        obj,method,tail=match.groups()
        yield (obj.lower() if method else 'project',method.lower() if method else obj.lower(),
               tuple(s.strip() for s in _split(tail,',')) if tail else ())


def _setting(obj,method,args):
    if obj=='eigenmodesolver' and method=='reset':return 'solver.reset'
    if obj=='meshsettings':
        return 'mesh.tet.'+(_string(args[0]).lower() if method=='set' else 'partition')
    return obj+'.'+method


def simulation_blocks(spec):
    """Shared allowlisted settings for the supported GEO eigenmode combination."""
    from .definition_editing import check_geometry_simulation
    from .winwrap_emitter import HistoryCall,With,String,Number,Boolean,render_history
    check_geometry_simulation(spec);sim=spec['simulation']
    def call(obj,method,*args):return HistoryCall(obj,method,args)
    def block(obj,rows):return With(obj,tuple(call(obj,m,*a) for m,a in rows))
    n=lambda value:String(str(value))
    groups=[('solver-family',[call('project','ChangeSolverType',String('HF Eigenmode'))]),
        ('background',[block('Background',[('Type',(String('pec'),))]+[(face+'space',(Number('0'),)) for face in ('Xmin','Xmax','Ymin','Ymax','Zmin','Zmax')])]),
        ('boundaries',[block('Boundary',[(face,(String('electric'),)) for face in ('Xmin','Xmax','Ymin','Ymax','Zmin','Zmax')]+[(a+'symmetry',(String('none'),)) for a in 'XYZ'])]),
        ('solver-context',[call('EigenmodeSolver','Reset'),
            call('EigenmodeSolver','SetMethodType',String('Default'),String('Tet')),
            call('EigenmodeSolver','SetMeshType',String('Tetrahedral Mesh')),
            call('EigenmodeSolver','SetMeshAdaptationTet',Boolean(False)),
            call('EigenmodeSolver','SetConsiderLossesInPostprocessingOnly',Boolean(True))]),
        ('mesh-density',[call('Mesh','MeshType',String('Tetrahedral')),block('MeshSettings',[('SetMeshType',(String('Tet'),)),('Set',(String('Version'),Number('1'))),
            ('Set',(String('StepsPerWaveNear'),n(sim['mesh']['cells_per_wavelength']))),
            ('Set',(String('StepsPerWaveFar'),n(sim['mesh']['cells_per_wavelength']))),
            ('Set',(String('CellsPerWavelengthPolicy'),String('cellsperwavelength')))])]),
        ('frequency',[call('Solver','FrequencyRange',n(sim['frequency_range_mhz']['min']),n(sim['frequency_range_mhz']['max'])),
            call('EigenmodeSolver','SetFrequencyTarget',Boolean(True),n(sim['frequency_lower_target_mhz']))]),
        ('modes',[call('EigenmodeSolver','SetNumberOfModes',Number('1'))])]
    order=('solver-family','background','boundaries','solver-context','frequency','mesh-density','modes')
    by_key=dict(groups)
    return tuple(dict(caption='CST Tools SIM '+key,history=render_history(by_key[key])) for key in order)


def partition(spec):
    """Lower existing typed bodies into minimal complete execution blocks."""
    if 'geometry' in spec:
        from .geometry_codegen import render_geometry_history
        blocks,_=render_geometry_history(spec)
        setup=units(blocks[0]['history']);program=[]
        for index,body in enumerate(setup):
            key='units' if index==0 else 'wcs' if index==1 else 'component-'+_string(next(calls(body))[2][0])
            program.append(dict(caption='CST Tools GEO '+key,history=body))
        program.extend(blocks[1:])
        if 'simulation' in spec:program.extend(simulation_blocks(spec))
    else:
        from .definition_editing import render_history
        text,_=render_history(spec);program=[];context=[];frequency=[];density=[];modes=[]
        for index,body in enumerate(units(text)):
            entries=list(calls(body));obj,method,args=entries[0]
            if obj=='eigenmodesolver':
                for o,m,a in entries:
                    line=o+'.'+m+(' '+', '.join(a) if a else '')
                    (frequency if m=='setfrequencytarget' else modes if m=='setnumberofmodes' else context).append(line)
                continue
            if obj=='solver':frequency.append(body);continue
            if obj=='meshsettings':density.append(body);continue
            if obj=='mesh':density.append(body);continue
            key={'units':'units','project':'solver-family','wcs':'wcs','background':'background',
                 'boundary':'boundaries','cylinder':'geometry-cylinder'}.get(obj)
            if obj=='component':key='component-'+_string(args[0])
            if key is None:raise GeneratedCodeError('unowned A1 functional block')
            program.append(dict(caption='CST Tools A1 '+key,history=body))
        for key,rows in (('solver-context',context),('frequency',frequency),('mesh-density',density),('modes',modes)):
            if not rows:raise GeneratedCodeError('missing A1 functional group '+key)
            program.append(dict(caption='CST Tools A1 '+key,history='\n'.join(rows)))
    validate(program,spec)
    return tuple(program)


def validate(program,spec):
    """Check actual command ownership/order, including implicit reset domains."""
    geometry='geometry' in spec;profile=GEOMETRY_PROFILE if geometry else PROFILE
    if not isinstance(program,(list,tuple)) or not 1<=len(program)<=560:
        raise GeneratedCodeError('history program block budget')
    seen=set();writes={};components=set();facts=set();contracts=[]
    live={};feature_by_caption={'CST Tools GEO '+f['feature_id']:f for f in spec.get('geometry',{}).get('features',[])}
    if geometry:
        from .geometry_contract import project_geometry
        parameter_reads={f['feature_id']:f['parameter_names'] for f in project_geometry(spec)['features']}
    for index,block in enumerate(program):
        if not isinstance(block,dict) or set(block)!={'caption','history'}:raise GeneratedCodeError('invalid history block')
        caption=block['caption']
        if caption in seen:raise GeneratedCodeError('duplicate history block identity')
        seen.add(caption);check_history(block['history'],profile=PROFILE if caption.startswith('CST Tools SIM ') else profile)
        entries=list(calls(block['history']));reads=set();owned=set();outputs=[];consumed=[]
        feature=feature_by_caption.get(caption)
        geometry_block=feature is not None or caption=='CST Tools A1 geometry-cylinder'
        if geometry_block:
            if not {'units','wcs'}<=facts:raise GeneratedCodeError('geometry requires explicit units/global WCS')
            reads.update(('units','wcs'))
            if feature:
                reads.update('parameter:'+name for name in parameter_reads[feature['feature_id']])
                op=feature['op']
                if op.startswith('create_'):
                    from .geometry_contract import native_component_name
                    component=native_component_name(feature['component_id'])
                    if component not in components:raise GeneratedCodeError('component dependency missing')
                    reads.add('component:'+component);oid=feature['object_id'];outputs.append(oid);live[oid]=caption
                else:
                    target=feature['object_id'] if op=='delete_object' else feature['target_id']
                    if target not in live:raise GeneratedCodeError('geometry dependency is forward/missing/consumed')
                    reads.add(live[target])
                    if op=='boolean_solids':
                        tool=feature['tool_id']
                        if tool not in live:raise GeneratedCodeError('boolean tool dependency missing')
                        reads.add(live[tool]);consumed.append(tool);del live[tool]
                    if op=='delete_object':consumed.append(target);del live[target]
                    else:outputs.append(target);live[target]=caption
            else:
                reads.update('parameter:'+name for name in re.findall(r'RestoreDoubleParameter\("([A-Za-z][A-Za-z0-9_]*)"\)',block['history']))
                component=next(_string(a[0]) for o,m,a in entries if m=='component')
                if component not in components:raise GeneratedCodeError('component dependency missing')
                reads.add('component:'+component)
        else:
            for obj,method,args in entries:
                if obj in ('brick','sphere','solid','transform','cylinder'):
                    raise GeneratedCodeError('geometry command outside its declared feature')
                if obj=='component':
                    name=_string(args[0])
                    if name in components:raise GeneratedCodeError('component has multiple creation owners')
                    components.add(name);owned.add('component:'+name);continue
                key=_setting(obj,method,args)
                if obj=='eigenmodesolver' and method=='reset':
                    # Reset affects solver settings even when its immediate text
                    # is different from a later setter. Never append a reset over
                    # another block's established solver configuration.
                    if any(k.startswith('eigenmodesolver.') for k in writes):
                        raise GeneratedCodeError('solver Reset invalidates prior settings')
                elif obj=='eigenmodesolver' and 'solver.reset' not in writes and 'solver.reset' not in owned:
                    raise GeneratedCodeError('solver setting requires initialized context')
                if key in owned or key in writes:raise GeneratedCodeError('setting has multiple owners: '+key)
                owned.add(key)
                if obj=='units':facts.add('units')
                if obj=='wcs':
                    if args!=('"global"',):raise GeneratedCodeError('global WCS is required')
                    facts.add('wcs')
                if obj in ('eigenmodesolver','meshsettings','mesh','solver') and 'solver.reset' in writes:
                    reads.add(writes['solver.reset'])
            # All commands in a functional block have one scope/context; the
            # known solver-context is the only allowed mixed-owner bundle.
            domains={o for o,_,_ in entries}
            if len(domains)>1 and not (caption in ('CST Tools A1 mesh-density','CST Tools SIM mesh-density') and domains<= {'meshsettings','mesh'}):
                # FrequencyRange and FrequencyTarget form one coupled range.
                if not (caption in ('CST Tools A1 frequency','CST Tools SIM frequency') and domains<= {'solver','eigenmodesolver'}):
                    raise GeneratedCodeError('unrelated functions in one block')
        for key in owned:writes[key]=caption
        contracts.append(dict(block_index=index,caption=caption,reads=sorted(reads),writes=sorted(owned),
                              outputs=outputs,consumed=consumed))
    if geometry:
        from .geometry_codegen import validate_geometry_history
        geometry_program=[b for b in program if not b['caption'].startswith('CST Tools SIM ')]
        validate_geometry_history(spec,logical_geometry(geometry_program))
        expected_sim=simulation_blocks(spec) if 'simulation' in spec else ()
        actual_sim=tuple(b for b in program if b['caption'].startswith('CST Tools SIM '))
        if actual_sim!=expected_sim:raise GeneratedCodeError('simulation block completeness/order/value differs')
    else:
        from .settings_projection import project_history
        from .definition_editing import render_history
        actual=project_history('\n'.join(b['history'] for b in program),
            [dict(name=k,expr=v['expression']) for k,v in spec['parameters'].items()],scope='root',available_scopes=('root',),require_identity=True)
        expected=render_history(spec)[1]
        if actual.status!='resolved' or dict(actual.fields)!=dict(expected.fields) or dict(actual.exact_values)!=dict(expected.exact_values):
            raise GeneratedCodeError('partition changed A1 semantics')
    return tuple(contracts)


def logical_geometry(program):
    """Canonical logical setup view for the existing GEO semantic projector.

    This is not arbitrary imported-history folding: only the exact generated
    prefix and immutable per-feature blocks are recognized; duplicates reject.
    """
    prefix=[];features=[];components=set()
    for block in program:
        caption=block['caption']
        if re.fullmatch(r'CST Tools GEO f_[a-f0-9]{32}',caption):features.append(block);continue
        if features:raise GeneratedCodeError('environment block after geometry')
        if len(prefix)==0 and caption=='CST Tools GEO units':pass
        elif len(prefix)==1 and caption=='CST Tools GEO wcs':pass
        elif len(prefix)>=2 and caption.startswith('CST Tools GEO component-'):
            if caption in components:raise GeneratedCodeError('duplicate component block')
            components.add(caption)
        else:raise GeneratedCodeError('unknown/reordered geometry setup block')
        prefix.append(block)
    if len(prefix)<2:raise GeneratedCodeError('geometry environment incomplete')
    return (dict(caption='CST Tools GEO setup',history='\n'.join(b['history'] for b in prefix)),*features)

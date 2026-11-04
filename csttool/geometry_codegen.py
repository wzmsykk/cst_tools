"""GEO lowering onto the shared WWB emitter/projector; no native dispatch."""
from .geometry_contract import (project_geometry, native_component_name, native_solid_name,
                                feature_expressions)
from .settings_projection import (GEOMETRY_PROFILE, project_geometry_history,
                                  geometry_expression_identity)
from .winwrap_emitter import (HistoryCall, With, String, Number, Boolean,
                             arithmetic, render_history, GeneratedCodeError)
from .winwrap_checks import check_history


def expected_geometry_history(spec):
    """Expectation from declaration projection, never from generated text."""
    declaration=project_geometry(spec);features=[];exact={}
    for index,(body,row) in enumerate(zip(spec['geometry']['features'],declaration['features'])):
        op=body['op'];feature=dict(op=op,resolved=row['resolved'])
        if op.startswith('create_'):
            feature.update(native_name=native_solid_name(body['component_id'],body['object_id']),material_id=body['material_id'])
        else:
            target=body['object_id'] if op=='delete_object' else body['target_id']
            feature['target_name']=declaration['objects'][target]['native_name']
            if op=='boolean_solids':
                feature.update(tool_name=declaration['objects'][body['tool_id']]['native_name'],operation=body['operation'])
        features.append(feature)
        parameters=[dict(name=k,expr=v['expression']) for k,v in spec['parameters'].items()]
        for path,text in feature_expressions(body).items():
            exact['geometry.features['+str(index)+'].'+path]=geometry_expression_identity(text,parameters)
    return {'units.length':'mm','units.frequency':'MHz','wcs.mode':'global','components':tuple(native_component_name(c) for c in spec['components']),
            'geometry.features':tuple(features),'geometry.objects':{
                row['native_name']:dict(state=row['state'],material_id=row['material_id']) for row in declaration['objects'].values()}},exact


def validate_geometry_history(spec, blocks):
    """Independent source syntax + semantic projection + symbolic preservation."""
    expectation,exact=expected_geometry_history(spec)
    expected_captions=['CST Tools GEO setup']+['CST Tools GEO '+f['feature_id'] for f in spec['geometry']['features']]
    if not isinstance(blocks,(tuple,list)) or len(blocks)!=len(expected_captions):
        raise GeneratedCodeError('GEO history block count differs from declaration')
    for block,caption in zip(blocks,expected_captions):
        if not isinstance(block,dict) or block.get('caption')!=caption or not isinstance(block.get('history'),str):
            raise GeneratedCodeError('GEO history caption/order differs from declaration')
        check_history(block['history'],profile=GEOMETRY_PROFILE)
    report=project_geometry_history(blocks,[dict(name=k,expr=v['expression']) for k,v in spec['parameters'].items()],
        scope='root',available_scopes=('root',))
    if report.status!='resolved' or report.missing_fields:
        error=GeneratedCodeError('GEO history projection rejected: '+str(report.reasons))
        error.origin=dict(report.failure_origin or {})
        raise error
    mismatch=next((k for k in sorted(set(exact)|set(report.exact_values)) if exact.get(k)!=report.exact_values.get(k)),None)
    if mismatch is None:
        mismatch=next((k for k,v in expectation.items() if report.fields.get(k)!=v),None)
        if mismatch=='geometry.features':
            mismatch=next('geometry.features['+str(i)+']' for i,(a,b) in enumerate(zip(report.fields['geometry.features'],expectation['geometry.features'])) if a!=b)
    if mismatch:
        error=GeneratedCodeError('GEO history values, operands or symbolic expressions differ at '+mismatch)
        error.input_field=mismatch
        origin=report.origins.get(mismatch,{})
        error.origin=dict(origin) if hasattr(origin,'items') else {}
        raise error
    return report


def render_geometry_history(spec):
    """One setup block and one uniquely-captioned block per active feature.

    Selection sets and identity reservations are document metadata, not Group or
    Pick calls. This returns code artifacts only and cannot build/save a model.
    """
    declaration=project_geometry(spec)
    def call(obj,method,*args):return HistoryCall(obj,method,args)
    def block(obj,rows):return With(obj,tuple(call(obj,m,*a) for m,a in rows))
    def number(text):return arithmetic(text,spec['parameters'])
    setup=[block('Units',[('Geometry',(String('mm'),)),('Frequency',(String('MHz'),))]),call('WCS','ActivateWCS',String('global'))]
    setup += [call('Component','New',String(native_component_name(c))) for c in spec['components']]
    program=[dict(caption='CST Tools GEO setup',history=render_history(setup,profile=GEOMETRY_PROFILE))]
    for index,feature in enumerate(spec['geometry']['features']):
        op=feature['op'];nodes=[]
        if op.startswith('create_'):
            component,name=native_solid_name(feature['component_id'],feature['object_id']).split(':')
            rows=[('Reset',()),('Name',(String(name),)),('Component',(String(component),)),('Material',(String(feature['material_id']),))]
            if op=='create_brick':
                obj='Brick';rows += [(axis.upper()+'range',tuple(number(e) for e in feature['bounds_mm'][axis])) for axis in 'xyz']
            elif op=='create_cylinder':
                obj='Cylinder';axis=feature['axis'];transverse=[a for a in 'xyz' if a!=axis]
                rows += [('Axis',(String(axis),)),('OuterRadius',(number(feature['outer_radius_mm']),)),('InnerRadius',(number(feature['inner_radius_mm']),))]
                rows += [(a.upper()+'center',(number(e),)) for a,e in zip(transverse,feature['transverse_center_mm'])]
                rows += [(axis.upper()+'range',tuple(number(e) for e in feature['axial_range_mm'])),('Segments',(Number('0'),))]
            else:
                obj='Sphere';rows += [('Axis',(String('z'),)),('CenterRadius',(number(feature['radius_mm']),)),
                    ('TopRadius',(Number('0'),)),('BottomRadius',(Number('0'),)),
                    ('Center',tuple(number(e) for e in feature['center_mm'])),('Segments',(Number('0'),))]
            nodes=[block(obj,rows+[('Create',())])]
        else:
            target=feature['object_id'] if op=='delete_object' else feature['target_id']
            native=declaration['objects'][target]['native_name']
            if op=='translate_solid':
                nodes=[block('Transform',[('Reset',()),('Name',(String(native),)),
                    ('Vector',tuple(number(e) for e in feature['translation_mm'])),('UsePickedPoints',(Boolean(False),)),
                    ('MultipleObjects',(Boolean(False),)),('GroupObjects',(Boolean(False),)),
                    ('Repetitions',(Number('1'),)),('Touch',(Boolean(False),)),('Transform',(String('Shape'),String('Translate')))])]
            elif op=='boolean_solids':
                nodes=[call('Solid',{'union':'Add','difference':'Subtract','intersection':'Intersect'}[feature['operation']],
                    String(native),String(declaration['objects'][feature['tool_id']]['native_name']))]
            elif op=='delete_object':nodes=[call('Solid','Delete',String(native))]
        try:history=render_history(nodes,profile=GEOMETRY_PROFILE)
        except GeneratedCodeError as error:
            error.feature_id=feature['feature_id'];error.input_field='geometry.features['+str(index)+']'
            raise
        program.append(dict(caption='CST Tools GEO '+feature['feature_id'],history=history))
    report=validate_geometry_history(spec,program)
    return tuple(program),report

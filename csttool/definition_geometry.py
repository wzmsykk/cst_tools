"""A1 native geometry observations, separate from persisted history claims."""
import math
from pathlib import Path
from .vb_codec import quote_vb_string


def geometry_expectation(projection):
    fields=projection.fields
    axis=fields['geometry.cylinder.axis'];radius=fields['geometry.cylinder.outerradius']
    lower,upper=fields['geometry.cylinder.'+axis+'range']
    bounds={a+side:float(value) for a in 'xyz' for side,value in
            zip(('min','max'),(lower,upper) if a==axis else (-radius,radius))}
    return dict(solid=fields['geometry.cylinder.component']+':'+fields['geometry.cylinder.name'],
                volume_mm3=math.pi*radius*radius*(upper-lower),bounds_mm=bounds)


def render_geometry_observer(projection,directory,nonce):
    expected=geometry_expectation(projection)
    q=lambda value:'"'+quote_vb_string(value)+'"'
    lines=['Private Sub CSTToolsObserveGeometry',
        '    Dim f As Integer, a As Double, b As Double, c As Double, d As Double, e As Double, g As Double',
        '    Dim ca As Double, cb As Double, cc As Double, cd As Double, ce As Double, cg As Double',
        '    Boundary.GetStructureBox a, b, c, d, e, g',
        '    Boundary.GetCalculationBox ca, cb, cc, cd, ce, cg',
        '    f = FreeFile','    Open '+q(directory/'geometry.tsv')+' For Output As #f']
    values=dict(nonce=q(nonce),project='GetProjectPath("Project")',solid=q(expected['solid']),
        exists='CStr(Solid.DoesExist('+q(expected['solid'])+'))',
        material='Solid.GetMaterialNameForShape('+q(expected['solid'])+')',
        volume_mm3='CStr(Solid.GetVolume('+q(expected['solid'])+'))')
    values.update({key+'_mm':'CStr('+value+')' for key,value in zip(('xmin','xmax','ymin','ymax','zmin','zmax'),'abcdeg')})
    values.update({'calculation_'+key+'_mm':'CStr(c'+value+')' for key,value in zip(('xmin','xmax','ymin','ymax','zmin','zmax'),'abcdeg')})
    values.update({'boundary.'+face:'Boundary.Get'+face.capitalize() for face in ('xmin','xmax','ymin','ymax','zmin','zmax')})
    for key,value in values.items():lines.append('    Print #f, '+q(key)+' & Chr(9) & '+value)
    lines+=['    Close #f','End Sub']
    return '\n'.join(lines)+'\n'


def verify_geometry_observation(path,projection,model,nonce):
    path=Path(path)
    if path.stat().st_size>65536:raise ValueError('G03 geometry observation exceeds budget')
    rows={}
    for line in path.read_text(encoding='ascii').splitlines():
        key,value=line.split('\t')
        if key in rows:raise ValueError('G03 duplicate geometry observation')
        rows[key]=value
    expected=geometry_expectation(projection)
    keys={'nonce','project','solid','exists','material','volume_mm3'}|{key+'_mm' for key in expected['bounds_mm']}|{
        'calculation_'+key+'_mm' for key in expected['bounds_mm']}|{'boundary.'+key for key in expected['bounds_mm']}
    if (set(rows)!=keys or rows['nonce']!=nonce or Path(rows['project']).resolve()!=Path(model).with_suffix('').resolve()
            or rows['solid']!=expected['solid'] or rows['exists'].lower() not in ('true','-1') or rows['material']!='Vacuum'):
        raise ValueError('G03 geometry identity/material mismatch')
    volume=float(rows['volume_mm3'])
    if not math.isfinite(volume) or not math.isclose(volume,expected['volume_mm3'],rel_tol=1e-6):
        raise ValueError('G03 cylinder volume mismatch (expected project mm^3)')
    for key,wanted in expected['bounds_mm'].items():
        for name in (key+'_mm','calculation_'+key+'_mm'):
            value=float(rows[name])
            if not math.isfinite(value) or not math.isclose(value,wanted,rel_tol=1e-6,abs_tol=1e-5):
                raise ValueError('G03 geometry/calculation bounds mismatch: '+name)
        if rows['boundary.'+key].lower()!='electric':raise ValueError('G03 boundary mismatch: '+key)
    return dict(status='verified',source='native-query',solid=expected['solid'],material=rows['material'],
        volume_mm3=volume,bounds_mm=expected['bounds_mm'],boundaries={key:'electric' for key in expected['bounds_mm']},
        background_evidence='persisted-and-replayed-history-only',raw=rows)


def geometry_objects(spec):
    """Declared names/lifetimes and analytic primitive volumes, not a CAD kernel."""
    from .geometry_contract import project_geometry
    projection=project_geometry(spec);volumes={};bounds={}
    for feature in projection['features']:
        op=feature['op'];value=feature['resolved']
        source=next(f for f in spec['geometry']['features'] if f['feature_id']==feature['feature_id'])
        if op=='create_brick':volume=math.prod(float(value[a][1])-float(value[a][0]) for a in 'xyz')
        elif op=='create_cylinder':volume=math.pi*(float(value['outer_radius_mm'])**2-float(value['inner_radius_mm'])**2)*(float(value['axial_range_mm'][1])-float(value['axial_range_mm'][0]))
        elif op=='create_sphere':volume=4*math.pi*float(value['radius_mm'])**3/3
        else:volume=None
        if op.startswith('create_'):
            oid=source['object_id'];volumes[oid]=volume
            if op=='create_brick':box={a:list(map(float,value[a])) for a in 'xyz'}
            elif op=='create_sphere':
                radius=float(value['radius_mm']);box={a:[float(c)-radius,float(c)+radius] for a,c in zip('xyz',value['center_mm'])}
            else:
                axis=value['axis'];box={axis:list(map(float,value['axial_range_mm']))};radius=float(value['outer_radius_mm'])
                for a,c in zip([a for a in 'xyz' if a!=axis],value['transverse_center_mm']):box[a]=[float(c)-radius,float(c)+radius]
            bounds[oid]=box
        elif op=='translate_solid':
            oid=source['target_id']
            if bounds.get(oid):bounds[oid]={a:[v+float(delta) for v in bounds[oid][a]] for a,delta in zip('xyz',value['translation_mm'])}
        elif op=='boolean_solids':volumes[source['target_id']]=None;bounds[source['target_id']]=None
    return tuple(dict(object_id=oid,**row,volume_mm3=volumes.get(oid),bounds_mm=bounds.get(oid)) for oid,row in projection['objects'].items())


def render_managed_geometry_observer(spec,directory,nonce):
    """Post-history observation only; deliberately never queries LooseBoundingBox."""
    q=lambda value:'"'+quote_vb_string(value)+'"'
    rows=['Private Sub CSTToolsObserveGeometry','    Dim f As Integer, a As Double, b As Double, c As Double, d As Double, e As Double, g As Double',
        '    Dim ca As Double, cb As Double, cc As Double, cd As Double, ce As Double, cg As Double',
        '    Boundary.GetStructureBox a, b, c, d, e, g',
        '    Boundary.GetCalculationBox ca, cb, cc, cd, ce, cg',
        '    Solid.UpdateAllBodyTypes','    f = FreeFile',
        '    Open '+q(str(Path(directory)/'geometry.tsv'))+' For Output As #f']
    def emit(key,value):rows.append('    Print #f, '+q(key)+' & Chr(9) & '+value)
    emit('nonce',q(nonce));emit('project','GetProjectPath("Project")')
    emit('count','CStr(Solid.GetNumberOfShapes())')
    for key,var in zip(('xmin','xmax','ymin','ymax','zmin','zmax'),'abcdeg'):
        emit('bounds.'+key,'CStr('+var+')');emit('calculation.'+key,'CStr(c'+var+')')
    for index,obj in enumerate(geometry_objects(spec)):
        prefix='solid.'+str(index)+'.';name=q(obj['native_name'])
        emit(prefix+'name',name);emit(prefix+'exists','CStr(Solid.DoesExist('+name+'))')
        if obj['state']=='live':
            emit(prefix+'material','Solid.GetMaterialNameForShape('+name+')')
            emit(prefix+'volume_mm3','CStr(Solid.GetVolume('+name+'))')
            emit(prefix+'solid','CStr(Solid.IsSolidShape('+name+'))')
            emit(prefix+'hybrid','CStr(Solid.IsHybridShape('+name+'))')
    emit('end',q('GEO1'));rows.extend(['    Close #f','End Sub'])
    return '\n'.join(rows)+'\n'


def verify_managed_geometry_observation(path,spec,model,nonce):
    path=Path(path)
    if path.stat().st_size>1024*1024:raise ValueError('GEO observation budget')
    rows={}
    for line in path.read_text(encoding='ascii').splitlines():
        key,value=line.split('\t')
        if key in rows:raise ValueError('duplicate GEO observation')
        rows[key]=value
    objects=geometry_objects(spec);wanted={'nonce','project','count','end'}
    wanted|={kind+'.'+axis+side for kind in ('bounds','calculation') for axis in 'xyz' for side in ('min','max')}
    def boolean(value):
        if value.lower() in ('true','-1'):return True
        if value.lower() in ('false','0'):return False
        raise ValueError('invalid native boolean')
    if (rows.get('nonce')!=nonce or rows.get('end')!='GEO1'
            or Path(rows.get('project','')).resolve()!=Path(model).with_suffix('').resolve()
            or rows.get('count')!=str(sum(o['state']=='live' for o in objects))):
        raise ValueError('GEO observation identity/count differs')
    facts=[]
    for index,obj in enumerate(objects):
        prefix='solid.'+str(index)+'.';live=obj['state']=='live';wanted.update((prefix+'name',prefix+'exists'))
        if rows.get(prefix+'name')!=obj['native_name'] or boolean(rows.get(prefix+'exists',''))!=live:
            raise ValueError('GEO solid lifetime/name differs')
        actual=dict(object_id=obj['object_id'],native_name=obj['native_name'],state=obj['state'],exists=live)
        if live:
            wanted.update(prefix+k for k in ('material','volume_mm3','solid','hybrid'))
            volume=float(rows[prefix+'volume_mm3'])
            if (rows.get(prefix+'material')!=obj['material_id'] or not boolean(rows.get(prefix+'solid',''))
                    or boolean(rows.get(prefix+'hybrid','')) or not math.isfinite(volume) or volume<=0):
                raise ValueError('GEO material/body type/positive volume differs')
            if obj['volume_mm3'] is not None and not math.isclose(volume,obj['volume_mm3'],rel_tol=1e-6,abs_tol=1e-6):
                raise ValueError('GEO primitive/translation analytic volume differs')
            actual.update(material_id=rows[prefix+'material'],volume_mm3=volume,solid=True,hybrid=False,
                volume_check='analytic' if obj['volume_mm3'] is not None else 'positive-only-CSG-not-general-equivalence')
        facts.append(actual)
    if set(rows)!=wanted:raise ValueError('GEO observation fields differ')
    boxes={kind:{key:float(rows[kind+'.'+key]) for key in (a+s for a in 'xyz' for s in ('min','max'))} for kind in ('bounds','calculation')}
    for box in boxes.values():
        if any(not math.isfinite(v) for v in box.values()) or any(box[a+'min']>box[a+'max'] for a in 'xyz'):
            raise ValueError('GEO global box is invalid')
    live=[o for o in objects if o['state']=='live']
    if live and all(o['bounds_mm'] is not None for o in live):
        for a in 'xyz':
            for i,side,op in ((0,'min',min),(1,'max',max)):
                expected=op(o['bounds_mm'][a][i] for o in live)
                if not math.isclose(boxes['bounds'][a+side],expected,rel_tol=1e-6,abs_tol=1e-5):
                    raise ValueError('GEO global primitive/translation structure bounds differ')
    return dict(status='verified',source='native-query',objects=facts,
                bounds_mm=boxes['bounds'],calculation_bounds_mm=boxes['calculation'],
                per_solid_bounds='not-queried; LooseBoundingBox structural-macro restriction',raw=rows)


def geometry_proof_ready(proof,source_hash):
    return (isinstance(proof,dict) and proof.get('status')=='verified' and proof.get('scope')=='root'
        and proof.get('source_sha256')==source_hash
        and proof.get('validation_target') in ('geometry','simulation')
        and isinstance(proof.get('gates'),list) and all(isinstance(g,str) for g in proof['gates'])
        and set(proof['gates'])=={'saved-reopened','identity','settings','standard-close'}
        and isinstance(proof.get('observations'),list) and all(isinstance(o,dict) for o in proof['observations'])
        and isinstance(proof.get('sessions'),list) and all(isinstance(s,dict) for s in proof['sessions'])
        and [o.get('phase') for o in proof.get('observations',[])]==['saved','reopened']
        and all(o.get('geometry',{}).get('status')=='verified' for o in proof['observations'])
        and [s.get('phase') for s in proof.get('sessions',[])]==['saved','reopened']
        and all(s.get('exit_confirmed') is True and type(s.get('exit_code')) is int and s['exit_code']==0 for s in proof['sessions']))

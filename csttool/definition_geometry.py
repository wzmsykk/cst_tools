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

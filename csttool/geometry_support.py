"""Read-only CST solid/material mask bridge; background is explicitly excluded."""
from pathlib import Path
from .physical_domain import DomainSupport
from .result_reconciliation import file_hash


def render_material_support(sampling, output_path, *, shape_names=()):
    """Return VBA helper; caller loads a known project and checks completion/exit.

    Selected solid union only, no inferred background region or mesh support.
    Different overlapping material labels are rejected instead of guessed.
    """
    def quote(value):
        value=str(value)
        if '\n' in value or '\r' in value:
            raise ValueError('invalid VBA name/path')
        return value.replace('"','""')
    path=quote(Path(output_path))
    if len(set(shape_names))!=len(shape_names) or any(not isinstance(name,str) or not name for name in shape_names):
        raise ValueError('invalid/duplicate selected shapes')
    predicate='True' if not shape_names else ' Or '.join(
        f'shape="{quote(name)}"' for name in shape_names)
    nx,ny,nz=sampling.counts
    a=sampling.bounds_m
    return f'''
Sub CSTDOM_WriteSupport
    Dim names() As String, materials() As String, count As Long, matched As Long
    Dim s As Long,i As Long,j As Long,k As Long,f As Integer, shape As String, label As String
    Dim x As Double,y As Double,z As Double,factor As Double
    count=Solid.GetNumberOfShapes
    If count<1 Then Err.Raise vbObjectError+2501,"domain","No solid support"
    ReDim names(count-1),materials(count-1)
    For s=0 To count-1
        shape=Solid.GetNameOfShapeFromIndex(s)
        If {predicate} Then
            names(s)=shape
            materials(s)=Solid.GetMaterialNameForShape(shape)
            matched=matched+1
            If shape="" Or materials(s)="" Then Err.Raise vbObjectError+2502,"domain","Unknown shape/material"
            If materials(s)="excluded" Then Err.Raise vbObjectError+2502,"domain","Reserved material label"
        End If
    Next s
    If matched<1 Then Err.Raise vbObjectError+2505,"domain","Selected solids not found"
    If {len(shape_names)}>0 And matched<>{len(shape_names)} Then Err.Raise vbObjectError+2505,"domain","Selected solid inventory differs"
    factor=Units.GetGeometryUnitToSI
    If factor<=0 Then Err.Raise vbObjectError+2503,"domain","Invalid SI scale"
    f=FreeFile
    Open "{path}.partial" For Output As #f
    For i=0 To {nx-1}
        x=({a[0]}+(i+0.5)*({a[1]-a[0]})/{nx})/factor
        For j=0 To {ny-1}
            y=({a[2]}+(j+0.5)*({a[3]-a[2]})/{ny})/factor
            For k=0 To {nz-1}
                z=({a[4]}+(k+0.5)*({a[5]-a[4]})/{nz})/factor
                label="excluded"
                For s=0 To count-1
                    If names(s)<>"" Then
                        If Solid.IsPointInsideShape(x,y,z,names(s)) Then
                            If label<>"excluded" And label<>materials(s) Then Err.Raise vbObjectError+2504,"domain","Ambiguous overlapping materials"
                            label=materials(s)
                        End If
                    End If
                Next s
                Print #f,label
            Next k
        Next j
        Debug.Print "CST_DOMAIN_ROW " & CStr(i+1)
    Next i
    Close #f
    Name "{path}.partial" As "{path}"
End Sub
'''


def load_material_support(sampling, path, *, expected_sha256, geometry_id):
    path=Path(path)
    if file_hash(path)!=expected_sha256:
        raise ValueError('geometry support artifact changed')
    labels=tuple(path.read_text(encoding='utf-8-sig').splitlines())
    return DomainSupport(sampling,labels,geometry_id,
                         'CST-Solid.IsPointInsideShape-and-GetMaterialNameForShape',True)

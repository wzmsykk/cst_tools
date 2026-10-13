' Optional diagnostic only: an export error does not invalidate the solver completion.
Sub ExportModeField_output(mode As Long, fieldKind As String, nx As Long, ny As Long, nz As Long, xmin As Double, xmax As Double, ymin As Double, ymax As Double, zmin As Double, zmax As Double, outputDir As String, outputName As String)
    Dim x() As Double,y() As Double,z() As Double
    Dim i As Long,j As Long,k As Long,p As Long,n As Long,invalid As Long
    Dim xr As Double,xi As Double,yr As Double,yi As Double,zr As Double,zi As Double
    Dim factor As Double,frequency As Double,filename As String,tempFile As String
    Dim bx1 As Double,bx2 As Double,by1 As Double,by2 As Double,bz1 As Double,bz2 As Double
    Dim f As Integer,message As String
    On Error GoTo Failed
    n=nx*ny*nz
    ReDim x(n-1),y(n-1),z(n-1)
    factor=Units.GetGeometryUnitToSI
    If factor<=0 Then Err.Raise vbObjectError+1,"field-export","invalid geometry units"
    Boundary.GetCalculationBox bx1,bx2,by1,by2,bz1,bz2
    If xmin/factor<bx1 Or xmax/factor>bx2 Or ymin/factor<by1 Or ymax/factor>by2 Or zmin/factor<bz1 Or zmax/factor>bz2 Then Err.Raise vbObjectError+5,"field-export","sampling outside calculation box"
    p=0
    For i=0 To nx-1
        For j=0 To ny-1
            For k=0 To nz-1
                x(p)=(xmin+(i+0.5)*(xmax-xmin)/nx)/factor
                y(p)=(ymin+(j+0.5)*(ymax-ymin)/ny)/factor
                z(p)=(zmin+(k+0.5)*(zmax-zmin)/nz)/factor
                p=p+1
            Next k
        Next j
    Next i
    If Not SelectTreeItem("2D/3D Results\Modes\Mode " & CStr(mode) & "\" & LCase(fieldKind)) Then Err.Raise vbObjectError+2,"field-export","mode field missing"
    frequency=EigenmodeSolver.GetModeFrequencyInHz(mode)
    VectorPlot3D.Reset
    VectorPlot3D.SetPoints x,y,z
    VectorPlot3D.CalculateList
    If VectorPlot3D.GetListLength<>n Then Err.Raise vbObjectError+3,"field-export","point count mismatch"
    For p=0 To n-1
        If Not VectorPlot3D.GetListItem(p,xr,xi,yr,yi,zr,zi) Then invalid=invalid+1
    Next p
    If invalid>0 Then Err.Raise vbObjectError+4,"field-export","invalid sample points: " & CStr(invalid)
    filename=outputDir & outputName & ".h5"
    tempFile=outputDir & outputName & ".partial.h5"
    With ASCIIExport
        .Reset
        .FileName tempFile
        .SetfileType "hdf5"
        .Mode "FixedWidth"
        .SetPoints x,y,z
        .ExportCoordinatesInMeter False
        .Execute
    End With
    Name tempFile As filename
    f=FreeFile
    Open outputDir & outputName & ".status.partial" For Output As #f
    Print #f,"SUCCESS"
    Print #f,CStr(frequency)
    Print #f,CStr(invalid)
    Print #f,CStr(factor)
    Print #f,Units.GetGeometryUnit
    Close #f
    Name outputDir & outputName & ".status.partial" As outputDir & outputName & ".status"
    Exit Sub
Failed:
    message="FAILURE " & CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    Close #f
    f=FreeFile
    Open outputDir & outputName & ".status" For Output As #f
    Print #f,message
    Close #f
End Sub

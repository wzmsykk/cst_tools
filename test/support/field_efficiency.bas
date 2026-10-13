'#Language "WWB-COM"
Option Explicit
Sub Main
    Dim stage As String, t As Double, opened As Double
    Dim side As Long, count As Long, i As Long, j As Long, k As Long, p As Long
    Dim m As Long, c As Long, rep As Long, levels As Variant, component As Variant
    Dim xs() As Double, ys() As Double, zs() As Double
    Dim a() As Double, b() As Double, values As Variant
    Dim na As Double, nb As Double, rr As Double, ii As Double
    Dim f As Integer, out As Integer, basename As String
    On Error GoTo Failed
    stage = "open"
    opened = Timer
    OpenFile "%SOURCE%"
    stage = "save-as-with-results"
    SaveAs "%PROJECT%", True
    out = FreeFile
    Open "%ROOT%\timings.csv" For Output As #out
    Print #out, "points,repeat,stage,seconds,norm_a,norm_b,cross_re,cross_im"
    Print #out, "0,0,open," & CStr(Timer-opened) & ",0,0,0,0"
    levels = Array(12,24,48)
    component = Array("xre","yre","zre","xim","yim","zim")
    For j = 0 To 2
        side = levels(j)
        count = side*side*side
        ReDim xs(count-1), ys(count-1), zs(count-1)
        ReDim a(count-1,5), b(count-1,5)
        p=0
        For i=0 To side-1
            For m=0 To side-1
                For k=0 To side-1
                    xs(p)=-10+20*(i+0.5)/side
                    ys(p)=-10+20*(m+0.5)/side
                    zs(p)=-50+100*(k+0.5)/side
                    p=p+1
                Next k
            Next m
        Next i
        For rep=1 To 3
            stage="sample"
            t=Timer
            For m=1 To 2
                If Not SelectTreeItem("2D/3D Results\Modes\Mode " & CStr(m) & "\e") Then Err.Raise vbObjectError+1, "benchmark", "missing E mode"
                VectorPlot3D.Reset
                VectorPlot3D.SetPoints xs,ys,zs
                VectorPlot3D.CalculateList
                If VectorPlot3D.GetListLength <> count Then Err.Raise vbObjectError+2, "benchmark", "sample length mismatch"
                For c=0 To 5
                    values=VectorPlot3D.GetList(component(c))
                    For p=0 To count-1
                        If m=1 Then
                            a(p,c)=values(p+LBound(values))
                        Else
                            b(p,c)=values(p+LBound(values))
                        End If
                    Next p
                Next c
            Next m
            Print #out,CStr(count)&","&CStr(rep)&",sample,"&CStr(Timer-t)&",0,0,0,0"
            stage="vba-sum"
            t=Timer
            na=0: nb=0: rr=0: ii=0
            For p=0 To count-1
                For c=0 To 2
                    na=na+a(p,c)^2+a(p,c+3)^2
                    nb=nb+b(p,c)^2+b(p,c+3)^2
                    rr=rr+a(p,c)*b(p,c)+a(p,c+3)*b(p,c+3)
                    ii=ii+a(p,c)*b(p,c+3)-a(p,c+3)*b(p,c)
                Next c
            Next p
            Print #out,CStr(count)&","&CStr(rep)&",vba-sum,"&CStr(Timer-t)&","&CStr(na)&","&CStr(nb)&","&CStr(rr)&","&CStr(ii)
            ' Export exactly the already sampled arrays: separates serialization from sampling.
            stage="csv-write"
            t=Timer
            basename="%ROOT%\sample-"&CStr(count)&"-"&CStr(rep)
            f=FreeFile
            Open basename & ".csv" For Output As #f
            For p=0 To count-1
                For c=0 To 5
                    Print #f,CStr(a(p,c))&",";
                Next c
                For c=0 To 5
                    If c<5 Then
                        Print #f,CStr(b(p,c))&",";
                    Else
                        Print #f,CStr(b(p,c))
                    End If
                Next c
            Next p
            Close #f
            Print #out,CStr(count)&","&CStr(rep)&",csv-write,"&CStr(Timer-t)&",0,0,0,0"
            ' Native exporter resamples selected mode 2; measure separately, not as CSV equivalent.
            stage="native-ascii"
            t=Timer
            For m=1 To 2
            If Not SelectTreeItem("2D/3D Results\Modes\Mode " & CStr(m) & "\e") Then Err.Raise vbObjectError+1, "benchmark", "missing export mode"
            With ASCIIExport
                .Reset
                .FileName basename & "-mode" & CStr(m) & ".txt"
                .SetfileType "ascii"
                .Mode "FixedWidth"
                .SetPoints xs,ys,zs
                .Execute
            End With
            Next m
            Print #out,CStr(count)&","&CStr(rep)&",native-ascii,"&CStr(Timer-t)&",0,0,0,0"
            stage="native-hdf5"
            t=Timer
            For m=1 To 2
            If Not SelectTreeItem("2D/3D Results\Modes\Mode " & CStr(m) & "\e") Then Err.Raise vbObjectError+1, "benchmark", "missing export mode"
            With ASCIIExport
                .Reset
                .FileName basename & "-mode" & CStr(m) & ".h5"
                .SetfileType "hdf5"
                .Mode "FixedWidth"
                .SetPoints xs,ys,zs
                .Execute
            End With
            Next m
            Print #out,CStr(count)&","&CStr(rep)&",native-hdf5,"&CStr(Timer-t)&",0,0,0,0"
        Next rep
    Next j
    Close #out
    stage="save"
    Save
    f=FreeFile
    Open "%ROOT%\completed.txt" For Output As #f
    Print #f,"SUCCESS"
    Close #f
    Quit
    Exit Sub
Failed:
    Dim message As String
    message=stage & ": " & CStr(Err.Number) & ": " & Err.Description
    On Error Resume Next
    Close
    f=FreeFile
    Open "%ROOT%\failed.txt" For Output As #f
    Print #f,message
    Close #f
    Save
    Quit
End Sub

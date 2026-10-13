'#Language "WWB-COM"
Option Explicit
Sub ProbeStage(value As String)
    Dim stageFile As Integer
    stageFile=FreeFile
    Open "%ROOT%\stage.partial" For Output As #stageFile
    Print #stageFile,value
    Close #stageFile
    If Dir("%ROOT%\stage.txt")<>"" Then Kill "%ROOT%\stage.txt"
    Name "%ROOT%\stage.partial" As "%ROOT%\stage.txt"
End Sub
Sub Main
    Dim stage As String, t As Double, side As Long, n As Long, i As Long, j As Long, k As Long
    Dim p As Long, c As Long, m As Long, rep As Long, level As Variant, components As Variant
    Dim xs() As Double, ys() As Double, zs() As Double, weights() As Double, weightedValues() As Double, v As Variant
    Dim aa As Object, ab As Object, ba As Object, bb As Object, ca As Object, cb As Object
    Dim na As Double, nb As Double, rr As Double, ii As Double, unused As Double
    Dim out As Integer, filename As String, message As String
    On Error GoTo Failed
    stage="open"
    ProbeStage "loading"
    t=Timer
    OpenFile "%SOURCE%"
    ProbeStage "loaded"
    SaveAs "%PROJECT%",True
    ProbeStage "saved-copy"
    out=FreeFile
    Open "%ROOT%\timings.csv" For Output As #out
    Print #out,"points,repeat,stage,seconds,norm_a,norm_b,cross_re,cross_im"
    Print #out,"0,0,open," & CStr(Timer-t) & ",0,0,0,0"
    level=Array(12,24,48)
    components=Array("xre","yre","zre","xim","yim","zim")
    For j=0 To 2
        side=level(j):n=side*side*side
        ReDim xs(n-1),ys(n-1),zs(n-1),weights(n-1),weightedValues(n-1)
        p=0
        For i=0 To side-1
            For m=0 To side-1
                For k=0 To side-1
                    xs(p)=-10+20*(i+0.5)/side
                    ys(p)=-10+20*(m+0.5)/side
                    zs(p)=-50+100*(k+0.5)/side
                    weights(p)=Sqr(1+xs(p)^2/100)
                    p=p+1
                Next k
            Next m
        Next i
        For rep=1 To 3
            ProbeStage "sampling-" & CStr(side) & "-" & CStr(rep)
            ' Reverse route order in repetition 2; each route includes tree selection.
            For c=0 To 1
                If (c=0 And rep<>2) Or (c=1 And rep=2) Then
                    stage="public-native":t=Timer
                    Set aa=Result3D(""):aa.Initialize n,1,1,"vector"
                    Set ab=Result3D(""):ab.Initialize n,1,1,"vector"
                    Set ba=Result3D(""):ba.Initialize n,1,1,"vector"
                    Set bb=Result3D(""):bb.Initialize n,1,1,"vector"
                    Set ca=Result3D(""):ca.Initialize n,1,1,"vector"
                    Set cb=Result3D(""):cb.Initialize n,1,1,"vector"
                    For m=1 To 2
                        If Not SelectTreeItem("2D/3D Results\Modes\Mode " & CStr(m) & "\e") Then Err.Raise vbObjectError+1,"benchmark","missing field"
                        VectorPlot3D.Reset
                        VectorPlot3D.SetPoints xs,ys,zs
                        VectorPlot3D.CalculateList
                        For k=0 To 5
                            v=VectorPlot3D.GetList(components(k))
                            If UBound(v)-LBound(v)+1<>n Then Err.Raise vbObjectError+2,"benchmark","invalid point inventory"
                            For p=0 To n-1
                                weightedValues(p)=v(p+LBound(v))*weights(p)
                            Next p
                            If m=1 Then
                                stage="setarray-mode1-" & CStr(k)
                                aa.SetArray weightedValues,CStr(components(k))
                                ab.SetArray weightedValues,CStr(components(k))
                                ca.SetArray weightedValues,CStr(components(k))
                            Else
                                stage="setarray-mode2-" & CStr(k)
                                ba.SetArray weightedValues,CStr(components(k))
                                bb.SetArray weightedValues,CStr(components(k))
                                cb.SetArray weightedValues,CStr(components(k))
                            End If
                        Next k
                    Next m
                    aa.Conjugate:aa.DotProduct ab,na,unused
                    ba.Conjugate:ba.DotProduct bb,nb,unused
                    ca.Conjugate:ca.DotProduct cb,rr,ii
                    Print #out,CStr(n) & "," & CStr(rep) & ",public-native," & CStr(Timer-t) & "," & CStr(na) & "," & CStr(nb) & "," & CStr(rr) & "," & CStr(ii)
                Else
                    stage="native-hdf5":t=Timer
                    For m=1 To 2
                        If Not SelectTreeItem("2D/3D Results\Modes\Mode " & CStr(m) & "\e") Then Err.Raise vbObjectError+1,"benchmark","missing export field"
                        filename="%ROOT%\sample-" & CStr(n) & "-" & CStr(rep) & "-mode" & CStr(m) & ".h5"
                        With ASCIIExport
                            .Reset
                            .FileName filename
                            .SetfileType "hdf5"
                            .Mode "FixedWidth"
                            .SetPoints xs,ys,zs
                            .Execute
                        End With
                    Next m
                    Print #out,CStr(n) & "," & CStr(rep) & ",native-hdf5," & CStr(Timer-t) & ",0,0,0,0"
                End If
            Next c
        Next rep
    Next j
    Close #out
    ProbeStage "saving"
    Save
    out=FreeFile
    Open "%ROOT%\completed.txt" For Output As #out
    Print #out,"SUCCESS"
    Close #out
    ProbeStage "completed"
    Quit
    Exit Sub
Failed:
    message=stage & ": " & CStr(Err.Number) & ": " & Err.Description
    On Error Resume Next
    Close
    out=FreeFile
    Open "%ROOT%\failed.txt" For Output As #out
    Print #out,message
    Close #out
    ' Loading may not have succeeded: never save the source or quit from a failed batch.
    ProbeStage "failed-returning"
End Sub

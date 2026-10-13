'#Language "WWB-COM"
Option Explicit
Sub Main
    Dim stage As String, t As Double, started As Double
    Dim ra As Object, rb As Object, tempA As Object, tempB As Object
    Dim fileA As String, fileB As String, components As Variant, va As Variant, vb As Variant
    Dim a() As Double, b() As Double
    Dim n As Long, i As Long, c As Long, rep As Long, out As Integer
    Dim na As Double, nb As Double, rr As Double, ii As Double, unused As Double
    Dim message As String
    On Error GoTo Failed
    stage="open"
    t=Timer
    OpenFile "%SOURCE%"
    SaveAs "%PROJECT%", True
    out=FreeFile
    Open "%ROOT%\timings.csv" For Output As #out
    Print #out,"points,repeat,stage,seconds,norm_a,norm_b,cross_re,cross_im"
    Print #out,"0,0,open," & CStr(Timer-t) & ",0,0,0,0"
    stage="synthetic"
    Set ra=Result3D("")
    Set rb=Result3D("")
    ra.Initialize 1,1,1,"vector"
    rb.Initialize 1,1,1,"vector"
    ra.SetXRe 0,1
    ra.SetXIm 0,1
    rb.SetXRe 0,2
    rb.SetXIm 0,3
    ra.DotProduct rb,rr,ii
    Print #out,"1,0,synthetic-raw,0,0,0," & CStr(rr) & "," & CStr(ii)
    Set ra=Result3D("")
    ra.Initialize 1,1,1,"vector"
    ra.SetXRe 0,1
    ra.SetXIm 0,1
    ra.Conjugate
    ra.DotProduct rb,rr,ii
    Print #out,"1,0,synthetic-conjugated,0,0,0," & CStr(rr) & "," & CStr(ii)
    stage="tree-files"
    fileA=ResultTree.GetFileFromTreeItem("2D/3D Results\Modes\Mode 1\e")
    fileB=ResultTree.GetFileFromTreeItem("2D/3D Results\Modes\Mode 2\e")
    components=Array("xre","yre","zre","xim","yim","zim")
    For rep=1 To 3
        started=Timer
        stage="load"
        t=Timer
        Set ra=Result3D(fileA)
        Set rb=Result3D(fileB)
        n=ra.GetLength
        If n<>rb.GetLength Or n<1 Then Err.Raise vbObjectError+1,"benchmark","native lengths differ or empty"
        Print #out,CStr(n) & "," & CStr(rep) & ",native-load," & CStr(Timer-t) & ",0,0,0,0"
        stage="native-dot"
        t=Timer
        ra.Conjugate
        ra.DotProduct rb,rr,ii
        Set tempA=Result3D(fileA)
        Set tempB=Result3D(fileA)
        tempA.Conjugate
        tempA.DotProduct tempB,na,unused
        Set tempA=Result3D(fileB)
        Set tempB=Result3D(fileB)
        tempA.Conjugate
        tempA.DotProduct tempB,nb,unused
        Print #out,CStr(n) & "," & CStr(rep) & ",native-dot," & CStr(Timer-t) & "," & CStr(na) & "," & CStr(nb) & "," & CStr(rr) & "," & CStr(ii)
        Print #out,CStr(n) & "," & CStr(rep) & ",native-total," & CStr(Timer-started) & "," & CStr(na) & "," & CStr(nb) & "," & CStr(rr) & "," & CStr(ii)
        stage="reference-load"
        t=Timer
        Set ra=Result3D(fileA)
        Set rb=Result3D(fileB)
        ReDim a(n-1,5),b(n-1,5)
        For c=0 To 5
            va=ra.GetArray(components(c))
            vb=rb.GetArray(components(c))
            For i=0 To n-1
                a(i,c)=va(i+LBound(va))
                b(i,c)=vb(i+LBound(vb))
            Next i
        Next c
        Print #out,CStr(n) & "," & CStr(rep) & ",reference-load-transfer," & CStr(Timer-t) & ",0,0,0,0"
        stage="reference-sum"
        t=Timer
        na=0:nb=0:rr=0:ii=0
        For i=0 To n-1
            For c=0 To 2
                na=na+a(i,c)^2+a(i,c+3)^2
                nb=nb+b(i,c)^2+b(i,c+3)^2
                rr=rr+a(i,c)*b(i,c)+a(i,c+3)*b(i,c+3)
                ii=ii+a(i,c)*b(i,c+3)-a(i,c+3)*b(i,c)
            Next c
        Next i
        Print #out,CStr(n) & "," & CStr(rep) & ",reference-sum," & CStr(Timer-t) & "," & CStr(na) & "," & CStr(nb) & "," & CStr(rr) & "," & CStr(ii)
    Next rep
    Close #out
    stage="save"
    Save
    out=FreeFile
    Open "%ROOT%\completed.txt" For Output As #out
    Print #out,"SUCCESS"
    Close #out
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
    If stage<>"open" Then Save
    Quit
End Sub

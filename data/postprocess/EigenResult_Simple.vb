Function EigenResult_Simple(iModeNumber As Integer,queryKey As String) As Double
    If (iModeNumber > EigenmodeSolver.GetNumberOfModesCalculated) Then
            ReportWarningToWindow("3D Eigenmode result template execution: Cannot find result for mode #"+CStr(iModeNumber)+".")
            'CalculateEigenModeResult = lib_rundef
            Exit Function
    End If
    Dim frq_cst As Double
    frq_cst = EigenmodeSolver.GetModeFrequencyInHz(iModeNumber)/Units.GetFrequencyUnitToSI
    If (Not SelectTreeItem("2D/3D Results\Modes\Mode " + CStr(iModeNumber) + "\e")) Then
                    ReportWarningToWindow("Error in 3D Eigenmode result template execution: Cannot find result for mode #"+CStr(iModeNumber)+".")
                    'CalculateEigenModeResult = lib_rundef
                    Exit Function
    End If
    Plot.Update
    ScreenUpdating True
    Wait 0.3
    Dim eng_cst As Double,pw_cst As Double,q_cst As Double
    With QFactor
        .Reset
        .SetHField "Mode " + Trim(Str(iModeNumber))
        .Calculate
        q_cst = .GetTotalQ
        pw_cst = .GetTotalLossRMS
        eng_cst = .GetTotalEnergy
    End With
    Dim cst_value As Double
    if queryKey="Q-Factor" or  queryKey="Q_Factor" or  queryKey="Q Factor" or  queryKey="Q"Then
        cst_value=q_cst
    ElseIf queryKey="Total Loss" or queryKey="Total_Loss" or queryKey="Total-Loss"Then
        cst_value=pw_cst
    ElseIf queryKey="Total Energy" or queryKey="Total_Energy" or queryKey="Total-Energy"Then
        cst_value=eng_cst
    ElseIf queryKey="Frequency" or queryKey="frequency" or queryKey="Freq" or queryKey="freq"Then
        cst_value=frq_cst
    End IF
    EigenResult_Simple=cst_value
End Function

Function EigenResult_Simple_output(iModeNumber As Integer,queryKey As String,outputDir As String, outputName As String)
    Dim roq As Double
    roq=EigenResult_Simple(iModeNumber,queryKey)
    Open(outputDir & outputName) For Output As #1
    Print #1,"Result Name"
    Print #1,"EigenResult_Simple" 'Name
    Print #1,"Result Type"
    Print #1,queryKey
    Print #1,"ModeNumber"
    Print #1,iModeNumber
    Print #1,"value"
    Print #1,roq
    Close #1

End Function
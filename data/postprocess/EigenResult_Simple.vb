Function EigenResult_Simple(iModeNumber As Integer,queryKey As String) As Double
    If (iModeNumber > EigenmodeSolver.GetNumberOfModesCalculated) Then
            ReportWarningToWindow("3D Eigenmode result template execution: Cannot find result for mode #"+CStr(iModeNumber)+".")
            'CalculateEigenModeResult = lib_rundef
            EigenResult_Simple=-1
            Exit Function
    End If
    Dim frq_cst As Double
    frq_cst = EigenmodeSolver.GetModeFrequencyInHz(iModeNumber)/Units.GetFrequencyUnitToSI
    If (Not SelectTreeItem("2D/3D Results\Modes\Mode " + CStr(iModeNumber) + "\e")) Then
                    ReportWarningToWindow("Error in 3D Eigenmode result template execution: Cannot find result for mode #"+CStr(iModeNumber)+".")
                    'CalculateEigenModeResult = lib_rundef
                    EigenResult_Simple=-1
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
    ElseIf queryKey="Loss Enclosure" or queryKey="Loss_Enclosure" or queryKey="**Cond. Enclosure**"Then
        cst_value=QFactor.GetLossRMS("**Cond. Enclosure**")
    ElseIf queryKey="Loss Volume" or queryKey="Loss_Volume" or queryKey="**Volume Losses**"Then
        cst_value=QFactor.GetLossRMS("**Volume Losses**")
    ElseIf queryKey="Loss Surface" or queryKey="Loss_Surface" or queryKey="**Sum of Surface Losses**"Then
        cst_value=QFactor.GetLossRMS("**Sum of Surface Losses**")
    ElseIf queryKey="Q-Factor(External)" or queryKey="Q_Ext" Then

        If (Port.StartPortNumberIteration = 0) Then
            ReportWarning("3D Eigenmode: Cannot calculate external Q value due to missing port.")
            cst_value = -1
        ElseIf (Port.GetFCutOff(Port.GetNextPortNumber, 1) > frq_cst) Then
            ReportWarning("3D Eigenmode: Cannot calculate external Q value, mode frequency is below port cutoff frequency.")
            cst_value = -1 ' use -1 instead of lib_rundef so that a plot is created
        Else
            cst_value = EigenmodeSolver.GetModeExternalQFactor(iModeNumber)
        End If
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
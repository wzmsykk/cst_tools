'#Language "WWB-COM"

Option Explicit

Public cstProjectPath As String
Public paramFileDstPath As String
Public statusFilePath As String
Public stageFilePath As String
Public detailFilePath As String
Public modifyMesh As Boolean

Sub Main
    Dim failureNumber As Long
    Dim failureDescription As String
    On Error GoTo Failed

    cstProjectPath = "%CSTPROJFILE%"
    paramFileDstPath = "%PARAMDSTPATH%"
    statusFilePath = "%STATUSPATH%"
    stageFilePath = "%STAGEPATH%"
    detailFilePath = "%DETAILPATH%"
    modifyMesh = %MODIFYMESH%

    ' -m -b loads the working project before compiling this project script.
    WriteStage "parameters"
    EnsureHomParameters
    WriteStage "bind-history"
    BindHomSolverSettings
    WriteStage "rebuild"
    If Not Rebuild Then Err.Raise vbObjectError + 2201, "HOM preprocess", "Rebuild returned False"
    WriteDetail "stage", "rebuild", "", "", "returned-success"
    WriteStage "save"
    Save
    WriteDetail "stage", "save", "", cstProjectPath, "returned"
    WriteStage "export-parameters"
    ExportParameterList paramFileDstPath
    WriteDetail "stage", "export-parameters", "", paramFileDstPath, "returned"
    WriteStatus "SUCCESS"
    Exit Sub

Failed:
    failureNumber = Err.Number
    failureDescription = Err.Description
    On Error Resume Next
    WriteDetail "error", "macro", CStr(failureNumber), failureDescription, "failed"
    WriteStatus "FAILURE" & vbTab & CStr(failureNumber) & vbTab & failureDescription
    ' Return to the batch runner; never Quit while its sheet is active.
End Sub

Sub WriteStage(message As String)
    Dim fileNumber As Integer
    fileNumber = FreeFile
    Open stageFilePath For Output As #fileNumber
    Print #fileNumber, message
    Close #fileNumber
    WriteDetail "stage", message, "", "", "started"
End Sub

Function DetailText(value As String) As String
    DetailText = Replace(Replace(Replace(value, vbTab, "\\t"), vbCr, "\\r"), vbLf, "\\n")
End Function

Sub WriteDetail(action As String, target As String, before As String, after As String, outcome As String)
    Dim detailNumber As Integer
    detailNumber = FreeFile
    Open detailFilePath For Append As #detailNumber
    Print #detailNumber, CStr(Now) & vbTab & action & vbTab & target & vbTab & DetailText(before) & vbTab & DetailText(after) & vbTab & outcome
    Close #detailNumber
End Sub

Function ParameterExpression(parameterName As String) As String
    Dim parameterIndex As Long
    For parameterIndex = 0 To GetNumberOfParameters() - 1
        If GetParameterName(parameterIndex) = parameterName Then
            ParameterExpression = GetParameterSValue(parameterIndex)
            Exit Function
        End If
    Next
    Err.Raise vbObjectError + 2203, "HOM preprocess", "Parameter not found: " & parameterName
End Function

Sub EnsureHomParameters
    If Not DoesParameterExist("fmin") Then
        WriteDetail "parameter-add", "fmin", "<absent>", CStr(Solver.GetFmin()), "requested"
        StoreParameterWithDescription "fmin", CStr(Solver.GetFmin()), "Minimum eigenmode frequency"
        WriteDetail "parameter-add", "fmin", "<absent>", ParameterExpression("fmin"), "applied"
    Else
        WriteDetail "parameter-keep", "fmin", ParameterExpression("fmin"), ParameterExpression("fmin"), "unchanged"
    End If
    If Not DoesParameterExist("fmax") Then
        WriteDetail "parameter-add", "fmax", "<absent>", CStr(Solver.GetFmax()), "requested"
        StoreParameterWithDescription "fmax", CStr(Solver.GetFmax()), "Maximum eigenmode frequency"
        WriteDetail "parameter-add", "fmax", "<absent>", ParameterExpression("fmax"), "applied"
    Else
        WriteDetail "parameter-keep", "fmax", ParameterExpression("fmax"), ParameterExpression("fmax"), "unchanged"
    End If
    If Not DoesParameterExist("nmodes") Then
        WriteDetail "parameter-add", "nmodes", "<absent>", "1", "requested"
        StoreParameterWithDescription "nmodes", "1", "Number of eigenmodes"
        WriteDetail "parameter-add", "nmodes", "<absent>", ParameterExpression("nmodes"), "applied"
    Else
        WriteDetail "parameter-keep", "nmodes", ParameterExpression("nmodes"), ParameterExpression("nmodes"), "unchanged"
    End If
    If Not modifyMesh Then
        WriteDetail "mesh-keep", "mesh", "<not-read>", "original settings", "unchanged"
        Exit Sub
    End If
    If DoesParameterExist("cell") Then
        WriteDetail "parameter-set", "cell", ParameterExpression("cell"), "%MESHCELLSPERWAVELENGTH%", "requested"
        StoreParameter "cell", "%MESHCELLSPERWAVELENGTH%"
    Else
        WriteDetail "parameter-add", "cell", "<absent>", "%MESHCELLSPERWAVELENGTH%", "requested"
        StoreParameterWithDescription "cell", "%MESHCELLSPERWAVELENGTH%", "Fixed tetrahedral cells per wavelength"
    End If
    WriteDetail "parameter-readback", "cell", "", ParameterExpression("cell"), "applied"
End Sub

Sub BindHomSolverSettings
    Dim history As String
    Dim modeCount As Double
    modeCount = RestoreDoubleParameter("nmodes")
    If modeCount < 1 Or modeCount > 32767 Or modeCount <> Fix(modeCount) Then Err.Raise vbObjectError + 2202, "HOM preprocess", "nmodes must be a positive integer"
    history = "Solver.FrequencyRange ""fmin"", ""fmax""" & vbCrLf
    history = history & "With EigenmodeSolver" & vbCrLf
    history = history & ".SetFrequencyTarget True, RestoreDoubleParameter(""fmin"")" & vbCrLf
    history = history & ".SetNumberOfModes CInt(RestoreDoubleParameter(""nmodes""))" & vbCrLf
    If modifyMesh Then history = history & ".SetMeshAdaptationTet False" & vbCrLf
    history = history & "End With" & vbCrLf
    If modifyMesh Then
    history = history & "With MeshSettings" & vbCrLf
    history = history & ".SetMeshType ""Tet""" & vbCrLf
    history = history & ".Set ""StepsPerWaveNear"", ""cell""" & vbCrLf
    history = history & "End With" & vbCrLf
    End If
    WriteDetail "history", "CST Tools: Bind HOM solver parameters", "<not-read>", history, "requested"
    AddToHistory "CST Tools: Bind HOM solver parameters", history
    WriteDetail "history", "CST Tools: Bind HOM solver parameters", "", "", "returned-not-verified"
End Sub

Sub ExportParameterList(outputPath As String)
    Dim fileNumber As Integer
    Dim parameterCount As Long
    Dim index As Long
    Dim parameterName As String
    Dim parameterValue As String
    Dim description As String

    parameterCount = GetNumberOfParameters()
    fileNumber = FreeFile
    Open outputPath For Output As #fileNumber
    Print #fileNumber, outputPath
    Print #fileNumber, cstProjectPath
    Print #fileNumber, parameterCount
    For index = 0 To parameterCount - 1
        parameterName = GetParameterName(index)
        parameterValue = GetParameterSValue(index)
        description = GetParameterDescription(parameterName)
        Print #fileNumber, index; vbTab; parameterName; vbTab; parameterValue; vbTab; description
    Next
    Close #fileNumber
End Sub

Sub WriteStatus(message As String)
    Dim fileNumber As Integer
    On Error Resume Next
    fileNumber = FreeFile
    Open statusFilePath For Output As #fileNumber
    Print #fileNumber, message
    Close #fileNumber
End Sub

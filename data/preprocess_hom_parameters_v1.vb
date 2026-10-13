'#Language "WWB-COM"

Option Explicit

Public cstProjectPath As String
Public paramFileDstPath As String
Public statusFilePath As String

Sub Main
    On Error GoTo Failed

    cstProjectPath = "%CSTPROJFILE%"
    paramFileDstPath = "%PARAMDSTPATH%"
    statusFilePath = "%STATUSPATH%"

    ' -m -b loads the working project before compiling this project script.
    EnsureHomParameters
    BindHomSolverSettings
    If Not Rebuild Then Err.Raise vbObjectError + 2201, "HOM preprocess", "Rebuild returned False"
    Save
    ExportParameterList paramFileDstPath
    WriteStatus "SUCCESS"
    Exit Sub

Failed:
    WriteStatus "FAILURE" & vbTab & CStr(Err.Number) & vbTab & Err.Description
    ' Return to the batch runner; never Quit while its sheet is active.
End Sub

Sub EnsureHomParameters
    If Not DoesParameterExist("fmin") Then
        StoreParameterWithDescription "fmin", CStr(Solver.GetFmin()), "Minimum eigenmode frequency"
    End If
    If Not DoesParameterExist("fmax") Then
        StoreParameterWithDescription "fmax", CStr(Solver.GetFmax()), "Maximum eigenmode frequency"
    End If
    If Not DoesParameterExist("nmodes") Then
        StoreParameterWithDescription "nmodes", "1", "Number of eigenmodes"
    End If
    If DoesParameterExist("cell") Then
        StoreParameter "cell", "%MESHCELLSPERWAVELENGTH%"
    Else
        StoreParameterWithDescription "cell", "%MESHCELLSPERWAVELENGTH%", "Fixed tetrahedral cells per wavelength"
    End If
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
    history = history & ".SetMeshAdaptationTet False" & vbCrLf
    history = history & "End With" & vbCrLf
    history = history & "With MeshSettings" & vbCrLf
    history = history & ".SetMeshType ""Tet""" & vbCrLf
    history = history & ".Set ""StepsPerWaveNear"", ""cell""" & vbCrLf
    history = history & "End With" & vbCrLf
    AddToHistory "CST Tools: Bind HOM solver parameters", history
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

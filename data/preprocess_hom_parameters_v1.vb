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

    OpenFile(cstProjectPath)
    EnsureHomParameters
    BindHomSolverSettings
    Rebuild
    Save
    ExportParameterList paramFileDstPath
    WriteStatus "SUCCESS"
    Quit
    Exit Sub

Failed:
    WriteStatus "FAILURE" & vbTab & CStr(Err.Number) & vbTab & Err.Description
    On Error Resume Next
    Quit
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
End Sub

Sub BindHomSolverSettings
    Dim history As String
    history = "Solver.FrequencyRange ""fmin"", ""fmax""" & vbCrLf
    history = history & "With EigenmodeSolver" & vbCrLf
    history = history & ".SetFrequencyTarget ""True"", ""fmin""" & vbCrLf
    history = history & ".SetNumberOfModes ""nmodes""" & vbCrLf
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

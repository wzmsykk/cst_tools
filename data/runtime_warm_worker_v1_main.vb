' Bounded two-task Warm Worker v1. This does not replace legacy worker.vb.
Sub Main
    Dim errorMessage As String
    Dim i As Long

    On Error GoTo WorkerFailed
    CSTPWW_WriteMarker "%MARKER_PATH%", "stage:open-project"
    OpenFile "%PROJECT_PATH%"

    If Not CSTPWW_RunTask("%TASK_0_PATH%", "%COMPLETION_0_PATH%", "%ACK_0_PATH%", "%SNAPSHOT_0_PATH%", "%RESULT_0_PATH%", "%TIMING_0_PATH%") Then Exit Sub
    If Not CSTPWW_RunTask("%TASK_1_PATH%", "%COMPLETION_1_PATH%", "%ACK_1_PATH%", "%SNAPSHOT_1_PATH%", "%RESULT_1_PATH%", "%TIMING_1_PATH%") Then Exit Sub

    CSTPWW_WriteMarker "%MARKER_PATH%", "stage:stop"
    For i = 1 To 600
        If Dir("%STOP_REQUEST_PATH%") <> "" Then
            If Not CSTP_ReadStopRequest("%STOP_REQUEST_PATH%", "%SESSION_ID%", errorMessage) Then
                CSTPWW_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                Exit Sub
            End If
            If Not CSTP_WriteStopAck("%STOP_ACK_PATH%", "%SESSION_ID%", errorMessage) Then
                CSTPWW_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                Exit Sub
            End If
            CSTPWW_WriteMarker "%MARKER_PATH%", "success"
            Save
            Quit
            Exit Sub
        End If
        Wait 0.1
    Next i
    CSTPWW_WriteMarker "%MARKER_PATH%", "failure:stop timeout"
    Exit Sub

WorkerFailed:
    CSTPWW_WriteMarker "%MARKER_PATH%", "failure:INTERNAL_ERROR:" & Err.Description
End Sub

Private Function CSTPWW_RunTask(ByVal taskPath As String, ByVal completionPath As String, ByVal ackPath As String, ByVal snapshotPath As String, ByVal resultPath As String, ByVal timingPath As String) As Boolean
    Dim task As CSTP_Task
    Dim errorCode As String
    Dim errorMessage As String
    Dim completionError As String
    Dim stage As String
    Dim rebuilt As Boolean
    Dim acknowledged As Boolean
    Dim rebuildStart As Double
    Dim solveStart As Double
    Dim flushStart As Double
    Dim rebuildSeconds As Double
    Dim solveSeconds As Double
    Dim flushSeconds As Double
    Dim i As Long

    CSTPWW_RunTask = False
    On Error GoTo TaskFailed
    stage = "read-task"
    If Not CSTP_ReadTask(taskPath, "%SESSION_ID%", task, errorCode, errorMessage) Then
        CSTPWW_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
        Exit Function
    End If

    stage = "parameters"
    For i = 0 To task.ParameterCount - 1
        StoreParameter task.Parameters(i).Name, task.Parameters(i).Value
    Next i

    stage = "rebuild"
    rebuildStart = Timer
    rebuilt = Rebuild
    rebuildSeconds = CSTPWW_Elapsed(rebuildStart, Timer)
    If Not rebuilt Then
        CSTPWW_PublishFailure completionPath, task, "REBUILD_FAILED", "Rebuild returned False"
        Exit Function
    End If

    stage = "solver"
    solveStart = Timer
    EigenmodeSolver.Start
    solveSeconds = CSTPWW_Elapsed(solveStart, Timer)

    stage = "flush"
    flushStart = Timer
    Backup snapshotPath
    flushSeconds = CSTPWW_Elapsed(flushStart, Timer)
    If Dir(resultPath) = "" Then
        CSTPWW_PublishFailure completionPath, task, "RESULT_FLUSH_FAILED", "native rd0 result was not flushed"
        Exit Function
    End If
    CSTPWW_WriteTiming timingPath, task.TaskId, rebuildSeconds, solveSeconds, flushSeconds

    stage = "completion"
    If Not CSTP_WriteCompletion(completionPath, task.TaskId, task.SessionId, True, "", "", completionError) Then
        CSTPWW_WriteMarker "%MARKER_PATH%", "failure:" & completionError
        Exit Function
    End If

    stage = "ack"
    acknowledged = False
    For i = 1 To 600
        If Dir(ackPath) <> "" Then
            If Not CSTP_ReadAck(ackPath, task.TaskId, task.SessionId, errorMessage) Then
                CSTPWW_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                Exit Function
            End If
            acknowledged = True
            Exit For
        End If
        Wait 0.1
    Next i
    If Not acknowledged Then
        CSTPWW_WriteMarker "%MARKER_PATH%", "failure:ack timeout"
        Exit Function
    End If
    CSTPWW_WriteMarker "%MARKER_PATH%", "ack:" & task.TaskId
    CSTPWW_RunTask = True
    Exit Function

TaskFailed:
    errorMessage = stage & " failed: " & Err.Description
    If stage = "solver" Then
        errorCode = "SOLVER_FAILED"
    ElseIf stage = "flush" Then
        errorCode = "RESULT_FLUSH_FAILED"
    Else
        errorCode = "INTERNAL_ERROR"
    End If
    CSTPWW_PublishFailure completionPath, task, errorCode, errorMessage
End Function

Private Sub CSTPWW_PublishFailure(ByVal completionPath As String, ByRef task As CSTP_Task, ByVal errorCode As String, ByVal errorMessage As String)
    Dim completionError As String
    If Not CSTP_WriteCompletion(completionPath, task.TaskId, task.SessionId, False, errorCode, errorMessage, completionError) Then
        CSTPWW_WriteMarker "%MARKER_PATH%", "failure:" & completionError
    Else
        CSTPWW_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
    End If
End Sub

Private Function CSTPWW_Elapsed(ByVal started As Double, ByVal finished As Double) As Double
    If finished >= started Then
        CSTPWW_Elapsed = finished - started
    Else
        CSTPWW_Elapsed = 86400# - started + finished
    End If
End Function

Private Sub CSTPWW_WriteTiming(ByVal filePath As String, ByVal taskId As String, ByVal rebuildSeconds As Double, ByVal solveSeconds As Double, ByVal flushSeconds As Double)
    Dim fileNumber As Integer
    fileNumber = FreeFile
    Open filePath For Output As #fileNumber
    Print #fileNumber, taskId
    Print #fileNumber, CStr(rebuildSeconds)
    Print #fileNumber, CStr(solveSeconds)
    Print #fileNumber, CStr(flushSeconds)
    Close #fileNumber
End Sub

Private Sub CSTPWW_WriteMarker(ByVal filePath As String, ByVal message As String)
    Dim fileNumber As Integer
    fileNumber = FreeFile
    Open filePath For Output As #fileNumber
    Print #fileNumber, message
    Close #fileNumber
End Sub

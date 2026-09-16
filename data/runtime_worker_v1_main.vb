' Independent one-shot Worker v1. This does not replace legacy worker.vb.
Sub Main
    Dim task As CSTP_Task
    Dim errorCode As String
    Dim errorMessage As String
    Dim completionError As String
    Dim stage As String
    Dim acknowledged As Boolean
    Dim rebuilt As Boolean
    Dim i As Long

    On Error GoTo WorkerFailed
    stage = "open-project"
    CSTPW_WriteMarker "%MARKER_PATH%", "stage:open-project"
    OpenFile "%PROJECT_PATH%"

    stage = "read-task"
    CSTPW_WriteMarker "%MARKER_PATH%", "stage:read-task"
    If Not CSTP_ReadTask("%TASK_PATH%", "%SESSION_ID%", task, errorCode, errorMessage) Then
        CSTPW_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
        Exit Sub
    End If

    stage = "parameters"
    CSTPW_WriteMarker "%MARKER_PATH%", "stage:parameters"
    For i = 0 To task.ParameterCount - 1
        StoreParameter task.Parameters(i).Name, task.Parameters(i).Value
    Next i

    stage = "rebuild"
    CSTPW_WriteMarker "%MARKER_PATH%", "stage:rebuild"
    rebuilt = Rebuild
    If Not rebuilt Then
        CSTPW_PublishFailure task, "REBUILD_FAILED", "Rebuild returned False"
        Exit Sub
    End If

    stage = "solver"
    CSTPW_WriteMarker "%MARKER_PATH%", "stage:solver"
    EigenmodeSolver.Start

    stage = "flush"
    CSTPW_WriteMarker "%MARKER_PATH%", "stage:flush"
    Backup "%SNAPSHOT_PATH%"
    If Dir("%RESULT_PATH%") = "" Then
        CSTPW_PublishFailure task, "RESULT_FLUSH_FAILED", "native rd0 result was not flushed"
        Exit Sub
    End If

    stage = "completion"
    CSTPW_WriteMarker "%MARKER_PATH%", "stage:completion"
    If Not CSTP_WriteCompletion("%COMPLETION_PATH%", task.TaskId, task.SessionId, True, "", "", completionError) Then
        CSTPW_WriteMarker "%MARKER_PATH%", "failure:" & completionError
        Exit Sub
    End If

    stage = "ack"
    acknowledged = False
    For i = 1 To 600
        If Dir("%ACK_PATH%") <> "" Then
            If CSTP_ReadAck("%ACK_PATH%", task.TaskId, task.SessionId, errorMessage) Then
                acknowledged = True
                Exit For
            Else
                CSTPW_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                Exit Sub
            End If
        End If
        Wait 0.1
    Next i

    If acknowledged Then
        CSTPW_WriteMarker "%MARKER_PATH%", "success"
        Save
        Quit
    Else
        CSTPW_WriteMarker "%MARKER_PATH%", "failure:ack timeout"
    End If
    Exit Sub

WorkerFailed:
    errorMessage = stage & " failed: " & Err.Description
    If stage = "solver" Then
        errorCode = "SOLVER_FAILED"
    ElseIf stage = "flush" Then
        errorCode = "RESULT_FLUSH_FAILED"
    Else
        errorCode = "INTERNAL_ERROR"
    End If
    CSTPW_PublishFailure task, errorCode, errorMessage
End Sub

Private Sub CSTPW_PublishFailure(ByRef task As CSTP_Task, ByVal errorCode As String, ByVal errorMessage As String)
    Dim completionError As String
    If Not CSTP_WriteCompletion("%COMPLETION_PATH%", task.TaskId, task.SessionId, False, errorCode, errorMessage, completionError) Then
        CSTPW_WriteMarker "%MARKER_PATH%", "failure:" & completionError
    Else
        CSTPW_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
    End If
End Sub

Private Sub CSTPW_WriteMarker(ByVal filePath As String, ByVal message As String)
    Dim fileNumber As Integer
    fileNumber = FreeFile
    Open filePath For Output As #fileNumber
    Print #fileNumber, message
    Close #fileNumber
End Sub

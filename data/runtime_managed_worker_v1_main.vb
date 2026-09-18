' Long-lived managed Worker v1. Python owns task identity and lifecycle.
Public outFullDir As String

Sub Main
    Dim task As CSTP_Task
    Dim errorCode As String
    Dim errorMessage As String
    Dim completionError As String
    Dim stage As String
    Dim rebuilt As Boolean
    Dim acknowledged As Boolean
    Dim i As Long

    On Error GoTo WorkerFailed
    OpenFile "%PROJECT_PATH%"
    CSTPMW_WriteMarker "%MARKER_PATH%", "ready"

    Do
        If Dir("%STOP_REQUEST_PATH%") <> "" Then
            If Not CSTP_ReadStopRequest("%STOP_REQUEST_PATH%", "%SESSION_ID%", errorMessage) Then
                CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                Exit Do
            End If
            If Not CSTP_WriteStopAck("%STOP_ACK_PATH%", "%SESSION_ID%", errorMessage) Then
                CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                Exit Do
            End If
            CSTPMW_WriteMarker "%MARKER_PATH%", "stopped"
            Save
            Quit
            Exit Sub
        End If

        If Dir("%TASK_PATH%") <> "" Then
            stage = "read-task"
            If Not CSTP_ReadTask("%TASK_PATH%", "%SESSION_ID%", task, errorCode, errorMessage) Then
                CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
                Exit Do
            End If

            stage = "parameters"
            For i = 0 To task.ParameterCount - 1
                StoreParameter task.Parameters(i).Name, task.Parameters(i).Value
            Next i

            stage = "rebuild"
            rebuilt = Rebuild
            If Not rebuilt Then
                CSTPMW_PublishFailure task, "REBUILD_FAILED", "Rebuild returned False"
                GoTo WaitForAck
            End If

            stage = "solver"
            EigenmodeSolver.Start

            stage = "postprocess"
            outFullDir = "%RESULT_ROOT%" & task.TaskId & "\"
            If Dir(outFullDir, 16) = "" Then MkDir outFullDir
            CustomPostProcess

            stage = "flush"
            Backup outFullDir & "project.cst"
            If Not CSTP_WriteCompletion("%COMPLETION_PATH%", task.TaskId, task.SessionId, True, "", "", completionError) Then
                CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & completionError
                Exit Do
            End If

WaitForAck:
            acknowledged = False
            For i = 1 To 6000
                If Dir("%ACK_PATH%") <> "" Then
                    If Not CSTP_ReadAck("%ACK_PATH%", task.TaskId, task.SessionId, errorMessage) Then
                        CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                        Exit Do
                    End If
                    Kill "%TASK_PATH%"
                    Kill "%COMPLETION_PATH%"
                    Kill "%ACK_PATH%"
                    CSTPMW_WriteMarker "%MARKER_PATH%", "ready"
                    acknowledged = True
                    Exit For
                End If
                Wait 0.1
            Next i
            If Not acknowledged Then
                CSTPMW_WriteMarker "%MARKER_PATH%", "failure:ack timeout"
                Exit Do
            End If
        Else
            Wait 0.1
        End If
    Loop

    Save
    Quit
    Exit Sub

WorkerFailed:
    errorMessage = stage & " failed: " & Err.Description
    If stage = "solver" Then
        errorCode = "SOLVER_FAILED"
    ElseIf stage = "flush" Or stage = "postprocess" Then
        errorCode = "RESULT_FLUSH_FAILED"
    Else
        errorCode = "INTERNAL_ERROR"
    End If
    If task.TaskId <> "" Then
        CSTPMW_PublishFailure task, errorCode, errorMessage
        Resume WaitForAck
    Else
        CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
        Save
        Quit
    End If
End Sub

Private Sub CSTPMW_PublishFailure(ByRef task As CSTP_Task, ByVal errorCode As String, ByVal errorMessage As String)
    Dim completionError As String
    If Not CSTP_WriteCompletion("%COMPLETION_PATH%", task.TaskId, task.SessionId, False, errorCode, errorMessage, completionError) Then
        CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & completionError
    End If
End Sub

Private Sub CSTPMW_WriteMarker(ByVal filePath As String, ByVal message As String)
    Dim fileNumber As Integer
    fileNumber = FreeFile
    Open filePath For Output As #fileNumber
    Print #fileNumber, message
    Close #fileNumber
End Sub

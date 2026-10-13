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
    Dim ackBlocked As Boolean
    Dim receiptPath As String

    On Error GoTo WorkerFailed
    OpenFile "%PROJECT_PATH%"
    CSTPMW_WriteMarker "%MARKER_PATH%", "ready"

    Do
        If Dir("%STOP_REQUEST_PATH%") <> "" Then
            If Not CSTP_ReadStopRequest("%STOP_REQUEST_PATH%", "%SESSION_ID%", errorMessage) Then
                CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                Exit Do
            End If
            CSTPMW_WriteMarker "%MARKER_PATH%", "stopped"
            CSTPMW_CloseSession
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
            For i = 0 To task.ParameterCount - 1
                If LCase(task.Parameters(i).Name) = "nmodes" Then
                    EigenmodeSolver.SetNumberOfModes "nmodes"
                End If
            Next i
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
            stage = "ack-read"
            CSTPMW_Trace stage, "%ACK_PATH%", "waiting"
            acknowledged = False
            ackBlocked = False
            receiptPath = "%ACK_PATH%." & task.TaskId & ".accepted"
            Do
                If Dir("%STOP_REQUEST_PATH%") <> "" Then
                    If Not CSTP_ReadStopRequest("%STOP_REQUEST_PATH%", "%SESSION_ID%", errorMessage) Then
                        CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                        CSTPMW_CloseSession
                        Exit Sub
                    End If
                    ' Preserve task/completion files. Python can recover and ACK
                    ' the completed result after this worker has safely exited.
                    CSTPMW_WriteMarker "%MARKER_PATH%", "stopped-with-completion"
                    CSTPMW_CloseSession
                    Exit Sub
                End If
                If Not ackBlocked And Dir("%ACK_PATH%") <> "" Then
                    If Not CSTP_ReadAck("%ACK_PATH%", task.TaskId, task.SessionId, errorMessage) Then
                        CSTPMW_Trace stage, "%ACK_PATH%", errorMessage
                        CSTPMW_WriteMarker "%MARKER_PATH%", "failure:ACK_BLOCKED:" & errorMessage
                        ackBlocked = True
                        GoTo AckWaitTick
                    End If
                    stage = "ack-receipt"
                    If Dir(receiptPath) <> "" Then
                        acknowledged = CSTP_ReadAck(receiptPath, task.TaskId, task.SessionId, errorMessage)
                    Else
                        acknowledged = CSTP_WriteAckReceipt(receiptPath, task.TaskId, task.SessionId, errorMessage)
                    End If
                    If Not acknowledged Then
                        CSTPMW_Trace stage, receiptPath, errorMessage
                        CSTPMW_WriteMarker "%MARKER_PATH%", "failure:ACK_BLOCKED:" & errorMessage
                        ackBlocked = True
                        GoTo AckWaitTick
                    End If
                    stage = "ack-cleanup"
                    CSTPMW_Trace stage, "%TASK_PATH%", "delete-task"
                    Kill "%TASK_PATH%"
                    CSTPMW_Trace stage, "%COMPLETION_PATH%", "delete-completion"
                    Kill "%COMPLETION_PATH%"
                    CSTPMW_Trace stage, "%ACK_PATH%", "delete-ack"
                    Kill "%ACK_PATH%"
                    CSTPMW_WriteMarker "%MARKER_PATH%", "ready"
                    acknowledged = True
                    Exit Do
                End If
AckWaitTick:
                Wait 0.1
            Loop
        Else
            Wait 0.1
        End If
    Loop

CloseWorker:
    CSTPMW_CloseSession
    Exit Sub

WorkerFailed:
    errorMessage = stage & " failed: number=" & CStr(Err.Number) & "; description=" & Err.Description
    CSTPMW_Trace stage, "%PROJECT_PATH%", errorMessage
    If stage = "ack-read" Or stage = "ack-receipt" Or stage = "ack-cleanup" Then
        CSTPMW_WriteMarker "%MARKER_PATH%", "failure:ACK_BLOCKED:" & errorMessage
        ackBlocked = True
        Resume AckWaitTick
    End If
    If stage = "solver" Then
        errorCode = "SOLVER_FAILED"
    ElseIf stage = "flush" Or stage = "postprocess" Then
        errorCode = "RESULT_FLUSH_FAILED"
    Else
        errorCode = "INTERNAL_ERROR"
    End If
    If task.TaskId <> "" And Dir("%COMPLETION_PATH%") = "" Then
        CSTPMW_PublishFailure task, errorCode, errorMessage
        Resume WaitForAck
    Else
        CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
        Resume CloseWorker
    End If
End Sub

Private Sub CSTPMW_CloseSession
    Dim closeStage As String
    Dim message As String
    Dim stopRequested As Boolean
    On Error GoTo CloseFailed
    stopRequested = (Dir("%STOP_REQUEST_PATH%") <> "")
    closeStage = "stop-read"
    If stopRequested Then
        If Not CSTP_ReadStopRequest("%STOP_REQUEST_PATH%", "%SESSION_ID%", message) Then
            CSTPMW_Trace closeStage, "%STOP_REQUEST_PATH%", message
            stopRequested = False
        End If
    End If
    closeStage = "save"
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "begin"
    Save
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "returned"
    If stopRequested Then
        closeStage = "stop-ack"
        If Not CSTP_WriteStopAck("%STOP_ACK_PATH%", "%SESSION_ID%", message) Then
            CSTPMW_Trace closeStage, "%STOP_ACK_PATH%", message
        End If
    End If
    closeStage = "quit"
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "begin"
    Quit
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "returned"
    Exit Sub
CloseFailed:
    message = "shutdown " & closeStage & " failed: number=" & CStr(Err.Number) & "; description=" & Err.Description
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", message
    On Error Resume Next
    CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & message
    On Error GoTo 0
    ' Do not retry Save, overwrite Completion, or Quit with unsaved changes.
End Sub

Private Sub CSTPMW_Trace(ByVal stage As String, ByVal path As String, ByVal detail As String)
    Dim fileNumber As Integer
    On Error Resume Next
    Debug.Print "CST_LIFECYCLE stage=" & stage & "; path=" & path & "; " & detail
    fileNumber = FreeFile
    Open "%LIFECYCLE_PATH%" For Append As #fileNumber
    Print #fileNumber, CStr(Now) & " | stage=" & stage & "; path=" & path & "; " & detail
    Close #fileNumber
    On Error GoTo 0
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

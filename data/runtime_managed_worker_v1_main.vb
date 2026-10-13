' Long-lived managed Worker v1. Python owns task identity and lifecycle.
Public outFullDir As String
Private goodParameterNames() As String
Private goodParameterExpressions() As String
Private goodParameterCount As Long
Private goodParametersAvailable As Boolean
Private modelNeedsRecovery As Boolean

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
    Dim requestedModes As Double
    Dim solverReturn As Long

    On Error GoTo WorkerFailed
    ' -m -b loads this project before compiling Model/3D/Model.run.
    ' Never OpenFile here: compiling in an empty project loses the parameter
    ' namespace used by CST's internal 3D/DS expression synchronization.
    stage = "parameter-checkpoint"
    CSTPMW_CaptureGoodParameters
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
            modelNeedsRecovery = True
            For i = 0 To task.ParameterCount - 1
                StoreParameter task.Parameters(i).Name, task.Parameters(i).Value
            Next i

            stage = "rebuild"
            rebuilt = Rebuild
            If Not rebuilt Then
                CSTPMW_PublishFailure task, "REBUILD_FAILED", "Rebuild returned False"
                GoTo WaitForAck
            End If

            stage = "solver-config"
            For i = 0 To task.ParameterCount - 1
                If LCase(task.Parameters(i).Name) = "nmodes" Then
                    requestedModes = RestoreDoubleParameter("nmodes")
                    If requestedModes < 1 Or requestedModes > 32767 Or requestedModes <> Fix(requestedModes) Then Err.Raise vbObjectError + 2202, "worker", "nmodes must be a positive integer"
                    EigenmodeSolver.SetNumberOfModes CInt(requestedModes)
                End If
            Next i
            stage = "solver-start"
            CSTPMW_Trace stage, "%PROJECT_PATH%", "calling EigenmodeSolver.Start"
            solverReturn = EigenmodeSolver.Start
            CSTPMW_Trace stage, "%PROJECT_PATH%", "returned=" & CStr(solverReturn)
            If solverReturn <> 1 Then
                CSTPMW_PublishFailure task, "SOLVER_FAILED", "EigenmodeSolver.Start returned 0"
                GoTo WaitForAck
            End If

            stage = "solver-result"
            If EigenmodeSolver.GetNumberOfModesCalculated < 1 Then
                CSTPMW_PublishFailure task, "SOLVER_FAILED", "Start returned 1 but no eigenmodes are available"
                GoTo WaitForAck
            End If

            stage = "postprocess"
            outFullDir = "%RESULT_ROOT%" & task.TaskId & "\"
            If Dir(outFullDir, 16) = "" Then MkDir outFullDir
            CustomPostProcess

            stage = "flush"
            Backup outFullDir & "project.cst"
            stage = "parameter-checkpoint"
            CSTPMW_CaptureGoodParameters
            modelNeedsRecovery = False
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
    If stage = "solver-start" Or stage = "solver-result" Then
        errorCode = "SOLVER_FAILED"
    ElseIf stage = "rebuild" Then
        errorCode = "REBUILD_FAILED"
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
    Dim recovered As Boolean
    Dim recoveryFile As Integer
    On Error GoTo CloseFailed
    stopRequested = (Dir("%STOP_REQUEST_PATH%") <> "")
    closeStage = "stop-read"
    If stopRequested Then
        If Not CSTP_ReadStopRequest("%STOP_REQUEST_PATH%", "%SESSION_ID%", message) Then
            CSTPMW_Trace closeStage, "%STOP_REQUEST_PATH%", message
            stopRequested = False
        End If
    End If
    If modelNeedsRecovery Then
        closeStage = "restore-parameters"
        CSTPMW_RestoreGoodParameters
        closeStage = "recovery-rebuild"
        CSTPMW_Trace closeStage, "%PROJECT_PATH%", "begin; no Solver replay"
        If Not Rebuild Then Err.Raise vbObjectError + 2401, "worker", "Recovery Rebuild returned False"
        modelNeedsRecovery = False
        recovered = True
        CSTPMW_Trace closeStage, "%PROJECT_PATH%", "returned True"
        closeStage = "recovery-snapshot"
        Backup "%PROJECT_PATH%.recovered.cst"
        If FileLen("%PROJECT_PATH%.recovered.cst") < 1 Then Err.Raise vbObjectError + 2403, "worker", "Recovery snapshot is empty"
    End If
    closeStage = "save"
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "begin"
    Save
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "returned"
    If recovered Then
        closeStage = "recovery-receipt"
        recoveryFile = FreeFile
        Open "%PROJECT_PATH%.recovery-saved" For Output As #recoveryFile
        Print #recoveryFile, "CST_RECOVERY_SAVED_V1"
        Print #recoveryFile, "%SESSION_ID%"
        Close #recoveryFile
    End If
    If stopRequested Then
        closeStage = "stop-ack"
        If Not CSTP_WriteStopAck("%STOP_ACK_PATH%", "%SESSION_ID%", message) Then
            CSTPMW_Trace closeStage, "%STOP_ACK_PATH%", message
        End If
    End If
    ' This worker is launched with -m as a batch macro. Quit here attempts
    ' to close its own sheet while the batch is still active. Return through
    ' Main instead; the batch runner closes the saved project normally.
    closeStage = "batch-return"
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "saved; returning to batch runner; Python must verify StopAck and process exit"
    Exit Sub
CloseFailed:
    message = "shutdown " & closeStage & " failed: number=" & CStr(Err.Number) & "; description=" & Err.Description
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", message
    On Error Resume Next
    CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & message
    On Error GoTo 0
    ' Do not retry Save, overwrite Completion, or Quit with unsaved changes.
End Sub

Private Sub CSTPMW_CaptureGoodParameters
    Dim index As Long, f As Integer
    goodParametersAvailable = False
    goodParameterCount = GetNumberOfParameters
    ReDim goodParameterNames(goodParameterCount), goodParameterExpressions(goodParameterCount)
    For index = 0 To goodParameterCount - 1
        goodParameterNames(index) = GetParameterName(index)
        goodParameterExpressions(index) = RestoreParameterExpression(goodParameterNames(index))
    Next index
    f = FreeFile
    Open "%PROJECT_PATH%.last-good-parameters.tsv" For Output As #f
    For index = 0 To goodParameterCount - 1
        Print #f, goodParameterNames(index) & Chr(9) & goodParameterExpressions(index)
    Next index
    Close #f
    goodParametersAvailable = True
    CSTPMW_Trace "parameter-checkpoint", "%PROJECT_PATH%.last-good-parameters.tsv", "captured expressions; count=" & CStr(goodParameterCount)
End Sub

Private Sub CSTPMW_RestoreGoodParameters
    Dim index As Long, saved As Long, name As String, found As Boolean
    If Not goodParametersAvailable Then Err.Raise vbObjectError + 2402, "worker", "No valid parameter checkpoint"
    For index = 0 To goodParameterCount - 1
        StoreParameter goodParameterNames(index), goodParameterExpressions(index)
    Next index
    For index = GetNumberOfParameters - 1 To 0 Step -1
        name = GetParameterName(index)
        found = False
        For saved = 0 To goodParameterCount - 1
            If LCase(name) = LCase(goodParameterNames(saved)) Then found = True
        Next saved
        If Not found Then DeleteParameter name
    Next index
    CSTPMW_Trace "restore-parameters", "%PROJECT_PATH%.last-good-parameters.tsv", "restored expressions; new task parameters removed"
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

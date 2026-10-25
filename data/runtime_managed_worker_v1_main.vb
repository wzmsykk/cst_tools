' Long-lived managed Worker v1. Python owns task identity and lifecycle.
Public outFullDir As String
Private goodParameterNames() As String
Private goodParameterExpressions() As String
Private goodParameterExists() As Boolean
Private taskParameterValues() As String
Private appliedParameterCount As Long
Private goodParameterCount As Long
Private goodParametersAvailable As Boolean
Private modelNeedsRecovery As Boolean
Private cancellationRequested As Boolean
Private activeTaskId As String
Private activeTaskSolveReady As Boolean
Private solverReturnedSuccess As Boolean
Private activeTaskOutcome As String
Private currentModelState As String
Private workerRetiring As Boolean

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
    activeTaskOutcome = "not-started"
    currentModelState = "prepared"
    If Dir("%STOP_REQUEST_PATH%") <> "" Then
        CSTPMW_CloseSession
        Exit Sub
    End If
    ' -m -b loads this project before compiling Model/3D/Model.run.
    ' Never OpenFile here: compiling in an empty project loses the parameter
    ' namespace used by CST's internal 3D/DS expression synchronization.
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

        If workerRetiring Then
            ' A failed model must not consume another task, even if one appears.
            Wait 0.1
        ElseIf Dir("%TASK_PATH%") <> "" Then
            stage = "read-task"
            If Not CSTP_ReadTask("%TASK_PATH%", "%SESSION_ID%", task, errorCode, errorMessage) Then
                CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
                Exit Do
            End If

            stage = "parameters"
            activeTaskId = task.TaskId
            activeTaskOutcome = "unknown"
            activeTaskSolveReady = False
            solverReturnedSuccess = False
            cancellationRequested = False
            CSTPMW_CheckStop "before-parameters"
            stage = "parameter-checkpoint"
            CSTPMW_CaptureTaskParameters task
            stage = "parameters"
            modelNeedsRecovery = True
            currentModelState = "dirty"
            For i = 0 To goodParameterCount - 1
                CSTPMW_CheckStop "parameters"
                ' A setter may mutate and then raise: record intent BEFORE calling it.
                appliedParameterCount = i + 1
                StoreParameter goodParameterNames(i), taskParameterValues(i)
            Next i

            stage = "rebuild"
            CSTPMW_CheckStop "before-rebuild"
            rebuilt = Rebuild
            If Not rebuilt Then
                CSTPMW_PublishFailure task, "REBUILD_FAILED", "Rebuild returned False"
                GoTo WaitForAck
            End If

            stage = "solver-config"
            CSTPMW_CheckStop "after-rebuild"
            For i = 0 To task.ParameterCount - 1
                If LCase(task.Parameters(i).Name) = "nmodes" Then
                    requestedModes = RestoreDoubleParameter("nmodes")
                    If requestedModes < 1 Or requestedModes > 32767 Or requestedModes <> Fix(requestedModes) Then Err.Raise vbObjectError + 2202, "worker", "nmodes must be a positive integer"
                    EigenmodeSolver.SetNumberOfModes CInt(requestedModes)
                End If
            Next i
            stage = "solver-start"
            CSTPMW_CheckStop "before-solver"
            CSTPMW_Trace stage, "%PROJECT_PATH%", "calling EigenmodeSolver.Start"
            solverReturn = EigenmodeSolver.Start
            CSTPMW_Trace stage, "%PROJECT_PATH%", "returned=" & CStr(solverReturn)
            If solverReturn <> 1 Then
                CSTPMW_PublishFailure task, "SOLVER_FAILED", "EigenmodeSolver.Start returned " & CStr(solverReturn)
                GoTo WaitForAck
            End If
            solverReturnedSuccess = True

            stage = "solver-result"
            If EigenmodeSolver.GetNumberOfModesCalculated < 1 Then
                CSTPMW_PublishFailure task, "SOLVER_FAILED", "Start returned 1 but no eigenmodes are available"
                GoTo WaitForAck
            End If
            activeTaskSolveReady = True
            CSTPMW_CheckStop "after-solver"

            stage = "postprocess"
            outFullDir = "%RESULT_ROOT%" & task.TaskId & "\"
            If Dir(outFullDir, 16) = "" Then MkDir outFullDir
            CustomPostProcess

            stage = "flush"
            CSTPMW_CheckStop "before-flush"
            Backup outFullDir & "project.cst"
            If FileLen(outFullDir & "project.cst") < 1 Then Err.Raise vbObjectError + 2408, "worker", "Task snapshot is empty"
            currentModelState = "committed"
            goodParametersAvailable = False
            modelNeedsRecovery = False
            activeTaskOutcome = "success"
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
                    If workerRetiring Then
                        CSTPMW_WriteMarker "%MARKER_PATH%", "retiring:" & task.TaskId
                    Else
                        CSTPMW_WriteMarker "%MARKER_PATH%", "ready:" & task.TaskId
                    End If
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
    If cancellationRequested Then
        errorCode = "INTERNAL_ERROR"
        errorMessage = "STOP_REQUESTED: " & errorMessage
    ElseIf stage = "solver-start" Or stage = "solver-result" Then
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
        workerRetiring = True
        If activeTaskId = "" Then activeTaskOutcome = "unknown"
        CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
        Resume CloseWorker
    End If
End Sub

Private Sub CSTPMW_CheckStop(checkpoint As String)
    Dim stopError As String
    If Dir("%STOP_REQUEST_PATH%") = "" Then Exit Sub
    If Not CSTP_ReadStopRequest("%STOP_REQUEST_PATH%", "%SESSION_ID%", stopError) Then
        Err.Raise vbObjectError + 2421, "worker stop", stopError
    End If
    cancellationRequested = True
    CSTPMW_Trace "cancel-checkpoint", checkpoint, "stop requested; no further task steps"
    If activeTaskSolveReady Then
        ' Preserve the solved project; never restore parameters over its results.
        modelNeedsRecovery = False
        outFullDir = "%RESULT_ROOT%" & activeTaskId & "\"
        If Dir(outFullDir, 16) = "" Then MkDir outFullDir
        Backup outFullDir & "interrupted-project.cst"
        If FileLen(outFullDir & "interrupted-project.cst") < 1 Then Err.Raise vbObjectError + 2409, "worker", "Interrupted snapshot is empty"
        currentModelState = "committed"
        CSTPMW_Trace "interrupted-solve", outFullDir, "saved; postprocess/acceptance not complete"
    End If
    Err.Raise vbObjectError + 2420, "worker stop", "Stopped at " & checkpoint
End Sub

Private Sub CSTPMW_CloseSession
    Dim closeStage As String
    Dim message As String
    Dim stopRequested As Boolean
    Dim recovered As Boolean
    Dim recoveryFile As Integer
    Dim closeReceipt As CSTC2_CloseReceipt
    Dim failureDetail As String
    On Error GoTo CloseFailed
    closeReceipt.SessionId = "%SESSION_ID%"
    closeReceipt.LastTaskId = activeTaskId
    If closeReceipt.LastTaskId = "" Then closeReceipt.LastTaskId = "none"
    closeReceipt.TaskOutcome = activeTaskOutcome
    closeReceipt.CloseOrigin = "worker-failure"
    closeReceipt.LastCompletedPhase = "none"
    closeReceipt.SnapshotRef = "none"
    closeReceipt.SnapshotBytes = "0"
    stopRequested = (Dir("%STOP_REQUEST_PATH%") <> "")
    closeStage = "stop-read"
    If stopRequested Then
        If Not CSTP_ReadStopRequest("%STOP_REQUEST_PATH%", "%SESSION_ID%", message) Then
            CSTPMW_Trace closeStage, "%STOP_REQUEST_PATH%", message
            Err.Raise vbObjectError + 2404, "worker", "Invalid stop request: " & message
        End If
        closeReceipt.CloseOrigin = "stop-request"
    End If
    ' Start succeeded and produced modes: never Rebuild merely because a
    ' required postprocessor, Backup or parameter-checkpoint writer failed.
    If activeTaskSolveReady Or solverReturnedSuccess Then
        modelNeedsRecovery = False
    End If
    If modelNeedsRecovery Then
        closeStage = "restore-parameters"
        CSTPMW_RestoreGoodParameters
        closeReceipt.LastCompletedPhase = "restore"
        closeStage = "recovery-rebuild"
        CSTPMW_Trace closeStage, "%PROJECT_PATH%", "begin; no Solver replay"
        If Not Rebuild Then Err.Raise vbObjectError + 2401, "worker", "Recovery Rebuild returned False"
        closeReceipt.LastCompletedPhase = "rebuild"
        currentModelState = "unknown"
        modelNeedsRecovery = False
        recovered = True
        CSTPMW_Trace closeStage, "%PROJECT_PATH%", "returned True"
        closeStage = "recovery-snapshot"
        CSTPMW_Trace closeStage, "%PROJECT_PATH%.recovered.cst", "begin"
        Backup "%PROJECT_PATH%.recovered.cst"
        If FileLen("%PROJECT_PATH%.recovered.cst") < 1 Then Err.Raise vbObjectError + 2403, "worker", "Recovery snapshot is empty"
        closeReceipt.LastCompletedPhase = "backup"
        CSTPMW_Trace closeStage, "%PROJECT_PATH%.recovered.cst", "returned; bytes=" & CStr(FileLen("%PROJECT_PATH%.recovered.cst"))
    End If
    closeStage = "save"
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "begin"
    Save
    If FileLen("%PROJECT_PATH%") < 1 Then Err.Raise vbObjectError + 2405, "worker", "Saved project is empty"
    closeReceipt.LastCompletedPhase = "save"
    If activeTaskSolveReady Or solverReturnedSuccess Then currentModelState = "committed"
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "returned"
    If recovered Then
        closeStage = "recovery-receipt"
        CSTPMW_Trace closeStage, "%PROJECT_PATH%.recovery-saved", "begin"
        recoveryFile = FreeFile
        Open "%PROJECT_PATH%.recovery-saved" For Output As #recoveryFile
        Print #recoveryFile, "CST_RECOVERY_SAVED_V1"
        Print #recoveryFile, "%SESSION_ID%"
        Close #recoveryFile
        recoveryFile = 0
        currentModelState = "restored-saved"
        CSTPMW_Trace closeStage, "%PROJECT_PATH%.recovery-saved", "returned"
    End If
    closeReceipt.ModelState = currentModelState
    closeReceipt.CloseOutcome = "saved"
    ' Batch shutdown may rewrite the active project after Save returns.
    ' Bind the receipt to an immutable Backup, not that mutable active file.
    If Not recovered Then
        closeStage = "close-snapshot"
        CSTPMW_Trace closeStage, "%PROJECT_PATH%.closed.cst", "begin; immutable close evidence"
        Backup "%PROJECT_PATH%.closed.cst"
        If FileLen("%PROJECT_PATH%.closed.cst") < 1 Then Err.Raise vbObjectError + 2408, "worker", "Close snapshot is empty"
        closeReceipt.SnapshotRef = "worker-input.cst.closed.cst"
        closeReceipt.SnapshotBytes = CStr(FileLen("%PROJECT_PATH%.closed.cst"))
        CSTPMW_Trace closeStage, "%PROJECT_PATH%.closed.cst", "returned; bytes=" & closeReceipt.SnapshotBytes
    End If
    If recovered Then
        closeReceipt.CloseOutcome = "restored-saved"
        closeReceipt.SnapshotRef = "worker-input.cst.recovered.cst"
        closeReceipt.SnapshotBytes = CStr(FileLen("%PROJECT_PATH%.recovered.cst"))
    End If
    closeReceipt.ErrorCode = "none"
    closeStage = "close-receipt"
    CSTPMW_Trace closeStage, "%CLOSE_RECEIPT_PATH%", "begin"
    If Not CSTC2_WriteCloseReceipt("%CLOSE_RECEIPT_PATH%", closeReceipt, message) Then Err.Raise vbObjectError + 2406, "worker", message
    CSTPMW_Trace closeStage, "%CLOSE_RECEIPT_PATH%", "returned"
    If stopRequested Then
        closeStage = "stop-ack"
        CSTPMW_Trace closeStage, "%STOP_ACK_PATH%", "begin"
        If Not CSTP_WriteStopAck("%STOP_ACK_PATH%", "%SESSION_ID%", message) Then
            CSTPMW_Trace closeStage, "%STOP_ACK_PATH%", message
            Err.Raise vbObjectError + 2407, "worker", message
        End If
        CSTPMW_Trace closeStage, "%STOP_ACK_PATH%", "returned"
    End If
    If Dir("%COMPLETION_PATH%") <> "" Then
        CSTPMW_WriteMarker "%MARKER_PATH%", "stopped-with-completion"
    Else
        CSTPMW_WriteMarker "%MARKER_PATH%", "stopped"
    End If
    ' This worker is launched with -m as a batch macro. Quit here attempts
    ' to close its own sheet while the batch is still active. Return through
    ' Main instead; the batch runner closes the saved project normally.
    closeStage = "batch-return"
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", "saved; returning to batch runner; Python must verify StopAck and process exit"
    Exit Sub
CloseFailed:
    message = "shutdown " & closeStage & " failed: number=" & CStr(Err.Number) & "; description=" & Err.Description
    failureDetail = message
    CSTPMW_Trace closeStage, "%PROJECT_PATH%", message
    On Error Resume Next
    If recoveryFile <> 0 Then Close #recoveryFile
    closeReceipt.CloseOutcome = "failed"
    closeReceipt.ModelState = currentModelState
    closeReceipt.SnapshotRef = "none"
    closeReceipt.SnapshotBytes = "0"
    closeReceipt.ErrorCode = "CLOSE_INTERNAL_ERROR"
    If closeStage = "stop-read" Or closeStage = "stop-ack" Then closeReceipt.ErrorCode = "CLOSE_PROTOCOL_ERROR"
    If closeStage = "restore-parameters" Then
        closeReceipt.ErrorCode = "CLOSE_RESTORE_FAILED"
        closeReceipt.ModelState = "restore-failed"
    End If
    If closeStage = "recovery-rebuild" Then
        closeReceipt.ErrorCode = "CLOSE_REBUILD_FAILED"
        closeReceipt.ModelState = "restore-failed"
    End If
    If closeStage = "recovery-snapshot" Or closeStage = "close-snapshot" Then closeReceipt.ErrorCode = "CLOSE_BACKUP_FAILED"
    If closeStage = "save" Then closeReceipt.ErrorCode = "CLOSE_SAVE_FAILED"
    If closeStage = "recovery-receipt" Or closeStage = "close-receipt" Then closeReceipt.ErrorCode = "CLOSE_RECEIPT_FAILED"
    ' This may fail if a positive receipt already exists: never overwrite it.
    If Not CSTC2_WriteCloseReceipt("%CLOSE_RECEIPT_PATH%", closeReceipt, message) Then
        CSTPMW_Trace "close-receipt-failed", "%CLOSE_RECEIPT_PATH%", message
    End If
    CSTPMW_WriteMarker "%MARKER_PATH%", "failure:" & failureDetail
    On Error GoTo 0
    ' Do not retry Save, overwrite Completion, or Quit with unsaved changes.
End Sub

Private Sub CSTPMW_CaptureTaskParameters(ByRef task As CSTP_Task)
    Dim index As Long, prior As Long, f As Integer
    Dim name As String, expression As String, existed As Boolean
    Dim failureNumber As Long, failureDescription As String
    On Error GoTo CaptureFailed
    goodParametersAvailable = False
    goodParameterCount = 0
    appliedParameterCount = 0
    ReDim goodParameterNames(task.ParameterCount), goodParameterExpressions(task.ParameterCount)
    ReDim goodParameterExists(task.ParameterCount), taskParameterValues(task.ParameterCount)
    For index = 0 To task.ParameterCount - 1
        name = task.Parameters(index).Name
        For prior = 0 To index - 1
            If LCase(name) = LCase(task.Parameters(prior).Name) Then Err.Raise vbObjectError + 2410, "worker", "Duplicate task parameter: " & name
        Next prior
        existed = DoesParameterExist(name)
        expression = ""
        If existed Then expression = RestoreParameterExpression(name)
        If Not existed Or expression <> task.Parameters(index).Value Then
            goodParameterNames(goodParameterCount) = name
            goodParameterExpressions(goodParameterCount) = expression
            goodParameterExists(goodParameterCount) = existed
            taskParameterValues(goodParameterCount) = task.Parameters(index).Value
            goodParameterCount = goodParameterCount + 1
        End If
    Next index
    ' Versioned task-scoped undo evidence, fully closed before the first setter.
    f = FreeFile
    Open "%PROJECT_PATH%.last-good-parameters.tsv" For Output As #f
    Print #f, "CST_PARAMETER_UNDO_V2"
    Print #f, "%SESSION_ID%" & Chr(9) & task.TaskId
    For index = 0 To goodParameterCount - 1
        Print #f, goodParameterNames(index) & Chr(9) & CStr(goodParameterExists(index)) & Chr(9) & CSTPMW_UndoText(goodParameterExpressions(index))
    Next index
    Close #f
    f = 0
    goodParametersAvailable = True
    CSTPMW_Trace "parameter-checkpoint", "%PROJECT_PATH%.last-good-parameters.tsv", "task undo ready; requested=" & CStr(task.ParameterCount) & "; changed=" & CStr(goodParameterCount)
    Exit Sub
CaptureFailed:
    failureNumber = Err.Number
    failureDescription = Err.Description
    On Error Resume Next
    If f <> 0 Then Close #f
    On Error GoTo 0
    Err.Raise failureNumber, "parameter checkpoint", failureDescription
End Sub

Private Function CSTPMW_UndoText(ByVal value As String) As String
    CSTPMW_UndoText = Replace(Replace(Replace(Replace(value, "\", "\\"), Chr(9), "\t"), vbCr, "\r"), vbLf, "\n")
End Function

Private Sub CSTPMW_RestoreGoodParameters
    Dim index As Long, restored As Long, removed As Long, slot As Long
    Dim names() As String, expressions() As String
    If Not goodParametersAvailable Then Err.Raise vbObjectError + 2402, "worker", "No valid task undo checkpoint"
    CSTPMW_Trace "restore-parameters", "%PROJECT_PATH%.last-good-parameters.tsv", "begin; attempted=" & CStr(appliedParameterCount)
    For index = 0 To appliedParameterCount - 1
        If goodParameterExists(index) Then restored = restored + 1
    Next index
    If restored > 0 Then
        ReDim names(0 To restored - 1), expressions(0 To restored - 1)
        For index = 0 To appliedParameterCount - 1
            If goodParameterExists(index) Then
                names(slot) = goodParameterNames(index)
                expressions(slot) = goodParameterExpressions(index)
                slot = slot + 1
            End If
        Next index
        CSTPMW_Trace "restore-batch", "%PROJECT_PATH%", "begin; count=" & CStr(restored)
        StoreParameters(names, expressions)
        CSTPMW_Trace "restore-batch", "%PROJECT_PATH%", "returned; count=" & CStr(restored)
    End If
    CSTPMW_Trace "restore-delete", "%PROJECT_PATH%", "begin"
    For index = appliedParameterCount - 1 To 0 Step -1
        If Not goodParameterExists(index) Then
            If DoesParameterExist(goodParameterNames(index)) Then
                DeleteParameter goodParameterNames(index)
                removed = removed + 1
            End If
        End If
    Next index
    CSTPMW_Trace "restore-delete", "%PROJECT_PATH%", "returned; removed=" & CStr(removed)
    CSTPMW_Trace "restore-verify", "%PROJECT_PATH%", "begin"
    For index = 0 To appliedParameterCount - 1
        If goodParameterExists(index) Then
            If Not DoesParameterExist(goodParameterNames(index)) Then Err.Raise vbObjectError + 2402, "worker", "Restored parameter missing: " & goodParameterNames(index)
            If RestoreParameterExpression(goodParameterNames(index)) <> goodParameterExpressions(index) Then Err.Raise vbObjectError + 2402, "worker", "Restored expression mismatch: " & goodParameterNames(index)
        Else
            If DoesParameterExist(goodParameterNames(index)) Then Err.Raise vbObjectError + 2402, "worker", "Added parameter still exists: " & goodParameterNames(index)
        End If
    Next index
    CSTPMW_Trace "restore-verify", "%PROJECT_PATH%", "returned"
    CSTPMW_Trace "restore-parameters", "%PROJECT_PATH%.last-good-parameters.tsv", "restored task expressions; new task parameters removed"
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
    workerRetiring = True
    activeTaskOutcome = "failure"
    If cancellationRequested Then activeTaskOutcome = "cancelled"
    ' The close path must preserve the only solved field data, even if the
    ' task's required postprocessing or result snapshot failed.
    If activeTaskSolveReady Or solverReturnedSuccess Then
        modelNeedsRecovery = False
    End If
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

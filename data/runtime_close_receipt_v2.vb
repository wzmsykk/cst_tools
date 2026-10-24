' Close receipt v2 library. Concatenate after runtime_protocol_v1.vb.
Public Const CSTC2_MAGIC As String = "CST_CLOSE_RECEIPT_V2"

Public Type CSTC2_CloseReceipt
    SessionId As String
    LastTaskId As String
    CloseOrigin As String
    TaskOutcome As String
    CloseOutcome As String
    ModelState As String
    LastCompletedPhase As String
    SnapshotRef As String
    SnapshotBytes As String
    ErrorCode As String
End Type

Private Function CSTC2_OneOf(ByVal value As String, ByVal choices As String) As Boolean
    CSTC2_OneOf = False
    If value = "" Or InStr(value, "|") > 0 Then Exit Function
    CSTC2_OneOf = InStr("|" & choices & "|", "|" & value & "|") > 0
End Function

Private Function CSTC2_IsUuid(ByVal value As String) As Boolean
    CSTC2_IsUuid = CSTP_IsUuid(value) And value = LCase(value)
End Function

Private Function CSTC2_IsSize(ByVal value As String) As Boolean
    CSTC2_IsSize = False
    If Not CSTP_IsNonNegativeInteger(value) Then Exit Function
    If Len(value) > 19 Then Exit Function
    If Len(value) > 1 And Left(value, 1) = "0" Then Exit Function
    If Len(value) = 19 Then
        If StrComp(value, "9223372036854775807", 0) > 0 Then Exit Function
    End If
    CSTC2_IsSize = True
End Function

Private Function CSTC2_Validate(ByRef receipt As CSTC2_CloseReceipt, ByRef errorMessage As String) As Boolean
    CSTC2_Validate = False
    errorMessage = "invalid close receipt identity or enum"
    If Not CSTC2_IsUuid(receipt.SessionId) Then Exit Function
    If receipt.LastTaskId <> "none" Then
        If Not CSTC2_IsUuid(receipt.LastTaskId) Then Exit Function
    End If
    If Not CSTC2_OneOf(receipt.CloseOrigin, "stop-request|worker-failure") Then Exit Function
    If Not CSTC2_OneOf(receipt.TaskOutcome, "not-started|success|failure|cancelled|unknown") Then Exit Function
    If Not CSTC2_OneOf(receipt.CloseOutcome, "saved|restored-saved|failed") Then Exit Function
    If Not CSTC2_OneOf(receipt.ModelState, "prepared|committed|dirty|restored-saved|restore-failed|unknown") Then Exit Function
    If Not CSTC2_OneOf(receipt.LastCompletedPhase, "none|restore|rebuild|backup|save|receipt") Then Exit Function
    If Not CSTC2_OneOf(receipt.SnapshotRef, "none|worker-input.cst|worker-input.cst.recovered.cst|worker-input.cst.closed.cst") Then Exit Function
    If Not CSTC2_OneOf(receipt.ErrorCode, "none|CLOSE_RESTORE_FAILED|CLOSE_REBUILD_FAILED|CLOSE_BACKUP_FAILED|CLOSE_SAVE_FAILED|CLOSE_RECEIPT_FAILED|CLOSE_PROTOCOL_ERROR|CLOSE_INTERNAL_ERROR") Then Exit Function
    If Not CSTC2_IsSize(receipt.SnapshotBytes) Then Exit Function
    errorMessage = "close receipt fields are inconsistent"
    If receipt.LastTaskId = "none" Then
        If Not CSTC2_OneOf(receipt.TaskOutcome, "not-started|unknown") Then Exit Function
    Else
        If receipt.TaskOutcome = "not-started" Then Exit Function
    End If
    If (receipt.SnapshotRef = "none") <> (receipt.SnapshotBytes = "0") Then Exit Function
    If (receipt.CloseOutcome = "failed") <> (receipt.ErrorCode <> "none") Then Exit Function
    If receipt.CloseOutcome <> "failed" Then
        If Not CSTC2_OneOf(receipt.LastCompletedPhase, "save|receipt") Then Exit Function
        If receipt.SnapshotBytes = "0" Then Exit Function
        If receipt.CloseOutcome = "saved" Then
            If Not CSTC2_OneOf(receipt.ModelState, "prepared|committed") Then Exit Function
            If Not CSTC2_OneOf(receipt.SnapshotRef, "worker-input.cst|worker-input.cst.closed.cst") Then Exit Function
        Else
            If receipt.ModelState <> "restored-saved" Then Exit Function
            If receipt.SnapshotRef <> "worker-input.cst.recovered.cst" Then Exit Function
        End If
    End If
    errorMessage = ""
    CSTC2_Validate = True
End Function

Private Sub CSTC2_Fields(ByRef receipt As CSTC2_CloseReceipt, ByRef keys() As String, ByRef values() As String)
    ReDim keys(0 To 9)
    ReDim values(0 To 9)
    keys(0) = "session_id": values(0) = receipt.SessionId
    keys(1) = "last_task_id": values(1) = receipt.LastTaskId
    keys(2) = "close_origin": values(2) = receipt.CloseOrigin
    keys(3) = "task_outcome": values(3) = receipt.TaskOutcome
    keys(4) = "close_outcome": values(4) = receipt.CloseOutcome
    keys(5) = "model_state": values(5) = receipt.ModelState
    keys(6) = "last_completed_phase": values(6) = receipt.LastCompletedPhase
    keys(7) = "snapshot_ref": values(7) = receipt.SnapshotRef
    keys(8) = "snapshot_bytes": values(8) = receipt.SnapshotBytes
    keys(9) = "error_code": values(9) = receipt.ErrorCode
End Sub

Public Function CSTC2_ReadCloseReceipt( _
    ByVal filePath As String, ByVal expectedSessionId As String, _
    ByVal expectedTaskId As String, ByRef receipt As CSTC2_CloseReceipt, _
    ByRef errorMessage As String) As Boolean

    Dim keys() As String, values() As String
    Dim fieldCount As Long
    CSTC2_ReadCloseReceipt = False
    errorMessage = ""
    On Error GoTo ReadFailed
    If FileLen(filePath) > 4096 Then
        errorMessage = "oversized close receipt"
        Exit Function
    End If
    If Not CSTP_LoadFields(filePath, CSTC2_MAGIC, keys, values, fieldCount, errorMessage) Then Exit Function
    If fieldCount <> 10 Then
        errorMessage = "close receipt contains missing or unknown fields"
        Exit Function
    End If
    If Not CSTP_GetRequired(keys, values, fieldCount, "session_id", receipt.SessionId, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "last_task_id", receipt.LastTaskId, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "close_origin", receipt.CloseOrigin, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "task_outcome", receipt.TaskOutcome, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "close_outcome", receipt.CloseOutcome, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "model_state", receipt.ModelState, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "last_completed_phase", receipt.LastCompletedPhase, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "snapshot_ref", receipt.SnapshotRef, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "snapshot_bytes", receipt.SnapshotBytes, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "error_code", receipt.ErrorCode, errorMessage) Then Exit Function
    If Not CSTC2_Validate(receipt, errorMessage) Then Exit Function
    If receipt.SessionId <> expectedSessionId Or receipt.LastTaskId <> expectedTaskId Then
        errorMessage = "close receipt belongs to another session/task"
        Exit Function
    End If
    CSTC2_ReadCloseReceipt = True
    Exit Function
ReadFailed:
    errorMessage = "close receipt read failed: " & Err.Description
End Function

Private Function CSTC2_Same(ByRef leftReceipt As CSTC2_CloseReceipt, ByRef rightReceipt As CSTC2_CloseReceipt) As Boolean
    Dim leftKeys() As String, leftValues() As String
    Dim rightKeys() As String, rightValues() As String
    Dim i As Long
    CSTC2_Fields leftReceipt, leftKeys, leftValues
    CSTC2_Fields rightReceipt, rightKeys, rightValues
    CSTC2_Same = False
    For i = 0 To 9
        If leftValues(i) <> rightValues(i) Then Exit Function
    Next i
    CSTC2_Same = True
End Function

Public Function CSTC2_WriteCloseReceipt( _
    ByVal filePath As String, ByRef receipt As CSTC2_CloseReceipt, _
    ByRef errorMessage As String) As Boolean

    Dim keys() As String, values() As String
    Dim existing As CSTC2_CloseReceipt
    CSTC2_WriteCloseReceipt = False
    errorMessage = ""
    On Error GoTo WriteFailed
    If Not CSTC2_Validate(receipt, errorMessage) Then Exit Function
    If Dir(filePath) <> "" Then
        If Not CSTC2_ReadCloseReceipt(filePath, receipt.SessionId, receipt.LastTaskId, existing, errorMessage) Then Exit Function
        If Not CSTC2_Same(receipt, existing) Then
            errorMessage = "conflicting immutable close receipt"
            Exit Function
        End If
        CSTC2_WriteCloseReceipt = True
        Exit Function
    End If
    CSTC2_Fields receipt, keys, values
    CSTC2_WriteCloseReceipt = CSTP_AtomicWrite(filePath, CSTC2_MAGIC, keys, values, 10, errorMessage)
    Exit Function
WriteFailed:
    errorMessage = "close receipt write failed: " & Err.Description
End Function

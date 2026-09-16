' Minimal CST Python/VBA file protocol codec.
' Library module: intentionally has no executable entry point.

Public Const CSTP_TASK_MAGIC As String = "CST_TASK_V1"
Public Const CSTP_COMPLETION_MAGIC As String = "CST_COMPLETION_V1"
Public Const CSTP_ACK_MAGIC As String = "CST_ACK_V1"

Public Type CSTP_Parameter
    Name As String
    Kind As String
    Value As String
End Type

Public Type CSTP_Task
    TaskId As String
    SessionId As String
    ParameterCount As Long
    Parameters() As CSTP_Parameter
End Type

Public Function CSTP_ReadTask( _
    ByVal filePath As String, _
    ByVal expectedSessionId As String, _
    ByRef task As CSTP_Task, _
    ByRef errorCode As String, _
    ByRef errorMessage As String) As Boolean

    Dim keys() As String
    Dim values() As String
    Dim fieldCount As Long
    Dim countText As String
    Dim i As Long
    Dim prefix As String

    CSTP_ReadTask = False
    errorCode = ""
    errorMessage = ""

    If Not CSTP_LoadFields(filePath, CSTP_TASK_MAGIC, keys, values, fieldCount, errorMessage) Then
        errorCode = "INVALID_TASK"
        Exit Function
    End If

    If Not CSTP_GetRequired(keys, values, fieldCount, "task_id", task.TaskId, errorMessage) Then GoTo InvalidTask
    If Not CSTP_GetRequired(keys, values, fieldCount, "session_id", task.SessionId, errorMessage) Then GoTo InvalidTask
    If Not CSTP_GetRequired(keys, values, fieldCount, "parameter_count", countText, errorMessage) Then GoTo InvalidTask

    If Not CSTP_IsUuid(task.TaskId) Then
        errorMessage = "task_id is not a canonical UUID"
        GoTo InvalidTask
    End If
    If task.SessionId <> expectedSessionId Then
        errorMessage = "task belongs to another worker session"
        GoTo InvalidTask
    End If
    If Not CSTP_IsNonNegativeInteger(countText) Then
        errorMessage = "parameter_count is not a non-negative integer"
        GoTo InvalidTask
    End If

    task.ParameterCount = CLng(countText)
    If fieldCount <> 3 + task.ParameterCount * 3 Then
        errorMessage = "task contains missing or unknown fields"
        GoTo InvalidTask
    End If

    If task.ParameterCount > 0 Then
        ReDim task.Parameters(0 To task.ParameterCount - 1)
    Else
        ReDim task.Parameters(0 To 0)
    End If

    For i = 0 To task.ParameterCount - 1
        prefix = "param." & CStr(i) & "."
        If Not CSTP_GetRequired(keys, values, fieldCount, prefix & "name", task.Parameters(i).Name, errorMessage) Then GoTo InvalidTask
        If Not CSTP_GetRequired(keys, values, fieldCount, prefix & "kind", task.Parameters(i).Kind, errorMessage) Then GoTo InvalidTask
        If Not CSTP_GetRequired(keys, values, fieldCount, prefix & "value", task.Parameters(i).Value, errorMessage) Then GoTo InvalidTask
        If task.Parameters(i).Kind <> "literal" And task.Parameters(i).Kind <> "expression" Then
            errorMessage = "unsupported parameter kind"
            GoTo InvalidTask
        End If
        If CSTP_HasDuplicateParameter(task, i) Then
            errorMessage = "duplicate parameter name"
            GoTo InvalidTask
        End If
    Next i

    CSTP_ReadTask = True
    Exit Function

InvalidTask:
    errorCode = "INVALID_TASK"
End Function

Public Function CSTP_WriteCompletion( _
    ByVal filePath As String, _
    ByVal taskId As String, _
    ByVal sessionId As String, _
    ByVal succeeded As Boolean, _
    ByVal failureCode As String, _
    ByVal failureMessage As String, _
    ByRef errorMessage As String) As Boolean

    Dim keys() As String
    Dim values() As String
    Dim fieldCount As Long

    CSTP_WriteCompletion = False
    errorMessage = ""
    If Not CSTP_IsUuid(taskId) Or Not CSTP_IsUuid(sessionId) Then
        errorMessage = "completion identity is invalid"
        Exit Function
    End If

    If succeeded Then
        fieldCount = 3
        ReDim keys(0 To 2)
        ReDim values(0 To 2)
    Else
        If failureCode = "" Or failureMessage = "" Then
            errorMessage = "failed completion requires error details"
            Exit Function
        End If
        fieldCount = 5
        ReDim keys(0 To 4)
        ReDim values(0 To 4)
    End If

    keys(0) = "task_id": values(0) = taskId
    keys(1) = "session_id": values(1) = sessionId
    keys(2) = "status"
    If succeeded Then
        values(2) = "success"
    Else
        values(2) = "failure"
        keys(3) = "error_code": values(3) = failureCode
        keys(4) = "error_message": values(4) = failureMessage
    End If

    CSTP_WriteCompletion = CSTP_AtomicWrite(filePath, CSTP_COMPLETION_MAGIC, keys, values, fieldCount, errorMessage)
End Function

Public Function CSTP_ReadAck( _
    ByVal filePath As String, _
    ByVal expectedTaskId As String, _
    ByVal expectedSessionId As String, _
    ByRef errorMessage As String) As Boolean

    Dim keys() As String
    Dim values() As String
    Dim fieldCount As Long
    Dim taskId As String
    Dim sessionId As String

    CSTP_ReadAck = False
    errorMessage = ""
    If Not CSTP_LoadFields(filePath, CSTP_ACK_MAGIC, keys, values, fieldCount, errorMessage) Then Exit Function
    If fieldCount <> 2 Then
        errorMessage = "ack contains missing or unknown fields"
        Exit Function
    End If
    If Not CSTP_GetRequired(keys, values, fieldCount, "task_id", taskId, errorMessage) Then Exit Function
    If Not CSTP_GetRequired(keys, values, fieldCount, "session_id", sessionId, errorMessage) Then Exit Function
    If taskId <> expectedTaskId Or sessionId <> expectedSessionId Then
        errorMessage = "ack does not match active task"
        Exit Function
    End If
    CSTP_ReadAck = True
End Function

Private Function CSTP_LoadFields( _
    ByVal filePath As String, _
    ByVal expectedMagic As String, _
    ByRef keys() As String, _
    ByRef values() As String, _
    ByRef fieldCount As Long, _
    ByRef errorMessage As String) As Boolean

    Dim fileNumber As Integer
    Dim magic As String
    Dim key As String
    Dim value As String
    Dim i As Long

    CSTP_LoadFields = False
    fieldCount = 0
    On Error GoTo ReadFailed
    fileNumber = FreeFile
    Open filePath For Input As #fileNumber
    If EOF(fileNumber) Then
        errorMessage = "protocol file is empty"
        Close #fileNumber
        Exit Function
    End If
    Line Input #fileNumber, magic
    If magic <> expectedMagic Then
        errorMessage = "unexpected protocol header"
        Close #fileNumber
        Exit Function
    End If

    Do While Not EOF(fileNumber)
        Line Input #fileNumber, key
        If EOF(fileNumber) Then
            errorMessage = "incomplete key/value pair"
            Close #fileNumber
            Exit Function
        End If
        Line Input #fileNumber, value
        If key = "" Or value = "" Then
            errorMessage = "empty protocol key or value"
            Close #fileNumber
            Exit Function
        End If
        For i = 0 To fieldCount - 1
            If keys(i) = key Then
                errorMessage = "duplicate protocol field"
                Close #fileNumber
                Exit Function
            End If
        Next i
        If fieldCount = 0 Then
            ReDim keys(0 To 0)
            ReDim values(0 To 0)
        Else
            ReDim Preserve keys(0 To fieldCount)
            ReDim Preserve values(0 To fieldCount)
        End If
        keys(fieldCount) = key
        values(fieldCount) = value
        fieldCount = fieldCount + 1
    Loop
    Close #fileNumber
    CSTP_LoadFields = True
    Exit Function

ReadFailed:
    errorMessage = "protocol read failed: " & Err.Description
    On Error Resume Next
    Close #fileNumber
    On Error GoTo 0
End Function

Private Function CSTP_AtomicWrite( _
    ByVal filePath As String, _
    ByVal magic As String, _
    ByRef keys() As String, _
    ByRef values() As String, _
    ByVal fieldCount As Long, _
    ByRef errorMessage As String) As Boolean

    Dim tempPath As String
    Dim fileNumber As Integer
    Dim i As Long

    CSTP_AtomicWrite = False
    tempPath = filePath & ".tmp"
    If Dir(filePath) <> "" Or Dir(tempPath) <> "" Then
        errorMessage = "protocol output already exists"
        Exit Function
    End If

    On Error GoTo WriteFailed
    fileNumber = FreeFile
    Open tempPath For Output As #fileNumber
    Print #fileNumber, magic
    For i = 0 To fieldCount - 1
        Print #fileNumber, keys(i)
        Print #fileNumber, values(i)
    Next i
    Close #fileNumber
    Name tempPath As filePath
    CSTP_AtomicWrite = True
    Exit Function

WriteFailed:
    errorMessage = "protocol write failed: " & Err.Description
    On Error Resume Next
    Close #fileNumber
    On Error GoTo 0
End Function

Private Function CSTP_GetRequired( _
    ByRef keys() As String, _
    ByRef values() As String, _
    ByVal fieldCount As Long, _
    ByVal wantedKey As String, _
    ByRef result As String, _
    ByRef errorMessage As String) As Boolean

    Dim i As Long
    CSTP_GetRequired = False
    For i = 0 To fieldCount - 1
        If keys(i) = wantedKey Then
            result = values(i)
            CSTP_GetRequired = True
            Exit Function
        End If
    Next i
    errorMessage = "missing field: " & wantedKey
End Function

Private Function CSTP_HasDuplicateParameter(ByRef task As CSTP_Task, ByVal lastIndex As Long) As Boolean
    Dim i As Long
    CSTP_HasDuplicateParameter = False
    For i = 0 To lastIndex - 1
        If task.Parameters(i).Name = task.Parameters(lastIndex).Name Then
            CSTP_HasDuplicateParameter = True
            Exit Function
        End If
    Next i
End Function

Private Function CSTP_IsNonNegativeInteger(ByVal value As String) As Boolean
    Dim i As Long
    CSTP_IsNonNegativeInteger = False
    If value = "" Then Exit Function
    For i = 1 To Len(value)
        If Mid(value, i, 1) < "0" Or Mid(value, i, 1) > "9" Then Exit Function
    Next i
    CSTP_IsNonNegativeInteger = True
End Function

Private Function CSTP_IsUuid(ByVal value As String) As Boolean
    Dim compact As String
    Dim i As Long
    Dim c As String

    CSTP_IsUuid = False
    If Len(value) <> 36 Then Exit Function
    If Mid(value, 9, 1) <> "-" Or Mid(value, 14, 1) <> "-" Or Mid(value, 19, 1) <> "-" Or Mid(value, 24, 1) <> "-" Then Exit Function
    compact = Replace(value, "-", "")
    If Len(compact) <> 32 Then Exit Function
    For i = 1 To 32
        c = LCase(Mid(compact, i, 1))
        If InStr("0123456789abcdef", c) = 0 Then Exit Function
    Next i
    CSTP_IsUuid = True
End Function

Sub Main
    Dim task As CSTP_Task
    Dim errorCode As String
    Dim errorMessage As String
    Dim completionError As String
    Dim acknowledged As Boolean
    Dim i As Long

    If Not CSTP_ReadTask("%TASK_PATH%", "%SESSION_ID%", task, errorCode, errorMessage) Then
        CSTPC_WriteMarker "%MARKER_PATH%", "failure:" & errorCode & ":" & errorMessage
        Exit Sub
    End If

    If task.ParameterCount <> 2 Then
        CSTPC_WriteMarker "%MARKER_PATH%", "failure:unexpected parameter count"
        Exit Sub
    End If
    If task.Parameters(0).Kind <> "literal" Or task.Parameters(1).Kind <> "expression" Then
        CSTPC_WriteMarker "%MARKER_PATH%", "failure:parameter kinds changed"
        Exit Sub
    End If

    If Not CSTP_WriteCompletion("%COMPLETION_PATH%", task.TaskId, task.SessionId, True, "", "", completionError) Then
        CSTPC_WriteMarker "%MARKER_PATH%", "failure:" & completionError
        Exit Sub
    End If

    acknowledged = False
    For i = 1 To 300
        If Dir("%ACK_PATH%") <> "" Then
            If CSTP_ReadAck("%ACK_PATH%", task.TaskId, task.SessionId, errorMessage) Then
                acknowledged = True
                Exit For
            Else
                CSTPC_WriteMarker "%MARKER_PATH%", "failure:" & errorMessage
                Exit Sub
            End If
        End If
        Wait 0.1
    Next i

    If acknowledged Then
        CSTPC_WriteMarker "%MARKER_PATH%", "success"
    Else
        CSTPC_WriteMarker "%MARKER_PATH%", "failure:ack timeout"
    End If
End Sub

Private Sub CSTPC_WriteMarker(ByVal filePath As String, ByVal message As String)
    Dim fileNumber As Integer
    fileNumber = FreeFile
    Open filePath For Output As #fileNumber
    Print #fileNumber, message
    Close #fileNumber
End Sub

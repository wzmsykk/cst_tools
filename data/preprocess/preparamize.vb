Const preprocessdonestr As String="PPSDONE"
'''IMPORT COMMON HEADERS
'ReportInformation
Sub setFreqRange(fmin As Double,fmax As Double)
    'check existence
    Dim flag As Boolean
    flag=DoesParameterExist("fmin") 
    If flag=False Then
        StoreParameterWithDescription "fmin" fmin "Minimum Freq For Solver"
    ElseIf
        ReportInformation("Fmin Already Exists")
    End If
    flag=DoesParameterExist("fmax") 
    If flag=False Then
        StoreParameterWithDescription "fmax" fmax "Maximum Freq For Solver"
    ElseIf
        ReportInformation("Fmax Already Exists")
    End If
    Solver.FrequencyRange "fmin", "fmax"
    ReportInformation("FrequencyRange Set As fmin, fmax")    
End Sub
Sub setEigenSolver(nmodes As Integer)
    Dim flag As Boolean
    Dim uint As Integer
    Dim udouble As Double
    flag=DoesParameterExist("fmin") 
    If flag=False Then
        StoreParameterWithDescription "fmin" 0 "Minimum Freq For Solver"
        ReportInformation("Fmin Not Exists Set Default Value As 0 MHZ")
    ElseIf
        ReportInformation("Found Existing Fmin")
    End If    
    flag=DoesParameterExist("nmodes") 
    If flag=False Then
        StoreParameterWithDescription "nmodes" nmodes "Min Mode Num to Calc"        
        ReportInformation("nmodes set As " & nmodes)
    ElseIf
        uint=RestoreParameter("nmodes") 
        ReportInformation("Found Existing nmodes" & uint)
    End If    
    With EigenmodeSolver 
        .SetFrequencyTarget "True", "fmin" 
        .SetNumberOfModes "nmodes"
    End With

    udouble=RestoreParameter("fmin")
    ReportInformation("EigenmodeSolver FrequencyTarget set As " & udouble)
    uint=RestoreParameter("nmodes")
    ReportInformation("EigenmodeSolver NumberOfModes set As " & uint)
End Sub
Sub SetPreprocessDone()
    StoreParameterWithDescription preprocessdonestr 1 "PreprocessDone"
End Sub
Function CheckPreprocess_Ext(resultPath As String) As Boolean
    'get the preprocess result to export
    Dim result As Boolean
    result=DoesParameterExist(preprocessdonestr)
    CheckPreprocess_Ext=result
End Function
Const preprocessdonestr As String="PPSDONE"
'''IMPORT COMMON HEADERS
'ReportInformation
Sub setFreqRange(fmin As Double,fmax As Double)
    'check existence
    Dim flag As Boolean
    MakeSureParameterExists("fmin",fmin)
    MakeSureParameterExists("fmax",fmax)
    SetParameterDescription   "fmin","Minimun Freq For Solver"
    SetParameterDescription   "fmax","Maximum Freq For Solver"
    Dim hislist As String
    hislist="Solver.FrequencyRange ""fmin"", ""fmax""" & vbCrLf
    AddToHistory("PRE_STEP_FREQ_CUSTOM_SET",hislist) 
    'Solver.FrequencyRange "fmin", "fmax"
    ReportInformation("FrequencyRange Set As fmin, fmax")    
End Sub
Sub setFreqRange_Auto()
    'check existence
    Dim flag As Boolean
    Dim localfmin As Double
    Dim localfmax As Double
    localfmin=Solver.GetFmin()
    localfmax=Solver.GetFmax()
    MakeSureParameterExists("fmin",localfmin)
    MakeSureParameterExists("fmax",localfmax)
    SetParameterDescription   "fmin","Minimun Freq For Solver"
    SetParameterDescription   "fmax","Maximum Freq For Solver"

    'Solver.FrequencyRange "fmin", "fmax"
    Dim hislist As String
    hislist="Solver.FrequencyRange ""fmin"", ""fmax""" & vbCrLf
    AddToHistory("PRE_STEP_FREQ_RANGE_SET",hislist) 
    ReportInformation("FrequencyRange Set As fmin, fmax")    
End Sub
Sub setEigenSolver(nmodes As Integer)
    Dim flag As Boolean
    Dim uint As Integer
    Dim udouble As Double
    MakeSureParameterExists("fmin",0)
    MakeSureParameterExists("nmodes",nmodes)
    flag=DoesParameterExist("nmodes") 
    ' With EigenmodeSolver 
    '     .SetFrequencyTarget "True", "fmin" 
    '     .SetNumberOfModes "nmodes"
    ' End With
    Dim hislist As String
    hislist="With EigenmodeSolver" & vbCrLf
    hislist=hislist & ".SetFrequencyTarget ""True"", ""fmin""" & vbCrLf
    hislist=hislist & ".SetNumberOfModes ""nmodes""" & vbCrLf
    hislist=hislist & "End With" & vbCrLf
    AddToHistory("PRE_STEP_EIGENSOLVER_CUSTOM_SET",hislist) 

    udouble=RestoreParameter("fmin")
    ReportInformation("EigenmodeSolver FrequencyTarget set As " & udouble)
    uint=RestoreParameter("nmodes")
    ReportInformation("EigenmodeSolver NumberOfModes set As " & uint)
End Sub
Sub setEigenSolver_Auto()
    Dim flag As Boolean
    Dim uint As Integer
    Dim udouble As Double
    MakeSureParameterExists("fmin",0)
    MakeSureParameterExists("nmodes",1)
    SetParameterDescription   "nmodes","Number of modes to calculate"
    ' With EigenmodeSolver 
    '     .SetFrequencyTarget "True", "fmin" 
    '     .SetNumberOfModes "nmodes"
    ' End With
    Dim hislist As String
    hislist="With EigenmodeSolver" & vbCrLf
    hislist=hislist & ".SetFrequencyTarget ""True"", ""fmin""" & vbCrLf
    hislist=hislist & ".SetNumberOfModes ""nmodes""" & vbCrLf
    hislist=hislist & "End With" & vbCrLf
    AddToHistory("PRE_STEP_EIGENSOLVER_SET",hislist) 
    udouble=RestoreParameter("fmin")
    ReportInformation("EigenmodeSolver FrequencyTarget set As " & udouble)
    uint=RestoreParameter("nmodes")
    ReportInformation("EigenmodeSolver NumberOfModes set As " & uint)
End Sub
Sub SetPreprocessDone()
    StoreParameterWithDescription preprocessdonestr,1,"PreprocessDone"
End Sub
Function CheckPreprocessDone() As Boolean
    'get the preprocess result
    Dim result As Boolean
    result=DoesParameterExist(preprocessdonestr)
    CheckPreprocessDone=result
End Function
Function CheckPreprocess_Ext(resultPath As String) As Boolean
    'get the preprocess result to export
    Dim result As Boolean
    result=DoesParameterExist(preprocessdonestr)
    CheckPreprocess_Ext=result
End Function

Sub StartPreProcess
    Dim result As Boolean
    result=CheckPreprocessDone
    If result=False Then
        setFreqRange_Auto
        setEigenSolver_Auto
        SetPreprocessDone
        Rebuild
    End If
End Sub
Function GetParamList(outputName As String)
    Dim numofparams As Long
    Dim N As Long
    Dim parname As String
    Dim svalue As String
    Dim description As String
    numofparams=GetNumberOfParameters()

    Open(outputDir & outputName) For Output As #1
    Print #1,outputDir & outputName
	Print #1,cstProjectPath
    Print #1,numofparams
    For N=0 To numofparams-1
        parname=GetParameterName (N)
        svalue=GetParameterSValue(N)
        description=GetParameterDescription (parname)
        Print #1,N;vbTab;parname;vbTab;svalue;vbTab;description
    Next
	Close #1
End Function
Function SaveCST(savedst As String)
    Backup(savedst)
End Function

Sub CustomPreProcess
    OpenFile"F:\programs\cst_tools\temp\testman\temp\tmpmc1717hm.cst"
    StartPreProcess
    GetParamList "a"
    SaveCST "F:\programs\cst_tools\temp\testman\processed.cst"
End Sub

Sub Main
    CustomPreProcess
End Sub

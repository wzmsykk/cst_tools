'#Language "WWB-COM"

Option Explicit
Sub defineCurvesNFaces

	Dim hz As Double
	
	'径向0-R直线
	With Line
     .Reset
     .Name "line_R"
     .Curve "curve_R"
     .X1 "0.0"
     .Y1 "0.0"
     .X2 "R"
     .Y2 "R"
     .Create
	End With

	'沿z轴X=0.5R Y=0的直线
	With AnalyticalCurve
     .Reset
     .Name "line_xp"
     .Curve "curv_line_xp"
     .LawX "0.5*R"
     .LawY "0"
     .LawZ "t"
     .ParameterRange "-L/2", "L/2"
     .Create
	End With
	'沿z轴X=-0.5R Y=0的直线
	With AnalyticalCurve
     .Reset
     .Name "line_xm"
     .Curve "curv_line_xm"
     .LawX "-0.5*R"
     .LawY "0"
     .LawZ "t"
     .ParameterRange "-L/2", "L/2"
     .Create
	End With
	'沿z=0.2L平面r=0.5R 的圆
	With Circle
     .Reset
     .Name "circle_p1"
     .Curve "curve_cp1"
     .Radius "R/2"
     .Xcenter "0.0"
     .Ycenter "0.0"
     .Segments "0"
     .Create
	End With
	With Transform
     .Reset
     .Name "curve_cp1:circle_p1"
     .Vector "0", "0", "0.35*L"
     .UsePickedPoints "False"
     .InvertPickedPoints "False"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .Transform "Curve", "Translate"
	End With
	'沿z=-0.2L平面r=0.5R 的圆
	With Circle
     .Reset
     .Name "circle_m1"
     .Curve "curve_cm1"
     .Radius "R/2"
     .Xcenter "0.0"
     .Ycenter "0.0"
     .Segments "0"
     .Create
	End With
	With Transform
     .Reset
     .Name "curve_cm1:circle_m1"
     .Vector "0", "0", "-0.35*L"
     .UsePickedPoints "False"
     .InvertPickedPoints "False"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .Transform "Curve", "Translate"
	End With
	'沿z=0.2L平面r=0.5R 的圆面
	With Face
     .Reset
     .Name "facep"
     .Type "CoverCurve"
     .Curve "curve_cm1:circle_m1"
     .DeleteCurve "False"
     .Create
	End With
	'沿z=-0.2L平面r=0.5R 的圆面
	With Face
     .Reset
     .Name "facem"
     .Type "CoverCurve"
     .Curve "curve_cp1:circle_p1"
     .DeleteCurve "False"
     .Create
	End With
	'沿z=0平面r=0.5R 的圆
	With Circle
     .Reset
     .Name "circle_0"
     .Curve "curve_0"
     .Radius "R/2"
     .Xcenter "0.0"
     .Ycenter "0.0"
     .Segments "0"
     .Create
	End With
	'沿z=0平面r=0.5R 的圆面
	With Face
     .Reset
     .Name "face0"
     .Type "CoverCurve"
     .Curve "curve_0:circle_0"
     .DeleteCurve "False"
     .Create
	End With

End Sub

Sub compute
	EigenmodeSolver.Start
End Sub
Sub postProcess
	Dim fullPath As String
	Dim basePath As String
	'fullPath=""
	basePath=""
	fullPath = "C:\Users\\ykk48\Documents\speedtest\pliibox_ay\"
	'fullPath = "C:\\Users\\ykk48\\Documents\\speedtest\\speedtest\\cst_new\\model\\Pillbox_test\\"
	Dim outmode,i As Integer
	Dim st,ed As Double
	Dim fieldResultPath As String
	Dim OBJ As Object
	Dim dIntReal As Double, dIntImag As Double
	Dim dArea As Double, dMax_abs As Double, dMax_z As Double
	Dim eps_tm As Double, eps_te As Double
	Dim TM_threshold As Double,TE_threshold As Double
	Dim m,n,p As Integer
	Dim IS_TM,IS_TE As Boolean
	eps_tm=0.1
	eps_te=0.1
	TM_threshold=100
	TE_threshold=100
	Dim result As Object
	Dim R_Q As Double
	Set result = Result0D("")
	Dim temp As Variant
	Dim cus As Double
	outmode = RestoreDoubleParameter("nmodes")
	Dim TM_fac As Double
	Dim TE_fac As Double

	Open(fullPath & "Mode_Result" &".txt") For Output As #1
	Print #1,"Mode_Index";vbTab;"Mode_Type"

	For i=1 To outmode
		IS_TE=False
		IS_TM=False
		TM_fac=0
		TE_fac=0
		ReportInformation("***************************")
		ReportInformation("MODE " & i)


		'电场
		SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\e")
		EvaluateFieldOnFace.CalculateIntegral ("face0","abs","re",dIntReal, dIntImag, dArea)
		dMax_abs=EvaluateFieldOnFace.GetValue("max")
		EvaluateFieldOnFace.CalculateIntegral("face0","z","re",dIntReal, dIntImag, dArea)
		dMax_z=EvaluateFieldOnFace.GetValue("max")
		ReportInformation("L0_E_ZMAX " & dMax_z)
		ReportInformation("L0_E_ABSMAX " & dMax_abs)
		If (Abs(dMax_z)/Abs(dMax_abs))<eps_te Or dMax_z<TE_threshold Then
			TE_fac+=1/3
		End If
		EvaluateFieldOnFace.CalculateIntegral ("facem","abs","re",dIntReal, dIntImag, dArea)
		dMax_abs=EvaluateFieldOnFace.GetValue("max")
		EvaluateFieldOnFace.CalculateIntegral("facem","z","re",dIntReal, dIntImag, dArea)
		dMax_z=EvaluateFieldOnFace.GetValue("max")
		ReportInformation("LM_E_ZMAX " & dMax_z)
		ReportInformation("LM_E_ABSMAX " & dMax_abs)
		If (Abs(dMax_z)/Abs(dMax_abs))<eps_te Or dMax_z<TE_threshold Then
			TE_fac+=1/3
		End If
		EvaluateFieldOnFace.CalculateIntegral ("facep","abs","re",dIntReal, dIntImag, dArea)
		dMax_abs=EvaluateFieldOnFace.GetValue("max")
		EvaluateFieldOnFace.CalculateIntegral("facep","z","re",dIntReal, dIntImag, dArea)
		dMax_z=EvaluateFieldOnFace.GetValue("max")
		ReportInformation("LP_E_ZMAX " & dMax_z)
		ReportInformation("LP_E_ABSMAX " & dMax_abs)
		If (Abs(dMax_z)/Abs(dMax_abs))<eps_te Or dMax_z<TE_threshold Then
			TE_fac+=1/3
		End If
		'For M
		Set OBJ = EvaluateFieldAlongCurve.GetField1D ("curve_cp1", "z", "real")
		fieldResultPath= basePath & "Mode" & i & "_EF_M.sig"
		OBJ.Save(fieldResultPath)
		OBJ.AddToTree("1D Results\Data\Mode_" & i & "_EF_M")
		'For N
		Set OBJ = EvaluateFieldAlongCurve.GetField1D ("curve_R", "tangential", "real")
		fieldResultPath= basePath & "Mode" & i & "_EF_N.sig"
		OBJ.Save(fieldResultPath)
		OBJ.AddToTree("1D Results\Data\Mode_" & i & "_EF_N")
		'For P
		Set OBJ = EvaluateFieldAlongCurve.GetField1D ("curv_line_xp", "z", "real")
		fieldResultPath= basePath & "Mode" & i & "_EF_P.sig"
		OBJ.Save(fieldResultPath)
		OBJ.AddToTree("1D Results\Data\Mode_" & i & "_EF_P")
		'输出
		SelectTreeItem("1D Results\Data\Mode_" & i & "_EF_M")
		With ASCIIExport
			.Reset
			.FileName (fullPath & "Mode_" & i & "_EF_M.txt")
			.Execute
		End With
		SelectTreeItem("1D Results\Data\Mode_" & i & "_EF_N")
		With ASCIIExport
			.Reset
			.FileName (fullPath & "Mode_" & i & "_EF_N.txt")
			.Execute
		End With
		SelectTreeItem("1D Results\Data\Mode_" & i & "_EF_P")
		With ASCIIExport
			.Reset
			.FileName (fullPath & "Mode_" & i & "_EF_P.txt")
			.Execute
		End With


		'磁场
		SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\h")
		EvaluateFieldOnFace.CalculateIntegral("face0","abs","imaginary",dIntReal, dIntImag, dArea)
		dMax_abs=EvaluateFieldOnFace.GetValue("max")
		EvaluateFieldOnFace.CalculateIntegral("face0","z","imaginary",dIntReal, dIntImag, dArea)
		dMax_z=EvaluateFieldOnFace.GetValue("max")
		ReportInformation(dMax_z)
		ReportInformation(dMax_abs)
		If (Abs(dMax_z)/Abs(dMax_abs))<eps_tm Or dMax_z<TM_threshold Then
			TM_fac+=1/3
		End If
		EvaluateFieldOnFace.CalculateIntegral("facem","abs","imaginary",dIntReal, dIntImag, dArea)
		dMax_abs=EvaluateFieldOnFace.GetValue("max")
		EvaluateFieldOnFace.CalculateIntegral("facem","z","imaginary",dIntReal, dIntImag, dArea)
		dMax_z=EvaluateFieldOnFace.GetValue("max")
		ReportInformation(dMax_z)
		ReportInformation(dMax_abs)
		If (Abs(dMax_z)/Abs(dMax_abs))<eps_tm Or dMax_z<TM_threshold Then
			TM_fac+=1/3
		End If
		EvaluateFieldOnFace.CalculateIntegral("facep","abs","imaginary",dIntReal, dIntImag, dArea)
		dMax_abs=EvaluateFieldOnFace.GetValue("max")
		EvaluateFieldOnFace.CalculateIntegral("facep","z","imaginary",dIntReal, dIntImag, dArea)
		dMax_z=EvaluateFieldOnFace.GetValue("max")
		ReportInformation(dMax_z)
		ReportInformation(dMax_abs)
		If (Abs(dMax_z)/Abs(dMax_abs))<eps_tm Or dMax_z<TM_threshold Then
			TM_fac+=1/3
		End If
		SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\h")
		'For M
		Set OBJ = EvaluateFieldAlongCurve.GetField1D ("curve_cp1", "z", "imaginary")
		fieldResultPath=basePath & "Mode_" & i & "_HF_M.sig"
		OBJ.Save(fieldResultPath)
		OBJ.AddToTree("1D Results\Data\Mode_" & i & "_HF_M")
		'For n
		Set OBJ = EvaluateFieldAlongCurve.GetField1D ("curve_R", "tangential", "imaginary")
		fieldResultPath=basePath & "Mode_" & i & "_HF_N.sig"
		OBJ.Save(fieldResultPath)
		OBJ.AddToTree("1D Results\Data\Mode_" & i & "_HF_N")
		'For P
		Set OBJ = EvaluateFieldAlongCurve.GetField1D ("curv_line_xp", "z", "imaginary")
		fieldResultPath=basePath & "Mode_" & i & "_HF_P.sig"
		OBJ.Save(fieldResultPath)
		OBJ.AddToTree("1D Results\Data\Mode_" & i & "_HF_P")

		'输出
		SelectTreeItem("1D Results\Data\Mode_" & i & "_HF_M")
		With ASCIIExport
			.Reset
			.FileName (fullPath & "Mode_" & i & "_HF_M.txt")
			.Execute
		End With
		SelectTreeItem("1D Results\Data\Mode_" & i & "_HF_N")
		With ASCIIExport
			.Reset
			.FileName (fullPath & "Mode_" & i & "_HF_N.txt")
			.Execute
		End With
		SelectTreeItem("1D Results\Data\Mode_" & i & "_HF_P")
		With ASCIIExport
			.Reset
			.FileName (fullPath & "Mode_" & i & "_HF_P.txt")
			.Execute
		End With

		If (TM_fac>TE_fac) Then
			IS_TM=True
		ElseIf (TE_fac>TM_fac) Then
			IS_TE=True
		End If

		SelectTreeItem("Tables\0D Results\R over Q beta=1 (Multiple Modes)\Mode " & i)
		temp=Resulttree.GetResultIDsFromTreeItem("Tables\0D Results\R over Q beta=1 (Multiple Modes)\Mode " & i)
		temp=Resulttree.GetResultFromTreeItem("Tables\0D Results\R over Q beta=1 (Multiple Modes)\Mode " & i,"3D:RunID:0")
		temp.GetData(cus)
		'ReportInformation(cus)
		If TM_fac>0.99 Then
			IS_TM=True
			IS_TE=False
		End If

		If cus>3 And IS_TM=False Then
			IS_TE=False
			IS_TM=True
		End If



		SelectTreeItem("Tables\0D Results\R over Q beta=1 (Multiple Modes)\Mode " & i)

		With ASCIIExport
			.Reset
			.FileName (fullPath & "Mode_" & i & "_ROQ_CENT.txt")
			.Execute
		End With
		If IS_TE=True Then
			ReportInformation("mode " & i & " IS_TE")
			Print #1,i;vbTab;"TE"
			fieldResultPath="Mode_" & i & "_TEMAXS.sig"
			With result
				.SetDataComplex(dMax_z,dMax_abs)
				.Title("TYP_TE_ZMAX_ABSMAX")
				.SetFileName(fieldResultPath)
				.Save()
				.AddToTree("1D Results\Mode_" & i & "_TEMAXS")
			End With

		ElseIf IS_TM=True Then
			ReportInformation("mode " & i & " IS_TM")
			Print #1,i;vbTab;"TM"
			fieldResultPath="Mode_" & i & "_TMMAXS.sig"
			With result
				.SetDataComplex(dMax_z,dMax_abs)
				.Title("TYP_TM_ZMAX_ABSMAX")
				.SetFileName(fieldResultPath)
				.Save()
				.AddToTree("1D Results\Mode_" & i & "_TMMAXS")
			End With
		Else
			ReportInformation("mode " & i & " IS_HX")
			Print #1,i;vbTab;"HX"
		End If
	Next i
	Close #1
End Sub
Sub Main
	'defineCurvesNFaces()
	'compute()
	postProcess()
End Sub

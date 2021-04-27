'#Language "WWB-COM"

Option Explicit


Function FindMaximum3D(ByRef xcoord As Double,ByRef ycoord As Double,ByRef zcoord As Double) As Double
	'Dim xcoord As Double, ycoord As Double, zcoord As Double
	Dim cst_value As Double
	cst_value = GetFieldPlotMaximumPos(xcoord, ycoord, zcoord)
	FindMaximum3D=cst_value
End Function
Function FindMinimum3D(ByRef xcoord As Double,ByRef ycoord As Double,ByRef zcoord As Double) As Double
	'Dim xcoord As Double, ycoord As Double, zcoord As Double
	Dim cst_value As Double
	cst_value = GetFieldPlotMinimumPos(xcoord, ycoord, zcoord)
	FindMinimum3D=cst_value
End Function
Function FindMaximumAbs3D(ByRef xcoord As Double,ByRef ycoord As Double,ByRef zcoord As Double) As Double
	Dim ux As Double, uy As Double, uz As Double
	Dim vx As Double, vy As Double, vz As Double
	Dim v1 As Double,v2 As Double,cst_value As Double
	v1 = FindMaximum3D(ux, uy, uz)
	v2 = FindMinimum3D(vx, vy, vz)
	If Abs(v1)>Abs(v2) Then
		xcoord=ux
		ycoord=uy
		zcoord=uz
		cst_value=Abs(v1)
	Else
		xcoord=vx
		ycoord=vy
		zcoord=vz
		cst_value=Abs(v2)
	End If
	FindMaximumAbs3D=cst_value
End Function
Function FindMaximum_Full(ByRef xcoord As Double,ByRef ycoord As Double,ByRef zcoord As Double,FieldType As String) As Double
	'FieldTypr Should be "e_F", "e_R", "e_Z", "h_F", "h_R", "h_Z"
	Dim uxcoord As Double, uycoord As Double, uzcoord As Double
	Dim cst_value As Double
	Dim result0D As Object

	Set result0D =Resulttree.GetResultFromTreeItem("Tables\0D Results\" +FieldType+ "_3D\Maximum X-Position","3D:RunID:0")
	result0D.GetData(xcoord)
	Set result0D =Resulttree.GetResultFromTreeItem("Tables\0D Results\" +FieldType+ "_3D\Maximum Y-Position","3D:RunID:0")
	result0D.GetData(ycoord)
	Set result0D =Resulttree.GetResultFromTreeItem("Tables\0D Results\" +FieldType+ "_3D\Maximum Z-Position","3D:RunID:0")
	result0D.GetData(zcoord)
	Set result0D =Resulttree.GetResultFromTreeItem("Tables\0D Results\" +FieldType+ "_3D\Maximum","3D:RunID:0")
	result0D.GetData(cst_value)
	'ReportInformation(cst_value)
	FindMaximum_Full=cst_value
End Function
Function FindMinimum_Full(ByRef xcoord As Double,ByRef ycoord As Double,ByRef zcoord As Double,FieldType As String) As Double
	'FieldTypr Should be "e_F", "e_R", "e_Z", "h_F", "h_R", "h_Z"
	Dim uxcoord As Double, uycoord As Double, uzcoord As Double
	Dim cst_value As Double
	Dim result0D As Object

	Set result0D =Resulttree.GetResultFromTreeItem("Tables\0D Results\" +FieldType+ "_3D\Minimum X-Position","3D:RunID:0")
	result0D.GetData(xcoord)
	Set result0D =Resulttree.GetResultFromTreeItem("Tables\0D Results\" +FieldType+ "_3D\Minimum Y-Position","3D:RunID:0")
	result0D.GetData(ycoord)
	Set result0D =Resulttree.GetResultFromTreeItem("Tables\0D Results\" +FieldType+ "_3D\Minimum Z-Position","3D:RunID:0")
	result0D.GetData(zcoord)
	Set result0D =Resulttree.GetResultFromTreeItem("Tables\0D Results\" +FieldType+ "_3D\Minimum","3D:RunID:0")
	result0D.GetData(cst_value)
	'ReportInformation(cst_value)
	FindMinimum_Full=cst_value
End Function
Function FindMaxiumAbs_Full(ByRef xcoord As Double,ByRef ycoord As Double,ByRef zcoord As Double,FieldType As String) As Double
	'FieldTypr Should be "e_F", "e_R", "e_Z", "h_F", "h_R", "h_Z"
	Dim ux As Double, uy As Double, uz As Double
	Dim vx As Double, vy As Double, vz As Double
	Dim v0 As Double,v1 As Double
	v0=FindMaximum_Full(ux,uy,uz,FieldType)
	v1=FindMinimum_Full(vx,vy,vz,FieldType)
	If Abs(v0)>Abs(v1) Then
		xcoord=ux
		ycoord=uy
		zcoord=uz
		FindMaxiumAbs_Full=Abs(v0)
	Else
		xcoord=vx
		ycoord=vy
		zcoord=vz
		FindMaxiumAbs_Full=Abs(v1)
	End If
End Function
Sub CreateCircleZplane(curvename As String ,radius As  Variant, zoffset As Variant)
	Dim compname As String
	compname="comp"
	With Circle
     .Reset
     .Name compname
     .Curve curvename
     .Radius Str(radius)
     .Xcenter "0.0"
     .Ycenter "0.0"
     .Segments "0"
     .Create
	End With
	With Transform
     .Reset
     .Name curvename+":"+compname
     .Vector "0", "0", Str(zoffset)
     .UsePickedPoints "False"
     .InvertPickedPoints "False"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .Transform "Curve", "Translate"
	End With
End Sub

Sub CreateLineZplane_Polar(curvename As String ,r As Variant,theta As Variant,zoffset As Variant)
	Dim compname As String
	compname="comp"
	Dim xp As String,yp As String
	xp=Str(Cos(theta))+"*"+Str(r)
	yp=Str(Sin(theta))+"*"+Str(r)
	With Line
     .Reset
     .Name compname
     .Curve curvename
     .X1 "0.0"
     .Y1 "0.0"
     .X2 xp
     .Y2 yp
     .Create
	End With
	With Transform
     .Reset
     .Name curvename+":"+compname
     .Vector "0", "0", Str(zoffset)
     .UsePickedPoints "False"
     .InvertPickedPoints "False"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .Transform "Curve", "Translate"
	End With

End Sub
Sub CreateLineZAxis(curvename As String ,xoffset As  Variant, yoffset As Variant)
	Dim compname As String
	compname="comp"
	Dim xp As String,yp As String
	With AnalyticalCurve
     .Reset
     .Name compname
     .Curve curvename
     .LawX Str(xoffset)
     .LawY Str(yoffset)
     .LawZ "t"
     .ParameterRange "-L/2", "L/2"
     .Create
	End With

End Sub

Function FieldAlongCurve(curvename As String, fieldComponent As String, resultType As String) As Object
	'''fieldComp:  enum{"x", "y", "z", "abs", "tangential"}
	'''resultType: enum{"real", "imaginary", "magnitude", "phase", "complex"} complexType
	'''return: object:Field1D
	'ReportInformation(zcoord)
	Set FieldAlongCurve = EvaluateFieldAlongCurve.GetField1D (curvename, fieldComponent, resultType)
	'fieldResultPath= basePath & "Mode" & i & "_EF_M.sig"
	'OBJ.Save(fieldResultPath)
	'OBJ.AddToTree("1D Results\Data\Mode_" & i & "_EF_M")
End Function

Sub postProcess()
	Dim value As Double
	Const Z0 As Double=Sqr(Mu0/Eps0)
	Const alpha As Double=10
	Dim xcoord As Double, ycoord As Double, zcoord As Double
	Dim i As Double,r As Double
	Dim ezabsmax As Double,hzabsmax As Double
	Dim coffd As Double
	Dim etabsmax As Double,htabsmax As Double

	Const basepath As String=""
	Dim fieldResultPath As String

	Dim uresult1D As Object


	i=1
	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\e\Z")
	ezabsmax=FindMaximumAbs3D(xcoord, ycoord, zcoord)

	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\h\Z")
	hzabsmax=FindMaximumAbs3D(xcoord, ycoord, zcoord)

	coffd=ezabsmax/hzabsmax/Z0
	ReportInformation("TEMcoff:"& coffd)
	'coffd>alpha TM
	'coffd<alpha TE
	If coffd>alpha Then
		ReportInformation("MODE:TM")
		StoreParameter("FieldType", 0)
	ElseIf coffd<1/alpha Then
		ReportInformation("MODE:TE")
		StoreParameter("FieldType", 1)
	Else
		ReportInformation("MODE:HX")
		StoreParameter("FieldType", 2)
	End If



	Dim rcoord As Double,fcoord As Double

	'Efield
	'find max e_theta
	etabsmax=FindMaxiumAbs_Full(rcoord, fcoord, zcoord,"e_F") 'in cylind coordiates R F Z Fcoord in degrees
	fcoord=fcoord/360.0*2*Pi 'convert to radian
	'convert to xy coord
	xcoord=rcoord*Cos(fcoord)
	ycoord=rcoord*Sin(fcoord)

	ReportInformation("MAXABSE_F:" & etabsmax)

	'create Circle,Zline

	CreateCircleZplane("emax_cir",rcoord,zcoord)
	CreateLineZplane_Polar("emax_xyline","R",fcoord,zcoord)
	CreateLineZAxis("emax_zline",xcoord,ycoord)

	'get fields along the curve

	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\e")

	'''E Field along circle
	Set uresult1D=FieldAlongCurve("emax_cir","tangential","real")
	fieldResultPath= basepath & "Mode" & i & "_ECircle_T.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_EC_T")

	Set uresult1D=FieldAlongCurve("emax_cir","x","real")
	fieldResultPath= basepath & "Mode" & i & "_ECircle_X.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_EC_X")

	Set uresult1D=FieldAlongCurve("emax_cir","y","real")
	fieldResultPath= basepath & "Mode" & i & "_ECircle_Y.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_EC_Y")

	Set uresult1D=FieldAlongCurve("emax_cir","z","real")
	fieldResultPath= basepath & "Mode" & i & "_ECircle_Z.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_EC_Z")


	'''E Field along Radius

	Set uresult1D=FieldAlongCurve("emax_xyline","x","real")
	fieldResultPath= basepath & "Mode" & i & "_ERadius_X.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_ER_X")

	Set uresult1D=FieldAlongCurve("emax_xyline","y","real")
	fieldResultPath= basepath & "Mode" & i & "_ERadius_Y.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_ER_Y")

	Set uresult1D=FieldAlongCurve("emax_xyline","z","real")
	fieldResultPath= basepath & "Mode" & i & "_ERadius_Z.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_ER_Z")

	Set uresult1D=FieldAlongCurve("emax_xyline","tangential","real")
	fieldResultPath= basepath & "Mode" & i & "_ERadius_T.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_ER_T")


	'''E Field along z axis

	Set uresult1D=FieldAlongCurve("emax_zline","x","real")
	fieldResultPath= basepath & "Mode" & i & "_EZLine_X.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_EZ_X")

	Set uresult1D=FieldAlongCurve("emax_zline","y","real")
	fieldResultPath= basepath & "Mode" & i & "_EZLine_Y.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_EZ_Y")

	Set uresult1D=FieldAlongCurve("emax_zline","z","real")
	fieldResultPath= basepath & "Mode" & i & "_EZLine_Z.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_EZ_Z")

	Set uresult1D=FieldAlongCurve("emax_zline","tangential","real")
	fieldResultPath= basepath & "Mode" & i & "_EZLine_T.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_EZ_T")


	'HField
	'find max h_theta

	htabsmax=FindMaxiumAbs_Full(rcoord, fcoord, zcoord,"h_F") 'in cylind coordiates R F Z
	ReportInformation("MAXABSH_F:" & htabsmax)

	fcoord=fcoord/360.0*2*Pi 'convert to radian
	'convert to xy coord
	xcoord=rcoord*Cos(fcoord)
	ycoord=rcoord*Sin(fcoord)



	CreateCircleZplane("hmax_cir",rcoord,zcoord)
	CreateLineZplane_Polar("hmax_xyline","R",fcoord,zcoord)
	CreateLineZAxis("hmax_zline",xcoord,ycoord)

	'get fields along the curve
	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\h")
	'''H Field along circle


	Set uresult1D=FieldAlongCurve("hmax_cir","x","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HCircle_X.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HC_X")

	Set uresult1D=FieldAlongCurve("hmax_cir","y","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HCircle_Y.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HC_Y")

	Set uresult1D=FieldAlongCurve("hmax_cir","z","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HCircle_Z.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HC_Z")

	Set uresult1D=FieldAlongCurve("hmax_cir","tangential","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HCircle_T.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HC_T")


	'''H Field along radius

	Set uresult1D=FieldAlongCurve("hmax_xyline","x","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HRadius_X.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HR_X")

	Set uresult1D=FieldAlongCurve("hmax_xyline","y","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HRadius_Y.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HR_Y")

	Set uresult1D=FieldAlongCurve("hmax_xyline","z","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HRadius_Z.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HR_Z")

	Set uresult1D=FieldAlongCurve("hmax_xyline","tangential","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HRadius_T.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HR_T")


	'''H Field along z axis


	Set uresult1D=FieldAlongCurve("hmax_zline","x","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HZLine_X.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HZ_X")

	Set uresult1D=FieldAlongCurve("hmax_zline","y","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HZLine_Y.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HZ_Y")

	Set uresult1D=FieldAlongCurve("hmax_zline","z","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HZLine_Z.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HZ_Z")

	Set uresult1D=FieldAlongCurve("hmax_zline","tangential","imaginary")
	fieldResultPath= basepath & "Mode" & i & "_HZLine_Z.sig"
	uresult1D.Save(fieldResultPath)
	uresult1D.AddToTree("1D Results\Data\Mode_" & i & "_HZ_T")




End Sub
Sub compute

	EigenmodeSolver.Start
End Sub

Sub nextMode(ByRef id As Integer)
	Dim freq As Double
	freq=EigenmodeSolver.GetModeFrequencyInHz(1)
	freq=freq/1E6
	freq=freq+1
	ReportInformation("Mode " & id & ":Freq " & freq & " Mhz")
	StoreParameter("fmin", freq)
End Sub

Sub saveResult(saveDir As String, id As Variant)
	Dim A As Variant,B As Variant,C As Variant
	Dim fi As String,cr As String,cm As String
	A = Array("H","E")
	B = Array("Z","R","C")
	C= Array("T","X","Y","Z")
	For Each fi In A
		For Each cr In B
			For Each cm In C
				SelectTreeItem("1D Results\Data\Mode_" & 1 & "_" & fi & cr & "_" & cm)
				With ASCIIExport
					.Reset
					.FileName (saveDir & "Mode_" & id & "_" & fi & cr & "_" & cm & ".txt")
					.Execute
				End With
			Next cm
		Next cr
	Next fi

	'save freq
	SelectTreeItem("Tables\0D Results\Frequency (Multiple Modes)\Mode " & 1)
	With ASCIIExport
		.Reset
		.FileName (saveDir & "Mode_" & id & "_FREQ.txt")
		.Execute
	End With


	'save E/H fields
	SelectTreeItem("2D/3D Results\Modes\Mode "& 1 &"\e")
	With ASCIIExport
		.Reset
		.FileName (saveDir & "Mode_"& id &"_EField.txt")
		.Mode ("FixedNumber")
		.StepX (128)
		.StepY (128)
		.StepZ (8)
		.Execute
	End With

	SelectTreeItem("2D/3D Results\Modes\Mode "& 1 &"\h")
	With ASCIIExport
		.Reset
		.FileName (saveDir & "Mode_"& id &"_HField.txt")
		.Mode ("FixedNumber")
		.StepX (128)
		.StepY (128)
		.StepZ (8)
		.Execute
	End With

	'save mode result
	Dim modetxt As String
	Dim ftype As String
	ftype=RestoreParameter("FieldType")
	Open(saveDir & "Mode_"& id &"_Type.txt") For Output As #1
	If ftype="0" Then
		Print #1,"Mode_Type";vbTab;"TM"
	ElseIf ftype="1" Then
		Print #1,"Mode_Type";vbTab;"TE"
	Else
		Print #1,"Mode_Type";vbTab;"HX"
	End If

	Close #1



End Sub


Sub Main
	StoreParameter("fmin", 400)
	Rebuild
	mainloop(1)

End Sub

Sub mainloop(maxcount As Integer)
	Dim id As Integer
	id=1
	For id=1 To maxcount
		compute()
		postProcess()
		saveResult("D:\tes\", id)
		nextMode(id)
		Rebuild
	Next id
End Sub

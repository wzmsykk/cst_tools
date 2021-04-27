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
Sub ChangeCurveCircleZplane
	Dim curve_cnt As Integer
	Dim cname As String
	curve_cnt=Curve.StartCurveNameIteration("all")
	cname=Curve.GetNextCurveName()
	ReportInformation(Str(curve_cnt) & cname)
	Curve.DeleteCurveItem ( cname, "line_R")


End Sub

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
	ReportInformation(cst_value)
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
	ReportInformation(cst_value)
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

Sub CreateCircleZplane(curvename As String ,radius As  String, zoffset As String)
	Dim compname As String
	compname="comp"
	With Circle
     .Reset
     .Name compname
     .Curve curvename
     .Radius radius
     .Xcenter "0.0"
     .Ycenter "0.0"
     .Segments "0"
     .Create
	End With
	With Transform
     .Reset
     .Name curvename+":"+compname
     .Vector "0", "0", zoffset
     .UsePickedPoints "False"
     .InvertPickedPoints "False"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .Transform "Curve", "Translate"
	End With
End Sub
Sub CreateLineZaxis(curvename As String ,xoffset As String, yoffset As String)
	Dim compname As String
	compname="comp"
	With Circle
     .Reset
     .Name compname
     .Curve curvename
     .Radius "R/2"
     .Xcenter "0.0"
     .Ycenter "0.0"
     .Segments "0"
     .Create
	End With
	With Transform
     .Reset
     .Name curvename+":"+compname
     .Vector xoffset, yoffset, "0"
     .UsePickedPoints "False"
     .InvertPickedPoints "False"
     .MultipleObjects "False"
     .GroupObjects "False"
     .Repetitions "1"
     .MultipleSelection "False"
     .Transform "Curve", "Translate"
	End With
End Sub
Function FieldAlongCurve(curvename As String, fieldComponent As String, resultType As String) As Object
	'''fieldComp:  enum{"x", "y", "z", "abs", "tangential"}
	'''resultType enum{"real", "imaginary", "magnitude", "phase", "complex"} complexType
	'''return object:Field1D
	ReportInformation(curvename)
	ReportInformation(fieldComponent)
	ReportInformation(resultType)
	'ReportInformation(zcoord)
	Set FieldAlongCurve = EvaluateFieldAlongCurve.GetField1D (curvename, fieldComponent, resultType)
	'fieldResultPath= basePath & "Mode" & i & "_EF_M.sig"
	'OBJ.Save(fieldResultPath)
	'OBJ.AddToTree("1D Results\Data\Mode_" & i & "_EF_M")
End Function


Sub Main2
	'defineCurvesNFaces
	'ChangeCurveCircleZplane
	Dim i As Double
	Dim circlename As String
	Dim resuld1D As Variant
	Dim fieldResultPath As String
	Dim basePath As String
	basePath=""
	i=4
	circlename="gen_cir"
	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\e" & "\Z")
	Dim xcoord As Double, ycoord As Double, zcoord As Double
	FindMaximum3D(xcoord, ycoord, zcoord)
	Dim r As Double
	r=Sqr(xcoord*xcoord+ycoord*ycoord)
	CreateCircleZplane(circlename,Str(r),Str(zcoord))
	Set resuld1D=FieldAlongCurve(circlename,"tangential","real") 'Epsi Alone Curve
	fieldResultPath= basePath & "Mode" & i & "_EF_M.sig"
	resuld1D.Save(fieldResultPath)
	resuld1D.AddToTree("1D Results\Data\Mode_" & i & "_EF_M")

End Sub
Sub Main3
	Dim i As Double,r As Double
	Dim circlename As String
	Dim tempstr As String
	Dim value As Double
	Dim fieldResultPath As String
	Dim list As Variant
	Dim resuld1D As Variant
	Dim xcoord As Double, ycoord As Double, zcoord As Double
	Dim basePath As String
	basePath=""
	i=2
	circlename="gen_cir"
	value=FindMaxiumAbs_Full(xcoord, ycoord, zcoord,"e_F")
	'r=Sqr(xcoord*xcoord+ycoord*ycoord)
	r=xcoord

	CreateCircleZplane("gen_cir",Str(r),Str(zcoord))
	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\e")
	Set resuld1D=FieldAlongCurve(circlename,"tangential","real") 'Epsi Alone Curve
	fieldResultPath= basePath & "Mode" & i & "_EF_M.sig"
	resuld1D.Save(fieldResultPath)
	resuld1D.AddToTree("1D Results\Data\Mode_" & i & "_EF_M")
	ReportInformation(xcoord)
	ReportInformation(ycoord)
	ReportInformation(zcoord)
	ReportInformation(r)
	ReportInformation(value)

End Sub

Sub Main
	Dim value As Double
	Dim Z0 As Double
	Z0=Sqr(Mu0/Eps0)
	Dim xcoord As Double, ycoord As Double, zcoord As Double
	Dim i As Double,r As Double
	Dim ezabsmax As Double,hzabsmax As Double
	Dim coffd As Double

	i=1
	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\e\Z")
	ezabsmax=FindMaximumAbs3D(xcoord, ycoord, zcoord)

	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\h\Z")
	hzabsmax=FindMaximumAbs3D(xcoord, ycoord, zcoord)

	coffd=ezabsmax/hzabsmax/Z0
	ReportInformation(coffd)


End Sub

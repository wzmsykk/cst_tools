'#Language "WWB-COM"

Option Explicit
'V4 save field sub volume


Function FindMaximumAbs3D_epllipse(comp As String, rxy As Double,rz As Double, ByRef xcoord As Double,ByRef ycoord As Double,ByRef zcoord As Double) As Double
	Dim x_cst As Double,y_cst As Double,z_cst As Double
	Dim x_step As Double,y_step As Double,z_step As Double
	Dim take_this As Boolean
	Dim i As Long
	Dim cst_value As Double
	'Restrict Volumes
	x_step=2.0
	y_step=2.0
	z_step=2.0
	VectorPlot3D.Reset
	Dim x_cst_list() As Double
	Dim y_cst_list() As Double
	Dim z_cst_list() As Double
	Dim MaxLength As Long
	MaxLength =(Int(2*rxy/x_step)+1)*(Int(2*rxy/y_step)+1)*(Int(2*rz/z_step)+1)
	ReDim x_cst_list(MaxLength)
	ReDim y_cst_list(MaxLength)
	ReDim z_cst_list(MaxLength)
	Dim totalPoints As Long
	totalPoints=0
	i=0
	For x_cst=-rxy To rxy STEP x_step
		For y_cst=-rxy To rxy STEP y_step
			For z_cst=-rz To rz STEP z_step

				If (x_cst/rxy)^2+(y_cst/rxy)^2+(z_cst/rz)^2<1 Then
					take_this=True
					totalPoints = totalPoints+1

				End If


				If take_this Then
					x_cst_list(i) =x_cst
					y_cst_list(i) =y_cst
					z_cst_list(i) =z_cst
					i=i+1
				End If

			Next z_cst
		Next y_cst
	Next x_cst
	ReportInformation("STEP1 Done")
	ReDim Preserve x_cst_list(totalPoints)
	ReDim Preserve y_cst_list(totalPoints)
	ReDim Preserve z_cst_list(totalPoints)

	VectorPlot3D.SetPoints(x_cst_list,y_cst_list,z_cst_list)


	VectorPlot3D.CalculateList
	ReportInformation("STEP2 Done")

	Dim i_CST_GetListItem As Long
	i_CST_GetListItem =0
	Dim vxre As Double,vyre As Double,vzre As Double,vxim As Double,vyim As Double,vzim As Double
	Dim tvxre As Double,tvyre As Double,tvzre As Double,tvxim As Double,tvyim As Double,tvzim As Double
	Dim tx_coord As Double,ty_coord As Double,tz_coord As Double
	Dim curList As Variant
	Dim tv As Double
	Select Case comp
		Case "Ex"
			curList=VectorPlot3D.GetList("xre")
		Case "Ey"
			curList=VectorPlot3D.GetList("yre")
		Case "Ez"
			curList=VectorPlot3D.GetList("zre")
		Case "Hx"
			curList=VectorPlot3D.GetList("xim")
		Case "Hy"
			curList=VectorPlot3D.GetList("yim")
		Case "Hz"
			curList=VectorPlot3D.GetList("zim")
	End Select
	tv=curList(0)
	tx_coord=x_cst_list(0)
	ty_coord=y_cst_list(0)
	tz_coord=z_cst_list(0)
	For i_CST_GetListItem=1 To totalPoints

		If Abs(curList(i_CST_GetListItem))>Abs(tv) Then
			tv=curList(i_CST_GetListItem)
			tx_coord=x_cst_list(i_CST_GetListItem)
			ty_coord=y_cst_list(i_CST_GetListItem)
			tz_coord=z_cst_list(i_CST_GetListItem)
		End If


	Next i_CST_GetListItem

	xcoord=tx_coord
	ycoord=ty_coord
	zcoord=tz_coord
	cst_value=Abs(tv)

	FindMaximumAbs3D_epllipse=cst_value
End Function
Function SumFieldAbsCylindrical_epllipse(comp As String, rxy As Double,rz As Double) As Double
	Dim x_cst As Double,y_cst As Double,z_cst As Double
	Dim r_cst As Double,f_cst As Double
	Dim r_step As Double,f_step As Double,z_step As Double
	Dim take_this As Boolean
	Dim i As Long
	Dim cst_value As Double
	'Restrict Volumes
	r_step=4.0
	f_step=4.0
	z_step=4.0
	VectorPlot3D.Reset
	Dim x_cst_list() As Double
	Dim y_cst_list() As Double
	Dim z_cst_list() As Double
	Dim r_cst_list() As Double
	Dim f_cst_list() As Double
	Dim MaxLength As Long
	MaxLength =(Int(rxy/r_step)+1)*(Int(360/f_step)+1)*(Int(2*rz/z_step)+1)
	ReDim x_cst_list(MaxLength)
	ReDim y_cst_list(MaxLength)
	ReDim z_cst_list(MaxLength)
	ReDim r_cst_list(MaxLength)
	ReDim f_cst_list(MaxLength)
	Dim totalPoints As Long
	totalPoints=0
	i=0
	For r_cst=0 To rxy STEP r_step
		For f_cst=0 To 360 STEP f_step
			For z_cst=-rz To rz STEP z_step

				If (r_cst/rxy)^2+(z_cst/rz)^2<1 Then
					take_this=True
					totalPoints = totalPoints+1
					i=i+1
				End If


				If take_this Then
					x_cst_list(i) =r_cst*Cos(f_cst/180*Pi)
					y_cst_list(i) =r_cst*Sin(f_cst/180*Pi)
					z_cst_list(i) =z_cst
					f_cst_list(i) =f_cst/180*Pi
					r_cst_list(i) =r_cst
				End If

			Next z_cst
		Next f_cst
	Next r_cst
	ReportInformation("STEP1 Done")
	ReDim Preserve x_cst_list(totalPoints)
	ReDim Preserve y_cst_list(totalPoints)
	ReDim Preserve z_cst_list(totalPoints)
	'No Need To Redim RF
	VectorPlot3D.SetPoints(x_cst_list,y_cst_list,z_cst_list)


	VectorPlot3D.CalculateList
	ReportInformation("STEP2 Done")

	Dim i_CST_GetListItem As Long
	i_CST_GetListItem =0
	Dim tr_coord As Double,tf_coord As Double,tz_coord As Double
	Dim ur_coord As Double,uf_coord As Double,uz_coord As Double
	Dim xre_list As Variant, yre_list As Variant, zre_list As Variant, xim_list As Variant, yim_list As Variant, zim_list As Variant
	Dim tv As Double
	Dim uv As Double


	'CONVERT cartensian to cylindrical
	Dim sum As Double
	sum=0
	Select Case comp
		Case "Ez"
			zre_list=VectorPlot3D.GetList("zre")
			For i_CST_GetListItem=0 To totalPoints
				tv=zre_list(i_CST_GetListItem)
				sum=sum+Abs(tv)
			Next i_CST_GetListItem

		Case "Hz"
			zim_list=VectorPlot3D.GetList("zim")
			For i_CST_GetListItem=0 To totalPoints
				tv=zim_list(i_CST_GetListItem)
				sum=sum+Abs(tv)
			Next i_CST_GetListItem

		Case "Er"
			xre_list=VectorPlot3D.GetList("xre")
			yre_list=VectorPlot3D.GetList("yre")
			ReDim vr_list(totalPoints)
			ReDim vf_list(totalPoints)

			For i_CST_GetListItem=0 To totalPoints
				ur_coord=r_cst_list(i_CST_GetListItem)
				uf_coord=f_cst_list(i_CST_GetListItem)
				uv=xre_list(i)*Cos(uf_coord)+yre_list(i)*Sin(uf_coord)
				sum=sum+Abs(uv)
			Next i_CST_GetListItem
		Case "Ef"
			xre_list=VectorPlot3D.GetList("xre")
			yre_list=VectorPlot3D.GetList("yre")
			ReDim vr_list(totalPoints)
			ReDim vf_list(totalPoints)

			For i_CST_GetListItem=0 To totalPoints
				ur_coord=r_cst_list(i_CST_GetListItem)
				uf_coord=f_cst_list(i_CST_GetListItem)
				uv=xre_list(i)*-Sin(uf_coord)+yre_list(i)*Cos(uf_coord)

				sum=sum+Abs(uv)
			Next i_CST_GetListItem
		Case "Hr"
			xim_list=VectorPlot3D.GetList("xim")
			yim_list=VectorPlot3D.GetList("yim")
			ReDim vr_list(totalPoints)
			ReDim vf_list(totalPoints)
			tr_coord=r_cst_list(0)
			tf_coord=f_cst_list(0)
			tv=xim_list(i)*-Sin(tf_coord)+yim_list(i)*Cos(tf_coord)
			For i_CST_GetListItem=0 To totalPoints
				ur_coord=r_cst_list(i_CST_GetListItem)
				uf_coord=f_cst_list(i_CST_GetListItem)
				uv=xim_list(i)*Cos(uf_coord)+yim_list(i)*Sin(uf_coord)
				sum=sum+Abs(uv)
			Next i_CST_GetListItem
		Case "Hf"
			xim_list=VectorPlot3D.GetList("xim")
			yim_list=VectorPlot3D.GetList("yim")
			ReDim vr_list(totalPoints)
			ReDim vf_list(totalPoints)
			tr_coord=r_cst_list(0)
			tf_coord=f_cst_list(0)
			tv=xim_list(i)*-Sin(tf_coord)+yim_list(i)*Cos(tf_coord)
			For i_CST_GetListItem=0 To totalPoints
				ur_coord=r_cst_list(i_CST_GetListItem)
				uf_coord=f_cst_list(i_CST_GetListItem)
				uv=xim_list(i)*-Sin(uf_coord)+yim_list(i)*Cos(uf_coord)
				sum=sum+Abs(uv)

			Next i_CST_GetListItem
	End Select



	cst_value=sum

	SumFieldAbsCylindrical_epllipse=cst_value
End Function
Function FindMaximumAbsCylindrical_epllipse(comp As String, rxy As Double,rz As Double, ByRef rcoord As Double,ByRef fcoord As Double,ByRef zcoord As Double) As Double
	Dim x_cst As Double,y_cst As Double,z_cst As Double
	Dim r_cst As Double,f_cst As Double
	Dim r_step As Double,f_step As Double,z_step As Double
	Dim take_this As Boolean
	Dim i As Long
	Dim cst_value As Double
	'Restrict Volumes
	r_step=2.0
	f_step=2.0
	z_step=2.0
	VectorPlot3D.Reset
	Dim x_cst_list() As Double
	Dim y_cst_list() As Double
	Dim z_cst_list() As Double
	Dim r_cst_list() As Double
	Dim f_cst_list() As Double
	Dim MaxLength As Long
	MaxLength =(Int(rxy/r_step)+1)*(Int(360/f_step)+1)*(Int(2*rz/z_step)+1)
	ReDim x_cst_list(MaxLength)
	ReDim y_cst_list(MaxLength)
	ReDim z_cst_list(MaxLength)
	ReDim r_cst_list(MaxLength)
	ReDim f_cst_list(MaxLength)
	Dim totalPoints As Long
	totalPoints=0
	i=0
	For r_cst=0 To rxy STEP r_step
		For f_cst=0 To 360 STEP f_step
			For z_cst=-rz To rz STEP z_step

				If (r_cst/rxy)^2+(z_cst/rz)^2<1 Then
					take_this=True
					totalPoints = totalPoints+1

				End If


				If take_this Then
					x_cst_list(i) =r_cst*Cos(f_cst/180*Pi)
					y_cst_list(i) =r_cst*Sin(f_cst/180*Pi)
					z_cst_list(i) =z_cst
					f_cst_list(i) =f_cst/180*Pi
					r_cst_list(i) =r_cst
					i=i+1
				End If

			Next z_cst
		Next f_cst
	Next r_cst
	ReportInformation("STEP1 Done")
	ReDim Preserve x_cst_list(totalPoints)
	ReDim Preserve y_cst_list(totalPoints)
	ReDim Preserve z_cst_list(totalPoints)
	'No Need To Redim RF
	VectorPlot3D.SetPoints(x_cst_list,y_cst_list,z_cst_list)


	VectorPlot3D.CalculateList
	ReportInformation("STEP2 Done")

	Dim i_CST_GetListItem As Long
	i_CST_GetListItem =0
	Dim tr_coord As Double,tf_coord As Double,tz_coord As Double
	Dim ur_coord As Double,uf_coord As Double,uz_coord As Double
	Dim xre_list As Variant, yre_list As Variant, zre_list As Variant, xim_list As Variant, yim_list As Variant, zim_list As Variant
	Dim tv As Double
	Dim uv As Double


	'CONVERT cartensian to cylindrical

	Select Case comp
		Case "Ez"
			zre_list=VectorPlot3D.GetList("zre")
			tv=zre_list(0)
			For i_CST_GetListItem=1 To totalPoints
				If Abs(zre_list(i_CST_GetListItem))>Abs(tv) Then
					tv=zre_list(i_CST_GetListItem)
					tr_coord=r_cst_list(i_CST_GetListItem)
					tf_coord=f_cst_list(i_CST_GetListItem)
					tz_coord=z_cst_list(i_CST_GetListItem)
				End If
			Next i_CST_GetListItem

		Case "Hz"
			zim_list=VectorPlot3D.GetList("zim")
			tv=zim_list(0)
			For i_CST_GetListItem=1 To totalPoints
				If Abs(zim_list(i_CST_GetListItem))>Abs(tv) Then
					tv=zim_list(i_CST_GetListItem)
					tr_coord=r_cst_list(i_CST_GetListItem)
					tf_coord=f_cst_list(i_CST_GetListItem)
					tz_coord=z_cst_list(i_CST_GetListItem)
				End If
			Next i_CST_GetListItem

		Case "Er"
			xre_list=VectorPlot3D.GetList("xre")
			yre_list=VectorPlot3D.GetList("yre")
			ReDim vr_list(totalPoints)
			ReDim vf_list(totalPoints)
			tr_coord=r_cst_list(0)
			tf_coord=f_cst_list(0)
			tv=xre_list(0)*-Sin(tf_coord)+yre_list(0)*Cos(tf_coord)
			For i_CST_GetListItem=1 To totalPoints
				ur_coord=r_cst_list(i_CST_GetListItem)
				uf_coord=f_cst_list(i_CST_GetListItem)

				uv=xre_list(i_CST_GetListItem)*Cos(uf_coord)+yre_list(i_CST_GetListItem)*Sin(uf_coord)
				If Abs(uv)>Abs(tv) Then
					tv=uv
					tr_coord=ur_coord
					tf_coord=uf_coord
					tz_coord=z_cst_list(i_CST_GetListItem)
				End If
			Next i_CST_GetListItem
		Case "Ef"
			xre_list=VectorPlot3D.GetList("xre")
			yre_list=VectorPlot3D.GetList("yre")
			ReDim vr_list(totalPoints)
			ReDim vf_list(totalPoints)
			tr_coord=r_cst_list(0)
			tf_coord=f_cst_list(0)
			tv=xre_list(0)*-Sin(tf_coord)+yre_list(0)*Cos(tf_coord)
			For i_CST_GetListItem=1 To totalPoints
				ur_coord=r_cst_list(i_CST_GetListItem)
				uf_coord=f_cst_list(i_CST_GetListItem)
				uv=xre_list(i_CST_GetListItem)*-Sin(uf_coord)+yre_list(i_CST_GetListItem)*Cos(uf_coord)

				If Abs(uv)>Abs(tv) Then
					tv=uv
					tr_coord=ur_coord
					tf_coord=uf_coord
					tz_coord=z_cst_list(i_CST_GetListItem)
				End If
			Next i_CST_GetListItem
		Case "Hr"
			xim_list=VectorPlot3D.GetList("xim")
			yim_list=VectorPlot3D.GetList("yim")
			ReDim vr_list(totalPoints)
			ReDim vf_list(totalPoints)
			tr_coord=r_cst_list(0)
			tf_coord=f_cst_list(0)
			tv=xim_list(0)*-Sin(tf_coord)+yim_list(0)*Cos(tf_coord)
			For i_CST_GetListItem=1 To totalPoints
				ur_coord=r_cst_list(i_CST_GetListItem)
				uf_coord=f_cst_list(i_CST_GetListItem)
				uv=xim_list(i_CST_GetListItem)*Cos(uf_coord)+yim_list(i_CST_GetListItem)*Sin(uf_coord)
				If Abs(uv)>Abs(tv) Then
					tv=uv
					tr_coord=ur_coord
					tf_coord=uf_coord
					tz_coord=z_cst_list(i_CST_GetListItem)
				End If
			Next i_CST_GetListItem
		Case "Hf"
			xim_list=VectorPlot3D.GetList("xim")
			yim_list=VectorPlot3D.GetList("yim")
			ReDim vr_list(totalPoints)
			ReDim vf_list(totalPoints)
			tr_coord=r_cst_list(0)
			tf_coord=f_cst_list(0)
			tv=xim_list(0)*-Sin(tf_coord)+yim_list(0)*Cos(tf_coord)
			For i_CST_GetListItem=1 To totalPoints
				ur_coord=r_cst_list(i_CST_GetListItem)
				uf_coord=f_cst_list(i_CST_GetListItem)
				uv=xim_list(i_CST_GetListItem)*-Sin(uf_coord)+yim_list(i_CST_GetListItem)*Cos(uf_coord)

				If Abs(uv)>Abs(tv) Then
					tv=uv
					tr_coord=ur_coord
					tf_coord=uf_coord
					tz_coord=z_cst_list(i_CST_GetListItem)
				End If
			Next i_CST_GetListItem
	End Select


	rcoord=tr_coord
	fcoord=tf_coord
	zcoord=tz_coord
	cst_value=Abs(tv)

	FindMaximumAbsCylindrical_epllipse=cst_value
End Function

Function Atn2(xcoord As Double,ycoord As Double)
	Dim con01 As Double
	con01=0
	If xcoord<0 And ycoord<0 Then
		con01=-Pi
	ElseIf xcoord<0 And ycoord>0 Then
		con01=Pi
	End If
	Atn2=Atn(ycoord/xcoord)+con01
End Function

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

Function CylindricalFieldAlongCircleZPlane(radius As  Variant, zoffset As Variant,FieldType As String) As Variant
	Dim f_step As Double
	f_step=1
	Dim totalPoints As Integer
	Dim maxsize As Integer
	maxsize=Int(360/f_step)+1
	totalPoints=0
	Dim f_cst As Double
	Dim f_cst_list() As Double,r_cst_list() As Double,z_cst_list() As Double
	Dim x_cst_list() As Double,y_cst_list() As Double
	ReDim f_cst_list(maxsize)
	ReDim r_cst_list(maxsize)
	ReDim z_cst_list(maxsize)
	ReDim x_cst_list(maxsize)
	ReDim y_cst_list(maxsize)
	For f_cst=0 To 360 STEP f_step
		f_cst_list(totalPoints)=f_cst/180 *Pi
		r_cst_list(totalPoints)=radius
		z_cst_list(totalPoints)=zoffset
		x_cst_list(totalPoints) =radius*Cos(f_cst/180*Pi)
		y_cst_list(totalPoints) =radius*Sin(f_cst/180*Pi)
		totalPoints=totalPoints+1
	Next f_cst
	ReDim Preserve x_cst_list(totalPoints)
	ReDim Preserve y_cst_list(totalPoints)
	ReDim Preserve z_cst_list(totalPoints)
	VectorPlot3D.Reset
	VectorPlot3D.SetPoints(x_cst_list,y_cst_list,z_cst_list)
	VectorPlot3D.CalculateList
	Dim xre_list As Variant, yre_list As Variant, zre_list As Variant, xim_list As Variant, yim_list As Variant, zim_list As Variant
	Dim vr As Double,vf As Double
	Dim i_CST As Integer
	Dim uf_coord As Double
	Dim result_list() As Double
	ReDim result_list(totalPoints-1,9)
	'x,y,z,r,f coord x,y,z,r,f comp
	Select Case FieldType
		Case "EField"
			xre_list=VectorPlot3D.GetList("xre")
			yre_list=VectorPlot3D.GetList("yre")
			zre_list=VectorPlot3D.GetList("zre")
			For i_CST=0 To totalPoints-1
				uf_coord=f_cst_list(i_CST)
				vr=xre_list(i_CST)*Cos(uf_coord)+yre_list(i_CST)*Sin(uf_coord)
				vf=xre_list(i_CST)*-Sin(uf_coord)+yre_list(i_CST)*Cos(uf_coord)
				result_list(i_CST,0)=x_cst_list(i_CST)
				result_list(i_CST,1)=y_cst_list(i_CST)
				result_list(i_CST,2)=z_cst_list(i_CST)
				result_list(i_CST,3)=r_cst_list(i_CST)
				result_list(i_CST,4)=uf_coord
				result_list(i_CST,5)=xre_list(i_CST)
				result_list(i_CST,6)=yre_list(i_CST)
				result_list(i_CST,7)=zre_list(i_CST)
				result_list(i_CST,8)=vR
				result_list(i_CST,9)=vf
			Next i_CST
		Case "HField"
			xim_list=VectorPlot3D.GetList("xim")
			yim_list=VectorPlot3D.GetList("yim")
			zim_list=VectorPlot3D.GetList("zim")
			For i_CST=0 To totalPoints-1
				uf_coord=f_cst_list(i_CST)
				vR=xim_list(i_CST)*Cos(uf_coord)+yim_list(i_CST)*Sin(uf_coord)
				vf=xim_list(i_CST)*-Sin(uf_coord)+yim_list(i_CST)*Cos(uf_coord)
				result_list(i_CST,0)=x_cst_list(i_CST)
				result_list(i_CST,1)=y_cst_list(i_CST)
				result_list(i_CST,2)=z_cst_list(i_CST)
				result_list(i_CST,3)=r_cst_list(i_CST)
				result_list(i_CST,4)=uf_coord
				result_list(i_CST,5)=xim_list(i_CST)
				result_list(i_CST,6)=yim_list(i_CST)
				result_list(i_CST,7)=zim_list(i_CST)
				result_list(i_CST,8)=vr
				result_list(i_CST,9)=vf
			Next i_CST
	End Select
	CylindricalFieldAlongCircleZPlane=result_list
End Function


Function CylindricalFieldAlongRadiusZPlane(radius As  Variant, theta As Variant,zoffset As Variant,FieldType As String) As Variant
	Dim r_step As Double
	r_step=1
	Dim totalPoints As Integer
	Dim maxsize As Integer
	maxsize=Int(radius*2/r_step)+1
	totalPoints=0
	Dim r_cst As Double
	Dim f_cst_list() As Double,r_cst_list() As Double,z_cst_list() As Double
	Dim x_cst_list() As Double,y_cst_list() As Double
	ReDim f_cst_list(maxsize)
	ReDim r_cst_list(maxsize)
	ReDim z_cst_list(maxsize)
	ReDim x_cst_list(maxsize)
	ReDim y_cst_list(maxsize)
	For r_cst=-radius To radius STEP r_step
		f_cst_list(totalPoints)=theta
		r_cst_list(totalPoints)=r_cst
		z_cst_list(totalPoints)=zoffset
		x_cst_list(totalPoints) =r_cst*Cos(theta)
		y_cst_list(totalPoints) =r_cst*Sin(theta)
		totalPoints=totalPoints+1
	Next r_cst
	ReDim Preserve x_cst_list(totalPoints)
	ReDim Preserve y_cst_list(totalPoints)
	ReDim Preserve z_cst_list(totalPoints)
	VectorPlot3D.Reset
	VectorPlot3D.SetPoints(x_cst_list,y_cst_list,z_cst_list)
	VectorPlot3D.CalculateList
	Dim xre_list As Variant, yre_list As Variant, zre_list As Variant, xim_list As Variant, yim_list As Variant, zim_list As Variant
	Dim vR As Double,vf As Double
	Dim i_CST As Integer
	Dim uf_coord As Double
	Dim result_list() As Double
	ReDim result_list(totalPoints-1,9)
	'x,y,z,r,f coord x,y,z,r,f comp
	Select Case FieldType
		Case "EField"
			xre_list=VectorPlot3D.GetList("xre")
			yre_list=VectorPlot3D.GetList("yre")
			zre_list=VectorPlot3D.GetList("zre")
			For i_CST=0 To totalPoints-1
				uf_coord=f_cst_list(i_CST)
				vR=xre_list(i_CST)*Cos(uf_coord)+yre_list(i_CST)*Sin(uf_coord)
				vf=xre_list(i_CST)*-Sin(uf_coord)+yre_list(i_CST)*Cos(uf_coord)
				result_list(i_CST,0)=x_cst_list(i_CST)
				result_list(i_CST,1)=y_cst_list(i_CST)
				result_list(i_CST,2)=z_cst_list(i_CST)
				result_list(i_CST,3)=r_cst_list(i_CST)
				result_list(i_CST,4)=uf_coord
				result_list(i_CST,5)=xre_list(i_CST)
				result_list(i_CST,6)=yre_list(i_CST)
				result_list(i_CST,7)=zre_list(i_CST)
				result_list(i_CST,8)=vr
				result_list(i_CST,9)=vf
			Next i_CST
		Case "HField"
			xim_list=VectorPlot3D.GetList("xim")
			yim_list=VectorPlot3D.GetList("yim")
			zim_list=VectorPlot3D.GetList("zim")
			For i_CST=0 To totalPoints-1
				uf_coord=f_cst_list(i_CST)
				vR=xim_list(i_CST)*Cos(uf_coord)+yim_list(i_CST)*Sin(uf_coord)
				vf=xim_list(i_CST)*-Sin(uf_coord)+yim_list(i_CST)*Cos(uf_coord)
				result_list(i_CST,0)=x_cst_list(i_CST)
				result_list(i_CST,1)=y_cst_list(i_CST)
				result_list(i_CST,2)=z_cst_list(i_CST)
				result_list(i_CST,3)=r_cst_list(i_CST)
				result_list(i_CST,4)=uf_coord
				result_list(i_CST,5)=xim_list(i_CST)
				result_list(i_CST,6)=yim_list(i_CST)
				result_list(i_CST,7)=zim_list(i_CST)
				result_list(i_CST,8)=vR
				result_list(i_CST,9)=vf
			Next i_CST
	End Select
	CylindricalFieldAlongRadiusZPlane=result_list
End Function

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

Function CylindricalFieldAlongZAxis(radius As  Variant, theta As Variant,Z0 As Variant,zt As Variant,FieldType As String) As Variant
	Dim z_step As Double
	z_step=1
	Dim totalPoints As Integer
	Dim maxsize As Integer
	maxsize=Int(Abs(zt-Z0)/z_step)+1
	totalPoints=0
	Dim z_cst As Double
	Dim f_cst_list() As Double,r_cst_list() As Double,z_cst_list() As Double
	Dim x_cst_list() As Double,y_cst_list() As Double
	ReDim f_cst_list(maxsize)
	ReDim r_cst_list(maxsize)
	ReDim z_cst_list(maxsize)
	ReDim x_cst_list(maxsize)
	ReDim y_cst_list(maxsize)
	Dim x0 As Double,y0 As Double
	x0=radius*Cos(theta)
	y0=radius*Sin(theta)
	For z_cst=Z0 To zt STEP z_step
		f_cst_list(totalPoints)=theta
		r_cst_list(totalPoints)=radius
		z_cst_list(totalPoints)=z_cst
		x_cst_list(totalPoints)=x0 
		y_cst_list(totalPoints)=y0
		totalPoints=totalPoints+1
	Next z_cst
	ReDim Preserve x_cst_list(totalPoints)
	ReDim Preserve y_cst_list(totalPoints)
	ReDim Preserve z_cst_list(totalPoints)
	VectorPlot3D.Reset
	VectorPlot3D.SetPoints(x_cst_list,y_cst_list,z_cst_list)
	VectorPlot3D.CalculateList
	Dim xre_list As Variant, yre_list As Variant, zre_list As Variant, xim_list As Variant, yim_list As Variant, zim_list As Variant
	Dim vr As Double,vf As Double
	Dim i_CST As Integer
	Dim uf_coord As Double
	Dim result_list() As Double
	ReDim result_list(totalPoints-1,9)
	'x,y,z,r,f coord x,y,z,r,f comp
	Select Case FieldType
		Case "EField"
			xre_list=VectorPlot3D.GetList("xre")
			yre_list=VectorPlot3D.GetList("yre")
			zre_list=VectorPlot3D.GetList("zre")
			For i_CST=0 To totalPoints-1
				uf_coord=f_cst_list(i_CST)
				vR=xre_list(i_CST)*Cos(uf_coord)+yre_list(i_CST)*Sin(uf_coord)
				vf=xre_list(i_CST)*-Sin(uf_coord)+yre_list(i_CST)*Cos(uf_coord)
				result_list(i_CST,0)=x_cst_list(i_CST)
				result_list(i_CST,1)=y_cst_list(i_CST)
				result_list(i_CST,2)=z_cst_list(i_CST)
				result_list(i_CST,3)=r_cst_list(i_CST)
				result_list(i_CST,4)=uf_coord
				result_list(i_CST,5)=xre_list(i_CST)
				result_list(i_CST,6)=yre_list(i_CST)
				result_list(i_CST,7)=zre_list(i_CST)
				result_list(i_CST,8)=vR
				result_list(i_CST,9)=vf
			Next i_CST
		Case "HField"
			xim_list=VectorPlot3D.GetList("xim")
			yim_list=VectorPlot3D.GetList("yim")
			zim_list=VectorPlot3D.GetList("zim")
			For i_CST=0 To totalPoints-1
				uf_coord=f_cst_list(i_CST)
				vR=xim_list(i_CST)*Cos(uf_coord)+yim_list(i_CST)*Sin(uf_coord)
				vf=xim_list(i_CST)*-Sin(uf_coord)+yim_list(i_CST)*Cos(uf_coord)
				result_list(i_CST,0)=x_cst_list(i_CST)
				result_list(i_CST,1)=y_cst_list(i_CST)
				result_list(i_CST,2)=z_cst_list(i_CST)
				result_list(i_CST,3)=r_cst_list(i_CST)
				result_list(i_CST,4)=uf_coord
				result_list(i_CST,5)=xim_list(i_CST)
				result_list(i_CST,6)=yim_list(i_CST)
				result_list(i_CST,7)=zim_list(i_CST)
				result_list(i_CST,8)=vR
				result_list(i_CST,9)=vf
			Next i_CST
	End Select
	CylindricalFieldAlongZAxis=result_list
End Function

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

Sub postProcess(saveDir As String,id As Variant)
	Dim value As Double
	Const Z0 As Double=Sqr(Mu0/Eps0)
	Const alpha As Double=10
	Dim xcoord As Double, ycoord As Double, zcoord As Double
	Dim i As Double,r As Double
	Dim ezabsmax As Double,hzabsmax As Double
	Dim coffd As Double, coffd2 As Double
	Dim etabsmax As Double,htabsmax As Double

	Const basepath As String=""
	Dim fieldResultPath As String

	Dim uresult1D As Object
	Dim resultArray As Variant
	Dim rxy As Double,rz As Double
	Dim radius As Double,z_0 As Double,z_t As Double
	Dim conv1 As Double, conv2 As Double
	Dim ezabssum As Double, hzabssum As Double
	radius = RestoreDoubleParameter(RIdStr)
	z_0=-RestoreDoubleParameter(LIdStr)*0.5
	z_t=RestoreDoubleParameter(LIdStr)*0.5

	conv1=0
	conv2=0
	Dim finconv As Double
	If conv1>conv2 Then
		finconv=conv1
	Else
		finconv=conv2
	End If
	rxy = radius*0.9
	rz = (RestoreDoubleParameter(LIdStr)*0.5-finconv)*0.9

	Open(saveDir & "Mode_"& id &"_Coffs.txt") For Output As #99



	i=1
	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\e\Z")
	ezabsmax=FindMaximumAbs3D_epllipse("Ez",rxy,rz,xcoord, ycoord, zcoord)
	Print #99,"Max_Abs_Ez"
	Print #99,"xcoord";vbTab;"ycoord";vbTab;"zcoord";vbTab;"value"
	Print #99,xcoord;vbTab;ycoord;vbTab;zcoord;vbTab;ezabsmax

	ezabssum=SumFieldAbsCylindrical_epllipse("Ez",rxy,rz)
	Print #99,"Sum_Abs_Ez"
	Print #99,"value"
	Print #99,ezabssum

	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\h\Z")
	hzabsmax=FindMaximumAbs3D_epllipse("Hz",rxy,rz,xcoord, ycoord, zcoord)

	Print #99,"Max_Abs_Hz"
	Print #99,"xcoord";vbTab;"ycoord";vbTab;"zcoord";vbTab;"value"
	Print #99,xcoord;vbTab;ycoord;vbTab;zcoord;vbTab;hzabsmax

	hzabssum=SumFieldAbsCylindrical_epllipse("Hz",rxy,rz)
	Print #99,"Sum_Abs_Hz"
	Print #99,"value"
	Print #99,hzabssum

	coffd=ezabsmax/hzabsmax/Z0
	ReportInformation("TEMcoff:"& coffd)

	coffd2=ezabssum/hzabssum/Z0
	ReportInformation("TEMcoff_method2:"& coffd2)
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

	Print #99,"TEM_Coffs"
	Print #99,"value"
	Print #99,coffd

	Print #99,"TEM_Coffs_method2"
	Print #99,"value"
	Print #99,coffd2



	Dim rcoord As Double,fcoord As Double

	'Efield
	'find max e_theta
	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\e")
	etabsmax=FindMaximumAbsCylindrical_epllipse("Ef",rxy,rz,rcoord, fcoord, zcoord) 'in cylind coordiates R F Z Fcoord in degrees



	fcoord=fcoord 'convert to radian
	'convert to xy coord
	xcoord=rcoord*Cos(fcoord)
	ycoord=rcoord*Sin(fcoord)

	ReportInformation("MAXABSE_F:" & etabsmax)

	Print #99,"Max_Abs_Ef"
	Print #99,"xcoord";vbTab;"ycoord";vbTab;"zcoord";vbTab;"rcoord";vbTab;"fcoord";vbTab;"value"
	Print #99,xcoord;vbTab;ycoord;vbTab;zcoord;vbTab;rcoord;vbTab;fcoord;vbTab;etabsmax

	'get fields along the curve

	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\e")

	'''E Field along circle
	resultArray=CylindricalFieldAlongCircleZPlane(rcoord,zcoord,"EField")
	saveCustomField(resultArray,saveDir,id,"E_Circle")


	'''E Field along Radius

	resultArray=CylindricalFieldAlongRadiusZPlane(radius,fcoord,zcoord,"EField")
	saveCustomField(resultArray,saveDir,id,"E_Radius")


	'''E Field along z axis

	resultArray=CylindricalFieldAlongZAxis(rcoord,fcoord,z_0,z_t,"EField")
	saveCustomField(resultArray,saveDir,id,"E_ZLine")


	'HField
	'find max h_theta
	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\h")
	htabsmax=FindMaximumAbsCylindrical_epllipse("Hf",rxy,rz,rcoord, fcoord, zcoord) 'in cylind coordiates R F Z
	ReportInformation("MAXABSH_F:" & htabsmax)

	fcoord=fcoord
	'convert to xy coord
	xcoord=rcoord*Cos(fcoord)
	ycoord=rcoord*Sin(fcoord)

	Print #99,"Max_Abs_Hf"
	Print #99,"xcoord";vbTab;"ycoord";vbTab;"zcoord";vbTab;"rcoord";vbTab;"fcoord";vbTab;"value"
	Print #99,xcoord;vbTab;ycoord;vbTab;zcoord;vbTab;rcoord;vbTab;fcoord;vbTab;htabsmax

	'get fields along the curve
	SelectTreeItem("2D/3D Results\Modes\Mode "& i &"\h")
	'''H Field along circle


	resultArray=CylindricalFieldAlongCircleZPlane(rcoord,zcoord,"HField")
	saveCustomField(resultArray,saveDir,id,"H_Circle")




	'''H Field along radius

	resultArray=CylindricalFieldAlongRadiusZPlane(radius,fcoord,zcoord,"HField")
	saveCustomField(resultArray,saveDir,id,"H_Radius")


	'''H Field along z axis


	resultArray=CylindricalFieldAlongZAxis(rcoord,fcoord,z_0,z_t,"HField")
	saveCustomField(resultArray,saveDir,id,"H_ZLine")

	Print #99,"Model_Info"
	Print #99,"model_name";vbTab;"USER_STRUCT"
	Print #99,"3D Field Output";vbTab

	Print #99,"HField_3D_info"
	Print #99,"xdims";vbTab;"ydims";vbTab;"zdims"
	Print #99,128;vbTab;128;vbTab;32;vbTab

	Print #99,"EField_3D_info"
	Print #99,"xdims";vbTab;"ydims";vbTab;"zdims"
	Print #99,128;vbTab;128;vbTab;32;vbTab

	Close #99
End Sub
Sub compute

	EigenmodeSolver.Start
End Sub

Sub nextMode(ByRef id As Integer)
	Dim freq_01 As Double
	Dim freq_02 As Double
	Dim freq As Double
	freq_01=EigenmodeSolver.GetModeFrequencyInHz(1)
	freq_02=EigenmodeSolver.GetModeFrequencyInHz(2)
	freq=freq_01/1E6
	ReportInformation("Mode " & id & ":Freq " & freq_01 & " Mhz")
	freq=freq_02/1E6
	ReportInformation("Next fmin " & ":Freq " & freq_02 & " Mhz")
	freq=(freq_01+freq_02)/2/1E6
	StoreParameter("fmin", freq)
	StoreParameter("fmax", Round(freq+500))
End Sub

Sub fmaxfix()
	Dim fmax As Double
	fmax=RestoreParameter("fmax")
	StoreParameter("fmax", Round(fmax+1))
End Sub

Sub saveCustomField(resultArray() As Double, saveDir As String, id As Variant, fieldname As Variant)
	Dim full_path As String
	full_path=saveDir & "Mode_" & id & "_" & fieldname & ".txt"
	Open(full_path) For Output As #1
	Dim linecount As Integer,i As Integer
	Dim str_item As String

	Print #1,"X";vbTab;"Y";vbTab;"Z";vbTab;"R";vbTab;"F";vbTab;"VX";vbTab;"VY";vbTab;"VZ";vbTab;"VR";vbTab;"VF"
	For linecount=LBound(resultArray,1) To UBound(resultArray,1)
		For i=LBound(resultArray,2) To UBound(resultArray,2)

			Print #1,resultArray(linecount,i);" ";vbTab;
		Next i
		Print #1
	Next linecount

	Close #1
End Sub

Sub saveResult(saveDir As String, id As Variant)

	
	' Dim A As Variant,B As Variant,C As Variant
	' Dim fi As String,cr As String,cm As String
	' A = Array("H","E")
	' B = Array("Z","R","C")
	' C= Array("T","X","Y","Z")
	' For Each fi In A
	' 	For Each cr In B
	' 		For Each cm In C
	' 			SelectTreeItem("1D Results\Data\Mode_" & 1 & "_" & fi & cr & "_" & cm)
	' 			With ASCIIExport
	' 				.Reset
	' 				.FileName (saveDir & "Mode_" & id & "_" & fi & cr & "_" & cm & ".txt")
	' 				.Execute
	' 			End With
	' 		Next cm
	' 	Next cr
	' Next fi
	
	'save freq
	Dim xmin As Double,xmax As Double,ymin As Double,ymax As Double,zmin As Double,zmax As Double
	Dim r As Double,l As Double
	r=RestoreParameter(RIdStr)
	l=RestoreParameter(LIdStr)
	xmin=-r
	xmax=r
	ymin=-r
	ymax=r
	zmin=-l/2
	zmax=l/2
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
		.SetSubvolume(xmin, xmax,ymin, ymax,zmin,zmax )

		.UseSubvolume(True)
		.FileName (saveDir & "Mode_"& id &"_EField.txt")
		.Mode ("FixedNumber")
		.StepX (128)
		.StepY (128)
		.StepZ (32)
		.Execute
	End With

	SelectTreeItem("2D/3D Results\Modes\Mode "& 1 &"\h")
	With ASCIIExport
		.Reset
		.SetSubvolume(xmin, xmax,ymin, ymax,zmin,zmax )
		.UseSubvolume(True)
		.FileName (saveDir & "Mode_"& id &"_HField.txt")
		.Mode ("FixedNumber")
		.StepX (128)
		.StepY (128)
		.StepZ (32)
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

Function IsFileExists(ByVal strFileName As String) As Boolean
    If Dir(strFileName, 16) <> Empty Then
        IsFileExists = True
    Else
        IsFileExists = False
    End If
End Function
Sub LinkRL_Interactive()
	If Not DoesParameterExist("R") Or Not DoesParameterExist("L") Then
		Begin Dialog UserDialog 400,203 ' %GRID:10,7,1,1
			Text 50,28,190,28,"L/R Parameter NOT found",.Text1
			OKButton 60,147,80,21
			CancelButton 190,147,120,21
			Text 40,77,100,21,"L Name",.Text2
			TextBox 40,105,160,21,.LName
			Text 250,77,100,21,"R Name",.Text3
			TextBox 250,105,130,21,.RName
		End Dialog
		Dim dlg As UserDialog
		Dialog dlg
		LinkRL_Force(dlg.RName,dlg.LName)
	Else
		LinkRL_Force("R","L")
	End If
End Sub
Sub LinkRL_Force(RName As String,LName As String)
	RIdStr=RName
	LIdStr=LName
End Sub
Public RIdStr As String
Public LIdStr As String
Sub Main

	StoreParameter("nmodes", 2)
	EigenmodeSolver.SetNumberOfModes(2)
	'StoreParameter("fmin", 480)
	'StoreParameter("fmax", 3000)
	LinkRL_Interactive()
	SimpleSaveModes(50)
End Sub
Sub SimpleSaveModes(ModeCount As Integer)
	Dim resultDir As String,pt1 As String,pt2 As String
	pt1="D:\PillVarientTest\"
	If Not IsFileExists(pt1) Then
		MkDir (pt1)
	End If
	resultDir=pt1 & "ResultFirst50" & "\"
	If Not IsFileExists(resultDir) Then
		MkDir (resultDir)
	End If
	mainloop(ModeCount,resultDir)

End Sub

Sub MyParameterSweep()
	Dim vL As Double, vR As Double
	Dim vL_r As Double, vR_r As Double
	Dim start As Boolean,midstart As Boolean
	Dim resultDir As String,pt1 As String,pt2 As String
	pt1="D:\PillVarientTest\"
	If Not IsFileExists(pt1) Then
		MkDir (pt1)
	End If
	start=False
	midstart=True
	vR_r=210
	vL_r=280

	For vR=190 To 270 STEP 10
		For vL=230 To 290 STEP 10
			If midstart Then
				If vR=vR_r And vL=vL_r Then
					midstart=False
				Else
					GoTo REND
				End If
			End If
			StoreParameter("fmin", 0)
			StoreParameter("fmax", 1500)
			StoreParameter("Req", vR)
			StoreParameter("Leq", vL)
			resultDir=pt1 & "R_" & vR & "_L_" & vL & "\"
			If Not IsFileExists(resultDir) Then
				MkDir (resultDir)
			End If
			mainloop(50,resultDir)

			REND:'END of Run
		Next vL
	Next vR



End Sub

Sub mainloop(maxcount As Integer,resultDir As String)
	Dim id As Integer
	id=1
	For id=1 To maxcount
		Rebuild
		compute()
		'check avil modes
		Do While EigenmodeSolver.GetNumberOfModesCalculated()=1
			fmaxfix()
			Rebuild
			compute()
		Loop
		Backup(resultDir & "Mode_" & id & ".cst")
		postProcess(resultDir, id)
		saveResult(resultDir, id)
		nextMode(id)
		Rebuild
	Next id
End Sub

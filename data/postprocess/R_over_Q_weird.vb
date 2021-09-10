Function votage(iModeNumber As Integer,axis As Integer,ByRef iUVWvalue() As Double) As Double()
    If (iModeNumber > EigenmodeSolver.GetNumberOfModesCalculated) Then
            ReportWarningToWindow("3D Eigenmode result template execution: Cannot find result for mode #"+CStr(iModeNumber)+".")
            'CalculateEigenModeResult = lib_rundef
            Exit Function
    End If
    Dim frq_cst As Double
    frq_cst = EigenmodeSolver.GetModeFrequencyInHz(iModeNumber)/Units.GetFrequencyUnitToSI
    If (Not SelectTreeItem("2D/3D Results\Modes\Mode " + CStr(iModeNumber) + "\e")) Then
                    ReportWarningToWindow("Error in 3D Eigenmode result template execution: Cannot find result for mode #"+CStr(iModeNumber)+".")
                    'CalculateEigenModeResult = lib_rundef
                    Exit Function
    End If
    Plot.Update
    ScreenUpdating True
    Wait 0.3
    Dim eng_cst As Double
    With QFactor
        .Reset
        .SetHField "Mode " + Trim(Str(iModeNumber))
        .Calculate
        eng_cst = .GetTotalEnergy
    End With
    ' . get min and max meshstep

    Dim dMeshMin As Double, dMeshMax As Double, dStepNow As Double
    Dim dmline1 As Double, dmline2 As Double, nMeshTmp As Long
    Dim dAbsMeshMax As Double

    Dim x1box As Double, x2box As Double
    Dim y1box As Double, y2box As Double
    Dim z1box As Double, z2box As Double

    Boundary.GetCalculationBox x1box, x2box, y1box, y2box, z1box, z2box

    dAbsMeshMax = 0

    With Mesh

        On Error GoTo NoMeshExists

        dMeshMin = .GetMinimumEdgeLength
        dMeshMax = .GetMaximumEdgeLength

        On Error GoTo 0
        GoTo MeshExists

    NoMeshExists:
        'CalculateEigenModeResult = lib_rundef
        ReportError "No Mesh Exists."
        Exit Function

    MeshExists:
        If Abs(x1box) > dAbsMeshMax Then dAbsMeshMax = Abs(x1box)
        If Abs(y1box) > dAbsMeshMax Then dAbsMeshMax = Abs(y1box)
        If Abs(z1box) > dAbsMeshMax Then dAbsMeshMax = Abs(z1box)

        If Abs(x2box) > dAbsMeshMax Then dAbsMeshMax = Abs(x2box)
        If Abs(y2box) > dAbsMeshMax Then dAbsMeshMax = Abs(y2box)
        If Abs(z2box) > dAbsMeshMax Then dAbsMeshMax = Abs(z2box)
        ' search all X-Meshlines

    End With

    Dim iDir_CST As Integer
    Dim bmaxrange_CST As Boolean
    'iDir_CST		= 1+CInt(GetScriptSetting("coordinates","0")) ' 1 for X, 2 for Y, 3 for Z
	iDir_CST=axis
	bmaxrange_CST=True

    Dim dUVWvalue(3,3) As Double ' first index=u,v,w   second index=low,high,step

    'dUVWvalue(1,1) = Evaluate (GetScriptSetting("u1","0.0"))
    'dUVWvalue(2,1) = Evaluate (GetScriptSetting("v1","0.0"))
    'dUVWvalue(3,1) = Evaluate (GetScriptSetting("w1","0.0"))
    'dUVWvalue(1,2) = Evaluate (GetScriptSetting("u2","0.0"))
    'dUVWvalue(2,2) = Evaluate (GetScriptSetting("v2","0.0"))
    'dUVWvalue(3,2) = Evaluate (GetScriptSetting("w2","0.0"))
    dUVWvalue(1,1) = iUVWvalue(1,1)
    dUVWvalue(2,1) = iUVWvalue(2,1)
	dUVWvalue(3,1) = iUVWvalue(3,1)
    dUVWvalue(1,2) = iUVWvalue(1,2)
    dUVWvalue(2,2) = iUVWvalue(2,2)
    dUVWvalue(3,2) = iUVWvalue(3,2)
	'dUVWvalue=iUVWvalue




    Dim ddStep As Double, nIndex As Long
    Select Case Mesh.GetMeshType
    Case "Surface", "Tetrahedral"
        If 50.0*dMeshMin > dMeshMax Then
            ddStep = 0.5 * dMeshMin
        Else
            ddStep = 0.1 * dMeshMax
        End If
    Case Else
        ' hex
        ddStep = 0.5 * dMeshMin ' for 1D half of min meshstep is used
    End Select

    Dim xyzbox(3,2) As Double
    xyzbox(1,1) = x1box
    xyzbox(1,2) = x2box
    xyzbox(2,1) = y1box
    xyzbox(2,2) = y2box
    xyzbox(3,1) = z1box
    xyzbox(3,2) = z2box

    ' if max-range, then set minmax values dep. on dim and coord.system

    If (bmaxrange_CST) Then
        dUVWvalue(iDir_CST,1) = xyzbox(iDir_CST,1)
        dUVWvalue(iDir_CST,2) = xyzbox(iDir_CST,2)
    End If

    ' now maxrange is set, all dUVWvalues() are set now

    '----------------------------------------------------------------------------------
    ' adjust final min, max values and afterwards adjust the stepsize, fitting to it
    ' also, recalculate angle-stepwidth from from ddStep

    Dim dstptmp As Double, nstpstmp As Long, dminmaxtmp As Double

    ' max=min, step = 1 for all directions unequal idir direction

    For nIndex = 1 To 3
        If nIndex <> iDir_CST Then
            dUVWvalue(nIndex,2) = dUVWvalue(nIndex,1)
            dUVWvalue(nIndex,3) = 1
        End If
    Next

    dstptmp = ddStep

    dminmaxtmp = dUVWvalue(iDir_CST,2)-dUVWvalue(iDir_CST,1)

    nstpstmp = CLng ( dminmaxtmp / dstptmp )
    If nstpstmp < 1 Then nstpstmp = 1
    dUVWvalue(iDir_CST,3) = dminmaxtmp / nstpstmp

    '----------------------------------------------------------------------------------
    '----------------------------------------------------------------------------------
    ' finally set min startpoint (1d => ONLY in IDIR, 2d=> ALL, but not for IDIR) at half stepsize

    dUVWvalue(iDir_CST,1) = dUVWvalue(iDir_CST,1) + 0.5 * dUVWvalue(iDir_CST,3)

    ' . loop over abc  (fit stepsize to range, then start at step/2)
    '   do a = amin + astep/2,  am Ende der Loop:  a = a + astep until a > amax
    ' for a=amin to amax step astep    (astep=1 amin=amax falls keine Loop)

    Dim u_CST As Double, v_CST As Double, w_CST As Double
    Dim x_CST As Double, y_CST As Double, z_CST As Double

    Dim dVoxel_Unit As Double, dVoxel_SI As Double
    dVoxel_Unit = 1

    ' angle-stepwidth needs to be taken in radian, new array dStepLength(1-3)

    Dim dStepLength(3) As Double
    For nIndex = 1 To 3
        dStepLength(nIndex) = dUVWvalue(nIndex,3)
    Next

    dVoxel_Unit = dVoxel_Unit * dStepLength(iDir_CST)
    dVoxel_SI = dVoxel_Unit * (Units.GetGeometryUnitToSI())

    Dim dRef_Voxel_Unit As Double, dRef_Voxel_SI As Double, dRsinTheta As Double

    Dim sFieldCST As String, bScalar As Boolean
    Dim sComponentCST As String
    Dim sComplexCST As String
    'Dim sActionCST As String

    sFieldCST		= "Modes\Mode " + Trim(Str(iModeNumber)) + "\e"
    sComponentCST	= "Tangential"
    'sActionCST 		= GetScriptSetting("a0DValue","")

    Mesh.ViewMeshMode  False

    If (Not SelectTreeItem("2D/3D Results\"+ sFieldCST)) Then
        'CalculateEigenModeResult = lib_rundef
        ReportError "Result not found in tree: " + sFieldCST
        Exit Function
    End If

    Plot3DPlotsOn2DPlane False
    bScalar = bScalarField(sFieldCST)

    Dim bLokVA_CST As Boolean, bLokVB_CST As Boolean, bLokVC_CST As Boolean
    bLokVA_CST = False		' rfw, rfz or rtf
    bLokVB_CST = False		' uvw
    bLokVC_CST = False		' xyz

    Dim va_CST(2) As Double, vb_CST(2) As Double, vc_CST(2) As Double
    For nIndex = 0 To 2
        va_CST(nIndex) = 0.0 	' component in rfw, rfz or rtf coordinates
        vb_CST(nIndex) = 0.0 	' component in uvw coordinates
        vc_CST(nIndex) = 0.0 	' component in xyz coordinates
    Next

    Dim im1Dir_CST As Integer
    im1Dir_CST = iDir_CST-1
    Select Case sComponentCST
        Case "Scalar"
            ' vector transformation not required for scalar
            ' MsgBox "hello scalar"
        Case "Tangential"
            ' -----------------------------------
            ' always true for cartesian + global
            ' -----------------------------------
            bLokVC_CST = True
            vc_CST(im1Dir_CST) = 1.0
    End Select
    Dim bFieldError As Boolean

    Dim vxre As Double, vxim As Double
    Dim vyre As Double, vyim As Double
    Dim vzre As Double, vzim As Double

    Dim vxam As Double, vxph As Double
    Dim vyam As Double, vyph As Double
    Dim vzam As Double, vzph As Double

    Dim vxTmp As Double, vyTmp As Double, vzTmp As Double, vNowCST As Double

    Dim dSumVoxel_Unit As Double
    Dim dSumIntegral As Double
    Dim dMaxCST As Double
    Dim dMinCST As Double

    Dim nDataCST As Long
    nDataCST = 0

    dSumVoxel_Unit = 0.0
    dSumIntegral = 0.0
    dMaxCST = lib_rundef ' -1.23456e27
    dMinCST = - lib_rundef ' 1.23456e27

    Dim rbeta As Double, alfa As Double, cosa As Double, sina As Double, dw As Double
    Dim iTTF As Integer, vwsumre As Double, vwsumim As Double, alfa_fac As Double, stmp As String

    'iTTF = CInt(GetScriptSetting("Check_ttf","0"))
    iTTF=1
    dw = dUVWvalue(iDir_CST,3)* Units.GetGeometryUnitToSI()
    vwsumre = 0.0
    vwsumim = 0.0

    If (iTTF = 0) Then
        alfa        = 0
        cosa        = 1
        sina        = 0
    Else
        'rbeta = Evaluate(GetScriptSetting("beta","not used"))
        rbeta=1
        alfa_fac    = Units.GetGeometryUnitToSI() * (2 * Pi * frq_cst * Units.GetFrequencyUnitToSI()) / (rbeta * CLight)
    End If

    Dim bTake_this_point As Boolean

    Dim uvw_CST(2) As Double, bbb(2) As Double, xyz_CST(2) As Double

    VectorPlot3D.Reset   ' necessary to reset list items


    ' ===============================================
    ' --- Loop ONE - writing points into list
    ' ===============================================

    For u_CST = dUVWvalue(1,1) To dUVWvalue(1,2) STEP dUVWvalue(1,3)
    uvw_CST(0) = u_CST

    For v_CST = dUVWvalue(2,1) To dUVWvalue(2,2) STEP dUVWvalue(2,3)
    uvw_CST(1) = v_CST

    For w_CST = dUVWvalue(3,1) To dUVWvalue(3,2) STEP dUVWvalue(3,3)
    uvw_CST(2) = w_CST

        ' if not cartesian : transfer uvw into cartesian xyz_CST

        xyz_CST(0) = uvw_CST(0)
        xyz_CST(1) = uvw_CST(1)
        xyz_CST(2) = uvw_CST(2)

        x_CST = xyz_CST(0)
        y_CST = xyz_CST(1)
        z_CST = xyz_CST(2)

        ' check abc against box (bei maxrange) + solid (if selected), remember solid-ID (iNowSolid_CST)

        bTake_this_point = False

        If (x_CST >= x1box) And  (x_CST <= x2box) And (y_CST >= y1box) And  (y_CST <= y2box) And (z_CST >= z1box) And  (z_CST <= z2box) Then
            bTake_this_point = True
        End If

        If (bTake_this_point) Then
            bFieldError = VectorPlot3D.AddListItem ( x_CST, y_CST, z_CST )
        End If

    Next w_CST
    Next v_CST
    Next u_CST

    ' ===============================================
    ' --- after Loop ONE - calculate list
    ' ===============================================

    VectorPlot3D.CalculateList

    ' ===============================================
    ' --- Loop TWO - reading fieldvalues from list
    ' ===============================================

    Dim i_CST_GetListItem As Long
    i_CST_GetListItem = 0

    For u_CST = dUVWvalue(1,1) To dUVWvalue(1,2) STEP dUVWvalue(1,3)
    uvw_CST(0) = u_CST

    For v_CST = dUVWvalue(2,1) To dUVWvalue(2,2) STEP dUVWvalue(2,3)
    uvw_CST(1) = v_CST

    For w_CST = dUVWvalue(3,1) To dUVWvalue(3,2) STEP dUVWvalue(3,3)
    uvw_CST(2) = w_CST

        ' if not cartesian : transfer uvw into cartesian xyz_CST

        xyz_CST(0) = uvw_CST(0)
        xyz_CST(1) = uvw_CST(1)
        xyz_CST(2) = uvw_CST(2)

        x_CST = xyz_CST(0)
        y_CST = xyz_CST(1)
        z_CST = xyz_CST(2)

        ' check abc against box (bei maxrange) + solid (if selected), remember solid-ID (iNowSolid_CST)

        bTake_this_point = False

        If (x_CST >= x1box) And  (x_CST <= x2box) And (y_CST >= y1box) And  (y_CST <= y2box) And (z_CST >= z1box) And  (z_CST <= z2box) Then
            bTake_this_point = True
        End If

        If (bTake_this_point) Then

            bFieldError = VectorPlot3D.GetListItem ( i_CST_GetListItem, vxre, vyre, vzre, vxim, vyim, vzim )
            i_CST_GetListItem = i_CST_GetListItem + 1

            'If bLogFileFirstEval Then
            '    Print #3,PP12(x_CST) + PP12(y_CST) + PP12(z_CST)
            'End If

            If ( Not bFieldError ) Then
                'If bLogFileFirstEval Then
                '    Print #2,PP12(x_CST) + PP12(y_CST) + PP12(z_CST) + "   Problem in reading fieldvalue"
                'End If
            Else
                If (iTTF = 1) Then
                    alfa = xyz_CST(iDir_CST-1) * alfa_fac
                    cosa = Cos(alfa)
                    sina = Sin(alfa)
                End If

                If iDir_CST=1 Then
                    vwsumre        = vwsumre + dw * (vxre*cosa - vxim*sina)
                    vwsumim        = vwsumim + dw * (vxim*cosa + vxre*sina)
                    stmp = PP12(vxre) + PP12(vxim)
                ElseIf iDir_CST=2 Then
                    vwsumre        = vwsumre + dw * (vyre*cosa - vyim*sina)
                    vwsumim        = vwsumim + dw * (vyim*cosa + vyre*sina)
                    stmp = PP12(vyre) + PP12(vyim)
                ElseIf iDir_CST=3 Then
                    vwsumre        = vwsumre + dw * (vzre*cosa - vzim*sina)
                    vwsumim        = vwsumim + dw * (vzim*cosa + vzre*sina)
                    stmp = PP12(vzre) + PP12(vzim)
                End If
                'If bLogFileFirstEval Then
                '    Print #2,PP12(u_CST) + PP12(v_CST) + PP12(w_CST) + PP12(dw) + stmp + PP12(cosa) + PP12(sina) + PP12(vwsumre) + PP12(vwsumim)
                'End If
            End If

            dSumVoxel_Unit = dSumVoxel_Unit + dVoxel_Unit
            nDataCST = nDataCST + 1

        End If

    Next w_CST
    Next v_CST
    Next u_CST
	'Dim vim,vre As Double
    Dim votagecomp(2) As Double
    'vwfull = Sqr(vwsumim*vwsumim+vwsumre*vwsumre)
    'cst_value = vwfull*vwfull/(2*Pi* frq_cst*Units.GetFrequencyUnitToSI() * eng_cst)

    'ReportInformation(cst_value)
    votagecomp(0)=vwsumre
    votagecomp(1)=vwsumim
    votage=votagecomp
End Function

Function R_over_Q_weird_output(iModeNumber As Integer,axis As Integer,xoffset As Double,yoffset As Double,zoffset As Double, outputPath As String)
    Dim roq_weird As Double
    Dim votage0 As Variant
    Dim votage1 As Variant
    Dim uvw(3,3) As Double
    Dim i As Integer
    uvw(1,1)=0
	uvw(1,2)=0
	uvw(1,3)=0
	uvw(2,1)=0
	uvw(2,2)=0
	uvw(2,3)=0
    uvw(3,1)=0
	uvw(3,2)=0
	uvw(3,3)=0
    votage0=R_over_Q_weird(iModeNumber,axis,uvw) 'in centor
    uvw(axis,1)=xoffset
    uvw(axis,2)=yoffset
    uvw(axis,3)=zoffset
    uvw(axis,axis)=0 'RECOVER

    votage1=R_over_Q_weird(iModeNumber,axis,uvw) 'in r0 offset
    Dim r0 As Double
    r0=0
    For i=1 To 3
        r0=r0+uvw(axis,i)*uvw(axis,i)
    End For
    r0=Sqrt(r0)
    Dim re As Double,im As Double
    re=votage0(0)-votage1(0)
    im=votage0(1)-votage1(1)
    
    Dim eng_cst As Double
    With QFactor
        .Reset
        .SetHField "Mode " + Trim(Str(iModeNumber))
        .Calculate
        eng_cst = .GetTotalEnergy
    End With
    Dim frq_cst As Double,k As Double
    frq_cst = EigenmodeSolver.GetModeFrequencyInHz(iModeNumber)/Units.GetFrequencyUnitToSI
    k=1
    roq_weird=Sqrt(re*re+im*im)/(2*Pi* frq_cst*Units.GetFrequencyUnitToSI() * eng_cst*(r0*r0)*(k*k))

    Open(outputPath) For Output As #1
    Print #1,"R_over_Q_weird_result"
    Print #1,"ModeNumber"
    Print #1,iModeNumber
    Print #1,"axisNumber"
    Print #1,axis
    Print #1,"xoffset"
    Print #1,iUVWvalue(axis,1)
    Print #1,"yoffset"
    Print #1,iUVWvalue(axis,2)
    Print #1,"zoffset"
    Print #1,iUVWvalue(axis,3)
    Print #1,"R_over_Q_weird_value"
    Print #1,roq_weird
    Close #1

End Function
Function 3DField_output(outputDir As String, outputName As String, iModeNumber As Integer)

	Dim resultDir As String,pt1 As String,pt2 As String
	If Not IsFileExists(outputDir) Then
			MkDir (outputDir)
	End If
    Dim subvolume(6) As Variant

    saveResult(outputDir,outputName,iModeNumber,False,subvolume)

End Sub

Function 3DField_output_sub(outputDir As String, outputName As String, iModeNumber As Integer,xmin as Varient,xmax as Varient,ymin as Varient,ymax As Varient,zmin As Varient,zmax As Varient)

	Dim resultDir As String,pt1 As String,pt2 As String
	If Not IsFileExists(outputDir) Then
			MkDir (outputDir)
	End If
    Dim subvolume(6) As Variant
    subvolume(1)=xmin
    subvolume(2)=xmax
    subvolume(3)=ymin
    subvolume(4)=ymax
    subvolume(5)=zmin
    subvolume(6)=zmax
    saveResult(outputDir,outputName,iModeNumber,subvolume)

End Sub


Sub saveResult(saveDir As String, saveName As String ,id As Variant,usesub As Boolean,subvolumeDef As Varient)

	
	Dim xmin As Variant,xmax As Variant,ymin As Variant,ymax As Variant,zmin As Variant,zmax As Variant ' Should support expression params
	Dim r As Double,l As Double
	If usesub Then
        xmin=subvolume(1)
        xmax=subvolume(2)
        ymin=subvolume(3)
        ymax=subvolume(4)
        zmin=subvolume(5)
        zmax=subvolume(6)
    End If


	'save E/H fields
	SelectTreeItem("2D/3D Results\Modes\Mode "& 1 &"\e")
	With ASCIIExport
		.Reset
        If usesub Then
		    .SetSubvolume(xmin, xmax,ymin, ymax,zmin,zmax )        
		    .UseSubvolume(True)
        End If
		.FileName (saveDir & "Mode_"& id &"_EField_" & saveName & ".txt")
		.Mode ("FixedNumber")
		.StepX (128)
		.StepY (128)
		.StepZ (32)
		.Execute
	End With

	SelectTreeItem("2D/3D Results\Modes\Mode "& 1 &"\h")
	With ASCIIExport
		.Reset
		If usesub Then
		    .SetSubvolume(xmin, xmax,ymin, ymax,zmin,zmax )        
		    .UseSubvolume(True)
        End If
		.FileName (saveDir & "Mode_"& id &"_HField_" & saveName & ".txt")
		.Mode ("FixedNumber")
		.StepX (128)
		.StepY (128)
		.StepZ (32)
		.Execute
	End With


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
Function IsFileExists(ByVal strFileName As String) As Boolean
    If Dir(strFileName, 16) <> Empty Then
        IsFileExists = True
    Else
        IsFileExists = False
    End If
End Function







#DoubleList fieldType ["xre","yre","zre","xim","yim","zim"]

Function FieldValue(xList As Double(),yList As Double(),zList As Double(),iModeNumber As Integer,fieldComp As String) As Double()
    SelectTreeItem("2D/3D Results\Modes\Mode "& iModeNumber & "\" & fieldComp)
    VectorPlot3D.Reset
    VectorPlot3D.SetPoints(xList,yList,zList)
	VectorPlot3D.CalculateList
    Dim totalPoints As Integer
    Dim i_cst_point As Integer
    totalPoints=UBound(xList)-LBound(xList)
    Dim resultArray(totalPoints,6) As Double
    Dim xre As Variant
    Dim yre As Variant
    Dim zre As Variant
    Dim xim As Variant
    Dim yim As Variant
    Dim zim As Variant
    xre=VectorPlot3D.GetList("xre")
    yre=VectorPlot3D.GetList("yre")
    zre=VectorPlot3D.GetList("zre")
    xim=VectorPlot3D.GetList("xim")
    yim=VectorPlot3D.GetList("yim")
    zim=VectorPlot3D.GetList("zim")
    For i_cst_point=0 To totalPoints
        resultArray(i_cst_point,0)=xre(i_cst_point)
        resultArray(i_cst_point,1)=yre(i_cst_point)
        resultArray(i_cst_point,2)=zre(i_cst_point)
        resultArray(i_cst_point,3)=xim(i_cst_point)
        resultArray(i_cst_point,4)=yim(i_cst_point)
        resultArray(i_cst_point,5)=zim(i_cst_point)
    Next i_cst_point
    FieldValue=resultArray
End Function

Function FieldValue_output(xList As Double(),yList As Double(),zList As Double(),iModeNumber As Integer,fieldComp As String, outputPath As String)
    Dim resultArray As Double()
    Dim 
    resultArray=FieldValue_output(xList,yList,zList,iModeNumber,fieldComp,outputPath)
    Open(outputPath) For Output As #1
    For linecount=LBound(resultArray,1) To UBound(resultArray,1)
		For i=LBound(resultArray,2) To UBound(resultArray,2)

			Print #1,resultArray(linecount,i);" ";vbTab;
		Next i
		Print #1
	Next linecount
    Close #1
End Function
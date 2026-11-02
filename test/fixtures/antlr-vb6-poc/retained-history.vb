With Units
 .Geometry "mm"
 .Frequency "MHz"
End With
ChangeSolverType "HF Eigenmode"
With Background
 .Type "pec"
 .XminSpace 0
 .XmaxSpace 0
 .YminSpace 0
 .YmaxSpace 0
 .ZminSpace 0
 .ZmaxSpace 0
End With
With Boundary
 .Xmin "electric"
 .Xmax "electric"
 .Ymin "electric"
 .Ymax "electric"
 .Zmin "electric"
 .Zmax "electric"
 .Xsymmetry "none"
 .Ysymmetry "none"
 .Zsymmetry "none"
End With
WCS.ActivateWCS "global"
Component.New "cavity"
With Cylinder
 .Reset
 .Name "pillbox"
 .Component "cavity"
 .Material "Vacuum"
 .Axis "z"
 .OuterRadius 0+RestoreDoubleParameter("R")
 .InnerRadius 0
 .Xcenter 0
 .Ycenter 0
 .Zcenter 0
 .Zrange 0+((-RestoreDoubleParameter("L"))/2), 0+(RestoreDoubleParameter("L")/2)
 .Segments 0
 .Create
End With
EigenmodeSolver.Reset
Solver.FrequencyRange "500", "2000"
Mesh.MeshType "Tetrahedral"
With MeshSettings
 .SetMeshType "Tet"
 .Set "Version", 1
 .Set "StepsPerWaveNear", "4"
 .Set "StepsPerWaveFar", "4"
 .Set "CellsPerWavelengthPolicy", "cellsperwavelength"
End With
With EigenmodeSolver
 .SetMethodType "Default", "Tet"
 .SetMeshType "Tetrahedral Mesh"
 .SetFrequencyTarget True, "500"
 .SetNumberOfModes 1
 .SetMeshAdaptationTet False
 .SetConsiderLossesInPostprocessingOnly True
End With
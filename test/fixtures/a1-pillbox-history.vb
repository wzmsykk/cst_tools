'@ units and solver identity
With Units
    .Geometry "mm"
    .Frequency "MHz"
End With
ChangeSolverType "HF Eigenmode"
'@ material domain and boundary declarations
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
'@ single parameterized vacuum cylinder
WCS.ActivateWCS "global"
Component.New "cavity"
With Cylinder
    .Reset
    .Name "pillbox"
    .Component "cavity"
    .Material "Vacuum"
    .Axis "z"
    .OuterRadius RestoreDoubleParameter("R")
    .InnerRadius 0
    .Xcenter 0
    .Ycenter 0
    .Zcenter 0
    .Zrange -RestoreDoubleParameter("L")/2, RestoreDoubleParameter("L")/2
    .Segments 0
    .Create
End With
'@ frequency and fixed modern Tet configuration
EigenmodeSolver.Reset
Solver.FrequencyRange "fmin", "fmax"
Mesh.MeshType "Tetrahedral"
With MeshSettings
    .SetMeshType "Tet"
    .Set "Version", 1
    .Set "StepsPerWaveNear", "cell"
    .Set "StepsPerWaveFar", "cell"
    .Set "CellsPerWavelengthPolicy", "cellsperwavelength"
End With
With EigenmodeSolver
    .SetMethodType "Default", "Tet"
    .SetMeshType "Tetrahedral Mesh"
    .SetFrequencyTarget True, "fmin"
    .SetNumberOfModes CInt(RestoreDoubleParameter("nmodes"))
    .SetMeshAdaptationTet False
    .SetConsiderLossesInPostprocessingOnly True
End With

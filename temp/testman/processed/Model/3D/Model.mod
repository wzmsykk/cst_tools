'# MWS Version: Version 2022.4 - Apr 26 2022 - ACIS 31.0.1 -

'# length = mm
'# frequency = MHz
'# time = ns
'# frequency range: fmin = fmin fmax = fmax
'# created = '[VERSION]2020.0|29.0.1|20190925[/VERSION]


'@ use template: Eigenmode_2.cfg

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
'set the units
With Units
    .Geometry "mm"
    .Frequency "MHz"
    .Voltage "V"
    .Resistance "Ohm"
    .Inductance "H"
    .TemperatureUnit  "Kelvin"
    .Time "ns"
    .Current "A"
    .Conductance "Siemens"
    .Capacitance "F"
End With
'----------------------------------------------------------------------------
With MStaticSolver
     .IgnorePECMaterial "True"
     .Method "Hexahedral Mesh"
End With
With Background
     .Type "pec"
End With
With Mesh
     .MeshType "Tetrahedral"
     .SetCreator "High Frequency"
End With
With MeshSettings
     .SetMeshType "Tet"
     .Set "Version", 1%
     .Set "SrfMeshGradation", "1.5"
     .Set "UseSameSrfAndVolMeshGradation", "1"
     .Set "VolMeshGradation", "1.5"
     .Set "CurvatureOrderPolicy", "fixedorder"
     .Set "CurvatureOrder", "2"
End With
'More accurate HEX Mesh Settings although TET is default
With Mesh
     .LinesPerWavelength "15"
     .MinimumStepNumber "15"
     .PointAccEnhancement "50"
End With
With MeshSettings
     .SetMeshType "Hex"
     .Set "StepsPerWaveNear", "15"
     .Set "StepsPerBoxNear", "20"
     .Set "RatioLimitGeometry", "50"
     .Set "EquilibrateOn", "1"
     .Set "Equilibrate", "1.5"
End With
PICSolver.Global "LongitudinalEmittance", "True"
Solver.AdaptivePortMeshing "False"
'----------------------------------------------------------------------------
With MeshSettings
     .SetMeshType "Tet"
     .Set "Version", 1%
End With
With Mesh
     .MeshType "Tetrahedral"
End With
'set the solver type
ChangeSolverType("HF Eigenmode")
'----------------------------------------------------------------------------

'@ new component: component1

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Component.New "component1"

'@ define cylinder: component1:solid1

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
With Cylinder 
     .Reset 
     .Name "solid1" 
     .Component "component1" 
     .Material "Vacuum" 
     .OuterRadius "R" 
     .InnerRadius "0" 
     .Axis "z" 
     .Zrange "0", "L/2" 
     .Xcenter "0" 
     .Ycenter "0" 
     .Segments "0" 
     .Create 
End With

'@ pick face

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Pick.PickFaceFromId "component1:solid1", "3"

'@ align wcs with face

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
WCS.AlignWCSWithSelected "Face"

'@ define cylinder: component1:solid2

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
With Cylinder 
     .Reset 
     .Name "solid2" 
     .Component "component1" 
     .Material "Vacuum" 
     .OuterRadius "Rtube" 
     .InnerRadius "0" 
     .Axis "z" 
     .Zrange "0", "Ltube" 
     .Xcenter "0" 
     .Ycenter "0" 
     .Segments "0" 
     .Create 
End With

'@ boolean add shapes: component1:solid1, component1:solid2

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Solid.Add "component1:solid1", "component1:solid2"

'@ activate global coordinates

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
WCS.ActivateWCS "global"

'@ transform: mirror component1

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
With Transform 
     .Reset 
     .Name "component1" 
     .Origin "Free" 
     .Center "0", "0", "0" 
     .PlaneNormal "0", "0", "1" 
     .MultipleObjects "True" 
     .GroupObjects "False" 
     .Repetitions "1" 
     .MultipleSelection "False" 
     .Destination "" 
     .Material "" 
     .Transform "Shape", "Mirror" 
End With

'@ switch working plane

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Plot.DrawWorkplane "false"

'@ boolean add shapes: component1:solid1, component1:solid1_1

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Solid.Add "component1:solid1", "component1:solid1_1"

'@ define frequency range

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Solver.FrequencyRange "fmin", "fmax"

'@ define boundaries

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
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
     .ApplyInAllDirections "True"
End With

'@ define eigenmode solver parameters

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Mesh.SetFlavor "High Frequency" 
Mesh.SetCreator "High Frequency" 
EigenmodeSolver.Reset 
With Solver
     .CalculationType "Eigenmode" 
     .AKSReset 
     .AKSPenaltyFactor "1" 
     .AKSEstimation "0" 
     .AKSAutomaticEstimation "True" 
     .AKSEstimationCycles "5" 
     .AKSIterations "2" 
     .AKSAccuracy "1e-12" 
End With
With EigenmodeSolver 
     .SetMethodType "AKS", "Hex" 
     .SetMethodType "Default", "Tet" 
     .SetMeshType "Tetrahedral Mesh" 
     .SetMeshAdaptationHex "False" 
     .SetMeshAdaptationTet "False" 
     .SetNumberOfModes "5" 
     .SetStoreResultsInCache "False" 
     .SetCalculateExternalQFactor "False" 
     .SetConsiderStaticModes "True" 
     .SetCalculateThermalLosses "True" 
     .SetModesInFrequencyRange "False" 
     .SetFrequencyTarget "True", "fmin*1.2" 
     .SetAccuracy "1e-6" 
     .SetQExternalAccuracy "1e-4" 
     .SetMaterialEvaluationFrequency "True", "" 
     .SetTDCompatibleMaterials "False" 
     .SetOrderTet "2" 
     .SetUseSensitivityAnalysis "False" 
     .SetConsiderLossesInPostprocessingOnly "True" 
     .SetMinimumQ "1.0" 
     .SetUseParallelization "True"
     .SetMaxNumberOfThreads "128"
     .MaximumNumberOfCPUDevices "2"
     .SetRemoteCalculation "False"
End With
UseDistributedComputingForParameters "False"
MaxNumberOfDistributedComputingParameters "2"
UseDistributedComputingMemorySetting "False"
MinDistributedComputingMemoryLimit "0"
UseDistributedComputingSharedDirectory "False"

'@ define eigenmode solver parameters

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Mesh.SetFlavor "High Frequency" 
Mesh.SetCreator "High Frequency" 
EigenmodeSolver.Reset 
With Solver
     .CalculationType "Eigenmode" 
     .AKSReset 
     .AKSPenaltyFactor "1" 
     .AKSEstimation "0" 
     .AKSAutomaticEstimation "True" 
     .AKSEstimationCycles "5" 
     .AKSIterations "2" 
     .AKSAccuracy "1e-12" 
End With
With EigenmodeSolver 
     .SetMethodType "AKS", "Hex" 
     .SetMethodType "Default", "Tet" 
     .SetMeshType "Tetrahedral Mesh" 
     .SetMeshAdaptationHex "False" 
     .SetMeshAdaptationTet "False" 
     .SetNumberOfModes "2" 
     .SetStoreResultsInCache "False" 
     .SetCalculateExternalQFactor "False" 
     .SetConsiderStaticModes "True" 
     .SetCalculateThermalLosses "True" 
     .SetModesInFrequencyRange "False" 
     .SetFrequencyTarget "True", "fmin*1.2" 
     .SetAccuracy "1e-6" 
     .SetQExternalAccuracy "1e-4" 
     .SetMaterialEvaluationFrequency "True", "" 
     .SetTDCompatibleMaterials "False" 
     .SetOrderTet "2" 
     .SetUseSensitivityAnalysis "False" 
     .SetConsiderLossesInPostprocessingOnly "True" 
     .SetMinimumQ "1.0" 
     .SetUseParallelization "True"
     .SetMaxNumberOfThreads "128"
     .MaximumNumberOfCPUDevices "2"
     .SetRemoteCalculation "False"
End With
UseDistributedComputingForParameters "False"
MaxNumberOfDistributedComputingParameters "2"
UseDistributedComputingMemorySetting "False"
MinDistributedComputingMemoryLimit "0"
UseDistributedComputingSharedDirectory "False"

'@ switch working plane

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Plot.DrawWorkplane "false"

'@ set mesh properties (Tetrahedral)

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
With Mesh 
     .MeshType "Tetrahedral" 
     .SetCreator "High Frequency"
End With 
With MeshSettings 
     .SetMeshType "Tet" 
     .Set "Version", 1%
     'MAX CELL - WAVELENGTH REFINEMENT 
     .Set "StepsPerWaveNear", "10" 
     .Set "StepsPerWaveFar", "4" 
     .Set "PhaseErrorNear", "0.02" 
     .Set "PhaseErrorFar", "0.02" 
     .Set "CellsPerWavelengthPolicy", "cellsperwavelength" 
     'MAX CELL - GEOMETRY REFINEMENT 
     .Set "StepsPerBoxNear", "10" 
     .Set "StepsPerBoxFar", "1" 
     .Set "ModelBoxDescrNear", "maxedge" 
     .Set "ModelBoxDescrFar", "maxedge" 
     'MIN CELL 
     .Set "UseRatioLimit", "0" 
     .Set "RatioLimit", "100" 
     .Set "MinStep", "0" 
     'MESHING METHOD 
     .SetMeshType "Unstr" 
     .Set "Method", "0" 
End With 
With MeshSettings 
     .SetMeshType "Tet" 
     .Set "CurvatureOrder", "2" 
     .Set "CurvatureOrderPolicy", "fixedorder" 
     .Set "CurvRefinementControl", "NormalTolerance" 
     .Set "NormalTolerance", "22.5" 
     .Set "SrfMeshGradation", "1.5" 
     .Set "SrfMeshOptimization", "1" 
End With 
With MeshSettings 
     .SetMeshType "Unstr" 
     .Set "UseMaterials",  "1" 
     .Set "MoveMesh", "0" 
End With 
With MeshSettings 
     .SetMeshType "All" 
     .Set "AutomaticEdgeRefinement",  "0" 
End With 
With MeshSettings 
     .SetMeshType "Tet" 
     .Set "UseAnisoCurveRefinement", "1" 
     .Set "UseSameSrfAndVolMeshGradation", "1" 
     .Set "VolMeshGradation", "1.5" 
     .Set "VolMeshOptimization", "1" 
End With 
With MeshSettings 
     .SetMeshType "Unstr" 
     .Set "SmallFeatureSize", "0" 
     .Set "CoincidenceTolerance", "1e-06" 
     .Set "SelfIntersectionCheck", "1" 
     .Set "OptimizeForPlanarStructures", "0" 
End With 
With Mesh 
     .SetParallelMesherMode "Tet", "maximum" 
     .SetMaxParallelMesherThreads "Tet", "1" 
End With

'@ define eigenmode solver parameters

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Mesh.SetFlavor "High Frequency" 
Mesh.SetCreator "High Frequency" 
EigenmodeSolver.Reset 
With Solver
     .CalculationType "Eigenmode" 
     .AKSReset 
     .AKSPenaltyFactor "1" 
     .AKSEstimation "0" 
     .AKSAutomaticEstimation "True" 
     .AKSEstimationCycles "5" 
     .AKSIterations "2" 
     .AKSAccuracy "1e-12" 
End With
With EigenmodeSolver 
     .SetMethodType "AKS", "Hex" 
     .SetMethodType "Default", "Tet" 
     .SetMeshType "Tetrahedral Mesh" 
     .SetMeshAdaptationHex "False" 
     .SetMeshAdaptationTet "False" 
     .SetNumberOfModes "6" 
     .SetStoreResultsInCache "False" 
     .SetCalculateExternalQFactor "True" 
     .SetConsiderStaticModes "True" 
     .SetCalculateThermalLosses "True" 
     .SetModesInFrequencyRange "False" 
     .SetFrequencyTarget "True", "fmin*1.2" 
     .SetAccuracy "1e-6" 
     .SetQExternalAccuracy "1e-4" 
     .SetMaterialEvaluationFrequency "True", "" 
     .SetTDCompatibleMaterials "False" 
     .SetOrderTet "2" 
     .SetUseSensitivityAnalysis "False" 
     .SetConsiderLossesInPostprocessingOnly "True" 
     .SetMinimumQ "1.0" 
     .SetUseParallelization "True"
     .SetMaxNumberOfThreads "128"
     .MaximumNumberOfCPUDevices "2"
     .SetRemoteCalculation "False"
End With
UseDistributedComputingForParameters "False"
MaxNumberOfDistributedComputingParameters "2"
UseDistributedComputingMemorySetting "False"
MinDistributedComputingMemoryLimit "0"
UseDistributedComputingSharedDirectory "False"

'@ define boundaries

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
With Boundary
     .Xmin "electric"
     .Xmax "electric"
     .Ymin "electric"
     .Ymax "electric"
     .Zmin "electric"
     .Zmax "electric"
     .Xsymmetry "magnetic"
     .Ysymmetry "none"
     .Zsymmetry "none"
     .ApplyInAllDirections "False"
End With

''@ pick face
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Pick.PickFaceFromId "component1:solid1", "12"
'
''@ align wcs with face
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'WCS.AlignWCSWithSelected "Face"
'
''@ define cylinder: component1:solid2
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Cylinder 
'     .Reset 
'     .Name "solid2" 
'     .Component "component1" 
'     .Material "Vacuum" 
'     .OuterRadius "Rchoke" 
'     .InnerRadius "Rchoke-Dchoke" 
'     .Axis "z" 
'     .Zrange "0", "Lchoke" 
'     .Xcenter "0" 
'     .Ycenter "0" 
'     .Segments "0" 
'     .Create 
'End With
'
''@ switch working plane
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Plot.DrawWorkplane "true"
'
''@ define curve polygon: curve1:polygon1
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Polygon 
'     .Reset 
'     .Name "polygon1" 
'     .Curve "curve1" 
'     .Point "Rchoke*cos(a/2/180*PI)", "Rchoke*sin(a/2/180*PI)" 
'     .LineTo "0", "0" 
'     .LineTo "Rchoke*cos(a/2/180*PI)", "-Rchoke*sin(a/2/180*PI)" 
'     .Create 
'End With
'
''@ define curve circle: curve1:circle1
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Circle
'     .Reset 
'     .Name "circle1" 
'     .Curve "curve1" 
'     .Radius "Rchoke" 
'     .Xcenter "0" 
'     .Ycenter "0" 
'     .Segments "0" 
'     .Create
'End With
'
''@ trim curves: curve1:circle1 with: curve1:polygon1
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With TrimCurves 
'  .Reset 
'  .Curve "curve1" 
'  .CurveItem1 "circle1" 
'  .CurveItem2 "polygon1" 
'  .DeleteEdges1 "1" 
'  .DeleteEdges2 "" 
'  .Trim 
'End With
'
''@ define extrudeprofile: component1:solid3
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With ExtrudeCurve
'     .Reset 
'     .Name "solid3" 
'     .Component "component1" 
'     .Material "Vacuum" 
'     .Thickness "0.0" 
'     .Twistangle "0.0" 
'     .Taperangle "0.0" 
'     .DeleteProfile "True" 
'     .Curve "curve1:polygon1" 
'     .Create
'End With
'
''@ pick face
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Pick.PickFaceFromId "component1:solid3", "1"
'
''@ define extrude: component1:solid4
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Extrude 
'     .Reset 
'     .Name "solid4" 
'     .Component "component1" 
'     .Material "Vacuum" 
'     .Mode "Picks" 
'     .Height "Lchoke" 
'     .Twist "0.0" 
'     .Taper "0.0" 
'     .UsePicksForHeight "False" 
'     .DeleteBaseFaceSolid "False" 
'     .KeepMaterials "False" 
'     .ClearPickedFace "True" 
'     .Create 
'End With
'
''@ boolean add shapes: component1:solid3, component1:solid4
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Solid.Add "component1:solid3", "component1:solid4"
'
''@ boolean subtract shapes: component1:solid2, component1:solid3
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Solid.Subtract "component1:solid2", "component1:solid3"
'
''@ switch working plane
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Plot.DrawWorkplane "false"
'
''@ activate global coordinates
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'WCS.ActivateWCS "global"
'
''@ transform: rotate component1:solid2
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Transform 
'     .Reset 
'     .Name "component1:solid2" 
'     .Origin "Free" 
'     .Center "0", "0", "0" 
'     .Angle "0", "0", "180" 
'     .MultipleObjects "True" 
'     .GroupObjects "False" 
'     .Repetitions "1" 
'     .MultipleSelection "False" 
'     .Destination "" 
'     .Material "" 
'     .Transform "Shape", "Rotate" 
'End With
'
''@ activate local coordinates
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'WCS.ActivateWCS "local"
'
''@ switch working plane
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Plot.DrawWorkplane "true"
'
''@ rotate wcs
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'WCS.RotateWCS "v", "90.0"
'
''@ activate global coordinates
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'WCS.ActivateWCS "global"
'
''@ activate local coordinates
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'WCS.ActivateWCS "local"
'
''@ activate global coordinates
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'WCS.ActivateWCS "global"
'
''@ boolean add shapes: component1:solid2, component1:solid2_1
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Solid.Add "component1:solid2", "component1:solid2_1"
'
''@ rename block: component1:solid2 to: component1:Cband
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Solid.Rename "component1:solid2", "Cband"
'
''@ rename block: component1:solid1 to: component1:cavity
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Solid.Rename "component1:solid1", "cavity"
'
''@ define curve polygon: curve1:polygon1
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Polygon 
'     .Reset 
'     .Name "polygon1" 
'     .Curve "curve1" 
'     .Point "R-20", "0" 
'     .LineTo "Lpick+R", "0" 
'     .LineTo "Lpick+R", "-Rpick" 
'     .LineTo "0", "-Rpick" 
'     .Create 
'End With
'
''@ define curve circle: curve1:circle1
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Circle
'     .Reset 
'     .Name "circle1" 
'     .Curve "curve1" 
'     .Radius "R-10" 
'     .Xcenter "0" 
'     .Ycenter "0" 
'     .Segments "0" 
'     .Create
'End With
'
''@ trim curves: curve1:circle1 with: curve1:polygon1
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With TrimCurves 
'  .Reset 
'  .Curve "curve1" 
'  .CurveItem1 "circle1" 
'  .CurveItem2 "polygon1" 
'  .DeleteEdges1 "1" 
'  .DeleteEdges2 "4,1" 
'  .Trim 
'End With
'
''@ define extrudeprofile: component1:solid1
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With ExtrudeCurve
'     .Reset 
'     .Name "solid1" 
'     .Component "component1" 
'     .Material "Vacuum" 
'     .Thickness "0.0" 
'     .Twistangle "0.0" 
'     .Taperangle "0.0" 
'     .DeleteProfile "True" 
'     .Curve "curve1:polygon1" 
'     .Create
'End With
'
''@ pick face
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Pick.PickFaceFromId "component1:solid1", "1"
'
''@ set edge
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Pick.AddEdge "258", "0", "0", "302", "0", "0"
'
''@ define rotate: component1:solid2
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Rotate 
'     .Reset 
'     .Name "solid2" 
'     .Component "component1" 
'     .NumberOfPickedFaces "1" 
'     .Material "Vacuum" 
'     .Mode "Picks" 
'     .Angle "360" 
'     .Height "0.0" 
'     .RadiusRatio "1.0" 
'     .TaperAngle "0.0" 
'     .NSteps "0" 
'     .SplitClosedEdges "True" 
'     .SegmentedProfile "False" 
'     .DeleteBaseFaceSolid "False" 
'     .ClearPickedFace "True" 
'     .SimplifySolid "True" 
'     .UseAdvancedSegmentedRotation "True" 
'     .CutEndOff "False" 
'     .Create 
'End With
'
''@ boolean add shapes: component1:solid1, component1:solid2
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Solid.Add "component1:solid1", "component1:solid2"
'
''@ rename block: component1:solid1 to: component1:pick
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Solid.Rename "component1:solid1", "pick"
'
''@ switch working plane
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Plot.DrawWorkplane "false"
'
''@ transform: rotate component1:Cband
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Transform 
'     .Reset 
'     .Name "component1:Cband" 
'     .Origin "Free" 
'     .Center "0", "0", "0" 
'     .Angle "0", "0", "thetaChoke" 
'     .MultipleObjects "False" 
'     .GroupObjects "False" 
'     .Repetitions "1" 
'     .MultipleSelection "False" 
'     .Transform "Shape", "Rotate" 
'End With
'
''@ switch working plane
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Plot.DrawWorkplane "false"
'
''@ define boundaries
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Boundary
'     .Xmin "electric"
'     .Xmax "electric"
'     .Ymin "electric"
'     .Ymax "electric"
'     .Zmin "electric"
'     .Zmax "electric"
'     .Xsymmetry "none"
'     .Ysymmetry "none"
'     .Zsymmetry "none"
'     .ApplyInAllDirections "False"
'End With
'
''@ pick face
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Pick.PickFaceFromId "component1:Cband", "9"
'
''@ pick face
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Pick.PickFaceFromId "component1:Cband", "22"
'
''@ define port: 1
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'With Port 
'     .Reset 
'     .PortNumber "1" 
'     .Label "" 
'     .Folder "" 
'     .NumberOfModes "4" 
'     .AdjustPolarization "False" 
'     .PolarizationAngle "0.0" 
'     .ReferencePlaneDistance "0" 
'     .TextSize "50" 
'     .TextMaxLimit "0" 
'     .Coordinates "Picks" 
'     .Orientation "positive" 
'     .PortOnBound "True" 
'     .ClipPickedPortToBound "False" 
'     .Xrange "-130", "130" 
'     .Yrange "-130", "130" 
'     .Zrange "630", "630" 
'     .XrangeAdd "0.0", "0.0" 
'     .YrangeAdd "0.0", "0.0" 
'     .ZrangeAdd "0.0", "0.0" 
'     .SingleEnded "False" 
'     .WaveguideMonitor "False" 
'     .Create 
'End With
'
''@ define eigenmode solver parameters
'
''[VERSION]2020.0|29.0.1|20190925[/VERSION]
'Mesh.SetFlavor "High Frequency" 
'Mesh.SetCreator "High Frequency" 
'EigenmodeSolver.Reset 
'With Solver
'     .CalculationType "Eigenmode" 
'     .AKSReset 
'     .AKSPenaltyFactor "1" 
'     .AKSEstimation "0" 
'     .AKSAutomaticEstimation "True" 
'     .AKSEstimationCycles "5" 
'     .AKSIterations "2" 
'     .AKSAccuracy "1e-12" 
'End With
'With EigenmodeSolver 
'     .SetMethodType "AKS", "Hex" 
'     .SetMethodType "Default", "Tet" 
'     .SetMeshType "Tetrahedral Mesh" 
'     .SetMeshAdaptationHex "False" 
'     .SetMeshAdaptationTet "False" 
'     .SetNumberOfModes "12" 
'     .SetStoreResultsInCache "False" 
'     .SetCalculateExternalQFactor "True" 
'     .SetConsiderStaticModes "True" 
'     .SetCalculateThermalLosses "True" 
'     .SetModesInFrequencyRange "False" 
'     .SetFrequencyTarget "True", "fmin*1.2" 
'     .SetAccuracy "1e-6" 
'     .SetQExternalAccuracy "1e-4" 
'     .SetMaterialEvaluationFrequency "True", "" 
'     .SetTDCompatibleMaterials "False" 
'     .SetOrderTet "2" 
'     .SetUseSensitivityAnalysis "False" 
'     .SetConsiderLossesInPostprocessingOnly "True" 
'     .SetMinimumQ "1.0" 
'     .SetUseParallelization "True"
'     .SetMaxNumberOfThreads "128"
'     .MaximumNumberOfCPUDevices "2"
'     .SetRemoteCalculation "False"
'End With
'UseDistributedComputingForParameters "False"
'MaxNumberOfDistributedComputingParameters "2"
'UseDistributedComputingMemorySetting "False"
'MinDistributedComputingMemoryLimit "0"
'UseDistributedComputingSharedDirectory "False"
'
'@ set mesh properties (Tetrahedral)

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Mesh.SetFlavor "High Frequency" 
Mesh.SetCreator "High Frequency" 
EigenmodeSolver.Reset 
With Solver
     .CalculationType "Eigenmode" 
     .AKSReset 
     .AKSPenaltyFactor "1" 
     .AKSEstimation "0" 
     .AKSAutomaticEstimation "True" 
     .AKSEstimationCycles "5" 
     .AKSIterations "2" 
     .AKSAccuracy "1e-12" 
End With
With EigenmodeSolver 
     .SetMethodType "AKS", "Hex" 
     .SetMethodType "Default", "Tet" 
     .SetMeshType "Tetrahedral Mesh" 
     .SetMeshAdaptationHex "False" 
     .SetMeshAdaptationTet "False" 
     .SetNumberOfModes "1" 
     .SetStoreResultsInCache "False" 
     .SetCalculateExternalQFactor "True" 
     .SetConsiderStaticModes "True" 
     .SetCalculateThermalLosses "True" 
     .SetModesInFrequencyRange "False" 
     .SetFrequencyTarget "True", "fmin*1.2" 
     .SetAccuracy "1e-6" 
     .SetQExternalAccuracy "1e-4" 
     .SetMaterialEvaluationFrequency "True", "" 
     .SetTDCompatibleMaterials "False" 
     .SetOrderTet "2" 
     .SetUseSensitivityAnalysis "False" 
     .SetConsiderLossesInPostprocessingOnly "True" 
     .SetMinimumQ "1.0" 
     .SetUseParallelization "True"
     .SetMaxNumberOfThreads "128"
     .MaximumNumberOfCPUDevices "2"
     .SetRemoteCalculation "False"
End With
UseDistributedComputingForParameters "False"
MaxNumberOfDistributedComputingParameters "2"
UseDistributedComputingMemorySetting "False"
MinDistributedComputingMemoryLimit "0"
UseDistributedComputingSharedDirectory "False"

'@ define eigenmode solver parameters

'[VERSION]2020.0|29.0.1|20190925[/VERSION]
Mesh.SetFlavor "High Frequency" 

Mesh.SetCreator "High Frequency" 

EigenmodeSolver.Reset 
With Solver
     .CalculationType "Eigenmode" 
     .AKSReset 
     .AKSPenaltyFactor "1" 
     .AKSEstimation "0" 
     .AKSAutomaticEstimation "True" 
     .AKSEstimationCycles "5" 
     .AKSIterations "2" 
     .AKSAccuracy "1e-12" 
End With
With EigenmodeSolver 
     .SetMethodType "AKS", "Hex" 
     .SetMethodType "Default", "Tet" 
     .SetMeshType "Tetrahedral Mesh" 
     .SetMeshAdaptationHex "False" 
     .SetMeshAdaptationTet "False" 
     .SetNumberOfModes "nmodes" 
     .SetStoreResultsInCache "False" 
     .SetCalculateExternalQFactor "True" 
     .SetConsiderStaticModes "True" 
     .SetCalculateThermalLosses "True" 
     .SetModesInFrequencyRange "False" 
     .SetFrequencyTarget "True", "fmin*1.2" 
     .SetAccuracy "1e-6" 
     .SetQExternalAccuracy "1e-4" 
     .SetMaterialEvaluationFrequency "True", "" 
     .SetTDCompatibleMaterials "False" 
     .SetOrderTet "2" 
     .SetUseSensitivityAnalysis "False" 
     .SetConsiderLossesInPostprocessingOnly "True" 
     .SetMinimumQ "1.0" 
     .SetUseParallelization "True"
     .SetMaxNumberOfThreads "128"
     .MaximumNumberOfCPUDevices "2"
     .SetRemoteCalculation "False"
End With
UseDistributedComputingForParameters "False"
MaxNumberOfDistributedComputingParameters "2"
UseDistributedComputingMemorySetting "False"
MinDistributedComputingMemoryLimit "0"
UseDistributedComputingSharedDirectory "False"


'@ PRE_STEP_FREQ_RANGE_SET

'[VERSION]2022.4|31.0.1|20220426[/VERSION]
Solver.FrequencyRange "fmin", "fmax"

'@ PRE_STEP_EIGENSOLVER_SET

'[VERSION]2022.4|31.0.1|20220426[/VERSION]
With EigenmodeSolver
.SetFrequencyTarget "True", "fmin"
.SetNumberOfModes "nmodes"
End With


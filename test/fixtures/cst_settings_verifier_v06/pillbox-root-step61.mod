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


param(
    [Parameter(Mandatory = $true)]
    [string] $ProgId,

    [Parameter(Mandatory = $true)]
    [string] $MacroPath
)

$ErrorActionPreference = "Stop"
$studio = $null
$project = $null

try {
    Write-Output "lifecycle:create-application:$ProgId"
    $studio = New-Object -ComObject $ProgId
    Write-Output "lifecycle:create-project"
    $project = $studio.NewMWS()
    Write-Output "lifecycle:run-script:$MacroPath"
    $project.RunScript($MacroPath)
    Write-Output "lifecycle:quit-project"
    $project.Quit()
    [void] [Runtime.InteropServices.Marshal]::FinalReleaseComObject($project)
    $project = $null
    Write-Output "lifecycle:quit-application"
    $studio.Quit()
    Write-Output "lifecycle:standard-exit-complete"
}
finally {
    Write-Output "lifecycle:release-com-objects"
    if ($null -ne $project) {
        [void] [Runtime.InteropServices.Marshal]::FinalReleaseComObject($project)
    }
    if ($null -ne $studio) {
        [void] [Runtime.InteropServices.Marshal]::FinalReleaseComObject($studio)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

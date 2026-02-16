 # 1_capture-collected-runs.ps1  

<#
.SYNOPSIS
Captures and validates all run folders created between start and end times.
Now uses shared functions from 1_common-paths.ps1.
#>

# ====================================================================
# Configuration – loaded from 1_common-paths.ps1
# ====================================================================
$commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
if (-not (Test-Path $commonPathsScript)) { throw "Common paths script not found" }
. $commonPathsScript

$appConfig = Get-ApplicationConfig

# ====================================================================
# SCRIPT‑SCOPED CONFIG
# ====================================================================
$Script:Config = @{
    StartTime    = $appConfig.EveryStartTime
    EndTime      = $appConfig.EveryEndTime
    RunsBasePath = $null
    LogFile      = $null
}


# ====================================================================
# PATH INITIALISATION
# ====================================================================
function Initialize-Paths {
    $dateStr = Get-Date -Format $appConfig.CaptureDateFormat
    $projectRoot = if ($PSScriptRoot) { Join-Path $PSScriptRoot ".." } else { $PWD.Path }
    $Script:Config.RunsBasePath = Join-Path $projectRoot $appConfig.CaptureRunsDirectory $dateStr
    $logDir = Join-Path $projectRoot $appConfig.CaptureLogsDirectory
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $logFileName = $appConfig.CaptureLogFilePattern -f (Get-Date -Format $appConfig.CaptureFileTimestampFormat)
    $Script:Config.LogFile = Join-Path $logDir $logFileName
    return $true
}



# ====================================================================
# LOCAL LOGGING WRAPPER
# ====================================================================
function Write-CaptureLog {
    param([string]$Message, [string]$Level = "INFO")
    Write-CommonLog -Message $Message -Level $Level -LogFile $Script:Config.LogFile
}


# ====================================================================
# TIME CONVERSION
# ====================================================================
function Convert-ToDateTime {
    param([string]$TimeString)
    try {
        $today = Get-Date -Format "yyyy-MM-dd"
        return [DateTime]::ParseExact("$today $TimeString", "yyyy-MM-dd HH:mm", $null)
    } catch {
        Write-CaptureLog "Invalid time format: $TimeString" -Level "ERROR"
        return $null
    }
}

function Is-WithinTimeWindow {
    param(
        [DateTime]$CheckTime,
        [DateTime]$WindowStart,
        [DateTime]$WindowEnd
    )
    
    return ($CheckTime -ge $WindowStart) -and ($CheckTime -le $WindowEnd)
}

# ====================================================================
# UPDATED: Enhanced Validate-Output Function
# ====================================================================
function Validate-RunFolder {
    param(
        [string]$FolderPath,
        [switch]$Detailed = $false
    )
    
    $result = @{
        Success = $false
        FolderPath = $FolderPath
        FolderName = Split-Path $FolderPath -Leaf
        CreationTime = $null
        MissingItems = @()
        Errors = @()
        Warnings = @()
        Details = @{
            FileSizes = @{}
            FileCount = 0
            HasMetadata = $false
            Metadata = $null
        }
    }
    
    try {
        # Get folder info
        $folder = Get-Item -Path $FolderPath -ErrorAction Stop
        $result.CreationTime = $folder.CreationTime
        
        Write-CaptureLog "Validating folder: $($result.FolderName)" -Level "INFO"
        
        # Check subfolders
        foreach ($subfolder in $Script:Config.ExpectedSubfolders) {
            $subfolderPath = Join-Path $FolderPath $subfolder
            if (-not (Test-Path $subfolderPath)) {
                $result.MissingItems += $subfolder
                $result.Warnings += "Missing subfolder: $subfolder"
            } else {
                # Count files in subfolder if detailed validation
                if ($Detailed) {
                    $files = Get-ChildItem -Path $subfolderPath -File -Recurse -ErrorAction SilentlyContinue
                    $result.Details.FileCount += $files.Count
                }
            }
        }
        
        # Check expected files
        foreach ($file in $Script:Config.ExpectedFiles) {
            $filePath = Join-Path $FolderPath $file
            if (-not (Test-Path $filePath)) {
                $result.MissingItems += $file
                $result.Warnings += "Missing file: $file"
            } else {
                # Get file info
                $fileInfo = Get-Item -Path $filePath -ErrorAction SilentlyContinue
                if ($fileInfo) {
                    $result.Details.FileSizes[$file] = $fileInfo.Length
                    
                    # Parse metadata.json if it exists
                    if ($file -eq "metadata.json") {
                        try {
                            $metadata = Get-Content $filePath -Raw | ConvertFrom-Json -ErrorAction Stop
                            $result.Details.Metadata = $metadata
                            $result.Details.HasMetadata = $true
                        } catch {
                            $result.Errors += "Invalid JSON in metadata.json: $_"
                        }
                    }
                }
            }
        }
        
        # Additional checks for data files
        $dataFiles = Get-ChildItem -Path $FolderPath -File -Filter "*.json" -ErrorAction SilentlyContinue | 
            Where-Object { $_.Name -ne "metadata.json" }
        
        if ($dataFiles.Count -eq 0) {
            $result.Warnings += "No data JSON files found"
        } else {
            $result.Details.FileCount += $dataFiles.Count
        }
        
        # Determine success
        $result.Success = ($result.MissingItems.Count -eq 0) -and ($result.Errors.Count -eq 0)
        
        if ($result.Success) {
            Write-CaptureLog "✓ Folder validation passed: $($result.FolderName)" -Level "SUCCESS"
        } else {
            Write-CaptureLog "✗ Folder validation failed: $($result.FolderName)" -Level "WARN"
            if ($result.MissingItems.Count -gt 0) {
                Write-CaptureLog "  Missing: $($result.MissingItems -join ', ')" -Level "WARN"
            }
            if ($result.Errors.Count -gt 0) {
                Write-CaptureLog "  Errors: $($result.Errors -join ', ')" -Level "ERROR"
            }
        }
        
    } catch {
        $result.Errors += "Error validating folder: $_"
        $result.Success = $false
        Write-CaptureLog "Error validating folder: $_" -Level "ERROR"
    }
    
    return $result
}

# ====================================================================
# MAIN COLLECTION – now uses shared functions
# ====================================================================
function Capture-CollectedRuns {
    param([DateTime]$WindowStart, [DateTime]$WindowEnd)
    Write-CaptureLog "Starting run collection..." -Level "INFO"
    if (-not (Test-Path $Script:Config.RunsBasePath)) {
        Write-CaptureLog "Runs base path does not exist: $($Script:Config.RunsBasePath)" -Level "WARN"
        return @()
    }
    $collected = Collect-RunsFromTimeWindow -BasePath $Script:Config.RunsBasePath `
                                            -WindowStart $WindowStart `
                                            -WindowEnd $WindowEnd `
                                            -ValidateEach
    foreach ($run in $collected) {
        if ($run.Status -eq "VALID") {
            Write-CaptureLog "✓ Collected: $($run.Name)" -Level "SUCCESS"
        } else {
            Write-CaptureLog "✗ Issues found: $($run.Name)" -Level "WARN"
        }
    }
    return $collected
}


# ====================================================================
# Summary Reporting
# ====================================================================
function Show-CollectionSummary {
    param([array]$CollectedRuns)
    $valid   = ($CollectedRuns | Where-Object { $_.Status -eq "VALID" }).Count
    $invalid = ($CollectedRuns | Where-Object { $_.Status -eq "INVALID" }).Count
    Write-CaptureLog "`n=== COLLECTION SUMMARY ===" -Level "INFO"
    Write-CaptureLog "Total runs collected: $($CollectedRuns.Count)" -Level "INFO"
    Write-CaptureLog "Valid runs: $valid" -Level "SUCCESS"
    Write-CaptureLog "Invalid runs: $invalid" -Level $(if ($invalid -gt 0) { "WARN" } else { "INFO" })
    
    # Show invalid runs details
    if ($invalidRuns.Count -gt 0) {
        Write-CaptureLog "`nInvalid runs details:" -Level "WARN"
        foreach ($run in $invalidRuns) {
            $folderName = $run.Name
            $missing = $run.Validation.MissingItems -join ', '
            Write-CaptureLog "  - : Missing $missing" -Level "WARN"
        }
    }
    
    # Show folder sizes
    $totalSize = 0
    foreach ($run in $CollectedRuns) {
        $folder = Get-Item -Path $run.Folder -ErrorAction SilentlyContinue
        if ($folder) {
            $size = (Get-ChildItem -Path $run.Folder -Recurse -File -ErrorAction SilentlyContinue | 
                    Measure-Object -Property Length -Sum).Sum
            $totalSize += $size
        }
    }
    
    $sizeMB = [math]::Round($totalSize / 1MB, 2)
    Write-CaptureLog "Total data collected: $sizeMB MB" -Level "INFO"
    
    return @{ TotalRuns = $CollectedRuns.Count; ValidRuns = $valid; InvalidRuns = $invalid }
}

# ====================================================================
# Export Function for Monitor Integration
# ====================================================================
function Export-CollectedRuns {
    param(
        [array]$CollectedRuns,
        [string]$ExportPath
    )
    
    try {
        $exportData = @{
            CollectionTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            TimeWindow = @{
                Start = $Script:Config.StartTime
                End = $Script:Config.EndTime
            }
            Runs = $CollectedRuns
            Summary = Show-CollectionSummary -CollectedRuns $CollectedRuns
        }
        
        $exportData | ConvertTo-Json -Depth 5 | Out-File -FilePath $ExportPath -Force
        Write-CaptureLog "Exported collection data to: $ExportPath" -Level "SUCCESS"
        return $true
    } catch {
        Write-CaptureLog "Failed to export collection data: $_" -Level "ERROR"
        return $false
    }
}

# ====================================================================
# Main Execution
# ====================================================================
function Start-RunCollection {
    param(
        [string]$StartTime = $null,
        [string]$EndTime = $null,
        [string]$ExportTo = $null
    )
    Write-CaptureLog "=== Run Collection Script Started ===" -Level "INFO"
    if (-not (Initialize-Paths)) { return }
    $start = if ($StartTime) { Convert-ToDateTime $StartTime } else { Convert-ToDateTime $Script:Config.StartTime }
    $end   = if ($EndTime)   { Convert-ToDateTime $EndTime }   else { Convert-ToDateTime $Script:Config.EndTime }
    if (-not $start -or -not $end) { return }
    $collected = Capture-CollectedRuns -WindowStart $start -WindowEnd $end
    $summary = Show-CollectionSummary -CollectedRuns $collected
    if ($ExportTo) { Export-CollectedRuns -CollectedRuns $collected -ExportPath $ExportTo }
    Write-CaptureLog "=== Run Collection Completed ===" -Level "INFO"
    return $collected
}


# ====================================================================
# Export functions for use in monitor
# ====================================================================
if ($MyInvocation.InvocationName -ne '.') {
    Start-RunCollection
} else {
    Export-ModuleMember -Function Start-RunCollection, Test-RunFolder, Show-CollectionSummary
}
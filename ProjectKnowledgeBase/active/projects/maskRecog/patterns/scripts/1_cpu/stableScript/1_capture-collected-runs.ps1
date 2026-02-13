# 1_capture-collected-runs.ps1
<#
.SYNOPSIS
Captures and validates all run folders created between start and end times.
Now uses shared functions from 1_common-paths.ps1.
#>

# ====================================================================
# LOAD COMMON MODULE
# ====================================================================
$commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
if (-not (Test-Path $commonPathsScript)) { throw "Common paths script not found" }
. $commonPathsScript

$appConfig = Get-ApplicationConfig

# ====================================================================
# SCRIPT‑SCOPED CONFIG – derived from central config
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
    # Get the correct runs base path for today
    try {
        $dateStr = Get-Date -Format $appConfig.CaptureDateFormat
        $Script:Config.RunsBasePath = Get-RunsDatePath -DateString $dateStr -Silent
        Write-Host "Using runs base path: $($Script:Config.RunsBasePath)" -ForegroundColor Cyan
    } catch {
        Write-Host "ERROR: Could not determine runs base path: $_" -ForegroundColor Red
        return $false
    }
    
    # Log file location – keep separate logs for capture script
    $projectRoot = Find-ProjectRoot -Silent
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
# MAIN COLLECTION – uses shared Collect-RunsFromTimeWindow
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
    
    if ($invalid -gt 0) {
        Write-CaptureLog "`nInvalid runs details:" -Level "WARN"
        foreach ($run in $CollectedRuns | Where-Object { $_.Status -eq "INVALID" }) {
            $folderName = $run.Name
            $missing = $run.Validation.MissingItems -join ', '
            Write-CaptureLog "  - $folderName : Missing $missing" -Level "WARN"
        }
    }
    
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
    Export-ModuleMember -Function Start-RunCollection, Show-CollectionSummary
}
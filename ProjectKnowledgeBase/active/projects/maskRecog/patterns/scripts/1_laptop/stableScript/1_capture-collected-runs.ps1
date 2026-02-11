# 1_capture-collected-runs.ps1

<#
.SYNOPSIS
Captures and validates all run folders created between start and end times.

.DESCRIPTION
Collects run folders created during the monitoring window and validates each one.
This ensures that even if the worker process stops suddenly, all runs are captured.
#>


# ====================================================================
# Configuration and Setup
# ====================================================================

# Centralized path configuration
$Script:PathConfig = @{
    # Base directories
    ProjectRootRelativePath = ".."  # Relative path to project root from script location
    RunsDirectory = "runs"          # Base runs directory name
    LogsDirectory = "logs"          # Base logs directory name
    
    # File and folder patterns
    OutputFolderPattern = "Laptop_Process_MaskDetect_*"
    LogFilePattern = "capture_collected_runs_{0}.log"
    
    # Default date format
    DateFormat = "yyyy-MM-dd"
    DateTimeFormat = "yyyy-MM-dd HH:mm"
    FileTimestampFormat = "yyyyMMdd_HHmmss"
}

$Script:Config = @{
    # Time window for collection
    StartTime = "08:00"
    EndTime = "16:23"
    
    # Paths - will be set by Initialize-Paths
    RunsBasePath = $null
    LogFile = $null
    
    # Validation settings
    ExpectedSubfolders = @("logs", "script_output")
    ExpectedFiles = @("metadata.json")
}

# ====================================================================
# Initialize Paths 
# ====================================================================
function Initialize-Paths {
    param(
        [string]$DateString = (Get-Date -Format $Script:PathConfig.DateFormat)
    )
    
    try {
        # Get project root (adjust as needed)
        $projectRoot = if ($PSScriptRoot) {
            Join-Path $PSScriptRoot $Script:PathConfig.ProjectRootRelativePath
        } else {
            $PWD.Path
        }
        
        # Build paths using centralized configuration
        $Script:Config.RunsBasePath = Join-Path $projectRoot `
            $Script:PathConfig.RunsDirectory `
            $DateString
        
        # Create log directory using centralized configuration
        $logDir = Join-Path $projectRoot $Script:PathConfig.LogsDirectory
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        
        # Set log file path using pattern from configuration
        $logFileName = $Script:PathConfig.LogFilePattern -f `
            (Get-Date -Format $Script:PathConfig.FileTimestampFormat)
        $Script:Config.LogFile = Join-Path $logDir $logFileName
        
        return $true
    } catch {
        Write-Error "Failed to initialize paths: $_"
        return $false
    }
}

# ====================================================================
# Logging Function
# ====================================================================
function Write-CaptureLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    
    # Write to console with colors
    switch ($Level) {
        "ERROR" { Write-Host $logEntry -ForegroundColor Red }
        "WARN" { Write-Host $logEntry -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logEntry -ForegroundColor Green }
        "INFO" { Write-Host $logEntry -ForegroundColor Cyan }
        default { Write-Host $logEntry -ForegroundColor White }
    }
    
    # Write to log file
    try {
        Add-Content -Path $Script:Config.LogFile -Value $logEntry -ErrorAction SilentlyContinue
    } catch {
        Write-Host "Failed to write to log file: $_" -ForegroundColor Yellow
    }
}

# ====================================================================
# Time Window Functions
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
# Main Collection Function
# ====================================================================
function Capture-CollectedRuns {
    param(
        [DateTime]$WindowStart,
        [DateTime]$WindowEnd
    )
    
    Write-CaptureLog "Starting run collection..." -Level "INFO"
    Write-CaptureLog "Time window: $($WindowStart.ToString('HH:mm')) to $($WindowEnd.ToString('HH:mm'))" -Level "INFO"
    
    $collectedRuns = @()
    
    try {
        # Check if runs base path exists
        if (-not (Test-Path $Script:Config.RunsBasePath)) {
            Write-CaptureLog "Runs base path does not exist: $($Script:Config.RunsBasePath)" -Level "WARN"
            return $collectedRuns
        }
        
        # Get all run folders matching the pattern
        $allRunFolders = Get-ChildItem -Path $Script:Config.RunsBasePath -Directory -Filter $Script:Config.OutputFolderPattern -ErrorAction SilentlyContinue
        
        if (-not $allRunFolders) {
            Write-CaptureLog "No run folders found in: $($Script:Config.RunsBasePath)" -Level "WARN"
            return $collectedRuns
        }
        
        Write-CaptureLog "Found $($allRunFolders.Count) total run folders" -Level "INFO"
        
        # Filter folders within time window
        $windowRuns = $allRunFolders | Where-Object {
            Is-WithinTimeWindow -CheckTime $_.CreationTime -WindowStart $WindowStart -WindowEnd $WindowEnd
        }
        
        Write-CaptureLog "$($windowRuns.Count) runs within specified time window" -Level "INFO"
        
        # Validate each folder
        foreach ($runFolder in $windowRuns) {
            Write-CaptureLog "Processing: $($runFolder.Name) (Created: $($runFolder.CreationTime.ToString('HH:mm:ss')))" -Level "INFO"
            
            $validationResult = Validate-RunFolder -FolderPath $runFolder.FullName -Detailed:$true
            
            # Add to collected runs
            $collectedRuns += @{
                Folder = $runFolder.FullName
                Name = $runFolder.Name
                CreationTime = $runFolder.CreationTime
                Validation = $validationResult
                Status = if ($validationResult.Success) { "VALID" } else { "INVALID" }
            }
            
            # Log summary
            if ($validationResult.Success) {
                Write-CaptureLog "✓ Collected: $($runFolder.Name)" -Level "SUCCESS"
            } else {
                Write-CaptureLog "✗ Issues found in: $($runFolder.Name)" -Level "WARN"
            }
        }
        
    } catch {
        Write-CaptureLog "Error during run collection: $_" -Level "ERROR"
    }
    
    return $collectedRuns
}

# ====================================================================
# Summary Reporting
# ====================================================================
function Show-CollectionSummary {
    param(
        [array]$CollectedRuns
    )
    
    Write-CaptureLog "`n=== COLLECTION SUMMARY ===" -Level "INFO"
    Write-CaptureLog "Total runs collected: $($CollectedRuns.Count)" -Level "INFO"
    
    $validRuns = $CollectedRuns | Where-Object { $_.Status -eq "VALID" }
    $invalidRuns = $CollectedRuns | Where-Object { $_.Status -eq "INVALID" }
    
    Write-CaptureLog "Valid runs: $($validRuns.Count)" -Level "SUCCESS"
    Write-CaptureLog "Invalid runs: $($invalidRuns.Count)" -Level $(if ($invalidRuns.Count -gt 0) { "WARN" } else { "INFO" })
    
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
    
    return @{
        TotalRuns = $CollectedRuns.Count
        ValidRuns = $validRuns.Count
        InvalidRuns = $invalidRuns.Count
        TotalSizeMB = $sizeMB
    }
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
    Write-CaptureLog "Script Version: 1.0" -Level "INFO"
    
    # Initialize paths
    if (-not (Initialize-Paths)) {
        Write-CaptureLog "Failed to initialize paths. Exiting." -Level "ERROR"
        return
    }
    
    # Use provided times or config defaults
    $collectionStart = if ($StartTime) { Convert-ToDateTime $StartTime } else { Convert-ToDateTime $Script:Config.StartTime }
    $collectionEnd = if ($EndTime) { Convert-ToDateTime $EndTime } else { Convert-ToDateTime $Script:Config.EndTime }
    
    if (-not $collectionStart -or -not $collectionEnd) {
        Write-CaptureLog "Invalid time window specified. Exiting." -Level "ERROR"
        return
    }
    
    # Capture runs
    $collectedRuns = Capture-CollectedRuns -WindowStart $collectionStart -WindowEnd $collectionEnd
    
    # Show summary
    $summary = Show-CollectionSummary -CollectedRuns $collectedRuns
    
    # Export if requested
    if ($ExportTo) {
        Export-CollectedRuns -CollectedRuns $collectedRuns -ExportPath $ExportTo
    }
    
    Write-CaptureLog "=== Run Collection Completed ===" -Level "INFO"
    
    return $collectedRuns
}

# ====================================================================
# Export functions for use in monitor
# ====================================================================
if ($MyInvocation.InvocationName -ne '.') {
    # If script is run directly
    Start-RunCollection
} else {
    # If script is dot-sourced, export the functions
    Export-ModuleMember -Function Start-RunCollection, Validate-RunFolder, Show-CollectionSummary
}
# 1_mask_portable.ps1
<#
.SYNOPSIS
Worker script for face recognition pipeline with monitor integration
.DESCRIPTION
Handles Python script execution with proper process tracking and logging
.NOTES
Updated to work with enhanced monitor script structure
#>

# ====================================================================
# ENHANCED: Import common paths module with monitor integration
# ====================================================================
$commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
if (Test-Path $commonPathsScript) {
    . $commonPathsScript
    Write-Host "✓ Common paths module loaded" -ForegroundColor Green
} else {
    Write-Host "ERROR: Common paths script not found at: $commonPathsScript" -ForegroundColor Red
    Write-Host "Attempting to find project root manually..." -ForegroundColor Yellow
    
    # Fallback to manual initialization
    function Initialize-ManualPaths {
        $scriptPath = $PSScriptRoot
        $currentPath = $scriptPath
        
        while ($currentPath -and (Split-Path $currentPath -Parent)) {
            $currentDirName = Split-Path $currentPath -Leaf
            if ($currentDirName -eq "maskRecog") {
                $global:ProjectRoot = $currentPath
                $global:ActiveRoot = Split-Path $currentPath -Parent | Split-Path -Parent
                break
            }
            $currentPath = Split-Path $currentPath -Parent
        }
        
        if (-not $global:ProjectRoot) {
            $global:ProjectRoot = Read-Host "Please enter full path to 'maskRecog' project root"
            if (!(Test-Path $global:ProjectRoot)) {
                Write-Host "ERROR: Path does not exist!" -ForegroundColor Red
                exit 1
            }
            $global:ActiveRoot = Split-Path $global:ProjectRoot -Parent | Split-Path -Parent
        }
    }
    
    Initialize-ManualPaths
}

# ====================================================================
# ENHANCED: Initialize paths for worker using common module
# ====================================================================
Write-Host "=== Mask Detection Worker Script ===" -ForegroundColor Cyan
Write-Host "Starting portable path initialization..." -ForegroundColor Cyan

$paths = Initialize-ProjectPortablePaths -IsWorker

# Extract validated paths
$ProjectRoot = $paths.ProjectRoot
$ActiveRoot = $paths.ActiveRoot
$ActiveDatePath = $paths.DateBasedPath
$VENV_ROOT = $paths.VenvRoot
$PYTHON_SCRIPT = $paths.PythonScript
$PYTHON_EXE = $paths.PythonExe
$RUNS_BASE_PATH = $paths.DateBasedPath

# Get current script name for logging
$POWERSHELL_SCRIPT_NAME = Split-Path -Leaf $MyInvocation.MyCommand.Path

# Store worker PID for monitor tracking
$global:WorkerPID = $PID
Write-Log "Worker process started (PID: $global:WorkerPID)" -Level "INFO"

# ====================================================================
# ENHANCED: Configuration for worker
# ====================================================================
$Script:WorkerConfig = @{
    # Python parameters
    PythonParams = @{
        # "--database" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\current_database-Copy"
        # "--input" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\process-run\Run_Classified2026-01-21_15-11-08\script_output\classified_output"
        "--multi-source" = $null # Flag parameter
    }
    
    # File patterns
    OutputFolderPattern = "Magick_Process_MaskDetect_*"
    
    # Logging
    WorkerLogFile = Join-Path $ActiveDatePath "worker_$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').log"
}

# ====================================================================
# ENHANCED: Helper functions
# ====================================================================

function Convert-HashtableToArgs {
    param([hashtable]$Params)
    
    $argsArray = @()
    foreach ($key in $Params.Keys) {
        $argsArray += $key
        if ($Params[$key] -ne $null) {
            $argsArray += $Params[$key]
        }
    }
    return $argsArray
}

function Write-WorkerLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $currentTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$currentTimestamp] [$Level] $Message"
    
    # Write to worker log file
    if ($Script:WorkerConfig.WorkerLogFile) {
        try {
            Add-Content -Path $Script:WorkerConfig.WorkerLogFile -Value $logEntry -ErrorAction SilentlyContinue
        } catch {
            # Fallback to console
            Write-Host "Worker log file write failed: $_" -ForegroundColor Yellow
        }
    }
    
    # Color-coded console output
    switch ($Level) {
        "ERROR" { Write-Host $logEntry -ForegroundColor Red }
        "WARN" { Write-Host $logEntry -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logEntry -ForegroundColor Green }
        "DEBUG" { Write-Host $logEntry -ForegroundColor Gray }
        default { Write-Host $logEntry -ForegroundColor White }
    }
}

function Create-RunFolderStructure {
    param(
        [string]$BasePath,
        [string]$Timestamp
    )
    
    Write-WorkerLog "Creating run folder structure..." -Level "INFO"
    
    $RUN_FOLDER_NAME = "Magick_Process_MaskDetect_$Timestamp"
    $RUN_FOLDER_PATH = Join-Path $BasePath $RUN_FOLDER_NAME
    
    # Create run folder structure
    $RUN_LOGS_PATH = Join-Path $RUN_FOLDER_PATH "logs"
    $RUN_SCRIPT_OUTPUT_PATH = Join-Path $RUN_FOLDER_PATH "script_output"
    $RUN_METADATA_PATH = Join-Path $RUN_FOLDER_PATH "metadata.json"
    
    try {
        # Create all directories
        New-Item -ItemType Directory -Path $RUN_FOLDER_PATH -Force | Out-Null
        New-Item -ItemType Directory -Path $RUN_LOGS_PATH -Force | Out-Null
        New-Item -ItemType Directory -Path $RUN_SCRIPT_OUTPUT_PATH -Force | Out-Null
        
        Write-WorkerLog "Created run folder structure at: $RUN_FOLDER_PATH" -Level "SUCCESS"
        
        return @{
            RunFolderPath = $RUN_FOLDER_PATH
            LogsPath = $RUN_LOGS_PATH
            ScriptOutputPath = $RUN_SCRIPT_OUTPUT_PATH
            MetadataPath = $RUN_METADATA_PATH
            RunFolderName = $RUN_FOLDER_NAME
        }
    } catch {
        Write-WorkerLog "Failed to create run folder structure: $_" -Level "ERROR"
        throw
    }
}

function Create-MetadataFile {
    param(
        [string]$MetadataPath,
        [string]$RunFolderPath,
        [string]$Timestamp,
        [array]$PythonArgs,
        [int]$WorkerPID
    )
    
    $metadata = @{
        run_id = $Timestamp
        start_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        powershell_script = $POWERSHELL_SCRIPT_NAME
        project_root = $ProjectRoot
        active_date_path = $ActiveDatePath
        virtual_env = $VENV_ROOT
        python_script = $PYTHON_SCRIPT
        python_exe = $PYTHON_EXE
        arguments = $PythonArgs
        arguments_count = $PythonArgs.Count
        run_folder = $RunFolderPath
        worker_pid = $WorkerPID
        python_pid = $null  # Will be set after Python process starts
    }
    
    $metadata | ConvertTo-Json | Out-File $MetadataPath
    Write-WorkerLog "Created metadata file: $MetadataPath" -Level "INFO"
    
    return $metadata
}

function Execute-PythonScript {
    param(
        [string]$PythonExe,
        [string]$PythonScript,
        [array]$PythonArgs,
        [string]$WorkingDirectory,
        [string]$OutputFile
    )
    
    Write-WorkerLog "Starting Python script execution..." -Level "INFO"
    Write-WorkerLog "Python executable: $PythonExe" -Level "DEBUG"
    Write-WorkerLog "Python script: $PythonScript" -Level "DEBUG"
    Write-WorkerLog "Working directory: $WorkingDirectory" -Level "DEBUG"
    
    if (-not (Test-Path $PythonExe)) {
        $errorMsg = "ERROR: Python executable not found at $PythonExe"
        Write-WorkerLog $errorMsg -Level "ERROR"
        throw $errorMsg
    }
    
    if (-not (Test-Path $PythonScript)) {
        $errorMsg = "ERROR: Python script not found at $PythonScript"
        Write-WorkerLog $errorMsg -Level "ERROR"
        throw $errorMsg
    }
    
    # Prepare the command
    $commandString = "`"$PythonExe`" `"$PythonScript`" $($PythonArgs -join ' ')"
    Write-WorkerLog "Executing: $commandString" -Level "INFO"
    
    # Capture start time
    $startTime = Get-Date
    Write-WorkerLog "Execution started at: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" -Level "INFO"
    
    try {
        # Save original location
        $originalLocation = Get-Location
        
        # Change to working directory
        Set-Location $WorkingDirectory
        Write-WorkerLog "Changed working directory to: $WorkingDirectory" -Level "DEBUG"
        
        # Start Python process
        $pythonProcess = Start-Process -FilePath $PythonExe `
            -ArgumentList @($PythonScript) + $PythonArgs `
            -NoNewWindow `
            -PassThru `
            -RedirectStandardOutput $OutputFile `
            -RedirectStandardError $OutputFile `
            -WorkingDirectory $WorkingDirectory
        
        # Store Python PID for monitor tracking
        $global:PythonPID = $pythonProcess.Id
        Write-WorkerLog "Python process started (PID: $global:PythonPID)" -Level "SUCCESS"
        
        # Wait for process to complete
        Wait-Process -Id $pythonProcess.Id -ErrorAction Stop
        $exitCode = $pythonProcess.ExitCode
        
        # Return to original location
        Set-Location $originalLocation
        
        Write-WorkerLog "Python process completed with exit code: $exitCode" -Level "INFO"
        
        return @{
            ExitCode = $exitCode
            PythonPID = $pythonProcess.Id
            StartTime = $startTime
            EndTime = Get-Date
        }
        
    } catch {
        $errorMessage = $_.Exception.Message
        Write-WorkerLog "Exception during Python script execution: $errorMessage" -Level "ERROR"
        throw
    }
}

function Create-CompletionSummary {
    param(
        [string]$SummaryPath,
        [hashtable]$RunInfo,
        [string]$RunFolderPath,
        [array]$PythonArgs,
        [int]$ExitCode,
        [string]$DurationFormatted,
        [datetime]$StartTime,
        [datetime]$EndTime
    )
    
    $completionSummary = @"
==================================================
RUN COMPLETION SUMMARY
==================================================
Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run ID: $($RunInfo.RunID)
PowerShell Script: $POWERSHELL_SCRIPT_NAME
Project Root: $ProjectRoot
Active Date Path: $ActiveDatePath
Status: $(if ($ExitCode -eq 0) { "SUCCESS" } else { "FAILED (Exit code: $ExitCode)" })

PORTABLE PATHS USED
==================================================
Project Root: $ProjectRoot
Active Date Path: $ActiveDatePath
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT
Python Executable: $PYTHON_EXE

FOLDER STRUCTURE
==================================================
Run Folder: $RunFolderPath
├── logs\
│   ├── run_$($RunInfo.RunID).log          (Main log file)
│   ├── python_output.txt                  (Full Python script output)
│   └── completion_summary.txt             (This summary)
├── script_output\                         (Python script's working directory)
│   └── [Output folders created by Python]
└── metadata.json                          (Run configuration metadata)

PROCESS INFORMATION
==================================================
Worker PID: $($RunInfo.WorkerPID)
Python PID: $($RunInfo.PythonPID)

EXECUTION DETAILS
==================================================
Start Time: $($StartTime.ToString('yyyy-MM-dd HH:mm:ss'))
End Time: $($EndTime.ToString('yyyy-MM-dd HH:mm:ss'))
Duration: $DurationFormatted
Exit Code: $ExitCode

ARGUMENTS PASSED
==================================================
$($PythonArgs | ForEach-Object { "  $_" } | Out-String)

LOG FILES
==================================================
1. Main Execution Log: $($RunInfo.MainLogFile)
2. Python Output: $($RunInfo.PythonOutputFile)
3. Worker Log: $($Script:WorkerConfig.WorkerLogFile)

NOTE: This run uses portable paths that are relative to the project root.
==================================================
"@

    $completionSummary | Out-File $SummaryPath
    Write-WorkerLog "Created completion summary: $SummaryPath" -Level "INFO"
}

# ====================================================================
# MAIN EXECUTION
# ====================================================================

try {
    Write-WorkerLog "=== Worker Script Started ===" -Level "INFO"
    Write-WorkerLog "Worker PID: $global:WorkerPID" -Level "INFO"
    Write-WorkerLog "Project Root: $ProjectRoot" -Level "INFO"
    Write-WorkerLog "Active Date Path: $ActiveDatePath" -Level "INFO"
    
    # Convert Python parameters to argument array
    $PYTHON_ARGS = Convert-HashtableToArgs -Params $Script:WorkerConfig.PythonParams
    Write-WorkerLog "Python arguments: $($PYTHON_ARGS -join ' ')" -Level "INFO"
    
    # Generate timestamp for this run
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    
    # Create run folder structure
    $folderStructure = Create-RunFolderStructure -BasePath $RUNS_BASE_PATH -Timestamp $timestamp
    
    # Set up log files
    $MAIN_LOG_FILE = Join-Path $folderStructure.LogsPath "run_$timestamp.log"
    $PYTHON_OUTPUT_FILE = Join-Path $folderStructure.LogsPath "python_output.txt"
    $COMPLETION_SUMMARY_FILE = Join-Path $folderStructure.LogsPath "completion_summary.txt"
    
    # Write initial log header
    @"
==================================================
RUN STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run Folder: $($folderStructure.RunFolderPath)
PowerShell Script: $POWERSHELL_SCRIPT_NAME
Project Root: $ProjectRoot
Active Date Path: $ActiveDatePath
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT
Arguments: $($PYTHON_ARGS -join ' ')
Number of arguments: $($PYTHON_ARGS.Count)
==================================================
"@ | Out-File $MAIN_LOG_FILE
    
    # Create metadata file
    $metadata = Create-MetadataFile `
        -MetadataPath $folderStructure.MetadataPath `
        -RunFolderPath $folderStructure.RunFolderPath `
        -Timestamp $timestamp `
        -PythonArgs $PYTHON_ARGS `
        -WorkerPID $global:WorkerPID
    
    # Execute Python script
    $executionResult = Execute-PythonScript `
        -PythonExe $PYTHON_EXE `
        -PythonScript $PYTHON_SCRIPT `
        -PythonArgs $PYTHON_ARGS `
        -WorkingDirectory $folderStructure.ScriptOutputPath `
        -OutputFile $PYTHON_OUTPUT_FILE
    
    # Calculate duration
    $duration = $executionResult.EndTime - $executionResult.StartTime
    $durationFormatted = "{0:D2}:{1:D2}:{2:D2}" -f $duration.Hours, $duration.Minutes, $duration.Seconds
    
    # Update metadata with completion info
    $metadata.end_time = $executionResult.EndTime.ToString("yyyy-MM-dd HH:mm:ss")
    $metadata.duration = $durationFormatted
    $metadata.exit_code = $executionResult.ExitCode
    $metadata.python_pid = $executionResult.PythonPID
    
    $metadata | ConvertTo-Json | Out-File $folderStructure.MetadataPath -Force
    
    # Create completion summary
    Create-CompletionSummary `
        -SummaryPath $COMPLETION_SUMMARY_FILE `
        -RunInfo @{
            RunID = $timestamp
            WorkerPID = $global:WorkerPID
            PythonPID = $executionResult.PythonPID
            MainLogFile = $MAIN_LOG_FILE
            PythonOutputFile = $PYTHON_OUTPUT_FILE
        } `
        -RunFolderPath $folderStructure.RunFolderPath `
        -PythonArgs $PYTHON_ARGS `
        -ExitCode $executionResult.ExitCode `
        -DurationFormatted $durationFormatted `
        -StartTime $executionResult.StartTime `
        -EndTime $executionResult.EndTime
    
    # Log summary to console
    Write-WorkerLog "==================================================" -Level "SUCCESS"
    Write-WorkerLog "RUN COMPLETED" -Level "SUCCESS"
    Write-WorkerLog "Run Folder: $($folderStructure.RunFolderPath)" -Level "INFO"
    Write-WorkerLog "Exit Code: $($executionResult.ExitCode)" -Level "INFO"
    Write-WorkerLog "Duration: $durationFormatted" -Level "INFO"
    Write-WorkerLog "Worker PID: $global:WorkerPID" -Level "INFO"
    Write-WorkerLog "Python PID: $($executionResult.PythonPID)" -Level "INFO"
    Write-WorkerLog "==================================================" -Level "SUCCESS"
    
    # Exit with Python's exit code
    exit $executionResult.ExitCode
    
} catch {
    Write-WorkerLog "FATAL ERROR in worker script: $_" -Level "ERROR"
    Write-WorkerLog "Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
    exit 1
}
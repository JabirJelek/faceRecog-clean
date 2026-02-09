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
    try {
        . $commonPathsScript
        Write-Host "✓ Common paths module loaded" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Failed to load common paths: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "ERROR: Common paths script not found at: $commonPathsScript" -ForegroundColor Red
    exit 1
}

# ====================================================================
# ENHANCED: Initialize paths for worker using common module
# ====================================================================
Write-Host "=== Mask Detection Worker Script ===" -ForegroundColor Cyan
Write-Host "Starting portable path initialization..." -ForegroundColor Cyan

$paths = Initialize-ProjectPortablePaths -IsWorker

# Initialize communication paths
$global:CommunicationPaths = Initialize-CommunicationPaths -Paths $paths -IsWorker

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
Write-Log "Worker process started (PID: $global:WorkerPID)" -Level "INFO"  # Changed from

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

# Add these functions to 1_common-paths.ps1 after the existing communication functions:

function Read-WorkerStatus {
    [CmdletBinding()]
    param([string]$StatusFile)
    
    if (-not (Test-Path $StatusFile)) {
        return @{ Status = "NOT_FOUND"; WorkerPID = 0; PythonPID = 0 }
    }
    
    try {
        $content = Get-Content $StatusFile -Raw
        return $content | ConvertFrom-Json -AsHashtable
    } catch {
        return @{ Status = "ERROR"; Error = $_; WorkerPID = 0; PythonPID = 0 }
    }
}

function Check-Heartbeat {
    [CmdletBinding()]
    param([string]$HeartbeatFile, [int]$TimeoutSeconds = 30)
    
    if (-not (Test-Path $HeartbeatFile)) {
        return $false
    }
    
    try {
        $content = Get-Content $HeartbeatFile -Raw
        $heartbeat = $content | ConvertFrom-Json -AsHashtable
        
        $lastBeat = [DateTime]::ParseExact($heartbeat.Timestamp, "yyyy-MM-dd HH:mm:ss", $null)
        $now = Get-Date
        
        return ($now - $lastBeat).TotalSeconds -le $TimeoutSeconds
    } catch {
        return $false
    }
}

function Acquire-Lock {
    [CmdletBinding()]
    param([string]$LockFile, [int]$TimeoutSeconds = 10)
    
    $startTime = Get-Date
    $lockAcquired = $false
    
    while (((Get-Date) - $startTime).TotalSeconds -lt $TimeoutSeconds) {
        try {
            if (Test-Path $LockFile) {
                # Check if lock is stale (older than 30 seconds)
                $lockTime = (Get-Item $LockFile).LastWriteTime
                if (((Get-Date) - $lockTime).TotalSeconds -gt 30) {
                    Remove-Item $LockFile -Force
                    Start-Sleep -Milliseconds 100
                }
                Start-Sleep -Milliseconds 200
                continue
            }
            
            # Create lock file
            $PID | Out-File $LockFile
            Start-Sleep -Milliseconds 100
            
            # Verify we still own the lock
            if ((Test-Path $LockFile) -and ((Get-Content $LockFile) -eq $PID)) {
                $lockAcquired = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    
    return $lockAcquired
}

function Release-Lock {
    [CmdletBinding()]
    param([string]$LockFile)
    
    if (Test-Path $LockFile) {
        try {
            if ((Get-Content $LockFile) -eq $PID) {
                Remove-Item $LockFile -Force
            }
        } catch {
            # Ignore cleanup errors
        }
    }
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

# function Write-Log1 {
#     param(
#         [string]$Message,
#         [string]$Level = "INFO"
#     )
    
#     $currentTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
#     $logEntry = "[$currentTimestamp] [$Level] $Message"
    
#     # Write to worker log file
#     if ($Script:WorkerConfig.WorkerLogFile) {
#         try {
#             Add-Content -Path $Script:WorkerConfig.WorkerLogFile -Value $logEntry -ErrorAction SilentlyContinue
#         } catch {
#             # Fallback to console
#             Write-Host "Worker log file write failed: $_" -ForegroundColor Yellow
#         }
#     }
    
#     # Color-coded console output
#     switch ($Level) {
#         "ERROR" { Write-Host $logEntry -ForegroundColor Red }
#         "WARN" { Write-Host $logEntry -ForegroundColor Yellow }
#         "SUCCESS" { Write-Host $logEntry -ForegroundColor Green }
#         "DEBUG" { Write-Host $logEntry -ForegroundColor Gray }
#         default { Write-Host $logEntry -ForegroundColor White }
#     }
# }

function Create-RunFolderStructure {
    param(
        [string]$BasePath,
        [string]$Timestamp
    )
    
    Write-Log "Creating run folder structure..." -Level "INFO"
    
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
        
        Write-Log "Created run folder structure at: $RUN_FOLDER_PATH" -Level "SUCCESS"
        
        return @{
            RunFolderPath = $RUN_FOLDER_PATH
            LogsPath = $RUN_LOGS_PATH
            ScriptOutputPath = $RUN_SCRIPT_OUTPUT_PATH
            MetadataPath = $RUN_METADATA_PATH
            RunFolderName = $RUN_FOLDER_NAME
        }
    } catch {
        Write-Log "Failed to create run folder structure: $_" -Level "ERROR"
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
    Write-Log "Created metadata file: $MetadataPath" -Level "INFO"
    
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
    
    Write-Log "Starting Python script execution..." -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile
    
    if (-not (Test-Path $PythonExe)) {
        $errorMsg = "ERROR: Python executable not found at $PythonExe"
        Write-Log $errorMsg -Level "ERROR" -LogFile $Script:WorkerConfig.WorkerLogFile
        throw $errorMsg
    }
    
    if (-not (Test-Path $PythonScript)) {
        $errorMsg = "ERROR: Python script not found at $PythonScript"
        Write-Log $errorMsg -Level "ERROR" -LogFile $Script:WorkerConfig.WorkerLogFile
        throw $errorMsg
    }
    
    # Prepare the command
    $commandString = "`"$PythonExe`" `"$PythonScript`" $($PythonArgs -join ' ')"
    Write-Log "Executing: $commandString" -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile
    
    # Capture start time
    $startTime = Get-Date
    Write-Log "Execution started at: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile

    try {
        # Save original location
        $originalLocation = Get-Location
        
        # Change to working directory
        Set-Location $WorkingDirectory
        Write-Log "Changed working directory to: $WorkingDirectory" -Level "DEBUG" -LogFile $Script:WorkerConfig.WorkerLogFile
        
        # Start Python process
        $pythonProcess = Start-Process -FilePath $PythonExe `
            -ArgumentList @($PythonScript) + $PythonArgs `
            -NoNewWindow `
            -PassThru `
            -RedirectStandardOutput $OutputFile `
            -RedirectStandardError $OutputFile `
            -WorkingDirectory $WorkingDirectory
        
        $global:PythonPID = $pythonProcess.Id
        
        # Update status
        Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `
            -Status "RUNNING" `
            -WorkerPID $global:WorkerPID `
            -PythonPID $global:PythonPID `
            -Message "Python script running"
        
        # Monitor loop with heartbeat and command checking
        while (-not $pythonProcess.HasExited) {
            # Send heartbeat
            Send-HeartbeatToMonitor -Message "Python script running"
            
            # Check for monitor commands
            $command = Check-ForMonitorCommand
            if ($command -eq "STOP") {
                Write-Log "Stopping Python process due to STOP command from monitor" -Level "WARN" -LogFile $Script:WorkerConfig.WorkerLogFile
                
                # Try graceful shutdown first
                if (-not $pythonProcess.HasExited) {
                    $pythonProcess.CloseMainWindow() | Out-Null
                    Start-Sleep -Seconds 2
                    
                    if (-not $pythonProcess.HasExited) {
                        Write-Log "Forcefully terminating Python process..." -Level "WARN" -LogFile $Script:WorkerConfig.WorkerLogFile
                        $pythonProcess.Kill()
                    }
                }
                
                # Update status
                Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `
                    -Status "STOPPED" `
                    -WorkerPID $global:WorkerPID `
                    -PythonPID $global:PythonPID `
                    -Message "Stopped by monitor command"
                
                break
            }
            
            Start-Sleep -Seconds 2
        }
        
        $pythonProcess.WaitForExit()
        $exitCode = $pythonProcess.ExitCode
        
        return @{
            ExitCode = $exitCode
            PythonPID = $pythonProcess.Id
            StartTime = $startTime
            EndTime = Get-Date
        }
        
    } catch {
        # Update status on error
        Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `
            -Status "ERROR" `
            -WorkerPID $global:WorkerPID `
            -PythonPID $global:PythonPID `
            -Message "Python execution error: $_"
        throw
    } finally {
        # Restore original location
        Set-Location $originalLocation
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
    Write-Log "Created completion summary: $SummaryPath" -Level "INFO"
}


function Register-WorkerWithMonitor {
    try {
        # Write PID file for monitor to detect
        $PID | Out-File $global:CommunicationPaths.PIDFile -Force
        
        # Create registration file
        $registration = @{
            Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            WorkerPID = $PID
            ScriptPath = $MyInvocation.MyCommand.Path
            Version = "2.0"
            Status = "STARTING"
        }
        
        $registration | ConvertTo-Json | Out-File $global:CommunicationPaths.RegistrationFile -Force
        
        # Initial status update using common function
        Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `
            -Status "STARTING" `
            -WorkerPID $PID `
            -Message "Worker script initializing"
        
        Write-Host "✓ Worker registered with monitor (PID: $PID)" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "WARNING: Failed to register with monitor: $_" -ForegroundColor Yellow
        return $false
    }
}

function Send-HeartbeatToMonitor {
    param([string]$Message = "")
    
    try {
        $success = Send-Heartbeat -HeartbeatFile $global:CommunicationPaths.HeartbeatFile
        
        if ($Message -ne "") {
            $status = Read-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile
            if ($status.Status -ne "ERROR") {
                $status.Message = $Message
                $status.LastHeartbeat = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                $status | ConvertTo-Json | Out-File $global:CommunicationPaths.StatusFile -Force
            }
        }
        
        return $success
    } catch {
        return $false
    }
}

function Check-ForMonitorCommand {
    if (Test-Path $global:CommunicationPaths.CommandFile) {
        try {
            $lockFile = $global:CommunicationPaths.LockFile
            if (Acquire-Lock -LockFile $lockFile) {
                $commandData = Get-Content $global:CommunicationPaths.CommandFile -Raw | ConvertFrom-Json
                Remove-Item $global:CommunicationPaths.CommandFile -Force
                
                Release-Lock -LockFile $lockFile
                
                Write-Log "Received command from monitor: $($commandData.Command)" -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile
                
                switch ($commandData.Command) {
                    "STOP" {
                        Write-Host "Received STOP command from monitor: $($commandData.Parameters.Reason)" -ForegroundColor Yellow
                        
                        # Update status to show we're shutting down
                        Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `
                            -Status "SHUTTING_DOWN" `
                            -WorkerPID $global:WorkerPID `
                            -PythonPID $global:PythonPID `
                            -Message "Received STOP command: $($commandData.Parameters.Reason)"
                        
                        return "STOP"
                    }
                    default {
                        Write-Log "Unknown command received: $($commandData.Command)" -Level "WARN" -LogFile $Script:WorkerConfig.WorkerLogFile
                        return $null
                    }
                }
            }
        } catch {
            Write-Log "Error reading monitor command: $_" -Level "ERROR" -LogFile $Script:WorkerConfig.WorkerLogFile
        }
    }
    return $null
}


# ====================================================================
# MAIN EXECUTION
# ====================================================================

try {
    Write-Log "=== Worker Script Started ===" -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile
    Write-Log "Worker PID: $global:WorkerPID" -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile
    
    # Convert Python parameters to argument array
    $PYTHON_ARGS = Convert-HashtableToArgs -Params $Script:WorkerConfig.PythonParams
    Write-Log "Python arguments: $($PYTHON_ARGS -join ' ')" -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile
    
    # Generate timestamp for this run
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    
    # Create run folder structure
    $folderStructure = Create-RunFolderStructure -BasePath $RUNS_BASE_PATH -Timestamp $timestamp
    
    # Set up log files
    $MAIN_LOG_FILE = Join-Path $folderStructure.LogsPath "run_$timestamp.log"
    $PYTHON_OUTPUT_FILE = Join-Path $folderStructure.LogsPath "python_output.txt"
    $COMPLETION_SUMMARY_FILE = Join-Path $folderStructure.LogsPath "completion_summary.txt"
    
    # Register worker with monitor
    Register-WorkerWithMonitor

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
    
    # Log summary
    Write-Log "==================================================" -Level "SUCCESS" -LogFile $Script:WorkerConfig.WorkerLogFile
    Write-Log "RUN COMPLETED" -Level "SUCCESS" -LogFile $Script:WorkerConfig.WorkerLogFile
    Write-Log "Run Folder: $($folderStructure.RunFolderPath)" -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile
    Write-Log "Exit Code: $($executionResult.ExitCode)" -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile
    Write-Log "Duration: $durationFormatted" -Level "INFO" -LogFile $Script:WorkerConfig.WorkerLogFile
    
    # Update status
    Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `
        -Status "COMPLETED" `
        -WorkerPID $global:WorkerPID `
        -PythonPID $global:PythonPID `
        -Message "Worker completed successfully" `
        -RunFolder $folderStructure.RunFolderPath
    
} catch {
    # Update status on error
    Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `
        -Status "ERROR" `
        -WorkerPID $global:WorkerPID `
        -Message "Worker error: $_"
    
    Write-Log "Worker error: $_" -Level "ERROR" -LogFile $Script:WorkerConfig.WorkerLogFile
    throw
}
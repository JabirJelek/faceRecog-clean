#### Important

- Maintain the query requirement.
- Check explanation in every ####
- DO NOT INTRODUCES unused solution that does not relate to the query.

#### Instruction

From the provided files, make it so that the data flow of each files is correct, and there are no problematic code.

Yes, the venv is located in the same drive as the project root

#### Tips

follow instructions, no need to add non-related solution.

#### References

Use this as references.

https://github.com/MicrosoftDocs/PowerShell-Docs

https://learn.microsoft.com/en-us/powershell/

#### several files

# 1_common-paths.ps1

<#
.SYNOPSIS
Common path initialization module shared by monitor and folder creation scripts
.DESCRIPTION
Handles portable path discovery and date-based folder creation
#>

function Initialize-ProjectPortablePaths {
[CmdletBinding()]
param(
[switch]$IsMonitor,
        [switch]$IsWorker
)

    Write-Host "Initializing portable paths for maskRecog project..." -ForegroundColor Cyan

    # ====================================================================
    # STEP 1: FIND THE PROJECT ROOT (maskRecog directory)
    # ====================================================================

    # Method A: Check if we're already IN maskRecog directory
    $scriptPath = $PSScriptRoot  # Where this script is located
    $currentPath = $scriptPath

    # Look for maskRecog by going UP through parent directories
    while ($currentPath -and (Split-Path $currentPath -Parent)) {
        $currentDirName = Split-Path $currentPath -Leaf

        if ($currentDirName -eq "maskRecog") {
            $projectRoot = $currentPath
            break
        }

        $parentPath = Split-Path $currentPath -Parent
        # Stop if we reach drive root (like D:\) or can't go further
        if (!$parentPath -or $parentPath -eq $currentPath) {
            break
        }
        $currentPath = $parentPath
    }

    # Method B: If not found above, check current directory name
    if (!$projectRoot) {
        $currentDir = Get-Location
        if ((Split-Path $currentDir -Leaf) -eq "maskRecog") {
            $projectRoot = $currentDir
        }
    }

    # Method C: Last resort - ask user
    if (!$projectRoot) {
        Write-Host "Could not automatically find 'maskRecog' directory." -ForegroundColor Yellow
        $projectRoot = Read-Host "Please enter the full path to 'maskRecog' project root"

        if (!(Test-Path $projectRoot)) {
            Write-Host "ERROR: Path '$projectRoot' does not exist!" -ForegroundColor Red
            exit 1
        }
    }

    # ====================================================================
    # STEP 2: BUILD PATHS RELATIVE TO PROJECT ROOT
    # ====================================================================

    $global:ProjectRoot = $projectRoot
    $global:ActiveRoot = Split-Path $projectRoot -Parent | Split-Path -Parent
    $global:VenvRoot = Split-Path $projectRoot -Parent | Split-Path -Parent | Split-Path -Parent | Split-Path -Parent

    # ====================================================================
    # STEP 3: CREATE DATE-BASED FOLDER STRUCTURE
    # ====================================================================

    $currentDate = Get-Date -Format "yyyy-MM-dd"
    $global:CurrentDateFolder = $currentDate

    # Create the base Magick folder if it doesn't exist
    $magickBasePath = Join-Path $ActiveRoot "logs-running\magick"
    if (-not (Test-Path $magickBasePath)) {
        New-Item -ItemType Directory -Path $magickBasePath -Force | Out-Null
        Write-Host "Created base Magick folder: $magickBasePath" -ForegroundColor Yellow
    }

    # Create date-specific folder
    $dateBasedPath = Join-Path $magickBasePath $currentDate
    if (-not (Test-Path $dateBasedPath)) {
        New-Item -ItemType Directory -Path $dateBasedPath -Force | Out-Null
        Write-Host "Created date-based folder: $dateBasedPath" -ForegroundColor Yellow
    } else {
        Write-Host "Using existing date-based folder: $dateBasedPath" -ForegroundColor Green
    }

    # Store the active date path globally
    $global:ActiveDatePath = $dateBasedPath

    # ====================================================================
    # STEP 4: RETURN PATHS BASED ON SCRIPT TYPE
    # ====================================================================

    $paths = @{
        ProjectRoot = $projectRoot
        ActiveRoot = $ActiveRoot
        VenvRoot = $VenvRoot
        DateBasedPath = $dateBasedPath
        CurrentDate = $currentDate
    }

    # Monitor-specific paths
    if ($IsMonitor) {
        $paths.WorkerScript = Join-Path $projectRoot "patterns\scripts\1_magick\1_mask_portable.ps1"
        $paths.PythonScriptPath = Join-Path $projectRoot "patterns\algorithm\entry_multi_USED-Magick.py"
        $paths.PIDFilePath = Join-Path $dateBasedPath "monitor_pid_Magick.json"
        $paths.LogFile = Join-Path $dateBasedPath "monitor_Magick.log"
    }

    # Worker-specific paths
    if ($IsWorker) {
        $paths.PythonScript = Join-Path $projectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
        $paths.PythonExe = Join-Path $VenvRoot "Scripts\python.exe"
    }

    return $paths

}

function Get-DateBasedPath {
<#
.SYNOPSIS
Gets or creates a date-based folder path for the current day
#>
param(
[string]$BasePath = (Join-Path $ActiveRoot "logs-running\magick"),
        [DateTime]$Date = (Get-Date)
)

    $dateString = $Date.ToString("yyyy-MM-dd")
    $datePath = Join-Path $BasePath $dateString

    # Create the directory if it doesn't exist
    if (-not (Test-Path $datePath)) {
        try {
            New-Item -ItemType Directory -Path $datePath -Force | Out-Null
            Write-Log "Created date-based folder: $datePath" -Level "INFO"
        } catch {
            Write-Log "Failed to create date-based folder: $_" -Level "ERROR"
            throw
        }
    }

    return $datePath

}

# 1_mask_portable.ps1

<#
.SYNOPSIS
Creates folder structure and runs Python face recognition script
.DESCRIPTION
Sets up organized folder structure and executes Python algorithm
#>

# Import common paths module

. (Join-Path $PSScriptRoot "common-paths.ps1")

function Initialize-WorkerPaths {
<#
.SYNOPSIS
Initializes paths specifically for the worker script
#>

    Write-Host "=== Mask Detection Worker Script ===" -ForegroundColor Cyan
    Write-Host "Starting portable path initialization..." -ForegroundColor Cyan

    # Get base paths from common module
    $paths = Initialize-ProjectPortablePaths -IsWorker

    # Extract validated paths
    $VENV_ROOT = $paths.VenvRoot
    $PYTHON_SCRIPT = $paths.PythonScript
    $RUNS_BASE_PATH = $paths.DateBasedPath
    $ProjectRoot = $paths.ProjectRoot
    $ActiveDatePath = $paths.DateBasedPath

    return @{
        VENV_ROOT = $VENV_ROOT
        PYTHON_SCRIPT = $PYTHON_SCRIPT
        RUNS_BASE_PATH = $RUNS_BASE_PATH
        ProjectRoot = $ProjectRoot
        ActiveDatePath = $ActiveDatePath
    }

}

function Create-RunFolderStructure {
<#
.SYNOPSIS
Creates organized folder structure for the current run
#>
param(
[string]$BasePath,
        [string]$ProjectRoot,
[string]$ActiveDatePath
)

    # Generate run folder with timestamp
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $RUN_FOLDER_NAME = "Laptop_Process_MaskDetect_$timestamp"
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

        Write-Host "Created run folder structure at: $RUN_FOLDER_PATH"
    } catch {
        Write-Error "Failed to create run folder structure: $_"
        exit 1
    }

    # Set up log files
    $MAIN_LOG_FILE = Join-Path $RUN_LOGS_PATH "run_$timestamp.log"
    $PYTHON_OUTPUT_FILE = Join-Path $RUN_LOGS_PATH "python_output.txt"
    $COMPLETION_SUMMARY_FILE = Join-Path $RUN_LOGS_PATH "completion_summary.txt"

    return @{
        RunFolderPath = $RUN_FOLDER_PATH
        RunFolderName = $RUN_FOLDER_NAME
        LogsPath = $RUN_LOGS_PATH
        ScriptOutputPath = $RUN_SCRIPT_OUTPUT_PATH
        MetadataPath = $RUN_METADATA_PATH
        MainLogFile = $MAIN_LOG_FILE
        PythonOutputFile = $PYTHON_OUTPUT_FILE
        CompletionSummaryFile = $COMPLETION_SUMMARY_FILE
        Timestamp = $timestamp
    }

}

function Write-RunMetadata {
<#
.SYNOPSIS
Creates metadata file with run information
#>
param(
[hashtable]$FolderInfo,
        [hashtable]$Paths,
[array]$PythonArgs
)

    $metadata = @{
        run_id = $FolderInfo.Timestamp
        start_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        powershell_script = Split-Path -Leaf $MyInvocation.MyCommand.Path
        project_root = $Paths.ProjectRoot
        active_date_path = $Paths.ActiveDatePath
        virtual_env = $Paths.VENV_ROOT
        python_script = $Paths.PYTHON_SCRIPT
        arguments = $PythonArgs
        arguments_count = $PythonArgs.Count
        run_folder = $FolderInfo.RunFolderPath
    }

    $metadata | ConvertTo-Json | Out-File $FolderInfo.MetadataPath
    Write-Host "Created metadata file: $($FolderInfo.MetadataPath)"

    return $metadata

}

function Execute-PythonScript {
<#
.SYNOPSIS
Executes the Python script with proper environment setup
#>
param(
[hashtable]$Paths,
        [hashtable]$FolderInfo,
[array]$PythonArgs
)

    $pythonExe = Join-Path $Paths.VENV_ROOT "Scripts\python.exe"

    if (-not (Test-Path $pythonExe)) {
        $errorMsg = "ERROR: Python executable not found at $pythonExe"
        Write-Error $errorMsg
        exit 1
    }

    # Capture start time
    $startTime = Get-Date

    try {
        # Set working directory to script_output
        $originalLocation = Get-Location
        Set-Location $FolderInfo.ScriptOutputPath

        # Run Python with array of arguments
        & $pythonExe $Paths.PYTHON_SCRIPT $PythonArgs 2>&1 | Tee-Object -FilePath $FolderInfo.PythonOutputFile

        $exitCode = $LASTEXITCODE

        # Return to original location
        Set-Location $originalLocation

    } catch {
        $errorMessage = $_.Exception.Message
        Write-Error "Exception during Python script execution: $errorMessage"
        $exitCode = 1
    }

    return @{
        ExitCode = $exitCode
        StartTime = $startTime
        EndTime = Get-Date
    }

}

function Write-CompletionSummary {
<#
.SYNOPSIS
Creates completion summary file
#>
param(
[hashtable]$FolderInfo,
        [hashtable]$Paths,
[hashtable]$ExecutionResult,
        [array]$PythonArgs
)

    $duration = $ExecutionResult.EndTime - $ExecutionResult.StartTime
    $durationFormatted = "{0:D2}:{1:D2}:{2:D2}" -f $duration.Hours, $duration.Minutes, $duration.Seconds

    $completionSummary = @"

==================================================
RUN COMPLETION SUMMARY
==================================================
Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run ID: $($FolderInfo.Timestamp)
Project Root: $($Paths.ProjectRoot)
Active Date Path: $($Paths.ActiveDatePath)
Status: $(if ($ExecutionResult.ExitCode -eq 0) { "SUCCESS" } else { "FAILED (Exit code: $($ExecutionResult.ExitCode))" })

# FOLDER STRUCTURE

Run Folder: $($FolderInfo.RunFolderPath)
├── logs\
│ ├── run\_$($FolderInfo.Timestamp).log
│ ├── python_output.txt
│ └── completion_summary.txt
├── script_output\
└── metadata.json

# EXECUTION DETAILS

Virtual Environment: $($Paths.VENV_ROOT)
Python Script: $($Paths.PYTHON_SCRIPT)
Start Time: $($ExecutionResult.StartTime.ToString('yyyy-MM-dd HH:mm:ss'))
End Time: $($ExecutionResult.EndTime.ToString('yyyy-MM-dd HH:mm:ss'))
Duration: $durationFormatted
"@

    $completionSummary | Out-File $FolderInfo.CompletionSummaryFile

    # Update metadata with completion info
    $completionMetadata = Get-Content $FolderInfo.MetadataPath | ConvertFrom-Json
    $completionMetadata | Add-Member -NotePropertyName "end_time" -NotePropertyValue (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Force
    $completionMetadata | Add-Member -NotePropertyName "duration" -NotePropertyValue $durationFormatted -Force
    $completionMetadata | Add-Member -NotePropertyName "exit_code" -NotePropertyValue $ExecutionResult.ExitCode -Force
    $completionMetadata | Add-Member -NotePropertyName "python_pid" -NotePropertyValue $PID -Force
    $completionMetadata | ConvertTo-Json | Out-File $FolderInfo.MetadataPath

    return @{
        ExitCode = $ExecutionResult.ExitCode
        Duration = $durationFormatted
    }

}

# ====================================================================

# MAIN EXECUTION

# ====================================================================

# Initialize paths for worker

$paths = Initialize-WorkerPaths

# Python arguments (worker-specific)

$PYTHON_ARGS = @( # Add your Python arguments here # "--database", "path\to\database" # "--input", "path\to\input" # "--multi-source"
"-i", "12",
"-o", "number_13"
)

# Create run folder structure

$folderInfo = Create-RunFolderStructure -BasePath $paths.RUNS_BASE_PATH -ProjectRoot $paths.ProjectRoot -ActiveDatePath $paths.ActiveDatePath

# Write initial log header

# $logHeader = @"

RUN STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run Folder: $($folderInfo.RunFolderPath)
Project Root: $($paths.ProjectRoot)
Active Date Path: $($paths.ActiveDatePath)
Virtual Environment: $($paths.VENV_ROOT)
Python Script: $($paths.PYTHON_SCRIPT)
Arguments: $($PYTHON_ARGS -join ' ')
==================================================
"@

$logHeader | Out-File $folderInfo.MainLogFile -Append

# Write metadata

$metadata = Write-RunMetadata -FolderInfo $folderInfo -Paths $paths -PythonArgs $PYTHON_ARGS

# Execute Python script

Write-Host "Starting Python script execution..."
Write-Host "Run folder: $($folderInfo.RunFolderPath)"
Write-Host "Arguments: $($PYTHON_ARGS -join ' ')"

$executionResult = Execute-PythonScript -Paths $paths -FolderInfo $folderInfo -PythonArgs $PYTHON_ARGS

# Create completion summary

$completion = Write-CompletionSummary -FolderInfo $folderInfo -Paths $paths -ExecutionResult $executionResult -PythonArgs $PYTHON_ARGS

# Final output

Write-Host ""
Write-Host "=================================================="
Write-Host "RUN COMPLETED"
Write-Host "=================================================="
Write-Host "Run Folder: $($folderInfo.RunFolderPath)"
Write-Host "Main Log: $($folderInfo.MainLogFile)"
Write-Host "Python Output: $($folderInfo.PythonOutputFile)"
Write-Host "Completion Summary: $($folderInfo.CompletionSummaryFile)"
Write-Host "Metadata: $($folderInfo.MetadataPath)"
Write-Host ""
Write-Host "Exit code: $($completion.ExitCode)"
Write-Host "Duration: $($completion.Duration)"
Write-Host "=================================================="

# Exit with Python's exit code

exit $completion.ExitCode

# 1_monitor.ps1

<#
.SYNOPSIS
Monitors face recognition worker process and manages lifecycle
.DESCRIPTION
Monitors worker process, validates output, and handles notifications
#>

# Import common paths module

. (Join-Path $PSScriptRoot "1_common-paths.ps1")

# Global variables

$WorkerProcess = $null
$WorkerPID = $null
$PythonPID = $null
$WorkerStartTime = $null
$PythonStartTime = $null
$LastValidation = $null
$CurrentRunFolder = $null
$WorkerIsRunning = $false
$PythonIsRunning = $false
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$LastWorkerAttempt = $null

# Enhanced tracking for resilience

$global:ForceStopAttempts = 0
$global:LastForceStopTime = $null
$global:ForceStopThreshold = 2
$global:ForceStopWindowSeconds = 5
$global:EmailAttachmentQueue = @()
$global:CollectedRunFolders = @()
$global:IsShuttingDown = $false
$global:PersistentTracking = @{
LastKnownRunFolder = $null
LastKnownPythonPID = $null
LastKnownWorkerPID = $null
LastValidationTime = $null
LastValidationResult = $null
ProcessStopHistory = @()
ValidationHistory = @()
DailyRunCount = 0
LastSuccessfulRun = $null
}

# PID tracking structure

$PIDTracking = @{
WorkerPID = $null
PythonPID = $null
WorkerStartTime = $null
PythonStartTime = $null
RunFolder = $null
LastUpdate = $null
EmailQueue = @()
CollectedFolders = @()
ShutdownInitiated = $false
PersistentTracking = $null
}

# ====================================================================

# CONFIGURATION

# ====================================================================

$Script:Config = @{ # Schedule configuration
StartTime = "08:00"
EndTime = "13:48"

    # Process tracking
    PythonProcessName = "python"
    WorkerProcessName = "powershell"

    # Expected folder structure
    ExpectedSubfolders = @("logs", "script_output")
    ExpectedFiles = @("metadata.json")

    # Validation settings
    MaxValidationRetries = 5
    RetryDelaySeconds = 10

    # Process monitoring
    ProcessCheckInterval = 15
    GracefulShutdownTimeout = 60

    # PID tracking
    MaxPIDFileAgeMinutes = 120

    # Email notifications
    SendEmailOnCompletion = $true
    EmailRecipients = @(
        @{ Address = "faridraihan17@gmail.com"; Language = "English" },
        @{ Address = "ikeepmypromiz@gmail.com"; Language = "Bahasa" }
    )
    EmailFrom = "faridraihan17@gmail.com"
    EmailSubject = @{
        English = "Face Recognition Process Completed Successfully"
        Bahasa = "Proses Pengenalan Wajah Selesai dengan Sukses"
    }
    SmtpServer = "smtp.gmail.com"
    SmtpPort = 587
    UseSSL = $true
    EmailCredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"

}

# ====================================================================

# MONITOR FUNCTIONS

# ====================================================================

function Write-Log {
param(
[string]$Message,
        [string]$Level = "INFO"
)

    $currentTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$currentTimestamp] [$Level] $Message"

    try {
        Add-Content -Path $Config.LogFile -Value $logEntry -ErrorAction SilentlyContinue
    } catch {
        Write-Host "Log file write failed: $_" -ForegroundColor Yellow
    }

    switch ($Level) {
        "ERROR" { Write-Host $logEntry -ForegroundColor Red }
        "WARN" { Write-Host $logEntry -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logEntry -ForegroundColor Green }
        "DEBUG" { Write-Host $logEntry -ForegroundColor Gray }
        default { Write-Host $logEntry -ForegroundColor White }
    }

}

function Check-ProcessStatus {
$status = @{
WorkerRunning = $false
PythonRunning = $false
WorkerPID = $WorkerPID
PythonPID = $PythonPID
}

    # Check worker process
    if ($WorkerPID -and $WorkerPID -ne 0) {
        $status.WorkerRunning = Is-ProcessRunning -ProcessId $WorkerPID -ProcessName $Config.WorkerProcessName
    }

    # Check Python process
    if ($PythonPID -and $PythonPID -ne 0) {
        $status.PythonRunning = Is-ProcessRunning -ProcessId $PythonPID -ProcessName $Config.PythonProcessName
    }

    # If we think Python is running but PID is null, try to find it
    if ((-not $status.PythonRunning) -and $WorkerIsRunning) {
        $foundPID = Find-PythonProcess
        if ($foundPID) {
            $global:PythonPID = $foundPID
            $status.PythonPID = $foundPID
            $status.PythonRunning = Is-ProcessRunning -ProcessId $foundPID -ProcessName $Config.PythonProcessName
            Save-PIDTracking
        }
    }

    # Update global state
    $previousWorkerRunning = $global:WorkerIsRunning
    $previousPythonRunning = $global:PythonIsRunning
    $global:WorkerIsRunning = $status.WorkerRunning
    $global:PythonIsRunning = $status.PythonRunning

    # Detect unexpected stops
    if (($previousWorkerRunning -and -not $status.WorkerRunning) -or
        ($previousPythonRunning -and -not $status.PythonRunning)) {
        Write-Log "Detected unexpected process stop" -Level "WARN"
    }

    return $status

}

function Find-PythonProcess { # Try to find the Python process running our specific script
Write-Log "Searching for Python process..." -Level "DEBUG"

    # Method 1: Check for processes with our script path in command line
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*python*" }

    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Config.PythonScriptPath)*") {
                Write-Log "Found Python process with our script: PID=$($proc.Id)" -Level "SUCCESS"
                return $proc.Id
            }
        } catch { }
    }

    # Method 2: Check for Python processes started after our worker
    if ($WorkerStartTime) {
        $pythonProcs = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
            Where-Object { $_.StartTime -gt $WorkerStartTime }

        if ($pythonProcs) {
            # Take the first one started after our worker
            $foundPID = $pythonProcs[0].Id
            Write-Log "Found Python process started after worker: PID=$foundPID" -Level "INFO"
            return $foundPID
        }
    }

    # Method 3: Look in the latest run folder's metadata for PID
    $runFolder = Find-LatestRunFolder
    if ($runFolder) {
        $metadataPath = Join-Path $runFolder.FullName "metadata.json"
        if (Test-Path $metadataPath) {
            try {
                $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
                if ($metadata.PSObject.Properties.Name -contains "python_pid") {
                    $foundPID = $metadata.python_pid
                    Write-Log "Found Python PID in metadata: $foundPID" -Level "INFO"

                    # Verify the process still exists
                    try {
                        Get-Process -Id $foundPID -ErrorAction Stop | Out-Null
                        return $foundPID
                    } catch {
                        Write-Log "Python PID from metadata no longer exists: $foundPID" -Level "WARN"
                    }
                }
            } catch { }
        }
    }

    Write-Log "No Python process found matching criteria" -Level "DEBUG"
    return $null

}

function Is-ProcessRunning {
param(
[int]$ProcessId, 
        [string]$ProcessName
)

    if (-not $ProcessId -or $ProcessId -eq 0) {
        return $false
    }

    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
        if ($ProcessName) {
            return ($process.ProcessName -like "*$ProcessName*" -and (-not $process.HasExited))
        }
        return (-not $process.HasExited)
    } catch {
        return $false
    }

}

function Start-WorkerProcess { # Check if we already have a running Python process
$existingPythonPID = Find-PythonProcess
    if ($existingPythonPID) {
Write-Log "Found existing Python process (PID: $existingPythonPID), not starting new one" -Level "WARN"
$global:PythonPID = $existingPythonPID
$global:PythonIsRunning = $true
$global:PythonStartTime = Get-Date
Save-PIDTracking
return $true
}

    try {
        Write-Log "Starting face recognition worker process..." -Level "INFO"

        $arguments = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$($Config.WorkerScript)`""
        )

        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processInfo.FileName = "powershell.exe"
        $processInfo.Arguments = $arguments
        $processInfo.RedirectStandardOutput = $false
        $processInfo.RedirectStandardError = $false
        $processInfo.UseShellExecute = $false
        $processInfo.CreateNoWindow = $true

        $WorkerProcess = New-Object System.Diagnostics.Process
        $WorkerProcess.StartInfo = $processInfo

        if ($WorkerProcess.Start()) {
            $global:WorkerPID = $WorkerProcess.Id
            $global:WorkerStartTime = Get-Date
            $global:WorkerIsRunning = $true

            Write-Log "Worker process started (PID: $WorkerPID)" -Level "SUCCESS"

            # Wait for Python process to start
            Write-Log "Waiting for Python process to start..." -Level "INFO"
            $maxWaitTime = 30
            $waitInterval = 2
            $waited = 0

            while ($waited -lt $maxWaitTime) {
                $foundPID = Find-PythonProcess
                if ($foundPID) {
                    $global:PythonPID = $foundPID
                    $global:PythonIsRunning = $true
                    $global:PythonStartTime = Get-Date
                    Write-Log "Python process found (PID: $PythonPID)" -Level "SUCCESS"
                    Save-PIDTracking
                    return $true
                }

                Start-Sleep -Seconds $waitInterval
                $waited += $waitInterval
            }

            Write-Log "Python process did not start within $maxWaitTime seconds" -Level "WARN"
            Save-PIDTracking
            return $true
        } else {
            Write-Log "Failed to start worker process" -Level "ERROR"
            return $false
        }
    }
    catch {
        Write-Log "ERROR: Failed to start worker process: $_" -Level "ERROR"
        return $false
    }

}

function Stop-WorkerProcess {
$stoppedProcesses = @()
$stopReason = "Normal Shutdown"

    Write-Log "Stopping worker process. Reason: $stopReason" -Level "INFO"

    # First, try to stop the Python process
    if ($PythonPID -and $PythonPID -ne 0) {
        Write-Log "Stopping Python process (PID: $PythonPID)..." -Level "INFO"

        try {
            $pythonProcess = Get-Process -Id $PythonPID -ErrorAction Stop

            if (-not $pythonProcess.HasExited) {
                $pythonProcess.CloseMainWindow() | Out-Null
                Start-Sleep -Seconds 2

                if (-not $pythonProcess.HasExited) {
                    Write-Log "Forcefully terminating Python process..." -Level "WARN"
                    $pythonProcess.Kill()
                    if ($pythonProcess.WaitForExit($Config.GracefulShutdownTimeout * 1000)) {
                        $stoppedProcesses += "Python"
                        Write-Log "Python process terminated" -Level "SUCCESS"
                    }
                } else {
                    $stoppedProcesses += "Python"
                    Write-Log "Python process exited gracefully" -Level "SUCCESS"
                }
            } else {
                Write-Log "Python process already exited" -Level "INFO"
            }
        }
        catch {
            Write-Log "Error stopping Python process: $_" -Level "ERROR"
        }
    }

    # Then stop the worker PowerShell process
    if ($WorkerPID -and $WorkerPID -ne 0) {
        Write-Log "Stopping worker process (PID: $WorkerPID)..." -Level "INFO"

        try {
            $workerProcess = Get-Process -Id $WorkerPID -ErrorAction Stop

            if (-not $workerProcess.HasExited) {
                $workerProcess.CloseMainWindow() | Out-Null
                Start-Sleep -Seconds 2

                if (-not $workerProcess.HasExited) {
                    Write-Log "Forcefully terminating worker process..." -Level "WARN"
                    $workerProcess.Kill()
                    if ($workerProcess.WaitForExit($Config.GracefulShutdownTimeout * 1000)) {
                        $stoppedProcesses += "Worker"
                        Write-Log "Worker process terminated" -Level "SUCCESS"
                    }
                } else {
                    $stoppedProcesses += "Worker"
                    Write-Log "Worker process exited gracefully" -Level "SUCCESS"
                }
            } else {
                Write-Log "Worker process already exited" -Level "INFO"
            }
        }
        catch {
            Write-Log "Error stopping worker process: $_" -Level "ERROR"
        }
    }

    # Clean up variables
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false

    # Remove PID tracking file
    if (Test-Path $Config.PIDFilePath) {
        Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        Write-Log "Removed PID tracking file" -Level "DEBUG"
    }

    if ($stoppedProcesses.Count -gt 0) {
        Write-Log "Stopped processes: $($stoppedProcesses -join ', ')" -Level "INFO"
    }

}

function Save-PIDTracking {
$workerStartString = if ($WorkerStartTime -and ($WorkerStartTime -is [DateTime])) {
$WorkerStartTime.ToString("yyyy-MM-dd HH:mm:ss")
} else {
$null
}

    $pythonStartString = if ($PythonStartTime -and ($PythonStartTime -is [DateTime])) {
        $PythonStartTime.ToString("yyyy-MM-dd HH:mm:ss")
    } else {
        $null
    }

    $PIDTracking.WorkerPID = $WorkerPID
    $PIDTracking.PythonPID = $PythonPID
    $PIDTracking.WorkerStartTime = $workerStartString
    $PIDTracking.PythonStartTime = $pythonStartString
    $PIDTracking.RunFolder = $CurrentRunFolder
    $PIDTracking.LastUpdate = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $PIDTracking.EmailQueue = $global:EmailAttachmentQueue
    $PIDTracking.CollectedFolders = $global:CollectedRunFolders
    $PIDTracking.ShutdownInitiated = $global:IsShuttingDown

    try {
        $PIDTracking | ConvertTo-Json -Depth 10 | Out-File -FilePath $Config.PIDFilePath -Force
        Write-Log "PID tracking saved" -Level "DEBUG"
    } catch {
        Write-Log "Failed to save PID tracking: $_" -Level "ERROR"
    }

}

function Load-PIDTracking {
if (-not (Test-Path $Config.PIDFilePath)) {
Write-Log "No PID tracking file found" -Level "DEBUG"
return $false
}

    try {
        $loaded = Get-Content -Path $Config.PIDFilePath -Raw | ConvertFrom-Json

        # Check if PID file is too old
        $lastUpdate = [DateTime]::ParseExact($loaded.LastUpdate, "yyyy-MM-dd HH:mm:ss", $null)
        $ageMinutes = ((Get-Date) - $lastUpdate).TotalMinutes

        if ($ageMinutes -gt $Config.MaxPIDFileAgeMinutes) {
            Write-Log "PID file is too old ($ageMinutes minutes), cleaning up" -Level "WARN"
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            return $false
        }

        # Check if processes are still running
        $workerAlive = $false
        $pythonAlive = $false

        if ($loaded.WorkerPID -and $loaded.WorkerPID -ne 0) {
            try {
                $workerProcess = Get-Process -Id $loaded.WorkerPID -ErrorAction Stop
                $workerAlive = (-not $workerProcess.HasExited)
            } catch { }
        }

        if ($loaded.PythonPID -and $loaded.PythonPID -ne 0) {
            try {
                $pythonProcess = Get-Process -Id $loaded.PythonPID -ErrorAction Stop
                $pythonAlive = (-not $pythonProcess.HasExited)
            } catch { }
        }

        if ($workerAlive -or $pythonAlive) {
            $global:WorkerPID = $loaded.WorkerPID
            $global:PythonPID = $loaded.PythonPID

            if ($loaded.WorkerStartTime -and $loaded.WorkerStartTime -ne "-") {
                try {
                    $global:WorkerStartTime = [DateTime]::ParseExact($loaded.WorkerStartTime, "yyyy-MM-dd HH:mm:ss", $null)
                } catch {
                    Write-Log "Invalid WorkerStartTime in PID file" -Level "WARN"
                    $global:WorkerStartTime = $null
                }
            }

            if ($loaded.PythonStartTime -and $loaded.PythonStartTime -ne "-") {
                try {
                    $global:PythonStartTime = [DateTime]::ParseExact($loaded.PythonStartTime, "yyyy-MM-dd HH:mm:ss", $null)
                } catch {
                    Write-Log "Invalid PythonStartTime in PID file" -Level "WARN"
                    $global:PythonStartTime = $null
                }
            }

            $global:CurrentRunFolder = $loaded.RunFolder

            Write-Log "PID tracking loaded: WorkerPID=$WorkerPID (Alive: $workerAlive)" -Level "INFO"
            return $true
        } else {
            Write-Log "Loaded PIDs are no longer running, cleaning up" -Level "INFO"
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            return $false
        }
    } catch {
        Write-Log "Failed to load PID tracking: $_" -Level "ERROR"
        Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        return $false
    }

}

function Find-LatestRunFolder {
try {
if (-not (Test-Path $Config.RunsBasePath)) {
return $null
}

        $folders = Get-ChildItem -Path $Config.RunsBasePath -Directory -Filter $Config.OutputFolderPattern -ErrorAction SilentlyContinue

        if (-not $folders) {
            return $null
        }

        $latestFolder = $folders | Sort-Object CreationTime -Descending | Select-Object -First 1
        return $latestFolder
    }
    catch {
        Write-Log "Error finding run folders: $_" -Level "ERROR"
        return $null
    }

}

function Validate-Output {
param([int]$RetryCount = 0)

    Write-Log "Validating face recognition output structure..." -Level "INFO"

    # Find the latest run folder
    $runFolder = Find-LatestRunFolder

    if (-not $runFolder) {
        if ($RetryCount -lt $Config.MaxValidationRetries) {
            Write-Log "No output folder found. Retrying..." -Level "WARN"
            Start-Sleep -Seconds $Config.RetryDelaySeconds
            return Validate-Output -RetryCount ($RetryCount + 1)
        } else {
            Write-Log "VALIDATION FAILED: No output folder found" -Level "ERROR"
            return @{
                Success = $false;
                Error = "No output folder created";
                RunFolder = $null
            }
        }
    }

    $Global:CurrentRunFolder = $runFolder.FullName

    # Perform folder structure validation
    $validationResult = @{
        Success = $true
        RunFolder = $runFolder.FullName
        FolderName = $runFolder.Name
        CreationTime = $runFolder.CreationTime
        MissingItems = @()
        Errors = @()
        Warnings = @()
        Details = @{
            FileSizes = @{}
            AttachmentFiles = @()
        }
    }

    Write-Log "Validating folder structure for: $($runFolder.Name)" -Level "INFO"

    # Check for expected subfolders
    foreach ($item in $Config.ExpectedSubfolders) {
        $itemPath = Join-Path $runFolder.FullName $item

        if (-not (Test-Path $itemPath)) {
            $validationResult.MissingItems += $item
            $validationResult.Success = $false
            Write-Log "Missing expected subfolder: $item" -Level "WARN"
        } else {
            Write-Log "Found subfolder: $item" -Level "DEBUG"
        }
    }

    # Check for expected files
    foreach ($item in $Config.ExpectedFiles) {
        $itemPath = Join-Path $runFolder.FullName $item

        if (-not (Test-Path $itemPath)) {
            $validationResult.MissingItems += $item
            $validationResult.Success = $false
            Write-Log "Missing expected file: $item" -Level "WARN"
        } else {
            if ($item -eq "metadata.json") {
                try {
                    $metadataContent = Get-Content $itemPath -Raw | ConvertFrom-Json
                    $validationResult.Details["metadata"] = @{
                        RunID = $metadataContent.run_id
                        StartTime = $metadataContent.start_time
                        ExitCode = $metadataContent.exit_code
                    }
                    Write-Log "Metadata file is valid JSON" -Level "DEBUG"

                    $fileSize = (Get-Item $itemPath).Length
                    $validationResult.Details.FileSizes[$item] = $fileSize
                    Write-Log "Metadata file size: $([math]::Round($fileSize/1KB, 2)) KB" -Level "DEBUG"

                } catch {
                    $validationResult.Errors += $item + ": Invalid JSON format"
                    $validationResult.Success = $false
                    Write-Log "Metadata file contains invalid JSON" -Level "WARN"
                }
            }
        }
    }

    # Summary
    if ($validationResult.Success) {
        if ($validationResult.Warnings.Count -gt 0) {
            Write-Log "VALIDATION SUCCESS with warnings" -Level "SUCCESS"
        } else {
            Write-Log "VALIDATION SUCCESS: Folder structure complete" -Level "SUCCESS"
        }
    } else {
        Write-Log "VALIDATION FAILED" -Level "ERROR"
    }

    return $validationResult

}

function Test-TimeWindow {
param([string]$TargetTime)

    $now = Get-Date
    try {
        $target = [DateTime]::ParseExact($TargetTime, "HH:mm", $null)
        return ($now.TimeOfDay -ge $target.TimeOfDay)
    } catch {
        Write-Log "Invalid time format: $TargetTime" -Level "ERROR"
        return $false
    }

}

function Show-StatusBanner {
$status = Get-ProcessStatus

    $currentSecond = (Get-Date).Second
    if ($currentSecond % 20 -ne 0) {
        return
    }

    Clear-Host
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "    FACE RECOGNITION PROCESS MONITOR" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Current Date: $(Get-Date -Format 'yyyy-MM-dd')" -ForegroundColor Yellow
    Write-Host "Current Time: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Yellow
    Write-Host "Schedule: $($Config.StartTime) - $($Config.EndTime)" -ForegroundColor Yellow

    if ($status.PythonRunning) {
        Write-Host "PYTHON STATUS: RUNNING" -ForegroundColor Green
        Write-Host "  PID: $PythonPID" -ForegroundColor White
    } else {
        Write-Host "PYTHON STATUS: STOPPED" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "WORKER STATUS: $(if ($status.WorkerRunning) {'RUNNING'} else {'STOPPED'})" -ForegroundColor $(if ($status.WorkerRunning) {'Green'} else {'Red'})

    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan

}

function Get-ProcessStatus {
$status = @{
WorkerRunning = $WorkerIsRunning
PythonRunning = $PythonIsRunning
CurrentTime = Get-Date -Format "HH:mm:ss"
CurrentDate = Get-Date -Format "yyyy-MM-dd"
WorkerInfo = @{
PID = $WorkerPID
PythonPID = $PythonPID
}
}

    return $status

}

# ====================================================================

# MAIN EXECUTION

# ====================================================================

try { # Initialize paths for monitor
$paths = Initialize-ProjectPortablePaths -IsMonitor

    # Update configuration with paths
    $Script:Config.WorkerScript = $paths.WorkerScript
    $Script:Config.PythonScriptPath = $paths.PythonScriptPath
    $Script:Config.RunsBasePath = $paths.DateBasedPath
    $Script:Config.OutputFolderPattern = "Laptop_Process_MaskDetect_*"
    $Script:Config.PIDFilePath = $paths.PIDFilePath
    $Script:Config.LogFile = $paths.LogFile
    $Script:Config.CurrentDate = $paths.CurrentDate
    $Script:Config.ActiveDatePath = $paths.DateBasedPath

    # Create log directory if it doesn't exist
    $logDir = Split-Path $Config.LogFile -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    Write-Log "=== Face Recognition Monitor Started ===" -Level "INFO"
    Write-Log "Start Time: $($Config.StartTime)" -Level "INFO"
    Write-Log "End Time: $($Config.EndTime)" -Level "INFO"

    # Load existing PID tracking
    $pidLoaded = Load-PIDTracking
    if ($pidLoaded) {
        Write-Log "Resumed monitoring of existing processes" -Level "SUCCESS"
        Check-ProcessStatus | Out-Null
    }

    # Ensure runs base path exists
    if (-not (Test-Path $Config.RunsBasePath)) {
        Write-Log "Creating runs base directory" -Level "WARN"
        New-Item -ItemType Directory -Path $Config.RunsBasePath -Force | Out-Null
    }

    Clear-Host

    # Main monitoring loop
    Write-Log "Entering main monitoring loop..." -Level "INFO"

    while ($true) {
        try {
            # Check process status
            $processStatus = Check-ProcessStatus

            # Get time window status
            $startPassed = Test-TimeWindow -TargetTime $Config.StartTime
            $endPassed = Test-TimeWindow -TargetTime $Config.EndTime
            $inWindow = ($startPassed -and !$endPassed)

            $currentTime = Get-Date -Format "HH:mm:ss"

            # Show status banner
            Show-StatusBanner

            Write-Log "Check: $currentTime | Window: $(if ($inWindow) {'Active'} else {'Inactive'}) | Python: $(if ($processStatus.PythonRunning) {'Running'} else {'Stopped'})" -Level "DEBUG"

            # Check if we should start worker
            if ($inWindow -and !$processStatus.PythonRunning) {
                Write-Log "Time window active and no Python process running - starting worker..." -Level "INFO"

                if ($LastWorkerAttempt -and ((Get-Date) - $LastWorkerAttempt).TotalSeconds -lt 60) {
                    Write-Log "Skipping worker start - too soon after last attempt" -Level "DEBUG"
                } else {
                    $started = Start-WorkerProcess
                    $global:LastWorkerAttempt = Get-Date

                    if ($started) {
                        Write-Log "Worker started. Monitoring Python process..." -Level "SUCCESS"
                        $processStatus = Check-ProcessStatus
                    } else {
                        Write-Log "Worker failed to start. Will retry on next check." -Level "WARN"
                    }
                }
            }

            # Handle end time
            elseif ($endPassed) {
                Write-Log "End time reached - initiating shutdown sequence..." -Level "INFO"

                # Stop processes if they're running
                if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
                    Write-Log "Stopping running processes..." -Level "INFO"
                    Stop-WorkerProcess
                    Start-Sleep -Seconds 5
                }

                # Validate the last output
                Write-Log "Validating final worker output..." -Level "INFO"
                $LastValidation = Validate-Output

                Write-Log "Daily process completed. Stopping monitor..." -Level "INFO"
                break
            }

            # Save PID tracking periodically
            if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
                Save-PIDTracking
            }

            # Wait before next check
            Start-Sleep -Seconds $Config.ProcessCheckInterval

        } catch {
            Write-Log "Error in main loop: $_" -Level "ERROR"
            Save-PIDTracking
            Start-Sleep -Seconds $Config.ProcessCheckInterval
        }
    }

}
catch {
Write-Log "FATAL ERROR: $\_" -Level "ERROR"
}
finally {
Write-Log "Cleaning up..." -Level "INFO"
Stop-WorkerProcess

    Write-Log "=== Face Recognition Monitor Stopped ===" -Level "INFO"
    Write-Host "Monitor stopped." -ForegroundColor Yellow
    Write-Host "Log file: $($Config.LogFile)" -ForegroundColor Yellow

}

#### Important

- Maintain the query requirement.
- Check explanation in every ####
- DO NOT INTRODUCES unused solution that does not relate to the query.

#### Instruction

Fix problematic code in the process. Unified other messy functions. Merge non-essential method. Reduce redundant unused method.

#### Tips

follow instructions, no need to add non-related solution.

#### References

Use this as references.

https://github.com/MicrosoftDocs/PowerShell-Docs

https://learn.microsoft.com/en-us/powershell/

#### Several utilized file

# 1_monitor.ps1

<#
.SYNOPSIS
Enhanced time-based process monitor for Face Recognition pipeline with PID tracking.
.DESCRIPTION
Monitors face recognition worker process with enhanced resilience and state recovery.
.NOTES
Updated with old version's process checking structure that works.
#>

# ====================================================================

# ENHANCED: Import common paths module with improved error handling

# ====================================================================

$commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
if (Test-Path $commonPathsScript) {
try { # Dot-source the script to load functions into current scope
. $commonPathsScript
Write-Host "✓ Common paths module loaded" -ForegroundColor Green

        # Test if functions are loaded
        if (-not (Get-Command Initialize-ProjectPortablePaths -ErrorAction SilentlyContinue)) {
            Write-Host "ERROR: Required functions not loaded from common-paths.ps1" -ForegroundColor Red
            exit 1
        }
    } catch {
        Write-Host "ERROR: Failed to load common paths: $_" -ForegroundColor Red
        exit 1
    }

} else {
Write-Host "ERROR: Common paths script not found at: $commonPathsScript" -ForegroundColor Red
exit 1
}

# ====================================================================

# ENHANCED: Initialize paths for monitor

# ====================================================================

Write-Host "Initializing enhanced monitor..." -ForegroundColor Cyan

# Use the common paths function with monitor configuration

$paths = Initialize-ProjectPortablePaths -IsMonitor
$global:MonitorPaths = $paths

# Check if paths initialization was successful

if (-not $paths -or -not $paths.ProjectRoot) {
Write-Host "ERROR: Failed to initialize paths. Check project structure." -ForegroundColor Red
exit 1
}

# Update configuration with paths

$Script:Config = @{ # Schedule configuration
StartTime = "08:00"
EndTime = "14:47"

    # Process tracking - USING OLD VERSION'S STRUCTURE
    PythonProcessName = "python"
    WorkerProcessName = "powershell"

    # Worker script path
    WorkerScript = $paths.WorkerScript
    PythonScript = $paths.PythonScript

    # Paths for validation
    RunsBasePath = $paths.DateBasedPath
    OutputFolderPattern = "Magick_Process_MaskDetect_*"

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
    PIDFilePath = $paths.PIDFilePath
    MaxPIDFileAgeMinutes = 120

    # Logging - FIXED: Ensure LogFile path is properly set
    LogFile = if ($paths.LogFile) { $paths.LogFile } else { Join-Path $paths.DateBasedPath "monitor_Magick.log" }
    CurrentDate = $paths.CurrentDate
    ActiveDatePath = $paths.DateBasedPath

    # Sudden termination tracking
    SuddenTermination = @{
        TrackingFile = Join-Path $paths.DateBasedPath "sudden_termination_tracking.json"
        RecordRetentionDays = 30
        ConsecutiveThreshold = 3
        CleanupAction = "ForceCleanupAndNotify"
    }

}

# ====================================================================

# ENHANCED: Global variables - UPDATED WITH OLD VERSION'S TRACKING

# ====================================================================

$global:WorkerProcess = $null
$global:WorkerPID = $null
$global:PythonPID = $null
$global:WorkerStartTime = $null
$global:PythonStartTime = $null
$global:LastValidation = $null
$global:CurrentRunFolder = $null
$global:WorkerIsRunning = $false
$global:PythonIsRunning = $false
$global:LastWorkerAttempt = $null

# Enhanced tracking from old version

$global:ForceStopAttempts = 0
$global:LastForceStopTime = $null
$global:ForceStopThreshold = 2
$global:ForceStopWindowSeconds = 5
$global:IsShuttingDown = $false

# Sudden Termination Tracking

$global:SuddenTerminationTracking = @{
Events = @()
CurrentStreak = 0
LastCleanupDate = $null
Statistics = @{
TotalSuddenTerminations = 0
TotalCleanups = 0
LastCleanupReason = $null
FirstEventDate = $null
LastEventDate = $null
}
}

# Persistent Tracking

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
CollectedRunFolders = @()
}

$global:CollectedRunFolders = @()
$global:EmailAttachmentQueue = @()

# ====================================================================

# CRITICAL UPDATE: Process Management Functions from OLD VERSION

# ====================================================================

function Check-ProcessStatus { # First try communication-based detection
if (-not $global:WorkerIsRunning) {
        $detected = Detect-WorkerProcess
        if ($detected) {
Save-PIDTracking
}
}

    # Then verify processes
    $status = @{
        WorkerRunning = $false
        PythonRunning = $false
        WorkerPID = $global:WorkerPID
        PythonPID = $global:PythonPID
        UsingCommunication = $false
    }

    # Check worker using multiple methods
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        $status.WorkerRunning = Is-ProcessRunning -ProcessId $global:WorkerPID -ProcessName "powershell"

        if (-not $status.WorkerRunning) {
            # Try communication check as fallback
            $status.WorkerRunning = Check-WorkerHealth
            if ($status.WorkerRunning) {
                $status.UsingCommunication = $true
            }
        }
    } else {
        # No worker PID set, try communication
        $status.WorkerRunning = Check-WorkerHealth
        if ($status.WorkerRunning) {
            $status.UsingCommunication = $true
            # Try to get PID from communication files
            $commPaths = Initialize-CommunicationPaths -Paths $global:MonitorPaths -IsMonitor
            $statusData = Read-WorkerStatus -StatusFile $commPaths.StatusFile
            if ($statusData.WorkerPID -gt 0) {
                $global:WorkerPID = $statusData.WorkerPID
                $status.WorkerPID = $statusData.WorkerPID
            }
        }
    }

    # Check Python
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        $status.PythonRunning = Is-ProcessRunning -ProcessId $global:PythonPID -ProcessName "python"
    } elseif ($global:WorkerIsRunning) {
        # Try to find Python if worker is running but PythonPID not set
        $foundPID = Find-PythonProcess
        if ($foundPID) {
            $global:PythonPID = $foundPID
            $status.PythonPID = $foundPID
            $status.PythonRunning = Is-ProcessRunning -ProcessId $foundPID -ProcessName "python"
            Save-PIDTracking
            Update-WorkerCommunication -WorkerPID $global:WorkerPID -PythonPID $foundPID
        }
    }

    # Update global state
    $global:WorkerIsRunning = $status.WorkerRunning
    $global:PythonIsRunning = $status.PythonRunning

    return $status

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

function Find-PythonProcess { # Try to find the Python process running our specific script
Write-Log "Searching for Python process..." -Level "DEBUG"

    # Method 1: Check for processes with our script path in command line
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*python*" }

    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.PythonScript)*") {
                Write-Log "Found Python process with our script: PID=$($proc.Id)" -Level "SUCCESS"
                return $proc.Id
            }
        } catch { }
    }

    # Method 2: Check for Python processes started after our worker
    if ($global:WorkerStartTime) {
        $pythonProcs = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
            Where-Object { $_.StartTime -gt $global:WorkerStartTime }

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

# ====================================================================

# ENHANCED: Logging function with file and console output

# ====================================================================

function Write-Log {
param(
[string]$Message,
        [string]$Level = "INFO"
)

    $currentTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$currentTimestamp] [$Level] $Message"

    # Write to log file
    if ($Script:Config.LogFile) {
        try {
            $logDir = Split-Path $Script:Config.LogFile -Parent
            if (-not (Test-Path $logDir)) {
                New-Item -ItemType Directory -Path $logDir -Force | Out-Null
            }

            Add-Content -Path $Script:Config.LogFile -Value $logEntry -ErrorAction SilentlyContinue
        } catch {
            # Fallback to console if file write fails
            Write-Host "Log file write failed: $_" -ForegroundColor Yellow
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

# ====================================================================

# ENHANCED: Worker Detection and Communication Functions

# ====================================================================

function Detect-WorkerProcess {
Write-Log "Detecting worker process..." -Level "INFO"

    # Method 1: Check communication status file
    $commPaths = Initialize-CommunicationPaths -Paths $paths -IsMonitor
    $statusFile = $commPaths.StatusFile

    if (Test-Path $statusFile) {
        try {
            $status = Read-WorkerStatus -StatusFile $statusFile

            if ($status.Status -ne "NOT_FOUND" -and $status.WorkerPID -gt 0) {
                # Verify the PID is actually running
                if (Is-ProcessRunning -ProcessId $status.WorkerPID -ProcessName "powershell") {
                    Write-Log "Found registered worker (PID: $($status.WorkerPID)) via status file" -Level "SUCCESS"
                    $global:WorkerPID = $status.WorkerPID
                    $global:PythonPID = $status.PythonPID
                    $global:WorkerIsRunning = $true
                    $global:PythonIsRunning = ($status.PythonPID -gt 0) -and (Is-ProcessRunning -ProcessId $status.PythonPID -ProcessName "python")
                    return $true
                }
            }
        } catch {
            Write-Log "Error reading worker status: $_" -Level "WARN"
        }
    }

    # Method 2: Check heartbeat file
    $heartbeatFile = $commPaths.HeartbeatFile
    if ((Test-Path $heartbeatFile) -and (Check-Heartbeat -HeartbeatFile $heartbeatFile)) {
        Write-Log "Worker heartbeat detected" -Level "INFO"
        return $true
    }

    # Method 3: Look for PID file
    $pidFile = Join-Path $commPaths.CommunicationDir "worker_pid.txt"
    if (Test-Path $pidFile) {
        try {
            $workerPID = Get-Content $pidFile
            if ($workerPID -match '^\d+$' -and (Is-ProcessRunning -ProcessId $workerPID -ProcessName "powershell")) {
                Write-Log "Found worker via PID file (PID: $workerPID)" -Level "SUCCESS"
                $global:WorkerPID = [int]$workerPID
                $global:WorkerIsRunning = $true
                return $true
            }
        } catch {
            # Continue to other methods
        }
    }

    # Method 4: Traditional process scanning
    Write-Log "Scanning for worker processes..." -Level "DEBUG"

    $workerProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.ProcessName -like "*powershell*") -and ($_.Id -ne $PID)
        }

    foreach ($proc in $workerProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.WorkerScript)*") {
                Write-Log "Found worker process via command line scan (PID: $($proc.Id))" -Level "SUCCESS"
                $global:WorkerPID = $proc.Id
                $global:WorkerIsRunning = $true

                # Try to find associated Python process
                $pythonPID = Find-PythonProcess
                if ($pythonPID) {
                    $global:PythonPID = $pythonPID
                    $global:PythonIsRunning = $true
                }

                # Update communication files
                Update-WorkerCommunication -WorkerPID $proc.Id -PythonPID $pythonPID
                return $true
            }
        } catch {
            continue
        }
    }

    Write-Log "No active worker process detected" -Level "INFO"
    return $false

}

function Update-WorkerCommunication {
param(
[int]$WorkerPID,
        [int]$PythonPID = 0
)

    $commPaths = Initialize-CommunicationPaths -Paths $paths -IsMonitor

    try {
        # Update status file
        $status = @{
            Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            Status = "RUNNING"
            WorkerPID = $WorkerPID
            PythonPID = $PythonPID
            Message = "Detected by monitor"
            MonitorDetected = $true
            LastHeartbeat = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        }

        $status | ConvertTo-Json | Out-File $commPaths.StatusFile -Force

        # Create heartbeat if missing
        if (-not (Test-Path $commPaths.HeartbeatFile)) {
            $heartbeat = @{
                Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                ProcessID = $WorkerPID
                Type = "Worker"
            }
            $heartbeat | ConvertTo-Json | Out-File $commPaths.HeartbeatFile -Force
        }

        Write-Log "Updated worker communication files" -Level "DEBUG"
        return $true
    } catch {
        Write-Log "Failed to update worker communication: $_" -Level "ERROR"
        return $false
    }

}

function Send-CommandToWorker {
param(
[string]$Command,
        [string]$CommandFile
)

    try {
        $lockFile = Join-Path (Split-Path $CommandFile) "communication.lock"
        if (Acquire-Lock -LockFile $lockFile) {
            $commandData = @{
                Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                Command = $Command
                MonitorPID = $PID
            }

            $commandData | ConvertTo-Json | Out-File $CommandFile -Force
            Write-Log "Sent command to worker: $Command" -Level "INFO"

            Release-Lock -LockFile $lockFile
            return $true
        }
        return $false
    } catch {
        Write-Log "Failed to send command to worker: $_" -Level "ERROR"
        return $false
    }

}

function Check-WorkerHealth {
$commPaths = Initialize-CommunicationPaths -Paths $global:MonitorPaths -IsMonitor

    # Check heartbeat
    $heartbeatAlive = Check-Heartbeat -HeartbeatFile $commPaths.HeartbeatFile

    # Check if process is still running
    $processAlive = $false
    if ($global:WorkerPID -gt 0) {
        $processAlive = Is-ProcessRunning -ProcessId $global:WorkerPID -ProcessName "powershell"
    }

    # If heartbeat says alive but process is dead, cleanup
    if ($heartbeatAlive -and -not $processAlive) {
        Write-Log "Worker heartbeat active but process not found - cleaning up stale heartbeat" -Level "WARN"
        Remove-Item $commPaths.HeartbeatFile -Force -ErrorAction SilentlyContinue
        return $false
    }

    return $heartbeatAlive -or $processAlive

}

# ====================================================================

# Modified Start-WorkerProcess with communication

# ====================================================================

function Send-StopCommand {
param(
[string]$Reason = "Normal Shutdown",
        [switch]$Force = $false
)

    $commPaths = Initialize-CommunicationPaths -Paths $paths -IsMonitor

    $commandData = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Command = "STOP"
        MonitorPID = $PID
        Action = "StopWorker"
        Parameters = @{
            Reason = $Reason
            Force = $Force
            GracePeriodSeconds = if ($Force) { 5 } else { 30 }
        }
    }

    $lockFile = $commPaths.LockFile
    if (Acquire-Lock -LockFile $lockFile) {
        try {
            $commandData | ConvertTo-Json | Out-File $commPaths.CommandFile -Force
            Write-Log "Sent STOP command to worker: $Reason" -Level "INFO"

            # Wait for acknowledgement if not forcing
            if (-not $Force) {
                Write-Log "Waiting for worker to acknowledge STOP command..." -Level "INFO"
                $maxWait = $commandData.Parameters.GracePeriodSeconds
                $waited = 0

                while ($waited -lt $maxWait) {
                    $status = Read-WorkerStatus -StatusFile $commPaths.StatusFile
                    if ($status.Status -eq "SHUTTING_DOWN" -or $status.Status -eq "STOPPED") {
                        Write-Log "Worker acknowledged STOP command" -Level "SUCCESS"
                        return $true
                    }

                    Start-Sleep -Seconds 2
                    $waited += 2
                }

                Write-Log "Worker did not acknowledge STOP command within $maxWait seconds" -Level "WARN"
            }

            return $true
        } catch {
            Write-Log "Failed to send STOP command: $_" -Level "ERROR"
            return $false
        } finally {
            Release-Lock -LockFile $lockFile
        }
    }

    return $false

}

function Start-WorkerProcess { # Clean up any stale communication files
$commPaths = Initialize-CommunicationPaths -Paths $paths -IsMonitor
if (Test-Path $commPaths.CommunicationDir) {
Get-ChildItem $commPaths.CommunicationDir -Filter "_.txt" -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem $commPaths.CommunicationDir -Filter "_.json" -ErrorAction SilentlyContinue | Remove-Item -Force
}

    Write-Log "Starting face recognition worker with enhanced communication..." -Level "INFO"

    try {
        # Create start signal
        # Send START command via unified CommandFile
        $commandData = @{
            Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            Command = "START"
            MonitorPID = $PID
            Action = "StartWorker"
            Parameters = @{
                WorkerScript = $Script:Config.WorkerScript
                PythonScript = $Script:Config.PythonScript
            }
        }

        $lockFile = $commPaths.LockFile
        if (Acquire-Lock -LockFile $lockFile) {
            try {
                $commandData | ConvertTo-Json | Out-File $commPaths.CommandFile -Force
                Write-Log "Sent START command to worker via CommandFile" -Level "DEBUG"
            } finally {
                Release-Lock -LockFile $lockFile
            }
        }

        # Start the worker process
        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processInfo.FileName = "powershell.exe"
        $processInfo.Arguments = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$($Script:Config.WorkerScript)`""
        )
        $processInfo.UseShellExecute = $false
        $processInfo.RedirectStandardOutput = $false
        $processInfo.CreateNoWindow = $true

        $WorkerProcess = New-Object System.Diagnostics.Process
        $WorkerProcess.StartInfo = $processInfo

        if ($WorkerProcess.Start()) {
            $global:WorkerPID = $WorkerProcess.Id
            $global:WorkerStartTime = Get-Date
            $global:WorkerIsRunning = $true

            Write-Log "Worker process started (PID: $global:WorkerPID)" -Level "SUCCESS"

            # Wait for worker to register
            Write-Log "Waiting for worker registration..." -Level "INFO"
            $maxWait = 30
            $waited = 0

            while ($waited -lt $maxWait) {
                if (Test-Path $commPaths.RegistrationFile) {
                    Write-Log "Worker registered successfully" -Level "SUCCESS"
                    break
                }

                Start-Sleep -Seconds 1
                $waited++

                # Check if process died
                if ($WorkerProcess.HasExited) {
                    Write-Log "Worker process exited unexpectedly" -Level "ERROR"
                    return $false
                }
            }

            # Wait for Python process
            Write-Log "Waiting for Python process..." -Level "INFO"
            $waited = 0

            while ($waited -lt $maxWait) {
                $foundPID = Find-PythonProcess
                if ($foundPID) {
                    $global:PythonPID = $foundPID
                    $global:PythonIsRunning = $true
                    $global:PythonStartTime = Get-Date

                    # Update communication
                    Update-WorkerCommunication -WorkerPID $global:WorkerPID -PythonPID $foundPID

                    Write-Log "Python process found (PID: $global:PythonPID)" -Level "SUCCESS"
                    Save-PIDTracking
                    return $true
                }

                Start-Sleep -Seconds 2
                $waited += 2
            }

            Write-Log "Python process did not start within $maxWait seconds" -Level "WARN"
            Save-PIDTracking
            return $true
        } else {
            Write-Log "Failed to start worker process" -Level "ERROR"
            return $false
        }
    } catch {
        Write-Log "ERROR starting worker: $_" -Level "ERROR"
        return $false
    }

}

function Stop-WorkerProcess {
$stoppedProcesses = @()
$stopReason = "Normal Shutdown"
$wasUnexpected = $false

    # Determine if this is an unexpected stop
    if ($global:IsShuttingDown -and $global:ForceStopAttempts -ge $global:ForceStopThreshold) {
        $stopReason = "Force Stop by User"
        $wasUnexpected = $true
    } elseif (-not $global:IsShuttingDown -and ($global:PythonIsRunning -or $global:WorkerIsRunning)) {
        $stopReason = "Unexpected Process Stop"
        $wasUnexpected = $true
    }

    Write-Log "Stopping worker process. Reason: $stopReason" -Level "INFO"

    # First, Send STOP command to worker first
    if ($global:WorkerIsRunning -and (-not $wasUnexpected)) {
        $forceStop = ($stopReason -eq "Force Stop by User")
        $commandSent = Send-StopCommand -Reason $stopReason -Force:$forceStop

        if ($commandSent -and (-not $forceStop)) {
            # Give worker time to shut down gracefully
            Write-Log "Waiting for graceful shutdown..." -Level "INFO"
            Start-Sleep -Seconds 10

            # Check if worker already stopped
            $status = Check-ProcessStatus
            if (-not $status.WorkerRunning) {
                Write-Log "Worker shut down gracefully after STOP command" -Level "SUCCESS"
                return
            }
        }
    }

    # ADD THIS SECTION: Stop worker PowerShell process
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        Write-Log "Stopping worker process (PID: $global:WorkerPID)..." -Level "INFO"

        try {
            $workerProcess = Get-Process -Id $global:WorkerPID -ErrorAction Stop

            if (-not $workerProcess.HasExited) {
                $workerProcess.CloseMainWindow() | Out-Null
                Start-Sleep -Seconds 2

                if (-not $workerProcess.HasExited) {
                    Write-Log "Forcefully terminating worker process..." -Level "WARN"
                    $workerProcess.Kill()
                    if ($workerProcess.WaitForExit($Script:Config.GracefulShutdownTimeout * 1000)) {
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
        } catch {
            Write-Log "Error stopping worker process: $_" -Level "ERROR"
        }
    }

    # Then, try to stop the Python process
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        Write-Log "Stopping Python process (PID: $global:PythonPID)..." -Level "INFO"

        try {
            $pythonProcess = Get-Process -Id $global:PythonPID -ErrorAction Stop

            if (-not $pythonProcess.HasExited) {
                $pythonProcess.CloseMainWindow() | Out-Null
                Start-Sleep -Seconds 2

                if (-not $pythonProcess.HasExited) {
                    Write-Log "Forcefully terminating Python process..." -Level "WARN"
                    $pythonProcess.Kill()
                    if ($pythonProcess.WaitForExit($Script:Config.GracefulShutdownTimeout * 1000)) {
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
        } catch {
            Write-Log "Error stopping Python process: $_" -Level "ERROR"
        }
    }


    # Clean up variables
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false

    # Remove PID tracking file
    if (Test-Path $Script:Config.PIDFilePath) {
        Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        Write-Log "Removed PID tracking file" -Level "DEBUG"
    }

    if ($stoppedProcesses.Count -gt 0) {
        Write-Log "Stopped processes: $($stoppedProcesses -join ', ')" -Level "INFO"
    }

}

# ====================================================================

# ENHANCED: Sudden Termination Handling Functions (from old version)

# ====================================================================

function Register-SuddenTermination {
param(
[string]$Reason,
        [string]$TerminationType = "Unexpected",
[hashtable]$ProcessInfo = @{}
)

    $eventHost = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Reason = $Reason
        TerminationType = $TerminationType
        ProcessInfo = $ProcessInfo
        ScriptVersion = "2.1"
        HostName = $env:COMPUTERNAME
    }

    # Add to events list
    $global:SuddenTerminationTracking.Events += $eventHost

    # Update statistics
    $global:SuddenTerminationTracking.Statistics.TotalSuddenTerminations++
    $global:SuddenTerminationTracking.Statistics.LastEventDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    if (-not $global:SuddenTerminationTracking.Statistics.FirstEventDate) {
        $global:SuddenTerminationTracking.Statistics.FirstEventDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }

    # Calculate streak
    if ($global:SuddenTerminationTracking.Events.Count -gt 1) {
        $lastEvent = $global:SuddenTerminationTracking.Events[-2]
        $lastEventTime = [DateTime]::ParseExact($lastEvent.Timestamp, "yyyy-MM-dd HH:mm:ss", $null)
        $currentTime = Get-Date

        if (($currentTime - $lastEventTime).TotalMinutes -le 5) {
            $global:SuddenTerminationTracking.CurrentStreak++
            Write-Log "Consecutive sudden termination detected. Streak: $($global:SuddenTerminationTracking.CurrentStreak)" -Level "WARN"
        } else {
            $global:SuddenTerminationTracking.CurrentStreak = 1
        }
    } else {
        $global:SuddenTerminationTracking.CurrentStreak = 1
    }

    # Check if we need to take action
    if ($global:SuddenTerminationTracking.CurrentStreak -ge $Script:Config.SuddenTermination.ConsecutiveThreshold) {
        Write-Log "Sudden termination streak threshold reached ($($global:SuddenTerminationTracking.CurrentStreak) consecutive). Taking cleanup action." -Level "ERROR"
        Invoke-StreakThresholdAction
    }

    # Save tracking data
    Save-SuddenTerminationTracking

    return $eventHost

}

function Save-SuddenTerminationTracking {
try { # Clean up old events beyond retention period
$retentionDate = (Get-Date).AddDays(-$Script:Config.SuddenTermination.RecordRetentionDays)
$filteredEvents = @()

        foreach ($eventHost in $global:SuddenTerminationTracking.Events) {
            $eventHostTime = [DateTime]::ParseExact($eventHost.Timestamp, "yyyy-MM-dd HH:mm:ss", $null)
            if ($eventHostTime -ge $retentionDate) {
                $filteredEvents += $eventHost
            }
        }

        $global:SuddenTerminationTracking.Events = $filteredEvents

        # Save to file
        if ($Script:Config.SuddenTermination.TrackingFile) {
            $global:SuddenTerminationTracking | ConvertTo-Json -Depth 5 | Out-File -FilePath $Script:Config.SuddenTermination.TrackingFile -Force
            Write-Log "Sudden termination tracking saved" -Level "DEBUG"
        }
    } catch {
        Write-Log "Failed to save sudden termination tracking: $_" -Level "ERROR"
    }

}

function Load-SuddenTerminationTracking {
if (-not $Script:Config.SuddenTermination.TrackingFile -or -not (Test-Path $Script:Config.SuddenTermination.TrackingFile)) {
Write-Log "No sudden termination tracking file found" -Level "DEBUG"
return $false
}

    try {
        $loaded = Get-Content -Path $Script:Config.SuddenTermination.TrackingFile -Raw | ConvertFrom-Json

        $global:SuddenTerminationTracking = @{
            Events = @($loaded.Events)
            CurrentStreak = $loaded.CurrentStreak
            LastCleanupDate = $loaded.LastCleanupDate
            Statistics = @{
                TotalSuddenTerminations = $loaded.Statistics.TotalSuddenTerminations
                TotalCleanups = $loaded.Statistics.TotalCleanups
                LastCleanupReason = $loaded.Statistics.LastCleanupReason
                FirstEventDate = $loaded.Statistics.FirstEventDate
                LastEventDate = $loaded.Statistics.LastEventDate
            }
        }

        Write-Log "Loaded sudden termination tracking: $($global:SuddenTerminationTracking.Statistics.TotalSuddenTerminations) total events" -Level "INFO"
        return $true
    } catch {
        Write-Log "Failed to load sudden termination tracking: $_" -Level "ERROR"
        return $false
    }

}

function Invoke-StreakThresholdAction {
$action = $Script:Config.SuddenTermination.CleanupAction
$streak = $global:SuddenTerminationTracking.CurrentStreak

    Write-Log "Executing cleanup action '$action' for streak of $streak consecutive sudden terminations" -Level "WARN"

    switch ($action) {
        "ForceCleanupAndNotify" {
            Force-CleanupOrphanedProcesses

            $global:SuddenTerminationTracking.Statistics.TotalCleanups++
            $global:SuddenTerminationTracking.Statistics.LastCleanupReason = "ConsecutiveSuddenTerminations"
            $global:SuddenTerminationTracking.LastCleanupDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

            $global:SuddenTerminationTracking.CurrentStreak = 0

            Save-SuddenTerminationTracking
        }
        default {
            Write-Log "Unknown cleanup action: $action" -Level "ERROR"
        }
    }

}

function Force-CleanupOrphanedProcesses {
Write-Log "Starting forced cleanup of orphaned processes..." -Level "WARN"

    $cleanedProcesses = @()

    # Clean up Python processes
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*python*" }

    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.PythonScript)*") {
                Write-Log "Forcefully terminating orphaned Python process (PID: $($proc.Id))" -Level "WARN"
                $proc.Kill()
                if ($proc.WaitForExit(5000)) {
                    $cleanedProcesses += "Python:$($proc.Id)"
                }
            }
        } catch { }
    }

    # Clean up worker PowerShell processes
    $workerProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "*powershell*" }

    foreach ($proc in $workerProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.WorkerScript)*") {
                Write-Log "Forcefully terminating orphaned worker process (PID: $($proc.Id))" -Level "WARN"
                $proc.Kill()
                if ($proc.WaitForExit(5000)) {
                    $cleanedProcesses += "Worker:$($proc.Id)"
                }
            }
        } catch { }
    }

    # Clean up PID tracking file
    if ($Script:Config.PIDFilePath -and (Test-Path $Script:Config.PIDFilePath)) {
        Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        Write-Log "Cleaned up PID tracking file" -Level "INFO"
    }

    # Reset global process variables
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false

    Write-Log "Forced cleanup completed. Cleaned processes: $($cleanedProcesses.Count)" -Level "INFO"

    return $cleanedProcesses

}

function Initialize-CleanupOnStartup {
Write-Log "Performing startup cleanup check..." -Level "INFO"

    Load-SuddenTerminationTracking

    $orphanedProcesses = @()

    # Check Python processes
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*python*" }

    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.PythonScript)*") {
                $orphanedProcesses += @{
                    Type = "Python"
                    PID = $proc.Id
                    StartTime = $proc.StartTime
                }
            }
        } catch { }
    }

    # Check worker processes
    $workerProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "*powershell*" }

    foreach ($proc in $workerProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.WorkerScript)*") {
                $orphanedProcesses += @{
                    Type = "Worker"
                    PID = $proc.Id
                    StartTime = $proc.StartTime
                }
            }
        } catch { }
    }

    if ($orphanedProcesses.Count -gt 0) {
        Write-Log "Found $($orphanedProcesses.Count) orphaned process(es) from previous run" -Level "WARN"

        foreach ($orphan in $orphanedProcesses) {
            Write-Log "  - $($orphan.Type) process (PID: $($orphan.PID), Started: $($orphan.StartTime))" -Level "WARN"
        }

        Register-SuddenTermination -Reason "Orphaned processes found on startup" `
            -TerminationType "StartupCleanup" `
            -ProcessInfo @{ OrphanedProcesses = $orphanedProcesses }

        Force-CleanupOrphanedProcesses
        return $true
    }

    Write-Log "No orphaned processes found on startup" -Level "INFO"
    return $false

}

function Clean-StalePIDFiles {
if ($Script:Config.PIDFilePath -and (Test-Path $Script:Config.PIDFilePath)) {
try {
$pidData = Get-Content $Script:Config.PIDFilePath -Raw | ConvertFrom-Json

            # Check if processes are still running
            $processesExist = $true
            if ($pidData.WorkerPID) {
                try {
                    Get-Process -Id $pidData.WorkerPID -ErrorAction Stop | Out-Null
                } catch {
                    $processesExist = $false
                    Write-Log "Stale worker PID found: $($pidData.WorkerPID)" -Level "WARN"
                }
            }

            if ($pidData.PythonPID) {
                try {
                    Get-Process -Id $pidData.PythonPID -ErrorAction Stop | Out-Null
                } catch {
                    $processesExist = $false
                    Write-Log "Stale Python PID found: $($pidData.PythonPID)" -Level "WARN"
                }
            }

            if (-not $processesExist) {
                Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
                Write-Log "Removed stale PID tracking file" -Level "INFO"
                return $true
            }
        } catch {
            # If PID file is corrupted, remove it
            Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            Write-Log "Removed corrupted PID tracking file" -Level "WARN"
            return $true
        }
    }
    return $false

}

function Handle-UnexpectedProcessStop { # Collect any incomplete run data
if ($global:CurrentRunFolder -and (Test-Path $global:CurrentRunFolder)) {
Write-Log "Collecting data from incomplete run: $(Split-Path $global:CurrentRunFolder -Leaf)" -Level "WARN"

        # Check for completion summary
        $completionPath = Join-Path $global:CurrentRunFolder "Magick_Process_*\logs\completion_summary.txt"
        if (Test-Path $completionPath) {
            $runData = @{
                RunFolder = $global:CurrentRunFolder
                RunFolderName = Split-Path $global:CurrentRunFolder -Leaf
                Attachments = @($completionPath)
                CollectionTime = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            }

            $global:CollectedRunFolders += $runData
            Write-Log "Collected incomplete run data" -Level "INFO"
        }
    }

}

# ====================================================================

# ENHANCED: PID Tracking with persistent data (from old version)

# ====================================================================

function Save-PIDTracking {
$workerStartString = if ($global:WorkerStartTime -and ($global:WorkerStartTime -is [DateTime])) {
$global:WorkerStartTime.ToString("yyyy-MM-dd HH:mm:ss")
} else {
$null
}

    $pythonStartString = if ($global:PythonStartTime -and ($global:PythonStartTime -is [DateTime])) {
        $global:PythonStartTime.ToString("yyyy-MM-dd HH:mm:ss")
    } else {
        $null
    }

    $PIDTracking = @{
        WorkerPID = $global:WorkerPID
        PythonPID = $global:PythonPID
        WorkerStartTime = $workerStartString
        PythonStartTime = $pythonStartString
        RunFolder = $global:CurrentRunFolder
        LastUpdate = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        EmailQueue = $global:EmailAttachmentQueue
        CollectedFolders = $global:CollectedRunFolders
        ShutdownInitiated = $global:IsShuttingDown
        PersistentTracking = $global:PersistentTracking
    }

    try {
        if ($Script:Config.PIDFilePath) {
            $PIDTracking | ConvertTo-Json -Depth 10 | Out-File -FilePath $Script:Config.PIDFilePath -Force
            Write-Log "PID tracking saved with $($global:CollectedRunFolders.Count) collected folders" -Level "DEBUG"
        }

        # Also save persistent tracking separately
        Save-PersistentTracking
    } catch {
        Write-Log "Failed to save PID tracking: $_" -Level "ERROR"
    }

}

function Load-PIDTracking {
if (-not $Script:Config.PIDFilePath -or -not (Test-Path $Script:Config.PIDFilePath)) {
Write-Log "No PID tracking file found" -Level "DEBUG"
Load-PersistentTracking
return $false
}

    try {
        $loaded = Get-Content -Path $Script:Config.PIDFilePath -Raw | ConvertFrom-Json

        # Check if PID file is too old
        $lastUpdate = [DateTime]::ParseExact($loaded.LastUpdate, "yyyy-MM-dd HH:mm:ss", $null)
        $ageMinutes = ((Get-Date) - $lastUpdate).TotalMinutes

        if ($ageMinutes -gt $Script:Config.MaxPIDFileAgeMinutes) {
            Write-Log "PID file is too old ($ageMinutes minutes), cleaning up" -Level "WARN"
            Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            return $false
        }

        # Load the data
        $global:WorkerPID = $loaded.WorkerPID
        $global:PythonPID = $loaded.PythonPID

        if ($loaded.WorkerStartTime) {
            try {
                $global:WorkerStartTime = [DateTime]::ParseExact($loaded.WorkerStartTime, "yyyy-MM-dd HH:mm:ss", $null)
            } catch {
                $global:WorkerStartTime = $null
            }
        }

        if ($loaded.PythonStartTime) {
            try {
                $global:PythonStartTime = [DateTime]::ParseExact($loaded.PythonStartTime, "yyyy-MM-dd HH:mm:ss", $null)
            } catch {
                $global:PythonStartTime = $null
            }
        }

        $global:CurrentRunFolder = $loaded.RunFolder
        $global:EmailAttachmentQueue = @($loaded.EmailQueue)
        $global:CollectedRunFolders = @($loaded.CollectedFolders)
        $global:IsShuttingDown = $loaded.ShutdownInitiated

        if ($loaded.PersistentTracking) {
            $global:PersistentTracking = $loaded.PersistentTracking
        }

        Write-Log "PID tracking loaded: WorkerPID=$global:WorkerPID, PythonPID=$global:PythonPID" -Level "INFO"
        return $true
    } catch {
        Write-Log "Failed to load PID tracking: $_" -Level "ERROR"
        Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        return $false
    }

}

function Save-PersistentTracking { # FIXED: Ensure LogFile path exists before splitting
if (-not $Script:Config.LogFile) {
Write-Log "Cannot save persistent tracking: LogFile path is null" -Level "ERROR"
return $false
}

    $logDir = Split-Path $Script:Config.LogFile -Parent
    if (-not $logDir) {
        Write-Log "Cannot save persistent tracking: Unable to determine log directory" -Level "ERROR"
        return $false
    }

    $persistentFilePath = Join-Path $logDir "persistent_tracking.json"

    # Update persistent tracking data
    $global:PersistentTracking.LastKnownRunFolder = $global:CurrentRunFolder
    $global:PersistentTracking.LastKnownPythonPID = $global:PythonPID
    $global:PersistentTracking.LastKnownWorkerPID = $global:WorkerPID
    $global:PersistentTracking.LastValidationTime = if ($global:LastValidation) { (Get-Date).ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
    $global:PersistentTracking.LastValidationResult = if ($global:LastValidation) { @{ Success = $global:LastValidation.Success; FolderName = $global:LastValidation.FolderName } } else { $null }
    $global:PersistentTracking.CollectedRunFolders = $global:CollectedRunFolders

    try {
        $global:PersistentTracking | ConvertTo-Json -Depth 10 | Out-File -FilePath $persistentFilePath -Force
        Write-Log "Persistent tracking saved" -Level "DEBUG"
        return $true
    } catch {
        Write-Log "Failed to save persistent tracking: $_" -Level "ERROR"
        return $false
    }

}

function Load-PersistentTracking { # FIXED: Ensure LogFile path exists before splitting
if (-not $Script:Config.LogFile) {
Write-Log "Cannot load persistent tracking: LogFile path is null" -Level "ERROR"
return $false
}

    $logDir = Split-Path $Script:Config.LogFile -Parent
    if (-not $logDir) {
        return $false
    }

    $persistentFilePath = Join-Path $logDir "persistent_tracking.json"

    if (Test-Path $persistentFilePath) {
        try {
            $loadedData = Get-Content -Path $persistentFilePath -Raw | ConvertFrom-Json

            $global:PersistentTracking = @{
                LastKnownRunFolder = $loadedData.LastKnownRunFolder
                LastKnownPythonPID = $loadedData.LastKnownPythonPID
                LastKnownWorkerPID = $loadedData.LastKnownWorkerPID
                LastValidationTime = $loadedData.LastValidationTime
                LastValidationResult = $loadedData.LastValidationResult
                ProcessStopHistory = @($loadedData.ProcessStopHistory)
                ValidationHistory = @($loadedData.ValidationHistory)
                DailyRunCount = $loadedData.DailyRunCount
                LastSuccessfulRun = $loadedData.LastSuccessfulRun
                CollectedRunFolders = @($loadedData.CollectedRunFolders)
            }

            $global:CollectedRunFolders = @($loadedData.CollectedRunFolders)

            Write-Log "Loaded persistent tracking with $($global:PersistentTracking.CollectedRunFolders.Count) collected folders" -Level "INFO"
            return $true
        } catch {
            Write-Log "Failed to load persistent tracking: $_" -Level "ERROR"
            return $false
        }
    }

    return $false

}

# ====================================================================

# ENHANCED: Validation and Folder Functions (improved)

# ====================================================================

function Find-LatestRunFolder {
try {
if (-not $Script:Config.RunsBasePath -or -not (Test-Path $Script:Config.RunsBasePath)) {
return $null
}

        $folders = Get-ChildItem -Path $Script:Config.RunsBasePath -Directory -Filter $Script:Config.OutputFolderPattern -ErrorAction SilentlyContinue

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

    $runFolder = Find-LatestRunFolder

    if (-not $runFolder) {
        if ($RetryCount -lt $Script:Config.MaxValidationRetries) {
            Write-Log "No output folder found. Retrying..." -Level "WARN"
            Start-Sleep -Seconds $Script:Config.RetryDelaySeconds
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

    $global:CurrentRunFolder = $runFolder.FullName

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

    # Check subfolders
    foreach ($item in $Script:Config.ExpectedSubfolders) {
        $itemPath = Join-Path $runFolder.FullName $item
        if (-not (Test-Path $itemPath)) {
            $validationResult.MissingItems += $item
            $validationResult.Success = $false
            Write-Log "Missing expected subfolder: $item" -Level "WARN"
        }
    }

    # Check files
    foreach ($item in $Script:Config.ExpectedFiles) {
        $itemPath = Join-Path $runFolder.FullName $item
        if (-not (Test-Path $itemPath)) {
            $validationResult.MissingItems += $item
            $validationResult.Success = $false
            Write-Log "Missing expected file: $item" -Level "WARN"
        } elseif ($item -eq "metadata.json") {
            try {
                $metadataContent = Get-Content $itemPath -Raw | ConvertFrom-Json
                $validationResult.Details["metadata"] = @{
                    RunID = $metadataContent.run_id
                    StartTime = $metadataContent.start_time
                    ExitCode = $metadataContent.exit_code
                }
            } catch {
                $validationResult.Errors += $item + ": Invalid JSON format"
                $validationResult.Success = $false
            }
        }
    }

    # Summary
    if ($validationResult.Success) {
        Write-Log "VALIDATION SUCCESS: Folder structure complete" -Level "SUCCESS"
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

# ====================================================================

# ENHANCED: Status Display (improved from old version)

# ====================================================================

function Show-StatusBanner {
$currentSecond = (Get-Date).Second
    if ($currentSecond % 20 -ne 0) {
return
}

    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "    ENHANCED FACE RECOGNITION PROCESS MONITOR" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Current Date: $(Get-Date -Format 'yyyy-MM-dd')" -ForegroundColor Yellow
    Write-Host "Current Time: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Yellow
    Write-Host "Schedule: $($Script:Config.StartTime) - $($Script:Config.EndTime)" -ForegroundColor Yellow

    $processStatus = Check-ProcessStatus

    if ($processStatus.PythonRunning) {
        Write-Host "PYTHON STATUS: RUNNING" -ForegroundColor Green
        Write-Host "  PID: $($global:PythonPID)" -ForegroundColor White
    } else {
        Write-Host "PYTHON STATUS: STOPPED" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "WORKER STATUS: $(if ($processStatus.WorkerRunning) {'RUNNING'} else {'STOPPED'})" -ForegroundColor $(if ($processStatus.WorkerRunning) {'Green'} else {'Red'})

    # Show sudden termination streak if any
    if ($global:SuddenTerminationTracking.CurrentStreak -gt 0) {
        Write-Host ""
        Write-Host "Sudden Termination Streak: $($global:SuddenTerminationTracking.CurrentStreak)" -ForegroundColor $(if ($global:SuddenTerminationTracking.CurrentStreak -ge $Script:Config.SuddenTermination.ConsecutiveThreshold) { 'Red' } else { 'Yellow' })
    }

    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan

}

# ====================================================================

# ENHANCED: Console Control Handler (from old version)

# ====================================================================

function Register-ConsoleControlHandler {
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

    public class ConsoleCtrlHandler {
        public delegate bool ConsoleEventDelegate(int eventType);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool SetConsoleCtrlHandler(ConsoleEventDelegate handler, bool add);

        public const int CTRL_C_EVENT = 0;
        public const int CTRL_BREAK_EVENT = 1;
        public const int CTRL_CLOSE_EVENT = 2;
        public const int CTRL_LOGOFF_EVENT = 5;
        public const int CTRL_SHUTDOWN_EVENT = 6;
    }

"@

    $handler = [ConsoleCtrlHandler+ConsoleEventDelegate]{
        param([int]$eventHostType)

        $currentTime = Get-Date
        $timeSinceLast = if ($global:LastForceStopTime) {
            ($currentTime - $global:LastForceStopTime).TotalSeconds
        } else {
            [double]::MaxValue
        }

        switch ($eventHostType) {
            { $_ -in 0, 1 } {
                Write-Host "`n[Console Control Handler] Control event detected" -ForegroundColor Yellow

                if ($timeSinceLast -lt $global:ForceStopWindowSeconds) {
                    $global:ForceStopAttempts++
                    Write-Host "  Rapid attempt detected ($global:ForceStopAttempts/$global:ForceStopThreshold)" -ForegroundColor Yellow
                } else {
                    $global:ForceStopAttempts = 1
                }

                $global:LastForceStopTime = $currentTime

                if ($global:ForceStopAttempts -ge $global:ForceStopThreshold) {
                    Write-Host "  Force shutdown requested by user" -ForegroundColor Red
                    $global:IsShuttingDown = $true
                    return $true
                } else {
                    Write-Host "  Monitor will continue until end time. Press Ctrl+C again within $($global:ForceStopWindowSeconds)s to force stop." -ForegroundColor Yellow
                    Write-Log "Ctrl+C intercepted - monitor will continue until end time. Attempts: $global:ForceStopAttempts/$global:ForceStopThreshold" -Level "WARN"
                    return $true
                }
            }
            default {
                return $false
            }
        }
    }

    [void][ConsoleCtrlHandler]::SetConsoleCtrlHandler($handler, $true)
    Write-Log "Console control handler registered" -Level "DEBUG"

}
function Write-WorkerStatus {
param(
[string]$StatusFile,
        [string]$Status,
[int]$WorkerPID,
        [int]$PythonPID = 0,
[string]$Message = "",
        [string]$RunFolder = ""
)

    $statusData = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Status = $Status
        WorkerPID = $WorkerPID
        PythonPID = $PythonPID
        Message = $Message
        RunFolder = $RunFolder
        MonitorDetected = $false
        LastHeartbeat = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }

    try {
        $statusData | ConvertTo-Json | Out-File $StatusFile -Force
        return $true
    } catch {
        Write-WorkerLog "Failed to write worker status: $_" -Level "ERROR"
        return $false
    }

}

# ====================================================================

# MAIN EXECUTION - UPDATED WITH OLD VERSION'S RELIABILITY

# ====================================================================

try { # Create log directory if it doesn't exist
if ($Script:Config.LogFile) {
$logDir = Split-Path $Script:Config.LogFile -Parent
if (-not (Test-Path $logDir)) {
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
}

    Write-Log "=== Enhanced Face Recognition Monitor Started ===" -Level "INFO"
    Write-Log "Version: 2.1 (Updated with old version's process checking)" -Level "INFO"
    Write-Log "Start Time: $($Script:Config.StartTime)" -Level "INFO"
    Write-Log "End Time: $($Script:Config.EndTime)" -Level "INFO"
    Write-Log "Log File: $($Script:Config.LogFile)" -Level "INFO"

    # Ensure runs base path exists
    if ($Script:Config.RunsBasePath -and -not (Test-Path $Script:Config.RunsBasePath)) {
        Write-Log "Creating runs base directory" -Level "WARN"
        New-Item -ItemType Directory -Path $Script:Config.RunsBasePath -Force | Out-Null
    }

    # Clear console for clean display
    #Clear-Host

    # Main monitoring loop with OLD VERSION'S reliability
    Write-Log "Entering enhanced monitoring loop..." -Level "INFO"

    # Initialize monitoring loop variables
    $monitoringActive = $true

    while ($monitoringActive) {
        try {
            # OLD VERSION'S PROCESS CHECKING LOGIC
            $processStatus = Check-ProcessStatus

            $startPassed = Test-TimeWindow -TargetTime $Script:Config.StartTime
            $endPassed = Test-TimeWindow -TargetTime $Script:Config.EndTime

            # FIXED: Correct syntax for boolean condition
            if ($startPassed -and (-not $endPassed)) {
                $inWindow = $true
            } else {
                $inWindow = $false
            }

            $currentTime = Get-Date -Format "HH:mm:ss"

            # Show status banner every 10 seconds
            $currentSecond = (Get-Date).Second
            if ($currentSecond % 10 -eq 0) {
                #Clear-Host
                Write-Host "================================================" -ForegroundColor Cyan
                Write-Host "    ENHANCED FACE RECOGNITION PROCESS MONITOR" -ForegroundColor Cyan
                Write-Host "================================================" -ForegroundColor Cyan
                Write-Host "Current Time: $currentTime" -ForegroundColor Yellow
                Write-Host "Schedule: $($Script:Config.StartTime) - $($Script:Config.EndTime)" -ForegroundColor Yellow
                Write-Host "Status: $(if ($inWindow) {'ACTIVE WINDOW'} else {'OUTSIDE WINDOW'})" -ForegroundColor $(if ($inWindow) {'Green'} else {'Yellow'})
                Write-Host ""

                if ($processStatus.PythonRunning) {
                    Write-Host "PYTHON STATUS: RUNNING" -ForegroundColor Green
                    Write-Host "  PID: $($global:PythonPID)" -ForegroundColor White
                    Write-Host "  Detected via: $(if ($processStatus.UsingCommunication) {'Communication'} else {'Process Scan'})" -ForegroundColor Gray
                } else {
                    Write-Host "PYTHON STATUS: STOPPED" -ForegroundColor Red
                }

                Write-Host ""
                Write-Host "WORKER STATUS: $(if ($processStatus.WorkerRunning) {'RUNNING'} else {'STOPPED'})" -ForegroundColor $(if ($processStatus.WorkerRunning) {'Green'} else {'Red'})
                if ($processStatus.WorkerRunning) {
                    Write-Host "  PID: $($global:WorkerPID)" -ForegroundColor White
                }

                # Show sudden termination streak if any
                if ($global:SuddenTerminationTracking.CurrentStreak -gt 0) {
                    Write-Host ""
                    Write-Host "Sudden Termination Streak: $($global:SuddenTerminationTracking.CurrentStreak)" -ForegroundColor $(if ($global:SuddenTerminationTracking.CurrentStreak -ge $Script:Config.SuddenTermination.ConsecutiveThreshold) { 'Red' } else { 'Yellow' })
                }

                Write-Host ""
                Write-Host "Communication: $(if (Test-Path (Initialize-CommunicationPaths -Paths $paths -IsMonitor).StatusFile) {'ACTIVE'} else {'INACTIVE'})" -ForegroundColor Gray
                Write-Host "================================================" -ForegroundColor Cyan
            }

            Write-Log "Check: $currentTime | Window: $(if ($inWindow) {'Active'} else {'Inactive'}) | Worker: $(if ($processStatus.WorkerRunning) {'Running'} else {'Stopped'}) | Python: $(if ($processStatus.PythonRunning) {'Running'} else {'Stopped'})" -Level "DEBUG"

            # OLD VERSION'S LOGIC: Check if we should start worker
            if ($inWindow -and (-not $processStatus.PythonRunning)) {
                Write-Log "Time window active and no Python process running - starting worker..." -Level "INFO"

                if ($global:LastWorkerAttempt -and ((Get-Date) - $global:LastWorkerAttempt).TotalSeconds -lt 60) {
                    Write-Log "Skipping worker start - too soon after last attempt" -Level "DEBUG"
                } else {
                    $started = Start-WorkerProcess
                    $global:LastWorkerAttempt = Get-Date

                    if ($started) {
                        Write-Log "Worker started. Monitoring Python process..." -Level "SUCCESS"
                    } else {
                        Write-Log "Failed to start worker process" -Level "ERROR"
                    }
                }
            }

            # OLD VERSION'S LOGIC: Handle end time
            elseif ($endPassed) {
                Write-Log "End time reached - initiating shutdown sequence..." -Level "INFO"

                if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
                    Write-Log "Stopping running processes..." -Level "INFO"
                    Stop-WorkerProcess
                    Start-Sleep -Seconds 5
                }

                # Validate the last output
                Write-Log "Validating final worker output..." -Level "INFO"
                $global:LastValidation = Validate-Output

                if ($global:LastValidation.Success) {
                    Write-Log "Validation successful. Run folder: $($global:LastValidation.FolderName)" -Level "SUCCESS"
                } else {
                    Write-Log "Validation failed: $($global:LastValidation.Error)" -Level "ERROR"
                }

                Write-Log "Daily process completed. Stopping monitor..." -Level "INFO"
                $monitoringActive = $false
                break
            }

            # If we're in the window and processes should be running, verify health
            if ($inWindow -and $processStatus.WorkerRunning) {
                # Send periodic heartbeat request to worker
                $commPaths = Initialize-CommunicationPaths -Paths $paths -IsMonitor
                if ((Get-Date).Second % 15 -eq 0) {
                    $workerHealth = Check-WorkerHealth
                    if (-not $workerHealth) {
                        Write-Log "Worker health check failed. Attempting to restart..." -Level "WARN"
                        Stop-WorkerProcess
                        Start-Sleep -Seconds 2
                        Start-WorkerProcess
                    }
                }
            }

            Start-Sleep -Seconds $Script:Config.ProcessCheckInterval

        } catch {
            Write-Log "Error in main loop: $_" -Level "ERROR"
            Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
            Start-Sleep -Seconds $Script:Config.ProcessCheckInterval
        }
    }

}
catch {
Write-Log "FATAL ERROR: $_" -Level "ERROR"
    Write-Log "Stack trace: $($\_.ScriptStackTrace)" -Level "DEBUG"

    # Register sudden termination
    $errorInfo = @{
        ErrorMessage = $_.Exception.Message
        ErrorType = $_.Exception.GetType().Name
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }

    Register-SuddenTermination -Reason "Fatal error in monitor main loop: $_" `
        -TerminationType "Fatal" `
        -ProcessInfo $errorInfo

}
finally {
Write-Log "Cleaning up..." -Level "INFO"

    # Stop any running processes
    Stop-WorkerProcess

    # Save final state
    Save-SuddenTerminationTracking
    Save-PersistentTracking

    Write-Log "=== Enhanced Face Recognition Monitor Stopped ===" -Level "INFO"

    # Final console output
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "MONITOR STOPPED" -ForegroundColor Yellow
    Write-Host "================================================" -ForegroundColor Cyan

    if ($Script:Config.LogFile) {
        Write-Host "Log file: $($Script:Config.LogFile)" -ForegroundColor White
    }

    if ($global:LastValidation) {
        if ($global:LastValidation.Success) {
            Write-Host "Last run validation: SUCCESS" -ForegroundColor Green
            Write-Host "  Folder: $($global:LastValidation.FolderName)" -ForegroundColor White
        } else {
            Write-Host "Last run validation: FAILED" -ForegroundColor Red
            Write-Host "  Error: $($global:LastValidation.Error)" -ForegroundColor White
        }
    }

    Write-Host "Collected runs: $($global:CollectedRunFolders.Count)" -ForegroundColor White
    Write-Host "Sudden terminations: $($global:SuddenTerminationTracking.Statistics.TotalSuddenTerminations)" -ForegroundColor $(if ($global:SuddenTerminationTracking.Statistics.TotalSuddenTerminations -gt 0) { 'Yellow' } else { 'White' })
    Write-Host "================================================" -ForegroundColor Cyan

}

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

$commonPathsScript = Join-Path $PSScriptRoot "1*common-paths.ps1"
if (Test-Path $commonPathsScript) {
try {
. $commonPathsScript
Write-Host "✓ Common paths module loaded" -ForegroundColor Green
} catch {
Write-Host "ERROR: Failed to load common paths: $*" -ForegroundColor Red
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
Write-WorkerLog "Worker process started (PID: $global:WorkerPID)" -Level "INFO" # Changed from Write-Log

# ====================================================================

# ENHANCED: Configuration for worker

# ====================================================================

$Script:WorkerConfig = @{ # Python parameters
PythonParams = @{ # "--database" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\current_database-Copy" # "--input" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\process-run\Run_Classified2026-01-21_15-11-08\script_output\classified_output"
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

    # Start heartbeat thread
    $heartbeatJob = Start-Job -ScriptBlock {
        param($HeartbeatFile, $WorkerPID)
        while ($true) {
            try {
                $heartbeat = @{
                    Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                    ProcessID = $WorkerPID
                    Type = "Worker"
                }
                $heartbeat | ConvertTo-Json | Out-File $HeartbeatFile -Force
                Start-Sleep -Seconds 5
            } catch {
                # If we can't write heartbeat, exit the job
                break
            }
        }
    } -ArgumentList $global:CommunicationPaths.HeartbeatFile, $global:WorkerPID

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

        $global:PythonPID = $pythonProcess.Id

        # Update status with Python PID
        Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `
            -Status "RUNNING" `
            -WorkerPID $global:WorkerPID `
            -PythonPID $global:PythonPID `
            -Message "Python script running"

        # Monitor loop with heartbeat and command checking
        while (-not $pythonProcess.HasExited) {
            # Send heartbeat via job (already running)

            # Check for monitor commands
            $command = Check-ForMonitorCommand
            if ($command -eq "STOP") {
                Write-WorkerLog "Stopping Python process due to STOP command from monitor" -Level "WARN"

                # Try graceful shutdown first
                if (-not $pythonProcess.HasExited) {
                    $pythonProcess.CloseMainWindow() | Out-Null
                    Start-Sleep -Seconds 2

                    if (-not $pythonProcess.HasExited) {
                        Write-WorkerLog "Forcefully terminating Python process..." -Level "WARN"
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
        # Clean up heartbeat job on error
        Stop-Job $heartbeatJob -ErrorAction SilentlyContinue
        Remove-Job $heartbeatJob -ErrorAction SilentlyContinue
        throw
    } finally {
        # Clean up heartbeat job
        Stop-Job $heartbeatJob -ErrorAction SilentlyContinue
        Remove-Job $heartbeatJob -ErrorAction SilentlyContinue
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

# PORTABLE PATHS USED

Project Root: $ProjectRoot
Active Date Path: $ActiveDatePath
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT
Python Executable: $PYTHON_EXE

# FOLDER STRUCTURE

Run Folder: $RunFolderPath
├── logs\
│   ├── run_$($RunInfo.RunID).log (Main log file)
│ ├── python_output.txt (Full Python script output)
│ └── completion_summary.txt (This summary)
├── script_output\ (Python script's working directory)
│ └── [Output folders created by Python]
└── metadata.json (Run configuration metadata)

# PROCESS INFORMATION

Worker PID: $($RunInfo.WorkerPID)
Python PID: $($RunInfo.PythonPID)

# EXECUTION DETAILS

Start Time: $($StartTime.ToString('yyyy-MM-dd HH:mm:ss'))
End Time: $($EndTime.ToString('yyyy-MM-dd HH:mm:ss'))
Duration: $DurationFormatted
Exit Code: $ExitCode

# ARGUMENTS PASSED

$($PythonArgs | ForEach-Object { " $\_" } | Out-String)

# LOG FILES

1. Main Execution Log: $($RunInfo.MainLogFile)
2. Python Output: $($RunInfo.PythonOutputFile)
3. Worker Log: $($Script:WorkerConfig.WorkerLogFile)

# NOTE: This run uses portable paths that are relative to the project root.

"@

    $completionSummary | Out-File $SummaryPath
    Write-WorkerLog "Created completion summary: $SummaryPath" -Level "INFO"

}

function Register-WorkerWithMonitor {
try { # Write PID file for monitor to detect
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

        # Initial status update
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

                Write-WorkerLog "Received command from monitor: $($commandData.Command)" -Level "INFO"

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
                    "RESTART" {
                        Write-Host "Received RESTART command from monitor" -ForegroundColor Yellow
                        return "RESTART"
                    }
                    "START" {
                        Write-Host "Received START command from monitor" -ForegroundColor Yellow
                        return "START"
                    }
                    "STATUS" {
                        Write-Host "Received STATUS request from monitor" -ForegroundColor Yellow
                        return "STATUS"
                    }
                    default {
                        Write-WorkerLog "Unknown command received: $($commandData.Command)" -Level "WARN"
                        return $null
                    }
                }
            }
        } catch {
            Write-WorkerLog "Error reading monitor command: $_" -Level "ERROR"
        }
    }
    return $null

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
    # exit $executionResult.ExitCode

    # At the end, update status
    Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `
        -Status "COMPLETED" `
        -WorkerPID $global:WorkerPID `
        -PythonPID $global:PythonPID `
        -Message "Worker completed successfully" `
        -RunFolder $folderStructure.RunFolderPath

} catch { # Update status on error
Write-WorkerStatus -StatusFile $global:CommunicationPaths.StatusFile `        -Status "ERROR"`
-WorkerPID $global:WorkerPID `
-Message "Worker error: $\_"

    throw

}

# 1_common-paths.ps1

<#
.SYNOPSIS
Common path initialization module shared by monitor and worker scripts
.DESCRIPTION
Handles portable path discovery and date-based folder creation with enhanced integration
.NOTES
Updated to support both monitor and worker script requirements - STABILIZED VERSION
#>

# ====================================================================

# ENHANCED: Module Configuration - REMOVED Export-ModuleMember

# ====================================================================

$Script:CommonConfig = @{
ProjectName = "maskRecog"
LogBasePath = "logs-running\magick"
DateFormat = "yyyy-MM-dd"
DateTimeFormat = "yyyy-MM-dd_HH-mm-ss"
LogDateTimeFormat = "yyyy-MM-dd HH:mm:ss"
}

# ====================================================================

# ENHANCED: Initialize Project Paths with improved validation

# ====================================================================

function Initialize-ProjectPortablePaths {
[CmdletBinding()]
param(
[switch]$IsMonitor,
        [switch]$IsWorker,
[switch]$Silent = $false
)

    if (-not $Silent) {
        Write-Host "Initializing portable paths for $($Script:CommonConfig.ProjectName) project..." -ForegroundColor Cyan
    }

    # ====================================================================
    # STEP 1: FIND THE PROJECT ROOT (maskRecog directory)
    # ====================================================================

    $projectRoot = Find-ProjectRoot -Silent:$Silent

    if (-not $projectRoot) {
        if (-not $Silent) {
            Write-Host "ERROR: Could not find project root directory '$($Script:CommonConfig.ProjectName)'" -ForegroundColor Red
        }
        throw "Project root directory '$($Script:CommonConfig.ProjectName)' not found"
    }

    # ====================================================================
    # STEP 2: BUILD PATHS RELATIVE TO PROJECT ROOT
    # ====================================================================

    $paths = Build-ProjectPaths -ProjectRoot $projectRoot

    # ====================================================================
    # STEP 3: CREATE DATE-BASED FOLDER STRUCTURE
    # ====================================================================

    $dateBasedPath = Initialize-DateBasedStructure -Paths $paths

    # ====================================================================
    # STEP 4: ADD SCRIPT-SPECIFIC PATHS
    # ====================================================================

    $paths = Add-ScriptSpecificPaths -Paths $paths -DateBasedPath $dateBasedPath -IsMonitor:$IsMonitor -IsWorker:$IsWorker

    # ====================================================================
    # STEP 5: VALIDATE CRITICAL PATHS
    # ====================================================================

    if (-not $Silent) {
        Validate-CriticalPaths -Paths $paths -IsMonitor:$IsMonitor -IsWorker:$IsWorker
    }

    return $paths

}

# ====================================================================

# ENHANCED: Helper Functions - STABILIZED

# ====================================================================

function Find-ProjectRoot {
[CmdletBinding()]
param([switch]$Silent)

    # Method A: Check if we're already IN maskRecog directory
    $scriptPath = $PSScriptRoot
    $currentPath = $scriptPath

    # Look for maskRecog by going UP through parent directories
    while ($currentPath -and (Split-Path $currentPath -Parent)) {
        $currentDirName = Split-Path $currentPath -Leaf

        if ($currentDirName -eq $Script:CommonConfig.ProjectName) {
            if (-not $Silent) {
                Write-Host "Found project root in current path: $currentPath" -ForegroundColor Green
            }
            return $currentPath
        }

        $parentPath = Split-Path $currentPath -Parent
        # Stop if we reach drive root (like D:\) or can't go further
        if (!$parentPath -or $parentPath -eq $currentPath) {
            break
        }
        $currentPath = $parentPath
    }

    # Method B: If not found above, check current directory name
    $currentDir = Get-Location
    if ((Split-Path $currentDir -Leaf) -eq $Script:CommonConfig.ProjectName) {
        if (-not $Silent) {
            Write-Host "Found project root in current directory: $currentDir" -ForegroundColor Green
        }
        return $currentDir
    }

    # Method C: Last resort - ask user
    if (-not $Silent) {
        Write-Host "Could not automatically find '$($Script:CommonConfig.ProjectName)' directory." -ForegroundColor Yellow
        $projectRoot = Read-Host "Please enter the full path to '$($Script:CommonConfig.ProjectName)' project root"

        if (!(Test-Path $projectRoot)) {
            Write-Host "ERROR: Path '$projectRoot' does not exist!" -ForegroundColor Red
            return $null
        }

        if ((Split-Path $projectRoot -Leaf) -ne $Script:CommonConfig.ProjectName) {
            Write-Host "WARNING: Directory name does not match '$($Script:CommonConfig.ProjectName)'" -ForegroundColor Yellow
        }

        return $projectRoot
    }

    return $null

}

function Build-ProjectPaths {
[CmdletBinding()]
param([string]$ProjectRoot)

    # Store project root globally so all functions can use it
    $global:ProjectRoot = $ProjectRoot

    # Calculate ActiveRoot (two levels up from ProjectRoot)
    $global:ActiveRoot = Split-Path $ProjectRoot -Parent | Split-Path -Parent

    # Calculate VenvRoot (four levels up from ProjectRoot)
    $global:VenvRoot = Split-Path $ProjectRoot -Parent | Split-Path -Parent | Split-Path -Parent | Split-Path -Parent

    # Get current date for folder structure
    $currentDate = Get-Date -Format $Script:CommonConfig.DateFormat
    $global:CurrentDateFolder = $currentDate

    return @{
        ProjectRoot = $ProjectRoot
        ActiveRoot = $global:ActiveRoot
        VenvRoot = $global:VenvRoot
        CurrentDate = $currentDate
    }

}

function Initialize-DateBasedStructure {
[CmdletBinding()]
param([hashtable]$Paths)

    # Create the base Magick folder if it doesn't exist
    $magickBasePath = Join-Path $Paths.ActiveRoot $Script:CommonConfig.LogBasePath
    if (-not (Test-Path $magickBasePath)) {
        try {
            New-Item -ItemType Directory -Path $magickBasePath -Force | Out-Null
            Write-Host "Created base Magick folder: $magickBasePath" -ForegroundColor Yellow
        } catch {
            Write-Host "ERROR: Failed to create base Magick folder: $_" -ForegroundColor Red
            throw
        }
    }

    # Create date-specific folder
    $dateBasedPath = Join-Path $magickBasePath $Paths.CurrentDate
    if (-not (Test-Path $dateBasedPath)) {
        try {
            New-Item -ItemType Directory -Path $dateBasedPath -Force | Out-Null
            Write-Host "Created date-based folder: $dateBasedPath" -ForegroundColor Yellow
        } catch {
            Write-Host "ERROR: Failed to create date-based folder: $_" -ForegroundColor Red
            throw
        }
    } else {
        Write-Host "Using existing date-based folder: $dateBasedPath" -ForegroundColor Green
    }

    # Store the active date path globally
    $global:ActiveDatePath = $dateBasedPath

    return $dateBasedPath

}

function Add-ScriptSpecificPaths {
[CmdletBinding()]
param(
[hashtable]$Paths,
        [string]$DateBasedPath,
[switch]$IsMonitor,
        [switch]$IsWorker
)

    # Add date-based path to common paths
    $Paths.DateBasedPath = $DateBasedPath
    $Paths.ActiveDatePath = $DateBasedPath

    # Monitor-specific paths
    if ($IsMonitor) {
        $Paths.WorkerScript = Join-Path $Paths.ProjectRoot "patterns\scripts\1_magick\1_mask_portable.ps1"
        $Paths.PythonScriptPath = Join-Path $Paths.ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
        $Paths.PIDFilePath = Join-Path $DateBasedPath "monitor_pid_Magick.json"
        $Paths.LogFile = Join-Path $DateBasedPath "monitor_Magick.log"
        $Paths.OutputFolderPattern = "Magick_Process_MaskDetect_*"

        # Enhanced: Additional monitor paths
        $Paths.SuddenTerminationTrackingFile = Join-Path $DateBasedPath "sudden_termination_tracking.json"
        $Paths.PersistentTrackingFile = Join-Path $DateBasedPath "persistent_tracking.json"
        $Paths.PythonExe = Join-Path $Paths.VenvRoot ".venv\Scripts\python.exe"
    }

    # Worker-specific paths
    if ($IsWorker) {
        $Paths.PythonScript = Join-Path $Paths.ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
        $Paths.PythonExe = Join-Path $Paths.VenvRoot ".venv\Scripts\python.exe"

        # Enhanced: Additional worker paths
        $Paths.WorkerLogPattern = "worker_*.log"
        $Paths.RunFolderPattern = "Magick_Process_MaskDetect_*"
    }

    return $Paths

}

function Validate-CriticalPaths {
[CmdletBinding()]
param(
[hashtable]$Paths,
        [switch]$IsMonitor,
[switch]$IsWorker
)

    $criticalPaths = @()
    $missingPaths = @()
    $warnings = @()

    # Common critical paths
    $criticalPaths += @{ Name = "Project Root"; Path = $Paths.ProjectRoot }
    $criticalPaths += @{ Name = "Active Root"; Path = $Paths.ActiveRoot }
    $criticalPaths += @{ Name = "Date-Based Path"; Path = $Paths.DateBasedPath }

    # Monitor-specific critical paths
    if ($IsMonitor) {
        $criticalPaths += @{ Name = "Worker Script"; Path = $Paths.WorkerScript }
        $criticalPaths += @{ Name = "Python Script (Monitor)"; Path = $Paths.PythonScriptPath }
        $criticalPaths += @{ Name = "PID File Path"; Path = $Paths.PIDFilePath }
        $criticalPaths += @{ Name = "Log File"; Path = $Paths.LogFile }
        $criticalPaths += @{ Name = "Venv path"; Path = $Paths.VenvRoot }
        $criticalPaths += @{ Name = "Python from venv"; Path = $Paths.PythonExe }
    }

    # Worker-specific critical paths
    if ($IsWorker) {
        $criticalPaths += @{ Name = "Python Script (Worker)"; Path = $Paths.PythonScript }
        $criticalPaths += @{ Name = "Python Executable"; Path = $Paths.PythonExe }
    }

    Write-Host "`nValidating critical paths..." -ForegroundColor Yellow

    foreach ($item in $criticalPaths) {
        if (Test-Path $item.Path) {
            Write-Host "  [✓] $($item.Name): $($item.Path)" -ForegroundColor Green
        } else {
            # Check if it's a file that might be created later
            if ($item.Name -match "File") {
                $parentDir = Split-Path $item.Path -Parent
                if (Test-Path $parentDir) {
                    Write-Host "  [?] $($item.Name): $($item.Path) (Directory exists, file will be created)" -ForegroundColor Yellow
                    $warnings += $item.Name
                } else {
                    Write-Host "  [✗] $($item.Name): $($item.Path)" -ForegroundColor Red
                    $missingPaths += $item.Name
                }
            } else {
                Write-Host "  [✗] $($item.Name): $($item.Path)" -ForegroundColor Red
                $missingPaths += $item.Name
            }
        }
    }

    # Summary
    if ($missingPaths.Count -gt 0) {
        Write-Host "`nERROR: Missing critical paths!" -ForegroundColor Red
        foreach ($missing in $missingPaths) {
            Write-Host "  - $missing" -ForegroundColor Red
        }

        if ($IsWorker) {
            Write-Host "`nTroubleshooting for Worker:" -ForegroundColor Yellow
            Write-Host "1. Check virtual environment exists at: $($Paths.VenvRoot)" -ForegroundColor Yellow
            Write-Host "2. Verify Python script location: $($Paths.PythonScript)" -ForegroundColor Yellow
        }

        if ($IsMonitor) {
            Write-Host "`nTroubleshooting for Monitor:" -ForegroundColor Yellow
            Write-Host "1. Verify worker script location: $($Paths.WorkerScript)" -ForegroundColor Yellow
            Write-Host "2. Check Python script location: $($Paths.PythonScriptPath)" -ForegroundColor Yellow
        }
    }

    if ($warnings.Count -gt 0) {
        Write-Host "`nWarnings: $($warnings.Count) path(s) will be created during execution" -ForegroundColor Yellow
    }

    if ($missingPaths.Count -eq 0) {
        Write-Host "`nAll critical paths validated successfully!" -ForegroundColor Green
    }

}

# ====================================================================

# ENHANCED: Get-DateBasedPath with improved functionality

# ====================================================================

# ====================================================================

# ENHANCED: Logging function with flexible output - STABILIZED

# ====================================================================

function Write-Log {
<#
.SYNOPSIS
Enhanced logging function for common module with multiple output options
.DESCRIPTION
Supports console output, file logging, and different log levels
#>
[CmdletBinding()]
param(
[Parameter(Mandatory=$true)]
[string]$Message,

        [ValidateSet("INFO", "DEBUG", "WARN", "ERROR", "SUCCESS")]
        [string]$Level = "INFO",

        [string]$LogFile,

        [switch]$NoConsole
    )

    $currentTimestamp = Get-Date -Format $Script:CommonConfig.LogDateTimeFormat
    $logEntry = "[$currentTimestamp] [$Level] $Message"

    # Write to log file if specified
    if ($LogFile -and (-not [string]::IsNullOrEmpty($LogFile))) {
        try {
            # Ensure directory exists
            $logDir = Split-Path $LogFile -Parent
            if (-not (Test-Path $logDir)) {
                New-Item -ItemType Directory -Path $logDir -Force | Out-Null
            }

            Add-Content -Path $LogFile -Value $logEntry -ErrorAction Stop
        } catch {
            # Fallback to console if file write fails
            if (-not $NoConsole) {
                Write-Host "Log file write failed: $_" -ForegroundColor Yellow
            }
        }
    }

    # Color-coded console output (unless suppressed)
    if (-not $NoConsole) {
        $color = switch ($Level) {
            "ERROR"   { "Red" }
            "WARN"    { "Yellow" }
            "SUCCESS" { "Green" }
            "DEBUG"   { "Gray" }
            default   { "White" }
        }

        Write-Host $logEntry -ForegroundColor $color
    }

    return $logEntry

}

# ====================================================================

# ENHANCED: Utility Functions - REMOVED Export-ModuleMember dependencies

# ====================================================================

# ====================================================================

# STABILIZATION: Global Variable Initialization

# ====================================================================

# Initialize global variables to prevent null reference errors

if (-not $global:ProjectRoot) { $global:ProjectRoot = $null }
if (-not $global:ActiveRoot) { $global:ActiveRoot = $null }
if (-not $global:VenvRoot) { $global:VenvRoot = $null }
if (-not $global:ActiveDatePath) { $global:ActiveDatePath = $null }
if (-not $global:CurrentDateFolder) { $global:CurrentDateFolder = $null }

# ====================================================================

# ENHANCED: Communication Functions for Monitor-Worker Coordination

# ====================================================================

function Initialize-CommunicationPaths {
[CmdletBinding()]
param(
[hashtable]$Paths,
        [switch]$IsMonitor,
[switch]$IsWorker
)

    if (-not $Paths -or -not $Paths.DateBasedPath) {
        Write-Host "ERROR: Invalid paths provided to Initialize-CommunicationPaths" -ForegroundColor Red
        return $null
    }

    $communicationPaths = @{}

    try {
        # Create communication directory
        $commDir = Join-Path $Paths.DateBasedPath "communication"
        if (-not (Test-Path $commDir)) {
            New-Item -ItemType Directory -Path $commDir -Force -ErrorAction Stop | Out-Null
            Write-Host "Created communication directory: $commDir" -ForegroundColor Yellow
        }

        # Common communication files (used by both monitor and worker)
        $communicationPaths.CommunicationDir = $commDir
        $communicationPaths.StatusFile = Join-Path $commDir "worker_status.json"
        $communicationPaths.HeartbeatFile = Join-Path $commDir "worker_heartbeat.json"
        $communicationPaths.CommandFile = Join-Path $commDir "monitor_command.json"
        $communicationPaths.LockFile = Join-Path $commDir "communication.lock"
        $communicationPaths.RegistrationFile = Join-Path $commDir "worker_registered.json"

        # Worker-specific communication
        if ($IsWorker) {
            $communicationPaths.PIDFile = Join-Path $commDir "worker_pid.txt"
        }

        return $communicationPaths
    } catch {
        Write-Host "ERROR: Failed to initialize communication paths: $_" -ForegroundColor Red
        return $null
    }

}

function Write-WorkerStatus {
[CmdletBinding()]
param(
[string]$StatusFile,
        [string]$Status,
[int]$WorkerPID,
        [int]$PythonPID = 0,
[string]$Message = "",
        [string]$RunFolder = ""
)

    $statusData = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Status = $Status
        WorkerPID = $WorkerPID
        PythonPID = $PythonPID
        Message = $Message
        RunFolder = $RunFolder
        MonitorDetected = $false
        LastHeartbeat = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }

    try {
        $statusData | ConvertTo-Json | Out-File $StatusFile -Force
        return $true
    } catch {
        Write-Host "Failed to write worker status: $_" -ForegroundColor Red
        return $false
    }

}

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

function Send-Heartbeat {
[CmdletBinding()]
param([string]$HeartbeatFile)

    try {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $heartbeat = @{
            Timestamp = $timestamp
            ProcessID = $PID
            Type = "Worker"
        }

        $heartbeat | ConvertTo-Json | Out-File $HeartbeatFile -Force
        return $true
    } catch {
        return $false
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

    # FIXED: Correct while loop syntax
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

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
    try {
        # Dot-source the script to load functions into current scope
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
$Script:Config = @{
    # Schedule configuration
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
# $global:SuddenTerminationTracking = @{
#     Events = @()
#     CurrentStreak = 0
#     LastCleanupDate = $null
#     Statistics = @{
#         TotalSuddenTerminations = 0
#         TotalCleanups = 0
#         LastCleanupReason = $null
#         FirstEventDate = $null
#         LastEventDate = $null
#     }
# }

# Persistent Tracking
# $global:PersistentTracking = @{
#     LastKnownRunFolder = $null
#     LastKnownPythonPID = $null
#     LastKnownWorkerPID = $null
#     LastValidationTime = $null
#     LastValidationResult = $null
#     ProcessStopHistory = @()
#     ValidationHistory = @()
#     DailyRunCount = 0
#     LastSuccessfulRun = $null
#     CollectedRunFolders = @()
# }

$global:CollectedRunFolders = @()
$global:EmailAttachmentQueue = @()

# ====================================================================
# CRITICAL UPDATE: Process Management Functions from OLD VERSION
# ====================================================================

function Check-ProcessStatus {
    # First try communication-based detection
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

function Find-PythonProcess {
    # Try to find the Python process running our specific script
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
    Write-Log "Detecting worker process..." -Level "INFO" -LogFile $Script:Config.LogFile
    
    # Method 1: Check communication status file
    $commPaths = Initialize-CommunicationPaths -Paths $paths -IsMonitor
    $statusFile = $commPaths.StatusFile
    
    if (Test-Path $statusFile) {
        try {
            $status = Read-WorkerStatus -StatusFile $statusFile
            
            if ($status.Status -ne "NOT_FOUND" -and $status.WorkerPID -gt 0) {
                # Verify the PID is actually running
                if (Is-ProcessRunning -ProcessId $status.WorkerPID -ProcessName "powershell") {
                    Write-Log "Found registered worker (PID: $($status.WorkerPID)) via status file" -Level "SUCCESS" -LogFile $Script:Config.LogFile
                    $global:WorkerPID = $status.WorkerPID
                    $global:PythonPID = $status.PythonPID
                    $global:WorkerIsRunning = $true
                    $global:PythonIsRunning = ($status.PythonPID -gt 0) -and (Is-ProcessRunning -ProcessId $status.PythonPID -ProcessName "python")
                    return $true
                }
            }
        } catch {
            Write-Log "Error reading worker status: $_" -Level "WARN" -LogFile $Script:Config.LogFile
        }
    }
    
    # Method 2: Check heartbeat file
    $heartbeatFile = $commPaths.HeartbeatFile
    if ((Test-Path $heartbeatFile) -and (Check-Heartbeat -HeartbeatFile $heartbeatFile)) {
        Write-Log "Worker heartbeat detected" -Level "INFO" -LogFile $Script:Config.LogFile
        return $true
    }
    
    # Method 3: Traditional process scanning
    Write-Log "Scanning for worker processes..." -Level "DEBUG" -LogFile $Script:Config.LogFile

    $workerProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue |
        Where-Object { 
            ($_.ProcessName -like "*powershell*") -and ($_.Id -ne $PID)
        }
    
    foreach ($proc in $workerProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.WorkerScript)*") {
                Write-Log "Found worker process via command line scan (PID: $($proc.Id))" -Level "SUCCESS" -LogFile $Script:Config.LogFile
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
    
    Write-Log "No active worker process detected" -Level "INFO" -LogFile $Script:Config.LogFile
    return $false
}


function Update-WorkerCommunication {
    param(
        [int]$WorkerPID,
        [int]$PythonPID = 0
    )
    
    $commPaths = Initialize-CommunicationPaths -Paths $paths -IsMonitor
    
    try {
        # Update status file using common function
        Write-WorkerStatus -StatusFile $commPaths.StatusFile `
            -Status "RUNNING" `
            -WorkerPID $WorkerPID `
            -PythonPID $PythonPID `
            -Message "Detected by monitor"
        
        # Create heartbeat if missing
        if (-not (Test-Path $commPaths.HeartbeatFile)) {
            Send-Heartbeat -HeartbeatFile $commPaths.HeartbeatFile
        }
        
        Write-Log "Updated worker communication files" -Level "DEBUG" -LogFile $Script:Config.LogFile
        return $true
    } catch {
        Write-Log "Failed to update worker communication: $_" -Level "ERROR" -LogFile $Script:Config.LogFile
        return $false
    }
}




function Check-WorkerHealth {
    $commPaths = Initialize-CommunicationPaths -Paths $global:MonitorPaths -IsMonitor
    
    # Check heartbeat using common function
    $heartbeatAlive = Check-Heartbeat -HeartbeatFile $commPaths.HeartbeatFile
    
    # Check if process is still running
    $processAlive = $false
    if ($global:WorkerPID -gt 0) {
        $processAlive = Is-ProcessRunning -ProcessId $global:WorkerPID -ProcessName "powershell"
    }
    
    # If heartbeat says alive but process is dead, cleanup
    if ($heartbeatAlive -and -not $processAlive) {
        Write-Log "Worker heartbeat active but process not found - cleaning up stale heartbeat" -Level "WARN" -LogFile $Script:Config.LogFile
        Remove-Item $commPaths.HeartbeatFile -Force -ErrorAction SilentlyContinue
        return $false
    }
    
    return $heartbeatAlive -or $processAlive
}

function Cleanup-OrphanedProcesses {
    Write-Log "Checking for orphaned processes..." -Level "INFO" -LogFile $Script:Config.LogFile
    
    $cleanedProcesses = @()
    
    # Clean up Python processes
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue | 
        Where-Object { $_.Path -like "*python*" }
    
    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.PythonScript)*") {
                Write-Log "Terminating orphaned Python process (PID: $($proc.Id))" -Level "WARN" -LogFile $Script:Config.LogFile
                $proc.Kill()
                $cleanedProcesses += "Python:$($proc.Id)"
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
                Write-Log "Terminating orphaned worker process (PID: $($proc.Id))" -Level "WARN" -LogFile $Script:Config.LogFile
                $proc.Kill()
                $cleanedProcesses += "Worker:$($proc.Id)"
            }
        } catch { }
    }
    
    # Clean up PID tracking file
    if ($Script:Config.PIDFilePath -and (Test-Path $Script:Config.PIDFilePath)) {
        Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        Write-Log "Cleaned up PID tracking file" -Level "INFO" -LogFile $Script:Config.LogFile
    }
    
    # Reset global process variables
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false
    
    if ($cleanedProcesses.Count -gt 0) {
        Write-Log "Cleanup completed. Cleaned processes: $($cleanedProcesses.Count)" -Level "INFO" -LogFile $Script:Config.LogFile
    }
    
    return $cleanedProcesses
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

function Start-WorkerProcess {
    # Clean up any stale communication files
    $commPaths = Initialize-CommunicationPaths -Paths $paths -IsMonitor
    if (Test-Path $commPaths.CommunicationDir) {
        Get-ChildItem $commPaths.CommunicationDir -Filter "*.txt" -ErrorAction SilentlyContinue | Remove-Item -Force
        Get-ChildItem $commPaths.CommunicationDir -Filter "*.json" -ErrorAction SilentlyContinue | Remove-Item -Force
    }
    
    Write-Log "Starting face recognition worker with enhanced communication..." -Level "INFO" -LogFile $Script:Config.LogFile
    
    try {
        # Create start command
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
                Write-Log "Sent START command to worker via CommandFile" -Level "DEBUG" -LogFile $Script:Config.LogFile
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
            
            Write-Log "Worker process started (PID: $global:WorkerPID)" -Level "SUCCESS" -LogFile $Script:Config.LogFile
            
            # Wait for worker to register
            Write-Log "Waiting for worker registration..." -Level "INFO" -LogFile $Script:Config.LogFile
            $maxWait = 30
            $waited = 0
            
            while ($waited -lt $maxWait) {
                if (Test-Path $commPaths.RegistrationFile) {
                    Write-Log "Worker registered successfully" -Level "SUCCESS" -LogFile $Script:Config.LogFile
                    break
                }
                
                Start-Sleep -Seconds 1
                $waited++
                
                # Check if process died
                if ($WorkerProcess.HasExited) {
                    Write-Log "Worker process exited unexpectedly" -Level "ERROR" -LogFile $Script:Config.LogFile
                    return $false
                }
            }
            
            # Wait for Python process
            Write-Log "Waiting for Python process..." -Level "INFO" -LogFile $Script:Config.LogFile
            $waited = 0
            
            while ($waited -lt $maxWait) {
                $foundPID = Find-PythonProcess
                if ($foundPID) {
                    $global:PythonPID = $foundPID
                    $global:PythonIsRunning = $true
                    $global:PythonStartTime = Get-Date
                    
                    # Update communication
                    Update-WorkerCommunication -WorkerPID $global:WorkerPID -PythonPID $foundPID
                    
                    Write-Log "Python process found (PID: $global:PythonPID)" -Level "SUCCESS" -LogFile $Script:Config.LogFile
                    Save-PIDTracking
                    return $true
                }
                
                Start-Sleep -Seconds 2
                $waited += 2
            }
            
            Write-Log "Python process did not start within $maxWait seconds" -Level "WARN" -LogFile $Script:Config.LogFile
            Save-PIDTracking
            return $true
        } else {
            Write-Log "Failed to start worker process" -Level "ERROR" -LogFile $Script:Config.LogFile
            return $false
        }
    } catch {
        Write-Log "ERROR starting worker: $_" -Level "ERROR" -LogFile $Script:Config.LogFile
        return $false
    }
}

function Stop-WorkerProcess {
    Write-Log "Stopping worker process..." -Level "INFO" -LogFile $Script:Config.LogFile
    
    $stoppedProcesses = @()
    
    # Send STOP command to worker first
    $commPaths = Initialize-CommunicationPaths -Paths $paths -IsMonitor
    $commandData = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Command = "STOP"
        MonitorPID = $PID
        Action = "StopWorker"
        Parameters = @{
            Reason = "Monitor Shutdown"
            GracePeriodSeconds = 10
        }
    }
    
    if (Acquire-Lock -LockFile $commPaths.LockFile) {
        try {
            $commandData | ConvertTo-Json | Out-File $commPaths.CommandFile -Force
            Write-Log "Sent STOP command to worker" -Level "INFO" -LogFile $Script:Config.LogFile
        } finally {
            Release-Lock -LockFile $commPaths.LockFile
        }
    }
    
    # Give worker time to shut down gracefully
    Start-Sleep -Seconds 5
    
    # Stop worker PowerShell process
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        Write-Log "Stopping worker process (PID: $global:WorkerPID)..." -Level "INFO" -LogFile $Script:Config.LogFile
        
        try {
            $workerProcess = Get-Process -Id $global:WorkerPID -ErrorAction Stop
            
            if (-not $workerProcess.HasExited) {
                $workerProcess.CloseMainWindow() | Out-Null
                Start-Sleep -Seconds 2
                
                if (-not $workerProcess.HasExited) {
                    Write-Log "Forcefully terminating worker process..." -Level "WARN" -LogFile $Script:Config.LogFile
                    $workerProcess.Kill()
                    if ($workerProcess.WaitForExit($Script:Config.GracefulShutdownTimeout * 1000)) {
                        $stoppedProcesses += "Worker"
                        Write-Log "Worker process terminated" -Level "SUCCESS" -LogFile $Script:Config.LogFile
                    }
                } else {
                    $stoppedProcesses += "Worker"
                    Write-Log "Worker process exited gracefully" -Level "SUCCESS" -LogFile $Script:Config.LogFile
                }
            } else {
                Write-Log "Worker process already exited" -Level "INFO" -LogFile $Script:Config.LogFile
            }
        } catch {
            Write-Log "Error stopping worker process: $_" -Level "ERROR" -LogFile $Script:Config.LogFile
        }
    }
    
    # Stop the Python process
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        Write-Log "Stopping Python process (PID: $global:PythonPID)..." -Level "INFO" -LogFile $Script:Config.LogFile
        
        try {
            $pythonProcess = Get-Process -Id $global:PythonPID -ErrorAction Stop
            
            if (-not $pythonProcess.HasExited) {
                $pythonProcess.CloseMainWindow() | Out-Null
                Start-Sleep -Seconds 2
                
                if (-not $pythonProcess.HasExited) {
                    Write-Log "Forcefully terminating Python process..." -Level "WARN" -LogFile $Script:Config.LogFile
                    $pythonProcess.Kill()
                    if ($pythonProcess.WaitForExit($Script:Config.GracefulShutdownTimeout * 1000)) {
                        $stoppedProcesses += "Python"
                        Write-Log "Python process terminated" -Level "SUCCESS" -LogFile $Script:Config.LogFile
                    }
                } else {
                    $stoppedProcesses += "Python"
                    Write-Log "Python process exited gracefully" -Level "SUCCESS" -LogFile $Script:Config.LogFile
                }
            } else {
                Write-Log "Python process already exited" -Level "INFO" -LogFile $Script:Config.LogFile
            }
        } catch {
            Write-Log "Error stopping Python process: $_" -Level "ERROR" -LogFile $Script:Config.LogFile
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
        Write-Log "Removed PID tracking file" -Level "DEBUG" -LogFile $Script:Config.LogFile
    }
    
    # Clean up communication files
    if (Test-Path $commPaths.CommunicationDir) {
        Remove-Item -Path $commPaths.CommunicationDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Log "Cleaned up communication directory" -Level "DEBUG" -LogFile $Script:Config.LogFile
    }
    
    if ($stoppedProcesses.Count -gt 0) {
        Write-Log "Stopped processes: $($stoppedProcesses -join ', ')" -Level "INFO" -LogFile $Script:Config.LogFile
    }
}

 

# ====================================================================
# ENHANCED: PID Tracking with persistent data (from old version)
# ====================================================================

function Save-PIDTracking {
    $PIDTracking = @{
        WorkerPID = $global:WorkerPID
        PythonPID = $global:PythonPID
        WorkerStartTime = if ($global:WorkerStartTime) { $global:WorkerStartTime.ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
        PythonStartTime = if ($global:PythonStartTime) { $global:PythonStartTime.ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
        RunFolder = $global:CurrentRunFolder
        LastUpdate = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }
    
    try {
        if ($Script:Config.PIDFilePath) {
            $PIDTracking | ConvertTo-Json -Depth 5 | Out-File -FilePath $Script:Config.PIDFilePath -Force
            Write-Log "PID tracking saved" -Level "DEBUG" -LogFile $Script:Config.LogFile
        }
    } catch {
        Write-Log "Failed to save PID tracking: $_" -Level "ERROR" -LogFile $Script:Config.LogFile
    }
}


function Load-PIDTracking {
    if (-not $Script:Config.PIDFilePath -or -not (Test-Path $Script:Config.PIDFilePath)) {
        Write-Log "No PID tracking file found" -Level "DEBUG" -LogFile $Script:Config.LogFile
        return $false
    }
    
    try {
        $loaded = Get-Content -Path $Script:Config.PIDFilePath -Raw | ConvertFrom-Json
        
        # Check if PID file is too old
        $lastUpdate = [DateTime]::ParseExact($loaded.LastUpdate, "yyyy-MM-dd HH:mm:ss", $null)
        $ageMinutes = ((Get-Date) - $lastUpdate).TotalMinutes
        
        if ($ageMinutes -gt $Script:Config.MaxPIDFileAgeMinutes) {
            Write-Log "PID file is too old ($ageMinutes minutes), cleaning up" -Level "WARN" -LogFile $Script:Config.LogFile
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
        
        Write-Log "PID tracking loaded: WorkerPID=$global:WorkerPID, PythonPID=$global:PythonPID" -Level "INFO" -LogFile $Script:Config.LogFile
        return $true
    } catch {
        Write-Log "Failed to load PID tracking: $_" -Level "ERROR" -LogFile $Script:Config.LogFile
        Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        return $false
    }
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
 
# ====================================================================
# MAIN EXECUTION - UPDATED WITH OLD VERSION'S RELIABILITY
# ====================================================================

try {
    # Create log directory if it doesn't exist
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
    Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
    
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
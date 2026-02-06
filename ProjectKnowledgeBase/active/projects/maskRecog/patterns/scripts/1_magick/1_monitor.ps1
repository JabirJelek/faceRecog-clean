# 1_monitor.ps1
<#
.SYNOPSIS
Enhanced time-based process monitor for Face Recognition pipeline with PID tracking.
.DESCRIPTION
Monitors face recognition worker process with enhanced resilience and state recovery.
.NOTES
Incorporates features from old version: sudden termination tracking, persistent state, MailKit email with verification.
#>

# ====================================================================
# ENHANCED: Import common paths module with improved error handling
# ====================================================================
$commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
if (Test-Path $commonPathsScript) {
    . $commonPathsScript
    Write-Host "✓ Common paths module loaded" -ForegroundColor Green
} else {
    Write-Host "ERROR: Common paths script not found at: $commonPathsScript" -ForegroundColor Red
    Write-Host "Attempting to find project root manually..." -ForegroundColor Yellow
    
    # Fallback to manual initialization similar to old version
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
# ENHANCED: Global variables with persistent tracking (from old version)
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
$global:timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$global:LastWorkerAttempt = $null

# Enhanced tracking for resilience (from old version)
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

# Sudden Termination Tracking (from old version)
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

# ====================================================================
# ENHANCED: Configuration with improved settings (from old version)
# ====================================================================
$Script:Config = @{
    # Schedule configuration
    StartTime = "08:00"
    EndTime = "14:18"

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
    
    # Email notifications (updated with old version's MailKit approach)
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
    
    # ENHANCED: Sudden termination tracking (from old version)
    SuddenTermination = @{
        TrackingFile = $null  # Will be set after paths initialized
        RecordRetentionDays = 30
        ConsecutiveThreshold = 3
        CleanupAction = "ForceCleanupAndNotify"
    }
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
    try {
        # Clean up old events beyond retention period
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
            if ($cmdLine -like "*$($Script:Config.PythonScriptPath)*") {
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
    if (Test-Path $Script:Config.PIDFilePath) {
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
            if ($cmdLine -like "*$($Script:Config.PythonScriptPath)*") {
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

# ====================================================================
# Process Management Functions
# ====================================================================

function Check-ProcessStatus {
    $status = @{
        WorkerRunning = $false
        PythonRunning = $false
        WorkerPID = $global:WorkerPID
        PythonPID = $global:PythonPID
    }
    
    # Simple check worker process
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        $status.WorkerRunning = Is-ProcessRunning -ProcessId $global:WorkerPID -ProcessName "powershell"
    }
    
    # Simple check Python process
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        $status.PythonRunning = Is-ProcessRunning -ProcessId $global:PythonPID -ProcessName "python"
    }
    
    # If we think Python is running but PID is null, try to find it
    if ((-not $status.PythonRunning) -and $global:WorkerIsRunning) {
        $foundPID = Find-PythonProcess
        if ($foundPID) {
            $global:PythonPID = $foundPID
            $status.PythonPID = $foundPID
            $status.PythonRunning = Is-ProcessRunning -ProcessId $foundPID -ProcessName "python"
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
        
        Write-Log "Detected unexpected process stop. Worker: $previousWorkerRunning -> $($status.WorkerRunning), Python: $previousPythonRunning -> $($status.PythonRunning)" -Level "WARN"
        
        # Only trigger validation if we're in the active time window
        $inWindow = Test-TimeWindow -TargetTime $Script:Config.StartTime -and (-not (Test-TimeWindow -TargetTime $Script:Config.EndTime))
        
        if ($inWindow -and $global:CurrentRunFolder) {
            Write-Log "Validating run due to unexpected process stop in active window..." -Level "INFO"
        }
    }
    
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


function Clean-StalePIDFiles {
    if (Test-Path $Script:Config.PIDFilePath) {
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

function Find-PythonProcess {
    # Try to find the Python process running our specific script
    Write-Log "Searching for Python process..." -Level "DEBUG"
    
    # Method 1: Check for processes with our script path in command line
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue | 
        Where-Object { $_.Path -like "*python*" }
    
    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.PythonScriptPath)*") {
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

function Start-WorkerProcess {
    # Check for existing Python process first
    $existingPythonPID = Find-PythonProcess
    if ($existingPythonPID) {
        Write-Log "Found existing Python process (PID: $existingPythonPID), reusing it" -Level "WARN"
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
            "-File", "`"$($Script:Config.WorkerScript)`""
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
            
            Write-Log "Worker process started (PID: $global:WorkerPID)" -Level "SUCCESS"
            
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
                    Write-Log "Python process found (PID: $global:PythonPID)" -Level "SUCCESS"
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
    $wasUnexpected = $false
    
    # Determine if this is an unexpected stop
    if ($global:IsShuttingDown -and $global:ForceStopAttempts -ge $global:ForceStopThreshold) {
        $stopReason = "Force Stop by User"
        $wasUnexpected = $true
    } elseif (-not $global:IsShuttingDown -and ($global:PythonIsRunning -or $global:WorkerIsRunning)) {
        $stopReason = "Unexpected Process Stop"
        $wasUnexpected = $true
        Register-SuddenTermination -Reason $stopReason -TerminationType "Unexpected"
    }
    
    Write-Log "Stopping worker process. Reason: $stopReason" -Level "INFO"
    
    # First, try to stop the Python process
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
        }
        catch {
            Write-Log "Error stopping Python process: $_" -Level "ERROR"
        }
    }
    
    # Then stop the worker PowerShell process
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
    if (Test-Path $Script:Config.PIDFilePath) {
        Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        Write-Log "Removed PID tracking file" -Level "DEBUG"
    }
    
    if ($stoppedProcesses.Count -gt 0) {
        Write-Log "Stopped processes: $($stoppedProcesses -join ', ')" -Level "INFO"
    }
}

function Handle-UnexpectedProcessStop {
    # Collect any incomplete run data
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
        $PIDTracking | ConvertTo-Json -Depth 10 | Out-File -FilePath $Script:Config.PIDFilePath -Force
        Write-Log "PID tracking saved with $($global:CollectedRunFolders.Count) collected folders" -Level "DEBUG"
        
        # Also save persistent tracking separately
        Save-PersistentTracking
    } catch {
        Write-Log "Failed to save PID tracking: $_" -Level "ERROR"
    }
}

function Load-PIDTracking {
    if (-not (Test-Path $Script:Config.PIDFilePath)) {
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

function Save-PersistentTracking {
    $persistentFilePath = Join-Path (Split-Path $Script:Config.LogFile -Parent) "persistent_tracking.json"
    
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

function Load-PersistentTracking {
    $persistentFilePath = Join-Path (Split-Path $Script:Config.LogFile -Parent) "persistent_tracking.json"
    
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
        if (-not (Test-Path $Script:Config.RunsBasePath)) {
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
    
    Clear-Host
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

# ====================================================================
# MAIN EXECUTION
# ====================================================================

try {
    # Initialize paths for monitor
    Write-Host "Initializing enhanced monitor..." -ForegroundColor Cyan
    
    # Use the common paths function but with enhanced configuration
    $paths = Initialize-ProjectPortablePaths -IsMonitor
    
    # Update configuration with paths
    $Script:Config.WorkerScript = $paths.WorkerScript
    $Script:Config.PythonScriptPath = $paths.PythonScriptPath
    $Script:Config.RunsBasePath = $paths.DateBasedPath
    $Script:Config.OutputFolderPattern = "Magick_Process_MaskDetect_*"
    $Script:Config.PIDFilePath = $paths.PIDFilePath
    $Script:Config.LogFile = $paths.LogFile
    $Script:Config.CurrentDate = $paths.CurrentDate
    $Script:Config.ActiveDatePath = $paths.DateBasedPath
    
    # Set sudden termination tracking file path
    $Script:Config.SuddenTermination.TrackingFile = Join-Path $paths.DateBasedPath "sudden_termination_tracking.json"
    
    # Create log directory if it doesn't exist
    $logDir = Split-Path $Script:Config.LogFile -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    
    Write-Log "=== Enhanced Face Recognition Monitor Started ===" -Level "INFO"
    Write-Log "Version: 2.1 (with sudden termination tracking)" -Level "INFO"
    Write-Log "Start Time: $($Script:Config.StartTime)" -Level "INFO"
    Write-Log "End Time: $($Script:Config.EndTime)" -Level "INFO"
    
    # Initialize cleanup and tracking
    Initialize-CleanupOnStartup
    Register-ConsoleControlHandler
    
    # Load existing PID tracking
    $pidLoaded = Load-PIDTracking
    if ($pidLoaded) {
        Write-Log "Resumed monitoring of existing processes" -Level "SUCCESS"
        Check-ProcessStatus | Out-Null
    }
    
    # Ensure runs base path exists
    if (-not (Test-Path $Script:Config.RunsBasePath)) {
        Write-Log "Creating runs base directory" -Level "WARN"
        New-Item -ItemType Directory -Path $Script:Config.RunsBasePath -Force | Out-Null
    }
    
    Clear-Host
    
    # Main monitoring loop with enhanced resilience
    Write-Log "Entering enhanced monitoring loop..." -Level "INFO"
    
    while ($true) {
        try {
            $processStatus = Check-ProcessStatus
            
            $startPassed = Test-TimeWindow -TargetTime $Script:Config.StartTime
            $endPassed = Test-TimeWindow -TargetTime $Script:Config.EndTime
            $inWindow = ($startPassed -and !$endPassed)
            
            $currentTime = Get-Date -Format "HH:mm:ss"
            
            Show-StatusBanner
            
            Write-Log "Check: $currentTime | Window: $(if ($inWindow) {'Active'} else {'Inactive'}) | Python: $(if ($processStatus.PythonRunning) {'Running (PID: ' + $global:PythonPID + ')'} else {'Stopped'})" -Level "DEBUG"
            
            # Check if we should start worker
            if ($inWindow -and !$processStatus.PythonRunning) {
                Write-Log "Time window active and no Python process running - starting worker..." -Level "INFO"
                
                if ($global:LastWorkerAttempt -and ((Get-Date) - $global:LastWorkerAttempt).TotalSeconds -lt 60) {
                    Write-Log "Skipping worker start - too soon after last attempt" -Level "DEBUG"
                } else {
                    $started = Start-WorkerProcess
                    $global:LastWorkerAttempt = Get-Date
                    
                    if ($started) {
                        Write-Log "Worker started. Monitoring Python process..." -Level "SUCCESS"
                    }
                }
            }
            
            # Handle end time
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
                
                Write-Log "Daily process completed. Stopping monitor..." -Level "INFO"
                break
            }
            
            # Save tracking periodically
            if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
                Save-PIDTracking
            }
            
            Start-Sleep -Seconds $Script:Config.ProcessCheckInterval
            
        } catch {
            Write-Log "Error in main loop: $_" -Level "ERROR"
            Register-SuddenTermination -Reason "Main loop error: $_" -TerminationType "Error"
            Save-PIDTracking
            Start-Sleep -Seconds $Script:Config.ProcessCheckInterval
        }
    }
}
catch {
    Write-Log "FATAL ERROR: $_" -Level "ERROR"
    Register-SuddenTermination -Reason "Fatal error: $_" -TerminationType "Fatal"
}
finally {
    Write-Log "Cleaning up..." -Level "INFO"
    Stop-WorkerProcess
    
    # Save final state
    Save-SuddenTerminationTracking
    Save-PersistentTracking
    
    Write-Log "=== Enhanced Face Recognition Monitor Stopped ===" -Level "INFO"
    Write-Host "Monitor stopped." -ForegroundColor Yellow
    Write-Host "Log file: $($Script:Config.LogFile)" -ForegroundColor Yellow
    Write-Host "Collected runs: $($global:CollectedRunFolders.Count)" -ForegroundColor Yellow
}
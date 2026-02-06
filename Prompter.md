#### Important

- Maintain the query requirement.
- Check explanation in every ####
- DO NOT INTRODUCES unused solution that does not relate to the query.

#### Instruction

No process found in the new version. Update the new version with older structure that works to check the running process

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

$Script:Config = @{ # Schedule configuration
StartTime = "08:00"
EndTime = "14:06"

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

# ENHANCED: Improved Process Management Functions

# ====================================================================

function Check-ProcessStatus {
$status = @{
WorkerRunning = $false
PythonRunning = $false
WorkerPID = $global:WorkerPID
PythonPID = $global:PythonPID
WorkerProcessName = $null
PythonProcessName = $null
}

    # IMPROVED: Check worker process with better validation
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        try {
            $process = Get-Process -Id $global:WorkerPID -ErrorAction Stop
            # Check if it's a PowerShell process with our script
            if (-not $process.HasExited) {
                $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($process.Id)").CommandLine
                if ($cmdLine -like "*$($Script:Config.WorkerScript)*") {
                    $status.WorkerRunning = $true
                    $status.WorkerProcessName = $process.ProcessName
                }
            }
        } catch {
            $status.WorkerRunning = $false
        }
    }

    # IMPROVED: Check Python process with better validation
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        try {
            $process = Get-Process -Id $global:PythonPID -ErrorAction Stop
            if (-not $process.HasExited) {
                $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($process.Id)").CommandLine
                if ($cmdLine -like "*$($Script:Config.PythonScriptPath)*" -or
                    $cmdLine -like "*entry_multi-USED-Magick.py*") {
                    $status.PythonRunning = $true
                    $status.PythonProcessName = $process.ProcessName
                }
            }
        } catch {
            $status.PythonRunning = $false
        }
    }

    # IMPROVED: Try to find processes if PIDs are not set
    if (-not $status.WorkerRunning -or -not $status.PythonRunning) {
        Find-RunningProcesses
    }

    # Detect unexpected stops
    $previousWorkerRunning = $global:WorkerIsRunning
    $previousPythonRunning = $global:PythonIsRunning
    $global:WorkerIsRunning = $status.WorkerRunning
    $global:PythonIsRunning = $status.PythonRunning

    if (($previousWorkerRunning -and -not $status.WorkerRunning) -or
        ($previousPythonRunning -and -not $status.PythonRunning)) {
        Write-Log "Detected unexpected process stop" -Level "WARN"
    }

    return $status

}

function Find-RunningProcesses {
Write-Log "Searching for running processes..." -Level "DEBUG"

    # Find worker PowerShell process
    $workerProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "*powershell*" }

    foreach ($proc in $workerProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.WorkerScript)*") {
                if (-not $global:WorkerPID -or $global:WorkerPID -ne $proc.Id) {
                    $global:WorkerPID = $proc.Id
                    $global:WorkerIsRunning = $true
                    Write-Log "Found worker process: PID=$($proc.Id)" -Level "SUCCESS"
                    Save-PIDTracking
                    break
                }
            }
        } catch { }
    }

    # Find Python process
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*python*" }

    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Script:Config.PythonScriptPath)*" -or
                $cmdLine -like "*entry_multi-USED-Magick.py*") {
                if (-not $global:PythonPID -or $global:PythonPID -ne $proc.Id) {
                    $global:PythonPID = $proc.Id
                    $global:PythonIsRunning = $true
                    Write-Log "Found Python process: PID=$($proc.Id)" -Level "SUCCESS"
                    Save-PIDTracking
                    break
                }
            }
        } catch { }
    }

    # Try to get from metadata if still not found
    if (-not $global:PythonPID -and $global:CurrentRunFolder) {
        $pythonPID = Find-PythonProcess
        if ($pythonPID) {
            $global:PythonPID = $pythonPID
            $global:PythonIsRunning = $true
            Write-Log "Found Python process from metadata: PID=$pythonPID" -Level "SUCCESS"
            Save-PIDTracking
        }
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
Write-Log "Searching for Python process using metadata..." -Level "DEBUG"

    # Method 1: Check the most recent run folder for metadata
    $latestRunFolder = Find-LatestRunFolder
    if ($latestRunFolder) {
        $metadataPath = Join-Path $latestRunFolder.FullName "metadata.json"
        if (Test-Path $metadataPath) {
            try {
                $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
                if ($metadata.PSObject.Properties.Name -contains "python_pid" -and $metadata.python_pid) {
                    $foundPID = $metadata.python_pid
                    Write-Log "Found Python PID in metadata: $foundPID" -Level "INFO"

                    try {
                        Get-Process -Id $foundPID -ErrorAction Stop | Out-Null
                        return $foundPID
                    } catch {
                        Write-Log "Python PID from metadata no longer exists" -Level "WARN"
                    }
                }
            } catch {
                Write-Log "Failed to read metadata: $_" -Level "WARN"
            }
        }
    }

    # Method 2: Search all processes for our Python script
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*python*" }

    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*entry_multi-USED-Magick.py*") {
                Write-Log "Found Python process with our script: PID=$($proc.Id)" -Level "SUCCESS"
                return $proc.Id
            }
        } catch { }
    }

    Write-Log "No Python process found" -Level "DEBUG"
    return $null

}

function Start-WorkerProcess { # Check for existing Python process first
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

try { # Initialize paths for monitor
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

    # Clean up stale PID files
    Clean-StalePIDFiles

    # Load existing PID tracking
    $pidLoaded = Load-PIDTracking
    if ($pidLoaded) {
        Write-Log "Resumed monitoring of existing processes" -Level "SUCCESS"

        # Force refresh of process status
        Find-RunningProcesses
        Check-ProcessStatus | Out-Null
    }

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

            Write-Log "Check: $currentTime | Window: $(if ($inWindow) {'Active'} else {'Inactive'}) | Python: $(if ($processStatus.PythonRunning) {'Running'} else {'Stopped'})" -Level "DEBUG"

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

$Script:WorkerConfig = @{ # Python parameters
PythonParams = @{ # "--database" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\current_database-Copy" # "--input" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\process-run\Run_Classified2026-01-21_15-11-08\script_output\classified_output"
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
    Write-WorkerLog "Stack trace: $($\_.ScriptStackTrace)" -Level "ERROR"
exit 1
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

function Get-DateBasedPath {
<#
.SYNOPSIS
Gets or creates a date-based folder path for the current or specified day
.DESCRIPTION
Enhanced version with better error handling and date flexibility
#>
[CmdletBinding()]
param(
[string]$BasePath = (Join-Path $global:ActiveRoot $Script:CommonConfig.LogBasePath),
        [DateTime]$Date = (Get-Date),
[switch]$CreateIfNotExist = $true
)

    try {
        $dateString = $Date.ToString($Script:CommonConfig.DateFormat)
        $datePath = Join-Path $BasePath $dateString

        # Create the directory if it doesn't exist and flag is set
        if (-not (Test-Path $datePath) -and $CreateIfNotExist) {
            try {
                # Ensure base directory exists
                if (-not (Test-Path $BasePath)) {
                    New-Item -ItemType Directory -Path $BasePath -Force | Out-Null
                    Write-Host "Created base directory: $BasePath" -ForegroundColor Yellow
                }

                New-Item -ItemType Directory -Path $datePath -Force | Out-Null
                Write-Host "Created date-based folder: $datePath" -ForegroundColor Yellow
            } catch {
                Write-Host "ERROR: Failed to create date-based folder: $_" -ForegroundColor Red
                throw
            }
        } elseif (Test-Path $datePath) {
            Write-Host "Using existing date-based folder: $datePath" -ForegroundColor Green
        } elseif (-not $CreateIfNotExist) {
            Write-Host "Date-based folder does not exist: $datePath" -ForegroundColor Yellow
        }

        return $datePath
    } catch {
        Write-Host "ERROR in Get-DateBasedPath: $_" -ForegroundColor Red
        throw
    }

}

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

function Get-RunFolderPattern {
<#
.SYNOPSIS
Returns the pattern for run folders based on current configuration
#>
param([string]$Pattern = "Magick*Process_MaskDetect*\*")
return $Pattern
}

function Get-WorkerScriptPath {
<#
.SYNOPSIS
Returns the path to the worker script
#>
param([string]$ProjectRoot = $global:ProjectRoot)

    if (-not $ProjectRoot) {
        Write-Host "ERROR: ProjectRoot not initialized" -ForegroundColor Red
        return $null
    }

    $workerScript = Join-Path $ProjectRoot "patterns\scripts\1_magick\1_mask_portable.ps1"

    if (Test-Path $workerScript) {
        return $workerScript
    } else {
        Write-Host "WARNING: Worker script not found at: $workerScript" -ForegroundColor Yellow
        return $null
    }

}

function Get-PythonPaths {
<#
.SYNOPSIS
Returns Python-related paths (script and executable)
#>
param(
[string]$ProjectRoot = $global:ProjectRoot,
        [string]$VenvRoot = $global:VenvRoot
)

    if (-not $ProjectRoot -or -not $VenvRoot) {
        Write-Host "ERROR: ProjectRoot or VenvRoot not initialized" -ForegroundColor Red
        return $null
    }

    $pythonScript = Join-Path $ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
    $pythonExe = Join-Path $VenvRoot ".venv\Scripts\python.exe"

    return @{
        PythonScript = $pythonScript
        PythonExe = $pythonExe
    }

}

function Test-ProjectStructure {
<#
.SYNOPSIS
Tests if the project structure is valid
#>
[CmdletBinding()]
param()

    try {
        $paths = Initialize-ProjectPortablePaths -Silent

        if (-not $paths) {
            return $false
        }

        # Test critical paths
        $criticalTests = @(
            @{ Path = $paths.ProjectRoot; Type = "Directory" }
            @{ Path = $paths.ActiveRoot; Type = "Directory" }
            @{ Path = $paths.DateBasedPath; Type = "Directory" }
        )

        foreach ($test in $criticalTests) {
            if ($test.Type -eq "Directory") {
                if (-not (Test-Path $test.Path -PathType Container)) {
                    Write-Host "Missing directory: $($test.Path)" -ForegroundColor Red
                    return $false
                }
            }
        }

        return $true
    } catch {
        Write-Host "Project structure test failed: $_" -ForegroundColor Red
        return $false
    }

}

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

# STABILIZATION: Main Execution Block for Testing

# ====================================================================

<#
This script is designed to be dot-sourced by other scripts.
When run directly, it will test the initialization functions.
#>

if ($MyInvocation.InvocationName -ne '.') {
    Write-Host "=== Common Paths Module Test ===" -ForegroundColor Cyan
    Write-Host "This script is designed to be dot-sourced by other scripts." -ForegroundColor Yellow
    Write-Host "Example usage in monitor script:" -ForegroundColor White
    Write-Host "  . `"$PSScriptRoot\1_common-paths.ps1`"" -ForegroundColor White
    Write-Host "  `$paths = Initialize-ProjectPortablePaths -IsMonitor" -ForegroundColor White
    Write-Host ""
    Write-Host "Example usage in worker script:" -ForegroundColor White
    Write-Host "  . `"$PSScriptRoot\1_common-paths.ps1`"" -ForegroundColor White
    Write-Host "  `$paths = Initialize-ProjectPortablePaths -IsWorker" -ForegroundColor White
Write-Host ""

    # Test the functions
    try {
        Write-Host "Testing project structure..." -ForegroundColor Cyan
        $testResult = Test-ProjectStructure
        if ($testResult) {
            Write-Host "✓ Project structure test passed" -ForegroundColor Green
        } else {
            Write-Host "✗ Project structure test failed" -ForegroundColor Red
        }
    } catch {
        Write-Host "Error during test: $_" -ForegroundColor Red
    }

}

#### OLd version that can check running process

<#
.SYNOPSIS
Time-based process monitor for Face Recognition pipeline with proper PID tracking.

.DESCRIPTION
Runs in background and manages the face recognition worker process based on schedule.
Tracks the actual Python process spawned by the worker script.

.NOTES
Configured for C:\RaihanFarid\Dokumen\faceRecog\process-run output structure
#>

# ====================================================================

# SECTION 1: INITIALIZATION AND CONFIGURATION

# ====================================================================

<#
.SYNOPSIS
Sets up portable paths for the project and validates all components exist
.DESCRIPTION
This SINGLE function does 3 things:

1.  Finds the maskRecog project root
2.  Builds all paths relative to it
3.  Validates critical components exist
    #>
    function Initialize-ProjectPortablePaths {
    [CmdletBinding()]
    param()

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
            # Stop if we reach drive root (like C:\) or can't go further
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

        # Load shared configuration if it exists
        $sharedConfigPath = Join-Path $projectRoot "project_config.psd1"
        if (Test-Path $sharedConfigPath) {
            try {
                $sharedConfig = Import-PowerShellDataFile -Path $sharedConfigPath
                Write-Host "Loaded shared configuration from: $sharedConfigPath" -ForegroundColor Green
            } catch {
                Write-Host "Note: Could not load shared configuration" -ForegroundColor Yellow
            }
        }

        # ====================================================================
        # STEP 2: BUILD PATHS RELATIVE TO PROJECT ROOT with Persistent Tracking Variables
        # ====================================================================

        # Store project root globally so all functions can use it
        $global:ProjectRoot = $projectRoot
        $global:ActiveRoot = Split-Path $projectRoot -Parent | Split-Path -Parent

        # Initialize global tracking variables
        Initialize-GlobalTrackingVariables

        # Show what we found
        Write-Host "Project Root: $ProjectRoot" -ForegroundColor Green
        Write-Host "Active Root: $ActiveRoot" -ForegroundColor Green

        # ====================================================================
        # STEP 3: UPDATE CONFIGURATION WITH RELATIVE PATHS
        # ====================================================================

        # Update the $Config object with relative paths
        $Script:Config = Get-ProjectConfiguration -ProjectRoot $ProjectRoot -ActiveRoot $ActiveRoot

        # ====================================================================
        # STEP 4: VALIDATE CRITICAL COMPONENTS EXIST
        # ====================================================================

        Write-Host "`nValidating project components..." -ForegroundColor Yellow

        $validationResult = Validate-ProjectComponents -Config $Config

        if ($validationResult.MissingComponents.Count -gt 0) {
            $continue = Read-Host "`nSome components are missing. Continue anyway? (Y/N)"
            if ($continue -notmatch '^[Yy]') {
                Write-Host "Exiting script..." -ForegroundColor Red
                exit 1
            }
        }

        Write-Host "`nProject initialization complete!" -ForegroundColor Green
        Write-Host "All paths are now portable and relative to:" -ForegroundColor Green
        Write-Host "  Project Root: $ProjectRoot" -ForegroundColor White

        # ====================================================================
        # STEP 5: Wait for key press with 60-second timeout
        # ====================================================================

        Invoke-StartupWait

        return $true

    }

function Initialize-GlobalTrackingVariables {
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

    $global:EmailAttachmentQueue = @()
    $global:CollectedRunFolders = @()
    $global:ForceStopAttempts = 0
    $global:LastForceStopTime = $null
    $global:ForceStopThreshold = 2
    $global:ForceStopWindowSeconds = 5
    $global:IsShuttingDown = $false

    # Process tracking variables
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

    # PID tracking structure
    $global:PIDTracking = @{
        WorkerPID = $null
        PythonPID = $null
        WorkerStartTime = $null
        PythonStartTime = $null
        RunFolder = $null
        LastUpdate = $null
    }

    # Sudden termination tracking
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

}

function Get-ProjectConfiguration {
param(
[string]$ProjectRoot,
        [string]$ActiveRoot
)

    # Get email credential from user profile
    $emailCredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
    if (!(Test-Path (Split-Path $emailCredentialPath -Parent))) {
        New-Item -ItemType Directory -Path (Split-Path $emailCredentialPath -Parent) -Force | Out-Null
    }

    return @{
        # Schedule configuration
        StartTime = "08:00"
        EndTime = "17:02"

        # Worker script path - RELATIVE to project root
        WorkerScript = Join-Path $ProjectRoot "patterns\scripts\1_magick\maskDetect-portable.ps1"

        # Python script path - RELATIVE to project root
        PythonScriptPath = Join-Path $ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"

        # Paths for validation - RELATIVE to active root
        RunsBasePath = Join-Path $ActiveRoot "logs-running\magick"
        OutputFolderPattern = "Magick_Process_MaskDetect_*"

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
        ProcessCheckInterval = 5
        GracefulShutdownTimeout = 60

        # PID tracking - RELATIVE to RunsBasePath
        PIDFilePath = Join-Path (Join-Path $ActiveRoot "logs-running\magick") "monitor_pid_Magick.json"
        MaxPIDFileAgeMinutes = 120

        # Logging - RELATIVE to RunsBasePath
        LogFile = Join-Path (Join-Path $ActiveRoot "logs-running\magick") "monitor_Magick.log"

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
        EmailCredentialPath = $emailCredentialPath

        # Sudden termination tracking configuration
        SuddenTermination = @{
            TrackingFile = Join-Path (Join-Path $ActiveRoot "logs-running\magick") "sudden_termination_tracking.json"
            RecordRetentionDays = 30
            ConsecutiveThreshold = 3
            CleanupAction = "ForceCleanupAndNotify"
        }
    }

}

function Validate-ProjectComponents {
param(
[hashtable]$Config
)

    $result = @{
        MissingComponents = @()
        CreatedDirectories = @()
    }

    $criticalComponents = @(
        @{ Name = "Worker Script"; Path = $Config.WorkerScript }
        @{ Name = "Python Script"; Path = $Config.PythonScriptPath }
        @{ Name = "Log Directory"; Path = (Split-Path $Config.LogFile -Parent) }
        @{ Name = "PID File Directory"; Path = (Split-Path $Config.PIDFilePath -Parent) }
    )

    foreach ($component in $criticalComponents) {
        if (!(Test-Path $component.Path)) {
            Write-Host "  [MISSING] $($component.Name): $($component.Path)" -ForegroundColor Red

            # Try to create missing directories
            if ($component.Name -match "Directory") {
                try {
                    New-Item -ItemType Directory -Path $component.Path -Force | Out-Null
                    Write-Host "  [CREATED] Directory: $($component.Path)" -ForegroundColor Yellow
                    $result.CreatedDirectories += $component.Path
                } catch {
                    $result.MissingComponents += $component.Name
                }
            } else {
                $result.MissingComponents += $component.Name
            }
        } else {
            Write-Host "  [OK] $($component.Name)" -ForegroundColor Green
        }
    }

    return $result

}

function Invoke-StartupWait {
Write-Host "`nPress any key to continue with monitoring (waiting for 60 seconds)..." -ForegroundColor Cyan

    # Create a timeout mechanism for 60 seconds
    $timeout = New-TimeSpan -Seconds 60
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $keyPressed = $false

    while ($stopwatch.Elapsed -lt $timeout -and -not $keyPressed) {
        if ($Host.UI.RawUI.KeyAvailable) {
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
            $keyPressed = $true
            Write-Host "`nKey pressed. Continuing..." -ForegroundColor Green
        } else {
            # Show countdown
            $remaining = 60 - [math]::Floor($stopwatch.Elapsed.TotalSeconds)
            if ($remaining % 10 -eq 0 -and $remaining -ne 60) {
                Write-Host "  Auto-continue in $remaining seconds..." -ForegroundColor Gray
            }
            Start-Sleep -Milliseconds 100
        }
    }

    if (-not $keyPressed) {
        Write-Host "`nTimeout reached. Continuing automatically..." -ForegroundColor Yellow
    }

}

# ====================================================================

# SECTION 2: LOGGING AND UTILITIES

# ====================================================================

function Write-Log {
param(
[string]$Message,
        [string]$Level = "INFO"
)

    # Get current timestamp for each log entry
    $currentTimestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$currentTimestamp] [$Level] $Message"

    try {
        # Use the log file from config (without timestamp in name for consistency)
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

function Join-String {
param(
[Parameter(Mandatory=$true, ValueFromPipeline=$true)]
[string[]]$InputObject,
        [string]$Separator = " "
)

    begin {
        $items = @()
    }

    process {
        $items += $InputObject
    }

    end {
        return $items -join $Separator
    }

}

function Test-TimeWindow {
param([string]$TargetTime)

    # Handle empty time string
    if ([string]::IsNullOrWhiteSpace($TargetTime)) {
        Write-Log "Empty time string provided to Test-TimeWindow" -Level "DEBUG"
        return $false
    }

    $now = Get-Date
    try {
        $target = [DateTime]::ParseExact($TargetTime.Trim(), "HH:mm", $null)
        return ($now.TimeOfDay -ge $target.TimeOfDay)
    } catch {
        Write-Log "Invalid time format: '$TargetTime'. Expected format: HH:mm" -Level "ERROR"
        return $false
    }

}

# ====================================================================

# SECTION 3: MAILKIT HANDLING

# ====================================================================

function Test-MailKitCompatibility {
param([string]$DllPath)

    try {
        $fileInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($DllPath)

        $compatibility = @{
            FilePath = $DllPath
            FileVersion = $fileInfo.FileVersion
            ProductVersion = $fileInfo.ProductVersion
            IsCompatible = $false
            Issues = @()
            VersionSpecificNotes = @()
        }

        # Check for MailKit specifically
        if ($fileInfo.ProductName -like "*MailKit*") {
            if ($fileInfo.FileMajorPart -eq 4) {
                if ($fileInfo.FileMinorPart -ge 0) {
                    $compatibility.IsCompatible = $true
                    $compatibility.VersionSpecificNotes += "MailKit 4.x detected - API changes present"
                    $compatibility.VersionSpecificNotes += "TextPart constructor with string format supported"
                    $compatibility.VersionSpecificNotes += "ContentType is read-only - must use constructor"
                }
            } elseif ($fileInfo.FileMajorPart -ge 3) {
                $compatibility.IsCompatible = $true
                $compatibility.VersionSpecificNotes += "MailKit 3.x detected - compatible"
            } else {
                $compatibility.Issues += "Version $($fileInfo.FileVersion) is too old (need 3.0+)"
            }
        }
        # Check for MimeKit
        elseif ($fileInfo.ProductName -like "*MimeKit*") {
            if ($fileInfo.FileMajorPart -ge 3) {
                $compatibility.IsCompatible = $true
            } else {
                $compatibility.Issues += "MimeKit version $($fileInfo.FileVersion) is too old (need 3.0+)"
            }
        }

        return $compatibility
    } catch {
        Write-Log "Failed to check MailKit compatibility: $_" -Level "ERROR"
        return @{
            FilePath = $DllPath
            IsCompatible = $false
            Issues = @("Failed to read version info: $_")
        }
    }

}

function Test-MailKitAssembly {
[CmdletBinding()]
param(
[Parameter(Mandatory=$false)]
[ValidateSet("Portable", "Global", "Auto")]
[string]$VerificationMode = "Auto"
)

    $verificationResult = @{
        IsAvailable = $false
        AssemblyLoadMethod = $null
        AssemblyVersion = $null
        MimeKitVersion = $null
        AssemblyPath = $null
        Issues = @()
        Warnings = @()
        Recommendations = @()
        DependenciesAvailable = $false
        LastChecked = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }

    Write-Log "Starting MailKit assembly verification..." -Level "INFO"

    try {
        # ====================================================================
        # STEP 1: Check if assemblies are already loaded
        # ====================================================================
        $allAssemblies = [AppDomain]::CurrentDomain.GetAssemblies()
        $mailKitLoaded = $allAssemblies | Where-Object { $_.FullName -like "MailKit, *" }
        $mimeKitLoaded = $allAssemblies | Where-Object { $_.FullName -like "MimeKit, *" }

        if ($mailKitLoaded -and $mimeKitLoaded) {
            Write-Log "MailKit is already loaded into current AppDomain" -Level "INFO"
            $verificationResult.IsAvailable = $true
            $verificationResult.AssemblyLoadMethod = "PreLoaded"
            $verificationResult.AssemblyVersion = $mailKitLoaded[0].GetName().Version.ToString()
            $verificationResult.MimeKitVersion = $mimeKitLoaded[0].GetName().Version.ToString()
            $verificationResult.DependenciesAvailable = $true

            Write-Log "  - MailKit Version: $($verificationResult.AssemblyVersion)" -Level "DEBUG"
            Write-Log "  - MimeKit Version: $($verificationResult.MimeKitVersion)" -Level "DEBUG"
            return $verificationResult
        }

        # ====================================================================
        # STEP 2: Portable Verification (DLLs in script directory)
        # ====================================================================
        if (($VerificationMode -eq "Portable") -or ($VerificationMode -eq "Auto")) {
            Write-Log "Checking for portable MailKit DLLs..." -Level "INFO"

            $scriptDir = $PSScriptRoot
            $mailKitDll = Join-Path $scriptDir "MailKit.dll"
            $mimeKitDll = Join-Path $scriptDir "MimeKit.dll"

            # Check if both DLLs exist
            $mailKitExists = Test-Path $mailKitDll
            $mimeKitExists = Test-Path $mimeKitDll

            if ($mailKitExists -and $mimeKitExists) {
                Write-Log "Found portable DLLs in script directory" -Level "INFO"

                # Get file info
                $mailKitFileInfo = Get-Item $mailKitDll
                $mimeKitFileInfo = Get-Item $mimeKitDll

                # Check file sizes are positive
                $mailKitValidSize = ($mailKitFileInfo.Length -gt 0)
                $mimeKitValidSize = ($mimeKitFileInfo.Length -gt 0)

                if ($mailKitValidSize -and $mimeKitValidSize) {
                    try {
                        # Test loading the assemblies
                        Write-Log "Testing assembly loading..." -Level "DEBUG"

                        # Load MimeKit first (dependency)
                        Add-Type -Path $mimeKitDll -ErrorAction Stop
                        Write-Log "  - MimeKit loaded successfully" -Level "DEBUG"

                        # Then load MailKit
                        Add-Type -Path $mailKitDll -ErrorAction Stop
                        Write-Log "  - MailKit loaded successfully" -Level "DEBUG"

                        # Get version information
                        $loadedAssemblies = [AppDomain]::CurrentDomain.GetAssemblies()
                        $mailKitAssembly = $loadedAssemblies | Where-Object { $_.Location -and $_.Location -eq $mailKitDll } | Select-Object -First 1
                        $mimeKitAssembly = $loadedAssemblies | Where-Object { $_.Location -and $_.Location -eq $mimeKitDll } | Select-Object -First 1

                        if ($mailKitAssembly -and $mimeKitAssembly) {
                            $verificationResult.IsAvailable = $true
                            $verificationResult.AssemblyLoadMethod = "Portable"
                            $verificationResult.AssemblyVersion = $mailKitAssembly.GetName().Version.ToString()
                            $verificationResult.MimeKitVersion = $mimeKitAssembly.GetName().Version.ToString()
                            $verificationResult.AssemblyPath = $scriptDir
                            $verificationResult.DependenciesAvailable = $true

                            Write-Log "Portable MailKit verification PASSED" -Level "SUCCESS"
                            Write-Log "  - Assembly Path: $scriptDir" -Level "DEBUG"
                            Write-Log "  - MailKit Version: $($verificationResult.AssemblyVersion)" -Level "DEBUG"
                            Write-Log "  - MimeKit Version: $($verificationResult.MimeKitVersion)" -Level "DEBUG"

                            return $verificationResult
                        }
                    } catch {
                        $errorMsg = "Failed to load portable DLLs: $($_.Exception.Message)"
                        Write-Log $errorMsg -Level "ERROR"
                        $verificationResult.Issues += $errorMsg
                        $verificationResult.Recommendations += "Check if DLLs are corrupted or incompatible"
                    }
                }
            }
        }

        # ====================================================================
        # STEP 3: Global/GAC Verification
        # ====================================================================
        if (($VerificationMode -eq "Global") -or (($VerificationMode -eq "Auto") -and (-not $verificationResult.IsAvailable))) {
            Write-Log "Checking for globally installed MailKit..." -Level "INFO"

            try {
                # Try to load from GAC/System
                Add-Type -AssemblyName "MimeKit" -ErrorAction Stop
                Write-Log "  - MimeKit loaded from GAC" -Level "DEBUG"

                Add-Type -AssemblyName "MailKit" -ErrorAction Stop
                Write-Log "  - MailKit loaded from GAC" -Level "DEBUG"

                # Get version information
                $loadedAssemblies = [AppDomain]::CurrentDomain.GetAssemblies()
                $mailKitAssembly = $loadedAssemblies | Where-Object { $_.FullName -like "MailKit, *" } | Select-Object -First 1
                $mimeKitAssembly = $loadedAssemblies | Where-Object { $_.FullName -like "MimeKit, *" } | Select-Object -First 1

                if ($mailKitAssembly -and $mimeKitAssembly) {
                    $verificationResult.IsAvailable = $true
                    $verificationResult.AssemblyLoadMethod = "Global"
                    $verificationResult.AssemblyVersion = $mailKitAssembly.GetName().Version.ToString()
                    $verificationResult.MimeKitVersion = $mimeKitAssembly.GetName().Version.ToString()
                    $verificationResult.DependenciesAvailable = $true

                    Write-Log "Global MailKit verification PASSED" -Level "SUCCESS"
                    Write-Log "  - MailKit Version: $($verificationResult.AssemblyVersion)" -Level "DEBUG"
                    Write-Log "  - MimeKit Version: $($verificationResult.MimeKitVersion)" -Level "DEBUG"

                    return $verificationResult
                }
            } catch {
                $errorMsg = "Failed to load from GAC: $($_.Exception.Message)"
                Write-Log $errorMsg -Level "WARN"
                $verificationResult.Issues += $errorMsg
            }
        }

        # ====================================================================
        # STEP 4: Verification Failed - Provide detailed analysis
        # ====================================================================
        if (-not $verificationResult.IsAvailable) {
            Write-Log "MailKit assembly verification FAILED" -Level "ERROR"

            # Check for common issues
            if ($verificationResult.Issues.Count -eq 0) {
                $verificationResult.Issues += "No MailKit assembly found in any searched location"
            }

            # Provide specific recommendations
            $verificationResult.Recommendations += "Download MailKit.dll and MimeKit.dll from NuGet"
            $verificationResult.Recommendations += "Place both DLLs in: $PSScriptRoot"
            $verificationResult.Recommendations += "Verify .NET Framework 4.7.2+ or .NET Core 2.0+ is installed"

            # Log detailed failure report
            Write-Log "Detailed failure report:" -Level "ERROR"
            Write-Log "  - Issues found: $($verificationResult.Issues.Count)" -Level "ERROR"
            foreach ($issue in $verificationResult.Issues) {
                Write-Log "    * $issue" -Level "ERROR"
            }
        }

    } catch {
        $errorMsg = "Unexpected error during MailKit verification: $($_.Exception.Message)"
        Write-Log $errorMsg -Level "ERROR"
        $verificationResult.Issues += $errorMsg
    }

    return $verificationResult

}

function Get-MailKitVersionInfo {
try {
$allAssemblies = [AppDomain]::CurrentDomain.GetAssemblies()
$mailKitAssembly = $allAssemblies | Where-Object { $_.FullName -like "MailKit, \*" } | Select-Object -First 1
$mimeKitAssembly = $allAssemblies | Where-Object { $_.FullName -like "MimeKit, \*" } | Select-Object -First 1

        $info = @{
            MailKitVersion = if ($mailKitAssembly) { $mailKitAssembly.GetName().Version.ToString() } else { "Unknown" }
            MimeKitVersion = if ($mimeKitAssembly) { $mimeKitAssembly.GetName().Version.ToString() } else { "Unknown" }
            MailKitMajorVersion = if ($mailKitAssembly) { $mailKitAssembly.GetName().Version.Major } else { 0 }
            MimeKitMajorVersion = if ($mimeKitAssembly) { $mimeKitAssembly.GetName().Version.Major } else { 0 }
            IsVersion4OrHigher = $false
            CompatibilityNotes = @()
        }

        # Check for MailKit 4.0+
        if ($info.MailKitMajorVersion -ge 4) {
            $info.IsVersion4OrHigher = $true
            $info.CompatibilityNotes += "MailKit 4.0+ detected - using updated BodyBuilder API"
        } else {
            $info.CompatibilityNotes += "MailKit 3.x detected - using legacy Multipart API"
        }

        return $info
    } catch {
        Write-Log "Failed to get MailKit version info: $_" -Level "ERROR"
        return @{
            MailKitVersion = "Unknown"
            MimeKitVersion = "Unknown"
            IsVersion4OrHigher = $false
            CompatibilityNotes = @("Error detecting version")
        }
    }

}

function Get-MailKitStatusReport {
[CmdletBinding()]
param()

    Write-Log "Generating MailKit status report..." -Level "INFO"

    # Initialize report with safe defaults
    $report = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        AssemblyStatus = @{
            IsAvailable = $false
            AssemblyLoadMethod = "Unknown"
            AssemblyVersion = "Unknown"
            MimeKitVersion = "Unknown"
            DependenciesAvailable = $false
            Issues = @()
            Warnings = @()
            Recommendations = @()
        }
        ConfigurationStatus = @{
            EmailEnabled = if ($Config.SendEmailOnCompletion -ne $null) { $Config.SendEmailOnCompletion } else { $false }
            SmtpConfigured = -not [string]::IsNullOrWhiteSpace($Config.SmtpServer)
            CredentialFileExists = Test-Path $Config.EmailCredentialPath
            RecipientsConfigured = ($Config.EmailRecipients -and $Config.EmailRecipients.Count -gt 0)
            SmtpServer = if ($Config.SmtpServer) { $Config.SmtpServer } else { "Not configured" }
            SmtpPort = if ($Config.SmtpPort) { $Config.SmtpPort } else { 0 }
            UseSSL = if ($Config.UseSSL -ne $null) { $Config.UseSSL } else { $true }
        }
        SystemInfo = @{
            PowerShellVersion = $PSVersionTable.PSVersion.ToString()
            CLRVersion = if ($PSVersionTable.CLRVersion) { $PSVersionTable.CLRVersion.ToString() } else { "Unknown" }
            OS = [System.Environment]::OSVersion.VersionString
            HostName = $env:COMPUTERNAME
        }
        Recommendations = @()
        OverallStatus = "ERROR"
    }

    try {
        # Get assembly status with error handling
        $assemblyStatus = Test-MailKitAssembly -VerificationMode "Auto"

        if ($assemblyStatus -and ($assemblyStatus.GetType().Name -eq 'Hashtable')) {
            $report.AssemblyStatus = $assemblyStatus
        } else {
            Write-Log "MailKit assembly test returned invalid result" -Level "WARN"
            $report.AssemblyStatus.IsAvailable = $false
            $report.AssemblyStatus.Issues += "Assembly test returned invalid result"
            $report.AssemblyStatus.Recommendations += "Reinstall MailKit and MimeKit DLLs"
        }

        # Determine overall status with safe checks
        $assemblyAvailable = $report.AssemblyStatus.IsAvailable
        $emailEnabled = $report.ConfigurationStatus.EmailEnabled
        $smtpConfigured = $report.ConfigurationStatus.SmtpConfigured
        $credentialExists = $report.ConfigurationStatus.CredentialFileExists

        if ($assemblyAvailable -and $emailEnabled -and $smtpConfigured -and $credentialExists) {
            $report.OverallStatus = "READY"
        } elseif (-not $assemblyAvailable) {
            $report.OverallStatus = "MISSING_ASSEMBLY"
            $report.Recommendations += "MailKit assembly not found. Install or provide DLLs."
        } elseif (-not $emailEnabled) {
            $report.OverallStatus = "EMAIL_DISABLED"
        } elseif (-not $smtpConfigured) {
            $report.OverallStatus = "SMTP_NOT_CONFIGURED"
            $report.Recommendations += "Configure SMTP server in configuration"
        } elseif (-not $credentialExists) {
            $report.OverallStatus = "CREDENTIAL_MISSING"
            $report.Recommendations += "Create credential file at: $($Config.EmailCredentialPath)"
        } else {
            $report.OverallStatus = "UNKNOWN"
        }

    } catch {
        Write-Log "Error in Get-MailKitStatusReport: $_" -Level "ERROR"
        $report.OverallStatus = "ERROR"
        $report.Recommendations += "Error checking MailKit status: $_"
    }

    return $report

}

function Write-MailKitStatusLog {
[CmdletBinding()]
param(
[Parameter(Mandatory=$false)]
[string]$LogFile = $null
)

    if ([string]::IsNullOrWhiteSpace($LogFile)) {
        $LogFile = $Config.LogFile
    }

    $statusReport = Get-MailKitStatusReport

    # SAFE property access with defaults
    $assemblyStatus = if ($statusReport.AssemblyStatus) { $statusReport.AssemblyStatus } else { @{ IsAvailable = $false } }
    $isAvailable = if ($assemblyStatus.IsAvailable -ne $null) { $assemblyStatus.IsAvailable } else { $false }
    $loadMethod = if ($assemblyStatus.AssemblyLoadMethod) { $assemblyStatus.AssemblyLoadMethod } else { 'Unknown' }
    $mailKitVersion = if ($assemblyStatus.AssemblyVersion) { $assemblyStatus.AssemblyVersion } else { 'Unknown' }
    $mimeKitVersion = if ($assemblyStatus.MimeKitVersion) { $assemblyStatus.MimeKitVersion } else { 'Unknown' }
    $depsAvailable = if ($assemblyStatus.DependenciesAvailable -ne $null) { $assemblyStatus.DependenciesAvailable } else { $false }

    $logEntry = @"

=== MAILKIT STATUS REPORT ===
Timestamp: $($statusReport.Timestamp)
Overall Status: $($statusReport.OverallStatus)

ASSEMBLY STATUS:

- Available: $isAvailable
- Load Method: $loadMethod
- MailKit Version: $mailKitVersion
- MimeKit Version: $mimeKitVersion
- Dependencies: $depsAvailable

CONFIGURATION STATUS:

- Email Enabled: $($statusReport.ConfigurationStatus.EmailEnabled)
- SMTP Configured: $($statusReport.ConfigurationStatus.SmtpConfigured)
- Credential File: $($statusReport.ConfigurationStatus.CredentialFileExists)
- Recipients: $($statusReport.ConfigurationStatus.RecipientsConfigured)
- SMTP Server: $($statusReport.ConfigurationStatus.SmtpServer)
- SMTP Port: $($statusReport.ConfigurationStatus.SmtpPort)
- SSL: $($statusReport.ConfigurationStatus.UseSSL)

SYSTEM INFORMATION:

- PowerShell: $($statusReport.SystemInfo.PowerShellVersion)
- CLR: $($statusReport.SystemInfo.CLRVersion)
- OS: $($statusReport.SystemInfo.OS)
- Host: $($statusReport.SystemInfo.HostName)

RECOMMENDATIONS:
$($statusReport.Recommendations -join "`n")
"@

    try {
        Add-Content -Path $LogFile -Value $logEntry -ErrorAction SilentlyContinue
        Write-Log "MailKit status report written to log" -Level "INFO"
    } catch {
        Write-Log "Failed to write MailKit status report: $_" -Level "ERROR"
    }

}

function Send-Email {
param(
[string[]]$To,
        [string]$From,
[string]$Subject,
        [string]$Body,
[string]$SmtpServer,
        [int]$Port,
[bool]$UseSsl,
        [System.Management.Automation.PSCredential]$Credential,
[string[]]$Attachments
)

    # First try MailKit
    $mailKitResult = Send-MailKitEmail @PSBoundParameters

    if ($mailKitResult) {
        return $true
    }

    # If MailKit fails, try System.Net.Mail fallback
    Write-Log "MailKit failed, attempting System.Net.Mail fallback..." -Level "WARN"
    return Send-SystemNetMailEmail @PSBoundParameters

}

function Send-MailKitEmail {
param(
[string[]]$To,
        [string]$From,
[string]$Subject,
        [string]$Body,
[string]$SmtpServer,
        [int]$Port,
[bool]$UseSsl,
        [System.Management.Automation.PSCredential]$Credential,
[string[]]$Attachments
)

    try {
        # Get version info first
        $versionInfo = Get-MailKitVersionInfo

        # Load MailKit assembly with fallback
        $assemblyLoaded = $false
        try {
            Add-Type -Path "MailKit.dll" -ErrorAction Stop
            $assemblyLoaded = $true
        } catch {
            try {
                Add-Type -AssemblyName "MailKit" -ErrorAction Stop
                $assemblyLoaded = $true
            } catch {
                Write-Log "MailKit assembly not found" -Level "WARN"
                return $false
            }
        }

        if (-not $assemblyLoaded) {
            return $false
        }

        # Create MIME message
        $message = New-Object MimeKit.MimeMessage
        $message.From.Add([MimeKit.InternetAddress]::Parse($From))

        foreach ($recipient in $To) {
            $message.To.Add([MimeKit.InternetAddress]::Parse($recipient))
        }

        $message.Subject = $Subject

        # Handle MailKit 4.0+ API changes
        if ($versionInfo.IsVersion4OrHigher) {
            Write-Log "Using MailKit 4.0+ API for message construction" -Level "DEBUG"

            # MailKit 4.0+ approach
            $bodyBuilder = New-Object MimeKit.BodyBuilder

            if ($Body -match '<.*>') {
                # HTML content
                $bodyBuilder.HtmlBody = $Body
            } else {
                # Plain text content
                $bodyBuilder.TextBody = $Body
            }

            # Add attachments if any
            if ($Attachments.Count -gt 0) {
                foreach ($attachmentPath in $Attachments) {
                    if (Test-Path $attachmentPath) {
                        $bodyBuilder.Attachments.Add($attachmentPath)
                        Write-Log "Added attachment using BodyBuilder: $attachmentPath" -Level "DEBUG"
                    }
                }
            }

            $message.Body = $bodyBuilder.ToMessageBody()

        } else {
            # MailKit 3.x approach (backward compatibility)
            Write-Log "Using MailKit 3.x API for message construction" -Level "DEBUG"

            # Create body part
            if ($Body -match '<.*>') {
                # HTML content
                $bodyPart = New-Object MimeKit.TextPart("html")
                $bodyPart.Text = $Body
            } else {
                # Plain text content
                $bodyPart = New-Object MimeKit.TextPart("plain")
                $bodyPart.Text = $Body
            }

            # Handle attachments for MailKit 3.x
            if ($Attachments.Count -gt 0) {
                $multipart = New-Object MimeKit.Multipart("mixed")
                $multipart.Add($bodyPart)

                foreach ($attachmentPath in $Attachments) {
                    if (Test-Path $attachmentPath) {
                        $attachment = New-MimeKitAttachment -FilePath $attachmentPath
                        if ($attachment) {
                            $multipart.Add($attachment)
                        }
                    }
                }

                $message.Body = $multipart
            } else {
                $message.Body = $bodyPart
            }
        }

        # Send email using MailKit SmtpClient
        $client = New-Object MailKit.Net.Smtp.SmtpClient

        try {
            Write-Log "Connecting to SMTP server ${SmtpServer}:${Port} (SSL: ${UseSsl})..." -Level "DEBUG"

            # Connect to SMTP server
            if ($Port -eq 587) {
                # Port 587 requires STARTTLS
                $client.Connect($SmtpServer, $Port, [MailKit.Security.SecureSocketOptions]::StartTls)
            } elseif ($UseSsl) {
                # Port 465 or other SSL ports
                $client.Connect($SmtpServer, $Port, [MailKit.Security.SecureSocketOptions]::SslOnConnect)
            } else {
                # No SSL
                $client.Connect($SmtpServer, $Port, [MailKit.Security.SecureSocketOptions]::None)
            }

            # Authenticate
            $networkCredential = $Credential.GetNetworkCredential()
            Write-Log "Authenticating as $($networkCredential.UserName)..." -Level "DEBUG"

            $client.Authenticate($networkCredential.UserName, $networkCredential.Password)

            # Send email
            Write-Log "Sending email..." -Level "DEBUG"
            $client.Send($message)

            # Disconnect
            $client.Disconnect($true)

            Write-Log "Email sent successfully using MailKit" -Level "SUCCESS"
            return $true

        } catch {
            Write-Log "MailKit SMTP error: $($_.Exception.Message)" -Level "ERROR"
            return $false
        }

    } catch {
        Write-Log "Failed to send email using MailKit: $($_.Exception.Message)" -Level "ERROR"
        return $false
    }

}

function Send-SystemNetMailEmail {
param(
[string[]]$To,
        [string]$From,
[string]$Subject,
        [string]$Body,
[string]$SmtpServer,
        [int]$Port,
[bool]$UseSsl,
        [System.Management.Automation.PSCredential]$Credential,
[string[]]$Attachments
)

    try {
        Write-Log "Attempting fallback email using System.Net.Mail..." -Level "WARN"

        # Create mail message
        $mailMessage = New-Object System.Net.Mail.MailMessage
        $mailMessage.From = New-Object System.Net.Mail.MailAddress($From)

        foreach ($recipient in $To) {
            $mailMessage.To.Add($recipient)
        }

        $mailMessage.Subject = $Subject
        $mailMessage.Body = $Body
        $mailMessage.IsBodyHtml = $Body -match '<.*>'

        # Add attachments
        foreach ($attachmentPath in $Attachments) {
            if (Test-Path $attachmentPath) {
                $attachment = New-Object System.Net.Mail.Attachment($attachmentPath)
                $mailMessage.Attachments.Add($attachment)
                Write-Log "Added attachment: $attachmentPath" -Level "DEBUG"
            }
        }

        # Create SMTP client
        $smtpClient = New-Object System.Net.Mail.SmtpClient($SmtpServer, $Port)
        $smtpClient.EnableSsl = $UseSsl
        $smtpClient.Timeout = 30000

        # Set credentials
        $networkCredential = $Credential.GetNetworkCredential()
        $smtpClient.Credentials = New-Object System.Net.NetworkCredential($networkCredential.UserName, $networkCredential.Password)

        # Send email
        $smtpClient.Send($mailMessage)

        # Cleanup
        $mailMessage.Dispose()
        if ($smtpClient -ne $null) {
            $smtpClient.Dispose()
        }

        Write-Log "Fallback email sent successfully using System.Net.Mail" -Level "SUCCESS"
        return $true

    } catch {
        Write-Log "Fallback email also failed: $_" -Level "ERROR"
        return $false
    }

}

function New-MimeKitAttachment {
param(
[string]$FilePath,
        [string]$MimeType = "application/octet-stream"
)

    try {
        if (-not (Test-Path $FilePath)) {
            throw "File not found: $FilePath"
        }

        $fileName = [System.IO.Path]::GetFileName($FilePath)

        # Try MailKit 4.0+ approach first
        try {
            # Method 1: Create with explicit content type
            $contentType = New-Object MimeKit.ContentType($MimeType)
            $contentType.Name = $fileName

            $attachment = New-Object MimeKit.MimePart
            $attachment.ContentType = $contentType

            # Set other properties
            $disposition = New-Object MimeKit.ContentDisposition([MimeKit.ContentDisposition]::Attachment)
            $disposition.FileName = $fileName
            $attachment.ContentDisposition = $disposition

            $attachment.ContentTransferEncoding = [MimeKit.ContentEncoding]::Base64

            $fileStream = [System.IO.File]::OpenRead($FilePath)
            $attachment.Content = New-Object MimeKit.MimeContent($fileStream)

            Write-Log "Created attachment using MailKit 4.0+ API" -Level "DEBUG"
            return $attachment

        } catch {
            # Fallback: Try MailKit 3.0 approach
            Write-Log "MailKit 4.0+ API failed, trying 3.0 compatible approach..." -Level "DEBUG"

            $attachment = New-Object MimeKit.MimePart

            # For MailKit 3.0, we can set ContentType.MediaType and ContentType.MediaSubtype
            $attachment.ContentType.MediaType = $MimeType.Split('/')[0]
            $attachment.ContentType.MediaSubtype = $MimeType.Split('/')[1]
            $attachment.ContentType.Parameters.Add("name", $fileName)

            $disposition = New-Object MimeKit.ContentDisposition([MimeKit.ContentDisposition]::Attachment)
            $disposition.Parameters.Add("filename", $fileName)
            $attachment.ContentDisposition = $disposition

            $attachment.ContentTransferEncoding = [MimeKit.ContentEncoding]::Base64

            $fileStream = [System.IO.File]::OpenRead($FilePath)
            $attachment.Content = New-Object MimeKit.MimeContent($fileStream)

            Write-Log "Created attachment using MailKit 3.0 compatible API" -Level "DEBUG"
            return $attachment
        }

    } catch {
        Write-Log "Failed to create MimeKit attachment: $_" -Level "ERROR"
        return $null
    }

}

function Test-MailKitDLLs {
param(
[string]$ScriptDir = $PSScriptRoot
)

    Write-Host "Testing MailKit DLLs in: $ScriptDir" -ForegroundColor Cyan

    $mailKitDll = Join-Path $ScriptDir "MailKit.dll"
    $mimeKitDll = Join-Path $ScriptDir "MimeKit.dll"

    # Check if files exist
    if (-not (Test-Path $mailKitDll)) {
        Write-Host "ERROR: MailKit.dll not found at: $mailKitDll" -ForegroundColor Red
        return $false
    }

    if (-not (Test-Path $mimeKitDll)) {
        Write-Host "ERROR: MimeKit.dll not found at: $mimeKitDll" -ForegroundColor Red
        return $false
    }

    # Check compatibility
    Write-Host "`nChecking DLL compatibility..." -ForegroundColor Cyan

    $mailKitCompat = Test-MailKitCompatibility -DllPath $mailKitDll
    $mimeKitCompat = Test-MailKitCompatibility -DllPath $mimeKitDll

    if (-not $mailKitCompat.IsCompatible) {
        Write-Host "ERROR: MailKit DLL compatibility issues:" -ForegroundColor Red
        foreach ($issue in $mailKitCompat.Issues) {
            Write-Host "  - $issue" -ForegroundColor Red
        }
    }

    if (-not $mimeKitCompat.IsCompatible) {
        Write-Host "ERROR: MimeKit DLL compatibility issues:" -ForegroundColor Red
        foreach ($issue in $mimeKitCompat.Issues) {
            Write-Host "  - $issue" -ForegroundColor Red
        }
    }

    Write-Host "✓ Both DLL files found" -ForegroundColor Green

    # Check file sizes
    $mailKitSize = (Get-Item $mailKitDll).Length
    $mimeKitSize = (Get-Item $mimeKitDll).Length

    Write-Host "  MailKit.dll size: $([math]::Round($mailKitSize/1KB, 2)) KB" -ForegroundColor Gray
    Write-Host "  MimeKit.dll size: $([math]::Round($mimeKitSize/1KB, 2)) KB" -ForegroundColor Gray

    if ($mailKitSize -eq 0 -or $mimeKitSize -eq 0) {
        Write-Host "ERROR: One or both DLLs have zero file size" -ForegroundColor Red
        return $false
    }

    Write-Host "✓ File sizes are valid" -ForegroundColor Green

    # Try to load the assemblies
    try {
        Write-Host "Attempting to load MimeKit..." -ForegroundColor Yellow
        Add-Type -Path $mimeKitDll -ErrorAction Stop
        Write-Host "✓ MimeKit loaded successfully" -ForegroundColor Green

        Write-Host "Attempting to load MailKit..." -ForegroundColor Yellow
        Add-Type -Path $mailKitDll -ErrorAction Stop
        Write-Host "✓ MailKit loaded successfully" -ForegroundColor Green

        # Get version info
        $assemblies = [AppDomain]::CurrentDomain.GetAssemblies()
        $mailKitAssembly = $assemblies | Where-Object { $_.Location -and $_.Location -eq $mailKitDll }
        $mimeKitAssembly = $assemblies | Where-Object { $_.Location -and $_.Location -eq $mimeKitDll }

        if ($mailKitAssembly) {
            $version = $mailKitAssembly.GetName().Version
            Write-Host "✓ MailKit Version: $version" -ForegroundColor Green
        }

        if ($mimeKitAssembly) {
            $version = $mimeKitAssembly.GetName().Version
            Write-Host "✓ MimeKit Version: $version" -ForegroundColor Green
        }

        Write-Host "`nSUCCESS: All MailKit tests passed!" -ForegroundColor Green
        return $true

    } catch {
        Write-Host "ERROR: Failed to load DLLs: $_" -ForegroundColor Red
        Write-Host "Stack trace: $($_.ScriptStackTrace)" -ForegroundColor Red
        return $false
    }

}

# ====================================================================

# SECTION 4: SUDDEN TERMINATION HANDLING

# ====================================================================

function Register-SuddenTermination {
param(
[string]$Reason,
        [string]$TerminationType = "Unexpected",
[hashtable]$ProcessInfo = @{}
)

    $event = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Reason = $Reason
        TerminationType = $TerminationType
        ProcessInfo = $ProcessInfo
        ScriptVersion = "2.0"
        HostName = $env:COMPUTERNAME
    }

    # Add to events list
    $SuddenTerminationTracking.Events += $event

    # Update statistics
    $SuddenTerminationTracking.Statistics.TotalSuddenTerminations++
    $SuddenTerminationTracking.Statistics.LastEventDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    if (-not $SuddenTerminationTracking.Statistics.FirstEventDate) {
        $SuddenTerminationTracking.Statistics.FirstEventDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }

    # Calculate streak - check if last event was also a sudden termination
    if ($SuddenTerminationTracking.Events.Count -gt 1) {
        $lastEvent = $SuddenTerminationTracking.Events[-2]
        $lastEventTime = [DateTime]::ParseExact($lastEvent.Timestamp, "yyyy-MM-dd HH:mm:ss", $null)
        $currentTime = Get-Date

        # If last sudden termination was within 5 minutes, consider it consecutive
        if (($currentTime - $lastEventTime).TotalMinutes -le 5) {
            $SuddenTerminationTracking.CurrentStreak++
            Write-Log "Consecutive sudden termination detected. Streak: $($SuddenTerminationTracking.CurrentStreak)" -Level "WARN"
        } else {
            # Reset streak if more than 5 minutes have passed
            $SuddenTerminationTracking.CurrentStreak = 1
            Write-Log "New sudden termination streak started" -Level "INFO"
        }
    } else {
        $SuddenTerminationTracking.CurrentStreak = 1
    }

    # Check if we need to take action based on consecutive sudden terminations
    if ($SuddenTerminationTracking.CurrentStreak -ge $Config.SuddenTermination.ConsecutiveThreshold) {
        Write-Log "Sudden termination streak threshold reached ($($SuddenTerminationTracking.CurrentStreak) consecutive). Taking cleanup action." -Level "ERROR"
        Invoke-StreakThresholdAction
    }

    # Save tracking data
    Save-SuddenTerminationTracking

    return $event

}

function Save-SuddenTerminationTracking {
try { # Clean up old events beyond retention period
$retentionDate = (Get-Date).AddDays(-$Config.SuddenTermination.RecordRetentionDays)
$filteredEvents = @()

        foreach ($event in $SuddenTerminationTracking.Events) {
            $eventTime = [DateTime]::ParseExact($event.Timestamp, "yyyy-MM-dd HH:mm:ss", $null)
            if ($eventTime -ge $retentionDate) {
                $filteredEvents += $event
            }
        }

        $SuddenTerminationTracking.Events = $filteredEvents

        # Save to file
        $SuddenTerminationTracking | ConvertTo-Json -Depth 5 | Out-File -FilePath $Config.SuddenTermination.TrackingFile -Force
        Write-Log "Sudden termination tracking saved" -Level "DEBUG"
    } catch {
        Write-Log "Failed to save sudden termination tracking: $_" -Level "ERROR"
    }

}

function Load-SuddenTerminationTracking {
if (-not (Test-Path $Config.SuddenTermination.TrackingFile)) {
Write-Log "No sudden termination tracking file found" -Level "DEBUG"
return $false
}

    try {
        $loaded = Get-Content -Path $Config.SuddenTermination.TrackingFile -Raw | ConvertFrom-Json

        # Convert back to hashtable and update global variable
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

        Write-Log "Loaded sudden termination tracking: $($SuddenTerminationTracking.Statistics.TotalSuddenTerminations) total events, current streak: $($SuddenTerminationTracking.CurrentStreak)" -Level "INFO"
        return $true
    } catch {
        Write-Log "Failed to load sudden termination tracking: $_" -Level "ERROR"
        return $false
    }

}

function Invoke-StreakThresholdAction {
$action = $Config.SuddenTermination.CleanupAction
$streak = $SuddenTerminationTracking.CurrentStreak

    Write-Log "Executing cleanup action '$action' for streak of $streak consecutive sudden terminations" -Level "WARN"

    switch ($action) {
        "ForceCleanupAndNotify" {
            # Force cleanup of all processes
            Force-CleanupOrphanedProcesses

            # Update statistics
            $SuddenTerminationTracking.Statistics.TotalCleanups++
            $SuddenTerminationTracking.Statistics.LastCleanupReason = "ConsecutiveSuddenTerminations"
            $SuddenTerminationTracking.LastCleanupDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

            # Reset streak after cleanup
            $SuddenTerminationTracking.CurrentStreak = 0

            # Send notification if email is configured
            if ($Config.SendEmailOnCompletion) {
                Send-StreakNotification -StreakCount $streak -ActionTaken $action
            }

            Save-SuddenTerminationTracking
        }

        "ForceCleanupOnly" {
            Force-CleanupOrphanedProcesses
            $SuddenTerminationTracking.CurrentStreak = 0
            Save-SuddenTerminationTracking
        }

        "LogOnly" {
            Write-Log "Logging threshold reached but no action taken (config: LogOnly)" -Level "WARN"
        }

        default {
            Write-Log "Unknown cleanup action: $action" -Level "ERROR"
        }
    }

}

function Force-CleanupOrphanedProcesses {
Write-Log "Starting forced cleanup of orphaned processes..." -Level "WARN"

    $cleanedProcesses = @()

    # Clean up any Python processes with our script
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*python*" }

    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Config.PythonScriptPath)*") {
                Write-Log "Forcefully terminating orphaned Python process (PID: $($proc.Id))" -Level "WARN"
                $proc.Kill()
                if ($proc.WaitForExit(5000)) {
                    $cleanedProcesses += "Python:$($proc.Id)"
                }
            }
        } catch {
            Write-Log "Error cleaning up Python process $($proc.Id): $_" -Level "ERROR"
        }
    }

    # Clean up worker PowerShell processes
    $workerProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "*powershell*" }

    foreach ($proc in $workerProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Config.WorkerScript)*") {
                Write-Log "Forcefully terminating orphaned worker process (PID: $($proc.Id))" -Level "WARN"
                $proc.Kill()
                if ($proc.WaitForExit(5000)) {
                    $cleanedProcesses += "Worker:$($proc.Id)"
                }
            }
        } catch {
            Write-Log "Error cleaning up worker process $($proc.Id): $_" -Level "ERROR"
        }
    }

    # Clean up PID tracking file if it exists
    if (Test-Path $Config.PIDFilePath) {
        try {
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            Write-Log "Cleaned up PID tracking file" -Level "INFO"
        } catch {
            Write-Log "Failed to clean up PID tracking file: $_" -Level "ERROR"
        }
    }

    # Reset global process variables
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false

    Write-Log "Forced cleanup completed. Cleaned processes: $($cleanedProcesses.Count)" -Level "INFO"

    if ($cleanedProcesses.Count -gt 0) {
        Write-Log "Details: $($cleanedProcesses -join ', ')" -Level "INFO"
    }

    return $cleanedProcesses

}

function Send-StreakNotification {
param(
[int]$StreakCount,
        [string]$ActionTaken
)

    if (-not $Config.SendEmailOnCompletion) {
        return $false
    }

    try {
        # Load credentials
        $credential = $null
        if (Test-Path $Config.EmailCredentialPath) {
            $credential = Import-Clixml -Path $Config.EmailCredentialPath
        } else {
            return $false
        }

        $subject = "ALERT: $StreakCount Consecutive Sudden Terminations - Face Recognition Monitor"

        $body = @"

# URGENT: CONSECUTIVE SUDDEN TERMINATIONS ALERT

## ALERT DETAILS

Alert Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Streak Count: $StreakCount consecutive sudden terminations
Action Taken: $ActionTaken
Host: $($env:COMPUTERNAME)

## STATISTICS

Total Sudden Terminations: $($SuddenTerminationTracking.Statistics.TotalSuddenTerminations)
Current Streak: $($SuddenTerminationTracking.CurrentStreak)
Total Cleanups Performed: $($SuddenTerminationTracking.Statistics.TotalCleanups)
First Event: $($SuddenTerminationTracking.Statistics.FirstEventDate)
Last Event: $($SuddenTerminationTracking.Statistics.LastEventDate)

## RECENT EVENTS (Last 5)

$($SuddenTerminationTracking.Events[-5..-1] | ForEach-Object {
"- $($_.Timestamp): $($_.Reason) ($($\_.TerminationType))"
} | Join-String -Separator "`n")

## AUTOMATIC ACTIONS

The system has automatically performed cleanup of orphaned processes.
Please check the monitor log for details: $($Config.LogFile)

## RECOMMENDATIONS

1. Check system resources (CPU, Memory, Disk)
2. Verify network connectivity if applicable
3. Review recent changes to scripts or configurations
4. Check for conflicting processes
5. Monitor system event logs for errors

## MONITOR STATUS

Worker PID: $(if ($WorkerPID) {$WorkerPID} else {'Not Running'})
Python PID: $(if ($PythonPID) {$PythonPID} else {'Not Running'})
Schedule: $($Config.StartTime) - $($Config.EndTime)

"@

        # Send to all configured recipients
        $recipients = $Config.EmailRecipients | ForEach-Object { $_.Address }

        $emailSent = Send-Email -To $recipients -From $Config.EmailFrom `
            -Subject $subject -Body $body -SmtpServer $Config.SmtpServer `
            -Port $Config.SmtpPort -UseSsl $Config.UseSSL -Credential $credential

        if ($emailSent) {
            Write-Log "Streak notification sent to $($recipients.Count) recipients" -Level "INFO"
            return $true
        }

        return $false
    } catch {
        Write-Log "Failed to send streak notification: $_" -Level "ERROR"
        return $false
    }

}

function Initialize-CleanupOnStartup {
Write-Log "Performing startup cleanup check..." -Level "INFO"

    # Load sudden termination tracking
    Load-SuddenTerminationTracking

    # Check for orphaned processes
    $orphanedProcesses = @()

    # Check Python processes
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*python*" }

    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Config.PythonScriptPath)*") {
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
            if ($cmdLine -like "*$($Config.WorkerScript)*") {
                $orphanedProcesses += @{
                    Type = "Worker"
                    PID = $proc.Id
                    StartTime = $proc.StartTime
                }
            }
        } catch { }
    }

    # If we found orphaned processes, clean them up
    if ($orphanedProcesses.Count -gt 0) {
        Write-Log "Found $($orphanedProcesses.Count) orphaned process(es) from previous run" -Level "WARN"

        foreach ($orphan in $orphanedProcesses) {
            Write-Log "  - $($orphan.Type) process (PID: $($orphan.PID), Started: $($orphan.StartTime))" -Level "WARN"
        }

        # Register a sudden termination event
        Register-SuddenTermination -Reason "Orphaned processes found on startup" `
            -TerminationType "StartupCleanup" `
            -ProcessInfo @{ OrphanedProcesses = $orphanedProcesses }

        # Clean up the orphaned processes
        Force-CleanupOrphanedProcesses

        return $true
    }

    Write-Log "No orphaned processes found on startup" -Level "INFO"
    return $false

}

function Handle-UnexpectedTermination {
param(
[string]$Reason,
        [System.Management.Automation.ErrorRecord]$ErrorRecord = $null
)

    Write-Log "Handling unexpected termination: $Reason" -Level "ERROR"

    if ($ErrorRecord) {
        Write-Log "Error details: $($ErrorRecord.Exception.Message)" -Level "ERROR"
        Write-Log "Stack trace: $($ErrorRecord.ScriptStackTrace)" -Level "ERROR"
    }

    # Capture current process state before cleanup
    $processState = @{
        WorkerPID = $WorkerPID
        PythonPID = $PythonPID
        WorkerRunning = $WorkerIsRunning
        PythonRunning = $PythonIsRunning
        RunFolder = $CurrentRunFolder
    }

    # Register the sudden termination
    Register-SuddenTermination -Reason $Reason `
        -TerminationType "Unexpected" `
        -ProcessInfo $processState

    # Perform cleanup
    Stop-WorkerProcess

    # Additional cleanup for PID file
    if (Test-Path $Config.PIDFilePath) {
        try {
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            Write-Log "Cleaned up PID tracking file after unexpected termination" -Level "INFO"
        } catch {
            Write-Log "Failed to clean up PID file: $_" -Level "ERROR"
        }
    }

    # Save final state
    Save-SuddenTerminationTracking

}

function Invoke-GracefulShutdown {
param(
[string]$Reason = "Normal shutdown"
)

    Write-Log "Initiating graceful shutdown: $Reason" -Level "INFO"

    try {
        # Stop worker process
        Stop-WorkerProcess

        # Save final tracking data
        Save-SuddenTerminationTracking

        # Clear streak on successful shutdown
        $SuddenTerminationTracking.CurrentStreak = 0
        Save-SuddenTerminationTracking

        Write-Log "Graceful shutdown completed successfully" -Level "SUCCESS"
    } catch {
        Write-Log "Error during graceful shutdown: $_" -Level "ERROR"
        Register-SuddenTermination -Reason "Error during graceful shutdown: $_" -TerminationType "ShutdownError"
    }

}

# ====================================================================

# SECTION 5: PROCESS MANAGEMENT

# ====================================================================

function Register-ConsoleControlHandler {
<#
.SYNOPSIS
Registers a handler for console control events (Ctrl+C, Ctrl+Break)
#>

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
        param([int]$eventType)

        $currentTime = Get-Date
        $timeSinceLast = if ($global:LastForceStopTime) {
            ($currentTime - $global:LastForceStopTime).TotalSeconds
        } else {
            [double]::MaxValue
        }

        switch ($eventType) {
            { $_ -in 0, 1 } {  # Ctrl+C or Ctrl+Break
                Write-Host "`n[Console Control Handler] Control event detected" -ForegroundColor Yellow

                # Check if this is a rapid double-press
                if ($timeSinceLast -lt $global:ForceStopWindowSeconds) {
                    $global:ForceStopAttempts++
                    Write-Host "  Rapid attempt detected ($global:ForceStopAttempts/$global:ForceStopThreshold)" -ForegroundColor Yellow
                } else {
                    $global:ForceStopAttempts = 1
                }

                $global:LastForceStopTime = $currentTime

                # If user has pressed Ctrl+C twice within the threshold, allow shutdown
                if ($global:ForceStopAttempts -ge $global:ForceStopThreshold) {
                    Write-Host "  Force shutdown requested by user" -ForegroundColor Red
                    $global:IsShuttingDown = $true
                    return $true
                } else {
                    # First attempt or single Ctrl+C - just log and continue
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

function Save-PersistentTracking {
<#
.SYNOPSIS
Saves persistent tracking data to disk for recovery
#>

    $persistentFilePath = Join-Path (Split-Path $Config.LogFile -Parent) "persistent_tracking.json"

    # Update persistent tracking data
    $global:PersistentTracking.LastKnownRunFolder = $CurrentRunFolder
    $global:PersistentTracking.LastKnownPythonPID = $PythonPID
    $global:PersistentTracking.LastKnownWorkerPID = $WorkerPID
    $global:PersistentTracking.LastValidationTime = if ($LastValidation) { (Get-Date).ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
    $global:PersistentTracking.LastValidationResult = if ($LastValidation) { @{ Success = $LastValidation.Success; FolderName = $LastValidation.FolderName } } else { $null }
    $global:PersistentTracking.CollectedRunFolders = $global:CollectedRunFolders

    # Add current process state to history
    $currentState = @{
        Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        PythonPID = $PythonPID
        WorkerPID = $WorkerPID
        RunFolder = $CurrentRunFolder
        PythonRunning = $PythonIsRunning
        WorkerRunning = $WorkerIsRunning
        ForceStopAttempts = $global:ForceStopAttempts
        CollectedFoldersCount = $global:CollectedRunFolders.Count
    }

    $global:PersistentTracking.ProcessStopHistory += $currentState

    # Keep only last 50 entries
    if ($global:PersistentTracking.ProcessStopHistory.Count -gt 50) {
        $global:PersistentTracking.ProcessStopHistory = $global:PersistentTracking.ProcessStopHistory | Select-Object -Last 50
    }

    try {
        $global:PersistentTracking | ConvertTo-Json -Depth 10 | Out-File -FilePath $persistentFilePath -Force
        Write-Log "Persistent tracking saved to: $persistentFilePath" -Level "DEBUG"
        return $true
    } catch {
        Write-Log "Failed to save persistent tracking: $_" -Level "ERROR"
        return $false
    }

}

function Load-PersistentTracking {
<#
.SYNOPSIS
Loads persistent tracking data from disk
#>

    $persistentFilePath = Join-Path (Split-Path $Config.LogFile -Parent) "persistent_tracking.json"

    if (Test-Path $persistentFilePath) {
        try {
            $loadedData = Get-Content -Path $persistentFilePath -Raw | ConvertFrom-Json

            # Check if data is stale (older than 7 days)
            if ($loadedData.ProcessStopHistory.Count -gt 0) {
                $lastEntry = $loadedData.ProcessStopHistory[-1]
                $lastTimestamp = [DateTime]::ParseExact($lastEntry.Timestamp, "yyyy-MM-dd HH:mm:ss", $null)
                $ageDays = ((Get-Date) - $lastTimestamp).TotalDays

                if ($ageDays -gt 7) {
                    Write-Log "Persistent tracking data is old ($ageDays days), starting fresh" -Level "WARN"
                    return $false
                }
            }

            # Load the data
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

            # Restore collected folders to global variable
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

function Check-OrphanedRuns {
<#
.SYNOPSIS
Checks for orphaned runs that might have been left behind by crashes
#>
param(
[string]$LastKnownFolder
)

    Write-Log "Checking for orphaned runs..." -Level "INFO"

    # First, check the last known folder
    if ($LastKnownFolder -and (Test-Path $LastKnownFolder)) {
        Write-Log "Validating last known folder: $(Split-Path $LastKnownFolder -Leaf)" -Level "DEBUG"

        # Try to validate the folder
        $runFolderObj = Get-Item $LastKnownFolder -ErrorAction SilentlyContinue
        if ($runFolderObj) {
            $validation = @{
                Success = $true
                RunFolder = $LastKnownFolder
                FolderName = $runFolderObj.Name
                CreationTime = $runFolderObj.CreationTime
            }

            # Collect this orphaned run
            $runData = Collect-RunFolderAttachments -RunFolder $LastKnownFolder
            if ($runData.Attachments.Count -gt 0) {
                # Check if we already have this folder
                $existingIndex = $global:CollectedRunFolders |
                    Where-Object { $_.RunFolder -eq $runData.RunFolder } |
                    Select-Object -First 1

                if (-not $existingIndex) {
                    $global:CollectedRunFolders += $runData
                    Write-Log "Collected orphaned run from previous session: $($runData.RunFolderName)" -Level "SUCCESS"

                    # Update persistent tracking
                    $global:PersistentTracking.LastSuccessfulRun = @{
                        Folder = $runData.RunFolder
                        CollectionTime = $runData.CollectionTime
                        FileCount = $runData.Attachments.Count
                    }
                    Save-PersistentTracking
                }
            }
        }
    }

}

function Collect-RunFolderAttachments {
<#
.SYNOPSIS
Collects all files from a run folder that should be attached to emails
#>
param(
[string]$RunFolder
)

    if (-not (Test-Path $RunFolder)) {
        Write-Log "Run folder not found for collection: $RunFolder" -Level "WARN"
        return @()
    }

    $attachments = @()
    $runFolderName = Split-Path $RunFolder -Leaf

    Write-Log "Collecting attachments from: $runFolderName" -Level "DEBUG"

    # 1. Completion summary
    $completionSummaryPath = Join-Path $RunFolder "Magick_Process_*\logs\completion_summary.txt"
    if (Test-Path $completionSummaryPath) {
        $attachments += $completionSummaryPath
        Write-Log "  Found completion_summary.txt" -Level "DEBUG"
    }

    # 2. Latest run log
    $logsPath = Join-Path $RunFolder "logs"
    if (Test-Path $logsPath) {
        $runLogs = Get-ChildItem -Path $logsPath -Filter "run_*.log" -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending
        if ($runLogs.Count -gt 0) {
            $attachments += $runLogs[0].FullName
            Write-Log "  Found run log: $($runLogs[0].Name)" -Level "DEBUG"
        }
    }

    # 3. Metadata file
    $metadataPath = Join-Path $RunFolder "metadata.json"
    if (Test-Path $metadataPath) {
        $attachments += $metadataPath
        Write-Log "  Found metadata.json" -Level "DEBUG"
    }

    # 4. Process logs from script_output if they exist
    $scriptOutputPath = Join-Path $RunFolder "script_output"
    if (Test-Path $scriptOutputPath) {
        $processLogs = Get-ChildItem -Path $scriptOutputPath -Filter "*.log" -ErrorAction SilentlyContinue
        foreach ($log in $processLogs) {
            $attachments += $log.FullName
            Write-Log "  Found process log: $($log.Name)" -Level "DEBUG"
        }
    }

    # 5. Any CSV or data files
    $dataFiles = Get-ChildItem -Path $RunFolder -Recurse -Filter "*.csv" -ErrorAction SilentlyContinue
    foreach ($file in $dataFiles) {
        $attachments += $file.FullName
        Write-Log "  Found data file: $($file.Name)" -Level "DEBUG"
    }

    # Calculate total size
    $totalSize = 0
    foreach ($attachment in $attachments) {
        if (Test-Path $attachment) {
            $totalSize += (Get-Item $attachment).Length
        }
    }
    $totalSizeMB = [math]::Round($totalSize / 1MB, 2)

    Write-Log "Collected $($attachments.Count) files from $runFolderName ($totalSizeMB MB)" -Level "INFO"

    return @{
        RunFolder = $RunFolder
        RunFolderName = $runFolderName
        Attachments = $attachments
        TotalSizeMB = $totalSizeMB
        CollectionTime = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }

}

function Validate-And-Collect-OnStop {
<#
.SYNOPSIS
Validates and collects run data when a process stops unexpectedly
#>
param(
[string]$StopReason = "Unexpected Stop"
)

    Write-Log "Performing validation on stop: $StopReason" -Level "INFO"

    # Always try to validate the current run folder
    if ($CurrentRunFolder -and (Test-Path $CurrentRunFolder)) {
        Write-Log "Validating current run folder on stop: $(Split-Path $CurrentRunFolder -Leaf)" -Level "DEBUG"

        # Create a basic validation result
        $validation = @{
            Success = $true
            RunFolder = $CurrentRunFolder
            FolderName = Split-Path $CurrentRunFolder -Leaf
            CreationTime = (Get-Item $CurrentRunFolder).CreationTime
        }

        if ($validation.Success) {
            # Collect the run data
            $runData = Collect-RunFolderAttachments -RunFolder $CurrentRunFolder
            if ($runData.Attachments.Count -gt 0) {
                # Check if we already have this folder
                $existingIndex = $global:CollectedRunFolders |
                    Where-Object { $_.RunFolder -eq $runData.RunFolder } |
                    Select-Object -First 1

                if (-not $existingIndex) {
                    $global:CollectedRunFolders += $runData
                    Write-Log "Collected run on stop: $($runData.RunFolderName)" -Level "SUCCESS"
                }
            }
        }
    } else {
        # If no current run folder, try to find the latest one
        Write-Log "No current run folder, finding latest..." -Level "DEBUG"
        $latestFolder = Find-LatestRunFolder
        if ($latestFolder) {
            Write-Log "Validating latest run folder on stop: $(Split-Path $latestFolder.FullName -Leaf)" -Level "DEBUG"

            $validation = @{
                Success = $true
                RunFolder = $latestFolder.FullName
                FolderName = $latestFolder.Name
                CreationTime = $latestFolder.CreationTime
            }

            if ($validation.Success) {
                $runData = Collect-RunFolderAttachments -RunFolder $latestFolder.FullName
                if ($runData.Attachments.Count -gt 0) {
                    # Check if we already have this folder
                    $existingIndex = $global:CollectedRunFolders |
                        Where-Object { $_.RunFolder -eq $runData.RunFolder } |
                        Select-Object -First 1

                    if (-not $existingIndex) {
                        $global:CollectedRunFolders += $runData
                        Write-Log "Collected latest run on stop: $($runData.RunFolderName)" -Level "SUCCESS"
                    }
                }
            }
        }
    }

    # Save all state
    Save-PIDTracking
    Save-PersistentTracking

}

function Record-ProcessStop {
<#
.SYNOPSIS
Records detailed information when a process stops
#>
param(
[string]$StopType,
        [string]$Reason,
[bool]$WasUnexpected = $false
)

    $stopRecord = @{
        Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        StopType = $StopType
        Reason = $Reason
        WasUnexpected = $WasUnexpected
        PythonPID = $PythonPID
        WorkerPID = $WorkerPID
        RunFolder = $CurrentRunFolder
        PythonRunningBefore = $PythonIsRunning
        WorkerRunningBefore = $WorkerIsRunning
        ForceStopAttempts = $global:ForceStopAttempts
        IsShuttingDown = $global:IsShuttingDown
    }

    # Add to validation history if this was a validation event
    if ($StopType -eq "Validation") {
        $global:PersistentTracking.ValidationHistory += $stopRecord
        if ($global:PersistentTracking.ValidationHistory.Count -gt 100) {
            $global:PersistentTracking.ValidationHistory = $global:PersistentTracking.ValidationHistory | Select-Object -Last 100
        }
    }

    # Always add to process stop history
    $global:PersistentTracking.ProcessStopHistory += $stopRecord
    if ($global:PersistentTracking.ProcessStopHistory.Count -gt 100) {
        $global:PersistentTracking.ProcessStopHistory = $global:PersistentTracking.ProcessStopHistory | Select-Object -Last 100
    }

    # Update daily run count if this was a successful validation
    if ($StopType -eq "Validation" -and $Reason -eq "Success") {
        $global:PersistentTracking.DailyRunCount++

        # Update last successful run
        if ($CurrentRunFolder) {
            $global:PersistentTracking.LastSuccessfulRun = @{
                Folder = $CurrentRunFolder
                Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                FolderName = Split-Path $CurrentRunFolder -Leaf
            }
        }
    }

    Write-Log "Process stop recorded: $StopType - $Reason (Unexpected: $WasUnexpected)" -Level "DEBUG"
    Save-PersistentTracking

}

function Save-PIDTracking { # Enhanced to include persistent tracking data

    $workerStartString = if ($WorkerStartTime -and ($WorkerStartTime -is [DateTime]) -and ($WorkerStartTime.ToString("yyyy-MM-dd HH:mm:ss") -ne "-")) {
        $WorkerStartTime.ToString("yyyy-MM-dd HH:mm:ss")
    } else {
        $null
    }

    $pythonStartString = if ($PythonStartTime -and ($PythonStartTime -is [DateTime]) -and ($PythonStartTime.ToString("yyyy-MM-dd HH:mm:ss") -ne "-")) {
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

    # Add persistent tracking data
    $PIDTracking.PersistentTracking = @{
        LastKnownRunFolder = $CurrentRunFolder
        LastKnownPythonPID = $PythonPID
        LastKnownWorkerPID = $WorkerPID
        DailyRunCount = $global:PersistentTracking.DailyRunCount
        LastSuccessfulRun = $global:PersistentTracking.LastSuccessfulRun
        CollectedFoldersCount = $global:CollectedRunFolders.Count
    }

    try {
        $PIDTracking | ConvertTo-Json -Depth 10 | Out-File -FilePath $Config.PIDFilePath -Force
        Write-Log "Enhanced PID tracking saved with $($global:CollectedRunFolders.Count) collected folders" -Level "DEBUG"

        # Also save persistent tracking separately
        Save-PersistentTracking
    } catch {
        Write-Log "Failed to save enhanced PID tracking: $_" -Level "ERROR"
    }

}

function Load-PIDTracking {
if (-not (Test-Path $Config.PIDFilePath)) {
Write-Log "No PID tracking file found" -Level "DEBUG"

        # Try to load persistent tracking separately
        Load-PersistentTracking | Out-Null

        # Check for orphaned runs
        Check-OrphanedRuns -LastKnownFolder $global:PersistentTracking.LastKnownRunFolder

        return $false
    }

    try {
        $loaded = Get-Content -Path $Config.PIDFilePath -Raw | ConvertFrom-Json

        # Check if PID file is too old
        $lastUpdate = [DateTime]::ParseExact($loaded.LastUpdate, "yyyy-MM-dd HH:mm:ss", $null)
        $ageMinutes = ((Get-Date) - $lastUpdate).TotalMinutes

        if ($ageMinutes -gt $Config.MaxPIDFileAgeMinutes) {
            Write-Log "PID file is too old ($ageMinutes minutes), cleaning up" -Level "WARN"

            # Before removing, try to validate and collect any ongoing run
            if ($loaded.RunFolder) {
                Write-Log "Attempting to validate stale run folder before cleanup..." -Level "INFO"
                Validate-And-Collect-OnStop -StopReason "Stale PID File"
            }

            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            return $false
        }

        # Restore PID tracking
        $global:PIDTracking = @{
            WorkerPID = $loaded.WorkerPID
            PythonPID = $loaded.PythonPID
            WorkerStartTime = $loaded.WorkerStartTime
            PythonStartTime = $loaded.PythonStartTime
            RunFolder = $loaded.RunFolder
            LastUpdate = $loaded.LastUpdate
        }

        # Restore global variables
        $global:WorkerPID = $loaded.WorkerPID
        $global:PythonPID = $loaded.PythonPID
        $global:CurrentRunFolder = $loaded.RunFolder

        # Convert string times back to DateTime
        if ($loaded.WorkerStartTime) {
            try {
                $global:WorkerStartTime = [DateTime]::ParseExact($loaded.WorkerStartTime, "yyyy-MM-dd HH:mm:ss", $null)
            } catch { }
        }

        if ($loaded.PythonStartTime) {
            try {
                $global:PythonStartTime = [DateTime]::ParseExact($loaded.PythonStartTime, "yyyy-MM-dd HH:mm:ss", $null)
            } catch { }
        }

        # Enhanced: Load persistent tracking data from PID file
        if ($loaded.PSObject.Properties.Name -contains "PersistentTracking") {
            $global:PersistentTracking.LastKnownRunFolder = $loaded.PersistentTracking.LastKnownRunFolder
            $global:PersistentTracking.LastKnownPythonPID = $loaded.PersistentTracking.LastKnownPythonPID
            $global:PersistentTracking.LastKnownWorkerPID = $loaded.PersistentTracking.LastKnownWorkerPID
            $global:PersistentTracking.DailyRunCount = $loaded.PersistentTracking.DailyRunCount
            $global:PersistentTracking.LastSuccessfulRun = $loaded.PersistentTracking.LastSuccessfulRun
        }

        Write-Log "Enhanced PID tracking loaded with $($global:CollectedRunFolders.Count) collected folders" -Level "INFO"

        # Also load separate persistent tracking file for history
        Load-PersistentTracking | Out-Null

        return $true

    } catch {
        Write-Log "Failed to load enhanced PID tracking: $_" -Level "ERROR"
        Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue

        # Try to load persistent tracking anyway
        Load-PersistentTracking | Out-Null

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

        # Use the stable approach from older codebase
        $arguments = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$($Config.WorkerScript)`""
        )

        # Start the worker process
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
$wasUnexpected = $false

    # Determine if this is an unexpected stop
    if ($global:IsShuttingDown -and $global:ForceStopAttempts -ge $global:ForceStopThreshold) {
        $stopReason = "Force Stop by User"
        $wasUnexpected = $true
    } elseif (-not $global:IsShuttingDown -and ($PythonIsRunning -or $WorkerIsRunning)) {
        $stopReason = "Unexpected Process Stop"
        $wasUnexpected = $true
    }

    Write-Log "Stopping worker process. Reason: $stopReason" -Level "INFO"

    # Record the stop event
    Record-ProcessStop -StopType "ProcessStop" -Reason $stopReason -WasUnexpected $wasUnexpected

    # If this was unexpected, validate and collect before stopping
    if ($wasUnexpected) {
        Write-Log "Unexpected stop detected - validating and collecting current run..." -Level "WARN"
        Validate-And-Collect-OnStop -StopReason $stopReason
    }

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
        catch [System.ComponentModel.Win32Exception] {
            Write-Log "Access denied when trying to stop Python process (PID: $PythonPID)" -Level "WARN"
        }
        catch [System.ArgumentException] {
            Write-Log "Python process (PID: $PythonPID) no longer exists" -Level "DEBUG"
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
        catch [System.ComponentModel.Win32Exception] {
            Write-Log "Access denied when trying to stop worker process (PID: $WorkerPID)" -Level "WARN"
        }
        catch [System.ArgumentException] {
            Write-Log "Worker process (PID: $WorkerPID) no longer exists" -Level "DEBUG"
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

    # Enhanced: Check for unexpected process stops
    $previousWorkerRunning = $global:WorkerIsRunning
    $previousPythonRunning = $global:PythonIsRunning

    # Update global state
    $global:WorkerIsRunning = $status.WorkerRunning
    $global:PythonIsRunning = $status.PythonRunning

    # Detect unexpected stops
    if (($previousWorkerRunning -and -not $status.WorkerRunning) -or
        ($previousPythonRunning -and -not $status.PythonRunning)) {

        Write-Log "Detected unexpected process stop. Worker: $previousWorkerRunning -> $($status.WorkerRunning), Python: $previousPythonRunning -> $($status.PythonRunning)" -Level "WARN"

        # Only trigger validation if we're in the active time window
        $inWindow = Test-TimeWindow -TargetTime $Config.StartTime -and (-not (Test-TimeWindow -TargetTime $Config.EndTime))

        if ($inWindow -and $CurrentRunFolder) {
            Write-Log "Validating run due to unexpected process stop in active window..." -Level "INFO"
            Validate-And-Collect-OnStop -StopReason "Unexpected Process Stop"
        }
    }

    return $status

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

# ====================================================================

# SECTION 6: VALIDATION AND OUTPUT

# ====================================================================

function Validate-Output {
param([int]$RetryCount = 0)

    Write-Log "Validating face recognition output structure..." -Level "INFO"

    # Find the latest run folder
    $runFolder = Find-LatestRunFolder

    if (-not $runFolder) {
        if ($RetryCount -lt $Config.MaxValidationRetries) {
            Write-Log "No output folder found. Retrying in $($Config.RetryDelaySeconds) seconds... (Attempt $($RetryCount + 1)/$($Config.MaxValidationRetries))" -Level "WARN"
            Start-Sleep -Seconds $Config.RetryDelaySeconds
            return Validate-Output -RetryCount ($RetryCount + 1)
        } else {
            Write-Log "VALIDATION FAILED: No output folder found after $($Config.MaxValidationRetries) retries" -Level "ERROR"
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
            # Special handling for metadata.json
            if ($item -eq "metadata.json") {
                try {
                    $metadataContent = Get-Content $itemPath -Raw | ConvertFrom-Json
                    $validationResult.Details["metadata"] = @{
                        RunID = $metadataContent.run_id
                        StartTime = $metadataContent.start_time
                        ExitCode = $metadataContent.exit_code
                    }
                    Write-Log "Metadata file is valid JSON" -Level "DEBUG"

                    # Check file size
                    $fileSize = (Get-Item $itemPath).Length
                    $validationResult.Details.FileSizes[$item] = $fileSize
                    Write-Log "Metadata file size: $([math]::Round($fileSize/1KB, 2)) KB" -Level "DEBUG"

                } catch {
                    # Fixed: Using string concatenation instead of interpolation with colon
                    $validationResult.Errors += $item + ": Invalid JSON format"
                    $validationResult.Success = $false
                    Write-Log "Metadata file contains invalid JSON" -Level "WARN"
                }
            }
        }
    }

    # Check log files
    $logPath = Join-Path $runFolder.FullName "logs"
    if (Test-Path $logPath) {
        $logFiles = Get-ChildItem -Path $logPath -File -ErrorAction SilentlyContinue
        $validationResult.Details["LogFiles"] = @($logFiles | ForEach-Object { $_.Name })

        if ($logFiles.Count -eq 0) {
            $validationResult.Warnings += "No log files found in logs folder"
            Write-Log "No log files found in logs folder" -Level "WARN"
        } else {
            Write-Log "Found $($logFiles.Count) log files" -Level "DEBUG"

            # Check for critical log files
            $expectedLogs = @("completion_summary.txt", "python_output.txt")
            foreach ($log in $expectedLogs) {
                $logFile = $logFiles | Where-Object { $_.Name -eq $log }
                if (-not $logFile) {
                    $validationResult.Warnings += "Missing log file: $log"
                    Write-Log "Missing log file: $log" -Level "WARN"
                } else {
                    # Check file sizes for potential email attachments
                    $fileSize = $logFile.Length
                    $validationResult.Details.FileSizes[$log] = $fileSize
                    Write-Log "$log size: $([math]::Round($fileSize/1KB, 2)) KB" -Level "DEBUG"

                    if ($logFile.Name -eq "completion_summary.txt") {
                        $validationResult.Details.AttachmentFiles += $logFile.FullName
                    }
                }
            }

            # Find run_*.log files
            $runLogs = $logFiles | Where-Object { $_.Name -like "run_*.log" } | Sort-Object LastWriteTime -Descending
            if ($runLogs.Count -gt 0) {
                $latestRunLog = $runLogs[0]
                $validationResult.Details.AttachmentFiles += $latestRunLog.FullName
                $fileSize = $latestRunLog.Length
                $validationResult.Details.FileSizes[$latestRunLog.Name] = $fileSize
                Write-Log "Latest run log: $($latestRunLog.Name) ($([math]::Round($fileSize/1KB, 2)) KB)" -Level "DEBUG"
            }
        }
    }

    # Check script_output folder
    $scriptOutputPath = Join-Path $runFolder.FullName "script_output"
    if (Test-Path $scriptOutputPath) {
        $outputItems = Get-ChildItem -Path $scriptOutputPath -ErrorAction SilentlyContinue
        $itemCount = $outputItems.Count
        $validationResult.Details["ScriptOutput"] = @{
            ItemCount = $itemCount
            Items = @($outputItems | ForEach-Object { $_.Name })
        }
        Write-Log "Script output contains $itemCount items" -Level "DEBUG"

        if ($itemCount -eq 0) {
            $validationResult.Warnings += "script_output folder is empty"
            Write-Log "script_output folder is empty" -Level "WARN"
        }
    }

    # Calculate folder size
    try {
        $files = Get-ChildItem -Path $runFolder.FullName -Recurse -File -ErrorAction SilentlyContinue
        if ($files) {
            $folderSize = ($files | Measure-Object -Property Length -Sum).Sum
            $sizeMB = [math]::Round($folderSize / 1MB, 2)
            $validationResult.Details["TotalSizeMB"] = $sizeMB

            # Check attachment sizes for email (Gmail limit is 25MB total)
            $attachmentSize = 0
            foreach ($attachment in $validationResult.Details.AttachmentFiles) {
                if (Test-Path $attachment) {
                    $attachmentSize += (Get-Item $attachment).Length
                }
            }

            $metadataSize = (Test-Path (Join-Path $runFolder.FullName "metadata.json")) ? (Get-Item (Join-Path $runFolder.FullName "metadata.json")).Length : 0
            $attachmentSize += $metadataSize

            $attachmentSizeMB = [math]::Round($attachmentSize / 1MB, 2)
            $validationResult.Details["AttachmentSizeMB"] = $attachmentSizeMB

            Write-Log "Total folder size: $sizeMB MB" -Level "DEBUG"
            Write-Log "Total attachment size: $attachmentSizeMB MB" -Level "DEBUG"

            if ($attachmentSizeMB -gt 20) { # Warning at 20MB, Gmail limit is 25MB
                $validationResult.Warnings += "Attachment files are large ($attachmentSizeMB MB). Email may fail if total exceeds 25MB."
                Write-Log "WARNING: Attachments are large ($attachmentSizeMB MB)" -Level "WARN"
            }
        } else {
            $validationResult.Warnings += "Could not calculate folder size (no files found)"
            Write-Log "Could not calculate folder size (no files found)" -Level "WARN"
        }
    } catch {
        $validationResult.Warnings += "Error calculating folder size: $_"
        Write-Log "Could not calculate folder size: $_" -Level "WARN"
    }

    # Summary
    if ($validationResult.Success) {
        if ($validationResult.Warnings.Count -gt 0) {
            Write-Log "VALIDATION SUCCESS with warnings:" -Level "SUCCESS"
            foreach ($warning in $validationResult.Warnings) {
                Write-Log "  Warning: $warning" -Level "WARN"
            }
        } else {
            Write-Log "VALIDATION SUCCESS: Folder structure complete" -Level "SUCCESS"
        }
        Write-Log "  - Path: $($runFolder.FullName)" -Level "SUCCESS"
        Write-Log "  - Created: $($runFolder.CreationTime)" -Level "SUCCESS"
        if ($validationResult.Details.ContainsKey("TotalSizeMB")) {
            Write-Log "  - Size: $($validationResult.Details['TotalSizeMB']) MB" -Level "SUCCESS"
        }
        if ($validationResult.Details.ContainsKey("AttachmentSizeMB")) {
            Write-Log "  - Attachments: $($validationResult.Details['AttachmentSizeMB']) MB" -Level "SUCCESS"
        }
    } else {
        Write-Log "VALIDATION FAILED:" -Level "ERROR"
        if ($validationResult.MissingItems.Count -gt 0) {
            Write-Log "  Missing items: $($validationResult.MissingItems -join ', ')" -Level "ERROR"
        }
        if ($validationResult.Errors.Count -gt 0) {
            Write-Log "  Errors: $($validationResult.Errors -join ', ')" -Level "ERROR"
        }
        if ($validationResult.Warnings.Count -gt 0) {
            Write-Log "  Warnings: $($validationResult.Warnings -join ', ')" -Level "WARN"
        }
    }

    return $validationResult

}

# ====================================================================

# SECTION 7: EMAIL AND NOTIFICATION

# ====================================================================

function Send-CompletionEmail {
param(
[string]$RunFolder,
        [object]$ValidationResult,
[array]$AllAttachments = @() # parameter for all collected attachments
)

    if (-not $Config.SendEmailOnCompletion) {
        Write-Log "Email notification on completion is disabled" -Level "DEBUG"
        return $false
    }

    if ($null -eq $Config.EmailRecipients -or $Config.EmailRecipients.Count -eq 0) {
        Write-Log "No email recipients configured" -Level "WARN"
        return $false
    }

    if ([string]::IsNullOrWhiteSpace($Config.SmtpServer)) {
        Write-Log "SMTP server not configured" -Level "WARN"
        return $false
    }

    try {
        Write-Log "Preparing to send completion notifications to $($Config.EmailRecipients.Count) recipient(s)..." -Level "INFO"

        # Load credentials if available
        $credential = $null
        if (Test-Path $Config.EmailCredentialPath) {
            try {
                $credential = Import-Clixml -Path $Config.EmailCredentialPath
                Write-Log "Email credential loaded from $($Config.EmailCredentialPath)" -Level "DEBUG"
            } catch {
                Write-Log "Failed to load email credential: $_" -Level "WARN"
                return $false
            }
        } else {
            Write-Log "Email credential file not found at $($Config.EmailCredentialPath)" -Level "WARN"
            return $false
        }

        # Modify attachment collection to use AllAttachments if provided
        if ($AllAttachments.Count -gt 0) {
            $attachments = $AllAttachments
            Write-Log "Using pre-collected attachments: $($attachments.Count) files" -Level "INFO"
        } else {
            # Original attachment collection logic
            $attachments = @()
            $completionSummaryPath = Join-Path $RunFolder "Magick_Process_*\logs\completion_summary.txt"
            if (Test-Path $completionSummaryPath) {
                $attachments += $completionSummaryPath
            }
            Write-Log "Found completion_summary.txt" -Level "DEBUG"
        }

        $logsPath = Join-Path $RunFolder "logs"
        if (Test-Path $logsPath) {
            $runLogs = Get-ChildItem -Path $logsPath -Filter "run_*.log" -ErrorAction SilentlyContinue |
                       Sort-Object LastWriteTime -Descending
            if ($runLogs.Count -gt 0) {
                $attachments += $runLogs[0].FullName
                Write-Log "Found latest run log: $($runLogs[0].Name)" -Level "DEBUG"
            }
        }

        $metadataPath = Join-Path $RunFolder "metadata.json"
        if (Test-Path $metadataPath) {
            $attachments += $metadataPath
            Write-Log "Found metadata.json" -Level "DEBUG"
        }

        # Get MailKit version info
        $mailKitVersionInfo = Get-MailKitVersionInfo

        # Determine which email function to use
        $useMailKit = $mailKitVersionInfo.MailKitMajorVersion -ge 3

        # Group recipients by language to avoid duplicate emails
        $recipientsByLanguage = @{}
        foreach ($recipient in $Config.EmailRecipients) {
            $lang = $recipient.Language
            if (-not $recipientsByLanguage.ContainsKey($lang)) {
                $recipientsByLanguage[$lang] = @()
            }
            $recipientsByLanguage[$lang] += $recipient.Address
        }

        Write-Log "Sending emails in $(($recipientsByLanguage.Keys | Measure-Object).Count) different language(s)" -Level "INFO"

        $successCount = 0
        $failCount = 0

        # Send one email per language group
        foreach ($language in $recipientsByLanguage.Keys) {
            $recipients = $recipientsByLanguage[$language]
            $recipientList = $recipients -join ", "

            Write-Log "Sending $language email to: $recipientList" -Level "INFO"

            # Get email content for this language
            $emailContent = Get-EmailContent -Language $language -RunFolder $RunFolder -ValidationResult $ValidationResult -Attachments $attachments

            $emailSent = $false

            if ($useMailKit) {
                Write-Log "Using MailKit v$($mailKitVersionInfo.MailKitVersion) for email sending" -Level "INFO"
                $emailSent = Send-MailKitEmail -To $recipients -From $Config.EmailFrom -Subject $emailContent.Subject -Body $emailContent.Body `
                    -SmtpServer $Config.SmtpServer -Port $Config.SmtpPort -UseSsl $Config.UseSSL -Credential $credential -Attachments $attachments
            } else {
                Write-Log "MailKit not available, using System.Net.Mail fallback" -Level "WARN"
                $emailSent = Send-SystemNetMailEmail -To $recipients -From $Config.EmailFrom -Subject $emailContent.Subject -Body $emailContent.Body `
                    -SmtpServer $Config.SmtpServer -Port $Config.SmtpPort -UseSsl $Config.UseSSL -Credential $credential -Attachments $attachments
            }

            if ($emailSent) {
                $successCount += $recipients.Count
                Write-Log "Successfully sent $language email to $($recipients.Count) recipient(s)" -Level "SUCCESS"
            } else {
                $failCount += $recipients.Count
                Write-Log "Failed to send $language email to $($recipients.Count) recipient(s)" -Level "ERROR"
            }
        }

        # Summary
        $totalRecipients = $successCount + $failCount
        if ($failCount -eq 0) {
            Write-Log "All emails sent successfully ($totalRecipients total recipients)" -Level "SUCCESS"
            return $true
        } elseif ($successCount -gt 0) {
            Write-Log "Partially successful: $successCount/$totalRecipients emails sent" -Level "WARN"
            return $true  # Return true if at least some emails were sent
        } else {
            Write-Log "All emails failed to send" -Level "ERROR"
            return $false
        }

    } catch {
        Write-Log "Failed to send completion emails: $($_.Exception.Message)" -Level "ERROR"

        # Provide troubleshooting tips for Gmail
        if ($Config.SmtpServer -like "*gmail*") {
            Write-Log "GMAIL TROUBLESHOOTING TIPS:" -Level "WARN"
            Write-Log "1. Ensure you're using an App Password (not your regular password)" -Level "WARN"
            Write-Log "2. Enable 2-Step Verification in your Google Account" -Level "WARN"
            Write-Log "3. Generate an App Password: https://myaccount.google.com/apppasswords" -Level "WARN"
            Write-Log "4. Make sure 'Allow less secure apps' is OFF (App Password replaces this)" -Level "WARN"
        }

        return $false
    }

}

function Get-EmailContent {
param(
[string]$Language,
        [string]$RunFolder,
[object]$ValidationResult,
        [array]$Attachments
)

    $runFolderName = Split-Path $RunFolder -Leaf
    $currentTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    # Try to load metadata for additional details
    $metadataContent = $null
    $metadataPath = Join-Path $RunFolder "metadata.json"
    if (Test-Path $metadataPath) {
        try {
            $metadataContent = Get-Content $metadataPath -Raw | ConvertFrom-Json
        } catch { }
    }

    switch ($Language.ToLower()) {
        "bahasa" {
            $subject = "$($Config.EmailSubject.Bahasa) - $runFolderName"

            $body = @"

# LAPORAN PENYELESAIAN PROSES PENGENALAN WAJAH

## RINGKASAN PROSES

Waktu Penyelesaian: $currentTime
Folder Proses: $runFolderName
Status Validasi: $(if ($ValidationResult.Success) {'BERHASIL'} else {'GAGAL'})

$(if ($metadataContent) {
"ID Proses: $($metadataContent.run_id)
Waktu Mulai: $($metadataContent.start_time)
Kode Keluar: $($metadataContent.exit_code)"
})

## HASIL VALIDASI

Folder Dibuat: $($ValidationResult.CreationTime)
Ukuran Folder: $(if ($ValidationResult.Details.TotalSizeMB) {"$($ValidationResult.Details.TotalSizeMB) MB"} else {"Tidak Diketahui"})

Struktur Folder:

- Subfolder: $($Config.ExpectedSubfolders.Count - $ValidationResult.MissingItems.Count)/$($Config.ExpectedSubfolders.Count)
- File: $($Config.ExpectedFiles.Count - $ValidationResult.MissingItems.Count)/$($Config.ExpectedFiles.Count)
- File Log: $($ValidationResult.Details.LogFiles.Count)
- Item Output: $($ValidationResult.Details.ScriptOutput.ItemCount)

## FILE LAMPIRAN

$(if ($Attachments.Count -gt 0) {
$attachments | ForEach-Object { "- $(Split-Path $\_ -Leaf)" } | Join-String -Separator "`n"
} else {
"Tidak ada file terlampir"
})

## INFORMASI SISTEM

Instans Monitor: $($env:COMPUTERNAME)
Path Dasar: $($Config.RunsBasePath)
Jadwal: $($Config.StartTime) - $($Config.EndTime)
Skrip Python: $($Config.PythonScriptPath)

## FILE LOG MONITOR

File Log: $($Config.LogFile)

$(if ($ValidationResult.Warnings.Count -gt 0) {
"PERINGATAN:
$(foreach ($warning in $ValidationResult.Warnings) {
"- $warning"
})
"
})
"@
}

        default {  # English (default)
            $subject = "$($Config.EmailSubject.English) - $runFolderName"

            $body = @"

# FACE RECOGNITION PROCESS COMPLETION REPORT

## PROCESS SUMMARY

Completion Time: $currentTime
Run Folder: $runFolderName
Validation Status: $(if ($ValidationResult.Success) {'SUCCESS'} else {'FAILED'})

$(if ($metadataContent) {
"Run ID: $($metadataContent.run_id)
Start Time: $($metadataContent.start_time)
Exit Code: $($metadataContent.exit_code)"
})

## VALIDATION RESULTS

Folder Created: $($ValidationResult.CreationTime)
Folder Size: $(if ($ValidationResult.Details.TotalSizeMB) {"$($ValidationResult.Details.TotalSizeMB) MB"} else {"Unknown"})

Folder Structure:

- Subfolders: $($Config.ExpectedSubfolders.Count - $ValidationResult.MissingItems.Count)/$($Config.ExpectedSubfolders.Count)
- Files: $($Config.ExpectedFiles.Count - $ValidationResult.MissingItems.Count)/$($Config.ExpectedFiles.Count)
- Log Files: $($validationResult.Details.LogFiles.Count)
- Output Items: $($ValidationResult.Details.ScriptOutput.ItemCount)

## ATTACHED FILES

$(if ($Attachments.Count -gt 0) {
$attachments | ForEach-Object { "- $(Split-Path $\_ -Leaf)" } | Join-String -Separator "`n"
} else {
"No files attached"
})

## SYSTEM INFORMATION

Monitor Instance: $($env:COMPUTERNAME)
Base Path: $($Config.RunsBasePath)
Schedule: $($Config.StartTime) - $($Config.EndTime)
Python Script: $($Config.PythonScriptPath)

## MONITOR LOG

Log File: $($Config.LogFile)

$(if ($ValidationResult.Warnings.Count -gt 0) {
"WARNINGS:
$(foreach ($warning in $ValidationResult.Warnings) {
"- $warning"
})
"
})
"@
}
}

    return @{
        Subject = $subject
        Body = $body
    }

}

function Get-ProcessStatus {
$status = @{
MonitorRunning = $true
WorkerRunning = $WorkerIsRunning
PythonRunning = $PythonIsRunning
CurrentTime = Get-Date -Format "HH:mm:ss"
CurrentDate = Get-Date -Format "yyyy-MM-dd"
Schedule = @{
StartTime = $Config.StartTime
EndTime = $Config.EndTime
InWindow = $false
}
WorkerInfo = @{
PID = $WorkerPID
PythonPID = $PythonPID
}
LastValidation = $LastValidation
}

    # Check time window
    $startPassed = Test-TimeWindow -TargetTime $Config.StartTime
    $endPassed = Test-TimeWindow -TargetTime $Config.EndTime
    $status.Schedule.InWindow = ($startPassed -and !$endPassed)
    $status.Schedule.StartPassed = $startPassed
    $status.Schedule.EndPassed = $endPassed

    return $status

}

function Test-EmailAddress {
param([string]$Email)

    try {
        $mailAddress = New-Object System.Net.Mail.MailAddress $Email
        return $mailAddress.Address -eq $Email
    } catch {
        return $false
    }

}

function Test-EmailConfiguration {
if (-not $Config.SendEmailOnCompletion) {
Write-Log "Email notifications on completion are disabled" -Level "INFO"
return $false
}

    Write-Log "Testing email configuration with enhanced MailKit verification..." -Level "INFO"

    $checksPassed = $true

    try {
        # Get MailKit status report with error handling
        $detailedReport = Get-MailKitStatusReport
        if (-not $detailedReport) {
            Write-Log "ERROR: Failed to get MailKit status report" -Level "ERROR"
            return $false
        }

        # Log the detailed status report
        Write-MailKitStatusLog

        # ====================================================================
        # STEP 1: Check MailKit Assembly with SAFE property access
        # ====================================================================
        Write-Log "Verifying MailKit assembly..." -Level "INFO"

        $assemblyStatus = $detailedReport.AssemblyStatus
        if (-not $assemblyStatus) {
            Write-Log "ERROR: MailKit assembly status is null" -Level "ERROR"
            $checksPassed = $false
        } elseif (-not $assemblyStatus.IsAvailable) {
            Write-Log "ERROR: MailKit assembly is not available" -Level "ERROR"
            $checksPassed = $false

            # Provide specific troubleshooting based on assembly test results
            if ($assemblyStatus.Issues -and $assemblyStatus.Issues.Count -gt 0) {
                Write-Log "Assembly issues detected:" -Level "ERROR"
                foreach ($issue in $assemblyStatus.Issues) {
                    Write-Log "  - $issue" -Level "ERROR"
                }
            }

            Write-Log "RECOMMENDATIONS:" -Level "WARN"
            if ($assemblyStatus.Recommendations -and $assemblyStatus.Recommendations.Count -gt 0) {
                foreach ($recommendation in $assemblyStatus.Recommendations) {
                    Write-Log "  - $recommendation" -Level "WARN"
                }
            } else {
                Write-Log "  - Install MailKit and MimeKit assemblies" -Level "WARN"
            }
        } else {
            Write-Log "MailKit assembly verification PASSED" -Level "SUCCESS"
            Write-Log "  - Load Method: $(if ($assemblyStatus.AssemblyLoadMethod) {$assemblyStatus.AssemblyLoadMethod} else {'Unknown'})" -Level "INFO"
            Write-Log "  - MailKit Version: $(if ($assemblyStatus.AssemblyVersion) {$assemblyStatus.AssemblyVersion} else {'Unknown'})" -Level "INFO"
            Write-Log "  - MimeKit Version: $(if ($assemblyStatus.MimeKitVersion) {$assemblyStatus.MimeKitVersion} else {'Unknown'})" -Level "INFO"
        }

        # ====================================================================
        # STEP 2: Check SMTP Configuration
        # ====================================================================
        Write-Log "Verifying SMTP configuration..." -Level "INFO"

        if ([string]::IsNullOrWhiteSpace($Config.SmtpServer)) {
            Write-Log "ERROR: SMTP server not configured" -Level "ERROR"
            $checksPassed = $false
        } else {
            Write-Log "SMTP configuration verification PASSED" -Level "SUCCESS"
            Write-Log "  - Server: $($Config.SmtpServer):$($Config.SmtpPort)" -Level "INFO"
            Write-Log "  - SSL: $($Config.UseSSL)" -Level "INFO"
        }

        # ====================================================================
        # STEP 3: Check Email Recipients
        # ====================================================================
        Write-Log "Verifying email recipients..." -Level "INFO"

        if ($null -eq $Config.EmailRecipients -or $Config.EmailRecipients.Count -eq 0) {
            Write-Log "ERROR: No email recipients configured" -Level "ERROR"
            $checksPassed = $false
        } else {
            Write-Log "Found $($Config.EmailRecipients.Count) email recipient(s)" -Level "SUCCESS"

            # Validate each recipient
            foreach ($recipient in $Config.EmailRecipients) {
                if ([string]::IsNullOrWhiteSpace($recipient.Address)) {
                    Write-Log "ERROR: Recipient has empty email address" -Level "ERROR"
                    $checksPassed = $false
                } elseif (-not (Test-EmailAddress -Email $recipient.Address)) {
                    Write-Log "WARNING: Invalid email address format: $($recipient.Address)" -Level "WARN"
                }

                if ([string]::IsNullOrWhiteSpace($recipient.Language)) {
                    Write-Log "WARNING: Recipient $($recipient.Address) has no language specified, defaulting to English" -Level "WARN"
                    $recipient.Language = "English"
                }
            }
        }

        # ====================================================================
        # STEP 4: Check Credential File
        # ====================================================================
        Write-Log "Verifying email credentials..." -Level "INFO"

        if (Test-Path $Config.EmailCredentialPath) {
            try {
                $credential = Import-Clixml -Path $Config.EmailCredentialPath
                $userName = $credential.UserName
                $hasPassword = $credential.GetNetworkCredential().Password -ne ""

                if (-not $userName) {
                    Write-Log "WARNING: Credential file does not contain a username" -Level "WARN"
                    $checksPassed = $false
                }

                if (-not $hasPassword) {
                    Write-Log "WARNING: Credential file does not contain a password" -Level "WARN"
                    $checksPassed = $false
                }

                if ($userName -and $hasPassword) {
                    Write-Log "Email credential verification PASSED" -Level "SUCCESS"
                    Write-Log "  - Credential file: $($Config.EmailCredentialPath)" -Level "INFO"
                }
            } catch {
                Write-Log "ERROR: Failed to load email credential: $_" -Level "ERROR"
                $checksPassed = $false
            }
        } else {
            Write-Log "ERROR: Email credential file not found at $($Config.EmailCredentialPath)" -Level "ERROR"
            Write-Log "To create credential file, run in PowerShell:" -Level "INFO"
            Write-Log "  `$cred = Get-Credential" -Level "INFO"
            Write-Log "  `$cred | Export-Clixml -Path '$($Config.EmailCredentialPath)'" -Level "INFO"
            $checksPassed = $false
        }

        # ====================================================================
        # STEP 5: Gmail-specific Warnings (if applicable)
        # ====================================================================
        if ($Config.SmtpServer -like "*gmail*") {
            Write-Log "GMAIL CONFIGURATION NOTES:" -Level "INFO"
            Write-Log "- Using SMTP: $($Config.SmtpServer):$($Config.SmtpPort)" -Level "INFO"
            Write-Log "- SSL Enabled: $($Config.UseSSL)" -Level "INFO"
            Write-Log "- Ensure you're using an App Password, not your regular password" -Level "INFO"
            Write-Log "- Gmail attachment limit: 25 MB total" -Level "INFO"
            Write-Log "- Enable 2-Step Verification in Google Account" -Level "INFO"
            Write-Log "- Generate App Password: https://myaccount.google.com/apppasswords" -Level "INFO"
        }

        # ====================================================================
        # STEP 6: Summary and Optional Test Email - MODIFIED: Skip user input
        # ====================================================================
        if ($checksPassed) {
            Write-Log "Email configuration validation COMPLETE" -Level "SUCCESS"
            Write-Log "Overall status: $(if ($detailedReport.OverallStatus) {$detailedReport.OverallStatus} else {'Unknown'})" -Level "INFO"
            Write-Log "Skipping interactive test email prompt as per configuration" -Level "INFO"
            return $true
        } else {
            Write-Log "Email configuration validation FAILED" -Level "ERROR"
            Write-Log "Emails will not be sent until configuration is fixed." -Level "ERROR"
            Write-Log "Check the MailKit status report in the log file for details." -Level "INFO"

            # Show quick reference for fixing common issues
            Write-Host "`nQUICK FIX REFERENCE:" -ForegroundColor Red
            Write-Host "1. MailKit Assembly: Download from https://www.nuget.org/packages/MailKit/" -ForegroundColor Yellow
            Write-Host "2. Place MailKit.dll and MimeKit.dll in: $PSScriptRoot" -ForegroundColor Yellow
            Write-Host "3. Create credential: `$cred = Get-Credential; `$cred | Export-Clixml -Path '$($Config.EmailCredentialPath)'" -ForegroundColor Yellow

            return $false
        }

    } catch {
        Write-Log "Error in Test-EmailConfiguration: $_" -Level "ERROR"
        Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
        return $false
    }

}

# ====================================================================

# SECTION 8: UI AND STATUS

# ====================================================================

function Show-StatusBanner {
$status = Get-ProcessStatus

    # Only show banner every 20 seconds to avoid flickering
    $currentSecond = (Get-Date).Second
    if ($currentSecond % 20 -ne 0) {
        return
    }

    Clear-Host
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "    FACE RECOGNITION PROCESS MONITOR" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Current Time: $($status.CurrentTime)" -ForegroundColor Yellow
    Write-Host "Schedule: $($Config.StartTime) - $($Config.EndTime)" -ForegroundColor Yellow
    Write-Host "Window: $(if ($status.Schedule.InWindow) { 'ACTIVE' } else { 'INACTIVE' })" `
                -ForegroundColor $(if ($status.Schedule.InWindow) { 'Green' } else { 'Gray' })
    Write-Host ""

    # Show MailKit status with safe property access
    try {
        $mailKitStatus = Get-MailKitStatusReport
        if ($mailKitStatus) {
            $mailKitColor = if ($mailKitStatus.OverallStatus -eq 'READY') { 'Green' }
                            elseif ($mailKitStatus.OverallStatus -eq 'EMAIL_DISABLED') { 'Gray' }
                            else { 'Red' }
            Write-Host "MailKit Status: $($mailKitStatus.OverallStatus)" -ForegroundColor $mailKitColor

            if ($mailKitStatus.AssemblyStatus -and $mailKitStatus.AssemblyStatus.IsAvailable) {
                Write-Host "  Version: $(if ($mailKitStatus.AssemblyStatus.AssemblyVersion) {$mailKitStatus.AssemblyStatus.AssemblyVersion} else {'Unknown'})" -ForegroundColor White
            }
        }
    } catch {
        Write-Host "MailKit Status: ERROR" -ForegroundColor Red
    }
    Write-Host ""

    # Show sudden termination streak info
    if ($SuddenTerminationTracking.CurrentStreak -gt 0) {
        Write-Host "Sudden Termination Streak: $($SuddenTerminationTracking.CurrentStreak)" -ForegroundColor $(if ($SuddenTerminationTracking.CurrentStreak -ge $Config.SuddenTermination.ConsecutiveThreshold) { 'Red' } else { 'Yellow' })
        Write-Host "Threshold: $($Config.SuddenTermination.ConsecutiveThreshold)" -ForegroundColor Gray
        Write-Host ""
    }

    if ($status.PythonRunning) {
        Write-Host "PYTHON STATUS: RUNNING" -ForegroundColor Green
        Write-Host "  PID: $PythonPID" -ForegroundColor White

        # FIX: Add validation for PythonStartTime
        if ($PythonStartTime -and ($PythonStartTime -is [DateTime]) -and ($PythonStartTime.ToString("yyyy-MM-dd HH:mm:ss") -ne "-")) {
            try {
                $runtime = [math]::Round((Get-Date - $PythonStartTime).TotalMinutes, 1)
                Write-Host "  Runtime: $runtime minutes" -ForegroundColor White
            } catch {
                Write-Host "  Runtime: Calculating..." -ForegroundColor Yellow
            }
        } else {
            Write-Host "  Runtime: Starting..." -ForegroundColor Yellow
        }
    } else {
        Write-Host "PYTHON STATUS: STOPPED" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "WORKER STATUS: $(if ($status.WorkerRunning) {'RUNNING'} else {'STOPPED'})" -ForegroundColor $(if ($status.WorkerRunning) {'Green'} else {'Red'})
    if ($status.WorkerRunning) {
        Write-Host "  PID: $WorkerPID" -ForegroundColor White
    }

    Write-Host ""
    if ($LastValidation) {
        if ($LastValidation.Success) {
            Write-Host "LAST VALIDATION: SUCCESS" -ForegroundColor Green
            Write-Host "  Folder: $(Split-Path $LastValidation.RunFolder -Leaf)" -ForegroundColor White
            if ($LastValidation.Warnings.Count -gt 0) {
                Write-Host "  Warnings: $($LastValidation.Warnings.Count)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "LAST VALIDATION: FAILED" -ForegroundColor Red
            Write-Host "  Error: $($LastValidation.Error)" -ForegroundColor Red
        }
    } else {
        Write-Host "LAST VALIDATION: Not yet performed" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "Runs Base Path: $($Config.RunsBasePath)" -ForegroundColor Gray
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop monitor" -ForegroundColor Gray

}

# ====================================================================

# SECTION 9: RECOVERY AND ERROR HANDLING

# ====================================================================

# Enhanced error recovery counter

$Script:ErrorRecoveryCount = 0
$Script:MaxErrorRecoveryAttempts = 3

function Invoke-SafeRecovery {
param([string]$ErrorContext)

    Write-Log "Attempting safe recovery for: $ErrorContext" -Level "WARN"

    # Increment recovery counter
    $Script:ErrorRecoveryCount++

    # Stop any running processes
    Stop-WorkerProcess

    # Clear process tracking
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false

    # Clean up PID file if it exists
    if (Test-Path $Config.PIDFilePath) {
        try {
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            Write-Log "Cleaned up PID tracking file during recovery" -Level "INFO"
        } catch {
            Write-Log "Failed to clean up PID file during recovery: $_" -Level "WARN"
        }
    }

    # Wait for system stabilization
    Start-Sleep -Seconds 5

    # Check if we should continue or exit
    if ($Script:ErrorRecoveryCount -ge $Script:MaxErrorRecoveryAttempts) {
        Write-Log "Maximum recovery attempts ($Script:MaxErrorRecoveryAttempts) reached. Exiting." -Level "ERROR"
        Register-SuddenTermination -Reason "Max recovery attempts reached" -TerminationType "RecoveryExhausted"
        exit 1
    }

    Write-Log "Recovery attempt $Script:ErrorRecoveryCount completed" -Level "INFO"
    return $true

}

# ====================================================================

# SECTION 10: MAIN EXECUTION

# ====================================================================

# Call initialization ONCE at the very beginning

Initialize-ProjectPortablePaths

# Run the MailKit DLL test

Test-MailKitDLLs

# Main execution

try { # Create log directory if it doesn't exist
$logDir = Split-Path $Config.LogFile -Parent
if (-not (Test-Path $logDir)) {
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

    Write-Log "=============== Face Recognition Monitor Started ===============" -Level "INFO"
    Write-Log "Monitor Version: 2.1 (Enhanced with MailKit Verification)" -Level "INFO"

    # Initialize error recovery
    $Script:ErrorRecoveryCount = 0

    Write-Log "Performing early MailKit assembly verification..." -Level "INFO"
    $mailKitStatus = Get-MailKitStatusReport

    if ($Config.SendEmailOnCompletion) {
        if ($mailKitStatus.OverallStatus -eq "READY") {
            Write-Log "MailKit is ready for email functionality" -Level "SUCCESS"
            Write-Log "  - Assembly: $($mailKitStatus.AssemblyStatus.AssemblyLoadMethod)" -Level "INFO"
            Write-Log "  - Version: $($mailKitStatus.AssemblyStatus.AssemblyVersion)" -Level "INFO"
        } else {
            Write-Log "MailKit status: $($mailKitStatus.OverallStatus)" -Level "WARN"

            if ($mailKitStatus.OverallStatus -eq "MISSING_ASSEMBLY") {
                Write-Log "Email functionality will be disabled due to missing MailKit assembly" -Level "ERROR"
                $Config.SendEmailOnCompletion = $false
            }
        }
    }

    # Initialize sudden termination tracking and cleanup
    Initialize-CleanupOnStartup

    # Test email configuration ONCE at startup
    $EmailConfigValid = Test-EmailConfiguration
    if ($EmailConfigValid) {
        Write-Log "Email configuration validated successfully" -Level "SUCCESS"
    }

    # Load existing PID tracking
    if (Load-PIDTracking) {
        Write-Log "Resumed monitoring of existing processes" -Level "SUCCESS"
        # Update process status
        Check-ProcessStatus | Out-Null
    }

    # Load persistent tracking
    Load-PersistentTracking

    # Check for orphaned runs
    Check-OrphanedRuns -LastKnownFolder $global:PersistentTracking.LastKnownRunFolder

    # Ensure runs base path exists
    if (-not (Test-Path $Config.RunsBasePath)) {
        Write-Log "Creating runs base directory: $($Config.RunsBasePath)" -Level "WARN"
        New-Item -ItemType Directory -Path $Config.RunsBasePath -Force | Out-Null
    }

    # Clear console and show initial status
    Clear-Host

    # Register console control handler
    Register-ConsoleControlHandler

    # Main monitoring loop with recovery
    while ($true) {
        # Inside the main while loop, add collection logic:
        if ($processStatus.PythonRunning -and $CurrentRunFolder -and
            (-not $global:CollectedRunFolders.Where({ $_.RunFolder -eq $CurrentRunFolder }))) {
            # Check if the run folder has a completion summary (indicating it's done)
            $completionPath = Join-Path $CurrentRunFolder "Magick_Process_*\logs\completion_summary.txt"
            if (Test-Path $completionPath) {
                Write-Log "Detected completed run, collecting data..." -Level "DEBUG"
                $runData = Collect-RunFolderAttachments -RunFolder $CurrentRunFolder
                if ($runData.Attachments.Count -gt 0) {
                    $global:CollectedRunFolders += $runData
                    Write-Log "Collected completed run: $($runData.RunFolderName)" -Level "INFO"
                    Save-PIDTracking
                }
            }
        }

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

            Write-Log "Check: $currentTime | Window: $(if ($inWindow) {'Active'} else {'Inactive'}) | Python: $(if ($processStatus.PythonRunning) {'Running (PID: ' + $PythonPID + ')'} else {'Stopped'})" -Level "DEBUG"

            # Check if we should start worker
            if ($inWindow -and !$processStatus.PythonRunning) {
                Write-Log "Check: $currentTime | Window: Active | Python: Stopped" -Level "DEBUG"
                Write-Log "Time window active and no Python process running - starting worker..." -Level "INFO"

                # Add delay to prevent rapid restart loops
                if ($LastWorkerAttempt -and ((Get-Date) - $LastWorkerAttempt).TotalSeconds -lt 10) { # Change this to reduce the cooldown time
                    Write-Log "Skipping worker start - too soon after last attempt (10s cooldown)" -Level "DEBUG"
                } else {
                    $started = Start-WorkerProcess
                    $global:LastWorkerAttempt = Get-Date

                    if ($started) {
                        Write-Log "Worker started. Monitoring Python process..." -Level "SUCCESS"
                        # Re-check process status
                        $processStatus = Check-ProcessStatus
                    } else {
                        Write-Log "Worker failed to start. Will retry on next check interval." -Level "WARN"
                    }
                }
            }

            # Check if end time has passed and we should stop
            elseif ($endPassed) {
                # If Python is running, stop it and send email
                if ($processStatus.PythonRunning) {
                    Write-Log "End time reached - stopping processes..." -Level "INFO"
                    Stop-WorkerProcess

                    # Wait for cleanup and output generation
                    Write-Log "Waiting for output generation..." -Level "INFO"
                    Start-Sleep -Seconds 10

                    # Validate the last output
                    Write-Log "Validating final worker output..." -Level "INFO"
                    $LastValidation = Validate-Output

                    # Collect data from the last run if not already collected
                    if ($LastValidation -and $LastValidation.Success -and $LastValidation.RunFolder) {
                        $runData = Collect-RunFolderAttachments -RunFolder $LastValidation.RunFolder
                        if ($runData.Attachments.Count -gt 0) {
                            # Check if we already have this folder
                            $existingIndex = $global:CollectedRunFolders |
                                Where-Object { $_.RunFolder -eq $runData.RunFolder } |
                                Select-Object -First 1

                            if (-not $existingIndex) {
                                $global:CollectedRunFolders += $runData
                                Write-Log "Added final run to collection: $($runData.RunFolderName)" -Level "SUCCESS"
                                }
                            }
                        }

                        # Send completion email if we have collected runs
                        if ($global:CollectedRunFolders.Count -gt 0) {
                            if ($Config.SendEmailOnCompletion -and $EmailConfigValid) {
                                # Send email with all collected runs
                                $allAttachments = @()
                                foreach ($run in $global:CollectedRunFolders) {
                                    $allAttachments += $run.Attachments
                                }

                                # Remove duplicates
                                $allAttachments = $allAttachments | Select-Object -Unique

                                # Send email
                                $emailSent = Send-CompletionEmail -RunFolder $LastValidation.RunFolder -ValidationResult $LastValidation -AllAttachments $allAttachments
                                if ($emailSent) {
                                    Write-Log "Completion emails sent successfully with $($global:CollectedRunFolders.Count) collected runs." -Level "SUCCESS"
                                }
                            }
                        } else {
                        Write-Log "Pipeline completed with validation issues" -Level "WARN"
                    }
                } else {
                    # No Python process running, just log and stop
                    Write-Log "End time reached - no active processes to stop" -Level "INFO"
                }

                # Clear collected data for next day
                $global:CollectedRunFolders = @()
                Save-PersistentTracking

                # Perform graceful shutdown
                Invoke-GracefulShutdown -Reason "Schedule completed"

                # Stop the monitor
                Write-Log "Process completed. Stopping monitor as configured..." -Level "INFO"
                break
            }

        } catch {
            Write-Log "Error in main monitoring loop: $_" -Level "ERROR"
            Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"

            # Attempt recovery
            $recoverySuccess = Invoke-SafeRecovery -ErrorContext "Main loop error: $_"

            if (-not $recoverySuccess) {
                throw "Recovery failed after main loop error"
            }

            # Reset recovery counter on successful loop iteration
            $Script:ErrorRecoveryCount = 0
        }

        # Wait before next check
        Start-Sleep -Seconds $Config.ProcessCheckInterval
    }

}
catch [System.Management.Automation.Host.HostException] {
Write-Log "Monitor interrupted by user" -Level "INFO"
Handle-UnexpectedTermination -Reason "User interrupted (Ctrl+C)"
}
catch {
Write-Log "FATAL ERROR: $_" -Level "ERROR"
    Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
Handle-UnexpectedTermination -Reason "Unhandled exception: $_" -ErrorRecord $\_
}
finally {
Write-Log "Cleaning up..." -Level "INFO"

    # Collect any remaining data before stopping
    if ($CurrentRunFolder -and (Test-Path $CurrentRunFolder)) {
        $runData = Collect-RunFolderAttachments -RunFolder $CurrentRunFolder
        if ($runData.Attachments.Count -gt 0) {
            $global:CollectedRunFolders += $runData
            Write-Log "Collected final run during cleanup: $($runData.RunFolderName)" -Level "INFO"
        }
    }

    Stop-WorkerProcess

    # Record final shutdown
    Record-ProcessStop -StopType "Shutdown" -Reason "Monitor stopping" -WasUnexpected $false

    # Save final persistent tracking
    Save-PersistentTracking

    Write-Log "=============== Face Recognition Monitor Stopped ===============" -Level "INFO"
    Write-Host "Monitor stopped. Collected $($global:CollectedRunFolders.Count) runs." -ForegroundColor Yellow
    Write-Host "Persistent tracking saved for recovery." -ForegroundColor Green

}

# maskDetect-portable.ps1

# ==============================================

# Organized version with unified folder structure

# ==============================================

# ========== PORTABLE PATH INITIALIZATION ==========

function Initialize-ProjectPortablePaths {
[CmdletBinding()]
param()

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

    # Load shared configuration if it exists
    $sharedConfigPath = Join-Path $projectRoot "project_config.psd1"
    if (Test-Path $sharedConfigPath) {
        try {
            $sharedConfig = Import-PowerShellDataFile -Path $sharedConfigPath
            Write-Host "Loaded shared configuration from: $sharedConfigPath" -ForegroundColor Green
        } catch {
            Write-Host "Note: Could not load shared configuration" -ForegroundColor Yellow
        }
    }

    # ====================================================================
    # STEP 2: BUILD PATHS RELATIVE TO PROJECT ROOT
    # ====================================================================

    # Store project root globally so all functions can use it
    $global:ProjectRoot = $projectRoot
    $global:ActiveRoot = Split-Path $projectRoot -Parent | Split-Path -Parent

    # Show what we found
    Write-Host "Project Root: $ProjectRoot" -ForegroundColor Green
    Write-Host "Active Root: $ActiveRoot" -ForegroundColor Green

    # ====================================================================
    # STEP 3: CREATE DATE-BASED FOLDER STRUCTURE
    # ====================================================================

    # Get current date for folder structure
    $currentDate = Get-Date -Format "yyyy-MM-dd"
    $global:CurrentDateFolder = $currentDate  # Store globally for other functions

    # Create the base Magick folder if it doesn't exist
    $magickBasePath = Join-Path $ActiveRoot "logs-running\Magick"
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
    # STEP 4: VALIDATE CRITICAL COMPONENTS EXIST
    # ====================================================================

    # Build portable paths
    $VENV_ROOT = "D:\RaihanFarid\Dokumen\faceRecog\.venv"  # Keep as is or make relative
    $PYTHON_SCRIPT = Join-Path $ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"

    # Base path for all runs (using date-based structure)
    $RUNS_BASE_PATH = $dateBasedPath

    Write-Host "`nValidating project components..." -ForegroundColor Yellow

    $criticalComponents = @(
        @{ Name = "Virtual Environment"; Path = $VENV_ROOT }
        @{ Name = "Python Script"; Path = $PYTHON_SCRIPT }
        @{ Name = "Date-Based Log Directory"; Path = $dateBasedPath }
        @{ Name = "Python Executable"; Path = "$VENV_ROOT\Scripts\python.exe" }
    )

    $missingComponents = @()
    $createdDirectories = @()

    foreach ($component in $criticalComponents) {
        if (!(Test-Path $component.Path)) {
            Write-Host "  [MISSING] $($component.Name): $($component.Path)" -ForegroundColor Red

            # Try to create missing directories
            if ($component.Name -match "Directory") {
                try {
                    New-Item -ItemType Directory -Path $component.Path -Force | Out-Null
                    Write-Host "  [CREATED] Directory: $($component.Path)" -ForegroundColor Yellow
                    $createdDirectories += $component.Path
                } catch {
                    $missingComponents += $component.Name
                }
            } else {
                $missingComponents += $component.Name
            }
        } else {
            Write-Host "  [OK] $($component.Name)" -ForegroundColor Green
        }
    }

    # ====================================================================
    # STEP 5: SUMMARY AND ERROR HANDLING
    # ====================================================================

    if ($missingComponents.Count -gt 0) {
        Write-Host "`nERROR: Missing critical components!" -ForegroundColor Red
        foreach ($missing in $missingComponents) {
            Write-Host "  - $missing" -ForegroundColor Red
        }

        Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
        Write-Host "1. Ensure virtual environment exists at: $VENV_ROOT" -ForegroundColor Yellow
        Write-Host "2. Check that Python script is at: $PYTHON_SCRIPT" -ForegroundColor Yellow
        Write-Host "3. Verify you have read/write permissions" -ForegroundColor Yellow

        $continue = Read-Host "`nSome components are missing. Continue anyway? (Y/N)"
        if ($continue -notmatch '^[Yy]') {
            Write-Host "Exiting script..." -ForegroundColor Red
            exit 1
        }
    }

    if ($createdDirectories.Count -gt 0) {
        Write-Host "`nNote: Created missing directories:" -ForegroundColor Yellow
        foreach ($dir in $createdDirectories) {
            Write-Host "  - $dir" -ForegroundColor Yellow
        }
    }

    Write-Host "`nProject initialization complete!" -ForegroundColor Green
    Write-Host "All paths are now portable and relative to:" -ForegroundColor Green
    Write-Host "  Project Root: $ProjectRoot" -ForegroundColor White
    Write-Host "  Active Date Path: $dateBasedPath" -ForegroundColor White

    # Return the validated paths
    return @{
        ProjectRoot = $projectRoot
        ActiveRoot = $global:ActiveRoot
        ActiveDatePath = $dateBasedPath
        VENV_ROOT = $VENV_ROOT
        PYTHON_SCRIPT = $PYTHON_SCRIPT
        RUNS_BASE_PATH = $dateBasedPath
    }

}

# ========== MAIN EXECUTION ==========

# Initialize portable paths and get validated paths

Write-Host "=== Mask Detection Worker Script ===" -ForegroundColor Cyan
Write-Host "Starting portable path initialization..." -ForegroundColor Cyan

$paths = Initialize-ProjectPortablePaths

# Extract validated paths

$VENV_ROOT = $paths.VENV_ROOT
$PYTHON_SCRIPT = $paths.PYTHON_SCRIPT
$RUNS_BASE_PATH = $paths.RUNS_BASE_PATH
$ProjectRoot = $paths.ProjectRoot
$ActiveDatePath = $paths.ActiveDatePath

# Get current script name for logging

$POWERSHELL_SCRIPT_NAME = Split-Path -Leaf $MyInvocation.MyCommand.Path

# Alternative: Use hashtable for named parameters (more readable)

$PYTHON_PARAMS = @{ # "--database" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\current_database-Copy" # "--input" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\process-run\Run_Classified2026-01-21_15-11-08\script_output\classified_output"
"--multi-source" = $null #Null is for Flag parameter
}

# ===================================

# Helper function to convert hashtable to argument array

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

# If using hashtable approach, convert to array

$PYTHON_ARGS = Convert-HashtableToArgs -Params $PYTHON_PARAMS

# Create runs base directory if it doesn't exist

if (-not (Test-Path $RUNS_BASE_PATH)) {
New-Item -ItemType Directory -Path $RUNS_BASE_PATH -Force | Out-Null
Write-Host "Created runs base directory: $RUNS_BASE_PATH"
}

# Generate run folder with timestamp

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$RUN*FOLDER_NAME = "Magick_Process_MaskDetect*$timestamp"
$RUN_FOLDER_PATH = Join-Path $RUNS_BASE_PATH $RUN_FOLDER_NAME

# Create run folder structure

$RUN_LOGS_PATH = Join-Path $RUN_FOLDER_PATH "logs"
$RUN_SCRIPT_OUTPUT_PATH = Join-Path $RUN_FOLDER_PATH "script_output"
$RUN_METADATA_PATH = Join-Path $RUN_FOLDER_PATH "metadata.json"

try { # Create all directories
New-Item -ItemType Directory -Path $RUN_FOLDER_PATH -Force | Out-Null
New-Item -ItemType Directory -Path $RUN_LOGS_PATH -Force | Out-Null
New-Item -ItemType Directory -Path $RUN_SCRIPT_OUTPUT_PATH -Force | Out-Null

    Write-Host "Created run folder structure at: $RUN_FOLDER_PATH"

} catch {
Write-Error "Failed to create run folder structure: $\_"
exit 1
}

# ========== LOG FILE SETUP ==========

$MAIN_LOG_FILE = Join-Path $RUN_LOGS_PATH "run_$timestamp.log"
$PYTHON_OUTPUT_FILE = Join-Path $RUN_LOGS_PATH "python_output.txt"
$COMPLETION_SUMMARY_FILE = Join-Path $RUN_LOGS_PATH "completion_summary.txt"

# Format arguments for logging

$argsString = $PYTHON_ARGS -join " "

# Write initial log header

"==================================================" | Out-File $MAIN_LOG_FILE
"RUN STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $MAIN_LOG_FILE -Append
"Run Folder: $RUN_FOLDER_PATH" | Out-File $MAIN_LOG_FILE -Append
"PowerShell Script: $POWERSHELL_SCRIPT_NAME" | Out-File $MAIN_LOG_FILE -Append
"Project Root: $ProjectRoot" | Out-File $MAIN_LOG_FILE -Append
"Active Date Path: $ActiveDatePath" | Out-File $MAIN_LOG_FILE -Append
"Virtual Environment: $VENV_ROOT" | Out-File $MAIN_LOG_FILE -Append
"Python Script: $PYTHON_SCRIPT" | Out-File $MAIN_LOG_FILE -Append
"Arguments: $argsString" | Out-File $MAIN_LOG_FILE -Append
"Number of arguments: $($PYTHON_ARGS.Count)" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append
"" | Out-File $MAIN_LOG_FILE -Append

# ========== CREATE METADATA FILE ==========

$metadata = @{
run_id = $timestamp
start_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
powershell_script = $POWERSHELL_SCRIPT_NAME
project_root = $ProjectRoot
active_date_path = $ActiveDatePath
virtual_env = $VENV_ROOT
python_script = $PYTHON_SCRIPT
arguments = $PYTHON_ARGS
arguments_count = $PYTHON_ARGS.Count
run_folder = $RUN_FOLDER_PATH
}

$metadata | ConvertTo-Json | Out-File $RUN_METADATA_PATH
Write-Host "Created metadata file: $RUN_METADATA_PATH"

# ========== EXECUTION ==========

Write-Host "Starting Python script execution..."
Write-Host "Run folder: $RUN_FOLDER_PATH"
Write-Host "Arguments: $argsString"
Write-Host ""

$pythonExe = "$VENV_ROOT\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
$errorMsg = "ERROR: Python executable not found at $pythonExe"
$errorMsg | Out-File $MAIN_LOG_FILE -Append
Write-Error $errorMsg
exit 1
}

# Capture start time

$startTime = Get-Date
"Execution started at: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append

try { # Prepare the command for logging
$commandString = "`"$pythonExe`" `"$PYTHON_SCRIPT`" $argsString"
Write-Host "Executing: $commandString"
$commandString | Out-File $MAIN_LOG_FILE -Append
"" | Out-File $MAIN_LOG_FILE -Append

    Write-Host "Python output will be saved to: $PYTHON_OUTPUT_FILE"

    # ========== KEY CHANGE: Run Python with working directory set to script_output ==========
    # This ensures Python creates its output folder inside our organized structure
    $originalLocation = Get-Location
    Set-Location $RUN_SCRIPT_OUTPUT_PATH

    # Run Python with array of arguments (PowerShell will handle them properly)
    & $pythonExe $PYTHON_SCRIPT $PYTHON_ARGS 2>&1 | Tee-Object -FilePath $PYTHON_OUTPUT_FILE

    $exitCode = $LASTEXITCODE

    # Return to original location
    Set-Location $originalLocation

} catch {
$errorMessage = $\_.Exception.Message
"EXCEPTION: $errorMessage" | Out-File $MAIN_LOG_FILE -Append
$errorMessage | Out-File $PYTHON_OUTPUT_FILE -Append
Write-Error "Exception during Python script execution: $errorMessage"
}

# Capture end time

$endTime = Get-Date
$duration = $endTime - $startTime
$durationFormatted = "{0:D2}:{1:D2}:{2:D2}" -f $duration.Hours, $duration.Minutes, $duration.Seconds

# ========== POST-EXECUTION LOGGING ==========

"" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append
"EXECUTION SUMMARY" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append
"PowerShell Script: $POWERSHELL_SCRIPT_NAME" | Out-File $MAIN_LOG_FILE -Append
"Project Root: $ProjectRoot" | Out-File $MAIN_LOG_FILE -Append
"Active Date Path: $ActiveDatePath" | Out-File $MAIN_LOG_FILE -Append
"Exit code: $exitCode" | Out-File $MAIN_LOG_FILE -Append
"Start time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append
"End time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append
"Duration: $durationFormatted" | Out-File $MAIN_LOG_FILE -Append

# Detailed argument logging

"Arguments passed to Python script:" | Out-File $MAIN_LOG_FILE -Append
for ($i = 0; $i -lt $PYTHON_ARGS.Count; $i++) {
    "  [$i]: $($PYTHON_ARGS[$i])" | Out-File $MAIN_LOG_FILE -Append
}

# Find what Python script created (look for newly created folders in script_output)

try {
$createdFolders = Get-ChildItem -Path $RUN*SCRIPT_OUTPUT_PATH -Directory |
Where-Object { $*.CreationTime -ge $startTime } |
Select-Object -ExpandProperty FullName

    if ($createdFolders) {
        "Python script created folders:" | Out-File $MAIN_LOG_FILE -Append
        foreach ($folder in $createdFolders) {
            "  - $folder" | Out-File $MAIN_LOG_FILE -Append
        }
    } else {
        "No new folders were created by Python script in: $RUN_SCRIPT_OUTPUT_PATH" | Out-File $MAIN_LOG_FILE -Append
    }

} catch {
"Could not analyze created folders: $\_" | Out-File $MAIN_LOG_FILE -Append
}

# ========== CREATE COMPLETION SUMMARY ==========

# $completionSummary = @"

# RUN COMPLETION SUMMARY

Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run ID: $timestamp
PowerShell Script: $POWERSHELL_SCRIPT_NAME
Project Root: $ProjectRoot
Active Date Path: $ActiveDatePath
Status: $(if ($exitCode -eq 0) { "SUCCESS" } else { "FAILED (Exit code: $exitCode)" })

# PORTABLE PATHS USED

Project Root: $ProjectRoot
Active Date Path: $ActiveDatePath
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT

# FOLDER STRUCTURE

Run Folder: $RUN_FOLDER_PATH
├── logs\
│   ├── run_$timestamp.log (This main log file)
│ ├── python_output.txt (Full Python script output)
│ └── completion_summary.txt (This summary)
├── script_output\ (Python script's working directory)
│ └── [Output folders created by Python]
└── metadata.json (Run configuration metadata)

# EXECUTION DETAILS

PowerShell Script: $POWERSHELL_SCRIPT_NAME
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT
Start Time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))
End Time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))
Duration: $durationFormatted

# ARGUMENTS PASSED

$($PYTHON*ARGS | ForEach-Object { " $*" } | Out-String)

# LOG FILES

1. Main Execution Log: $MAIN_LOG_FILE
2. Python Output: $PYTHON_OUTPUT_FILE
3. Python Exit Code: $exitCode

# SCRIPT OUTPUT LOCATION

Any folders/files created by the Python script should be located in:
$RUN_SCRIPT_OUTPUT_PATH

# NOTE: This run uses portable paths that are relative to the project root.

"@

$completionSummary | Out-File $COMPLETION_SUMMARY_FILE

# Update metadata with completion info

$completionMetadata = Get-Content $RUN_METADATA_PATH | ConvertFrom-Json
$completionMetadata | Add-Member -NotePropertyName "end_time" -NotePropertyValue (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Force
$completionMetadata | Add-Member -NotePropertyName "duration" -NotePropertyValue $durationFormatted -Force
$completionMetadata | Add-Member -NotePropertyName "exit_code" -NotePropertyValue $exitCode -Force
$completionMetadata | Add-Member -NotePropertyName "python_pid" -NotePropertyValue $PID -Force  # Store PID for monitoring
$completionMetadata | ConvertTo-Json | Out-File $RUN_METADATA_PATH

# ========== FINAL OUTPUT ==========

Write-Host ""
Write-Host "=================================================="
Write-Host "RUN COMPLETED"
Write-Host "=================================================="
Write-Host "PowerShell Script: $POWERSHELL_SCRIPT_NAME"
Write-Host "Project Root: $ProjectRoot"
Write-Host "Active Date Path: $ActiveDatePath"
Write-Host "Run Folder: $RUN_FOLDER_PATH"
Write-Host "Main Log: $MAIN_LOG_FILE"
Write-Host "Python Output: $PYTHON_OUTPUT_FILE"
Write-Host "Completion Summary: $COMPLETION_SUMMARY_FILE"
Write-Host "Metadata: $RUN_METADATA_PATH"
Write-Host ""
Write-Host "Arguments used:"
$PYTHON*ARGS | ForEach-Object { Write-Host " $*" }
Write-Host ""
Write-Host "All logs and outputs are organized in the run folder."
Write-Host "Exit code: $exitCode"
Write-Host "Duration: $durationFormatted"
Write-Host "=================================================="

# Exit with Python's exit code

exit $exitCode

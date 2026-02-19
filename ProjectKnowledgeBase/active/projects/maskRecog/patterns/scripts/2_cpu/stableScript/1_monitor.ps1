# 1_monitor.ps1
<#
.SYNOPSIS
Enhanced time-based process monitor for Face Recognition pipeline with PID tracking.
Now uses blocking wait for low CPU usage.
#>

# ====================================================================
# LOAD COMMON MODULE – always first
# ====================================================================
$commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
if (-not (Test-Path $commonPathsScript)) { throw "Common paths script not found" }
. $commonPathsScript

$centralConfig = Get-ApplicationConfig

# ====================================================================
# INITIALISE PATHS – single attempt, no fallback clutter
# ====================================================================
Write-Host "Initialising enhanced monitor..." -ForegroundColor Cyan
try {
    $paths = Initialize-ProjectPortablePaths -IsMonitor
} catch {
    Write-Host "FATAL: Paths initialisation failed: $_" -ForegroundColor Red
    exit 1
}
$global:MonitorPaths = $paths

# ====================================================================
# MONITOR‑SPECIFIC CONFIG – built from central config + paths
# ====================================================================
# Default maximum runtime for a single worker (in minutes)
$maxRuntimeMinutes = if ($centralConfig.ContainsKey('MonitorMaxWorkerRuntimeMinutes')) {
    $centralConfig.MonitorMaxWorkerRuntimeMinutes
} else {
    60
}

$Script:Config = @{
    StartTime        = $centralConfig.EveryStartTime
    EndTime          = $centralConfig.EveryEndTime
    WorkerScript     = $paths.WorkerScript
    PythonScript     = $paths.PythonScriptPath
    RunsBasePath     = $paths.DateBasedPath
    PIDFilePath      = $paths.PIDFilePath
    LogFile          = $paths.LogFile
    EmailSenders     = $paths.EmailSendScript
    ProcessCheckInterval = $centralConfig.MonitorProcessCheckInterval   # kept for compatibility, not used in main loop
    MaxPIDFileAgeMinutes = $centralConfig.MonitorMaxPIDFileAgeMinutes
    ExpectedSubfolders   = $centralConfig.ExpectedSubfolders
    ExpectedFiles        = $centralConfig.ExpectedFiles
    MaxValidationRetries = $centralConfig.MaxValidationRetries
    RetryDelaySeconds    = $centralConfig.RetryDelaySeconds
    MaxWorkerRuntimeMinutes = $maxRuntimeMinutes
}

# ====================================================================
# SINGLETON INSTANCE LOCK – improved lock file path
# ====================================================================
$global:MonitorLockFile = Join-Path $env:TEMP "maskRecog_monitor_$PID.lock"
if (Test-Path $global:MonitorLockFile) {
    $existingPID = Get-Content $global:MonitorLockFile -ErrorAction SilentlyContinue
    if ($existingPID) {
        try {
            $null = Get-Process -Id $existingPID -ErrorAction Stop
            Write-Host "Another monitor instance is running (PID: $existingPID). Exiting." -ForegroundColor Yellow
            exit 0
        } catch { Remove-Item $global:MonitorLockFile -Force -ErrorAction SilentlyContinue }
    }
}
$PID | Out-File $global:MonitorLockFile -Force

# ====================================================================
# LOCAL LOGGING WRAPPER – uses shared Write-CommonLog
# ====================================================================
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    Write-CommonLog -Message $Message -Level $Level -LogFile $Script:Config.LogFile
}

# ====================================================================
# GLOBAL STATE – with missing console‑handler defaults added
# ====================================================================
$global:WorkerProcess = $null
$global:WorkerPID = $null
$global:PythonPID = $null
$global:WorkerStartTime = $null
$global:PythonStartTime = $null
$global:WorkerIsRunning = $false
$global:PythonIsRunning = $false
$global:LastWorkerAttempt = $null
$global:CollectedRunFolders = @()
$global:IsShuttingDown = $false
$global:ForceStopWindowSeconds = 3
$global:ForceStopThreshold = 2
$global:ForceStopAttempts = 0
$global:LastForceStopTime = $null

# ====================================================================
# CONSOLE CONTROL HANDLER – uses the newly defined globals
# ====================================================================
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class ConsoleCtrlHandler {
    public delegate bool ConsoleEventDelegate(int eventType);
    [DllImport("kernel32.dll")] public static extern bool SetConsoleCtrlHandler(ConsoleEventDelegate handler, bool add);
}
"@
$handler = [ConsoleCtrlHandler+ConsoleEventDelegate]{
    param($eventType)
    $current = Get-Date
    $sinceLast = if ($global:LastForceStopTime) { ($current - $global:LastForceStopTime).TotalSeconds } else { [double]::MaxValue }
    switch ($eventType) {
        { $_ -in 0,1 } {
            Write-Host "`n[Console] Control event detected" -ForegroundColor Yellow
            if ($sinceLast -lt $global:ForceStopWindowSeconds) {
                $global:ForceStopAttempts++
                Write-Host "  Rapid attempt ($global:ForceStopAttempts/$global:ForceStopThreshold)" -ForegroundColor Yellow
            } else { $global:ForceStopAttempts = 1 }
            $global:LastForceStopTime = $current
            if ($global:ForceStopAttempts -ge $global:ForceStopThreshold) {
                Write-Host "  Force shutdown requested" -ForegroundColor Red
                $global:IsShuttingDown = $true
                return $true
            }
            Write-Host "  Press Ctrl+C again within $($global:ForceStopWindowSeconds)s to force stop." -ForegroundColor Yellow
            return $true
        }
        default { return $false }
    }
}
[void][ConsoleCtrlHandler]::SetConsoleCtrlHandler($handler, $true)

# ====================================================================
# Process Management Functions
# ====================================================================
function Is-ProcessRunning {
    param(
        [int]$ProcessId, 
        [string]$ProcessName
    )
    if (-not $ProcessId -or $ProcessId -eq 0) { return $false }
    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
        if ($ProcessName) {
            return ($process.ProcessName -like "*$ProcessName*" -and (-not $process.HasExited))
        }
        return (-not $process.HasExited)
    } catch { return $false }
}

function Find-PythonProcess {
    Write-Log "Looking for Python PID from available data..." -Level "DEBUG"
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        Write-Log "Using Python PID from worker output: $global:PythonPID" -Level "DEBUG"
        return $global:PythonPID
    }
    $runFolder = Find-LatestRunFolder
    if ($runFolder) {
        $metadataPath = Join-Path $runFolder.FullName "metadata.json"
        if (Test-Path $metadataPath) {
            try {
                $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
                if ($metadata.PSObject.Properties.Name -contains "python_pid") {
                    $foundPID = $metadata.python_pid
                    Write-Log "Found Python PID in metadata: $foundPID" -Level "INFO"
                    return $foundPID
                }
            } catch { }
        }
    }
    Write-Log "No Python process data available yet" -Level "DEBUG"
    return $null
}

# ====================================================================
# Modified Start-WorkerProcess – returns process object
# ====================================================================
function Start-WorkerProcess {
    Write-Log "Starting face recognition worker..." -Level "INFO"
    try {
        if (-not (Test-Path $Script:Config.WorkerScript)) {
            Write-Log "ERROR: Worker script not found at: $($Script:Config.WorkerScript)" -Level "ERROR"
            return $null
        }
        Write-Log "Starting worker process..." -Level "INFO"
        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processInfo.FileName = "powershell.exe"
        $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$($Script:Config.WorkerScript)`"")
        $processInfo.Arguments = $arguments
        $processInfo.UseShellExecute = $false
        $processInfo.RedirectStandardOutput = $true
        $processInfo.RedirectStandardError = $true
        $processInfo.CreateNoWindow = $true
        $workerProcess = New-Object System.Diagnostics.Process
        $workerProcess.StartInfo = $processInfo

        $stdOutBuilder = New-Object System.Text.StringBuilder
        $stdErrBuilder = New-Object System.Text.StringBuilder

        $outAction = { if (-not [String]::IsNullOrEmpty($EventArgs.Data)) { $Event.MessageData.AppendLine($EventArgs.Data) } }
        $errAction = { if (-not [String]::IsNullOrEmpty($EventArgs.Data)) { $Event.MessageData.AppendLine($EventArgs.Data) } }

        $stdOutEvent = Register-ObjectEvent -InputObject $workerProcess -EventName 'OutputDataReceived' -Action $outAction -MessageData $stdOutBuilder
        $stdErrEvent = Register-ObjectEvent -InputObject $workerProcess -EventName 'ErrorDataReceived' -Action $errAction -MessageData $stdErrBuilder

        if ($workerProcess.Start()) {
            $global:WorkerPID = $workerProcess.Id
            $global:WorkerStartTime = Get-Date
            $global:WorkerIsRunning = $true
            $global:WorkerProcess = $workerProcess
            Write-Log "Worker process started (PID: $global:WorkerPID)" -Level "SUCCESS"
            $workerProcess.BeginOutputReadLine()
            $workerProcess.BeginErrorReadLine()
            Start-Sleep -Seconds 2

            if ($workerProcess.HasExited) {
                $exitCode = $workerProcess.ExitCode
                $output = $stdOutBuilder.ToString()
                $errorOutput = $stdErrBuilder.ToString()
                Write-Log "Worker process exited immediately with code: $exitCode" -Level "ERROR"
                if ($output) { foreach ($line in $output -split "`n") { if ($line.Trim()) { Write-Log "  $line" -Level "DEBUG" } } }
                if ($errorOutput) { foreach ($line in $errorOutput -split "`n") { if ($line.Trim()) { Write-Log "  $line" -Level "ERROR" } } }
                Unregister-Event -SourceIdentifier $stdOutEvent.Name -ErrorAction SilentlyContinue
                Unregister-Event -SourceIdentifier $stdErrEvent.Name -ErrorAction SilentlyContinue
                return $null
            }

            Write-Log "Worker process is running, waiting for Python..." -Level "INFO"
            $maxWait = 60; $waited = 0
            while ($waited -lt $maxWait) {
                $foundPID = Find-PythonProcess
                if ($foundPID) {
                    $global:PythonPID = $foundPID
                    $global:PythonIsRunning = $true
                    $global:PythonStartTime = Get-Date
                    Write-Log "Python process found (PID: $global:PythonPID)" -Level "SUCCESS"
                    Save-PIDTracking
                    Unregister-Event -SourceIdentifier $stdOutEvent.Name -ErrorAction SilentlyContinue
                    Unregister-Event -SourceIdentifier $stdErrEvent.Name -ErrorAction SilentlyContinue
                    return $workerProcess
                }
                Start-Sleep -Seconds 5; $waited += 5
                if ($workerProcess.HasExited) {
                    Write-Log "Worker process exited while waiting for Python" -Level "ERROR"
                    break
                }
            }
            Write-Log "Python process not found within $maxWait seconds" -Level "WARN"
            Unregister-Event -SourceIdentifier $stdOutEvent.Name -ErrorAction SilentlyContinue
            Unregister-Event -SourceIdentifier $stdErrEvent.Name -ErrorAction SilentlyContinue
            Save-PIDTracking
            return $workerProcess
        } else {
            Write-Log "Failed to start worker process" -Level "ERROR"
            return $null
        }
    } catch {
        Write-Log "ERROR starting worker: $_" -Level "ERROR"
        Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
        return $null
    }
}

function Stop-WorkerProcess {
    Write-Log "Stopping worker process..." -Level "INFO"
    $stoppedProcesses = @()
    $processesToStop = @()
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        try {
            $pythonProcess = Get-Process -Id $global:PythonPID -ErrorAction SilentlyContinue
            if ($pythonProcess -and (-not $pythonProcess.HasExited)) {
                $processesToStop += @{ Type = "Python"; PID = $global:PythonPID; Process = $pythonProcess }
            }
        } catch { Write-Log "Python process not found (PID: $global:PythonPID) - $_" -Level "DEBUG" }
    }
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        try {
            $workerProcess = Get-Process -Id $global:WorkerPID -ErrorAction SilentlyContinue
            if ($workerProcess -and (-not $workerProcess.HasExited)) {
                $processesToStop += @{ Type = "Worker"; PID = $global:WorkerPID; Process = $workerProcess }
            }
        } catch { Write-Log "Worker process not found (PID: $global:WorkerPID) - $_" -Level "DEBUG" }
    }
    foreach ($procInfo in $processesToStop | Where-Object { $_.Type -eq "Python" }) {
        Write-Log "Stopping $($procInfo.Type) process (PID: $($procInfo.PID))..." -Level "INFO"
        try {
            $procInfo.Process.Kill()
            Write-Log "Waiting 10 seconds for Python process to stop completely..." -Level "WARN"
            Start-Sleep -Seconds 10
            $timeout = 10
            $startTime = Get-Date
            while ((-not $procInfo.Process.HasExited) -and ((Get-Date) - $startTime).TotalSeconds -lt $timeout) { Start-Sleep -Milliseconds 100 }
            if ($procInfo.Process.HasExited) { $stoppedProcesses += $procInfo.Type; Write-Log "$($procInfo.Type) process stopped successfully" -Level "SUCCESS" }
            else { Write-Log "$($procInfo.Type) process did not stop within timeout" -Level "WARN" }
        } catch { Write-Log "Error stopping $($procInfo.Type) process: $_" -Level "ERROR" }
    }
    foreach ($procInfo in $processesToStop | Where-Object { $_.Type -eq "Worker" }) {
        Write-Log "Stopping $($procInfo.Type) process (PID: $($procInfo.PID))..." -Level "INFO"
        try {
            if ($procInfo.Process.CloseMainWindow()) {
                $timeout = 5
                $startTime = Get-Date
                while ((-not $procInfo.Process.HasExited) -and ((Get-Date) - $startTime).TotalSeconds -lt $timeout) { Start-Sleep -Milliseconds 100 }
            }
            if (-not $procInfo.Process.HasExited) { $procInfo.Process.Kill(); Start-Sleep -Seconds 2 }
            if ($procInfo.Process.HasExited) { $stoppedProcesses += $procInfo.Type; Write-Log "$($procInfo.Type) process stopped successfully" -Level "SUCCESS" }
        } catch { Write-Log "Error stopping $($procInfo.Type) process: $_" -Level "ERROR" }
    }
    Write-Log "Checking for known orphaned processes..." -Level "INFO"
    $orphanedProcesses = @()
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        try {
            $proc = Get-Process -Id $global:PythonPID -ErrorAction SilentlyContinue
            if ($proc -and (-not $proc.HasExited)) { Write-Log "Found orphaned Python process (PID: $global:PythonPID) - terminating" -Level "WARN"; $proc.Kill(); $orphanedProcesses += "Python:$global:PythonPID"; Start-Sleep -Seconds 1 }
        } catch { }
    }
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false
    $global:WorkerStartTime = $null
    $global:PythonStartTime = $null
    $commPaths = Initialize-CommunicationPaths -Paths $global:MonitorPaths -IsMonitor
    if (Test-Path $commPaths.CommunicationDir) { Remove-Item -Path $commPaths.CommunicationDir -Recurse -Force -ErrorAction SilentlyContinue; Write-Log "Cleaned up communication directory" -Level "DEBUG" }
    if ($stoppedProcesses.Count -gt 0) { Write-Log "Successfully stopped processes: $($stoppedProcesses -join ', ')" -Level "INFO" }
    if ($orphanedProcesses.Count -gt 0) { Write-Log "Cleaned up orphaned processes: $($orphanedProcesses.Count)" -Level "INFO" }
    Write-Log "Worker process cleanup completed" -Level "INFO"
}

# ====================================================================
# Email Reporting Integration (unchanged)
# ====================================================================
function Initialize-EmailReporting {
    Write-Log "Initializing email reporting..." -Level "INFO"
    $emailSenderScript = $Script:Config.EmailSenders
    if (Test-Path $emailSenderScript) {
        try {
            Remove-Item "function:Invoke-StableEmailReport" -ErrorAction SilentlyContinue
            Remove-Item "function:Register-StableEmailSender" -ErrorAction SilentlyContinue
            Remove-Item "function:Send-RunReport" -ErrorAction SilentlyContinue
            . $emailSenderScript
            if (-not (Get-Command -Name "Invoke-StableEmailReport" -ErrorAction SilentlyContinue)) {
                Write-Log "ERROR: Invoke-StableEmailReport function not found after loading script" -Level "ERROR"
                return $false
            }
            $emailConfig = @{
                ScheduleStartTime = $Script:Config.StartTime
                ScheduleEndTime = $Script:Config.EndTime
                EmailSubject = "[FaceRecog] Runs - $(Get-Date -Format 'yyyy-MM-dd') - Schedule: $($Script:Config.StartTime)-$($Script:Config.EndTime)"
            }
            $registrationResult = Register-StableEmailSender -MonitorConfig $Script:Config -CustomEmailConfig $emailConfig
            if ($registrationResult -and $global:StableEmailSender) {
                Write-Log "Stable Email sender initialized successfully" -Level "SUCCESS"
                return $true
            } else { Write-Log "Failed to register stable email sender" -Level "ERROR"; return $false }
        } catch {
            Write-Log "Failed to initialize email reporting: $_" -Level "ERROR"
            Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
            return $false
        }
    } else { Write-Log "Email sender script not found: $emailSenderScript" -Level "WARN"; return $false }
}

function Invoke-EmailReport {
    [CmdletBinding()] param(
        [switch]$Force = $false,
        [array]$CollectedRuns = $null           
        )

    Write-Log "Scheduled email report triggered..." -Level "INFO"
    Write-Log "Email configuration:" -Level "DEBUG"
    Write-Log "  Start time: $($Script:Config.StartTime)" -Level "DEBUG"
    Write-Log "  End time: $($Script:Config.EndTime)" -Level "DEBUG"
    Write-Log "  Runs base path: $($Script:Config.RunsBasePath)" -Level "DEBUG"

    try {
        if (-not (Get-Command -Name "Invoke-StableEmailReport" -ErrorAction SilentlyContinue)) {
            Write-Log "Invoke-StableEmailReport function not available, attempting to load email sender..." -Level "WARN"
            $emailTestScript = $Script:Config.EmailSenders
            if (Test-Path $emailTestScript) { . $emailTestScript; Write-Log "Email sender script reloaded" -Level "INFO" }
            else { Write-Log "ERROR: Email sender script not found at: $emailTestScript" -Level "ERROR"; return $false }
        }
        if (-not $global:StableEmailSender -or -not $global:StableEmailSender.Enabled) {
            Write-Log "Stable email sender not registered or disabled, attempting to initialize..." -Level "WARN"
            $reinitialized = Initialize-EmailReporting
            if (-not $reinitialized) { Write-Log "Failed to re-initialize email reporting" -Level "ERROR"; return $false }
        }
        Write-Log "Sending email report for schedule starting at: $($Script:Config.StartTime)" -Level "INFO"

        # Pass CollectedRuns to the stable sender
        $success = Invoke-StableEmailReport -Force:$Force -CollectedRuns $CollectedRuns
        if ($success) { Write-Log "Email report sent successfully!" -Level "SUCCESS" }
        else { Write-Log "Failed to send email report" -Level "ERROR" }
        return $success
    } catch {
        Write-Log "Error in email report: $_" -Level "ERROR"
        Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
        return $false
    }
}


# ====================================================================
# PID Tracking (kept for compatibility)
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
    } catch { Write-Log "Failed to save PID tracking: $_" -Level "ERROR" -LogFile $Script:Config.LogFile }
}

# ====================================================================
# Folder and Validation Functions
# ====================================================================
function Find-LatestRunFolder {
    try {
        if (-not $Script:Config.RunsBasePath -or -not (Test-Path $Script:Config.RunsBasePath)) { return $null }
        $folders = Get-ChildItem -Path $Script:Config.RunsBasePath -Directory -Filter $Script:Config.OutputFolderPattern -ErrorAction SilentlyContinue
        if (-not $folders) { return $null }
        return $folders | Sort-Object CreationTime -Descending | Select-Object -First 1
    } catch { Write-Log "Error finding run folders: $_" -Level "ERROR"; return $null }
}

function Validate-Output {
    param(
        [int]$RetryCount = 0,
        [switch]$CollectAll = $false,
        [DateTime]$CollectionStart = $null,
        [DateTime]$CollectionEnd = $null
    )
    if ($CollectAll) {
        $start = if ($null -ne $CollectionStart) { $CollectionStart } else {
            [DateTime]::ParseExact((Get-Date -Format "yyyy-MM-dd") + " " + $Script:Config.StartTime, "yyyy-MM-dd HH:mm", $null)
        }
        $end = if ($null -ne $CollectionEnd) { $CollectionEnd } else {
            [DateTime]::ParseExact((Get-Date -Format "yyyy-MM-dd") + " " + $Script:Config.EndTime, "yyyy-MM-dd HH:mm", $null)
        }
        $collected = Collect-RunsFromTimeWindow -BasePath $Script:Config.RunsBasePath -WindowStart $start -WindowEnd $end -ValidateEach
        $global:CollectedRunFolders = $collected
        $valid = ($collected | Where-Object { $_.Status -eq "VALID" }).Count
        $invalid = ($collected | Where-Object { $_.Status -eq "INVALID" }).Count
        return @{
            Success = ($invalid -eq 0)
            Mode = "COLLECT_ALL"
            CollectionResults = @{ TotalRuns = $collected.Count; ValidRuns = $valid; InvalidRuns = $invalid }
            TotalRuns = $collected.Count
            ValidRuns = $valid
            InvalidRuns = $invalid
        }
    } else {
        $folder = Get-LatestRunFolder -BasePath $Script:Config.RunsBasePath
        if (-not $folder) {
            if ($RetryCount -lt $Script:Config.MaxValidationRetries) {
                Start-Sleep -Seconds $Script:Config.RetryDelaySeconds
                return Validate-Output -RetryCount ($RetryCount+1)
            }
            return @{ Success = $false; Mode = "SINGLE"; Error = "No output folder created" }
        }
        $validation = Test-RunFolder -FolderPath $folder.FullName
        $global:CurrentRunFolder = $folder.FullName
        return @{
            Success = $validation.Success
            Mode = "SINGLE"
            RunFolder = $folder.FullName
            FolderName = $folder.Name
            ValidationDetails = $validation
        }
    }
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
# MAIN EXECUTION – redesigned with blocking waits
# ====================================================================
try {
    if ($Script:Config.LogFile) {
        $null = New-Item -ItemType Directory -Path (Split-Path $Script:Config.LogFile -Parent) -Force
    }

    Write-Log "=== Enhanced Face Recognition Monitor Started ===" -Level "INFO"
    Write-Log "Version: 2.2 (Blocking wait, low CPU)" -Level "INFO"
    Write-Log "Start Time: $($Script:Config.StartTime)" -Level "INFO"
    Write-Log "End Time: $($Script:Config.EndTime)" -Level "INFO"
    Write-Log "Max Worker Runtime: $($Script:Config.MaxWorkerRuntimeMinutes) minutes" -Level "INFO"

    if (-not (Test-Path $Script:Config.RunsBasePath)) {
        New-Item -ItemType Directory -Path $Script:Config.RunsBasePath -Force | Out-Null
    }

    $emailReportingInitialized = Initialize-EmailReporting

    # Determine absolute start and end DateTimes for today
    $today = Get-Date -Format "yyyy-MM-dd"
    $startDateTime = [DateTime]::ParseExact("$today $($Script:Config.StartTime)", "yyyy-MM-dd HH:mm", $null)
    $endDateTime   = [DateTime]::ParseExact("$today $($Script:Config.EndTime)",   "yyyy-MM-dd HH:mm", $null)

    # If current time is already past end time, collect and exit immediately
    if ((Get-Date) -gt $endDateTime) {
        Write-Log "Current time is past end time. Starting immediate collection and exit." -Level "WARN"
        $global:LastValidation = Validate-Output -CollectAll -CollectionStart $startDateTime -CollectionEnd $endDateTime
        if ($emailReportingInitialized) {
            Invoke-EmailReport -Force -CollectedRuns $global:CollectedRunFolders   # <-- added CollectedRuns
        }
        exit 0
    }

    

    # Wait until start time if we are too early
    $now = Get-Date
    if ($now -lt $startDateTime) {
        $waitSeconds = ($startDateTime - $now).TotalSeconds
        Write-Log "Waiting $([math]::Round($waitSeconds,0)) seconds until start time $($Script:Config.StartTime) ..." -Level "INFO"
        Start-Sleep -Seconds $waitSeconds   # blocking wait – zero CPU
    }

    # We are now within the active window
    Write-Log "Entering active window. Will run workers until $($Script:Config.EndTime)" -Level "INFO"

    # Main loop: run workers sequentially until end time
    while ((Get-Date) -lt $endDateTime) {
        # Start a worker only if none is currently running
        if (-not $global:WorkerIsRunning) {
            $worker = Start-WorkerProcess
            if (-not $worker) {
                Write-Log "Failed to start worker. Retrying in 60 seconds." -Level "ERROR"
                Start-Sleep -Seconds 60
                continue
            }
            # Worker process is now running; it has set $global:WorkerPID, $global:PythonPID, etc.
        }

        # Calculate timeout: either the maximum allowed runtime or the time remaining until end of window
        $remainingToEnd = ($endDateTime - (Get-Date)).TotalMilliseconds
        $timeoutMs = [math]::Min($Script:Config.MaxWorkerRuntimeMinutes * 60 * 1000, $remainingToEnd)
        if ($timeoutMs -le 0) { break }   # window already closed

        Write-Log "Waiting for worker (PID: $global:WorkerPID) to finish (timeout = $([math]::Round($timeoutMs/1000/60,1)) minutes)..." -Level "INFO"

        # BLOCKING WAIT – process suspended, zero CPU
        $exited = $global:WorkerProcess.WaitForExit($timeoutMs)

        if ($exited) {
            # Worker exited naturally
            $exitCode = $global:WorkerProcess.ExitCode
            Write-Log "Worker exited naturally with code $exitCode" -Level "INFO"
            $global:WorkerIsRunning = $false
            $global:WorkerProcess.Dispose()
            # Optionally, collect this single run immediately? Not required; final collection will catch it.
            # Continue loop to possibly start another worker if still within window.
        } else {
            # Timeout reached – worker took too long or end time arrived
            Write-Log "Worker exceeded allowed runtime or end time reached. Terminating..." -Level "WARN"
            Stop-WorkerProcess
            # After termination, break out of loop because we are likely at or past end time.
            break
        }
    }

    # End of window: collect all runs in the window and send email report
    Write-Log "End time reached or window closed. Collecting runs and sending report." -Level "INFO"
    $global:LastValidation = Validate-Output -CollectAll -CollectionStart $startDateTime -CollectionEnd $endDateTime
    if ($emailReportingInitialized) {
        Invoke-EmailReport -Force -CollectedRuns $global:CollectedRunFolders   # <-- added CollectedRuns
    }

} catch {
    Write-Log "FATAL ERROR: $_" -Level "ERROR"
} finally {
    Write-Log "Cleaning up..." -Level "INFO"
    Stop-WorkerProcess
    if (Test-Path $global:MonitorLockFile) { Remove-Item $global:MonitorLockFile -Force }
    Write-Log "=== Monitor Stopped ===" -Level "INFO"
    Write-Host "`n================================================" -ForegroundColor Cyan
    Write-Host "MONITOR STOPPED" -ForegroundColor Yellow
    Write-Host "Log file: $($Script:Config.LogFile)" -ForegroundColor White
    Write-Host "Collected folders with full data: $($global:CollectedRunFolders.Count)" -ForegroundColor White
    Write-Host "================================================" -ForegroundColor Cyan
}
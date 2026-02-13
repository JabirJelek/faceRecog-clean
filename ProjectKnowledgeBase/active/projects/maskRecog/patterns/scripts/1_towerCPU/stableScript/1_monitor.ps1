# 1_monitor.ps1
<#
.SYNOPSIS
Enhanced time-based process monitor for Face Recognition pipeline with PID tracking.
#>

# ====================================================================
# LOAD COMMON MODULE
# ====================================================================
$commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
if (-not (Test-Path $commonPathsScript)) { throw "Common paths script not found" }
. $commonPathsScript

$centralConfig = Get-ApplicationConfig

# ====================================================================
# INITIALISE PATHS
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
# MONITOR‑SPECIFIC CONFIG
# ====================================================================
$Script:Config = @{
    StartTime        = $centralConfig.EveryStartTime
    EndTime          = $centralConfig.EveryEndTime
    WorkerScript     = $paths.WorkerScript
    PythonScript     = $paths.PythonScriptPath
    RunsBasePath     = $paths.DateBasedPath
    PIDFilePath      = $paths.PIDFilePath
    LogFile          = $paths.LogFile
    EmailSenders     = $paths.EmailSendScript
    MonitorMetadataFile = $paths.MonitorMetadataFile           # <-- NEW
    ProcessCheckInterval = $centralConfig.MonitorProcessCheckInterval
    MaxPIDFileAgeMinutes = $centralConfig.MonitorMaxPIDFileAgeMinutes
    ExpectedSubfolders   = $centralConfig.ExpectedSubfolders
    ExpectedFiles        = $centralConfig.ExpectedFiles
    MaxValidationRetries = $centralConfig.MaxValidationRetries
    RetryDelaySeconds    = $centralConfig.RetryDelaySeconds
}

# ====================================================================
# SINGLETON INSTANCE LOCK (using shared function)
# ====================================================================
$lock = Acquire-SingletonLock -LockName "monitor_TowerCPU" -TimeoutSeconds 30
if (-not $lock.Acquired) {
    Write-Host "Another monitor instance is running. Exiting." -ForegroundColor Yellow
    exit 0
}
$global:MonitorLockFile = $lock.LockFile

# ====================================================================
# LOCAL LOGGING WRAPPER 
# ====================================================================
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    Write-CommonLog -Message $Message -Level $Level -LogFile $paths.LogFile
}


# ====================================================================
# GLOBAL STATE
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

# --- Monitor metadata ---
$global:MonitorStartTime = Get-Date
$global:MonitorExitCode = 0

# ====================================================================
# CONSOLE CONTROL HANDLER
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
                $global:MonitorExitCode = 1
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
# CREATE / UPDATE MONITOR METADATA
# ====================================================================
function Write-MonitorMetadata {
    param([switch]$Final = $false)
    $metadata = @{
        monitor_pid = $PID
        monitor_start_time = $global:MonitorStartTime.ToString("yyyy-MM-dd HH:mm:ss")
        scheduled_start = $centralConfig.EveryStartTime
        scheduled_end   = $centralConfig.EveryEndTime
        runs_base_path  = $paths.DateBasedPath
        log_file        = $paths.LogFile
    }
    if ($Final) {
        $metadata.monitor_end_time = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        $start = [datetime]::ParseExact($metadata.monitor_start_time, "yyyy-MM-dd HH:mm:ss", $null)
        $end   = [datetime]::ParseExact($metadata.monitor_end_time,   "yyyy-MM-dd HH:mm:ss", $null)
        $metadata.duration = "{0:hh\:mm\:ss}" -f ($end - $start)
        $metadata.exit_code = $global:MonitorExitCode
    }
    try {
        $metadata | ConvertTo-Json | Out-File $paths.MonitorMetadataFile -Force
        Write-Log "Monitor metadata $(if($Final){'final'}else{'initial'}) written" -Level "DEBUG"
    } catch { Write-Log "Failed to write monitor metadata: $_" -Level "ERROR" }
}


# ====================================================================
# PROCESS MANAGEMENT FUNCTIONS
# ====================================================================
function Check-ProcessStatus {
    $status = @{
        WorkerRunning = $false
        PythonRunning = $false
        WorkerPID = $global:WorkerPID
        PythonPID = $global:PythonPID
    }
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        $status.WorkerRunning = Is-ProcessRunning -ProcessId $global:WorkerPID -ProcessName "powershell"
    }
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        $status.PythonRunning = Is-ProcessRunning -ProcessId $global:PythonPID -ProcessName "python"
    }
    $global:WorkerIsRunning = $status.WorkerRunning
    $global:PythonIsRunning = $status.PythonRunning
    return $status
}

function Is-ProcessRunning {
    param([int]$ProcessId, [string]$ProcessName)
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

function Start-WorkerProcess {
    Write-Log "Starting face recognition worker..." -Level "INFO"
    try {
        Write-Log "Worker script path: $($Script:Config.WorkerScript)" -Level "INFO"
        if ([string]::IsNullOrEmpty($Script:Config.WorkerScript)) {
            Write-Log "ERROR: Worker script path is null or empty" -Level "ERROR"
            return $false
        }
        if (-not (Test-Path $Script:Config.WorkerScript)) {
            Write-Log "ERROR: Worker script not found at: $($Script:Config.WorkerScript)" -Level "ERROR"
            return $false
        }
        Write-Log "Starting worker process..." -Level "INFO"
        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processInfo.FileName = "powershell.exe"
        $arguments = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$($Script:Config.WorkerScript)`""
        )
        $processInfo.Arguments = $arguments
        $processInfo.UseShellExecute = $false
        $processInfo.RedirectStandardOutput = $true
        $processInfo.RedirectStandardError = $true
        $processInfo.CreateNoWindow = $true
        
        $WorkerProcess = New-Object System.Diagnostics.Process
        $WorkerProcess.StartInfo = $processInfo
        
        $stdOutBuilder = New-Object System.Text.StringBuilder
        $stdErrBuilder = New-Object System.Text.StringBuilder
        
        $outAction = {
            if (-not [String]::IsNullOrEmpty($EventArgs.Data)) {
                $Event.MessageData.AppendLine($EventArgs.Data)
                if ($EventArgs.Data -match "Python process started \(PID: (\d+)\)") {
                    $global:PythonPID = $matches[1]
                    Write-Log "Captured Python PID from worker output: $global:PythonPID" -Level "SUCCESS"
                }
                Write-Log "Worker Output: $($EventArgs.Data)" -Level "DEBUG"
            }
        }
        $errAction = {
            if (-not [String]::IsNullOrEmpty($EventArgs.Data)) {
                $Event.MessageData.AppendLine($EventArgs.Data)
                Write-Log "Worker Error: $($EventArgs.Data)" -Level "ERROR"
            }
        }
        
        $stdOutEvent = Register-ObjectEvent -InputObject $WorkerProcess -EventName 'OutputDataReceived' -Action $outAction -MessageData $stdOutBuilder
        $stdErrEvent = Register-ObjectEvent -InputObject $WorkerProcess -EventName 'ErrorDataReceived' -Action $errAction -MessageData $stdErrBuilder
        
        if ($WorkerProcess.Start()) {
            $global:WorkerPID = $WorkerProcess.Id
            $global:WorkerStartTime = Get-Date
            $global:WorkerIsRunning = $true
            Write-Log "Worker process started (PID: $global:WorkerPID)" -Level "SUCCESS"
            $WorkerProcess.BeginOutputReadLine()
            $WorkerProcess.BeginErrorReadLine()
            Start-Sleep -Seconds 2
            
            if ($WorkerProcess.HasExited) {
                $exitCode = $WorkerProcess.ExitCode
                $output = $stdOutBuilder.ToString()
                $errorOutput = $stdErrBuilder.ToString()
                Write-Log "Worker process exited immediately with code: $exitCode" -Level "ERROR"
                if ($output) {
                    foreach ($line in $output -split "`n") {
                        if ($line.Trim()) { Write-Log "  $line" -Level "DEBUG" }
                    }
                }
                if ($errorOutput) {
                    foreach ($line in $errorOutput -split "`n") {
                        if ($line.Trim()) { Write-Log "  $line" -Level "ERROR" }
                    }
                }
                if ($stdOutEvent) { Unregister-Event -SourceIdentifier $stdOutEvent.Name -ErrorAction SilentlyContinue }
                if ($stdErrEvent) { Unregister-Event -SourceIdentifier $stdErrEvent.Name -ErrorAction SilentlyContinue }
                return $false
            }
            
            Write-Log "Worker process is running, waiting for Python..." -Level "INFO"
            $maxWait = 60
            $waited = 0
            while ($waited -lt $maxWait) {
                $foundPID = Find-PythonProcess
                if ($foundPID) {
                    $global:PythonPID = $foundPID
                    $global:PythonIsRunning = $true
                    $global:PythonStartTime = Get-Date
                    Write-Log "Python process found (PID: $global:PythonPID)" -Level "SUCCESS"
                    Save-PIDTracking
                    if ($stdOutEvent) { Unregister-Event -SourceIdentifier $stdOutEvent.Name -ErrorAction SilentlyContinue }
                    if ($stdErrEvent) { Unregister-Event -SourceIdentifier $stdErrEvent.Name -ErrorAction SilentlyContinue }
                    return $true
                }
                Start-Sleep -Seconds 5
                $waited += 5
                if ($WorkerProcess.HasExited) {
                    Write-Log "Worker process exited while waiting for Python" -Level "ERROR"
                    break
                }
            }
            Write-Log "Python process not found within $maxWait seconds" -Level "WARN"
            if ($stdOutEvent) { Unregister-Event -SourceIdentifier $stdOutEvent.Name -ErrorAction SilentlyContinue }
            if ($stdErrEvent) { Unregister-Event -SourceIdentifier $stdErrEvent.Name -ErrorAction SilentlyContinue }
            Save-PIDTracking
            return $true
        } else {
            Write-Log "Failed to start worker process" -Level "ERROR"
            return $false
        }
    } catch {
        Write-Log "ERROR starting worker: $_" -Level "ERROR"
        Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
        return $false
    }
}

function Stop-WorkerProcess {
    Write-Log "Stopping worker process..." -Level "INFO"
    $stoppedProcesses = @()
    $processesToStop = @()
    
    # ---- Python process ----
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        try {
            $pythonProcess = Get-Process -Id $global:PythonPID -ErrorAction SilentlyContinue
            if ($pythonProcess -and (-not $pythonProcess.HasExited)) {
                $processesToStop += @{ Type = "Python"; PID = $global:PythonPID; Process = $pythonProcess }
            } else {
                Write-Log "Python process already exited (PID: $global:PythonPID)" -Level "DEBUG"
            }
        } catch { 
            Write-Log "Python process not found (PID: $global:PythonPID) - $_" -Level "DEBUG"
        }
    }
    
    # ---- Worker process ----
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        try {
            $workerProcess = Get-Process -Id $global:WorkerPID -ErrorAction SilentlyContinue
            if ($workerProcess -and (-not $workerProcess.HasExited)) {
                $processesToStop += @{ Type = "Worker"; PID = $global:WorkerPID; Process = $workerProcess }
            } else {
                Write-Log "Worker process already exited (PID: $global:WorkerPID)" -Level "DEBUG"
            }
        } catch { 
            Write-Log "Worker process not found (PID: $global:WorkerPID) - $_" -Level "DEBUG"
        }
    }
    
    # Stop Python first
    foreach ($procInfo in $processesToStop | Where-Object { $_.Type -eq "Python" }) {
        Write-Log "Stopping $($procInfo.Type) process (PID: $($procInfo.PID))..." -Level "INFO"
        try {
            $procInfo.Process.Kill()
            Write-Log "Waiting for Python process to exit..." -Level "INFO"
            $timeout = 10  # seconds
            $startTime = Get-Date
            while ((-not $procInfo.Process.HasExited) -and ((Get-Date) - $startTime).TotalSeconds -lt $timeout) {
                Start-Sleep -Milliseconds 100
            }
            if ($procInfo.Process.HasExited) {
                $stoppedProcesses += $procInfo.Type
                Write-Log "$($procInfo.Type) process stopped successfully" -Level "SUCCESS"
            } else {
                Write-Log "$($procInfo.Type) process did not stop within timeout" -Level "WARN"
            }
        } catch { 
            Write-Log "Error stopping $($procInfo.Type) process: $_" -Level "ERROR" 
        }
    }
    
    # Stop Worker second
    foreach ($procInfo in $processesToStop | Where-Object { $_.Type -eq "Worker" }) {
        Write-Log "Stopping $($procInfo.Type) process (PID: $($procInfo.PID))..." -Level "INFO"
        try {
            if ($procInfo.Process.CloseMainWindow()) {
                $timeout = 5
                $startTime = Get-Date
                while ((-not $procInfo.Process.HasExited) -and ((Get-Date) - $startTime).TotalSeconds -lt $timeout) {
                    Start-Sleep -Milliseconds 100
                }
            }
            if (-not $procInfo.Process.HasExited) {
                $procInfo.Process.Kill()
                Start-Sleep -Seconds 2
            }
            if ($procInfo.Process.HasExited) {
                $stoppedProcesses += $procInfo.Type
                Write-Log "$($procInfo.Type) process stopped successfully" -Level "SUCCESS"
            }
        } catch { 
            Write-Log "Error stopping $($procInfo.Type) process: $_" -Level "ERROR" 
        }
    }
    
    # Orphaned process check (only if still running after above)
    Write-Log "Checking for known orphaned processes..." -Level "INFO"
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        try {
            $proc = Get-Process -Id $global:PythonPID -ErrorAction SilentlyContinue
            if ($proc -and (-not $proc.HasExited)) {
                Write-Log "Found orphaned Python process (PID: $global:PythonPID) - terminating" -Level "WARN"
                $proc.Kill()
                Start-Sleep -Seconds 1
            }
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
    if (Test-Path $commPaths.CommunicationDir) {
        Remove-Item -Path $commPaths.CommunicationDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Log "Cleaned up communication directory" -Level "DEBUG"
    }
    
    if ($stoppedProcesses.Count -gt 0) {
        Write-Log "Successfully stopped processes: $($stoppedProcesses -join ', ')" -Level "INFO"
    }
    Write-Log "Worker process cleanup completed" -Level "INFO"
}

function Find-LatestRunFolder {
    try {
        if (-not (Test-Path $paths.DateBasedPath)) { return $null }
        $folders = Get-ChildItem -Path $paths.DateBasedPath -Directory -Filter $centralConfig.WorkerRunFolderPrefix -ErrorAction SilentlyContinue
        if (-not $folders) { return $null }
        return $folders | Sort-Object CreationTime -Descending | Select-Object -First 1
    } catch { Write-Log "Error finding run folders: $_" -Level "ERROR"; return $null }
}

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
            Write-Log "PID tracking saved" -Level "DEBUG"
        }
    } catch { Write-Log "Failed to save PID tracking: $_" -Level "ERROR" }
}

# ====================================================================
# VALIDATION – using shared functions from common-paths
# ====================================================================
function Validate-Output {
    param(
        [int]$RetryCount = 0,
        [switch]$CollectAll = $false,
        [DateTime]$CollectionStart = $null,
        [DateTime]$CollectionEnd = $null
    )
    if ($CollectAll) {
        # Use shared collection function
        $start = if ($CollectionStart) { $CollectionStart } else {
            [DateTime]::ParseExact((Get-Date -Format "yyyy-MM-dd") + " " + $centralConfig.EveryStartTime, "yyyy-MM-dd HH:mm", $null)
        }
        $end = if ($CollectionEnd) { $CollectionEnd } else {
            [DateTime]::ParseExact((Get-Date -Format "yyyy-MM-dd") + " " + $centralConfig.EveryEndTime, "yyyy-MM-dd HH:mm", $null)
        }
        $collected = Collect-RunsFromTimeWindow -BasePath $paths.DateBasedPath -WindowStart $start -WindowEnd $end -ValidateEach
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
        $folder = Get-LatestRunFolder   # uses local function above
        if (-not $folder) {
            if ($RetryCount -lt $centralConfig.MaxValidationRetries) {
                Start-Sleep -Seconds $centralConfig.RetryDelaySeconds
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
# EMAIL REPORTING
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
            } else {
                Write-Log "Failed to register stable email sender" -Level "ERROR"
                return $false
            }
        } catch {
            Write-Log "Failed to initialize email reporting: $_" -Level "ERROR"
            Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
            return $false
        }
    } else {
        Write-Log "Email sender script not found: $emailSenderScript" -Level "WARN"
        return $false
    }
}

function Invoke-EmailReport {
    [CmdletBinding()]
    param([switch]$Force = $false)
    Write-Log "Scheduled email report triggered..." -Level "INFO"
    Write-Log "Email configuration:" -Level "DEBUG"
    Write-Log "  Start time: $($Script:Config.StartTime)" -Level "DEBUG"
    Write-Log "  End time: $($Script:Config.EndTime)" -Level "DEBUG"
    Write-Log "  Runs base path: $($Script:Config.RunsBasePath)" -Level "DEBUG"
    try {
        if (-not (Get-Command -Name "Invoke-StableEmailReport" -ErrorAction SilentlyContinue)) {
            $emailTestScript = $Script:Config.EmailSenders
            if (Test-Path $emailTestScript) {
                . $emailTestScript
                Write-Log "Email sender script reloaded" -Level "INFO"
            } else {
                Write-Log "ERROR: Email sender script not found at: $emailTestScript" -Level "ERROR"
                return $false
            }
        }
        if (-not $global:StableEmailSender -or -not $global:StableEmailSender.Enabled) {
            Write-Log "Stable email sender not registered or disabled, attempting to initialize..." -Level "WARN"
            $reinitialized = Initialize-EmailReporting
            if (-not $reinitialized) {
                Write-Log "Failed to re-initialize email reporting" -Level "ERROR"
                return $false
            }
        }
        Write-Log "Sending email report for schedule starting at: $($Script:Config.StartTime)" -Level "INFO"
        $success = Invoke-StableEmailReport -Force:$Force
        if ($success) {
            Write-Log "Email report sent successfully!" -Level "SUCCESS"
        } else {
            Write-Log "Failed to send email report" -Level "ERROR"
        }
        return $success
    } catch {
        Write-Log "Error in email report: $_" -Level "ERROR"
        Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
        return $false
    }
}

# ====================================================================
# MAIN EXECUTION
# ====================================================================
try {
    if ($paths.LogFile) { $null = New-Item -ItemType Directory -Path (Split-Path $paths.LogFile -Parent) -Force }
    Write-MonitorMetadata   # initial
    Write-Log "=== Enhanced Face Recognition Monitor Started ===" -Level "INFO"
    Write-Log "Version: 2.2 (refactored, shared validation)" -Level "INFO"
    Write-Log "Start Time: $($centralConfig.EveryStartTime)" -Level "INFO"
    Write-Log "End Time: $($centralConfig.EveryEndTime)" -Level "INFO"
    
    if (-not (Test-Path $paths.DateBasedPath)) { New-Item -ItemType Directory -Path $paths.DateBasedPath -Force | Out-Null }
    
    $emailReportingInitialized = Initialize-EmailReporting
    
    $today = Get-Date -Format "yyyy-MM-dd"
    $startDateTime = [DateTime]::ParseExact("$today $($centralConfig.EveryStartTime)", "yyyy-MM-dd HH:mm", $null)
    $endDateTime   = [DateTime]::ParseExact("$today $($centralConfig.EveryEndTime)",   "yyyy-MM-dd HH:mm", $null)
    
    if ((Get-Date) -gt $endDateTime) {
        Write-Log "Current time is past end time. Starting immediate shutdown and validation." -Level "WARN"
        $monitoringActive = $false
        $global:LastValidation = Validate-Output -CollectAll -CollectionStart $startDateTime -CollectionEnd $endDateTime
    } else {
        $monitoringActive = $true
        Write-Log "Monitoring window: $($startDateTime.ToString('HH:mm:ss')) to $($endDateTime.ToString('HH:mm:ss'))" -Level "INFO"
    }
    
    while ($monitoringActive) {
        try {
            $processStatus = Check-ProcessStatus
            $startPassed = Test-TimeWindow -TargetTime $centralConfig.EveryStartTime
            $endPassed   = Test-TimeWindow -TargetTime $centralConfig.EveryEndTime
            $inWindow = $startPassed -and (-not $endPassed)
            
            if ((Get-Date).Second % 10 -eq 0) {
                Write-Host "================================================" -ForegroundColor Cyan
                Write-Host "    FACE RECOGNITION MONITOR" -ForegroundColor Cyan
                Write-Host "================================================" -ForegroundColor Cyan
                Write-Host "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | Schedule: $($Script:Config.StartTime)-$($Script:Config.EndTime)" -ForegroundColor Yellow
                Write-Host "Status: $(if ($inWindow) {'ACTIVE'} else {'WAITING'})" -ForegroundColor $(if ($inWindow) {'Green'} else {'Yellow'})
                Write-Host "Python: $(if ($processStatus.PythonRunning) {'RUNNING'} else {'STOPPED'})" -ForegroundColor $(if ($processStatus.PythonRunning) {'Green'} else {'Red'})
                Write-Host "Worker: $(if ($processStatus.WorkerRunning) {'RUNNING'} else {'STOPPED'})" -ForegroundColor $(if ($processStatus.WorkerRunning) {'Green'} else {'Red'})
                Write-Host "================================================" -ForegroundColor Cyan
            }
            
            if ($inWindow -and (-not $processStatus.PythonRunning)) {
                if (-not $global:LastWorkerAttempt -or ((Get-Date) - $global:LastWorkerAttempt).TotalSeconds -ge 60) {
                    $started = Start-WorkerProcess
                    $global:LastWorkerAttempt = Get-Date
                    if ($started) { Write-Log "Worker started." -Level "SUCCESS" }
                }
            }
            elseif ($endPassed) {
                Write-Log "End time reached – shutting down." -Level "SHUTDOWN"
                if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
                    Stop-WorkerProcess
                    Start-Sleep -Seconds 10
                }
                $global:LastValidation = Validate-Output -CollectAll -CollectionStart $startDateTime -CollectionEnd $endDateTime
                if ($emailReportingInitialized) {
                    Invoke-EmailReport -Force
                }
                $monitoringActive = $false
                break
            }
            Start-Sleep -Seconds $Script:Config.ProcessCheckInterval
        } catch {
            Write-Log "Error in main loop: $_" -Level "ERROR"
            Write-Log $_.ScriptStackTrace -Level "DEBUG"
            Start-Sleep -Seconds 15
        }
    }
} catch {
    Write-Log "FATAL ERROR: $_" -Level "ERROR"
    $global:MonitorExitCode = 1
} finally {
    Write-Log "Cleaning up..." -Level "INFO"
    Stop-WorkerProcess
    Release-SingletonLock -LockFile $global:MonitorLockFile
    Write-MonitorMetadata -Final
    Write-Log "=== Monitor Stopped ===" -Level "INFO"
}

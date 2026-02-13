# 1_monitor.ps1 

<#
.SYNOPSIS
Enhanced time-based process monitor for Face Recognition pipeline with PID tracking.
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
$Script:Config = @{
    StartTime        = $centralConfig.EveryStartTime
    EndTime          = $centralConfig.EveryEndTime
    WorkerScript     = $paths.WorkerScript
    PythonScript     = $paths.PythonScriptPath
    RunsBasePath     = $paths.DateBasedPath
    PIDFilePath      = $paths.PIDFilePath
    LogFile          = $paths.LogFile
    EmailSenders     = $paths.EmailSendScript
    ProcessCheckInterval = $centralConfig.MonitorProcessCheckInterval
    MaxPIDFileAgeMinutes = $centralConfig.MonitorMaxPIDFileAgeMinutes
    ExpectedSubfolders   = $centralConfig.ExpectedSubfolders
    ExpectedFiles        = $centralConfig.ExpectedFiles
    MaxValidationRetries = $centralConfig.MaxValidationRetries
    RetryDelaySeconds    = $centralConfig.RetryDelaySeconds
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
# CRITICAL UPDATE: Process Management Functions from OLD VERSION
# ====================================================================

function Check-ProcessStatus {
    $status = @{
        WorkerRunning = $false
        PythonRunning = $false
        WorkerPID = $global:WorkerPID
        PythonPID = $global:PythonPID
    }
    
    # Check worker process (we need to know this)
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        $status.WorkerRunning = Is-ProcessRunning -ProcessId $global:WorkerPID -ProcessName "powershell"
    }
    
    # Check Python process - ONLY if we already have the PID from worker output
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        $status.PythonRunning = Is-ProcessRunning -ProcessId $global:PythonPID -ProcessName "python"
    }
    # Note: We do NOT try to find the Python process if we don't have the PID
    # This prevents capturing the wrong process
    
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
    # Simplified: Only try to get PID from metadata if we don't have it yet
    Write-Log "Looking for Python PID from available data..." -Level "DEBUG"
    
    # Method 1: Already have it from worker output?
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        Write-Log "Using Python PID from worker output: $global:PythonPID" -Level "DEBUG"
        return $global:PythonPID
    }
    
    # Method 2: Look in the latest run folder's metadata for PID
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
# Modified Start-WorkerProcess with communication
# ====================================================================


function Start-WorkerProcess {
    Write-Log "Starting face recognition worker..." -Level "INFO"
    
    try {
        Write-Log "Worker script path: $($Script:Config.WorkerScript)" -Level "INFO"
        
        # Verify worker script exists - FIX: Better error handling
        if ([string]::IsNullOrEmpty($Script:Config.WorkerScript)) {
            Write-Log "ERROR: Worker script path is null or empty" -Level "ERROR"
            return $false
        }
        
        if (-not (Test-Path $Script:Config.WorkerScript)) {
            Write-Log "ERROR: Worker script not found at: $($Script:Config.WorkerScript)" -Level "ERROR"
            return $false
        }
        
        # Start worker process with explicit output capture
        Write-Log "Starting worker process..." -Level "INFO"
        
        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processInfo.FileName = "powershell.exe"
        
        # FIXED: Properly formatted arguments array
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
        
        # Create output collectors
        $stdOutBuilder = New-Object System.Text.StringBuilder
        $stdErrBuilder = New-Object System.Text.StringBuilder
        
        # better PID parsing:

        $outAction = {
            if (-not [String]::IsNullOrEmpty($EventArgs.Data)) {
                $Event.MessageData.AppendLine($EventArgs.Data)
                
                # Parse for Python PID from worker output
                if ($EventArgs.Data -match "Python process started \(PID: (\d+)\)") {
                    $global:PythonPID = $matches[1]
                    Write-Log "Captured Python PID from worker output: $global:PythonPID" -Level "SUCCESS"
                }
                
                # Also log to monitor log
                Write-Log "Worker Output: $($EventArgs.Data)" -Level "DEBUG"
            }
        }
        
        $errAction = {
            if (-not [String]::IsNullOrEmpty($EventArgs.Data)) {
                $Event.MessageData.AppendLine($EventArgs.Data)
                # Also log to monitor log
                Write-Log "Worker Error: $($EventArgs.Data)" -Level "ERROR"
            }
        }
        
        # Register events
        $stdOutEvent = Register-ObjectEvent -InputObject $WorkerProcess `
            -EventName 'OutputDataReceived' `
            -Action $outAction `
            -MessageData $stdOutBuilder
        
        $stdErrEvent = Register-ObjectEvent -InputObject $WorkerProcess `
            -EventName 'ErrorDataReceived' `
            -Action $errAction `
            -MessageData $stdErrBuilder
        
        # Start the process
        if ($WorkerProcess.Start()) {
            $global:WorkerPID = $WorkerProcess.Id
            $global:WorkerStartTime = Get-Date
            $global:WorkerIsRunning = $true
            
            Write-Log "Worker process started (PID: $global:WorkerPID)" -Level "SUCCESS"
            
            # Begin async output reading
            $WorkerProcess.BeginOutputReadLine()
            $WorkerProcess.BeginErrorReadLine()
            
            # Wait a moment for initial output
            Start-Sleep -Seconds 2
            
            # Check if process is still running
            if ($WorkerProcess.HasExited) {
                $exitCode = $WorkerProcess.ExitCode
                $output = $stdOutBuilder.ToString()
                $errorOutput = $stdErrBuilder.ToString()
                
                Write-Log "Worker process exited immediately with code: $exitCode" -Level "ERROR"
                
                if ($output) {
                    Write-Log "Worker output:" -Level "DEBUG"
                    foreach ($line in $output -split "`n") {
                        if ($line.Trim()) {
                            Write-Log "  $line" -Level "DEBUG"
                        }
                    }
                }
                
                if ($errorOutput) {
                    Write-Log "Worker error output:" -Level "ERROR"
                    foreach ($line in $errorOutput -split "`n") {
                        if ($line.Trim()) {
                            Write-Log "  $line" -Level "ERROR"
                        }
                    }
                }
                
                # Clean up events
                if ($stdOutEvent) {
                    Unregister-Event -SourceIdentifier $stdOutEvent.Name -ErrorAction SilentlyContinue
                }
                if ($stdErrEvent) {
                    Unregister-Event -SourceIdentifier $stdErrEvent.Name -ErrorAction SilentlyContinue
                }
                
                return $false
            }
            
            Write-Log "Worker process is running, waiting for Python..." -Level "INFO"
            
            # Look for Python process
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
                    
                    # Clean up events
                    if ($stdOutEvent) {
                        Unregister-Event -SourceIdentifier $stdOutEvent.Name -ErrorAction SilentlyContinue
                    }
                    if ($stdErrEvent) {
                        Unregister-Event -SourceIdentifier $stdErrEvent.Name -ErrorAction SilentlyContinue
                    }
                    
                    return $true
                }
                
                Start-Sleep -Seconds 5
                $waited += 5
                
                # Check if worker is still running
                if ($WorkerProcess.HasExited) {
                    Write-Log "Worker process exited while waiting for Python" -Level "ERROR"
                    break
                }
            }
            
            Write-Log "Python process not found within $maxWait seconds" -Level "WARN"
            
            # Clean up events
            if ($stdOutEvent) {
                Unregister-Event -SourceIdentifier $stdOutEvent.Name -ErrorAction SilentlyContinue
            }
            if ($stdErrEvent) {
                Unregister-Event -SourceIdentifier $stdErrEvent.Name -ErrorAction SilentlyContinue
            }
            
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

    # Collect all processes to stop
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        try {
            $pythonProcess = Get-Process -Id $global:PythonPID -ErrorAction SilentlyContinue
            if ($pythonProcess -and (-not $pythonProcess.HasExited)) {
                $processesToStop += @{
                    Type = "Python"
                    PID = $global:PythonPID
                    Process = $pythonProcess
                }
            }
        } catch {
            Write-Log "Python process not found (PID: $global:PythonPID) - $_" -Level "DEBUG"
        }
    }

    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        try {
            $workerProcess = Get-Process -Id $global:WorkerPID -ErrorAction SilentlyContinue
            if ($workerProcess -and (-not $workerProcess.HasExited)) {
                $processesToStop += @{
                    Type = "Worker"
                    PID = $global:WorkerPID
                    Process = $workerProcess
                }
            }
        } catch {
            Write-Log "Worker process not found (PID: $global:WorkerPID) - $_" -Level "DEBUG"
        }
    }

    # Stop processes in reverse order (Python first, then Worker)
    foreach ($procInfo in $processesToStop | Where-Object { $_.Type -eq "Python" }) {
        Write-Log "Stopping $($procInfo.Type) process (PID: $($procInfo.PID))..." -Level "INFO"
        
        # Change from immediate kill to graceful wait
        try {
            # For Python processes, use Kill() directly as they don't respond well to CloseMainWindow
            $procInfo.Process.Kill()
            
            # Add waiting time for Python to stop completely
            Write-Log "Waiting 10 seconds for Python process to stop completely..." -Level "WARN"
            Start-Sleep -Seconds 10
            
            # Wait for process to exit
            $timeout = 10 # seconds
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

    # Now stop Worker processes
    foreach ($procInfo in $processesToStop | Where-Object { $_.Type -eq "Worker" }) {
        Write-Log "Stopping $($procInfo.Type) process (PID: $($procInfo.PID))..." -Level "INFO"
        
        try {
            # Try to close gracefully first
            if ($procInfo.Process.CloseMainWindow()) {
                $timeout = 5 # seconds
                $startTime = Get-Date
                while ((-not $procInfo.Process.HasExited) -and ((Get-Date) - $startTime).TotalSeconds -lt $timeout) {
                    Start-Sleep -Milliseconds 100
                }
            }
            
            # Force kill if still running
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

    # Inside Stop-WorkerProcess function, update the orphaned process section:

    # Additional cleanup: ONLY terminate processes we know about
    Write-Log "Checking for known orphaned processes..." -Level "INFO"
    $orphanedProcesses = @()

    # Only kill processes that we specifically know about
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        try {
            $proc = Get-Process -Id $global:PythonPID -ErrorAction SilentlyContinue
            if ($proc -and (-not $proc.HasExited)) {
                Write-Log "Found orphaned Python process (PID: $global:PythonPID) - terminating" -Level "WARN"
                $proc.Kill()
                $orphanedProcesses += "Python:$global:PythonPID"
                Start-Sleep -Seconds 1
            }
        } catch { }
    }

    # Reset global process variables
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false
    $global:WorkerStartTime = $null
    $global:PythonStartTime = $null

    # Clean up communication directory
    $commPaths = Initialize-CommunicationPaths -Paths $global:MonitorPaths -IsMonitor
    if (Test-Path $commPaths.CommunicationDir) {
        Remove-Item -Path $commPaths.CommunicationDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Log "Cleaned up communication directory" -Level "DEBUG"
    }

    # Summary
    if ($stoppedProcesses.Count -gt 0) {
        Write-Log "Successfully stopped processes: $($stoppedProcesses -join ', ')" -Level "INFO"
    }
    
    if ($orphanedProcesses.Count -gt 0) {
        Write-Log "Cleaned up orphaned processes: $($orphanedProcesses.Count)" -Level "INFO"
    }

    Write-Log "Worker process cleanup completed" -Level "INFO"
}




# ====================================================================
# Email Reporting Integration
# ====================================================================
function Initialize-EmailReporting {
    Write-Log "Initializing email reporting..." -Level "INFO"
    
    # Load email sender script
    $emailSenderScript = $Script:Config.EmailSenders
    if (Test-Path $emailSenderScript) {
        try {
            # Clear any existing functions to avoid conflicts
            Remove-Item "function:Invoke-StableEmailReport" -ErrorAction SilentlyContinue
            Remove-Item "function:Register-StableEmailSender" -ErrorAction SilentlyContinue
            Remove-Item "function:Send-RunReport" -ErrorAction SilentlyContinue
            
            # Dot-source the script to load functions into current scope
            . $emailSenderScript
            
            # Verify the function exists after loading
            if (-not (Get-Command -Name "Invoke-StableEmailReport" -ErrorAction SilentlyContinue)) {
                Write-Log "ERROR: Invoke-StableEmailReport function not found after loading script" -Level "ERROR"
                return $false
            }
            
            # Create email config with schedule information
            $emailConfig = @{
                ScheduleStartTime = $Script:Config.StartTime
                ScheduleEndTime = $Script:Config.EndTime
                EmailSubject = "[FaceRecog] Runs - $(Get-Date -Format 'yyyy-MM-dd') - Schedule: $($Script:Config.StartTime)-$($Script:Config.EndTime)"
            }
            
            # Initialize and register the email sender
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
        # First, ensure the function is available
        if (-not (Get-Command -Name "Invoke-StableEmailReport" -ErrorAction SilentlyContinue)) {
            Write-Log "Invoke-StableEmailReport function not available, attempting to load email sender..." -Level "WARN"
            
            # Try to re-initialize
            $emailTestScript = $Script:Config.EmailSenders
            if (Test-Path $emailTestScript) {
                . $emailTestScript
                Write-Log "Email sender script reloaded" -Level "INFO"
            } else {
                Write-Log "ERROR: Email sender script not found at: $emailTestScript" -Level "ERROR"
                return $false
            }
        }

        # Check if email sender is properly initialized
        if (-not $global:StableEmailSender -or -not $global:StableEmailSender.Enabled) {
            Write-Log "Stable email sender not registered or disabled, attempting to initialize..." -Level "WARN"
            
            $reinitialized = Initialize-EmailReporting
            if (-not $reinitialized) {
                Write-Log "Failed to re-initialize email reporting" -Level "ERROR"
                return $false
            }
        }

        Write-Log "Sending email report for schedule starting at: $($Script:Config.StartTime)" -Level "INFO"

        # Call the function - now it should be available
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


# ====================================================================
# VALIDATION – now uses shared functions, no duplicate definitions
# ====================================================================
function Validate-Output {
    param(
        [int]$RetryCount = 0,
        [switch]$CollectAll = $false,
        [DateTime]$CollectionStart = $null,
        [DateTime]$CollectionEnd = $null
    )
    if ($CollectAll) {
        $start = $CollectionStart ?? [DateTime]::ParseExact((Get-Date -Format "yyyy-MM-dd") + " " + $Script:Config.StartTime, "yyyy-MM-dd HH:mm", $null)
        $end   = $CollectionEnd   ?? [DateTime]::ParseExact((Get-Date -Format "yyyy-MM-dd") + " " + $Script:Config.EndTime,   "yyyy-MM-dd HH:mm", $null)
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


function Collect-RunsFromTimeWindow {
    param(
        [DateTime]$StartTime,
        [DateTime]$EndTime,
        [switch]$ForceValidation = $false
    )
    
    Write-Log "Collecting runs from $($StartTime.ToString('HH:mm')) to $($EndTime.ToString('HH:mm'))..." -Level "INFO"
    
    $collectionResults = @{
        TotalRuns = 0
        ValidRuns = 0
        InvalidRuns = 0
        Runs = @()
        Summary = $null
    }
    
    try {
        # FIX: Use just the time portion (HH:mm) instead of full datetime
        $startTimeStr = $StartTime.ToString("HH:mm")
        $endTimeStr = $EndTime.ToString("HH:mm")
        
        Write-Log "Time window for collection: $startTimeStr to $endTimeStr" -Level "INFO"
        
        # Check if integrated functions are available
        if (Get-Command -Name "Start-RunCollection-Integrated" -ErrorAction SilentlyContinue) {
            $collectedRuns = Start-RunCollection-Integrated -StartTime $startTimeStr -EndTime $endTimeStr
        } else {
            # Fallback to simple manual collection using TimeOfDay
            Write-Log "Integrated functions not available, using manual collection" -Level "WARN"
            $collectedRuns = @()
            
            if ($Script:Config.RunsBasePath -and (Test-Path $Script:Config.RunsBasePath)) {
                $folders = Get-ChildItem -Path $Script:Config.RunsBasePath -Directory -Filter $Script:Config.OutputFolderPattern -ErrorAction SilentlyContinue
                
                Write-Log "Found $($folders.Count) total folders to check" -Level "INFO"
                
                foreach ($folder in $folders) {
                    # Check if folder creation time is within window using TimeOfDay
                    $folderTime = $folder.CreationTime.TimeOfDay
                    $startTimeOfDay = $StartTime.TimeOfDay
                    $endTimeOfDay = $EndTime.TimeOfDay
                    
                    if ($folderTime -ge $startTimeOfDay -and $folderTime -le $endTimeOfDay) {
                        $collectedRuns += @{
                            Folder = $folder.FullName
                            Name = $folder.Name
                            CreationTime = $folder.CreationTime
                            Validation = @{ Success = $true; MissingItems = @() }
                            Status = "VALID"
                        }
                        Write-Log "✓ Manual collection added: $($folder.Name)" -Level "INFO"
                    }
                }
            }
        }
        
        if ($collectedRuns) {
            $collectionResults.TotalRuns = $collectedRuns.Count
            $collectionResults.ValidRuns = ($collectedRuns | Where-Object { $_.Status -eq "VALID" }).Count
            $collectionResults.InvalidRuns = ($collectedRuns | Where-Object { $_.Status -eq "INVALID" }).Count
            $collectionResults.Runs = $collectedRuns
            
            Write-Log "Collection completed: $($collectionResults.ValidRuns)/$($collectionResults.TotalRuns) valid runs" -Level "INFO"
            
            # Store in global variable
            $global:CollectedRunFolders = $collectedRuns
        } else {
            Write-Log "No runs collected in the specified time window" -Level "WARN"
        }
        
    } catch {
        Write-Log "Error during run collection: $_" -Level "ERROR"
        Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
    }
    
    return $collectionResults
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

function Initialize-RunCollection {
    Write-Log "Initializing run collection system..." -Level "INFO"
    
    # Instead of loading external script, integrate key functions directly
    try {
        # Define the core collection function inline
        function global:Validate-RunFolder-Integrated {
            param(
                [string]$FolderPath
            )
            
            Write-Log "Validating folder: $FolderPath" -Level "DEBUG"
            
            $result = @{
                Success = $false
                FolderPath = $FolderPath
                FolderName = Split-Path $FolderPath -Leaf
                MissingItems = @()
            }

            try {
                $folder = Get-Item -Path $FolderPath -ErrorAction Stop

                # Check subfolders
                foreach ($subfolder in $Script:Config.ExpectedSubfolders) {
                    $subfolderPath = Join-Path $FolderPath $subfolder
                    if (-not (Test-Path $subfolderPath)) {
                        $result.MissingItems += $subfolder
                    }
                }

                # Check files
                foreach ($file in $Script:Config.ExpectedFiles) {
                    $filePath = Join-Path $FolderPath $file
                    if (-not (Test-Path $filePath)) {
                        $result.MissingItems += $file
                    }
                }

                $result.Success = ($result.MissingItems.Count -eq 0)
                return $result
            } catch {
                Write-Log "Error validating folder: $_" -Level "ERROR"
                return $result
            }
        }
        
        # Define simple collection function
        function global:Start-RunCollection-Integrated {
            param(
                [string]$StartTime,
                [string]$EndTime
            )
            
            $collectedRuns = @()
            
            try {
                # Debug: Log what we're receiving
                Write-Log "Integrated collection called with StartTime: '$StartTime', EndTime: '$EndTime'" -Level "DEBUG"
                
                # Check if runs path exists
                if (-not $Script:Config.RunsBasePath -or -not (Test-Path $Script:Config.RunsBasePath)) {
                    Write-Log "Runs base path not found: $($Script:Config.RunsBasePath)" -Level "WARN"
                    return $collectedRuns
                }
                
                # Get all run folders
                $global:TotalRunFolders = Get-ChildItem -Path $Script:Config.RunsBasePath -Directory -Filter $Script:Config.OutputFolderPattern -ErrorAction SilentlyContinue
                
                Write-Log "Found $($global:TotalRunFolders.Count) total run folders" -Level "INFO"
                
                if ($global:TotalRunFolders) {
                    # Parse time window - FIX: Check what format we're getting
                    $windowStart = $null
                    $windowEnd = $null
                    
                    try {
                        # Try to parse as full datetime first
                        if ($StartTime -match '^\d{4}-\d{2}-\d{2}') {
                            $windowStart = [DateTime]::ParseExact($StartTime, "yyyy-MM-dd HH:mm:ss", $null)
                            $windowEnd = [DateTime]::ParseExact($EndTime, "yyyy-MM-dd HH:mm:ss", $null)
                        } else {
                            # Parse as time only (HH:mm)
                            $today = Get-Date -Format "yyyy-MM-dd"
                            $windowStart = [DateTime]::ParseExact("$today $StartTime", "yyyy-MM-dd HH:mm", $null)
                            $windowEnd = [DateTime]::ParseExact("$today $EndTime", "yyyy-MM-dd HH:mm", $null)
                        }
                    } catch {
                        Write-Log "Error parsing time window: $_" -Level "ERROR"
                        Write-Log "StartTime was: '$StartTime', EndTime was: '$EndTime'" -Level "DEBUG"
                        return $collectedRuns
                    }
                    
                    Write-Log "Time window parsed: $($windowStart.ToString('yyyy-MM-dd HH:mm:ss')) to $($windowEnd.ToString('yyyy-MM-dd HH:mm:ss'))" -Level "INFO"
                    
                    foreach ($runFolder in $global:TotalRunFolders) {
                        # Check if folder is within time window
                        $folderTime = $runFolder.CreationTime
                        
                        if ($folderTime -ge $windowStart -and $folderTime -le $windowEnd) {
                            $validation = Validate-RunFolder-Integrated -FolderPath $runFolder.FullName

                            $collectedRuns += @{
                                Folder = $runFolder.FullName
                                Name = $runFolder.Name
                                CreationTime = $runFolder.CreationTime
                                Validation = $validation
                                Status = if ($validation.Success) { "VALID" } else { "INVALID" }
                            }

                            Write-Log "✓ Collected: $($runFolder.Name)" -Level "INFO"
                        }
                    }
                }
            } catch {
                Write-Log "Error in integrated collection: $_" -Level "ERROR"
                Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
            }
            
            Write-Log "Collection complete. Found $($collectedRuns.Count) runs within time window." -Level "INFO"
            return $collectedRuns
        }
        
        Write-Log "Integrated run collection functions initialized" -Level "SUCCESS"
        return $true
        
    } catch {
        Write-Log "Failed to initialize integrated run collection: $_" -Level "ERROR"
        return $false
    }
}

 
# ====================================================================
# MAIN EXECUTION – streamlined
# ====================================================================
try {
    # Create log directory
    if ($Script:Config.LogFile) {
        $null = New-Item -ItemType Directory -Path (Split-Path $Script:Config.LogFile -Parent) -Force
    }

    Write-Log "=== Enhanced Face Recognition Monitor Started ===" -Level "INFO"
    Write-Log "Version: 2.1 (Cleaned structure)" -Level "INFO"
    Write-Log "Start Time: $($Script:Config.StartTime)" -Level "INFO"
    Write-Log "End Time: $($Script:Config.EndTime)" -Level "INFO"

    # Ensure runs base path exists
    if (-not (Test-Path $Script:Config.RunsBasePath)) {
        New-Item -ItemType Directory -Path $Script:Config.RunsBasePath -Force | Out-Null
    }

    # Initialise email and run‑collection (no duplicate function definitions)
    $emailReportingInitialized = Initialize-EmailReporting
    # No need to call Initialize-RunCollection – functions now in common module

    # Determine if we are already past end time
    $today = Get-Date -Format "yyyy-MM-dd"
    $startDateTime = [DateTime]::ParseExact("$today $($Script:Config.StartTime)", "yyyy-MM-dd HH:mm", $null)
    $endDateTime   = [DateTime]::ParseExact("$today $($Script:Config.EndTime)",   "yyyy-MM-dd HH:mm", $null)

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
            $startPassed = Test-TimeWindow -TargetTime $Script:Config.StartTime
            $endPassed   = Test-TimeWindow -TargetTime $Script:Config.EndTime
            $inWindow = $startPassed -and (-not $endPassed)

            # Status banner every 10 seconds
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

            # Start worker if needed
            if ($inWindow -and (-not $processStatus.PythonRunning)) {
                if (-not $global:LastWorkerAttempt -or ((Get-Date) - $global:LastWorkerAttempt).TotalSeconds -ge 60) {
                    $started = Start-WorkerProcess
                    $global:LastWorkerAttempt = Get-Date
                    if ($started) { Write-Log "Worker started." -Level "SUCCESS" }
                }
            }

            # End time reached
            elseif ($endPassed) {
                Write-Log "End time reached – shutting down." -Level "SHUTDOWN"
                if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
                    Stop-WorkerProcess
                    Start-Sleep -Seconds 10   # allow graceful exit
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

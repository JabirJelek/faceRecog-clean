#### Important

- Maintain the query requirement.
- Check explanation in every ####
- DO NOT INTRODUCES unused solution that does not relate to the query.
- Focus on what is being queried in the instructions, only take note other non-related with instructions unless user asks for it.
- Small and effective changes

#### Instructions

the hardcoded path of each file call in the file is scattered. Extract the hardcoded value and provide ease of modifiable value of portabilities in the early line of code

#### expected Output of the codebase

Ease of modifiable value for file location path.

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

# Test module load into monitor

if (Test-Path $commonPathsScript) {
try {
. $commonPathsScript
Write-Host "✓ Common paths module loaded" -ForegroundColor Green
} catch {
Write-Host "ERROR: Failed to load common paths: $\_" -ForegroundColor Red
exit 1
}
} else {
Write-Host "ERROR: Common paths script not found at: $commonPathsScript" -ForegroundColor Red
exit 1
}

# ====================================================================

# ENHANCED: Initialize paths for monitor with fallbacks

# ====================================================================

Write-Host "Initializing enhanced monitor..." -ForegroundColor Cyan

# Use the common paths function with monitor configuration

try {
$paths = Initialize-ProjectPortablePaths -IsMonitor
    $global:MonitorPaths = $paths
} catch {
    Write-Host "WARNING: Paths initialization failed, using fallbacks: $_" -ForegroundColor Yellow
    # Create fallback paths
    $projectRoot = $PSScriptRoot
    $paths = @{
        ProjectRoot = $projectRoot
        WorkerScript = Join-Path $projectRoot "worker.ps1"
        PythonScript = Join-Path $projectRoot "python_script.py"
        DateBasedPath = Join-Path $projectRoot "runs" $(Get-Date -Format 'yyyy-MM-dd')
        PIDFilePath = Join-Path $projectRoot "pid_tracking.json"
        LogFile = Join-Path $projectRoot "logs" "monitor_Magick_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
}
$global:MonitorPaths = $paths
}

# Update configuration with paths

$Script:Config = @{ # Schedule configuration
StartTime = "13:12"
EndTime = "14:58"

    # Process tracking - USING OLD VERSION'S STRUCTURE
    PythonProcessName = "python"
    WorkerProcessName = "powershell"

    # Worker script path - FIX: Ensure not null
    WorkerScript = if ($paths.WorkerScript) { $paths.WorkerScript } else {
        Join-Path $paths.ProjectRoot "scripts" "worker.ps1"
    }
    PythonScript = $paths.PythonScript

    # Paths for validation
    RunsBasePath = if ($paths.DateBasedPath) { $paths.DateBasedPath } else {
        Join-Path $paths.ProjectRoot "runs" $(Get-Date -Format 'yyyy-MM-dd')
    }
    OutputFolderPattern = "Magick_Process_MaskDetect_*"

    # Expected folder structure
    ExpectedSubfolders = @("logs", "script_output")
    ExpectedFiles = @("metadata.json")

    # Validation settings
    MaxValidationRetries = 5
    RetryDelaySeconds = 10

    # Process monitoring
    ProcessCheckInterval = if ($paths.ProcessCheckInterval) { $paths.ProcessCheckInterval } else { 15 }

    # PID tracking - FIX: Ensure not null
    PIDFilePath = if ($paths.PIDFilePath) { $paths.PIDFilePath } else {
        Join-Path $paths.ProjectRoot "pid_tracking.json"
    }
    MaxPIDFileAgeMinutes = 120

    # Logging - FIXED: Ensure LogFile path is properly set
    LogFile = if ($paths.LogFile) { $paths.LogFile } else {
        Join-Path $paths.ProjectRoot "logs" "monitor_Magick_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
    }
    CurrentDate = if ($paths.CurrentDate) { $paths.CurrentDate } else { Get-Date -Format "yyyy-MM-dd" }
    ActiveDatePath = if ($paths.DateBasedPath) { $paths.DateBasedPath } else {
        Join-Path $paths.ProjectRoot "runs" $(Get-Date -Format 'yyyy-MM-dd')
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
$global:TotalRunFolders = $null
$global:CollectedRunFolders = @()

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

    # Check worker process
    if ($global:WorkerPID -and $global:WorkerPID -ne 0) {
        $status.WorkerRunning = Is-ProcessRunning -ProcessId $global:WorkerPID -ProcessName "powershell"
    }

    # Check Python process
    if ($global:PythonPID -and $global:PythonPID -ne 0) {
        $status.PythonRunning = Is-ProcessRunning -ProcessId $global:PythonPID -ProcessName "python"
    } else {
        # If PythonPID not set but worker is running, try to find it
        if ($status.WorkerRunning) {
            $foundPID = Find-PythonProcess
            if ($foundPID) {
                $global:PythonPID = $foundPID
                $status.PythonPID = $foundPID
                $status.PythonRunning = Is-ProcessRunning -ProcessId $foundPID -ProcessName "python"
            }
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
        "SHUTDOWN" {Write-Host $logEntry -ForegroundColor Blue}
        default { Write-Host $logEntry -ForegroundColor White }
    }

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

        # Set up event handlers for async output
        $outAction = {
            if (-not [String]::IsNullOrEmpty($EventArgs.Data)) {
                $Event.MessageData.AppendLine($EventArgs.Data)
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

        try {
            # For Python processes, use Kill() directly as they don't respond well to CloseMainWindow
            $procInfo.Process.Kill()

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

    # Additional cleanup: Find and stop any orphaned Python processes
    Write-Log "Checking for orphaned Python processes..." -Level "INFO"
    $orphanedProcesses = @()

    try {
        $allPythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "*python*" -and $_.Id -ne $PID }

        foreach ($proc in $allPythonProcesses) {
            try {
                $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
                if ($cmdLine -like "*$($Script:Config.PythonScript)*") {
                    Write-Log "Found orphaned Python process (PID: $($proc.Id)) - terminating" -Level "WARN"
                    $proc.Kill()
                    $orphanedProcesses += "Python:$($proc.Id)"
                    Start-Sleep -Seconds 1
                }
            } catch { }
        }
    } catch {
        Write-Log "Error checking for orphaned processes: $_" -Level "DEBUG"
    }

    # Reset global process variables
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false
    $global:WorkerStartTime = $null
    $global:PythonStartTime = $null

    # # Remove PID tracking file
    # if (Test-Path $Script:Config.PIDFilePath) {
    #     Remove-Item -Path $Script:Config.PIDFilePath -Force -ErrorAction SilentlyContinue
    #     Write-Log "Removed PID tracking file" -Level "DEBUG"
    # }

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
    $emailSenderScript = Join-Path $PSScriptRoot "1_email-sender-stable.ps1"
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
            $emailScript = Join-Path $PSScriptRoot "1_email-sender-stable.ps1"
            if (Test-Path $emailScript) {
                . $emailScript
                Write-Log "Email sender script reloaded" -Level "INFO"
            } else {
                Write-Log "ERROR: Email sender script not found at: $emailScript" -Level "ERROR"
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

# UPDATED: Enhanced Validate-Output Function

# ====================================================================

function Validate-Output {
param(
[int]$RetryCount = 0,
        [switch]$CollectAll = $false,
        [DateTime]$CollectionStart = $null,
        [DateTime]$CollectionEnd = $null
)

    Write-Log "Validating face recognition output structure..." -Level "INFO"

    # If CollectAll is specified, use the new collection method
    if ($CollectAll) {
        Write-Log "Using enhanced collection mode for all runs in time window" -Level "INFO"

        # Determine time window
        if (-not $CollectionStart) {
            $CollectionStart = [DateTime]::ParseExact((Get-Date -Format "yyyy-MM-dd") + " " + $Script:Config.StartTime, "yyyy-MM-dd HH:mm", $null)
        }
        if (-not $CollectionEnd) {
            $CollectionEnd = [DateTime]::ParseExact((Get-Date -Format "yyyy-MM-dd") + " " + $Script:Config.EndTime, "yyyy-MM-dd HH:mm", $null)
        }

        # Collect and validate all runs
        $collectionResults = Collect-RunsFromTimeWindow -StartTime $CollectionStart -EndTime $CollectionEnd

        # Return comprehensive results
        return @{
            Success = ($collectionResults.InvalidRuns -eq 0)
            Mode = "COLLECT_ALL"
            CollectionResults = $collectionResults
            TotalRuns = $collectionResults.TotalRuns
            ValidRuns = $collectionResults.ValidRuns
            InvalidRuns = $collectionResults.InvalidRuns
            Error = if ($collectionResults.InvalidRuns -gt 0) { "$($collectionResults.InvalidRuns) invalid runs found" } else { $null }
        }
    }

    # Original single-folder validation logic (for backward compatibility)
    $runFolder = Find-LatestRunFolder

    if (-not $runFolder) {
        if ($RetryCount -lt $Script:Config.MaxValidationRetries) {
            Write-Log "No output folder found. Retrying..." -Level "WARN"
            Start-Sleep -Seconds $Script:Config.RetryDelaySeconds
            return Validate-Output -RetryCount ($RetryCount + 1)
        } else {
            Write-Log "VALIDATION FAILED: No output folder found" -Level "ERROR"
            return @{
                Success = $false
                Mode = "SINGLE"
                Error = "No output folder created"
                RunFolder = $null
            }
        }
    }

    $global:CurrentRunFolder = $runFolder.FullName

    # Use the integrated validation function if available
    $validationResult = if (Get-Command -Name "Validate-RunFolder-Integrated" -ErrorAction SilentlyContinue) {
        Validate-RunFolder-Integrated -FolderPath $runFolder.FullName
    } else {
        # Simple fallback validation
        $missing = @()
        foreach ($subfolder in $Script:Config.ExpectedSubfolders) {
            if (-not (Test-Path (Join-Path $runFolder.FullName $subfolder))) {
                $missing += $subfolder
            }
        }
        foreach ($file in $Script:Config.ExpectedFiles) {
            if (-not (Test-Path (Join-Path $runFolder.FullName $file))) {
                $missing += $file
            }
        }

        @{
            Success = ($missing.Count -eq 0)
            RunFolder = $runFolder.FullName
            FolderName = $runFolder.Name
            CreationTime = $runFolder.CreationTime
            MissingItems = $missing
            Errors = @()
        }
    }

    # Summary
    if ($validationResult.Success) {
        Write-Log "VALIDATION SUCCESS: Folder structure complete" -Level "SUCCESS"
    } else {
        Write-Log "VALIDATION FAILED" -Level "ERROR"
    }

    return @{
        Success = $validationResult.Success
        Mode = "SINGLE"
        RunFolder = $validationResult.RunFolder
        FolderName = $validationResult.FolderName
        ValidationDetails = $validationResult
        Error = if (-not $validationResult.Success) { "Validation failed" } else { $null }
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

    # Add to main try block (before the monitoring loop):
    $emailReportingInitialized = Initialize-EmailReporting

    # Add to main try block (before the monitoring loop):
    $runCollectionInitialized = Initialize-RunCollection

    # Quick test of email function availability
    $emailTestScript = Join-Path $PSScriptRoot "1_email-sender-stable.ps1"
    if (Test-Path $emailTestScript) {
        try {
            . $emailTestScript
            Write-Host "✓ Email sender functions pre-loaded" -Level "SUCCESS"
        } catch {
            Write-Host "⚠ Email sender pre-load failed (may load later): $_" -Level "WARN"
        }
    }
    # Main monitoring loop with OLD VERSION'S reliability
    Write-Log "Entering enhanced monitoring loop..." -Level "INFO"


    # Check if we're already past end time
    $now = Get-Date
    $today = Get-Date -Format "yyyy-MM-dd"
    $startDateTime = [DateTime]::ParseExact("$today $($Script:Config.StartTime)", "yyyy-MM-dd HH:mm", $null)
    $endDateTime = [DateTime]::ParseExact("$today $($Script:Config.EndTime)", "yyyy-MM-dd HH:mm", $null)

    Write-Log "Current time: $($now.ToString('yyyy-MM-dd HH:mm:ss'))" -Level "INFO"
    Write-Log "Monitor window: $($startDateTime.ToString('HH:mm')) to $($endDateTime.ToString('HH:mm'))" -Level "INFO"

    if ($now -gt $endDateTime) {
        Write-Log "Current time is past end time. Starting immediate shutdown and validation." -Level "WARN"
        $monitoringActive = $false

        # Validate runs from the window that just passed
        Write-Log "Validating runs from completed time window..." -Level "INFO"
        $global:LastValidation = Validate-Output -CollectAll -CollectionStart $startDateTime -CollectionEnd $endDateTime

        if ($global:LastValidation.TotalRuns -gt 0) {
            Write-Log "Found $($global:LastValidation.TotalRuns) runs in time window" -Level "INFO"
        }
    } else {
        $monitoringActive = $true
        Write-Log "Monitoring window: $($startDateTime.ToString('HH:mm:ss')) to $($endDateTime.ToString('HH:mm:ss'))" -Level "INFO"
    }


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

            $currentTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

            # Show status banner every 10 seconds
            $currentSecond = (Get-Date).Second
            if ($currentSecond % 10 -eq 0) {
                Write-Host "================================================" -ForegroundColor Cyan
                Write-Host "    FACE RECOGNITION MONITOR" -ForegroundColor Cyan
                Write-Host "================================================" -ForegroundColor Cyan
                Write-Host "Time: $currentTime | Schedule: $($Script:Config.StartTime)-$($Script:Config.EndTime)" -ForegroundColor Yellow
                Write-Host "Status: $(if ($inWindow) {'ACTIVE'} else {'WAITING'})" -ForegroundColor $(if ($inWindow) {'Green'} else {'Yellow'})
                Write-Host "Python: $(if ($processStatus.PythonRunning) {'RUNNING'} else {'STOPPED'})" -ForegroundColor $(if ($processStatus.PythonRunning) {'Green'} else {'Red'})
                Write-Host "Worker: $(if ($processStatus.WorkerRunning) {'RUNNING'} else {'STOPPED'})" -ForegroundColor $(if ($processStatus.WorkerRunning) {'Green'} else {'Red'})
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

            # In the main monitoring loop, update the end-time section:
            elseif ($endPassed) {
                Write-Log "End time reached - initiating shutdown sequence..." -Level "SHUTDOWN"

                if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
                    Write-Log "Stopping running processes..." -Level "INFO"
                    Stop-WorkerProcess
                    Start-Sleep -Seconds 5
                }

                # FIX: Define window variables here
                $today = Get-Date -Format "yyyy-MM-dd"
                $windowStart = [DateTime]::ParseExact("$today $($Script:Config.StartTime)", "yyyy-MM-dd HH:mm", $null)
                $windowEnd = [DateTime]::ParseExact("$today $($Script:Config.EndTime)", "yyyy-MM-dd HH:mm", $null)

                Write-Log "Time window for validation: $($windowStart.ToString('HH:mm')) to $($windowEnd.ToString('HH:mm'))" -Level "INFO"
                Write-Log "Current time: $(Get-Date -Format 'HH:mm:ss')" -Level "INFO"

                # ENHANCED: Validate ALL runs from start to end time
                Write-Log "Validating ALL runs from today's monitoring window..." -Level "INFO"
                $global:LastValidation = Validate-Output -CollectAll -CollectionStart $windowStart -CollectionEnd $windowEnd

                if ($global:LastValidation.TotalRuns -gt 0) {
                    if ($global:LastValidation.InvalidRuns -eq 0) {
                        Write-Log "All runs validation successful: $($global:LastValidation.ValidRuns)/$($global:LastValidation.TotalRuns) valid" -Level "SUCCESS"
                    } else {
                        Write-Log "Validation issues found: $($global:LastValidation.InvalidRuns) invalid runs" -Level "WARN"
                    }
                } else {
                    Write-Log "No runs found in the specified time window" -Level "INFO"
                    $global:LastValidation.Success = $true  # Treat no runs as success
                }

                # Send final email report for the day
                if ($emailReportingInitialized -or $global:StableEmailSender) {
                    Write-Log "Sending final daily email report..." -Level "INFO"

                    # Double-check the function exists
                    if (Get-Command -Name "Invoke-EmailReport" -ErrorAction SilentlyContinue) {
                        Invoke-EmailReport -Force
                    } else {
                        Write-Log "ERROR: Invoke-EmailReport function not available" -Level "ERROR"
                    }
                } else {
                    Write-Log "Email reporting not initialized, skipping final report" -Level "WARN"
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

            # FIX: Ensure ProcessCheckInterval is not null
            $sleepInterval = if ($Script:Config.ProcessCheckInterval) {
                $Script:Config.ProcessCheckInterval
            } else {
                15  # Default value
            }

            Start-Sleep -Seconds $sleepInterval

        } catch {
            Write-Log "Error in main loop: $_" -Level "ERROR"
            Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"

            # FIX: Use default sleep interval on error
            Start-Sleep -Seconds 15
        }
    }

}
catch {
Write-Log "FATAL ERROR: $_" -Level "ERROR"
    Write-Log "Stack trace: $($\_.ScriptStackTrace)" -Level "DEBUG"
}
finally {
Write-Log "Cleaning up..." -Level "INFO"

    # Stop any running processes
    Stop-WorkerProcess

    Write-Log "=== Enhanced Face Recognition Monitor Stopped ===" -Level "INFO"

    # Final console output
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "MONITOR STOPPED" -ForegroundColor Yellow
    Write-Host "================================================" -ForegroundColor Cyan

    if ($Script:Config.LogFile) {
        Write-Host "Log file: $($Script:Config.LogFile)" -ForegroundColor White
    }

    # Handle new validation format
    if ($global:LastValidation) {
        if ($global:LastValidation.Mode -eq "COLLECT_ALL") {
            Write-Host "Run validation on every created folder:" -ForegroundColor White
            Write-Host "  Total Folder Created: $($global:TotalRunFolders.Count)" -ForegroundColor White
            Write-Host "  Valid runs: $($global:LastValidation.ValidRuns)" -ForegroundColor Green
            if ($global:LastValidation.InvalidRuns -gt 0) {
                Write-Host "  Invalid runs: $($global:LastValidation.InvalidRuns)" -ForegroundColor Red
            }
        } else {
            if ($global:LastValidation.Success) {
                Write-Host "Last run validation: SUCCESS" -ForegroundColor Green
                Write-Host "  Folder: $($global:LastValidation.FolderName)" -ForegroundColor White
            } else {
                Write-Host "Last run validation: FAILED" -ForegroundColor Red
                Write-Host "  Error: $($global:LastValidation.Error)" -ForegroundColor White
            }
        }
    }

    Write-Host "Collected valid runs: $($global:CollectedRunFolders.Count)" -ForegroundColor White
    Write-Host "================================================" -ForegroundColor Cyan

}

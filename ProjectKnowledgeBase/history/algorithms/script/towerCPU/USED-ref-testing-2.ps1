# script-organized-TowerCPU-0-resilient-fixed.ps1
# ==============================================
# Resilient version with fixed monitor script generation
# ==============================================

# ========== CONFIGURATION ==========
$VENV_ROOT = "C:\raihan\dokumen\project\global-env\faceRecog\.venv"
$PYTHON_SCRIPT = "C:\raihan\dokumen\project\global-env\faceRecog\run_py\modular\entry_multi-USED-TowerCPU.py"
$POWERSHELL_SCRIPT_NAME = Split-Path -Leaf $MyInvocation.MyCommand.Path

# Python parameters
$PYTHON_PARAMS = @{
    "--multi-source" = $null
}

# Base path for all runs
$RUNS_BASE_PATH = "C:\raihan\dokumen\project\global-env\faceRecog\process-run"

# Email Configuration 
$EMAIL_CONFIG = @{
    Enabled = $false  # Set to $true after configuring and testing
    SmtpServer = "smtp.gmail.com"
    SmtpPort = 587
    UseSsl = $true
    SenderEmail = "tester@gmail.com"
    RecipientEmail = "faridraihan17@gmail.com"
    SubjectPrefix = "[FaceRecog Status]"
}

# Monitoring Configuration
$MONITORING_CONFIG = @{
    # Completion file monitoring
    CompletionFileCheck = @{
        Enabled = $true
        FileName = "metadata.json"
        CheckIntervalSeconds = 30  # Check every 30 seconds
        MaxMonitorTimeMinutes = 120  # Monitor for up to 2 hours
    }
    
    # Process monitoring
    ProcessWatchdog = @{
        Enabled = $true
        CheckIntervalSeconds = 10  # Check Python process every 10 seconds
        MaxWaitForStartSeconds = 30  # Wait up to 30 seconds for process to start
    }
    
    # Email retry configuration
    EmailRetry = @{
        MaxRetries = 3
        RetryDelaySeconds = 30
    }
}
# ===================================

# ========== GLOBAL STATE ==========
$Global:ProcessState = @{
    RunId = $null
    RunFolder = $null
    ProcessStartTime = $null
    ProcessEndTime = $null
    PythonProcessId = $null
    ExitCode = $null
    Status = "NOT_STARTED"
    CompletionFileFound = $false
    CompletionFilePath = $null
    EmailSent = $false
    LastCheckTime = $null
    CheckCount = 0
}

$Global:MonitoringActive = $true
# ===================================

# ========== CORE HELPER FUNCTIONS ==========
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

function Get-FormattedTimestamp {
    return Get-Date -Format "yyyy-MM-dd HH:mm:ss"
}

function Get-DetailedTimestamp {
    return Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
}

function Format-Duration {
    param([TimeSpan]$Duration)
    
    if ($Duration.Days -gt 0) {
        return "$($Duration.Days)d $($Duration.Hours)h $($Duration.Minutes)m $($Duration.Seconds)s"
    } elseif ($Duration.Hours -gt 0) {
        return "$($Duration.Hours)h $($Duration.Minutes)m $($Duration.Seconds)s"
    } elseif ($Duration.Minutes -gt 0) {
        return "$($Duration.Minutes)m $($Duration.Seconds)s"
    } else {
        return "$($Duration.Seconds)s"
    }
}

function Write-ProcessLog {
    param(
        [string]$Message,
        [string]$LogFile,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-DetailedTimestamp
    $logEntry = "$timestamp [$Level] $Message"
    
    # Write to log file
    if ($LogFile) {
        $logEntry | Out-File $LogFile -Append
    }
    
    # Write to console with appropriate color
    switch ($Level) {
        "ERROR" { Write-Host $logEntry -ForegroundColor Red }
        "WARN" { Write-Host $logEntry -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logEntry -ForegroundColor Green }
        "INFO" { Write-Host $logEntry -ForegroundColor Cyan }
        "DEBUG" { Write-Host $logEntry -ForegroundColor Gray }
        default { Write-Host $logEntry }
    }
}
# ===================================

# ========== SIMPLIFIED MONITORING FUNCTIONS ==========
function Start-ProcessMonitor {
    param(
        [string]$RunFolder,
        [string]$RunId,
        [hashtable]$Config
    )
    
    Write-ProcessLog "Starting simplified process monitor..." -Level "INFO"
    
    # Create a simpler monitor script without complex string interpolation
    $monitorScriptContent = @'
# Independent Process Monitor
# ===========================
param(
    [string]$RunFolder,
    [string]$RunId,
    [string]$CheckInterval,
    [string]$MaxMonitorTime,
    [string]$CompletionFileName
)

# Initialize
$startTime = Get-Date
$checkCount = 0
$completionFileFound = $false
$completionFilePath = $null
$monitorLog = Join-Path $RunFolder "monitor_$RunId.log"

"Monitor started at: $(Get-Date)" | Out-File $monitorLog
"Monitoring run folder: $RunFolder" | Out-File $monitorLog -Append
"Check interval: $CheckInterval seconds" | Out-File $monitorLog -Append
"Max monitor time: $MaxMonitorTime minutes" | Out-File $monitorLog -Append

# Convert strings to numbers
$checkIntervalSec = [int]$CheckInterval
$maxMonitorSec = [int]$MaxMonitorTime * 60
$maxChecks = [math]::Ceiling($maxMonitorSec / $checkIntervalSec)

"Max checks: $maxChecks" | Out-File $monitorLog -Append

# Main monitoring loop
while ($checkCount -lt $maxChecks) {
    $checkCount++
    $currentTime = Get-Date
    $elapsed = $currentTime - $startTime
    
    # Check for completion file
    if (-not $completionFileFound) {
        $completionFile = Join-Path $RunFolder $CompletionFileName
        $completionFileAlt = Join-Path $RunFolder "script_output" $CompletionFileName
        
        if (Test-Path $completionFile) {
            $completionFileFound = $true
            $completionFilePath = $completionFile
            "COMPLETION FILE FOUND: $completionFile at $(Get-Date)" | Out-File $monitorLog -Append
        } elseif (Test-Path $completionFileAlt) {
            $completionFileFound = $true
            $completionFilePath = $completionFileAlt
            "COMPLETION FILE FOUND: $completionFileAlt at $(Get-Date)" | Out-File $monitorLog -Append
        }
    }
    
    # Log check status
    "Check #$checkCount at $(Get-Date) - Elapsed: $($elapsed.ToString('hh\:mm\:ss'))" | Out-File $monitorLog -Append
    
    # Wait for next check
    Start-Sleep -Seconds $checkIntervalSec
}

"Monitor completed at: $(Get-Date)" | Out-File $monitorLog -Append
"Total checks: $checkCount" | Out-File $monitorLog -Append
"Completion file found: $completionFileFound" | Out-File $monitorLog -Append
'@
    
    # Save monitor script to file
    $monitorScriptPath = Join-Path $RunFolder "independent_monitor.ps1"
    $monitorScriptContent | Out-File $monitorScriptPath -Encoding UTF8
    
    Write-ProcessLog "Monitor script saved to: $monitorScriptPath" -Level "INFO"
    
    # Start monitor as a background job with proper arguments
    $checkInterval = $Config.CompletionFileCheck.CheckIntervalSeconds
    $maxMonitorTime = $Config.CompletionFileCheck.MaxMonitorTimeMinutes
    $completionFileName = $Config.CompletionFileCheck.FileName
    
    $monitorJob = Start-Job -Name "ProcessMonitor_$RunId" -ScriptBlock {
        param($ScriptPath, $RunFolder, $RunId, $Interval, $MaxTime, $FileName)
        
        # Execute the monitor script with parameters
        & $ScriptPath -RunFolder $RunFolder -RunId $RunId -CheckInterval $Interval -MaxMonitorTime $MaxTime -CompletionFileName $FileName
    } -ArgumentList $monitorScriptPath, $RunFolder, $RunId, $checkInterval, $maxMonitorTime, $completionFileName
    
    Write-ProcessLog "Monitor started as job with ID: $($monitorJob.Id)" -Level "SUCCESS"
    
    return $monitorJob
}

function Check-ForCompletionFile {
    param(
        [string]$RunFolder,
        [hashtable]$Config
    )
    
    $completionFile = Join-Path $RunFolder $Config.FileName
    $scriptOutputPath = Join-Path $RunFolder "script_output"
    $completionFileAlt = Join-Path $scriptOutputPath $Config.FileName
    
    if (Test-Path $completionFile) {
        return @{
            Found = $true
            Path = $completionFile
            Location = "root"
        }
    }
    
    if (Test-Path $completionFileAlt) {
        return @{
            Found = $true
            Path = $completionFileAlt
            Location = "script_output"
        }
    }
    
    return @{
        Found = $false
        Path = $null
        Location = $null
    }
}

function Watch-ProcessWithSleep {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$LogFile,
        [string]$OutputFile
    )
    
    try {
        # Simple process watching with sleep intervals
        $processStartTime = Get-Date
        $checkCount = 0
        
        Write-ProcessLog "Starting process watch with sleep intervals..." -Level "INFO" -LogFile $LogFile
        
        while (-not $Process.HasExited) {
            $checkCount++
            $elapsed = (Get-Date) - $processStartTime
            
            # Log process status every 10 checks (every ~30 seconds)
            if ($checkCount % 10 -eq 0) {
                Write-ProcessLog "Process still running. Elapsed: $(Format-Duration $elapsed)" -Level "INFO" -LogFile $LogFile
            }
            
            # Check if process has been running too long (optional timeout)
            if ($elapsed.TotalMinutes -gt 60) {  # 1 hour timeout
                Write-ProcessLog "Process timeout reached (1 hour). Stopping..." -Level "WARN" -LogFile $LogFile
                if (-not $Process.HasExited) {
                    $Process.Kill()
                    $Global:ProcessState.Status = "TIMEOUT"
                }
                break
            }
            
            # Sleep before next check
            Start-Sleep -Seconds 3
        }
        
        # Process has exited
        $processEndTime = Get-Date
        $duration = $processEndTime - $processStartTime
        
        if ($Process.ExitCode -ne $null) {
            $Global:ProcessState.ExitCode = $Process.ExitCode
            $Global:ProcessState.Status = if ($Process.ExitCode -eq 0) { "COMPLETED" } else { "FAILED" }
            Write-ProcessLog "Process exited with code: $($Process.ExitCode). Duration: $(Format-Duration $duration)" -Level "INFO" -LogFile $LogFile
        } else {
            $Global:ProcessState.Status = "STOPPED"
            Write-ProcessLog "Process was stopped. Duration: $(Format-Duration $duration)" -Level "WARN" -LogFile $LogFile
        }
        
        $Global:ProcessState.ProcessEndTime = $processEndTime
        
    } catch {
        Write-ProcessLog "Error in process watch: $_" -Level "ERROR" -LogFile $LogFile
        $Global:ProcessState.Status = "ERROR_IN_WATCH"
    }
}
# ===================================

# ========== EMAIL FUNCTIONS ==========
function Send-EmailReport {
    param(
        [hashtable]$Config,
        [hashtable]$ProcessState,
        [string]$Trigger = "COMPLETION"
    )
    
    if (-not $Config.Enabled) {
        Write-ProcessLog "Email notifications are disabled" -Level "WARN"
        return $false
    }
    
    Write-ProcessLog "Preparing email report (Trigger: $Trigger)..." -Level "INFO"
    
    try {
        $subject = "$($Config.SubjectPrefix) $($ProcessState.Status) - $($ProcessState.RunId)"
        
        # Calculate durations
        $processDuration = if ($ProcessState.ProcessEndTime -and $ProcessState.ProcessStartTime) {
            $ProcessState.ProcessEndTime - $ProcessState.ProcessStartTime
        } else {
            [TimeSpan]::Zero
        }
        
        $currentDuration = if ($ProcessState.ProcessStartTime) {
            (Get-Date) - $ProcessState.ProcessStartTime
        } else {
            [TimeSpan]::Zero
        }
        
        $body = @"
Face Recognition Processing Report
==================================================
Report Trigger: $Trigger
Run ID: $($ProcessState.RunId)
Report Time: $(Get-FormattedTimestamp)

PROCESS STATE
==================================================
Status: $($ProcessState.Status)
Exit Code: $(if ($ProcessState.ExitCode -ne $null) { $ProcessState.ExitCode } else { "N/A" })
Python Process ID: $(if ($ProcessState.PythonProcessId) { $ProcessState.PythonProcessId } else { "N/A" })

TIMING INFORMATION
==================================================
Process Start: $(if ($ProcessState.ProcessStartTime) { $ProcessState.ProcessStartTime.ToString('yyyy-MM-dd HH:mm:ss') } else { "N/A" })
Process End: $(if ($ProcessState.ProcessEndTime) { $ProcessState.ProcessEndTime.ToString('yyyy-MM-dd HH:mm:ss') } else { "N/A" })
Process Duration: $(Format-Duration $processDuration)
Current Duration: $(Format-Duration $currentDuration)

COMPLETION FILE STATUS
==================================================
Found: $(if ($ProcessState.CompletionFileFound) { "YES" } else { "NO" })
Path: $(if ($ProcessState.CompletionFilePath) { $ProcessState.CompletionFilePath } else { "N/A" })

LOCATION DETAILS
==================================================
Run Folder: $($ProcessState.RunFolder)

SYSTEM INFORMATION
==================================================
Host Name: $env:COMPUTERNAME
User: $env:USERNAME
Report Time: $(Get-FormattedTimestamp)

NOTES
==================================================
This is an automated report from the resilient process monitoring system.
Report trigger: $Trigger
"@
        
        # Send email using default credentials
        Send-MailMessage `
            -From $Config.SenderEmail `
            -To $Config.RecipientEmail `
            -Subject $subject `
            -Body $body `
            -SmtpServer $Config.SmtpServer `
            -Port $Config.SmtpPort `
            -UseSsl:$Config.UseSsl `
            -ErrorAction Stop
        
        Write-ProcessLog "Email report sent successfully" -Level "SUCCESS"
        return $true
        
    } catch {
        Write-ProcessLog "Failed to send email report: $_" -Level "ERROR"
        return $false
    }
}

function Send-FinalReport {
    param(
        [hashtable]$Config,
        [hashtable]$ProcessState
    )
    
    # Try to send email with retries
    $maxRetries = $MONITORING_CONFIG.EmailRetry.MaxRetries
    $retryDelay = $MONITORING_CONFIG.EmailRetry.RetryDelaySeconds
    
    for ($retry = 1; $retry -le $maxRetries; $retry++) {
        Write-ProcessLog "Attempting to send final report (Attempt $retry of $maxRetries)..." -Level "INFO"
        
        $sent = Send-EmailReport -Config $Config -ProcessState $ProcessState -Trigger "FINAL_REPORT"
        
        if ($sent) {
            $ProcessState.EmailSent = $true
            return $true
        }
        
        if ($retry -lt $maxRetries) {
            Write-ProcessLog "Waiting $retryDelay seconds before retry..." -Level "INFO"
            Start-Sleep -Seconds $retryDelay
        }
    }
    
    Write-ProcessLog "Failed to send final report after $maxRetries attempts" -Level "ERROR"
    return $false
}
# ===================================

# ========== MAIN EXECUTION ==========

Write-Host "=================================================="
Write-Host "RESILIENT PROCESS EXECUTION SYSTEM"
Write-Host "=================================================="

# Initialize run
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$RUN_FOLDER_NAME = "Run_Process_TowerCPU_Resilient_$timestamp"
$RUN_FOLDER_PATH = Join-Path $RUNS_BASE_PATH $RUN_FOLDER_NAME

# Create run folder structure
$RUN_LOGS_PATH = Join-Path $RUN_FOLDER_PATH "logs"
$RUN_SCRIPT_OUTPUT_PATH = Join-Path $RUN_FOLDER_PATH "script_output"

try {
    New-Item -ItemType Directory -Path $RUN_FOLDER_PATH -Force | Out-Null
    New-Item -ItemType Directory -Path $RUN_LOGS_PATH -Force | Out-Null
    New-Item -ItemType Directory -Path $RUN_SCRIPT_OUTPUT_PATH -Force | Out-Null
    Write-ProcessLog "Created run folder: $RUN_FOLDER_PATH" -Level "SUCCESS"
} catch {
    Write-ProcessLog "Failed to create run folder: $_" -Level "ERROR"
    exit 1
}

# Set up log files
$MAIN_LOG_FILE = Join-Path $RUN_LOGS_PATH "run_$timestamp.log"
$PYTHON_OUTPUT_FILE = Join-Path $RUN_LOGS_PATH "python_output.txt"

# Initialize process state
$Global:ProcessState.RunId = $timestamp
$Global:ProcessState.RunFolder = $RUN_FOLDER_PATH

# Write initial log header
$logHeader = @"
==================================================
RESILIENT PROCESS EXECUTION STARTED
==================================================
Start Time: $(Get-FormattedTimestamp)
Run ID: $timestamp
Run Folder: $RUN_FOLDER_PATH
Script: $POWERSHELL_SCRIPT_NAME
Python Script: $PYTHON_SCRIPT
==================================================
"@

$logHeader | Out-File $MAIN_LOG_FILE
Write-Host $logHeader -ForegroundColor Cyan

# Convert Python parameters
$PYTHON_ARGS = Convert-HashtableToArgs -Params $PYTHON_PARAMS
$argsString = $PYTHON_ARGS -join " "

# Check Python executable
$pythonExe = "$VENV_ROOT\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-ProcessLog "Python executable not found: $pythonExe" -Level "ERROR" -LogFile $MAIN_LOG_FILE
    $Global:ProcessState.Status = "FAILED_PYTHON_NOT_FOUND"
    
    # Send failure report if email is enabled
    if ($EMAIL_CONFIG.Enabled) {
        Send-FinalReport -Config $EMAIL_CONFIG -ProcessState $Global:ProcessState
    }
    
    exit 1
}

# PHASE 1: Start Independent Monitor (if enabled)
$monitorJob = $null
if ($MONITORING_CONFIG.CompletionFileCheck.Enabled) {
    $monitorJob = Start-ProcessMonitor -RunFolder $RUN_FOLDER_PATH -RunId $timestamp -Config $MONITORING_CONFIG
}

# PHASE 2: Start Python Process
Write-ProcessLog "Starting Python process execution..." -Level "INFO" -LogFile $MAIN_LOG_FILE
Write-ProcessLog "Arguments: $argsString" -Level "INFO" -LogFile $MAIN_LOG_FILE

$Global:ProcessState.ProcessStartTime = Get-Date
$Global:ProcessState.Status = "RUNNING"

# Send start notification if email is enabled
if ($EMAIL_CONFIG.Enabled) {
    Send-EmailReport -Config $EMAIL_CONFIG -ProcessState $Global:ProcessState -Trigger "START"
}

try {
    # Prepare Python process
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $pythonExe
    $psi.Arguments = "`"$PYTHON_SCRIPT`" $argsString"
    $psi.WorkingDirectory = $RUN_SCRIPT_OUTPUT_PATH
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    
    # Start Python process
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    
    # Capture output
    $process.Start() | Out-Null
    $Global:ProcessState.PythonProcessId = $process.Id
    
    Write-ProcessLog "Python process started with PID: $($process.Id)" -Level "SUCCESS" -LogFile $MAIN_LOG_FILE
    
    # Asynchronously read output
    $outputReader = $process.StandardOutput
    $errorReader = $process.StandardError
    
    # Start reading output in background
    $outputJob = Start-Job -ScriptBlock {
        param($Reader, $OutputFile)
        while (-not $Reader.EndOfStream) {
            $line = $Reader.ReadLine()
            $line | Out-File $OutputFile -Append
        }
    } -ArgumentList $outputReader, $PYTHON_OUTPUT_FILE
    
    $errorJob = Start-Job -ScriptBlock {
        param($Reader, $OutputFile)
        while (-not $Reader.EndOfStream) {
            $line = $Reader.ReadLine()
            $line | Out-File $OutputFile -Append
        }
    } -ArgumentList $errorReader, $PYTHON_OUTPUT_FILE
    
    # PHASE 3: Watch process with sleep intervals
    Watch-ProcessWithSleep -Process $process -LogFile $MAIN_LOG_FILE -OutputFile $PYTHON_OUTPUT_FILE
    
    # Clean up output jobs
    if ($outputJob) {
        Stop-Job $outputJob -ErrorAction SilentlyContinue
        Remove-Job $outputJob -ErrorAction SilentlyContinue
    }
    
    if ($errorJob) {
        Stop-Job $errorJob -ErrorAction SilentlyContinue
        Remove-Job $errorJob -ErrorAction SilentlyContinue
    }
    
} catch {
    Write-ProcessLog "Error in main execution: $_" -Level "ERROR" -LogFile $MAIN_LOG_FILE
    $Global:ProcessState.Status = "ERROR_IN_EXECUTION"
    $Global:ProcessState.ProcessEndTime = Get-Date
}

# PHASE 4: Post-Execution Monitoring and Sleep
Write-ProcessLog "Entering post-execution monitoring phase..." -Level "INFO" -LogFile $MAIN_LOG_FILE

# Wait a moment for any completion file to be written
Write-ProcessLog "Waiting 10 seconds for completion file to be written..." -Level "INFO" -LogFile $MAIN_LOG_FILE
Start-Sleep -Seconds 10

# Check for completion file
if ($MONITORING_CONFIG.CompletionFileCheck.Enabled) {
    Write-ProcessLog "Checking for completion file..." -Level "INFO" -LogFile $MAIN_LOG_FILE
    
    $checkResult = Check-ForCompletionFile -RunFolder $RUN_FOLDER_PATH -Config $MONITORING_CONFIG.CompletionFileCheck
    
    if ($checkResult.Found) {
        $Global:ProcessState.CompletionFileFound = $true
        $Global:ProcessState.CompletionFilePath = $checkResult.Path
        Write-ProcessLog "Completion file found: $($checkResult.Path)" -Level "SUCCESS" -LogFile $MAIN_LOG_FILE
    } else {
        Write-ProcessLog "Completion file not found immediately after execution" -Level "WARN" -LogFile $MAIN_LOG_FILE
        
        # Additional checks with sleep intervals
        Write-ProcessLog "Performing additional checks with sleep intervals..." -Level "INFO" -LogFile $MAIN_LOG_FILE
        
        for ($i = 1; $i -le 3; $i++) {
            Write-ProcessLog "Additional check $i/3. Waiting 30 seconds..." -Level "INFO" -LogFile $MAIN_LOG_FILE
            Start-Sleep -Seconds 30
            
            $checkResult = Check-ForCompletionFile -RunFolder $RUN_FOLDER_PATH -Config $MONITORING_CONFIG.CompletionFileCheck
            if ($checkResult.Found) {
                $Global:ProcessState.CompletionFileFound = $true
                $Global:ProcessState.CompletionFilePath = $checkResult.Path
                Write-ProcessLog "Completion file found in additional check $i!" -Level "SUCCESS" -LogFile $MAIN_LOG_FILE
                break
            }
        }
    }
}

# PHASE 5: Wait for Monitor Completion
if ($monitorJob) {
    Write-ProcessLog "Checking monitor job status..." -Level "INFO" -LogFile $MAIN_LOG_FILE
    
    # Check if monitor job is still running
    $jobState = Get-Job -Name "ProcessMonitor_$timestamp" -ErrorAction SilentlyContinue
    
    if ($jobState -and $jobState.State -eq "Running") {
        Write-ProcessLog "Monitor job is still running. Waiting up to 60 seconds for completion..." -Level "INFO" -LogFile $MAIN_LOG_FILE
        
        # Wait for monitor with timeout
        $waitResult = Wait-Job $monitorJob -Timeout 60
        
        if ($waitResult) {
            Write-ProcessLog "Monitor job completed" -Level "INFO" -LogFile $MAIN_LOG_FILE
        } else {
            Write-ProcessLog "Monitor job timed out after 60 seconds. Stopping..." -Level "WARN" -LogFile $MAIN_LOG_FILE
            Stop-Job $monitorJob -ErrorAction SilentlyContinue
        }
    }
    
    # Clean up monitor job
    Remove-Job $monitorJob -ErrorAction SilentlyContinue
    Write-ProcessLog "Monitor job cleaned up" -Level "INFO" -LogFile $MAIN_LOG_FILE
}

# PHASE 6: Final Check and Reporting
Write-ProcessLog "Performing final check and reporting..." -Level "INFO" -LogFile $MAIN_LOG_FILE

# Final check for completion file (one last time)
if ($MONITORING_CONFIG.CompletionFileCheck.Enabled -and -not $Global:ProcessState.CompletionFileFound) {
    Write-ProcessLog "Performing final completion file check..." -Level "INFO" -LogFile $MAIN_LOG_FILE
    $finalCheck = Check-ForCompletionFile -RunFolder $RUN_FOLDER_PATH -Config $MONITORING_CONFIG.CompletionFileCheck
    
    if ($finalCheck.Found) {
        $Global:ProcessState.CompletionFileFound = $true
        $Global:ProcessState.CompletionFilePath = $finalCheck.Path
        Write-ProcessLog "Completion file found in final check!" -Level "SUCCESS" -LogFile $MAIN_LOG_FILE
    }
}

# Update final status
if ($Global:ProcessState.Status -eq "COMPLETED" -and $Global:ProcessState.CompletionFileFound) {
    $Global:ProcessState.Status = "COMPLETED_WITH_FILE"
} elseif ($Global:ProcessState.Status -eq "COMPLETED" -and -not $Global:ProcessState.CompletionFileFound) {
    $Global:ProcessState.Status = "COMPLETED_NO_FILE"
} elseif ($Global:ProcessState.Status -eq "STOPPED" -and $Global:ProcessState.CompletionFileFound) {
    $Global:ProcessState.Status = "STOPPED_WITH_FILE"
}

# Send final report if email is enabled
if ($EMAIL_CONFIG.Enabled) {
    Send-FinalReport -Config $EMAIL_CONFIG -ProcessState $Global:ProcessState
} else {
    Write-ProcessLog "Email notifications are disabled. Skipping email report." -Level "INFO" -LogFile $MAIN_LOG_FILE
}

# Create completion summary
$COMPLETION_SUMMARY_FILE = Join-Path $RUN_LOGS_PATH "completion_summary.txt"

$summary = @"
==================================================
RESILIENT PROCESS EXECUTION SUMMARY
==================================================
Completion Time: $(Get-FormattedTimestamp)
Run ID: $timestamp
Final Status: $($Global:ProcessState.Status)
Exit Code: $(if ($Global:ProcessState.ExitCode -ne $null) { $Global:ProcessState.ExitCode } else { "N/A" })
Python PID: $(if ($Global:ProcessState.PythonProcessId) { $Global:ProcessState.PythonProcessId } else { "N/A" })

TIMING
==================================================
Start: $(if ($Global:ProcessState.ProcessStartTime) { $Global:ProcessState.ProcessStartTime.ToString('yyyy-MM-dd HH:mm:ss') } else { "N/A" })
End: $(if ($Global:ProcessState.ProcessEndTime) { $Global:ProcessState.ProcessEndTime.ToString('yyyy-MM-dd HH:mm:ss') } else { "N/A" })
Duration: $(if ($Global:ProcessState.ProcessEndTime -and $Global:ProcessState.ProcessStartTime) { 
    Format-Duration ($Global:ProcessState.ProcessEndTime - $Global:ProcessState.ProcessStartTime) 
} else { "N/A" })

COMPLETION FILE
==================================================
Found: $(if ($Global:ProcessState.CompletionFileFound) { "YES" } else { "NO" })
Path: $(if ($Global:ProcessState.CompletionFilePath) { $Global:ProcessState.CompletionFilePath } else { "N/A" })

EMAIL REPORT
==================================================
Sent: $(if ($Global:ProcessState.EmailSent) { "YES" } else { "NO" })

FOLDER STRUCTURE
==================================================
Run Folder: $RUN_FOLDER_PATH
├── logs\
│   ├── run_$timestamp.log          (This main log)
│   ├── python_output.txt           (Python output)
│   ├── completion_summary.txt      (This summary)
│   └── monitor_$timestamp.log      (Monitor log, if exists)
├── script_output\                  (Python working directory)
└── independent_monitor.ps1         (Monitor script)

NOTES
==================================================
This process uses resilient monitoring with sleep intervals.
The system checks for completion files multiple times with delays.
"@

$summary | Out-File $COMPLETION_SUMMARY_FILE
Write-ProcessLog "Completion summary saved: $COMPLETION_SUMMARY_FILE" -Level "INFO" -LogFile $MAIN_LOG_FILE

# Final output
Write-Host "`n" + "="*50
Write-Host "EXECUTION COMPLETE"
Write-Host "="*50
Write-Host "Run ID: $timestamp" -ForegroundColor Cyan
Write-Host "Status: $($Global:ProcessState.Status)" -ForegroundColor $(if ($Global:ProcessState.Status -match "COMPLETED") { "Green" } else { "Yellow" })
Write-Host "Run Folder: $RUN_FOLDER_PATH" -ForegroundColor Cyan
Write-Host "Completion File: $(if ($Global:ProcessState.CompletionFileFound) { 'FOUND ✓' } else { 'NOT FOUND ✗' })" -ForegroundColor $(if ($Global:ProcessState.CompletionFileFound) { "Green" } else { "Yellow" })
Write-Host "Email Sent: $(if ($Global:ProcessState.EmailSent) { 'YES ✓' } else { 'NO ✗' })" -ForegroundColor $(if ($Global:ProcessState.EmailSent) { "Green" } else { "Yellow" })
Write-Host "="*50

# Exit with appropriate code
$exitCode = if ($Global:ProcessState.ExitCode -ne $null) { $Global:ProcessState.ExitCode } else { 1 }
exit $exitCode
# script-organized-TowerCPU-0-resilient.ps1
# ==============================================
# Resilient version with independent timing detection and monitoring
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

# Email Configuration - SIMPLIFIED (no password in script)
$EMAIL_CONFIG = @{
    Enabled = $true  # Set to $false to disable email
    SmtpServer = "smtp.gmail.com"
    SmtpPort = 587
    UseSsl = $true
    SenderEmail = "tester@gmail.com"  # Update this
    RecipientEmail = "faridraihan17@gmail.com"  # Update this
    SubjectPrefix = "[FaceRecog Completion]"
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
    Status = "NOT_STARTED"  # NOT_STARTED, RUNNING, COMPLETED, FAILED, STOPPED
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

# ========== MONITORING FUNCTIONS ==========
function Start-ProcessMonitor {
    <#
    .SYNOPSIS
    Starts an independent monitoring process that checks for completion files
    and sends email reports even if the main process is stopped.
    #>
    
    param(
        [string]$RunFolder,
        [string]$RunId,
        [hashtable]$Config
    )
    
    Write-ProcessLog "Starting independent process monitor..." -Level "INFO"
    
    # Save monitoring script to a temporary file
    $monitorScript = @"
# Independent Process Monitor
# ===========================
# This script runs independently to monitor the main process

`$RunFolder = "$RunFolder"
`$RunId = "$RunId"
`$EmailConfig = @"
$(ConvertTo-Json $EMAIL_CONFIG -Depth 3)
"@ | ConvertFrom-Json

`$MonitorConfig = @"
$(ConvertTo-Json $Config -Depth 3)
"@ | ConvertFrom-Json

# Initialize state
`$startTime = Get-Date
`$lastCheck = Get-Date
`$checkCount = 0
`$completionFileFound = `$false
`$completionFilePath = `$null
`$emailSent = `$false

# Log file for monitor
`$monitorLog = Join-Path `$RunFolder "monitor_`$RunId.log"
"Monitor started at: `$(Get-Date)" | Out-File `$monitorLog
"Monitoring run folder: `$RunFolder" | Out-File `$monitorLog -Append

# Main monitoring loop
`$maxChecks = [math]::Ceiling((`$MonitorConfig.CompletionFileCheck.MaxMonitorTimeMinutes * 60) / `$MonitorConfig.CompletionFileCheck.CheckIntervalSeconds)

while (`$checkCount -lt `$maxChecks) {
    `$checkCount++
    `$currentTime = Get-Date
    `$elapsed = `$currentTime - `$startTime
    
    # Check for completion file
    if (-not `$completionFileFound) {
        `$completionFile = Join-Path `$RunFolder `$MonitorConfig.CompletionFileCheck.FileName
        `$completionFileAlt = Join-Path `$RunFolder "script_output" `$MonitorConfig.CompletionFileCheck.FileName
        
        if (Test-Path `$completionFile) {
            `$completionFileFound = `$true
            `$completionFilePath = `$completionFile
            "COMPLETION FILE FOUND: `$completionFile at `$(Get-Date)" | Out-File `$monitorLog -Append
        } elseif (Test-Path `$completionFileAlt) {
            `$completionFileFound = `$true
            `$completionFilePath = `$completionFileAlt
            "COMPLETION FILE FOUND: `$completionFileAlt at `$(Get-Date)" | Out-File `$monitorLog -Append
        }
    }
    
    # Check if main process is still running
    `$mainLog = Join-Path `$RunFolder "logs\run_`$RunId.log"
    if (Test-Path `$mainLog) {
        `$logContent = Get-Content `$mainLog -Tail 10
        `$hasErrors = `$logContent | Where-Object { `$_ -match "ERROR|EXCEPTION|FAILED" }
        
        if (`$hasErrors) {
            "Main process has errors detected in log" | Out-File `$monitorLog -Append
        }
    }
    
    # Send email if completion file found or max time reached
    if (`$completionFileFound -or (`$checkCount -eq `$maxChecks)) {
        if (-not `$emailSent) {
            `$status = if (`$completionFileFound) { "COMPLETED_WITH_FILE" } else { "TIMEOUT_NO_FILE" }
            `$result = Send-MonitorEmail -Config `$EmailConfig -RunFolder `$RunFolder -RunId `$RunId -Status `$status -CompletionFilePath `$completionFilePath -ElapsedTime `$elapsed
            if (`$result) {
                `$emailSent = `$true
                "Email notification sent for status: `$status" | Out-File `$monitorLog -Append
            }
        }
        
        if (`$completionFileFound) {
            # If completion file found, we can exit
            "Completion file found and email sent. Exiting monitor." | Out-File `$monitorLog -Append
            break
        }
    }
    
    "Check #`$checkCount at `$(Get-Date) - Elapsed: `$(`$elapsed.ToString('hh\:mm\:ss'))" | Out-File `$monitorLog -Append
    
    # Wait for next check
    Start-Sleep -Seconds `$MonitorConfig.CompletionFileCheck.CheckIntervalSeconds
}

"Monitor completed at: `$(Get-Date)" | Out-File `$monitorLog -Append
"Total checks: `$checkCount" | Out-File `$monitorLog -Append
"Completion file found: `$completionFileFound" | Out-File `$monitorLog -Append
"Email sent: `$emailSent" | Out-File `$monitorLog -Append

# Email sending function
function Send-MonitorEmail {
    param(
        `$Config,
        `$RunFolder,
        `$RunId,
        `$Status,
        `$CompletionFilePath,
        `$ElapsedTime
    )
    
    try {
        # Use default Windows credentials (no password in script)
        `$subject = "`$(`$Config.SubjectPrefix) Monitor Report - `$RunId"
        
        `$body = @"
Independent Monitor Report
==========================
Run ID: `$RunId
Report Time: `$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Status: `$Status
Monitor Elapsed Time: `$(`$ElapsedTime.ToString('hh\:mm\:ss'))

LOCATION
==========================
Run Folder: `$RunFolder

COMPLETION FILE
==========================
Status: `$(if (`$CompletionFilePath) { "FOUND at `$CompletionFilePath" } else { "NOT FOUND" })

MONITOR LOG
==========================
Monitor log file: `$monitorLog

NOTES
==========================
This is an automated report from the independent process monitor.
The monitor runs separately from the main process and continues
checking even if the main process is stopped or fails.

System: `$env:COMPUTERNAME
User: `$env:USERNAME
"@
        
        # Try to send email using default credentials
        Send-MailMessage `
            -From `$Config.SenderEmail `
            -To `$Config.RecipientEmail `
            -Subject `$subject `
            -Body `$body `
            -SmtpServer `$Config.SmtpServer `
            -Port `$Config.SmtpPort `
            -UseSsl:`$(`$Config.UseSsl) `
            -ErrorAction Stop
        
        return `$true
    } catch {
        "Failed to send email: `$_" | Out-File `$monitorLog -Append
        return `$false
    }
}
"@
    
    # Save monitor script to file
    $monitorScriptPath = Join-Path $RunFolder "independent_monitor.ps1"
    $monitorScript | Out-File $monitorScriptPath -Encoding UTF8
    
    Write-ProcessLog "Monitor script saved to: $monitorScriptPath" -Level "INFO"
    
    # Start monitor as a background job
    $monitorJob = Start-Job -Name "ProcessMonitor_$RunId" -ScriptBlock {
        param($MonitorScriptPath)
        & $MonitorScriptPath
    } -ArgumentList $monitorScriptPath
    
    Write-ProcessLog "Monitor started as job with ID: $($monitorJob.Id)" -Level "SUCCESS"
    
    return $monitorJob
}

function Check-ForCompletionFile {
    <#
    .SYNOPSIS
    Checks if completion file exists and returns its path
    #>
    
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
# ===================================

# ========== EMAIL FUNCTIONS ==========
function Send-EmailReport {
    <#
    .SYNOPSIS
    Sends email report with current process state
    Uses default Windows credentials (no password in script)
    #>
    
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
        # Note: For Gmail, you may need to enable "Allow less secure apps" or use app password
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
    <#
    .SYNOPSIS
    Sends final report after all monitoring is complete
    #>
    
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

# ========== PROCESS EXECUTION FUNCTIONS ==========
function Start-PythonProcess {
    <#
    .SYNOPSIS
    Starts the Python process and returns process information
    #>
    
    param(
        [string]$PythonExe,
        [string]$PythonScript,
        [array]$PythonArgs,
        [string]$WorkingDirectory,
        [string]$OutputFile
    )
    
    try {
        Write-ProcessLog "Starting Python process..." -Level "INFO"
        
        # Create process start info
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $PythonExe
        $startInfo.Arguments = "`"$PythonScript`" $($PythonArgs -join ' ')"
        $startInfo.WorkingDirectory = $WorkingDirectory
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        
        # Start the process
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        
        # Set up output redirection
        $stdoutBuilder = New-Object System.Text.StringBuilder
        $stderrBuilder = New-Object System.Text.StringBuilder
        
        $outputHandler = {
            if (![String]::IsNullOrWhiteSpace($EventArgs.Data)) {
                $stdoutBuilder.AppendLine($EventArgs.Data)
                $EventArgs.Data | Out-File $OutputFile -Append
            }
        }
        
        $errorHandler = {
            if (![String]::IsNullOrWhiteSpace($EventArgs.Data)) {
                $stderrBuilder.AppendLine($EventArgs.Data)
                $EventArgs.Data | Out-File $OutputFile -Append
            }
        }
        
        $eventJob = Register-ObjectEvent -InputObject $process -EventName OutputDataReceived -Action $outputHandler
        $errorJob = Register-ObjectEvent -InputObject $process -EventName ErrorDataReceived -Action $errorHandler
        
        # Start process
        $processStarted = $process.Start()
        
        if (-not $processStarted) {
            throw "Failed to start Python process"
        }
        
        $process.BeginOutputReadLine()
        $process.BeginErrorReadLine()
        
        # Return process information
        return @{
            Process = $process
            ProcessId = $process.Id
            StartTime = Get-Date
            EventJobs = @($eventJob, $errorJob)
        }
        
    } catch {
        Write-ProcessLog "Failed to start Python process: $_" -Level "ERROR"
        throw
    }
}

function Watch-ProcessCompletion {
    <#
    .SYNOPSIS
    Watches for process completion and updates state
    #>
    
    param(
        [hashtable]$ProcessInfo,
        [ref]$ProcessState
    )
    
    try {
        $process = $ProcessInfo.Process
        
        # Wait for process to exit with timeout
        $timeoutMinutes = 5
        $timeout = New-TimeSpan -Minutes $timeoutMinutes
        
        if ($process.WaitForExit([int]$timeout.TotalMilliseconds)) {
            # Process exited normally
            $ProcessState.Value.ExitCode = $process.ExitCode
            $ProcessState.Value.ProcessEndTime = Get-Date
            $ProcessState.Value.Status = if ($process.ExitCode -eq 0) { "COMPLETED" } else { "FAILED" }
            
            Write-ProcessLog "Python process exited with code: $($process.ExitCode)" -Level "INFO"
        } else {
            # Process timed out or was stopped
            $ProcessState.Value.Status = "STOPPED_OR_TIMEOUT"
            $ProcessState.Value.ProcessEndTime = Get-Date
            
            Write-ProcessLog "Python process did not complete within $timeoutMinutes minutes" -Level "WARN"
            
            # Try to kill the process if it's still running
            if (-not $process.HasExited) {
                $process.Kill()
                Write-ProcessLog "Python process killed" -Level "WARN"
            }
        }
        
        # Clean up event jobs
        foreach ($job in $ProcessInfo.EventJobs) {
            if ($job) {
                Unregister-Event -SourceIdentifier $job.Name -ErrorAction SilentlyContinue
                Remove-Job $job -ErrorAction SilentlyContinue
            }
        }
        
    } catch {
        Write-ProcessLog "Error watching process: $_" -Level "ERROR"
        $ProcessState.Value.Status = "ERROR_IN_MONITORING"
    }
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

# Start independent monitor
$monitorJob = $null
if ($MONITORING_CONFIG.CompletionFileCheck.Enabled) {
    $monitorJob = Start-ProcessMonitor -RunFolder $RUN_FOLDER_PATH -RunId $timestamp -Config $MONITORING_CONFIG
}

# Convert Python parameters
$PYTHON_ARGS = Convert-HashtableToArgs -Params $PYTHON_PARAMS
$argsString = $PYTHON_ARGS -join " "

# Check Python executable
$pythonExe = "$VENV_ROOT\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-ProcessLog "Python executable not found: $pythonExe" -Level "ERROR" -LogFile $MAIN_LOG_FILE
    $Global:ProcessState.Status = "FAILED_PYTHON_NOT_FOUND"
    
    # Send failure report
    Send-FinalReport -Config $EMAIL_CONFIG -ProcessState $Global:ProcessState
    
    # Stop monitor if running
    if ($monitorJob) {
        Stop-Job $monitorJob -ErrorAction SilentlyContinue
        Remove-Job $monitorJob -ErrorAction SilentlyContinue
    }
    
    exit 1
}

# PHASE 1: Start Python Process
Write-ProcessLog "Starting Python process execution..." -Level "INFO" -LogFile $MAIN_LOG_FILE
Write-ProcessLog "Arguments: $argsString" -Level "INFO" -LogFile $MAIN_LOG_FILE

$Global:ProcessState.ProcessStartTime = Get-Date
$Global:ProcessState.Status = "RUNNING"

# Send start notification
Send-EmailReport -Config $EMAIL_CONFIG -ProcessState $Global:ProcessState -Trigger "START"

try {
    # Start Python process
    $processInfo = Start-PythonProcess `
        -PythonExe $pythonExe `
        -PythonScript $PYTHON_SCRIPT `
        -PythonArgs $PYTHON_ARGS `
        -WorkingDirectory $RUN_SCRIPT_OUTPUT_PATH `
        -OutputFile $PYTHON_OUTPUT_FILE
    
    $Global:ProcessState.PythonProcessId = $processInfo.ProcessId
    
    Write-ProcessLog "Python process started with PID: $($processInfo.ProcessId)" -Level "SUCCESS" -LogFile $MAIN_LOG_FILE
    
    # PHASE 2: Monitor Process Completion
    Write-ProcessLog "Starting process completion watch..." -Level "INFO" -LogFile $MAIN_LOG_FILE
    
    Watch-ProcessCompletion -ProcessInfo $processInfo -ProcessState ([ref]$Global:ProcessState)
    
} catch {
    Write-ProcessLog "Error in main execution: $_" -Level "ERROR" -LogFile $MAIN_LOG_FILE
    $Global:ProcessState.Status = "ERROR_IN_EXECUTION"
    $Global:ProcessState.ProcessEndTime = Get-Date
}

# PHASE 3: Post-Execution Monitoring
Write-ProcessLog "Entering post-execution monitoring phase..." -Level "INFO" -LogFile $MAIN_LOG_FILE

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
    }
}

# PHASE 4: Wait for Monitor Completion
if ($monitorJob) {
    Write-ProcessLog "Waiting for independent monitor to complete..." -Level "INFO" -LogFile $MAIN_LOG_FILE
    
    # Wait for monitor job to complete (with timeout)
    $monitorTimeout = New-TimeSpan -Minutes ($MONITORING_CONFIG.CompletionFileCheck.MaxMonitorTimeMinutes + 5)
    
    $waitResult = Wait-Job $monitorJob -Timeout $monitorTimeout.TotalSeconds
    
    if ($waitResult) {
        Write-ProcessLog "Independent monitor completed" -Level "INFO" -LogFile $MAIN_LOG_FILE
        
        # Get monitor results
        $monitorResult = Receive-Job $monitorJob -ErrorAction SilentlyContinue
        if ($monitorResult) {
            $monitorResult | Out-File $MAIN_LOG_FILE -Append
        }
    } else {
        Write-ProcessLog "Independent monitor timed out" -Level "WARN" -LogFile $MAIN_LOG_FILE
        
        # Stop the monitor job
        Stop-Job $monitorJob -ErrorAction SilentlyContinue
    }
    
    # Clean up monitor job
    Remove-Job $monitorJob -ErrorAction SilentlyContinue
}

# PHASE 5: Final Reporting
Write-ProcessLog "Generating final reports..." -Level "INFO" -LogFile $MAIN_LOG_FILE

# Final check for completion file
if ($MONITORING_CONFIG.CompletionFileCheck.Enabled -and -not $Global:ProcessState.CompletionFileFound) {
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
}

# Send final report
Send-FinalReport -Config $EMAIL_CONFIG -ProcessState $Global:ProcessState

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
This process uses resilient monitoring that continues
even if the main Python process is stopped or fails.
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
# script-organized-TowerCPU-0-resilient-monitor-only.ps1
# ==============================================
# Resilient version with independent monitor job only (no sleep intervals)
# Monitor keeps running until email is sent
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
    Enabled = $true  # Set to $true after configuring
    SmtpServer = "smtp.gmail.com"
    SmtpPort = 587
    UseSsl = $true
    SenderEmail = "your-email@gmail.com"
    RecipientEmail = "faridraihan17@gmail.com"
    SubjectPrefix = "[FaceRecog Process]"
}

# Monitor Configuration - SIMPLIFIED
$MONITOR_CONFIG = @{
    # Monitor will keep running until email is sent
    MonitorEnabled = $true
    CompletionFileName = "metadata.json"
    CheckIntervalSeconds = 30  # Check every 30 seconds
    MaxMonitorTimeHours = 24   # Maximum 24 hours (monitor will stop after this)
    SendEmailOnCompletion = $true
    SendEmailOnTimeout = $true
}

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
}

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

function Write-ProcessLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "$timestamp [$Level] $Message"
    
    # Write to console with appropriate color
    switch ($Level) {
        "ERROR" { Write-Host $logEntry -ForegroundColor Red }
        "WARN" { Write-Host $logEntry -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logEntry -ForegroundColor Green }
        "INFO" { Write-Host $logEntry -ForegroundColor Cyan }
        default { Write-Host $logEntry }
    }
}
# ===================================

# ========== MONITOR FUNCTIONS ==========
function Start-IndependentMonitor {
    <#
    .SYNOPSIS
    Starts an independent monitor that keeps running until email is sent
    Runs in a separate PowerShell process that continues even if main script exits
    #>
    
    param(
        [string]$RunFolder,
        [string]$RunId,
        [hashtable]$MonitorConfig,
        [hashtable]$EmailConfig
    )
    
    Write-ProcessLog "Starting independent monitor process..." -Level "INFO"
    
    # Create a separate monitor script file
    $monitorScript = @'
# ==============================================
# INDEPENDENT MONITOR PROCESS
# Runs continuously until email is sent or timeout
# ==============================================

param(
    [string]$RunFolder,
    [string]$RunId,
    [int]$CheckIntervalSeconds = 30,
    [int]$MaxMonitorTimeHours = 24,
    [string]$CompletionFileName = "metadata.json",
    [string]$SmtpServer,
    [int]$SmtpPort,
    [bool]$UseSsl,
    [string]$SenderEmail,
    [string]$RecipientEmail,
    [string]$SubjectPrefix,
    [bool]$SendEmailOnCompletion = $true,
    [bool]$SendEmailOnTimeout = $true
)

# Create monitor log file
$monitorLog = Join-Path $RunFolder "monitor_$RunId.log"
"==================================================" | Out-File $monitorLog
"INDEPENDENT MONITOR STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $monitorLog -Append
"Run Folder: $RunFolder" | Out-File $monitorLog -Append
"Run ID: $RunId" | Out-File $monitorLog -Append
"Check Interval: ${CheckIntervalSeconds}s" | Out-File $monitorLog -Append
"Max Monitor Time: ${MaxMonitorTimeHours}h" | Out-File $monitorLog -Append
"==================================================" | Out-File $monitorLog -Append

# Calculate end time for monitoring
$monitorStartTime = Get-Date
$monitorEndTime = $monitorStartTime.AddHours($MaxMonitorTimeHours)
$emailSent = $false
$checkCount = 0

# Main monitor loop - runs until email is sent or timeout
while ((Get-Date) -lt $monitorEndTime -and -not $emailSent) {
    $checkCount++
    $currentTime = Get-Date
    $elapsedTime = $currentTime - $monitorStartTime
    $elapsedFormatted = "{0:D2}:{1:D2}:{2:D2}" -f $elapsedTime.Hours, $elapsedTime.Minutes, $elapsedTime.Seconds
    
    # Log check
    "Check #$checkCount at $($currentTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $monitorLog -Append
    "  Elapsed: $elapsedFormatted" | Out-File $monitorLog -Append
    
    # Check for completion file in multiple locations
    $completionFilePaths = @(
        Join-Path $RunFolder $CompletionFileName
        Join-Path $RunFolder "script_output" $CompletionFileName
        Join-Path $RunFolder "logs" $CompletionFileName
    )
    
    $foundFile = $null
    foreach ($path in $completionFilePaths) {
        if (Test-Path $path) {
            $foundFile = $path
            "  COMPLETION FILE FOUND: $path" | Out-File $monitorLog -Append
            break
        }
    }
    
    # If completion file found, send email
    if ($foundFile -and $SendEmailOnCompletion -and -not $emailSent) {
        try {
            $completionTime = Get-Date
            $subject = "$SubjectPrefix PROCESS COMPLETED - $RunId"
            
            $body = @"
INDEPENDENT MONITOR REPORT - PROCESS COMPLETED
==================================================
Run ID: $RunId
Completion Time: $($completionTime.ToString('yyyy-MM-dd HH:mm:ss'))
Monitor Runtime: $elapsedFormatted
Check Count: $checkCount

COMPLETION FILE
==================================================
Found at: $foundFile
Found at check: $checkCount

LOCATION
==================================================
Run Folder: $RunFolder

MONITOR INFORMATION
==================================================
Monitor started: $($monitorStartTime.ToString('yyyy-MM-dd HH:mm:ss'))
Monitor log: $monitorLog

SYSTEM INFORMATION
==================================================
Host: $env:COMPUTERNAME
User: $env:USERNAME

NOTES
==================================================
This email was sent by the independent monitor process
when it detected the completion file.
"@
            
            # Send email
            Send-MailMessage `
                -From $SenderEmail `
                -To $RecipientEmail `
                -Subject $subject `
                -Body $body `
                -SmtpServer $SmtpServer `
                -Port $SmtpPort `
                -UseSsl:$UseSsl `
                -ErrorAction Stop
            
            "EMAIL SENT SUCCESSFULLY to $RecipientEmail" | Out-File $monitorLog -Append
            $emailSent = $true
            
            # Exit monitor since email was sent
            break
            
        } catch {
            $errorMsg = "Failed to send email: $_"
            $errorMsg | Out-File $monitorLog -Append
            
            # Don't break - keep trying on next check
        }
    }
    
    # Check if we've reached timeout
    if ((Get-Date) -ge $monitorEndTime) {
        "MONITOR TIMEOUT REACHED: $MaxMonitorTimeHours hours" | Out-File $monitorLog -Append
        
        if ($SendEmailOnTimeout -and -not $emailSent) {
            try {
                $subject = "$SubjectPrefix MONITOR TIMEOUT - $RunId"
                
                $body = @"
INDEPENDENT MONITOR REPORT - TIMEOUT
==================================================
Run ID: $RunId
Timeout Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Monitor Runtime: $elapsedFormatted
Total Checks: $checkCount

STATUS
==================================================
Completion file was NOT found within $MaxMonitorTimeHours hours.

LOCATION
==================================================
Run Folder: $RunFolder

CHECKED LOCATIONS
==================================================
$(($completionFilePaths | ForEach-Object { "  • $_" }) -join "`n")

MONITOR INFORMATION
==================================================
Monitor started: $($monitorStartTime.ToString('yyyy-MM-dd HH:mm:ss'))
Monitor ended: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Monitor log: $monitorLog

SYSTEM INFORMATION
==================================================
Host: $env:COMPUTERNAME
User: $env:USERNAME

NOTES
==================================================
The independent monitor has stopped after $MaxMonitorTimeHours hours
without finding the completion file.
"@
                
                # Send timeout email
                Send-MailMessage `
                    -From $SenderEmail `
                    -To $RecipientEmail `
                    -Subject $subject `
                    -Body $body `
                    -SmtpServer $SmtpServer `
                    -Port $SmtpPort `
                    -UseSsl:$UseSsl `
                    -ErrorAction Stop
                
                "TIMEOUT EMAIL SENT to $RecipientEmail" | Out-File $monitorLog -Append
                $emailSent = $true
                
            } catch {
                $errorMsg = "Failed to send timeout email: $_"
                $errorMsg | Out-File $monitorLog -Append
            }
        }
        
        break
    }
    
    # Wait for next check
    "Waiting $CheckIntervalSeconds seconds for next check..." | Out-File $monitorLog -Append
    Start-Sleep -Seconds $CheckIntervalSeconds
}

# Final log entry
if ($emailSent) {
    "MONITOR COMPLETED: Email was sent successfully" | Out-File $monitorLog -Append
} else {
    "MONITOR STOPPED: Timeout reached without sending email" | Out-File $monitorLog -Append
}

"Total checks performed: $checkCount" | Out-File $monitorLog -Append
"Monitor ended at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $monitorLog -Append
"==================================================" | Out-File $monitorLog -Append
'@
    
    # Save monitor script to file
    $monitorScriptPath = Join-Path $RunFolder "independent_monitor.ps1"
    $monitorScript | Out-File $monitorScriptPath -Encoding UTF8
    
    Write-ProcessLog "Monitor script saved to: $monitorScriptPath" -Level "INFO"
    
    # Build arguments for the monitor script
    $monitorArgs = @(
        "-WindowStyle", "Hidden",
        "-File", "`"$monitorScriptPath`"",
        "-RunFolder", "`"$RunFolder`"",
        "-RunId", $RunId,
        "-CheckIntervalSeconds", $MonitorConfig.CheckIntervalSeconds,
        "-MaxMonitorTimeHours", $MonitorConfig.MaxMonitorTimeHours,
        "-CompletionFileName", $MonitorConfig.CompletionFileName,
        "-SmtpServer", $EmailConfig.SmtpServer,
        "-SmtpPort", $EmailConfig.SmtpPort,
        "-UseSsl", $EmailConfig.UseSsl,
        "-SenderEmail", $EmailConfig.SenderEmail,
        "-RecipientEmail", $EmailConfig.RecipientEmail,
        "-SubjectPrefix", $EmailConfig.SubjectPrefix,
        "-SendEmailOnCompletion", $MonitorConfig.SendEmailOnCompletion,
        "-SendEmailOnTimeout", $MonitorConfig.SendEmailOnTimeout
    )
    
    # Start the monitor as a completely independent process
    # This process will continue even if the main script exits
    $monitorProcess = Start-Process powershell.exe -ArgumentList $monitorArgs -PassThru
    
    Write-ProcessLog "Independent monitor started with PID: $($monitorProcess.Id)" -Level "SUCCESS"
    
    return $monitorProcess
}

function Check-ProcessCompletionSimple {
    <#
    .SYNOPSIS
    Simple process completion check without sleep intervals
    Just runs the process and waits for it to exit
    #>
    
    param(
        [System.Diagnostics.Process]$Process,
        [string]$OutputFile
    )
    
    try {
        # Simply wait for the process to exit
        $process.WaitForExit()
        
        $Global:ProcessState.ExitCode = $process.ExitCode
        $Global:ProcessState.ProcessEndTime = Get-Date
        $Global:ProcessState.Status = if ($process.ExitCode -eq 0) { "COMPLETED" } else { "FAILED" }
        
        Write-ProcessLog "Process exited with code: $($process.ExitCode)" -Level "INFO"
        
        # Read any remaining output
        $output = $process.StandardOutput.ReadToEnd()
        $errorOutput = $process.StandardError.ReadToEnd()
        
        if ($output) { $output | Out-File $OutputFile -Append }
        if ($errorOutput) { $errorOutput | Out-File $OutputFile -Append }
        
    } catch {
        Write-ProcessLog "Error checking process completion: $_" -Level "ERROR"
        $Global:ProcessState.Status = "ERROR"
        $Global:ProcessState.ProcessEndTime = Get-Date
    }
}
# ===================================

# ========== MAIN EXECUTION ==========
Write-Host "=================================================="
Write-Host "PROCESS EXECUTION WITH INDEPENDENT MONITOR"
Write-Host "=================================================="
Write-Host "Note: Independent monitor will keep running until email is sent"
Write-Host "=================================================="

# Initialize run
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$RUN_FOLDER_NAME = "Run_Process_TowerCPU_Monitor_$timestamp"
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
PROCESS EXECUTION WITH INDEPENDENT MONITOR
==================================================
Start Time: $(Get-FormattedTimestamp)
Run ID: $timestamp
Run Folder: $RUN_FOLDER_PATH
Script: $POWERSHELL_SCRIPT_NAME
Python Script: $PYTHON_SCRIPT
Independent Monitor: $(if ($MONITOR_CONFIG.MonitorEnabled -and $EMAIL_CONFIG.Enabled) { "ENABLED" } else { "DISABLED" })
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
    Write-ProcessLog "Python executable not found: $pythonExe" -Level "ERROR"
    $Global:ProcessState.Status = "FAILED_PYTHON_NOT_FOUND"
    exit 1
}

# PHASE 1: Start Independent Monitor (if enabled)
$monitorProcess = $null
if ($MONITOR_CONFIG.MonitorEnabled -and $EMAIL_CONFIG.Enabled) {
    $monitorProcess = Start-IndependentMonitor `
        -RunFolder $RUN_FOLDER_PATH `
        -RunId $timestamp `
        -MonitorConfig $MONITOR_CONFIG `
        -EmailConfig $EMAIL_CONFIG
} else {
    if (-not $EMAIL_CONFIG.Enabled) {
        Write-ProcessLog "Email is disabled. Monitor will not start." -Level "WARN"
    }
    if (-not $MONITOR_CONFIG.MonitorEnabled) {
        Write-ProcessLog "Monitor is disabled in configuration." -Level "WARN"
    }
}

# PHASE 2: Run Python Process (NO SLEEP INTERVALS)
Write-ProcessLog "Starting Python process execution..." -Level "INFO"
Write-ProcessLog "Arguments: $argsString" -Level "INFO"

$Global:ProcessState.ProcessStartTime = Get-Date
$Global:ProcessState.Status = "RUNNING"

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
    
    # Start the process
    $process.Start() | Out-Null
    $Global:ProcessState.PythonProcessId = $process.Id
    
    Write-ProcessLog "Python process started with PID: $($process.Id)" -Level "SUCCESS"
    
    # PHASE 3: Simple Process Completion Check (NO SLEEP INTERVALS)
    Write-ProcessLog "Waiting for process completion..." -Level "INFO"
    Write-ProcessLog "No sleep intervals - just waiting for process to exit" -Level "INFO"
    
    Check-ProcessCompletionSimple -Process $process -OutputFile $PYTHON_OUTPUT_FILE
    
} catch {
    Write-ProcessLog "Error in main execution: $_" -Level "ERROR"
    $Global:ProcessState.Status = "ERROR_IN_EXECUTION"
    $Global:ProcessState.ProcessEndTime = Get-Date
}

# PHASE 4: Quick Post-Execution Check
Write-ProcessLog "Performing quick post-execution check..." -Level "INFO"

# Do a single immediate check for completion file (no waiting)
$completionFilePaths = @(
    Join-Path $RUN_FOLDER_PATH $MONITOR_CONFIG.CompletionFileName
    Join-Path $RUN_SCRIPT_OUTPUT_PATH $MONITOR_CONFIG.CompletionFileName
    Join-Path $RUN_LOGS_PATH $MONITOR_CONFIG.CompletionFileName
)

foreach ($path in $completionFilePaths) {
    if (Test-Path $path) {
        $Global:ProcessState.CompletionFileFound = $true
        $Global:ProcessState.CompletionFilePath = $path
        Write-ProcessLog "Completion file found: $path" -Level "SUCCESS"
        break
    }
}

# Update final status
if ($Global:ProcessState.Status -eq "COMPLETED" -and $Global:ProcessState.CompletionFileFound) {
    $Global:ProcessState.Status = "COMPLETED_WITH_FILE"
} elseif ($Global:ProcessState.Status -eq "COMPLETED" -and -not $Global:ProcessState.CompletionFileFound) {
    $Global:ProcessState.Status = "COMPLETED_NO_FILE"
} elseif ($Global:ProcessState.Status -eq "FAILED" -and $Global:ProcessState.CompletionFileFound) {
    $Global:ProcessState.Status = "FAILED_WITH_FILE"
}

# PHASE 5: Create Completion Summary
$COMPLETION_SUMMARY_FILE = Join-Path $RUN_LOGS_PATH "completion_summary.txt"

$duration = if ($Global:ProcessState.ProcessEndTime -and $Global:ProcessState.ProcessStartTime) {
    $Global:ProcessState.ProcessEndTime - $Global:ProcessState.ProcessStartTime
    "{0:D2}:{1:D2}:{2:D2}" -f $duration.Hours, $duration.Minutes, $duration.Seconds
} else {
    "N/A"
}

$summary = @"
==================================================
PROCESS EXECUTION SUMMARY
==================================================
Completion Time: $(Get-FormattedTimestamp)
Run ID: $timestamp
Final Status: $($Global:ProcessState.Status)
Exit Code: $(if ($Global:ProcessState.ExitCode -ne $null) { $Global:ProcessState.ExitCode } else { "N/A" })
Python PID: $(if ($Global:ProcessState.PythonProcessId) { $Global:ProcessState.PythonProcessId } else { "N/A" })

PROCESS TIMING
==================================================
Start: $(if ($Global:ProcessState.ProcessStartTime) { $Global:ProcessState.ProcessStartTime.ToString('yyyy-MM-dd HH:mm:ss') } else { "N/A" })
End: $(if ($Global:ProcessState.ProcessEndTime) { $Global:ProcessState.ProcessEndTime.ToString('yyyy-MM-dd HH:mm:ss') } else { "N/A" })
Duration: $duration

COMPLETION FILE
==================================================
Found: $(if ($Global:ProcessState.CompletionFileFound) { "YES" } else { "NO" })
Path: $(if ($Global:ProcessState.CompletionFilePath) { $Global:ProcessState.CompletionFilePath } else { "N/A" })

INDEPENDENT MONITOR
==================================================
Status: $(if ($monitorProcess) { "RUNNING (PID: $($monitorProcess.Id))" } else { "DISABLED" })
Configuration: $(if ($MONITOR_CONFIG.MonitorEnabled -and $EMAIL_CONFIG.Enabled) { 
    "Enabled - Will run for up to $($MONITOR_CONFIG.MaxMonitorTimeHours) hours or until email is sent"
} else { "Disabled" })

MONITOR DETAILS
==================================================
Check Interval: $($MONITOR_CONFIG.CheckIntervalSeconds) seconds
Max Runtime: $($MONITOR_CONFIG.MaxMonitorTimeHours) hours
Completion File: $($MONITOR_CONFIG.CompletionFileName)

Email on Completion: $(if ($MONITOR_CONFIG.SendEmailOnCompletion) { "YES" } else { "NO" })
Email on Timeout: $(if ($MONITOR_CONFIG.SendEmailOnTimeout) { "YES" } else { "NO" })

MONITOR LOG FILE
==================================================
$(if ($monitorProcess) { Join-Path $RUN_FOLDER_PATH "monitor_$timestamp.log" } else { "N/A" })

FOLDER STRUCTURE
==================================================
Run Folder: $RUN_FOLDER_PATH
├── logs\
│   ├── run_$timestamp.log          (This main log)
│   ├── python_output.txt           (Python output)
│   └── completion_summary.txt      (This summary)
├── script_output\                  (Python working directory)
└── independent_monitor.ps1         (Monitor script)

NOTES
==================================================
1. The independent monitor runs in a separate PowerShell process
2. Monitor will continue running until it sends an email or times out ($($MONITOR_CONFIG.MaxMonitorTimeHours) hours)
3. No sleep intervals in main process - just simple execution
4. Check monitor log for ongoing monitoring activity
"@

$summary | Out-File $COMPLETION_SUMMARY_FILE
Write-ProcessLog "Completion summary saved: $COMPLETION_SUMMARY_FILE" -Level "INFO"

# Final output
Write-Host "`n" + "="*60
Write-Host "PROCESS EXECUTION COMPLETE"
Write-Host "="*60
Write-Host "Run ID: $timestamp" -ForegroundColor Cyan
Write-Host "Status: $($Global:ProcessState.Status)" -ForegroundColor $(if ($Global:ProcessState.Status -match "COMPLETED") { "Green" } else { "Yellow" })
Write-Host "Exit Code: $(if ($Global:ProcessState.ExitCode -ne $null) { $Global:ProcessState.ExitCode } else { "N/A" })" -ForegroundColor $(if ($Global:ProcessState.ExitCode -eq 0) { "Green" } else { "Red" })
Write-Host "Duration: $duration" -ForegroundColor Cyan
Write-Host "Run Folder: $RUN_FOLDER_PATH" -ForegroundColor Cyan
Write-Host ""
Write-Host "INDEPENDENT MONITOR STATUS:" -ForegroundColor White
if ($monitorProcess) {
    Write-Host "  • Status: RUNNING ✓" -ForegroundColor Green
    Write-Host "  • PID: $($monitorProcess.Id)" -ForegroundColor Gray
    Write-Host "  • Will run for up to $($MONITOR_CONFIG.MaxMonitorTimeHours) hours" -ForegroundColor Gray
    Write-Host "  • Or until email is sent to: $($EMAIL_CONFIG.RecipientEmail)" -ForegroundColor Gray
    Write-Host "  • Monitor log: $RUN_FOLDER_PATH\monitor_$timestamp.log" -ForegroundColor Gray
} else {
    Write-Host "  • Status: DISABLED" -ForegroundColor Yellow
    if (-not $EMAIL_CONFIG.Enabled) {
        Write-Host "  • Reason: Email is disabled in configuration" -ForegroundColor Yellow
    }
    if (-not $MONITOR_CONFIG.MonitorEnabled) {
        Write-Host "  • Reason: Monitor is disabled in configuration" -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "COMPLETION FILE STATUS:" -ForegroundColor White
Write-Host "  • Found: $(if ($Global:ProcessState.CompletionFileFound) { 'YES ✓' } else { 'NO ✗' })" -ForegroundColor $(if ($Global:ProcessState.CompletionFileFound) { "Green" } else { "Yellow" })
Write-Host "  • Path: $(if ($Global:ProcessState.CompletionFilePath) { $Global:ProcessState.CompletionFilePath } else { 'Not found' })" -ForegroundColor Gray
Write-Host ""
Write-Host "NOTES:" -ForegroundColor White
Write-Host "  1. Main process has completed" -ForegroundColor Gray
Write-Host "  2. Independent monitor will continue running separately" -ForegroundColor Gray
Write-Host "  3. Monitor will send email when completion file is found" -ForegroundColor Gray
Write-Host "  4. Monitor will stop automatically after sending email" -ForegroundColor Gray
Write-Host "="*60

# Exit with process exit code
$exitCode = if ($Global:ProcessState.ExitCode -ne $null) { $Global:ProcessState.ExitCode } else { 1 }
exit $exitCode
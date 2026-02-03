<#
.SYNOPSIS
Time-based process monitor for Face Recognition pipeline.

.DESCRIPTION
Runs in background and manages the face recognition worker process based on schedule.
When start time is reached, launches secondScript.ps1. When end time is reached,
stops worker and validates output folder structure.

.NOTES
Configured for D:\RaihanFarid\Dokumen\faceRecog\process-run output structure
#>

    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
# Configuration for face recognition pipeline
$Config = @{
    # Worker script path
    WorkerScript = "D:\RaihanFarid\Dokumen\exp-magick\maskDetect.ps1"


    
    # Schedule (24-hour format)
    StartTime = "15:22"    # 3:08 PM
    EndTime = "15:25"      # 3:15 PM
    
    # Paths for validation
    RunsBasePath = "D:\RaihanFarid\Dokumen\faceRecog\process-run"
    OutputFolderPattern = "Magick_Process_MaskDetect_"
    
    # Expected folder structure
    ExpectedSubfolders = @("logs", "script_output")
    ExpectedFiles = @("metadata.json")
    
    # Validation settings
    MaxValidationRetries = 5
    RetryDelaySeconds = 10
    
    # Process monitoring
    ProcessCheckInterval = 30  # seconds
    GracefulShutdownTimeout = 60  # seconds
    
    # Worker monitoring
    WorkerStartDelay = 10  # Wait for worker to fully start
    WorkerCooldownTime = 300  # 5 minutes cooldown after worker completes
    
    # Logging
    LogFile = "D:\RaihanFarid\Dokumen\faceRecog\monitor_$timestamp.log"
    
    # Email notifications (optional)
    NotifyOnCompletion = $false
    EmailTo = "user@example.com"
    EmailFrom = "monitor@system.com"
    SmtpServer = "smtp.example.com"
}

# Global variables
$WorkerProcess = $null
$WorkerPID = $null
$WorkerStartTime = $null
$WorkerLastStartTime = $null
$WorkerCooldownUntil = $null
$ScriptStartTime = Get-Date
$LastValidation = $null
$CurrentRunFolder = $null
$WorkerIsRunning = $false

# Functions
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    
    # Write to log file
    try {
        Add-Content -Path $Config.LogFile -Value $logEntry -ErrorAction SilentlyContinue
    } catch {
        # If log file is locked, write to console only
        Write-Host "Log file write failed: $_" -ForegroundColor Yellow
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

function Start-WorkerProcess {
    # Check if we're in cooldown period
    if ($WorkerCooldownUntil -and (Get-Date) -lt $WorkerCooldownUntil) {
        $cooldownLeft = [math]::Round(($WorkerCooldownUntil - (Get-Date)).TotalMinutes, 1)
        Write-Log "In cooldown period. $cooldownLeft minutes remaining before next start attempt." -Level "WARN"
        return $null
    }
    
    # Check if we have a recent PID that might still be running
    if ($WorkerPID -and $WorkerPID -ne 0) {
        try {
            $process = Get-Process -Id $WorkerPID -ErrorAction Stop
            if ($process -and (-not $process.HasExited)) {
                Write-Log "Worker process already running (PID: $WorkerPID)" -Level "WARN"
                $WorkerIsRunning = $true
                return $process
            }
        } catch {
            # Process doesn't exist, continue to start new one
            Write-Log "Previous worker process (PID: $WorkerPID) no longer exists" -Level "DEBUG"
        }
    }
    
    try {
        Write-Log "Starting face recognition worker process..." -Level "INFO"
        
        # Prepare arguments
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
            $WorkerPID = $WorkerProcess.Id
            $WorkerStartTime = Get-Date
            $WorkerLastStartTime = $WorkerStartTime
            $WorkerIsRunning = $true
            
            Write-Log "Worker process started successfully (PID: $WorkerPID)" -Level "SUCCESS"
            
            # Give the worker some time to initialize
            Write-Log "Waiting $($Config.WorkerStartDelay) seconds for worker to initialize..." -Level "DEBUG"
            Start-Sleep -Seconds $Config.WorkerStartDelay
            
            # Check if process is still running
            try {
                $checkProcess = Get-Process -Id $WorkerPID -ErrorAction Stop
                if (-not $checkProcess.HasExited) {
                    Write-Log "Worker process confirmed running" -Level "SUCCESS"
                    return $WorkerProcess
                } else {
                    Write-Log "Worker process exited during initialization" -Level "WARN"
                    $WorkerIsRunning = $false
                    return $null
                }
            } catch {
                Write-Log "Worker process PID not found after start" -Level "WARN"
                $WorkerIsRunning = $false
                return $null
            }
        } else {
            Write-Log "Failed to start worker process" -Level "ERROR"
            $WorkerIsRunning = $false
            return $null
        }
    }
    catch {
        Write-Log "ERROR: Failed to start worker process: $_" -Level "ERROR"
        $WorkerIsRunning = $false
        return $null
    }
}

function Stop-WorkerProcess {
    $wasRunning = $false
    
    if ($WorkerPID -and $WorkerPID -ne 0) {
        $wasRunning = $true
        Write-Log "Stopping worker process (PID: $WorkerPID)..." -Level "INFO"
        
        try {
            $process = Get-Process -Id $WorkerPID -ErrorAction Stop
            
            # Try graceful shutdown first
            if (-not $process.HasExited) {
                $process.CloseMainWindow() | Out-Null
                Start-Sleep -Seconds 2
                
                # If still running, kill it
                if (-not $process.HasExited) {
                    Write-Log "Forcefully terminating worker process..." -Level "WARN"
                    $process.Kill()
                    if ($process.WaitForExit($Config.GracefulShutdownTimeout * 1000)) {
                        Write-Log "Worker process terminated" -Level "SUCCESS"
                    } else {
                        Write-Log "Worker process did not terminate in timeout" -Level "ERROR"
                    }
                } else {
                    Write-Log "Worker process exited gracefully" -Level "SUCCESS"
                }
            } else {
                Write-Log "Worker process already exited" -Level "INFO"
            }
        }
        catch [System.ComponentModel.Win32Exception] {
            Write-Log "Access denied when trying to stop process (PID: $WorkerPID)" -Level "WARN"
        }
        catch [System.ArgumentException] {
            Write-Log "Process (PID: $WorkerPID) no longer exists" -Level "DEBUG"
        }
        catch {
            Write-Log "Error stopping process: $_" -Level "ERROR"
        }
    }
    
    # Clean up variables
    $WorkerProcess = $null
    $WorkerPID = $null
    $WorkerIsRunning = $false
    
    # Set cooldown period to prevent immediate restarts
    if ($wasRunning) {
        $WorkerCooldownUntil = (Get-Date).AddSeconds($Config.WorkerCooldownTime)
        Write-Log "Cooldown period set for $($Config.WorkerCooldownTime) seconds" -Level "DEBUG"
    }
}

function Is-WorkerRunning {
    if (-not $WorkerPID -or $WorkerPID -eq 0) {
        return $false
    }
    
    try {
        $process = Get-Process -Id $WorkerPID -ErrorAction Stop
        return (-not $process.HasExited)
    } catch {
        return $false
    }
}

function Find-LatestRunFolder {
    try {
        if (-not (Test-Path $Config.RunsBasePath)) {
            Write-Log "Runs base path does not exist: $($Config.RunsBasePath)" -Level "ERROR"
            return $null
        }
        
        # Find all folders matching the pattern
        $folders = Get-ChildItem -Path $Config.RunsBasePath -Directory -Filter $Config.OutputFolderPattern -ErrorAction SilentlyContinue
        
        if (-not $folders) {
            Write-Log "No matching run folders found" -Level "DEBUG"
            return $null
        }
        
        # If we have a worker start time, prefer folders created after that
        if ($WorkerLastStartTime) {
            $recentFolders = $folders | Where-Object { $_.CreationTime -ge $WorkerLastStartTime } | Sort-Object CreationTime -Descending
            if ($recentFolders) {
                $latestFolder = $recentFolders[0]
                Write-Log "Found recent run folder: $($latestFolder.Name) created at $($latestFolder.CreationTime)" -Level "DEBUG"
                return $latestFolder
            }
        }
        
        # Otherwise get the most recent folder
        $latestFolder = $folders | Sort-Object CreationTime -Descending | Select-Object -First 1
        Write-Log "Found latest run folder: $($latestFolder.Name) created at $($latestFolder.CreationTime)" -Level "DEBUG"
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
        Details = @{}
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
                }
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
            Write-Log "Total folder size: $sizeMB MB" -Level "DEBUG"
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

function Get-ProcessStatus {
    $status = @{
        MonitorRunning = $true
        WorkerRunning = $false
        CurrentTime = Get-Date -Format "HH:mm:ss"
        CurrentDate = Get-Date -Format "yyyy-MM-dd"
        Schedule = @{
            StartTime = $Config.StartTime
            EndTime = $Config.EndTime
            InWindow = $false
        }
        WorkerInfo = @{}
        LastValidation = $LastValidation
        WorkerCooldown = $false
    }
    
    # Check if worker is running
    $status.WorkerRunning = $WorkerIsRunning -or (Is-WorkerRunning)
    
    if ($status.WorkerRunning) {
        $status.WorkerInfo = @{
            PID = $WorkerPID
            StartTime = if ($WorkerStartTime) { $WorkerStartTime.ToString("HH:mm:ss") } else { "Unknown" }
            Runtime = if ($WorkerStartTime) { [math]::Round((Get-Date - $WorkerStartTime).TotalMinutes, 1) } else { 0 }
        }
    }
    
    # Check time window
    $startPassed = Test-TimeWindow -TargetTime $Config.StartTime
    $endPassed = Test-TimeWindow -TargetTime $Config.EndTime
    $status.Schedule.InWindow = ($startPassed -and !$endPassed)
    $status.Schedule.StartPassed = $startPassed
    $status.Schedule.EndPassed = $endPassed
    
    # Check cooldown
    if ($WorkerCooldownUntil -and (Get-Date) -lt $WorkerCooldownUntil) {
        $status.WorkerCooldown = $true
        $status.CooldownRemaining = [math]::Round(($WorkerCooldownUntil - (Get-Date)).TotalMinutes, 1)
    }
    
    return $status
}

function Send-Notification {
    param(
        [string]$Subject,
        [string]$Body
    )
    
    if (-not $Config.NotifyOnCompletion) {
        return
    }
    
    try {
        Send-MailMessage -To $Config.EmailTo `
                        -From $Config.EmailFrom `
                        -Subject $Subject `
                        -Body $Body `
                        -SmtpServer $Config.SmtpServer
        Write-Log "Notification email sent" -Level "SUCCESS"
    } catch {
        Write-Log "Failed to send notification: $_" -Level "ERROR"
    }
}

function Show-StatusBanner {
    $status = Get-ProcessStatus
    
    # Only show banner every 30 seconds to avoid flickering
    $currentSecond = (Get-Date).Second
    if ($currentSecond % 30 -ne 0) {
        return
    }
    
    Clear-Host
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "    FACE RECOGNITION PROCESS MONITOR" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Current Time: $($status.CurrentTime)" -ForegroundColor Yellow
    Write-Host "Schedule: $($Config.StartTime) - $($Config.EndTime)" -ForegroundColor Yellow
    Write-Host "Status: $(if ($status.Schedule.InWindow) { 'ACTIVE WINDOW' } else { 'OUTSIDE WINDOW' })" `
                -ForegroundColor $(if ($status.Schedule.InWindow) { 'Green' } else { 'Gray' })
    Write-Host ""
    
    if ($status.WorkerRunning) {
        Write-Host "WORKER STATUS: RUNNING" -ForegroundColor Green
        Write-Host "  PID: $($status.WorkerInfo.PID)" -ForegroundColor White
        Write-Host "  Started: $($status.WorkerInfo.StartTime)" -ForegroundColor White
        Write-Host "  Runtime: $($status.WorkerInfo.Runtime) minutes" -ForegroundColor White
    } else {
        Write-Host "WORKER STATUS: STOPPED" -ForegroundColor Red
    }
    
    if ($status.WorkerCooldown) {
        Write-Host ""
        Write-Host "COOLDOWN ACTIVE: $($status.CooldownRemaining) minutes remaining" -ForegroundColor Yellow
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

# Main execution
try {
    # Create log directory if it doesn't exist
    $logDir = Split-Path $Config.LogFile -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    
    Write-Log "=== Face Recognition Monitor Started ===" -Level "INFO"
    Write-Log "Start Time: $($Config.StartTime)" -Level "INFO"
    Write-Log "End Time: $($Config.EndTime)" -Level "INFO"
    Write-Log "Worker Script: $($Config.WorkerScript)" -Level "INFO"
    Write-Log "Runs Base Path: $($Config.RunsBasePath)" -Level "INFO"
    Write-Log "Worker Start Delay: $($Config.WorkerStartDelay) seconds" -Level "INFO"
    
    # Ensure runs base path exists
    if (-not (Test-Path $Config.RunsBasePath)) {
        Write-Log "Creating runs base directory: $($Config.RunsBasePath)" -Level "WARN"
        New-Item -ItemType Directory -Path $Config.RunsBasePath -Force | Out-Null
    }
    
    # Clear console and show initial status
    Clear-Host
    
    # Main monitoring loop
    $lastStatusCheck = $null
    while ($true) {
        $status = Get-ProcessStatus
        $currentTime = Get-Date -Format "HH:mm"
        
        # Show status banner periodically
        Show-StatusBanner
        
        # Log status changes
        if ($lastStatusCheck -ne $status.WorkerRunning) {
            Write-Log "Worker status changed: $(if ($status.WorkerRunning) {'Running'} else {'Stopped'})" -Level "INFO"
            $lastStatusCheck = $status.WorkerRunning
        }
        
        Write-Log "Check: $currentTime | Worker: $(if ($status.WorkerRunning) {'Running'} else {'Stopped'}) | Window: $(if ($status.Schedule.InWindow) {'Active'} else {'Inactive'})" -Level "DEBUG"
        
        # Check if we should start worker
        if ($status.Schedule.InWindow -and !$status.WorkerRunning -and !$status.WorkerCooldown) {
            Write-Log "Time window active - starting face recognition worker..." -Level "INFO"
            $WorkerProcess = Start-WorkerProcess
            
            if ($WorkerProcess) {
                Write-Log "Worker started successfully. Monitoring progress..." -Level "SUCCESS"
                
                # Send notification
                $body = @"
Face Recognition Worker Started
Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
PID: $WorkerPID
Schedule Window: $($Config.StartTime) - $($Config.EndTime)
"@
                Send-Notification -Subject "[FaceRecog] Worker Started" -Body $body
            } else {
                Write-Log "Worker failed to start or exited immediately" -Level "WARN"
            }
        }
        # Check if we should stop worker
        elseif ($status.Schedule.EndPassed -and $status.WorkerRunning) {
            Write-Log "End time reached - stopping face recognition worker..." -Level "INFO"
            Stop-WorkerProcess
            
            # Wait a moment for cleanup
            Start-Sleep -Seconds 5
            
            # Validate output
            Write-Log "Validating worker output..." -Level "INFO"
            $LastValidation = Validate-Output
            
            if ($LastValidation.Success) {
                Write-Log "Face recognition pipeline completed successfully!" -Level "SUCCESS"
                
                # Send success notification
                $body = @"
Face Recognition Pipeline Completed Successfully
Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run Folder: $(Split-Path $LastValidation.RunFolder -Leaf)
Folder Size: $($LastValidation.Details.TotalSizeMB) MB
Schedule: $($Config.StartTime) - $($Config.EndTime)
"@
                Send-Notification -Subject "[FaceRecog] Pipeline Success" -Body $body
            } else {
                Write-Log "Pipeline completed with validation issues" -Level "WARN"
                
                # Send warning notification
                $body = @"
Face Recognition Pipeline Completed with Issues
Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Issues: $($LastValidation.Error)
Missing Items: $($LastValidation.MissingItems -join ', ')
Schedule: $($Config.StartTime) - $($Config.EndTime)
"@
                Send-Notification -Subject "[FaceRecog] Pipeline Issues" -Body $body
            }
        }
        
        # Check if worker process unexpectedly died (but only if we think it should be running)
        if ($status.WorkerRunning -and $status.Schedule.InWindow) {
            $actuallyRunning = Is-WorkerRunning
            if (-not $actuallyRunning) {
                Write-Log "Worker process died unexpectedly!" -Level "ERROR"
                $WorkerIsRunning = $false
                
                # Don't try to restart immediately - set cooldown
                $WorkerCooldownUntil = (Get-Date).AddSeconds($Config.WorkerCooldownTime)
                Write-Log "Setting cooldown for $($Config.WorkerCooldownTime) seconds" -Level "WARN"
            }
        }
        
        # Wait before next check
        Start-Sleep -Seconds $Config.ProcessCheckInterval
    }
}
catch [System.Management.Automation.Host.HostException] {
    # Ctrl+C was pressed
    Write-Log "Monitor interrupted by user" -Level "INFO"
}
catch {
    Write-Log "FATAL ERROR: $_" -Level "ERROR"
    Write-Log $_.ScriptStackTrace -Level "ERROR"
}
finally {
    # Cleanup on exit
    Write-Log "Cleaning up..." -Level "INFO"
    Stop-WorkerProcess
    
    Write-Log "=== Face Recognition Monitor Stopped ===" -Level "INFO"
    Write-Host "Monitor stopped. Log file: $($Config.LogFile)" -ForegroundColor Yellow
}
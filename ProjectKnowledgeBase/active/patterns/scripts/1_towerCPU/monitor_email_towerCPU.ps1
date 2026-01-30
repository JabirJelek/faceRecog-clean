

<#
.SYNOPSIS
Time-based process monitor for Face Recognition pipeline with proper PID tracking.

.DESCRIPTION
Runs in background and manages the face recognition worker process based on schedule.
Tracks the actual Python process spawned by the worker script.

.NOTES
Configured for D:\RaihanFarid\Dokumen\faceRecog\process-run output structure
#>

# Configuration for face recognition pipeline
$Config = @{
    # Worker script path
    WorkerScript = "D:\RaihanFarid\Dokumen\exp-magick\maskDetect.ps1"
    
    # Schedule (24-hour format)
    StartTime = "16:02"    # 3:08 PM
    EndTime = "16:04"      # 3:15 PM
    
    # Paths for validation
    RunsBasePath = "D:\RaihanFarid\Dokumen\faceRecog\process-run"
    OutputFolderPattern = "Magick_Process_MaskDetect_*"
    
    # Process tracking
    PythonProcessName = "python"  # The actual process we want to track
    WorkerProcessName = "powershell"  # PowerShell wrapper process
    PythonScriptPath = "D:\RaihanFarid\Dokumen\faceRecog\run_py\modular\entry_multi-USED-Magick.py"
    
    # Expected folder structure
    ExpectedSubfolders = @("logs", "script_output")
    ExpectedFiles = @("metadata.json")
    
    # Validation settings
    MaxValidationRetries = 5
    RetryDelaySeconds = 10
    
    # Process monitoring
    ProcessCheckInterval = 10  # seconds (reduced for better tracking)
    GracefulShutdownTimeout = 60  # seconds
    
    # PID tracking
    PIDFilePath = "D:\RaihanFarid\Dokumen\faceRecog\monitor_pid.json"
    MaxPIDFileAgeMinutes = 120  # Clean up old PID files
    
    # Logging
    LogFile = "D:\RaihanFarid\Dokumen\faceRecog\monitor.log"

    
    # Email notifications for successful process COMPLETION
    SendEmailOnCompletion = $true
    
    # Recipients with language preferences
    EmailRecipients = @(
        @{
            Address = "faridraihan17@gmail.com"
            Language = "English"  # English
        },
        @{
            Address = "ikeepmypromiz@gmail.com"
            Language = "Bahasa"  # Indonesian
        }
        # @{ 
        #     Address = "itdiv@sinarcemaramasabadi.co.id" # Only un-comment this when the code is in production, because
        #                                                 # this is formal IT email.
        #     Language = "Bahasa"  # Indonesian
        # }
    )
    
    # Email sender configuration
    EmailFrom = "faridraihan17@gmail.com"  # Should match your Gmail address
    EmailSubject = @{
        English = "Face Recognition Process Completed Successfully"
        Bahasa = "Proses Pengenalan Wajah Selesai dengan Sukses"
    }
    
    # SMTP Configuration
    SmtpServer = "smtp.gmail.com"
    SmtpPort = 587
    UseSSL = $true
    EmailCredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
}

# Global variables
$WorkerProcess = $null
$WorkerPID = $null
$PythonPID = $null
$WorkerStartTime = $null
$PythonStartTime = $null
$LastValidation = $null
$CurrentRunFolder = $null
$WorkerIsRunning = $false
$PythonIsRunning = $false
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
# PID tracking structure
$PIDTracking = @{
    WorkerPID = $null
    PythonPID = $null
    WorkerStartTime = $null
    PythonStartTime = $null
    RunFolder = $null
    LastUpdate = $null
}



# Functions
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    
    try {
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

function Send-CompletionEmail {
    param(
        [string]$RunFolder,
        [object]$ValidationResult
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
        
        # Find and prepare attachments (same as before)
        $attachments = @()
        $completionSummaryPath = Join-Path $RunFolder "logs\completion_summary.txt"
        if (Test-Path $completionSummaryPath) {
            $attachments += $completionSummaryPath
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
            
            try {
                # Prepare email parameters
                $mailParams = @{
                    To          = $recipients  # Send to all recipients of this language at once
                    From        = $Config.EmailFrom
                    Subject     = $emailContent.Subject
                    Body        = $emailContent.Body
                    SmtpServer  = $Config.SmtpServer
                    Port        = $Config.SmtpPort
                    UseSsl      = $Config.UseSSL
                    Credential  = $credential
                    ErrorAction = 'Stop'
                }
                
                # Add attachments if we have any
                if ($attachments.Count -gt 0) {
                    $mailParams.Attachments = $attachments
                }
                
                # Send the email
                Send-MailMessage @mailParams
                
                Write-Log "Successfully sent $language email to $($recipients.Count) recipient(s)" -Level "SUCCESS"
                $successCount += $recipients.Count
                
            } catch {
                Write-Log "Failed to send $language email to $($recipients.Count) recipient(s): $($_.Exception.Message)" -Level "ERROR"
                $failCount += $recipients.Count
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
    
    $now = Get-Date
    try {
        $target = [DateTime]::ParseExact($TargetTime, "HH:mm", $null)
        return ($now.TimeOfDay -ge $target.TimeOfDay)
    } catch {
        Write-Log "Invalid time format: $TargetTime" -Level "ERROR"
        return $false
    }
}

function Save-PIDTracking {
    $PIDTracking.WorkerPID = $WorkerPID
    $PIDTracking.PythonPID = $PythonPID
    $PIDTracking.WorkerStartTime = if ($WorkerStartTime) { $WorkerStartTime.ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
    $PIDTracking.PythonStartTime = if ($PythonStartTime) { $PythonStartTime.ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
    $PIDTracking.RunFolder = $CurrentRunFolder
    $PIDTracking.LastUpdate = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    
    try {
        $PIDTracking | ConvertTo-Json | Out-File -FilePath $Config.PIDFilePath -Force
        Write-Log "PID tracking saved: WorkerPID=$WorkerPID, PythonPID=$PythonPID" -Level "DEBUG"
    } catch {
        Write-Log "Failed to save PID tracking: $_" -Level "ERROR"
    }
}

function Load-PIDTracking {
    if (-not (Test-Path $Config.PIDFilePath)) {
        Write-Log "No PID tracking file found" -Level "DEBUG"
        return $false
    }
    
    try {
        $loaded = Get-Content -Path $Config.PIDFilePath -Raw | ConvertFrom-Json
        
        # Check if PID file is too old
        $lastUpdate = [DateTime]::ParseExact($loaded.LastUpdate, "yyyy-MM-dd HH:mm:ss", $null)
        $ageMinutes = ((Get-Date) - $lastUpdate).TotalMinutes
        
        if ($ageMinutes -gt $Config.MaxPIDFileAgeMinutes) {
            Write-Log "PID file is too old ($ageMinutes minutes), cleaning up" -Level "WARN"
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            return $false
        }
        
        # Check if processes are still running
        $workerAlive = $false
        $pythonAlive = $false
        
        if ($loaded.WorkerPID -and $loaded.WorkerPID -ne 0) {
            try {
                $workerProcess = Get-Process -Id $loaded.WorkerPID -ErrorAction Stop
                $workerAlive = (-not $workerProcess.HasExited)
            } catch { }
        }
        
        if ($loaded.PythonPID -and $loaded.PythonPID -ne 0) {
            try {
                $pythonProcess = Get-Process -Id $loaded.PythonPID -ErrorAction Stop
                $pythonAlive = (-not $pythonProcess.HasExited)
            } catch { }
        }
        
        if ($workerAlive -or $pythonAlive) {
            $global:WorkerPID = $loaded.WorkerPID
            $global:PythonPID = $loaded.PythonPID
            
            if ($loaded.WorkerStartTime) {
                $global:WorkerStartTime = [DateTime]::ParseExact($loaded.WorkerStartTime, "yyyy-MM-dd HH:mm:ss", $null)
            }
            
            if ($loaded.PythonStartTime) {
                $global:PythonStartTime = [DateTime]::ParseExact($loaded.PythonStartTime, "yyyy-MM-dd HH:mm:ss", $null)
            }
            
            $global:CurrentRunFolder = $loaded.RunFolder
            
            Write-Log "Loaded PID tracking: WorkerPID=$WorkerPID (Alive: $workerAlive), PythonPID=$PythonPID (Alive: $pythonAlive)" -Level "INFO"
            return $true
        } else {
            Write-Log "Loaded PIDs are no longer running, cleaning up" -Level "INFO"
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            return $false
        }
    } catch {
        Write-Log "Failed to load PID tracking: $_" -Level "ERROR"
        Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        return $false
    }
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

function Start-WorkerProcess {
    # Check if we already have a running Python process
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
        [int]$ProcessId,  # Changed from $PID to $ProcessId
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
        $status.WorkerRunning = Is-ProcessRunning -ProcessId $WorkerPID -ProcessName $Config.WorkerProcessName  # Updated
    }
    
    # Check Python process
    if ($PythonPID -and $PythonPID -ne 0) {
        $status.PythonRunning = Is-ProcessRunning -ProcessId $PythonPID -ProcessName $Config.PythonProcessName  # Updated
    }
    
    # If we think Python is running but PID is null, try to find it
    if ((-not $status.PythonRunning) -and $WorkerIsRunning) {
        $foundPID = Find-PythonProcess
        if ($foundPID) {
            $global:PythonPID = $foundPID
            $status.PythonPID = $foundPID
            $status.PythonRunning = Is-ProcessRunning -ProcessId $foundPID -ProcessName $Config.PythonProcessName  # Updated
            Save-PIDTracking
        }
    }
    
    # Update global state
    $global:WorkerIsRunning = $status.WorkerRunning
    $global:PythonIsRunning = $status.PythonRunning
    
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
LAPORAN PENYELESAIAN PROSES PENGENALAN WAJAH
============================================

RINGKASAN PROSES
----------------
Waktu Penyelesaian: $currentTime
Folder Proses: $runFolderName
Status Validasi: $(if ($ValidationResult.Success) {'BERHASIL'} else {'GAGAL'})

$(if ($metadataContent) {
"ID Proses: $($metadataContent.run_id)
Waktu Mulai: $($metadataContent.start_time)
Kode Keluar: $($metadataContent.exit_code)"
})

HASIL VALIDASI
--------------
Folder Dibuat: $($ValidationResult.CreationTime)
Ukuran Folder: $(if ($ValidationResult.Details.TotalSizeMB) {"$($ValidationResult.Details.TotalSizeMB) MB"} else {"Tidak Diketahui"})

Struktur Folder:
- Subfolder: $($Config.ExpectedSubfolders.Count - $ValidationResult.MissingItems.Count)/$($Config.ExpectedSubfolders.Count)
- File: $($Config.ExpectedFiles.Count - $ValidationResult.MissingItems.Count)/$($Config.ExpectedFiles.Count)
- File Log: $($ValidationResult.Details.LogFiles.Count)
- Item Output: $($ValidationResult.Details.ScriptOutput.ItemCount)

FILE LAMPIRAN
-------------
$(if ($Attachments.Count -gt 0) {
    $attachments | ForEach-Object { "- $(Split-Path $_ -Leaf)" } | Join-String -Separator "`n"
} else {
    "Tidak ada file terlampir"
})

INFORMASI SISTEM
----------------
Instans Monitor: $($env:COMPUTERNAME)
Path Dasar: $($Config.RunsBasePath)
Jadwal: $($Config.StartTime) - $($Config.EndTime)
Skrip Python: $($Config.PythonScriptPath)

FILE LOG MONITOR
----------------
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
FACE RECOGNITION PROCESS COMPLETION REPORT
===========================================

PROCESS SUMMARY
---------------
Completion Time: $currentTime
Run Folder: $runFolderName
Validation Status: $(if ($ValidationResult.Success) {'SUCCESS'} else {'FAILED'})

$(if ($metadataContent) {
"Run ID: $($metadataContent.run_id)
Start Time: $($metadataContent.start_time)
Exit Code: $($metadataContent.exit_code)"
})

VALIDATION RESULTS
------------------
Folder Created: $($ValidationResult.CreationTime)
Folder Size: $(if ($ValidationResult.Details.TotalSizeMB) {"$($ValidationResult.Details.TotalSizeMB) MB"} else {"Unknown"})

Folder Structure:
- Subfolders: $($Config.ExpectedSubfolders.Count - $ValidationResult.MissingItems.Count)/$($Config.ExpectedSubfolders.Count)
- Files: $($Config.ExpectedFiles.Count - $ValidationResult.MissingItems.Count)/$($Config.ExpectedFiles.Count)
- Log Files: $($ValidationResult.Details.LogFiles.Count)
- Output Items: $($ValidationResult.Details.ScriptOutput.ItemCount)

ATTACHED FILES
--------------
$(if ($Attachments.Count -gt 0) {
    $attachments | ForEach-Object { "- $(Split-Path $_ -Leaf)" } | Join-String -Separator "`n"
} else {
    "No files attached"
})

SYSTEM INFORMATION
------------------
Monitor Instance: $($env:COMPUTERNAME)
Base Path: $($Config.RunsBasePath)
Schedule: $($Config.StartTime) - $($Config.EndTime)
Python Script: $($Config.PythonScriptPath)

MONITOR LOG
-----------
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

# Function to validate email addresses
function Test-EmailAddress {
    param([string]$Email)
    
    try {
        $mailAddress = New-Object System.Net.Mail.MailAddress $Email
        return $mailAddress.Address -eq $Email
    } catch {
        return $false
    }
}

# Function to backup original configuration if needed
function Backup-OriginalConfig {
    $backupPath = Join-Path (Split-Path $Config.LogFile -Parent) "config_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    $Config | ConvertTo-Json -Depth 10 | Out-File -FilePath $backupPath -Force
    Write-Log "Configuration backed up to: $backupPath" -Level "DEBUG"
}

function Test-EmailConfiguration {
    if (-not $Config.SendEmailOnCompletion) {
        Write-Log "Email notifications on completion are disabled" -Level "INFO"
        return $false
    }
    
    Write-Log "Testing email configuration..." -Level "INFO"
    
    $checksPassed = $true
    
    if ([string]::IsNullOrWhiteSpace($Config.SmtpServer)) {
        Write-Log "ERROR: SMTP server not configured" -Level "ERROR"
        $checksPassed = $false
    }
    
    if ($null -eq $Config.EmailRecipients -or $Config.EmailRecipients.Count -eq 0) {
        Write-Log "ERROR: No email recipients configured" -Level "ERROR"
        $checksPassed = $false
    } else {
        Write-Log "Found $($Config.EmailRecipients.Count) email recipient(s)" -Level "SUCCESS"
        
        # Check languages
        $languages = $Config.EmailRecipients | ForEach-Object { $_.Language } | Sort-Object -Unique
        Write-Log "Configured languages: $($languages -join ', ')" -Level "INFO"
        
        # Validate each recipient
        foreach ($recipient in $Config.EmailRecipients) {
            if ([string]::IsNullOrWhiteSpace($recipient.Address)) {
                Write-Log "ERROR: Recipient has empty email address" -Level "ERROR"
                $checksPassed = $false
            }
            
            if ([string]::IsNullOrWhiteSpace($recipient.Language)) {
                Write-Log "WARNING: Recipient $($recipient.Address) has no language specified, defaulting to English" -Level "WARN"
                $recipient.Language = "English"
            }
        }
    }
    
    # Test if credential file exists
    if (Test-Path $Config.EmailCredentialPath) {
        try {
            $credential = Import-Clixml -Path $Config.EmailCredentialPath
            Write-Log "Email credential file found and loaded successfully" -Level "SUCCESS"
            
            # Test credential
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
            
        } catch {
            Write-Log "ERROR: Failed to load email credential: $_" -Level "ERROR"
            $checksPassed = $false
        }
    } else {
        Write-Log "ERROR: Email credential file not found at $($Config.EmailCredentialPath)" -Level "ERROR"
        $checksPassed = $false
    }
    
    # Gmail-specific warnings
    if ($Config.SmtpServer -like "*gmail*") {
        Write-Log "GMAIL CONFIGURATION NOTES:" -Level "INFO"
        Write-Log "- Using SMTP: $($Config.SmtpServer):$($Config.SmtpPort)" -Level "INFO"
        Write-Log "- SSL Enabled: $($Config.UseSSL)" -Level "INFO"
        Write-Log "- Make sure you're using an App Password, not your regular password" -Level "INFO"
        Write-Log "- Gmail attachment limit: 25 MB total" -Level "INFO"
    }
    
    if ($checksPassed) {
        Write-Log "Email configuration valid" -Level "SUCCESS"
        return $true
    } else {
        Write-Log "Email configuration invalid. Emails will not be sent." -Level "ERROR"
        return $false
    }
}



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
    
    if ($status.PythonRunning) {
        Write-Host "PYTHON STATUS: RUNNING" -ForegroundColor Green
        Write-Host "  PID: $PythonPID" -ForegroundColor White
        if ($PythonStartTime) {
            $runtime = [math]::Round((Get-Date - $PythonStartTime).TotalMinutes, 1)
            Write-Host "  Runtime: $runtime minutes" -ForegroundColor White
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
    Write-Log "Python Script: $($Config.PythonScriptPath)" -Level "INFO"
    
    # Test email configuration ONCE at startup
    $EmailConfigValid = Test-EmailConfiguration
    
    # Load existing PID tracking
    if (Load-PIDTracking) {
        Write-Log "Resumed monitoring of existing processes" -Level "SUCCESS"
        # Update process status
        Check-ProcessStatus | Out-Null
    }
    
    # Ensure runs base path exists
    if (-not (Test-Path $Config.RunsBasePath)) {
        Write-Log "Creating runs base directory: $($Config.RunsBasePath)" -Level "WARN"
        New-Item -ItemType Directory -Path $Config.RunsBasePath -Force | Out-Null
    }
    
    # Clear console and show initial status
    Clear-Host
    
    # Main monitoring loop
    while ($true) {
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
            Write-Log "Time window active and no Python process running - starting worker..." -Level "INFO"
            $started = Start-WorkerProcess
            
            if ($started) {
                Write-Log "Worker started. Monitoring Python process..." -Level "SUCCESS"
                # Re-check process status
                $processStatus = Check-ProcessStatus
            }
        }
        
                
        # In the main loop, update the email section:
        elseif ($endPassed -and $processStatus.PythonRunning) {
            Write-Log "End time reached - stopping processes..." -Level "INFO"
            Stop-WorkerProcess
            
            # Wait for cleanup
            Start-Sleep -Seconds 5
            
            # Validate output
            Write-Log "Validating worker output..." -Level "INFO"
            $LastValidation = Validate-Output
            
            # Send completion email if validation was successful
            if ($LastValidation -and $LastValidation.Success) {
                if ($Config.SendEmailOnCompletion -and $EmailConfigValid) {
                    # Backup original config before sending
                    Backup-OriginalConfig
                    
                    $emailSent = Send-CompletionEmail -RunFolder $LastValidation.RunFolder -ValidationResult $LastValidation
                    if ($emailSent) {
                        Write-Log "Completion emails sent successfully." -Level "SUCCESS"
                    } else {
                        Write-Log "Failed to send some or all completion emails, but process completed successfully." -Level "WARN"
                    }
                } elseif ($Config.SendEmailOnCompletion -and -not $EmailConfigValid) {
                    Write-Log "Email configuration is invalid. Skipping email notification." -Level "WARN"
                }
                
                Write-Log "Face recognition pipeline completed successfully!" -Level "SUCCESS"
            } else {
                Write-Log "Pipeline completed with validation issues" -Level "WARN"
            }
            
            # Stop the monitor
            Write-Log "Process completed. Stopping monitor as configured..." -Level "INFO"
            break
        }
        
        # Save PID tracking periodically
        if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
            Save-PIDTracking
        }
        
        # Wait before next check
        Start-Sleep -Seconds $Config.ProcessCheckInterval
    }
}
catch [System.Management.Automation.Host.HostException] {
    Write-Log "Monitor interrupted by user" -Level "INFO"
}
catch {
    Write-Log "FATAL ERROR: $_" -Level "ERROR"
    Write-Log $_.ScriptStackTrace -Level "ERROR"
}
finally {
    Write-Log "Cleaning up..." -Level "INFO"
    Stop-WorkerProcess
    
    Write-Log "=== Face Recognition Monitor Stopped ===" -Level "INFO"
    Write-Host "Monitor stopped. Log file: $($Config.LogFile)" -ForegroundColor Yellow
}
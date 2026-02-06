
<#
.SYNOPSIS
Sets up portable paths for the project and validates all components exist
.DESCRIPTION
This SINGLE function does 3 things:
1. Finds the maskRecog project root
2. Builds all paths relative to it
3. Validates critical components exist
#>


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

function Backup-OriginalConfig {
    $backupDir = Join-Path (Split-Path $Config.LogFile -Parent) "backups"
    if (-not (Test-Path $backupDir)) {
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    }
    
    $backupPath = Join-Path $backupDir "config_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    $Config | ConvertTo-Json -Depth 10 | Out-File -FilePath $backupPath -Force
    Write-Log "Configuration backed up to: $backupPath" -Level "DEBUG"
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
            # You can use $sharedConfig.Paths.patterns, etc.
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
    # STEP 4: UPDATE CONFIGURATION WITH DATE-BASED PATHS
    # ====================================================================
    
    # Get email credential from user profile
    $emailCredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
    if (!(Test-Path (Split-Path $emailCredentialPath -Parent))) {
        New-Item -ItemType Directory -Path (Split-Path $emailCredentialPath -Parent) -Force | Out-Null
    }
    
    # Update the $Config object with date-based paths
    $Script:Config = @{
        # Schedule configuration (CRITICAL - was missing)
        StartTime = "08:00"  # Default start time
        EndTime = "09:48"    # Default end time
        
        # Worker script path - RELATIVE to project root
        WorkerScript = Join-Path $ProjectRoot "patterns\scripts\1_magick\maskDetect-exp.ps1"
        
        # Python script path - RELATIVE to project root  
        PythonScriptPath = Join-Path $ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
        
        # Paths for validation - USING DATE-BASED PATH
        RunsBasePath = $dateBasedPath  # Now points to date-specific folder
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
        ProcessCheckInterval = 15
        GracefulShutdownTimeout = 60
        
        # PID tracking - RELATIVE TO DATE-BASED PATH
        PIDFilePath = Join-Path $dateBasedPath "monitor_pid_Magick.json"
        MaxPIDFileAgeMinutes = 120
        
        # Logging - RELATIVE TO DATE-BASED PATH
        LogFile = Join-Path $dateBasedPath "monitor_Magick.log"
        
        # Email notifications (updated to use MailKit)
        SendEmailOnCompletion = $false # Toggle Email send
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
        
        # NEW: Date-based path tracking
        CurrentDate = $currentDate
        ActiveDatePath = $dateBasedPath
    }
    
    # ====================================================================
    # STEP 5: VALIDATE CRITICAL COMPONENTS EXIST
    # ====================================================================
    
    Write-Host "`nValidating project components..." -ForegroundColor Yellow
    
    $criticalComponents = @(
        @{ Name = "Worker Script"; Path = $Config.WorkerScript }
        @{ Name = "Python Script"; Path = $Config.PythonScriptPath }
        @{ Name = "Date-Based Log Directory"; Path = $dateBasedPath }
        @{ Name = "PID File Directory"; Path = $dateBasedPath }
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
    # STEP 6: SUMMARY AND ERROR HANDLING
    # ====================================================================
    
    if ($missingComponents.Count -gt 0) {
        Write-Host "`nERROR: Missing critical components!" -ForegroundColor Red
        foreach ($missing in $missingComponents) {
            Write-Host "  - $missing" -ForegroundColor Red
        }
        
        Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
        Write-Host "1. Ensure all scripts are in the correct locations" -ForegroundColor Yellow
        Write-Host "2. Check that the maskRecog project structure is intact" -ForegroundColor Yellow
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
    
    # ====================================================================
    # STEP 7: MODIFIED - Wait for key press with 60-second timeout
    # ====================================================================
    
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
    
    return $true
}



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

function Save-ResilienceState {
    <#
    .SYNOPSIS
    Saves the resilience state (collected folders, email queue, etc.)
    #>
    
    $resilienceData = @{
        EmailAttachmentQueue = $global:EmailAttachmentQueue
        CollectedRunFolders = $global:CollectedRunFolders
        ForceStopAttempts = $global:ForceStopAttempts
        LastForceStopTime = if ($global:LastForceStopTime) { 
            $global:LastForceStopTime.ToString("yyyy-MM-dd HH:mm:ss") 
        } else { 
            $null 
        }
        IsShuttingDown = $global:IsShuttingDown
        LastSaveTime = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }
    
    $resilienceFilePath = Join-Path (Split-Path $Config.LogFile -Parent) "resilience_state.json"
    
    try {
        $resilienceData | ConvertTo-Json -Depth 10 | Out-File -FilePath $resilienceFilePath -Force
        Write-Log "Resilience state saved to: $resilienceFilePath" -Level "DEBUG"
    } catch {
        Write-Log "Failed to save resilience state: $_" -Level "ERROR"
    }
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

function Load-ResilienceState {
    <#
    .SYNOPSIS
    Loads the resilience state if it exists
    #>
    
    $resilienceFilePath = Join-Path (Split-Path $Config.LogFile -Parent) "resilience_state.json"
    
    if (Test-Path $resilienceFilePath) {
        try {
            $loadedData = Get-Content -Path $resilienceFilePath -Raw | ConvertFrom-Json
            
            # Check if state is stale (older than 24 hours)
            $lastSaveTime = [DateTime]::ParseExact($loadedData.LastSaveTime, "yyyy-MM-dd HH:mm:ss", $null)
            $ageHours = ((Get-Date) - $lastSaveTime).TotalHours
            
            if ($ageHours -gt 24) {
                Write-Log "Resilience state is stale ($ageHours hours old), clearing" -Level "WARN"
                Remove-Item -Path $resilienceFilePath -Force -ErrorAction SilentlyContinue
                return $false
            }
            
            # Load the data
            $global:EmailAttachmentQueue = @($loadedData.EmailAttachmentQueue)
            $global:CollectedRunFolders = @($loadedData.CollectedRunFolders)
            $global:ForceStopAttempts = $loadedData.ForceStopAttempts
            $global:LastForceStopTime = if ($loadedData.LastForceStopTime) {
                [DateTime]::ParseExact($loadedData.LastForceStopTime, "yyyy-MM-dd HH:mm:ss", $null)
            } else {
                $null
            }
            $global:IsShuttingDown = $loadedData.IsShuttingDown
            
            Write-Log "Loaded resilience state with $($global:CollectedRunFolders.Count) collected folders" -Level "INFO"
            
            # Clean up old file
            Remove-Item -Path $resilienceFilePath -Force -ErrorAction SilentlyContinue
            
            return $true
        } catch {
            Write-Log "Failed to load resilience state: $_" -Level "ERROR"
            Remove-Item -Path $resilienceFilePath -Force -ErrorAction SilentlyContinue
            return $false
        }
    }
    
    return $false
}

function Register-ConsoleControlHandler {
    <#
    .SYNOPSIS
    Registers a handler for console control events (Ctrl+C, Ctrl+Break)
    #>
    
    # Import required WinAPI functions
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

    # Create handler function
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
                Write-Host "`n[Console Control Handler] Control event detected (Type: $eventType)" -ForegroundColor Yellow
                
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
                    return $true  # Allow the event to propagate
                } else {
                    # First attempt or single Ctrl+C - just log and continue
                    Write-Host "  Monitor will continue until end time. Press Ctrl+C again within $($global:ForceStopWindowSeconds)s to force stop." -ForegroundColor Yellow
                    Write-Log "Ctrl+C intercepted - monitor will continue until end time. Attempts: $global:ForceStopAttempts/$global:ForceStopThreshold" -Level "WARN"
                    return $true  # Swallow the event, don't terminate
                }
            }
            { $_ -in 2, 5, 6 } {  # Console close, logoff, or shutdown
                Write-Host "`n[Console Control Handler] System shutdown event detected" -ForegroundColor Yellow
                Write-Log "System shutdown event detected - initiating graceful shutdown" -Level "WARN"
                $global:IsShuttingDown = $true
                return $false  # Allow normal shutdown processing
            }
            default {
                return $false  # Allow other events to propagate
            }
        }
    }

    # Register the handler
    [void][ConsoleCtrlHandler]::SetConsoleCtrlHandler($handler, $true)
    Write-Log "Console control handler registered" -Level "DEBUG"
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
    Write-Host "Current Date: $($status.CurrentDate)" -ForegroundColor Yellow
    Write-Host "Current Time: $($status.CurrentTime)" -ForegroundColor Yellow
    Write-Host "Date Folder: $($Config.CurrentDate)" -ForegroundColor Yellow
    Write-Host "Schedule: $($Config.StartTime) - $($Config.EndTime)" -ForegroundColor Yellow
    Write-Host "Window: $(if ($status.Schedule.InWindow) { 'ACTIVE' } else { 'INACTIVE' })" `
                -ForegroundColor $(if ($status.Schedule.InWindow) { 'Green' } else { 'Gray' })
    Write-Host ""
    
    if ($status.PythonRunning) {
        Write-Host "PYTHON STATUS: RUNNING" -ForegroundColor Green
        Write-Host "  PID: $PythonPID" -ForegroundColor White
        
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
    Write-Host "ACTIVE DATE PATH: $($Config.ActiveDatePath)" -ForegroundColor Gray
    
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
    Write-Host "Date-based runs path: $($Config.RunsBasePath)" -ForegroundColor Gray
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop monitor" -ForegroundColor Gray
}


function Get-ProcessStatus {
    $status = @{
        MonitorRunning = $true
        WorkerRunning = $WorkerIsRunning
        PythonRunning = $PythonIsRunning
        CurrentTime = Get-Date -Format "HH:mm:ss"
        CurrentDate = Get-Date -Format "yyyy-MM-dd"
        CurrentDateFolder = $Config.CurrentDate
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
        PathInfo = @{
            ActiveDatePath = $Config.ActiveDatePath
            RunsBasePath = $Config.RunsBasePath
        }
    }
    
    # Check time window
    $startPassed = Test-TimeWindow -TargetTime $Config.StartTime
    $endPassed = Test-TimeWindow -TargetTime $Config.EndTime
    $status.Schedule.InWindow = ($startPassed -and !$endPassed)
    $status.Schedule.StartPassed = $startPassed
    $status.Schedule.EndPassed = $endPassed
    
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

function Send-CompletionEmailEnhanced {
    <#
    .SYNOPSIS
    Enhanced email function that sends all collected files from the day
    #>
    param(
        [array]$AllRunData,
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
        Write-Log "Preparing to send ENHANCED completion notifications with $($AllRunData.Count) collected runs..." -Level "INFO"
        
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
        
        # Collect all attachments from all runs
        $allAttachments = @()
        foreach ($runData in $AllRunData) {
            $allAttachments += $runData.Attachments
        }
        
        # Remove duplicates (in case same file appears in multiple runs)
        $allAttachments = $allAttachments | Select-Object -Unique
        
        # Check total attachment size
        $totalAttachmentSize = 0
        foreach ($attachment in $allAttachments) {
            if (Test-Path $attachment) {
                $totalAttachmentSize += (Get-Item $attachment).Length
            }
        }
        $totalSizeMB = [math]::Round($totalAttachmentSize / 1MB, 2)
        
        Write-Log "Total attachments to send: $($allAttachments.Count) files ($totalSizeMB MB)" -Level "INFO"
        
        # Check Gmail limit (25MB)
        if ($totalSizeMB -gt 25) {
            Write-Log "WARNING: Total attachment size ($totalSizeMB MB) exceeds Gmail limit (25 MB)" -Level "WARN"
            # We'll send anyway and let it fail if it's too large
        }
        
        # Group recipients by language
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
            
            # Get enhanced email content
            $emailContent = Get-EmailContentEnhanced -Language $language -AllRunData $AllRunData -ValidationResult $ValidationResult
            
            try {
                # Prepare email parameters
                $mailParams = @{
                    To          = $recipients
                    From        = $Config.EmailFrom
                    Subject     = $emailContent.Subject
                    Body        = $emailContent.Body
                    SmtpServer  = $Config.SmtpServer
                    Port        = $Config.SmtpPort
                    UseSsl      = $Config.UseSSL
                    Credential  = $credential
                    ErrorAction = 'Stop'
                }
                
                # Add all attachments if we have any
                if ($allAttachments.Count -gt 0) {
                    $mailParams.Attachments = $allAttachments
                }
                
                # Send the email
                Send-MailMessage @mailParams
                
                Write-Log "Successfully sent $language email with $($allAttachments.Count) attachments to $($recipients.Count) recipient(s)" -Level "SUCCESS"
                $successCount += $recipients.Count
                
            } catch {
                Write-Log "Failed to send $language email: $($_.Exception.Message)" -Level "ERROR"
                $failCount += $recipients.Count
                
                # If attachments are too large, try sending without them
                if ($_.Exception.Message -like "*size*" -or $_.Exception.Message -like "*large*") {
                    Write-Log "Attempting to send without attachments due to size limit..." -Level "WARN"
                    try {
                        Send-MailMessage @mailParams -Body ($emailContent.Body + "`n`n[NOTE: Attachments omitted due to size limitations]")
                        Write-Log "Email sent without attachments" -Level "SUCCESS"
                        $successCount += $recipients.Count
                        $failCount -= $recipients.Count
                    } catch {
                        Write-Log "Failed to send even without attachments: $($_.Exception.Message)" -Level "ERROR"
                    }
                }
            }
        }
        
        # Summary
        $totalRecipients = $successCount + $failCount
        if ($failCount -eq 0) {
            Write-Log "All enhanced emails sent successfully ($totalRecipients total recipients)" -Level "SUCCESS"
            return $true
        } elseif ($successCount -gt 0) {
            Write-Log "Partially successful: $successCount/$totalRecipients enhanced emails sent" -Level "WARN"
            return $true
        } else {
            Write-Log "All enhanced emails failed to send" -Level "ERROR"
            return $false
        }
        
    } catch {
        Write-Log "Failed to send enhanced completion emails: $($_.Exception.Message)" -Level "ERROR"
        return $false
    }
}

function Get-EmailContentEnhanced {
    <#
    .SYNOPSIS
    Enhanced email content function that includes all collected runs
    #>
    param(
        [string]$Language,
        [array]$AllRunData,  # Array of collected run data
        [object]$ValidationResult
    )
    
    $currentTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    switch ($Language.ToLower()) {
        "bahasa" {
            $subject = "$($Config.EmailSubject.Bahasa) - Laporan Akhir Hari"
            
            $body = @"
LAPORAN AKHIR HARIAN PROSES PENGENALAN WAJAH
============================================

RINGKASAN HARIAN
----------------
Waktu Penyelesaian: $currentTime
Total Proses Dijalankan: $($AllRunData.Count)
Status Keseluruhan: $(if ($ValidationResult.Success) {'BERHASIL'} else {'DENGAN PERINGATAN'})

DETAIL SETIAP PROSES
-------------------
$(foreach ($run in $AllRunData) {
"• $($run.RunFolderName):
  - Jumlah File: $($run.Attachments.Count)
  - Ukuran Total: $($run.TotalSizeMB) MB
  - Waktu Koleksi: $($run.CollectionTime)
"
})

STATISTIK HARIAN
----------------
Total Folder: $($AllRunData.Count)
Total File Lampiran: $(($AllRunData | ForEach-Object { $_.Attachments.Count } | Measure-Object -Sum).Sum)
Ukuran Total Semua Lampiran: $(($AllRunData | ForEach-Object { $_.TotalSizeMB } | Measure-Object -Sum).Sum) MB

HASIL VALIDASI TERAKHIR
-----------------------
$(if ($ValidationResult) {
"Folder Terakhir: $($ValidationResult.FolderName)
Dibuat: $($ValidationResult.CreationTime)
Ukuran: $(if ($ValidationResult.Details.TotalSizeMB) {"$($ValidationResult.Details.TotalSizeMB) MB"} else {"Tidak Diketahui"})
"
} else {
"Tidak ada validasi terakhir"
})

$(if ($ValidationResult.Warnings.Count -gt 0) {
"PERINGATAN:
$(foreach ($warning in $ValidationResult.Warnings) {
"- $warning"
})
"
})

INFORMASI SISTEM
----------------
Instans Monitor: $($env:COMPUTERNAME)
Path Dasar: $($Config.RunsBasePath)
Jadwal: $($Config.StartTime) - $($Config.EndTime)
File Log Monitor: $($Config.LogFile)

CATATAN
-------
Laporan ini mencakup semua proses yang berjalan antara $($Config.StartTime) hingga $($Config.EndTime).
Setiap file lampiran berasal dari folder proses masing-masing.
"@
        }
        
        default {  # English (default)
            $subject = "$($Config.EmailSubject.English) - End of Day Report"
            
            $body = @"
DAILY FACE RECOGNITION PROCESS REPORT
=====================================

DAILY SUMMARY
-------------
Completion Time: $currentTime
Total Processes Run: $($AllRunData.Count)
Overall Status: $(if ($ValidationResult.Success) {'SUCCESSFUL'} else {'WITH WARNINGS'})

INDIVIDUAL PROCESS DETAILS
--------------------------
$(foreach ($run in $AllRunData) {
"• $($run.RunFolderName):
  - File Count: $($run.Attachments.Count)
  - Total Size: $($run.TotalSizeMB) MB
  - Collection Time: $($run.CollectionTime)
"
})

DAILY STATISTICS
----------------
Total Folders: $($AllRunData.Count)
Total Attachment Files: $(($AllRunData | ForEach-Object { $_.Attachments.Count } | Measure-Object -Sum).Sum)
Total Size of All Attachments: $(($AllRunData | ForEach-Object { $_.TotalSizeMB } | Measure-Object -Sum).Sum) MB

LAST VALIDATION RESULTS
-----------------------
$(if ($ValidationResult) {
"Last Folder: $($ValidationResult.FolderName)
Created: $($ValidationResult.CreationTime)
Size: $(if ($ValidationResult.Details.TotalSizeMB) {"$($ValidationResult.Details.TotalSizeMB) MB"} else {"Unknown"})
"
} else {
"No recent validation"
})

$(if ($ValidationResult.Warnings.Count -gt 0) {
"WARNINGS:
$(foreach ($warning in $ValidationResult.Warnings) {
"- $warning"
})
"
})

SYSTEM INFORMATION
------------------
Monitor Instance: $($env:COMPUTERNAME)
Base Path: $($Config.RunsBasePath)
Schedule: $($Config.StartTime) - $($Config.EndTime)
Monitor Log File: $($Config.LogFile)

NOTES
-----
This report includes all processes that ran between $($Config.StartTime) and $($Config.EndTime).
Each attachment file comes from its respective process folder.
"@
        }
    }
    
    return @{
        Subject = $subject
        Body = $body
    }
}

function Send-CompletionEmailEnhanced {
    <#
    .SYNOPSIS
    Enhanced email function that sends all collected files from the day
    #>
    param(
        [array]$AllRunData,
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
        Write-Log "Preparing to send ENHANCED completion notifications with $($AllRunData.Count) collected runs..." -Level "INFO"
        
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
        
        # Collect all attachments from all runs
        $allAttachments = @()
        foreach ($runData in $AllRunData) {
            $allAttachments += $runData.Attachments
        }
        
        # Remove duplicates (in case same file appears in multiple runs)
        $allAttachments = $allAttachments | Select-Object -Unique
        
        # Check total attachment size
        $totalAttachmentSize = 0
        foreach ($attachment in $allAttachments) {
            if (Test-Path $attachment) {
                $totalAttachmentSize += (Get-Item $attachment).Length
            }
        }
        $totalSizeMB = [math]::Round($totalAttachmentSize / 1MB, 2)
        
        Write-Log "Total attachments to send: $($allAttachments.Count) files ($totalSizeMB MB)" -Level "INFO"
        
        # Check Gmail limit (25MB)
        if ($totalSizeMB -gt 25) {
            Write-Log "WARNING: Total attachment size ($totalSizeMB MB) exceeds Gmail limit (25 MB)" -Level "WARN"
            # We'll send anyway and let it fail if it's too large
        }
        
        # Group recipients by language
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
            
            # Get enhanced email content
            $emailContent = Get-EmailContentEnhanced -Language $language -AllRunData $AllRunData -ValidationResult $ValidationResult
            
            try {
                # Prepare email parameters
                $mailParams = @{
                    To          = $recipients
                    From        = $Config.EmailFrom
                    Subject     = $emailContent.Subject
                    Body        = $emailContent.Body
                    SmtpServer  = $Config.SmtpServer
                    Port        = $Config.SmtpPort
                    UseSsl      = $Config.UseSSL
                    Credential  = $credential
                    ErrorAction = 'Stop'
                }
                
                # Add all attachments if we have any
                if ($allAttachments.Count -gt 0) {
                    $mailParams.Attachments = $allAttachments
                }
                
                # Send the email
                Send-MailMessage @mailParams
                
                Write-Log "Successfully sent $language email with $($allAttachments.Count) attachments to $($recipients.Count) recipient(s)" -Level "SUCCESS"
                $successCount += $recipients.Count
                
            } catch {
                Write-Log "Failed to send $language email: $($_.Exception.Message)" -Level "ERROR"
                $failCount += $recipients.Count
                
                # If attachments are too large, try sending without them
                if ($_.Exception.Message -like "*size*" -or $_.Exception.Message -like "*large*") {
                    Write-Log "Attempting to send without attachments due to size limit..." -Level "WARN"
                    try {
                        Send-MailMessage @mailParams -Body ($emailContent.Body + "`n`n[NOTE: Attachments omitted due to size limitations]")
                        Write-Log "Email sent without attachments" -Level "SUCCESS"
                        $successCount += $recipients.Count
                        $failCount -= $recipients.Count
                    } catch {
                        Write-Log "Failed to send even without attachments: $($_.Exception.Message)" -Level "ERROR"
                    }
                }
            }
        }
        
        # Summary
        $totalRecipients = $successCount + $failCount
        if ($failCount -eq 0) {
            Write-Log "All enhanced emails sent successfully ($totalRecipients total recipients)" -Level "SUCCESS"
            return $true
        } elseif ($successCount -gt 0) {
            Write-Log "Partially successful: $successCount/$totalRecipients enhanced emails sent" -Level "WARN"
            return $true
        } else {
            Write-Log "All enhanced emails failed to send" -Level "ERROR"
            return $false
        }
        
    } catch {
        Write-Log "Failed to send enhanced completion emails: $($_.Exception.Message)" -Level "ERROR"
        return $false
    }
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

function Get-DateBasedPath {
    <#
    .SYNOPSIS
    Gets or creates a date-based folder path for the current day
    #>
    param(
        [string]$BasePath = (Join-Path $ActiveRoot "logs-running\Magick"),
        [DateTime]$Date = (Get-Date)
    )
    
    $dateString = $Date.ToString("yyyy-MM-dd")
    $datePath = Join-Path $BasePath $dateString
    
    # Create the directory if it doesn't exist
    if (-not (Test-Path $datePath)) {
        try {
            New-Item -ItemType Directory -Path $datePath -Force | Out-Null
            Write-Log "Created date-based folder: $datePath" -Level "INFO"
        } catch {
            Write-Log "Failed to create date-based folder: $_" -Level "ERROR"
            throw
        }
    }
    
    return $datePath
}

function Update-ConfigForCurrentDate {
    <#
    .SYNOPSIS
    Updates configuration paths for the current date folder
    #>
    
    $currentDate = Get-Date -Format "yyyy-MM-dd"
    
    # Update paths in config to use date-based folder
    $dateBasedPath = Get-DateBasedPath -Date (Get-Date)
    
    $Script:Config.RunsBasePath = $dateBasedPath
    $Script:Config.PIDFilePath = Join-Path $dateBasedPath "monitor_pid_Magick.json"
    $Script:Config.LogFile = Join-Path $dateBasedPath "monitor_Magick.log"
    $Script:Config.CurrentDate = $currentDate
    $Script:Config.ActiveDatePath = $dateBasedPath
    
    # Update global variables
    $global:CurrentDateFolder = $currentDate
    $global:ActiveDatePath = $dateBasedPath
    
    Write-Log "Updated configuration for date: $currentDate" -Level "INFO"
    Write-Log "Active date path: $dateBasedPath" -Level "DEBUG"
}


function Find-LatestRunFolder {
    <#
    .SYNOPSIS
    Finds the latest run folder within the current date's directory
    #>
    
    try {
        # First check the current date's path
        $currentDatePath = $Config.RunsBasePath
        
        if (-not (Test-Path $currentDatePath)) {
            Write-Log "Current date path does not exist: $currentDatePath" -Level "WARN"
            return $null
        }
        
        $folders = Get-ChildItem -Path $currentDatePath -Directory -Filter $Config.OutputFolderPattern -ErrorAction SilentlyContinue
        
        if ($folders) {
            $latestFolder = $folders | Sort-Object CreationTime -Descending | Select-Object -First 1
            Write-Log "Found latest run folder in date-based path: $($latestFolder.Name)" -Level "DEBUG"
            return $latestFolder
        } else {
            # If no folders in current date path, check if we're looking at the wrong day
            # This handles the case where the script might run across midnight
            $parentPath = Split-Path $currentDatePath -Parent
            $allDateFolders = Get-ChildItem -Path $parentPath -Directory -Filter "????-??-??" | Sort-Object Name -Descending
            
            foreach ($dateFolder in $allDateFolders) {
                $checkPath = Join-Path $dateFolder.FullName "*"
                $potentialFolders = Get-ChildItem -Path $checkPath -Directory -Filter $Config.OutputFolderPattern -ErrorAction SilentlyContinue
                
                if ($potentialFolders) {
                    $latestFolder = $potentialFolders | Sort-Object CreationTime -Descending | Select-Object -First 1
                    Write-Log "Found run folder in different date folder: $($dateFolder.Name)" -Level "INFO"
                    return $latestFolder
                }
            }
            
            Write-Log "No run folders found in any date directory" -Level "DEBUG"
            return $null
        }
    }
    catch {
        Write-Log "Error finding run folders: $_" -Level "ERROR"
        return $null
    }
}

# Call it ONCE at the very beginning
Initialize-ProjectPortablePaths
# ====================================================================
# SECTION 2.1: ENHANCED GLOBAL VARIABLES FOR RESILIENCE
# ====================================================================

# Global variables (keep existing ones and add new ones)
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
$LastWorkerAttempt = $null

# NEW: Enhanced tracking for resilience
$global:ForceStopAttempts = 0
$global:LastForceStopTime = $null
$global:ForceStopThreshold = 2  # Require 2 Ctrl+C within 5 seconds to force stop
$global:ForceStopWindowSeconds = 5
$global:EmailAttachmentQueue = @()
$global:CollectedRunFolders = @()
$global:IsShuttingDown = $false

# ENHANCED: Persistent tracking for last known state
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

# PID tracking structure
$PIDTracking = @{
    WorkerPID = $null
    PythonPID = $null
    WorkerStartTime = $null
    PythonStartTime = $null
    RunFolder = $null
    LastUpdate = $null
    # NEW: Enhanced tracking
    EmailQueue = @()
    CollectedFolders = @()
    ShutdownInitiated = $false
    # ENHANCED: Persistent tracking data
    PersistentTracking = $null
}

# ====================================================================
# SECTION 3.2: ENHANCED PERSISTENCE TRACKING FUNCTIONS
# ====================================================================

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
    
    # Add current process state to history if it's significant
    $currentState = @{
        Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        PythonPID = $PythonPID
        WorkerPID = $WorkerPID
        RunFolder = $CurrentRunFolder
        PythonRunning = $PythonIsRunning
        WorkerRunning = $WorkerIsRunning
        ForceStopAttempts = $global:ForceStopAttempts
    }
    
    $global:PersistentTracking.ProcessStopHistory += $currentState
    
    # Keep only last 50 entries to prevent file bloat
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
                    # Start fresh but keep the file for reference
                    $backupPath = "$persistentFilePath.backup_$(Get-Date -Format 'yyyyMMdd')"
                    Copy-Item -Path $persistentFilePath -Destination $backupPath -Force
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
            }
            
            Write-Log "Loaded persistent tracking with $($global:PersistentTracking.ProcessStopHistory.Count) history entries" -Level "INFO"
            
            # Check if there was an unexpected stop in previous session
            if ($global:PersistentTracking.ProcessStopHistory.Count -gt 0) {
                $lastStop = $global:PersistentTracking.ProcessStopHistory[-1]
                
                # If last session ended with running processes, we should check for orphaned runs
                if ($lastStop.PythonRunning -or $lastStop.WorkerRunning) {
                    Write-Log "Previous session appears to have ended unexpectedly. Checking for orphaned runs..." -Level "WARN"
                    Check-OrphanedRuns -LastKnownFolder $lastStop.RunFolder
                }
            }
            
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
        $validation = Validate-Output -RunFolder $LastKnownFolder -RetryCount 0
        
        if ($validation.Success) {
            # Collect this orphaned run
            $runData = Collect-RunFolderAttachments -RunFolder $LastKnownFolder
            if ($runData.Attachments.Count -gt 0) {
                $global:CollectedRunFolders += $runData
                $global:EmailAttachmentQueue += $runData.Attachments
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
    
    # Check all run folders in the base path
    $allRunFolders = Get-ChildItem -Path $Config.RunsBasePath -Directory -Filter $Config.OutputFolderPattern -ErrorAction SilentlyContinue
    
    if ($allRunFolders) {
        Write-Log "Found $($allRunFolders.Count) total run folders" -Level "DEBUG"
        
        # Check each folder for completeness
        foreach ($folder in $allRunFolders) {
            # Skip if this is the last known folder we already processed
            if ($folder.FullName -eq $LastKnownFolder) {
                continue
            }
            
            # Check if folder has completion marker
            $completionPath = Join-Path $folder.FullName "Magick_Process_*\logs\completion_summary.txt"
            $metadataPath = Join-Path $folder.FullName "metadata.json"
            
            if ((Test-Path $completionPath) -and (Test-Path $metadataPath)) {
                # Check if we already collected this folder
                $alreadyCollected = $global:CollectedRunFolders | Where-Object { $_.RunFolder -eq $folder.FullName }
                
                if (-not $alreadyCollected) {
                    Write-Log "Found uncollected completed run: $(Split-Path $folder.FullName -Leaf)" -Level "INFO"
                    $runData = Collect-RunFolderAttachments -RunFolder $folder.FullName
                    if ($runData.Attachments.Count -gt 0) {
                        $global:CollectedRunFolders += $runData
                        $global:EmailAttachmentQueue += $runData.Attachments
                        Write-Log "Collected previously uncollected run: $($runData.RunFolderName)" -Level "SUCCESS"
                    }
                }
            }
        }
    }
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
        $validation = Validate-Output -RunFolder $CurrentRunFolder -RetryCount 0
        
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
                    $global:EmailAttachmentQueue += $runData.Attachments
                    Write-Log "Collected run on stop: $($runData.RunFolderName)" -Level "SUCCESS"
                    Record-ProcessStop -StopType "Validation" -Reason "Success" -WasUnexpected $true
                }
            }
        } else {
            Write-Log "Validation failed for run folder on stop" -Level "WARN"
            Record-ProcessStop -StopType "Validation" -Reason "Failed: $($validation.Error)" -WasUnexpected $true
        }
    } else {
        # If no current run folder, try to find the latest one
        Write-Log "No current run folder, finding latest..." -Level "DEBUG"
        $latestFolder = Find-LatestRunFolder
        if ($latestFolder) {
            Write-Log "Validating latest run folder on stop: $(Split-Path $latestFolder.FullName -Leaf)" -Level "DEBUG"
            $validation = Validate-Output -RunFolder $latestFolder.FullName -RetryCount 0
            
            if ($validation.Success) {
                $runData = Collect-RunFolderAttachments -RunFolder $latestFolder.FullName
                if ($runData.Attachments.Count -gt 0) {
                    # Check if we already have this folder
                    $existingIndex = $global:CollectedRunFolders | 
                        Where-Object { $_.RunFolder -eq $runData.RunFolder } | 
                        Select-Object -First 1
                    
                    if (-not $existingIndex) {
                        $global:CollectedRunFolders += $runData
                        $global:EmailAttachmentQueue += $runData.Attachments
                        Write-Log "Collected latest run on stop: $($runData.RunFolderName)" -Level "SUCCESS"
                        Record-ProcessStop -StopType "Validation" -Reason "Success" -WasUnexpected $true
                    }
                }
            }
        } else {
            Write-Log "No run folders found to validate on stop" -Level "WARN"
            Record-ProcessStop -StopType "Validation" -Reason "No folders found" -WasUnexpected $true
        }
    }
    
    # Save all state
    Save-PIDTracking
    Save-ResilienceState
    Save-PersistentTracking
}

# ====================================================================
# SECTION 4.1: ENHANCED STOP-WORKERPROCESS FUNCTION
# ====================================================================

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
    
    # Record final stop event
    Record-ProcessStop -StopType "ProcessStopComplete" -Reason "Processes stopped: $($stoppedProcesses.Count)" -WasUnexpected $wasUnexpected
}

# ====================================================================
# SECTION 4.2: ENHANCED SAVE-PIDTRACKING FUNCTION
# ====================================================================

function Save-PIDTracking {
    # Enhanced to include resilience data
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
    
    # NEW: Add resilience data
    $PIDTracking.EmailQueue = $global:EmailAttachmentQueue
    $PIDTracking.CollectedFolders = $global:CollectedRunFolders
    $PIDTracking.ShutdownInitiated = $global:IsShuttingDown
    
    # ENHANCED: Add persistent tracking data
    $PIDTracking.PersistentTracking = @{
        LastKnownRunFolder = $CurrentRunFolder
        LastKnownPythonPID = $PythonPID
        LastKnownWorkerPID = $WorkerPID
        DailyRunCount = $global:PersistentTracking.DailyRunCount
        LastSuccessfulRun = $global:PersistentTracking.LastSuccessfulRun
    }
    
    try {
        $PIDTracking | ConvertTo-Json -Depth 10 | Out-File -FilePath $Config.PIDFilePath -Force
        Write-Log "Enhanced PID tracking saved with $($global:CollectedRunFolders.Count) collected folders" -Level "DEBUG"
        
        # Also save resilience state and persistent tracking separately
        Save-ResilienceState
        Save-PersistentTracking
    } catch {
        Write-Log "Failed to save enhanced PID tracking: $_" -Level "ERROR"
    }
}

# ====================================================================
# SECTION 5.1: ENHANCED LOAD-PIDTRACKING FUNCTION
# ====================================================================

function Load-PIDTracking {
    if (-not (Test-Path $Config.PIDFilePath)) {
        Write-Log "No PID tracking file found" -Level "DEBUG"
        
        # Try to load resilience state separately
        Load-ResilienceState | Out-Null
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
            
            # Handle DateTime values
            if ($loaded.WorkerStartTime -and $loaded.WorkerStartTime -ne "-") {
                try {
                    $global:WorkerStartTime = [DateTime]::ParseExact($loaded.WorkerStartTime, "yyyy-MM-dd HH:mm:ss", $null)
                } catch {
                    Write-Log "Invalid WorkerStartTime in PID file: $($loaded.WorkerStartTime)" -Level "WARN"
                    $global:WorkerStartTime = $null
                }
            }
            
            if ($loaded.PythonStartTime -and $loaded.PythonStartTime -ne "-") {
                try {
                    $global:PythonStartTime = [DateTime]::ParseExact($loaded.PythonStartTime, "yyyy-MM-dd HH:mm:ss", $null)
                } catch {
                    Write-Log "Invalid PythonStartTime in PID file: $($loaded.PythonStartTime)" -Level "WARN"
                    $global:PythonStartTime = $null
                }
            }
            
            $global:CurrentRunFolder = $loaded.RunFolder
            
            # NEW: Load resilience data
            if ($loaded.PSObject.Properties.Name -contains "EmailQueue") {
                $global:EmailAttachmentQueue = @($loaded.EmailQueue)
            }
            if ($loaded.PSObject.Properties.Name -contains "CollectedFolders") {
                $global:CollectedRunFolders = @($loaded.CollectedFolders)
            }
            if ($loaded.PSObject.Properties.Name -contains "ShutdownInitiated") {
                $global:IsShuttingDown = $loaded.ShutdownInitiated
            }
            
            # ENHANCED: Load persistent tracking data from PID file
            if ($loaded.PSObject.Properties.Name -contains "PersistentTracking") {
                $global:PersistentTracking.LastKnownRunFolder = $loaded.PersistentTracking.LastKnownRunFolder
                $global:PersistentTracking.LastKnownPythonPID = $loaded.PersistentTracking.LastKnownPythonPID
                $global:PersistentTracking.LastKnownWorkerPID = $loaded.PersistentTracking.LastKnownWorkerPID
                $global:PersistentTracking.DailyRunCount = $loaded.PersistentTracking.DailyRunCount
                $global:PersistentTracking.LastSuccessfulRun = $loaded.PersistentTracking.LastSuccessfulRun
            }
            
            Write-Log "Enhanced PID tracking loaded: WorkerPID=$WorkerPID (Alive: $workerAlive), $($global:CollectedRunFolders.Count) collected folders" -Level "INFO"
            
            # Also load separate persistent tracking file for history
            Load-PersistentTracking | Out-Null
            
            return $true
        } else {
            Write-Log "Loaded PIDs are no longer running, cleaning up" -Level "INFO"
            
            # ENHANCED: Validate and collect before cleaning up
            if ($loaded.RunFolder) {
                Write-Log "Validating and collecting run folder before cleanup..." -Level "INFO"
                Validate-And-Collect-OnStop -StopReason "Processes Dead on Load"
            }
            
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            
            # Load persistent tracking separately
            Load-PersistentTracking | Out-Null
            Save-ResilienceState
            
            return $false
        }
    } catch {
        Write-Log "Failed to load enhanced PID tracking: $_" -Level "ERROR"
        Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        
        # Try to load persistent tracking anyway
        Load-PersistentTracking | Out-Null
        
        return $false
    }
}

# ====================================================================
# SECTION 6.1: ENHANCED CHECK-PROCESSSTATUS FUNCTION
# ====================================================================

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
    
    # ENHANCED: Check for unexpected process stops
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

# ====================================================================
# SECTION 7.1: ENHANCED VALIDATE-OUTPUT FUNCTION WITH RUNFOLDER PARAM
# ====================================================================

function Validate-Output {
    param(
        [string]$RunFolder,
        [int]$RetryCount = 0
    )
    
    # If no RunFolder specified, use the latest one
    if ([string]::IsNullOrEmpty($RunFolder)) {
        Write-Log "No run folder specified, finding latest..." -Level "DEBUG"
        $latestFolder = Find-LatestRunFolder
        if ($latestFolder) {
            $RunFolder = $latestFolder.FullName
        } else {
            if ($RetryCount -lt $Config.MaxValidationRetries) {
                Write-Log "No output folder found. Retrying in $($Config.RetryDelaySeconds) seconds... (Attempt $($RetryCount + 1)/$($Config.MaxValidationRetries))" -Level "WARN"
                Start-Sleep -Seconds $Config.RetryDelaySeconds
                return Validate-Output -RunFolder $null -RetryCount ($RetryCount + 1)
            } else {
                Write-Log "VALIDATION FAILED: No output folder found after $($Config.MaxValidationRetries) retries" -Level "ERROR"
                return @{ 
                    Success = $false; 
                    Error = "No output folder created"; 
                    RunFolder = $null 
                }
            }
        }
    }
    
    $Global:CurrentRunFolder = $RunFolder
    
    # Perform folder structure validation
    $validationResult = @{
        Success = $true
        RunFolder = $RunFolder
        FolderName = Split-Path $RunFolder -Leaf
        CreationTime = if (Test-Path $RunFolder) { (Get-Item $RunFolder).CreationTime } else { $null }
        MissingItems = @()
        Errors = @()
        Warnings = @()
        Details = @{
            FileSizes = @{}
            AttachmentFiles = @()
        }
    }
    
    Write-Log "Validating folder structure for: $($validationResult.FolderName)" -Level "INFO"
    
    # Check for expected subfolders
    foreach ($item in $Config.ExpectedSubfolders) {
        $itemPath = Join-Path $RunFolder $item
        
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
        $itemPath = Join-Path $RunFolder $item
        
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
                    $validationResult.Errors += $item + ": Invalid JSON format"
                    $validationResult.Success = $false
                    Write-Log "Metadata file contains invalid JSON" -Level "WARN"
                }
            }
        }
    }
    
    # Check log files
    $logPath = Join-Path $RunFolder "logs"
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
    $scriptOutputPath = Join-Path $RunFolder "script_output"
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
        $files = Get-ChildItem -Path $RunFolder -Recurse -File -ErrorAction SilentlyContinue
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
            
            $metadataSize = (Test-Path (Join-Path $RunFolder "metadata.json")) ? (Get-Item (Join-Path $RunFolder "metadata.json")).Length : 0
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
    
    # ENHANCED: Record validation in persistent tracking
    if ($validationResult.Success) {
        Record-ProcessStop -StopType "Validation" -Reason "Success"
    } else {
        Record-ProcessStop -StopType "Validation" -Reason "Failed: $($validationResult.Errors -join ', ')"
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
        Write-Log "  - Path: $($validationResult.RunFolder)" -Level "SUCCESS"
        Write-Log "  - Created: $($validationResult.CreationTime)" -Level "SUCCESS"
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
# SECTION 8.1: ENHANCED MAIN EXECUTION WITH PERSISTENT TRACKING
# ====================================================================

# Main execution - Enhanced with persistent tracking
try {
    # Create log directory if it doesn't exist
    $logDir = Split-Path $Config.LogFile -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    
    Write-Log "=== ENHANCED Face Recognition Monitor Started ===" -Level "INFO"
    Write-Log "Monitor Version: 3.1 (Persistent Tracking)" -Level "INFO"
    Write-Log "Start Time: $($Config.StartTime)" -Level "INFO"
    Write-Log "End Time: $($Config.EndTime)" -Level "INFO"
    Write-Log "Force stop threshold: $global:ForceStopThreshold attempts within $global:ForceStopWindowSeconds seconds" -Level "INFO"
    
    # Initialize resilience state BEFORE registering handler
    Write-Log "Initializing resilience system..." -Level "DEBUG"
    
    # Ensure resilience variables are properly initialized
    $global:ForceStopAttempts = 0
    $global:LastForceStopTime = $null
    $global:EmailAttachmentQueue = @()
    $global:CollectedRunFolders = @()
    $global:IsShuttingDown = $false
    
    # Initialize persistent tracking
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
    
    # Test email configuration ONCE at startup
    $EmailConfigValid = Test-EmailConfiguration
    if ($EmailConfigValid) {
        Write-Log "Email configuration validated successfully" -Level "SUCCESS"
    }
    
    # Load existing PID tracking, resilience state, AND persistent tracking
    Write-Log "Loading persistence data..." -Level "INFO"
    $pidLoaded = Load-PIDTracking
    $persistentLoaded = Load-PersistentTracking
    
    if ($pidLoaded) {
        Write-Log "Resumed monitoring of existing processes" -Level "SUCCESS"
        Write-Log "Loaded $($global:CollectedRunFolders.Count) previously collected folders" -Level "INFO"
        # Update process status
        Check-ProcessStatus | Out-Null
    } else {
        # Initialize fresh resilience state if none loaded
        Save-ResilienceState
        Save-PersistentTracking
    }
    
    # Register console control handler AFTER state is initialized
    Write-Log "Registering console control handler..." -Level "DEBUG"
    Register-ConsoleControlHandler
    
    # Ensure runs base path exists
    if (-not (Test-Path $Config.RunsBasePath)) {
        Write-Log "Creating runs base directory: $($Config.RunsBasePath)" -Level "WARN"
        New-Item -ItemType Directory -Path $Config.RunsBasePath -Force | Out-Null
    }
    
    # Clear console and show initial status
    Clear-Host
    
    # Main monitoring loop with enhanced resilience
    Write-Log "Entering main monitoring loop..." -Level "INFO"
    
    while ($true) {
        try {
            # Check if forced shutdown was requested
            if ($global:IsShuttingDown) {
                Write-Log "Shutdown requested. Checking if end time reached..." -Level "INFO"
                $endPassed = Test-TimeWindow -TargetTime $Config.EndTime
                
                if ($endPassed) {
                    Write-Log "End time reached - proceeding with shutdown" -Level "INFO"
                    break
                } else {
                    Write-Log "End time not reached yet - continuing until $($Config.EndTime)" -Level "WARN"
                    # Reset shutdown flag to continue monitoring
                    $global:IsShuttingDown = $false
                    Write-Host "`nShutdown cancelled. Monitor will continue until $($Config.EndTime)" -ForegroundColor Yellow
                    Write-Host "Press Ctrl+C twice within 5 seconds to force stop." -ForegroundColor Gray
                }
            }
            
            # Check process status (now includes unexpected stop detection)
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
                if ($LastWorkerAttempt -and ((Get-Date) - $LastWorkerAttempt).TotalSeconds -lt 60) {
                    Write-Log "Skipping worker start - too soon after last attempt (60s cooldown)" -Level "DEBUG"
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
            
            # Handle end time with enhanced collection
            elseif ($endPassed) {
                Write-Log "End time reached - initiating shutdown sequence..." -Level "INFO"
                
                # Stop processes if they're running
                if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
                    Write-Log "Stopping running processes..." -Level "INFO"
                    Stop-WorkerProcess
                    
                    # Wait for cleanup
                    Start-Sleep -Seconds 5
                }
                
                # Validate the last output
                Write-Log "Validating final worker output..." -Level "INFO"
                $LastValidation = Validate-Output
                
                # Collect data from the last run
                if ($LastValidation -and $LastValidation.Success -and $LastValidation.RunFolder) {
                    $runData = Collect-RunFolderAttachments -RunFolder $LastValidation.RunFolder
                    if ($runData.Attachments.Count -gt 0) {
                        # Check if we already have this folder
                        $existingIndex = $global:CollectedRunFolders | 
                            Where-Object { $_.RunFolder -eq $runData.RunFolder } | 
                            Select-Object -First 1
                        
                        if (-not $existingIndex) {
                            $global:CollectedRunFolders += $runData
                            $global:EmailAttachmentQueue += $runData.Attachments
                            Write-Log "Added final run to collection: $($runData.RunFolderName)" -Level "SUCCESS"
                        }
                    }
                }
                
                # Send enhanced completion email if we have collected runs
                if ($global:CollectedRunFolders.Count -gt 0) {
                    if ($Config.SendEmailOnCompletion -and $EmailConfigValid) {
                        # Backup original config before sending
                        Backup-OriginalConfig
                        
                        $emailSent = Send-CompletionEmailEnhanced -AllRunData $global:CollectedRunFolders -ValidationResult $LastValidation
                        if ($emailSent) {
                            Write-Log "Enhanced completion emails sent successfully with $($global:CollectedRunFolders.Count) collected runs." -Level "SUCCESS"
                        } else {
                            Write-Log "Failed to send some or all enhanced completion emails." -Level "WARN"
                        }
                    } elseif ($Config.SendEmailOnCompletion -and -not $EmailConfigValid) {
                        Write-Log "Email configuration is invalid. Skipping enhanced email notification." -Level "WARN"
                    }
                    
                    Write-Log "Face recognition pipeline completed successfully! Processed $($global:CollectedRunFolders.Count) runs today." -Level "SUCCESS"
                } else {
                    Write-Log "No runs were collected today." -Level "WARN"
                }
                
                # Clear collected data for next day
                $global:CollectedRunFolders = @()
                $global:EmailAttachmentQueue = @()
                Save-ResilienceState
                
                # Stop the monitor
                Write-Log "Daily process completed. Stopping monitor..." -Level "INFO"
                break
            }
            
            # Periodically collect data from completed runs (even before end time)
            elseif ($processStatus.PythonRunning -and $CurrentRunFolder -and 
                    (-not $global:CollectedRunFolders.Where({ $_.RunFolder -eq $CurrentRunFolder }))) {
                # Check if the run folder has a completion summary (indicating it's done)
                $completionPath = Join-Path $CurrentRunFolder "Magick_Process_*\logs\completion_summary.txt"
                if (Test-Path $completionPath) {
                    Write-Log "Detected completed run, collecting data..." -Level "DEBUG"
                    $runData = Collect-RunFolderAttachments -RunFolder $CurrentRunFolder
                    if ($runData.Attachments.Count -gt 0) {
                        $global:CollectedRunFolders += $runData
                        $global:EmailAttachmentQueue += $runData.Attachments
                        Write-Log "Collected completed run: $($runData.RunFolderName)" -Level "INFO"
                        Save-PIDTracking
                    }
                }
            }
            
            # Save PID tracking periodically
            if ($processStatus.PythonRunning -or $processStatus.WorkerRunning) {
                Save-PIDTracking
            }
            
            # Wait before next check
            Start-Sleep -Seconds $Config.ProcessCheckInterval
            
        } catch {
            # Enhanced error handling for resilience
            Write-Log "Error in main loop: $_" -Level "ERROR"
            Write-Log $_.ScriptStackTrace -Level "DEBUG"
            
            # Save state before potentially crashing
            Save-PIDTracking
            Save-ResilienceState
            Save-PersistentTracking
            
            # Record error in persistent tracking
            Record-ProcessStop -StopType "Error" -Reason $_ -WasUnexpected $true
            
            # Continue monitoring unless it's a critical error
            if ($_.Exception.Message -like "*fatal*" -or $_.Exception.Message -like "*critical*") {
                Write-Log "Critical error detected, but continuing until end time" -Level "ERROR"
            }
            
            # Wait before retrying
            Start-Sleep -Seconds $Config.ProcessCheckInterval
        }
    }
}
catch [System.Management.Automation.Host.HostException] {
    # This catch block should rarely be reached now that we have the console handler
    Write-Log "Host exception caught - likely Ctrl+C without handler interception" -Level "WARN"
    Write-Log "Attempting to save state and continue..." -Level "INFO"
    
    # Save state and try to continue
    Save-PIDTracking
    Save-ResilienceState
    Save-PersistentTracking
    
    # Record the host exception
    Record-ProcessStop -StopType "HostException" -Reason "Ctrl+C or similar" -WasUnexpected $true
    
    # Don't break - continue from the top of the while loop
    # The console handler should prevent this from being reached
}
catch {
    Write-Log "FATAL ERROR: $_" -Level "ERROR"
    Write-Log $_.ScriptStackTrace -Level "ERROR"
    
    # Save state before exiting
    Save-ResilienceState
    Save-PersistentTracking
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
    
    # Clear resilience state
    $resilienceFilePath = Join-Path (Split-Path $Config.LogFile -Parent) "resilience_state.json"
    if (Test-Path $resilienceFilePath) {
        Remove-Item -Path $resilienceFilePath -Force -ErrorAction SilentlyContinue
    }
    
    # Keep persistent tracking for next time
    Save-PersistentTracking
    
    Write-Log "=== ENHANCED Face Recognition Monitor Stopped ===" -Level "INFO"
    Write-Host "Monitor stopped. Processed $($global:CollectedRunFolders.Count) runs today." -ForegroundColor Yellow
    Write-Host "Daily run count: $($global:PersistentTracking.DailyRunCount)" -ForegroundColor Yellow
    Write-Host "Persistent tracking saved for recovery." -ForegroundColor Green
    Write-Host "Log file: $($Config.LogFile)" -ForegroundColor Yellow
}
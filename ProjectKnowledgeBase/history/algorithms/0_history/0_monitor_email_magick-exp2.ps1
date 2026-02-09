# old-monitor.ps1
<#
.SYNOPSIS
Time-based process monitor for Face Recognition pipeline with proper PID tracking.

.DESCRIPTION
Runs in background and manages the face recognition worker process based on schedule.
Tracks the actual Python process spawned by the worker script.

.NOTES
Configured for C:\RaihanFarid\Dokumen\faceRecog\process-run output structure
#>

# ====================================================================
# SECTION 1: INITIALIZATION AND CONFIGURATION
# ====================================================================

<#
.SYNOPSIS
Sets up portable paths for the project and validates all components exist
.DESCRIPTION
This SINGLE function does 3 things:
1. Finds the maskRecog project root
2. Builds all paths relative to it
3. Validates critical components exist
#>
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
        # Stop if we reach drive root (like C:\) or can't go further
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
        } catch {
            Write-Host "Note: Could not load shared configuration" -ForegroundColor Yellow
        }
    }
    
    # ====================================================================
    # STEP 2: BUILD PATHS RELATIVE TO PROJECT ROOT with Persistent Tracking Variables
    # ====================================================================
    
    # Store project root globally so all functions can use it
    $global:ProjectRoot = $projectRoot
    $global:ActiveRoot = Split-Path $projectRoot -Parent | Split-Path -Parent
    
    # Initialize global tracking variables
    Initialize-GlobalTrackingVariables
    
    # Show what we found
    Write-Host "Project Root: $ProjectRoot" -ForegroundColor Green
    Write-Host "Active Root: $ActiveRoot" -ForegroundColor Green
    
    # ====================================================================
    # STEP 3: UPDATE CONFIGURATION WITH RELATIVE PATHS
    # ====================================================================
    
    # Update the $Config object with relative paths
    $Script:Config = Get-ProjectConfiguration -ProjectRoot $ProjectRoot -ActiveRoot $ActiveRoot
    
    # ====================================================================
    # STEP 4: VALIDATE CRITICAL COMPONENTS EXIST
    # ====================================================================
    
    Write-Host "`nValidating project components..." -ForegroundColor Yellow
    
    $validationResult = Validate-ProjectComponents -Config $Config
    
    if ($validationResult.MissingComponents.Count -gt 0) {
        $continue = Read-Host "`nSome components are missing. Continue anyway? (Y/N)"
        if ($continue -notmatch '^[Yy]') {
            Write-Host "Exiting script..." -ForegroundColor Red
            exit 1
        }
    }
    
    Write-Host "`nProject initialization complete!" -ForegroundColor Green
    Write-Host "All paths are now portable and relative to:" -ForegroundColor Green
    Write-Host "  Project Root: $ProjectRoot" -ForegroundColor White
    
    # ====================================================================
    # STEP 5: Wait for key press with 60-second timeout
    # ====================================================================
    
    Invoke-StartupWait
    
    return $true
}

function Initialize-GlobalTrackingVariables {
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
        CollectedRunFolders = @()
    }

    $global:EmailAttachmentQueue = @()
    $global:CollectedRunFolders = @()
    $global:ForceStopAttempts = 0
    $global:LastForceStopTime = $null
    $global:ForceStopThreshold = 2
    $global:ForceStopWindowSeconds = 5
    $global:IsShuttingDown = $false
    
    # Process tracking variables
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
    
    # PID tracking structure
    $global:PIDTracking = @{
        WorkerPID = $null
        PythonPID = $null
        WorkerStartTime = $null
        PythonStartTime = $null
        RunFolder = $null
        LastUpdate = $null
    }
    
    # Sudden termination tracking
    $global:SuddenTerminationTracking = @{
        Events = @()
        CurrentStreak = 0
        LastCleanupDate = $null
        Statistics = @{
            TotalSuddenTerminations = 0
            TotalCleanups = 0
            LastCleanupReason = $null
            FirstEventDate = $null
            LastEventDate = $null
        }
    }
}

function Get-ProjectConfiguration {
    param(
        [string]$ProjectRoot,
        [string]$ActiveRoot
    )
    
    # Get email credential from user profile
    $emailCredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
    if (!(Test-Path (Split-Path $emailCredentialPath -Parent))) {
        New-Item -ItemType Directory -Path (Split-Path $emailCredentialPath -Parent) -Force | Out-Null
    }
    
    return @{
        # Schedule configuration
        StartTime = "08:00"
        EndTime = "17:02"
        
        # Worker script path - RELATIVE to project root
        WorkerScript = Join-Path $ProjectRoot "patterns\scripts\1_magick\maskDetect-portable.ps1"
        
        # Python script path - RELATIVE to project root  
        PythonScriptPath = Join-Path $ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
        
        # Paths for validation - RELATIVE to active root
        RunsBasePath = Join-Path $ActiveRoot "logs-running\magick"
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
        ProcessCheckInterval = 5
        GracefulShutdownTimeout = 60
        
        # PID tracking - RELATIVE to RunsBasePath
        PIDFilePath = Join-Path (Join-Path $ActiveRoot "logs-running\magick") "monitor_pid_Magick.json"
        MaxPIDFileAgeMinutes = 120
        
        # Logging - RELATIVE to RunsBasePath
        LogFile = Join-Path (Join-Path $ActiveRoot "logs-running\magick") "monitor_Magick.log"
        
        # Email notifications
        SendEmailOnCompletion = $true
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
        
        # Sudden termination tracking configuration
        SuddenTermination = @{
            TrackingFile = Join-Path (Join-Path $ActiveRoot "logs-running\magick") "sudden_termination_tracking.json"
            RecordRetentionDays = 30
            ConsecutiveThreshold = 3
            CleanupAction = "ForceCleanupAndNotify"
        }
    }
}

function Validate-ProjectComponents {
    param(
        [hashtable]$Config
    )
    
    $result = @{
        MissingComponents = @()
        CreatedDirectories = @()
    }
    
    $criticalComponents = @(
        @{ Name = "Worker Script"; Path = $Config.WorkerScript }
        @{ Name = "Python Script"; Path = $Config.PythonScriptPath }
        @{ Name = "Log Directory"; Path = (Split-Path $Config.LogFile -Parent) }
        @{ Name = "PID File Directory"; Path = (Split-Path $Config.PIDFilePath -Parent) }
    )
    
    foreach ($component in $criticalComponents) {
        if (!(Test-Path $component.Path)) {
            Write-Host "  [MISSING] $($component.Name): $($component.Path)" -ForegroundColor Red
            
            # Try to create missing directories
            if ($component.Name -match "Directory") {
                try {
                    New-Item -ItemType Directory -Path $component.Path -Force | Out-Null
                    Write-Host "  [CREATED] Directory: $($component.Path)" -ForegroundColor Yellow
                    $result.CreatedDirectories += $component.Path
                } catch {
                    $result.MissingComponents += $component.Name
                }
            } else {
                $result.MissingComponents += $component.Name
            }
        } else {
            Write-Host "  [OK] $($component.Name)" -ForegroundColor Green
        }
    }
    
    return $result
}

function Invoke-StartupWait {
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
}

# ====================================================================
# SECTION 2: LOGGING AND UTILITIES
# ====================================================================

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
    
    # Handle empty time string
    if ([string]::IsNullOrWhiteSpace($TargetTime)) {
        Write-Log "Empty time string provided to Test-TimeWindow" -Level "DEBUG"
        return $false
    }
    
    $now = Get-Date
    try {
        $target = [DateTime]::ParseExact($TargetTime.Trim(), "HH:mm", $null)
        return ($now.TimeOfDay -ge $target.TimeOfDay)
    } catch {
        Write-Log "Invalid time format: '$TargetTime'. Expected format: HH:mm" -Level "ERROR"
        return $false
    }
}

# ====================================================================
# SECTION 3: MAILKIT HANDLING
# ====================================================================

function Test-MailKitCompatibility {
    param([string]$DllPath)
    
    try {
        $fileInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($DllPath)
        
        $compatibility = @{
            FilePath = $DllPath
            FileVersion = $fileInfo.FileVersion
            ProductVersion = $fileInfo.ProductVersion
            IsCompatible = $false
            Issues = @()
            VersionSpecificNotes = @()
        }
        
        # Check for MailKit specifically
        if ($fileInfo.ProductName -like "*MailKit*") {
            if ($fileInfo.FileMajorPart -eq 4) {
                if ($fileInfo.FileMinorPart -ge 0) {
                    $compatibility.IsCompatible = $true
                    $compatibility.VersionSpecificNotes += "MailKit 4.x detected - API changes present"
                    $compatibility.VersionSpecificNotes += "TextPart constructor with string format supported"
                    $compatibility.VersionSpecificNotes += "ContentType is read-only - must use constructor"
                }
            } elseif ($fileInfo.FileMajorPart -ge 3) {
                $compatibility.IsCompatible = $true
                $compatibility.VersionSpecificNotes += "MailKit 3.x detected - compatible"
            } else {
                $compatibility.Issues += "Version $($fileInfo.FileVersion) is too old (need 3.0+)"
            }
        }
        # Check for MimeKit
        elseif ($fileInfo.ProductName -like "*MimeKit*") {
            if ($fileInfo.FileMajorPart -ge 3) {
                $compatibility.IsCompatible = $true
            } else {
                $compatibility.Issues += "MimeKit version $($fileInfo.FileVersion) is too old (need 3.0+)"
            }
        }
        
        return $compatibility
    } catch {
        Write-Log "Failed to check MailKit compatibility: $_" -Level "ERROR"
        return @{
            FilePath = $DllPath
            IsCompatible = $false
            Issues = @("Failed to read version info: $_")
        }
    }
}

function Test-MailKitAssembly {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$false)]
        [ValidateSet("Portable", "Global", "Auto")]
        [string]$VerificationMode = "Auto"
    )
    
    $verificationResult = @{
        IsAvailable = $false
        AssemblyLoadMethod = $null
        AssemblyVersion = $null
        MimeKitVersion = $null
        AssemblyPath = $null
        Issues = @()
        Warnings = @()
        Recommendations = @()
        DependenciesAvailable = $false
        LastChecked = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }
    
    Write-Log "Starting MailKit assembly verification..." -Level "INFO"
    
    try {
        # ====================================================================
        # STEP 1: Check if assemblies are already loaded
        # ====================================================================
        $allAssemblies = [AppDomain]::CurrentDomain.GetAssemblies()
        $mailKitLoaded = $allAssemblies | Where-Object { $_.FullName -like "MailKit, *" }
        $mimeKitLoaded = $allAssemblies | Where-Object { $_.FullName -like "MimeKit, *" }
        
        if ($mailKitLoaded -and $mimeKitLoaded) {
            Write-Log "MailKit is already loaded into current AppDomain" -Level "INFO"
            $verificationResult.IsAvailable = $true
            $verificationResult.AssemblyLoadMethod = "PreLoaded"
            $verificationResult.AssemblyVersion = $mailKitLoaded[0].GetName().Version.ToString()
            $verificationResult.MimeKitVersion = $mimeKitLoaded[0].GetName().Version.ToString()
            $verificationResult.DependenciesAvailable = $true
            
            Write-Log "  - MailKit Version: $($verificationResult.AssemblyVersion)" -Level "DEBUG"
            Write-Log "  - MimeKit Version: $($verificationResult.MimeKitVersion)" -Level "DEBUG"
            return $verificationResult
        }
        
        # ====================================================================
        # STEP 2: Portable Verification (DLLs in script directory)
        # ====================================================================
        if (($VerificationMode -eq "Portable") -or ($VerificationMode -eq "Auto")) {
            Write-Log "Checking for portable MailKit DLLs..." -Level "INFO"
            
            $scriptDir = $PSScriptRoot
            $mailKitDll = Join-Path $scriptDir "MailKit.dll"
            $mimeKitDll = Join-Path $scriptDir "MimeKit.dll"
            
            # Check if both DLLs exist
            $mailKitExists = Test-Path $mailKitDll
            $mimeKitExists = Test-Path $mimeKitDll
            
            if ($mailKitExists -and $mimeKitExists) {
                Write-Log "Found portable DLLs in script directory" -Level "INFO"
                
                # Get file info
                $mailKitFileInfo = Get-Item $mailKitDll
                $mimeKitFileInfo = Get-Item $mimeKitDll
                
                # Check file sizes are positive
                $mailKitValidSize = ($mailKitFileInfo.Length -gt 0)
                $mimeKitValidSize = ($mimeKitFileInfo.Length -gt 0)
                
                if ($mailKitValidSize -and $mimeKitValidSize) {
                    try {
                        # Test loading the assemblies
                        Write-Log "Testing assembly loading..." -Level "DEBUG"
                        
                        # Load MimeKit first (dependency)
                        Add-Type -Path $mimeKitDll -ErrorAction Stop
                        Write-Log "  - MimeKit loaded successfully" -Level "DEBUG"
                        
                        # Then load MailKit
                        Add-Type -Path $mailKitDll -ErrorAction Stop
                        Write-Log "  - MailKit loaded successfully" -Level "DEBUG"
                        
                        # Get version information
                        $loadedAssemblies = [AppDomain]::CurrentDomain.GetAssemblies()
                        $mailKitAssembly = $loadedAssemblies | Where-Object { $_.Location -and $_.Location -eq $mailKitDll } | Select-Object -First 1
                        $mimeKitAssembly = $loadedAssemblies | Where-Object { $_.Location -and $_.Location -eq $mimeKitDll } | Select-Object -First 1
                        
                        if ($mailKitAssembly -and $mimeKitAssembly) {
                            $verificationResult.IsAvailable = $true
                            $verificationResult.AssemblyLoadMethod = "Portable"
                            $verificationResult.AssemblyVersion = $mailKitAssembly.GetName().Version.ToString()
                            $verificationResult.MimeKitVersion = $mimeKitAssembly.GetName().Version.ToString()
                            $verificationResult.AssemblyPath = $scriptDir
                            $verificationResult.DependenciesAvailable = $true
                            
                            Write-Log "Portable MailKit verification PASSED" -Level "SUCCESS"
                            Write-Log "  - Assembly Path: $scriptDir" -Level "DEBUG"
                            Write-Log "  - MailKit Version: $($verificationResult.AssemblyVersion)" -Level "DEBUG"
                            Write-Log "  - MimeKit Version: $($verificationResult.MimeKitVersion)" -Level "DEBUG"
                            
                            return $verificationResult
                        }
                    } catch {
                        $errorMsg = "Failed to load portable DLLs: $($_.Exception.Message)"
                        Write-Log $errorMsg -Level "ERROR"
                        $verificationResult.Issues += $errorMsg
                        $verificationResult.Recommendations += "Check if DLLs are corrupted or incompatible"
                    }
                }
            }
        }
        
        # ====================================================================
        # STEP 3: Global/GAC Verification
        # ====================================================================
        if (($VerificationMode -eq "Global") -or (($VerificationMode -eq "Auto") -and (-not $verificationResult.IsAvailable))) {
            Write-Log "Checking for globally installed MailKit..." -Level "INFO"
            
            try {
                # Try to load from GAC/System
                Add-Type -AssemblyName "MimeKit" -ErrorAction Stop
                Write-Log "  - MimeKit loaded from GAC" -Level "DEBUG"
                
                Add-Type -AssemblyName "MailKit" -ErrorAction Stop
                Write-Log "  - MailKit loaded from GAC" -Level "DEBUG"
                
                # Get version information
                $loadedAssemblies = [AppDomain]::CurrentDomain.GetAssemblies()
                $mailKitAssembly = $loadedAssemblies | Where-Object { $_.FullName -like "MailKit, *" } | Select-Object -First 1
                $mimeKitAssembly = $loadedAssemblies | Where-Object { $_.FullName -like "MimeKit, *" } | Select-Object -First 1
                
                if ($mailKitAssembly -and $mimeKitAssembly) {
                    $verificationResult.IsAvailable = $true
                    $verificationResult.AssemblyLoadMethod = "Global"
                    $verificationResult.AssemblyVersion = $mailKitAssembly.GetName().Version.ToString()
                    $verificationResult.MimeKitVersion = $mimeKitAssembly.GetName().Version.ToString()
                    $verificationResult.DependenciesAvailable = $true
                    
                    Write-Log "Global MailKit verification PASSED" -Level "SUCCESS"
                    Write-Log "  - MailKit Version: $($verificationResult.AssemblyVersion)" -Level "DEBUG"
                    Write-Log "  - MimeKit Version: $($verificationResult.MimeKitVersion)" -Level "DEBUG"
                    
                    return $verificationResult
                }
            } catch {
                $errorMsg = "Failed to load from GAC: $($_.Exception.Message)"
                Write-Log $errorMsg -Level "WARN"
                $verificationResult.Issues += $errorMsg
            }
        }
        
        # ====================================================================
        # STEP 4: Verification Failed - Provide detailed analysis
        # ====================================================================
        if (-not $verificationResult.IsAvailable) {
            Write-Log "MailKit assembly verification FAILED" -Level "ERROR"
            
            # Check for common issues
            if ($verificationResult.Issues.Count -eq 0) {
                $verificationResult.Issues += "No MailKit assembly found in any searched location"
            }
            
            # Provide specific recommendations
            $verificationResult.Recommendations += "Download MailKit.dll and MimeKit.dll from NuGet"
            $verificationResult.Recommendations += "Place both DLLs in: $PSScriptRoot"
            $verificationResult.Recommendations += "Verify .NET Framework 4.7.2+ or .NET Core 2.0+ is installed"
            
            # Log detailed failure report
            Write-Log "Detailed failure report:" -Level "ERROR"
            Write-Log "  - Issues found: $($verificationResult.Issues.Count)" -Level "ERROR"
            foreach ($issue in $verificationResult.Issues) {
                Write-Log "    * $issue" -Level "ERROR"
            }
        }
        
    } catch {
        $errorMsg = "Unexpected error during MailKit verification: $($_.Exception.Message)"
        Write-Log $errorMsg -Level "ERROR"
        $verificationResult.Issues += $errorMsg
    }
    
    return $verificationResult
}

function Get-MailKitVersionInfo {
    try {
        $allAssemblies = [AppDomain]::CurrentDomain.GetAssemblies()
        $mailKitAssembly = $allAssemblies | Where-Object { $_.FullName -like "MailKit, *" } | Select-Object -First 1
        $mimeKitAssembly = $allAssemblies | Where-Object { $_.FullName -like "MimeKit, *" } | Select-Object -First 1
        
        $info = @{
            MailKitVersion = if ($mailKitAssembly) { $mailKitAssembly.GetName().Version.ToString() } else { "Unknown" }
            MimeKitVersion = if ($mimeKitAssembly) { $mimeKitAssembly.GetName().Version.ToString() } else { "Unknown" }
            MailKitMajorVersion = if ($mailKitAssembly) { $mailKitAssembly.GetName().Version.Major } else { 0 }
            MimeKitMajorVersion = if ($mimeKitAssembly) { $mimeKitAssembly.GetName().Version.Major } else { 0 }
            IsVersion4OrHigher = $false
            CompatibilityNotes = @()
        }
        
        # Check for MailKit 4.0+
        if ($info.MailKitMajorVersion -ge 4) {
            $info.IsVersion4OrHigher = $true
            $info.CompatibilityNotes += "MailKit 4.0+ detected - using updated BodyBuilder API"
        } else {
            $info.CompatibilityNotes += "MailKit 3.x detected - using legacy Multipart API"
        }
        
        return $info
    } catch {
        Write-Log "Failed to get MailKit version info: $_" -Level "ERROR"
        return @{
            MailKitVersion = "Unknown"
            MimeKitVersion = "Unknown"
            IsVersion4OrHigher = $false
            CompatibilityNotes = @("Error detecting version")
        }
    }
}

function Get-MailKitStatusReport {
    [CmdletBinding()]
    param()
    
    Write-Log "Generating MailKit status report..." -Level "INFO"
    
    # Initialize report with safe defaults
    $report = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        AssemblyStatus = @{
            IsAvailable = $false
            AssemblyLoadMethod = "Unknown"
            AssemblyVersion = "Unknown"
            MimeKitVersion = "Unknown"
            DependenciesAvailable = $false
            Issues = @()
            Warnings = @()
            Recommendations = @()
        }
        ConfigurationStatus = @{
            EmailEnabled = if ($Config.SendEmailOnCompletion -ne $null) { $Config.SendEmailOnCompletion } else { $false }
            SmtpConfigured = -not [string]::IsNullOrWhiteSpace($Config.SmtpServer)
            CredentialFileExists = Test-Path $Config.EmailCredentialPath
            RecipientsConfigured = ($Config.EmailRecipients -and $Config.EmailRecipients.Count -gt 0)
            SmtpServer = if ($Config.SmtpServer) { $Config.SmtpServer } else { "Not configured" }
            SmtpPort = if ($Config.SmtpPort) { $Config.SmtpPort } else { 0 }
            UseSSL = if ($Config.UseSSL -ne $null) { $Config.UseSSL } else { $true }
        }
        SystemInfo = @{
            PowerShellVersion = $PSVersionTable.PSVersion.ToString()
            CLRVersion = if ($PSVersionTable.CLRVersion) { $PSVersionTable.CLRVersion.ToString() } else { "Unknown" }
            OS = [System.Environment]::OSVersion.VersionString
            HostName = $env:COMPUTERNAME
        }
        Recommendations = @()
        OverallStatus = "ERROR"
    }
    
    try {
        # Get assembly status with error handling
        $assemblyStatus = Test-MailKitAssembly -VerificationMode "Auto"
        
        if ($assemblyStatus -and ($assemblyStatus.GetType().Name -eq 'Hashtable')) {
            $report.AssemblyStatus = $assemblyStatus
        } else {
            Write-Log "MailKit assembly test returned invalid result" -Level "WARN"
            $report.AssemblyStatus.IsAvailable = $false
            $report.AssemblyStatus.Issues += "Assembly test returned invalid result"
            $report.AssemblyStatus.Recommendations += "Reinstall MailKit and MimeKit DLLs"
        }
        
        # Determine overall status with safe checks
        $assemblyAvailable = $report.AssemblyStatus.IsAvailable
        $emailEnabled = $report.ConfigurationStatus.EmailEnabled
        $smtpConfigured = $report.ConfigurationStatus.SmtpConfigured
        $credentialExists = $report.ConfigurationStatus.CredentialFileExists
        
        if ($assemblyAvailable -and $emailEnabled -and $smtpConfigured -and $credentialExists) {
            $report.OverallStatus = "READY"
        } elseif (-not $assemblyAvailable) {
            $report.OverallStatus = "MISSING_ASSEMBLY"
            $report.Recommendations += "MailKit assembly not found. Install or provide DLLs."
        } elseif (-not $emailEnabled) {
            $report.OverallStatus = "EMAIL_DISABLED"
        } elseif (-not $smtpConfigured) {
            $report.OverallStatus = "SMTP_NOT_CONFIGURED"
            $report.Recommendations += "Configure SMTP server in configuration"
        } elseif (-not $credentialExists) {
            $report.OverallStatus = "CREDENTIAL_MISSING"
            $report.Recommendations += "Create credential file at: $($Config.EmailCredentialPath)"
        } else {
            $report.OverallStatus = "UNKNOWN"
        }
        
    } catch {
        Write-Log "Error in Get-MailKitStatusReport: $_" -Level "ERROR"
        $report.OverallStatus = "ERROR"
        $report.Recommendations += "Error checking MailKit status: $_"
    }
    
    return $report
}

function Write-MailKitStatusLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$false)]
        [string]$LogFile = $null
    )
    
    if ([string]::IsNullOrWhiteSpace($LogFile)) {
        $LogFile = $Config.LogFile
    }
    
    $statusReport = Get-MailKitStatusReport
    
    # SAFE property access with defaults
    $assemblyStatus = if ($statusReport.AssemblyStatus) { $statusReport.AssemblyStatus } else { @{ IsAvailable = $false } }
    $isAvailable = if ($assemblyStatus.IsAvailable -ne $null) { $assemblyStatus.IsAvailable } else { $false }
    $loadMethod = if ($assemblyStatus.AssemblyLoadMethod) { $assemblyStatus.AssemblyLoadMethod } else { 'Unknown' }
    $mailKitVersion = if ($assemblyStatus.AssemblyVersion) { $assemblyStatus.AssemblyVersion } else { 'Unknown' }
    $mimeKitVersion = if ($assemblyStatus.MimeKitVersion) { $assemblyStatus.MimeKitVersion } else { 'Unknown' }
    $depsAvailable = if ($assemblyStatus.DependenciesAvailable -ne $null) { $assemblyStatus.DependenciesAvailable } else { $false }
    
    $logEntry = @"
=== MAILKIT STATUS REPORT ===
Timestamp: $($statusReport.Timestamp)
Overall Status: $($statusReport.OverallStatus)

ASSEMBLY STATUS:
- Available: $isAvailable
- Load Method: $loadMethod
- MailKit Version: $mailKitVersion
- MimeKit Version: $mimeKitVersion
- Dependencies: $depsAvailable

CONFIGURATION STATUS:
- Email Enabled: $($statusReport.ConfigurationStatus.EmailEnabled)
- SMTP Configured: $($statusReport.ConfigurationStatus.SmtpConfigured)
- Credential File: $($statusReport.ConfigurationStatus.CredentialFileExists)
- Recipients: $($statusReport.ConfigurationStatus.RecipientsConfigured)
- SMTP Server: $($statusReport.ConfigurationStatus.SmtpServer)
- SMTP Port: $($statusReport.ConfigurationStatus.SmtpPort)
- SSL: $($statusReport.ConfigurationStatus.UseSSL)

SYSTEM INFORMATION:
- PowerShell: $($statusReport.SystemInfo.PowerShellVersion)
- CLR: $($statusReport.SystemInfo.CLRVersion)
- OS: $($statusReport.SystemInfo.OS)
- Host: $($statusReport.SystemInfo.HostName)

RECOMMENDATIONS:
$($statusReport.Recommendations -join "`n")
"@
    
    try {
        Add-Content -Path $LogFile -Value $logEntry -ErrorAction SilentlyContinue
        Write-Log "MailKit status report written to log" -Level "INFO"
    } catch {
        Write-Log "Failed to write MailKit status report: $_" -Level "ERROR"
    }
}

function Send-Email {
    param(
        [string[]]$To,
        [string]$From,
        [string]$Subject,
        [string]$Body,
        [string]$SmtpServer,
        [int]$Port,
        [bool]$UseSsl,
        [System.Management.Automation.PSCredential]$Credential,
        [string[]]$Attachments
    )
    
    # First try MailKit
    $mailKitResult = Send-MailKitEmail @PSBoundParameters
    
    if ($mailKitResult) {
        return $true
    }
    
    # If MailKit fails, try System.Net.Mail fallback
    Write-Log "MailKit failed, attempting System.Net.Mail fallback..." -Level "WARN"
    return Send-SystemNetMailEmail @PSBoundParameters
}

function Send-MailKitEmail {
    param(
        [string[]]$To,
        [string]$From,
        [string]$Subject,
        [string]$Body,
        [string]$SmtpServer,
        [int]$Port,
        [bool]$UseSsl,
        [System.Management.Automation.PSCredential]$Credential,
        [string[]]$Attachments
    )
    
    try {
        # Get version info first
        $versionInfo = Get-MailKitVersionInfo
        
        # Load MailKit assembly with fallback
        $assemblyLoaded = $false
        try {
            Add-Type -Path "MailKit.dll" -ErrorAction Stop
            $assemblyLoaded = $true
        } catch {
            try {
                Add-Type -AssemblyName "MailKit" -ErrorAction Stop
                $assemblyLoaded = $true
            } catch {
                Write-Log "MailKit assembly not found" -Level "WARN"
                return $false
            }
        }
        
        if (-not $assemblyLoaded) {
            return $false
        }
        
        # Create MIME message
        $message = New-Object MimeKit.MimeMessage
        $message.From.Add([MimeKit.InternetAddress]::Parse($From))
        
        foreach ($recipient in $To) {
            $message.To.Add([MimeKit.InternetAddress]::Parse($recipient))
        }
        
        $message.Subject = $Subject
        
        # Handle MailKit 4.0+ API changes
        if ($versionInfo.IsVersion4OrHigher) {
            Write-Log "Using MailKit 4.0+ API for message construction" -Level "DEBUG"
            
            # MailKit 4.0+ approach
            $bodyBuilder = New-Object MimeKit.BodyBuilder
            
            if ($Body -match '<.*>') {
                # HTML content
                $bodyBuilder.HtmlBody = $Body
            } else {
                # Plain text content
                $bodyBuilder.TextBody = $Body
            }
            
            # Add attachments if any
            if ($Attachments.Count -gt 0) {
                foreach ($attachmentPath in $Attachments) {
                    if (Test-Path $attachmentPath) {
                        $bodyBuilder.Attachments.Add($attachmentPath)
                        Write-Log "Added attachment using BodyBuilder: $attachmentPath" -Level "DEBUG"
                    }
                }
            }
            
            $message.Body = $bodyBuilder.ToMessageBody()
            
        } else {
            # MailKit 3.x approach (backward compatibility)
            Write-Log "Using MailKit 3.x API for message construction" -Level "DEBUG"
            
            # Create body part
            if ($Body -match '<.*>') {
                # HTML content
                $bodyPart = New-Object MimeKit.TextPart("html")
                $bodyPart.Text = $Body
            } else {
                # Plain text content
                $bodyPart = New-Object MimeKit.TextPart("plain")
                $bodyPart.Text = $Body
            }
            
            # Handle attachments for MailKit 3.x
            if ($Attachments.Count -gt 0) {
                $multipart = New-Object MimeKit.Multipart("mixed")
                $multipart.Add($bodyPart)
                
                foreach ($attachmentPath in $Attachments) {
                    if (Test-Path $attachmentPath) {
                        $attachment = New-MimeKitAttachment -FilePath $attachmentPath
                        if ($attachment) {
                            $multipart.Add($attachment)
                        }
                    }
                }
                
                $message.Body = $multipart
            } else {
                $message.Body = $bodyPart
            }
        }
        
        # Send email using MailKit SmtpClient
        $client = New-Object MailKit.Net.Smtp.SmtpClient
        
        try {
            Write-Log "Connecting to SMTP server ${SmtpServer}:${Port} (SSL: ${UseSsl})..." -Level "DEBUG"
            
            # Connect to SMTP server
            if ($Port -eq 587) {
                # Port 587 requires STARTTLS
                $client.Connect($SmtpServer, $Port, [MailKit.Security.SecureSocketOptions]::StartTls)
            } elseif ($UseSsl) {
                # Port 465 or other SSL ports
                $client.Connect($SmtpServer, $Port, [MailKit.Security.SecureSocketOptions]::SslOnConnect)
            } else {
                # No SSL
                $client.Connect($SmtpServer, $Port, [MailKit.Security.SecureSocketOptions]::None)
            }
            
            # Authenticate
            $networkCredential = $Credential.GetNetworkCredential()
            Write-Log "Authenticating as $($networkCredential.UserName)..." -Level "DEBUG"
            
            $client.Authenticate($networkCredential.UserName, $networkCredential.Password)
            
            # Send email
            Write-Log "Sending email..." -Level "DEBUG"
            $client.Send($message)
            
            # Disconnect
            $client.Disconnect($true)
            
            Write-Log "Email sent successfully using MailKit" -Level "SUCCESS"
            return $true
            
        } catch {
            Write-Log "MailKit SMTP error: $($_.Exception.Message)" -Level "ERROR"
            return $false
        }
        
    } catch {
        Write-Log "Failed to send email using MailKit: $($_.Exception.Message)" -Level "ERROR"
        return $false
    }
}

function Send-SystemNetMailEmail {
    param(
        [string[]]$To,
        [string]$From,
        [string]$Subject,
        [string]$Body,
        [string]$SmtpServer,
        [int]$Port,
        [bool]$UseSsl,
        [System.Management.Automation.PSCredential]$Credential,
        [string[]]$Attachments
    )
    
    try {
        Write-Log "Attempting fallback email using System.Net.Mail..." -Level "WARN"
        
        # Create mail message
        $mailMessage = New-Object System.Net.Mail.MailMessage
        $mailMessage.From = New-Object System.Net.Mail.MailAddress($From)
        
        foreach ($recipient in $To) {
            $mailMessage.To.Add($recipient)
        }
        
        $mailMessage.Subject = $Subject
        $mailMessage.Body = $Body
        $mailMessage.IsBodyHtml = $Body -match '<.*>'
        
        # Add attachments
        foreach ($attachmentPath in $Attachments) {
            if (Test-Path $attachmentPath) {
                $attachment = New-Object System.Net.Mail.Attachment($attachmentPath)
                $mailMessage.Attachments.Add($attachment)
                Write-Log "Added attachment: $attachmentPath" -Level "DEBUG"
            }
        }
        
        # Create SMTP client
        $smtpClient = New-Object System.Net.Mail.SmtpClient($SmtpServer, $Port)
        $smtpClient.EnableSsl = $UseSsl
        $smtpClient.Timeout = 30000
        
        # Set credentials
        $networkCredential = $Credential.GetNetworkCredential()
        $smtpClient.Credentials = New-Object System.Net.NetworkCredential($networkCredential.UserName, $networkCredential.Password)
        
        # Send email
        $smtpClient.Send($mailMessage)
        
        # Cleanup
        $mailMessage.Dispose()
        if ($smtpClient -ne $null) {
            $smtpClient.Dispose()
        }
        
        Write-Log "Fallback email sent successfully using System.Net.Mail" -Level "SUCCESS"
        return $true
        
    } catch {
        Write-Log "Fallback email also failed: $_" -Level "ERROR"
        return $false
    }
}

function New-MimeKitAttachment {
    param(
        [string]$FilePath,
        [string]$MimeType = "application/octet-stream"
    )
    
    try {
        if (-not (Test-Path $FilePath)) {
            throw "File not found: $FilePath"
        }
        
        $fileName = [System.IO.Path]::GetFileName($FilePath)
        
        # Try MailKit 4.0+ approach first
        try {
            # Method 1: Create with explicit content type
            $contentType = New-Object MimeKit.ContentType($MimeType)
            $contentType.Name = $fileName
            
            $attachment = New-Object MimeKit.MimePart
            $attachment.ContentType = $contentType
            
            # Set other properties
            $disposition = New-Object MimeKit.ContentDisposition([MimeKit.ContentDisposition]::Attachment)
            $disposition.FileName = $fileName
            $attachment.ContentDisposition = $disposition
            
            $attachment.ContentTransferEncoding = [MimeKit.ContentEncoding]::Base64
            
            $fileStream = [System.IO.File]::OpenRead($FilePath)
            $attachment.Content = New-Object MimeKit.MimeContent($fileStream)
            
            Write-Log "Created attachment using MailKit 4.0+ API" -Level "DEBUG"
            return $attachment
            
        } catch {
            # Fallback: Try MailKit 3.0 approach
            Write-Log "MailKit 4.0+ API failed, trying 3.0 compatible approach..." -Level "DEBUG"
            
            $attachment = New-Object MimeKit.MimePart
            
            # For MailKit 3.0, we can set ContentType.MediaType and ContentType.MediaSubtype
            $attachment.ContentType.MediaType = $MimeType.Split('/')[0]
            $attachment.ContentType.MediaSubtype = $MimeType.Split('/')[1]
            $attachment.ContentType.Parameters.Add("name", $fileName)
            
            $disposition = New-Object MimeKit.ContentDisposition([MimeKit.ContentDisposition]::Attachment)
            $disposition.Parameters.Add("filename", $fileName)
            $attachment.ContentDisposition = $disposition
            
            $attachment.ContentTransferEncoding = [MimeKit.ContentEncoding]::Base64
            
            $fileStream = [System.IO.File]::OpenRead($FilePath)
            $attachment.Content = New-Object MimeKit.MimeContent($fileStream)
            
            Write-Log "Created attachment using MailKit 3.0 compatible API" -Level "DEBUG"
            return $attachment
        }
        
    } catch {
        Write-Log "Failed to create MimeKit attachment: $_" -Level "ERROR"
        return $null
    }
}

function Test-MailKitDLLs {
    param(
        [string]$ScriptDir = $PSScriptRoot
    )
    
    Write-Host "Testing MailKit DLLs in: $ScriptDir" -ForegroundColor Cyan
    
    $mailKitDll = Join-Path $ScriptDir "MailKit.dll"
    $mimeKitDll = Join-Path $ScriptDir "MimeKit.dll"
    
    # Check if files exist
    if (-not (Test-Path $mailKitDll)) {
        Write-Host "ERROR: MailKit.dll not found at: $mailKitDll" -ForegroundColor Red
        return $false
    }
    
    if (-not (Test-Path $mimeKitDll)) {
        Write-Host "ERROR: MimeKit.dll not found at: $mimeKitDll" -ForegroundColor Red
        return $false
    }

    # Check compatibility
    Write-Host "`nChecking DLL compatibility..." -ForegroundColor Cyan
    
    $mailKitCompat = Test-MailKitCompatibility -DllPath $mailKitDll
    $mimeKitCompat = Test-MailKitCompatibility -DllPath $mimeKitDll
    
    if (-not $mailKitCompat.IsCompatible) {
        Write-Host "ERROR: MailKit DLL compatibility issues:" -ForegroundColor Red
        foreach ($issue in $mailKitCompat.Issues) {
            Write-Host "  - $issue" -ForegroundColor Red
        }
    }
    
    if (-not $mimeKitCompat.IsCompatible) {
        Write-Host "ERROR: MimeKit DLL compatibility issues:" -ForegroundColor Red
        foreach ($issue in $mimeKitCompat.Issues) {
            Write-Host "  - $issue" -ForegroundColor Red
        }
    }    
    
    Write-Host "✓ Both DLL files found" -ForegroundColor Green
    
    # Check file sizes
    $mailKitSize = (Get-Item $mailKitDll).Length
    $mimeKitSize = (Get-Item $mimeKitDll).Length
    
    Write-Host "  MailKit.dll size: $([math]::Round($mailKitSize/1KB, 2)) KB" -ForegroundColor Gray
    Write-Host "  MimeKit.dll size: $([math]::Round($mimeKitSize/1KB, 2)) KB" -ForegroundColor Gray
    
    if ($mailKitSize -eq 0 -or $mimeKitSize -eq 0) {
        Write-Host "ERROR: One or both DLLs have zero file size" -ForegroundColor Red
        return $false
    }
    
    Write-Host "✓ File sizes are valid" -ForegroundColor Green
    
    # Try to load the assemblies
    try {
        Write-Host "Attempting to load MimeKit..." -ForegroundColor Yellow
        Add-Type -Path $mimeKitDll -ErrorAction Stop
        Write-Host "✓ MimeKit loaded successfully" -ForegroundColor Green
        
        Write-Host "Attempting to load MailKit..." -ForegroundColor Yellow
        Add-Type -Path $mailKitDll -ErrorAction Stop
        Write-Host "✓ MailKit loaded successfully" -ForegroundColor Green
        
        # Get version info
        $assemblies = [AppDomain]::CurrentDomain.GetAssemblies()
        $mailKitAssembly = $assemblies | Where-Object { $_.Location -and $_.Location -eq $mailKitDll }
        $mimeKitAssembly = $assemblies | Where-Object { $_.Location -and $_.Location -eq $mimeKitDll }
        
        if ($mailKitAssembly) {
            $version = $mailKitAssembly.GetName().Version
            Write-Host "✓ MailKit Version: $version" -ForegroundColor Green
        }
        
        if ($mimeKitAssembly) {
            $version = $mimeKitAssembly.GetName().Version
            Write-Host "✓ MimeKit Version: $version" -ForegroundColor Green
        }
        
        Write-Host "`nSUCCESS: All MailKit tests passed!" -ForegroundColor Green
        return $true
        
    } catch {
        Write-Host "ERROR: Failed to load DLLs: $_" -ForegroundColor Red
        Write-Host "Stack trace: $($_.ScriptStackTrace)" -ForegroundColor Red
        return $false
    }
}

# ====================================================================
# SECTION 4: SUDDEN TERMINATION HANDLING
# ====================================================================

function Register-SuddenTermination {
    param(
        [string]$Reason,
        [string]$TerminationType = "Unexpected",
        [hashtable]$ProcessInfo = @{}
    )
    
    $event = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Reason = $Reason
        TerminationType = $TerminationType
        ProcessInfo = $ProcessInfo
        ScriptVersion = "2.0"
        HostName = $env:COMPUTERNAME
    }
    
    # Add to events list
    $SuddenTerminationTracking.Events += $event
    
    # Update statistics
    $SuddenTerminationTracking.Statistics.TotalSuddenTerminations++
    $SuddenTerminationTracking.Statistics.LastEventDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    if (-not $SuddenTerminationTracking.Statistics.FirstEventDate) {
        $SuddenTerminationTracking.Statistics.FirstEventDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }
    
    # Calculate streak - check if last event was also a sudden termination
    if ($SuddenTerminationTracking.Events.Count -gt 1) {
        $lastEvent = $SuddenTerminationTracking.Events[-2]
        $lastEventTime = [DateTime]::ParseExact($lastEvent.Timestamp, "yyyy-MM-dd HH:mm:ss", $null)
        $currentTime = Get-Date
        
        # If last sudden termination was within 5 minutes, consider it consecutive
        if (($currentTime - $lastEventTime).TotalMinutes -le 5) {
            $SuddenTerminationTracking.CurrentStreak++
            Write-Log "Consecutive sudden termination detected. Streak: $($SuddenTerminationTracking.CurrentStreak)" -Level "WARN"
        } else {
            # Reset streak if more than 5 minutes have passed
            $SuddenTerminationTracking.CurrentStreak = 1
            Write-Log "New sudden termination streak started" -Level "INFO"
        }
    } else {
        $SuddenTerminationTracking.CurrentStreak = 1
    }
    
    # Check if we need to take action based on consecutive sudden terminations
    if ($SuddenTerminationTracking.CurrentStreak -ge $Config.SuddenTermination.ConsecutiveThreshold) {
        Write-Log "Sudden termination streak threshold reached ($($SuddenTerminationTracking.CurrentStreak) consecutive). Taking cleanup action." -Level "ERROR"
        Invoke-StreakThresholdAction
    }
    
    # Save tracking data
    Save-SuddenTerminationTracking
    
    return $event
}

function Save-SuddenTerminationTracking {
    try {
        # Clean up old events beyond retention period
        $retentionDate = (Get-Date).AddDays(-$Config.SuddenTermination.RecordRetentionDays)
        $filteredEvents = @()
        
        foreach ($event in $SuddenTerminationTracking.Events) {
            $eventTime = [DateTime]::ParseExact($event.Timestamp, "yyyy-MM-dd HH:mm:ss", $null)
            if ($eventTime -ge $retentionDate) {
                $filteredEvents += $event
            }
        }
        
        $SuddenTerminationTracking.Events = $filteredEvents
        
        # Save to file
        $SuddenTerminationTracking | ConvertTo-Json -Depth 5 | Out-File -FilePath $Config.SuddenTermination.TrackingFile -Force
        Write-Log "Sudden termination tracking saved" -Level "DEBUG"
    } catch {
        Write-Log "Failed to save sudden termination tracking: $_" -Level "ERROR"
    }
}

function Load-SuddenTerminationTracking {
    if (-not (Test-Path $Config.SuddenTermination.TrackingFile)) {
        Write-Log "No sudden termination tracking file found" -Level "DEBUG"
        return $false
    }
    
    try {
        $loaded = Get-Content -Path $Config.SuddenTermination.TrackingFile -Raw | ConvertFrom-Json
        
        # Convert back to hashtable and update global variable
        $global:SuddenTerminationTracking = @{
            Events = @($loaded.Events)
            CurrentStreak = $loaded.CurrentStreak
            LastCleanupDate = $loaded.LastCleanupDate
            Statistics = @{
                TotalSuddenTerminations = $loaded.Statistics.TotalSuddenTerminations
                TotalCleanups = $loaded.Statistics.TotalCleanups
                LastCleanupReason = $loaded.Statistics.LastCleanupReason
                FirstEventDate = $loaded.Statistics.FirstEventDate
                LastEventDate = $loaded.Statistics.LastEventDate
            }
        }
        
        Write-Log "Loaded sudden termination tracking: $($SuddenTerminationTracking.Statistics.TotalSuddenTerminations) total events, current streak: $($SuddenTerminationTracking.CurrentStreak)" -Level "INFO"
        return $true
    } catch {
        Write-Log "Failed to load sudden termination tracking: $_" -Level "ERROR"
        return $false
    }
}

function Invoke-StreakThresholdAction {
    $action = $Config.SuddenTermination.CleanupAction
    $streak = $SuddenTerminationTracking.CurrentStreak
    
    Write-Log "Executing cleanup action '$action' for streak of $streak consecutive sudden terminations" -Level "WARN"
    
    switch ($action) {
        "ForceCleanupAndNotify" {
            # Force cleanup of all processes
            Force-CleanupOrphanedProcesses
            
            # Update statistics
            $SuddenTerminationTracking.Statistics.TotalCleanups++
            $SuddenTerminationTracking.Statistics.LastCleanupReason = "ConsecutiveSuddenTerminations"
            $SuddenTerminationTracking.LastCleanupDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            
            # Reset streak after cleanup
            $SuddenTerminationTracking.CurrentStreak = 0
            
            # Send notification if email is configured
            if ($Config.SendEmailOnCompletion) {
                Send-StreakNotification -StreakCount $streak -ActionTaken $action
            }
            
            Save-SuddenTerminationTracking
        }
        
        "ForceCleanupOnly" {
            Force-CleanupOrphanedProcesses
            $SuddenTerminationTracking.CurrentStreak = 0
            Save-SuddenTerminationTracking
        }
        
        "LogOnly" {
            Write-Log "Logging threshold reached but no action taken (config: LogOnly)" -Level "WARN"
        }
        
        default {
            Write-Log "Unknown cleanup action: $action" -Level "ERROR"
        }
    }
}

function Force-CleanupOrphanedProcesses {
    Write-Log "Starting forced cleanup of orphaned processes..." -Level "WARN"
    
    $cleanedProcesses = @()
    
    # Clean up any Python processes with our script
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue | 
        Where-Object { $_.Path -like "*python*" }
    
    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Config.PythonScriptPath)*") {
                Write-Log "Forcefully terminating orphaned Python process (PID: $($proc.Id))" -Level "WARN"
                $proc.Kill()
                if ($proc.WaitForExit(5000)) {
                    $cleanedProcesses += "Python:$($proc.Id)"
                }
            }
        } catch {
            Write-Log "Error cleaning up Python process $($proc.Id): $_" -Level "ERROR"
        }
    }
    
    # Clean up worker PowerShell processes
    $workerProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "*powershell*" }
    
    foreach ($proc in $workerProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Config.WorkerScript)*") {
                Write-Log "Forcefully terminating orphaned worker process (PID: $($proc.Id))" -Level "WARN"
                $proc.Kill()
                if ($proc.WaitForExit(5000)) {
                    $cleanedProcesses += "Worker:$($proc.Id)"
                }
            }
        } catch {
            Write-Log "Error cleaning up worker process $($proc.Id): $_" -Level "ERROR"
        }
    }
    
    # Clean up PID tracking file if it exists
    if (Test-Path $Config.PIDFilePath) {
        try {
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            Write-Log "Cleaned up PID tracking file" -Level "INFO"
        } catch {
            Write-Log "Failed to clean up PID tracking file: $_" -Level "ERROR"
        }
    }
    
    # Reset global process variables
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false
    
    Write-Log "Forced cleanup completed. Cleaned processes: $($cleanedProcesses.Count)" -Level "INFO"
    
    if ($cleanedProcesses.Count -gt 0) {
        Write-Log "Details: $($cleanedProcesses -join ', ')" -Level "INFO"
    }
    
    return $cleanedProcesses
}

function Send-StreakNotification {
    param(
        [int]$StreakCount,
        [string]$ActionTaken
    )
    
    if (-not $Config.SendEmailOnCompletion) {
        return $false
    }
    
    try {
        # Load credentials
        $credential = $null
        if (Test-Path $Config.EmailCredentialPath) {
            $credential = Import-Clixml -Path $Config.EmailCredentialPath
        } else {
            return $false
        }
        
        $subject = "ALERT: $StreakCount Consecutive Sudden Terminations - Face Recognition Monitor"
        
        $body = @"
URGENT: CONSECUTIVE SUDDEN TERMINATIONS ALERT
=============================================

ALERT DETAILS
-------------
Alert Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Streak Count: $StreakCount consecutive sudden terminations
Action Taken: $ActionTaken
Host: $($env:COMPUTERNAME)

STATISTICS
----------
Total Sudden Terminations: $($SuddenTerminationTracking.Statistics.TotalSuddenTerminations)
Current Streak: $($SuddenTerminationTracking.CurrentStreak)
Total Cleanups Performed: $($SuddenTerminationTracking.Statistics.TotalCleanups)
First Event: $($SuddenTerminationTracking.Statistics.FirstEventDate)
Last Event: $($SuddenTerminationTracking.Statistics.LastEventDate)

RECENT EVENTS (Last 5)
----------------------
$($SuddenTerminationTracking.Events[-5..-1] | ForEach-Object {
    "- $($_.Timestamp): $($_.Reason) ($($_.TerminationType))"
} | Join-String -Separator "`n")

AUTOMATIC ACTIONS
-----------------
The system has automatically performed cleanup of orphaned processes.
Please check the monitor log for details: $($Config.LogFile)

RECOMMENDATIONS
---------------
1. Check system resources (CPU, Memory, Disk)
2. Verify network connectivity if applicable
3. Review recent changes to scripts or configurations
4. Check for conflicting processes
5. Monitor system event logs for errors

MONITOR STATUS
--------------
Worker PID: $(if ($WorkerPID) {$WorkerPID} else {'Not Running'})
Python PID: $(if ($PythonPID) {$PythonPID} else {'Not Running'})
Schedule: $($Config.StartTime) - $($Config.EndTime)

"@
        
        # Send to all configured recipients
        $recipients = $Config.EmailRecipients | ForEach-Object { $_.Address }
        
        $emailSent = Send-Email -To $recipients -From $Config.EmailFrom `
            -Subject $subject -Body $body -SmtpServer $Config.SmtpServer `
            -Port $Config.SmtpPort -UseSsl $Config.UseSSL -Credential $credential
        
        if ($emailSent) {
            Write-Log "Streak notification sent to $($recipients.Count) recipients" -Level "INFO"
            return $true
        }
        
        return $false
    } catch {
        Write-Log "Failed to send streak notification: $_" -Level "ERROR"
        return $false
    }
}

function Initialize-CleanupOnStartup {
    Write-Log "Performing startup cleanup check..." -Level "INFO"
    
    # Load sudden termination tracking
    Load-SuddenTerminationTracking
    
    # Check for orphaned processes
    $orphanedProcesses = @()
    
    # Check Python processes
    $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue | 
        Where-Object { $_.Path -like "*python*" }
    
    foreach ($proc in $pythonProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Config.PythonScriptPath)*") {
                $orphanedProcesses += @{
                    Type = "Python"
                    PID = $proc.Id
                    StartTime = $proc.StartTime
                }
            }
        } catch { }
    }
    
    # Check worker processes
    $workerProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "*powershell*" }
    
    foreach ($proc in $workerProcesses) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*$($Config.WorkerScript)*") {
                $orphanedProcesses += @{
                    Type = "Worker"
                    PID = $proc.Id
                    StartTime = $proc.StartTime
                }
            }
        } catch { }
    }
    
    # If we found orphaned processes, clean them up
    if ($orphanedProcesses.Count -gt 0) {
        Write-Log "Found $($orphanedProcesses.Count) orphaned process(es) from previous run" -Level "WARN"
        
        foreach ($orphan in $orphanedProcesses) {
            Write-Log "  - $($orphan.Type) process (PID: $($orphan.PID), Started: $($orphan.StartTime))" -Level "WARN"
        }
        
        # Register a sudden termination event
        Register-SuddenTermination -Reason "Orphaned processes found on startup" `
            -TerminationType "StartupCleanup" `
            -ProcessInfo @{ OrphanedProcesses = $orphanedProcesses }
        
        # Clean up the orphaned processes
        Force-CleanupOrphanedProcesses
        
        return $true
    }
    
    Write-Log "No orphaned processes found on startup" -Level "INFO"
    return $false
}

function Handle-UnexpectedTermination {
    param(
        [string]$Reason,
        [System.Management.Automation.ErrorRecord]$ErrorRecord = $null
    )
    
    Write-Log "Handling unexpected termination: $Reason" -Level "ERROR"
    
    if ($ErrorRecord) {
        Write-Log "Error details: $($ErrorRecord.Exception.Message)" -Level "ERROR"
        Write-Log "Stack trace: $($ErrorRecord.ScriptStackTrace)" -Level "ERROR"
    }
    
    # Capture current process state before cleanup
    $processState = @{
        WorkerPID = $WorkerPID
        PythonPID = $PythonPID
        WorkerRunning = $WorkerIsRunning
        PythonRunning = $PythonIsRunning
        RunFolder = $CurrentRunFolder
    }
    
    # Register the sudden termination
    Register-SuddenTermination -Reason $Reason `
        -TerminationType "Unexpected" `
        -ProcessInfo $processState
    
    # Perform cleanup
    Stop-WorkerProcess
    
    # Additional cleanup for PID file
    if (Test-Path $Config.PIDFilePath) {
        try {
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            Write-Log "Cleaned up PID tracking file after unexpected termination" -Level "INFO"
        } catch {
            Write-Log "Failed to clean up PID file: $_" -Level "ERROR"
        }
    }
    
    # Save final state
    Save-SuddenTerminationTracking
}

function Invoke-GracefulShutdown {
    param(
        [string]$Reason = "Normal shutdown"
    )
    
    Write-Log "Initiating graceful shutdown: $Reason" -Level "INFO"
    
    try {
        # Stop worker process
        Stop-WorkerProcess
        
        # Save final tracking data
        Save-SuddenTerminationTracking
        
        # Clear streak on successful shutdown
        $SuddenTerminationTracking.CurrentStreak = 0
        Save-SuddenTerminationTracking
        
        Write-Log "Graceful shutdown completed successfully" -Level "SUCCESS"
    } catch {
        Write-Log "Error during graceful shutdown: $_" -Level "ERROR"
        Register-SuddenTermination -Reason "Error during graceful shutdown: $_" -TerminationType "ShutdownError"
    }
}

# ====================================================================
# SECTION 5: PROCESS MANAGEMENT
# ====================================================================

function Register-ConsoleControlHandler {
    <#
    .SYNOPSIS
    Registers a handler for console control events (Ctrl+C, Ctrl+Break)
    #>
    
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
        param([int]$eventType)
        
        $currentTime = Get-Date
        $timeSinceLast = if ($global:LastForceStopTime) { 
            ($currentTime - $global:LastForceStopTime).TotalSeconds 
        } else { 
            [double]::MaxValue 
        }
        
        switch ($eventType) {
            { $_ -in 0, 1 } {  # Ctrl+C or Ctrl+Break
                Write-Host "`n[Console Control Handler] Control event detected" -ForegroundColor Yellow
                
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
                    return $true
                } else {
                    # First attempt or single Ctrl+C - just log and continue
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
    $global:PersistentTracking.CollectedRunFolders = $global:CollectedRunFolders
    
    # Add current process state to history
    $currentState = @{
        Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        PythonPID = $PythonPID
        WorkerPID = $WorkerPID
        RunFolder = $CurrentRunFolder
        PythonRunning = $PythonIsRunning
        WorkerRunning = $WorkerIsRunning
        ForceStopAttempts = $global:ForceStopAttempts
        CollectedFoldersCount = $global:CollectedRunFolders.Count
    }
    
    $global:PersistentTracking.ProcessStopHistory += $currentState
    
    # Keep only last 50 entries
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
                CollectedRunFolders = @($loadedData.CollectedRunFolders)
            }
            
            # Restore collected folders to global variable
            $global:CollectedRunFolders = @($loadedData.CollectedRunFolders)
            
            Write-Log "Loaded persistent tracking with $($global:PersistentTracking.CollectedRunFolders.Count) collected folders" -Level "INFO"
            
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
        
        # Try to validate the folder
        $runFolderObj = Get-Item $LastKnownFolder -ErrorAction SilentlyContinue
        if ($runFolderObj) {
            $validation = @{
                Success = $true
                RunFolder = $LastKnownFolder
                FolderName = $runFolderObj.Name
                CreationTime = $runFolderObj.CreationTime
            }
            
            # Collect this orphaned run
            $runData = Collect-RunFolderAttachments -RunFolder $LastKnownFolder
            if ($runData.Attachments.Count -gt 0) {
                # Check if we already have this folder
                $existingIndex = $global:CollectedRunFolders | 
                    Where-Object { $_.RunFolder -eq $runData.RunFolder } | 
                    Select-Object -First 1
                
                if (-not $existingIndex) {
                    $global:CollectedRunFolders += $runData
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
        
        # Create a basic validation result
        $validation = @{
            Success = $true
            RunFolder = $CurrentRunFolder
            FolderName = Split-Path $CurrentRunFolder -Leaf
            CreationTime = (Get-Item $CurrentRunFolder).CreationTime
        }
        
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
                    Write-Log "Collected run on stop: $($runData.RunFolderName)" -Level "SUCCESS"
                }
            }
        }
    } else {
        # If no current run folder, try to find the latest one
        Write-Log "No current run folder, finding latest..." -Level "DEBUG"
        $latestFolder = Find-LatestRunFolder
        if ($latestFolder) {
            Write-Log "Validating latest run folder on stop: $(Split-Path $latestFolder.FullName -Leaf)" -Level "DEBUG"
            
            $validation = @{
                Success = $true
                RunFolder = $latestFolder.FullName
                FolderName = $latestFolder.Name
                CreationTime = $latestFolder.CreationTime
            }
            
            if ($validation.Success) {
                $runData = Collect-RunFolderAttachments -RunFolder $latestFolder.FullName
                if ($runData.Attachments.Count -gt 0) {
                    # Check if we already have this folder
                    $existingIndex = $global:CollectedRunFolders | 
                        Where-Object { $_.RunFolder -eq $runData.RunFolder } | 
                        Select-Object -First 1
                    
                    if (-not $existingIndex) {
                        $global:CollectedRunFolders += $runData
                        Write-Log "Collected latest run on stop: $($runData.RunFolderName)" -Level "SUCCESS"
                    }
                }
            }
        }
    }
    
    # Save all state
    Save-PIDTracking
    Save-PersistentTracking
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

function Save-PIDTracking {
    # Enhanced to include persistent tracking data
    
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
    
    # Add persistent tracking data
    $PIDTracking.PersistentTracking = @{
        LastKnownRunFolder = $CurrentRunFolder
        LastKnownPythonPID = $PythonPID
        LastKnownWorkerPID = $WorkerPID
        DailyRunCount = $global:PersistentTracking.DailyRunCount
        LastSuccessfulRun = $global:PersistentTracking.LastSuccessfulRun
        CollectedFoldersCount = $global:CollectedRunFolders.Count
    }
    
    try {
        $PIDTracking | ConvertTo-Json -Depth 10 | Out-File -FilePath $Config.PIDFilePath -Force
        Write-Log "Enhanced PID tracking saved with $($global:CollectedRunFolders.Count) collected folders" -Level "DEBUG"
        
        # Also save persistent tracking separately
        Save-PersistentTracking
    } catch {
        Write-Log "Failed to save enhanced PID tracking: $_" -Level "ERROR"
    }
}

function Load-PIDTracking {
    if (-not (Test-Path $Config.PIDFilePath)) {
        Write-Log "No PID tracking file found" -Level "DEBUG"
        
        # Try to load persistent tracking separately
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
        
        # Restore PID tracking
        $global:PIDTracking = @{
            WorkerPID = $loaded.WorkerPID
            PythonPID = $loaded.PythonPID
            WorkerStartTime = $loaded.WorkerStartTime
            PythonStartTime = $loaded.PythonStartTime
            RunFolder = $loaded.RunFolder
            LastUpdate = $loaded.LastUpdate
        }
        
        # Restore global variables
        $global:WorkerPID = $loaded.WorkerPID
        $global:PythonPID = $loaded.PythonPID
        $global:CurrentRunFolder = $loaded.RunFolder
        
        # Convert string times back to DateTime
        if ($loaded.WorkerStartTime) {
            try {
                $global:WorkerStartTime = [DateTime]::ParseExact($loaded.WorkerStartTime, "yyyy-MM-dd HH:mm:ss", $null)
            } catch { }
        }
        
        if ($loaded.PythonStartTime) {
            try {
                $global:PythonStartTime = [DateTime]::ParseExact($loaded.PythonStartTime, "yyyy-MM-dd HH:mm:ss", $null)
            } catch { }
        }
        
        # Enhanced: Load persistent tracking data from PID file
        if ($loaded.PSObject.Properties.Name -contains "PersistentTracking") {
            $global:PersistentTracking.LastKnownRunFolder = $loaded.PersistentTracking.LastKnownRunFolder
            $global:PersistentTracking.LastKnownPythonPID = $loaded.PersistentTracking.LastKnownPythonPID
            $global:PersistentTracking.LastKnownWorkerPID = $loaded.PersistentTracking.LastKnownWorkerPID
            $global:PersistentTracking.DailyRunCount = $loaded.PersistentTracking.DailyRunCount
            $global:PersistentTracking.LastSuccessfulRun = $loaded.PersistentTracking.LastSuccessfulRun
        }
        
        Write-Log "Enhanced PID tracking loaded with $($global:CollectedRunFolders.Count) collected folders" -Level "INFO"
        
        # Also load separate persistent tracking file for history
        Load-PersistentTracking | Out-Null
        
        return $true
        
    } catch {
        Write-Log "Failed to load enhanced PID tracking: $_" -Level "ERROR"
        Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
        
        # Try to load persistent tracking anyway
        Load-PersistentTracking | Out-Null
        
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
    
    # Enhanced: Check for unexpected process stops
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

# ====================================================================
# SECTION 6: VALIDATION AND OUTPUT
# ====================================================================

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

# ====================================================================
# SECTION 7: EMAIL AND NOTIFICATION
# ====================================================================

function Send-CompletionEmail {
    param(
        [string]$RunFolder,
        [object]$ValidationResult,
        [array]$AllAttachments = @() # parameter for all collected attachments
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
        
        # Modify attachment collection to use AllAttachments if provided
        if ($AllAttachments.Count -gt 0) {
            $attachments = $AllAttachments
            Write-Log "Using pre-collected attachments: $($attachments.Count) files" -Level "INFO"
        } else {
            # Original attachment collection logic
            $attachments = @()
            $completionSummaryPath = Join-Path $RunFolder "Magick_Process_*\logs\completion_summary.txt"
            if (Test-Path $completionSummaryPath) {
                $attachments += $completionSummaryPath
            }
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
        
        # Get MailKit version info
        $mailKitVersionInfo = Get-MailKitVersionInfo
        
        # Determine which email function to use
        $useMailKit = $mailKitVersionInfo.MailKitMajorVersion -ge 3
        
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
            
            $emailSent = $false
            
            if ($useMailKit) {
                Write-Log "Using MailKit v$($mailKitVersionInfo.MailKitVersion) for email sending" -Level "INFO"
                $emailSent = Send-MailKitEmail -To $recipients -From $Config.EmailFrom -Subject $emailContent.Subject -Body $emailContent.Body `
                    -SmtpServer $Config.SmtpServer -Port $Config.SmtpPort -UseSsl $Config.UseSSL -Credential $credential -Attachments $attachments
            } else {
                Write-Log "MailKit not available, using System.Net.Mail fallback" -Level "WARN"
                $emailSent = Send-SystemNetMailEmail -To $recipients -From $Config.EmailFrom -Subject $emailContent.Subject -Body $emailContent.Body `
                    -SmtpServer $Config.SmtpServer -Port $Config.SmtpPort -UseSsl $Config.UseSSL -Credential $credential -Attachments $attachments
            }
            
            if ($emailSent) {
                $successCount += $recipients.Count
                Write-Log "Successfully sent $language email to $($recipients.Count) recipient(s)" -Level "SUCCESS"
            } else {
                $failCount += $recipients.Count
                Write-Log "Failed to send $language email to $($recipients.Count) recipient(s)" -Level "ERROR"
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
- Log Files: $($validationResult.Details.LogFiles.Count)
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

function Test-EmailAddress {
    param([string]$Email)
    
    try {
        $mailAddress = New-Object System.Net.Mail.MailAddress $Email
        return $mailAddress.Address -eq $Email
    } catch {
        return $false
    }
}

function Test-EmailConfiguration {
    if (-not $Config.SendEmailOnCompletion) {
        Write-Log "Email notifications on completion are disabled" -Level "INFO"
        return $false
    }
    
    Write-Log "Testing email configuration with enhanced MailKit verification..." -Level "INFO"
    
    $checksPassed = $true
    
    try {
        # Get MailKit status report with error handling
        $detailedReport = Get-MailKitStatusReport
        if (-not $detailedReport) {
            Write-Log "ERROR: Failed to get MailKit status report" -Level "ERROR"
            return $false
        }
        
        # Log the detailed status report
        Write-MailKitStatusLog
        
        # ====================================================================
        # STEP 1: Check MailKit Assembly with SAFE property access
        # ====================================================================
        Write-Log "Verifying MailKit assembly..." -Level "INFO"
        
        $assemblyStatus = $detailedReport.AssemblyStatus
        if (-not $assemblyStatus) {
            Write-Log "ERROR: MailKit assembly status is null" -Level "ERROR"
            $checksPassed = $false
        } elseif (-not $assemblyStatus.IsAvailable) {
            Write-Log "ERROR: MailKit assembly is not available" -Level "ERROR"
            $checksPassed = $false
            
            # Provide specific troubleshooting based on assembly test results
            if ($assemblyStatus.Issues -and $assemblyStatus.Issues.Count -gt 0) {
                Write-Log "Assembly issues detected:" -Level "ERROR"
                foreach ($issue in $assemblyStatus.Issues) {
                    Write-Log "  - $issue" -Level "ERROR"
                }
            }
            
            Write-Log "RECOMMENDATIONS:" -Level "WARN"
            if ($assemblyStatus.Recommendations -and $assemblyStatus.Recommendations.Count -gt 0) {
                foreach ($recommendation in $assemblyStatus.Recommendations) {
                    Write-Log "  - $recommendation" -Level "WARN"
                }
            } else {
                Write-Log "  - Install MailKit and MimeKit assemblies" -Level "WARN"
            }
        } else {
            Write-Log "MailKit assembly verification PASSED" -Level "SUCCESS"
            Write-Log "  - Load Method: $(if ($assemblyStatus.AssemblyLoadMethod) {$assemblyStatus.AssemblyLoadMethod} else {'Unknown'})" -Level "INFO"
            Write-Log "  - MailKit Version: $(if ($assemblyStatus.AssemblyVersion) {$assemblyStatus.AssemblyVersion} else {'Unknown'})" -Level "INFO"
            Write-Log "  - MimeKit Version: $(if ($assemblyStatus.MimeKitVersion) {$assemblyStatus.MimeKitVersion} else {'Unknown'})" -Level "INFO"
        }
        
        # ====================================================================
        # STEP 2: Check SMTP Configuration
        # ====================================================================
        Write-Log "Verifying SMTP configuration..." -Level "INFO"
        
        if ([string]::IsNullOrWhiteSpace($Config.SmtpServer)) {
            Write-Log "ERROR: SMTP server not configured" -Level "ERROR"
            $checksPassed = $false
        } else {
            Write-Log "SMTP configuration verification PASSED" -Level "SUCCESS"
            Write-Log "  - Server: $($Config.SmtpServer):$($Config.SmtpPort)" -Level "INFO"
            Write-Log "  - SSL: $($Config.UseSSL)" -Level "INFO"
        }
        
        # ====================================================================
        # STEP 3: Check Email Recipients
        # ====================================================================
        Write-Log "Verifying email recipients..." -Level "INFO"
        
        if ($null -eq $Config.EmailRecipients -or $Config.EmailRecipients.Count -eq 0) {
            Write-Log "ERROR: No email recipients configured" -Level "ERROR"
            $checksPassed = $false
        } else {
            Write-Log "Found $($Config.EmailRecipients.Count) email recipient(s)" -Level "SUCCESS"
            
            # Validate each recipient
            foreach ($recipient in $Config.EmailRecipients) {
                if ([string]::IsNullOrWhiteSpace($recipient.Address)) {
                    Write-Log "ERROR: Recipient has empty email address" -Level "ERROR"
                    $checksPassed = $false
                } elseif (-not (Test-EmailAddress -Email $recipient.Address)) {
                    Write-Log "WARNING: Invalid email address format: $($recipient.Address)" -Level "WARN"
                }
                
                if ([string]::IsNullOrWhiteSpace($recipient.Language)) {
                    Write-Log "WARNING: Recipient $($recipient.Address) has no language specified, defaulting to English" -Level "WARN"
                    $recipient.Language = "English"
                }
            }
        }
        
        # ====================================================================
        # STEP 4: Check Credential File
        # ====================================================================
        Write-Log "Verifying email credentials..." -Level "INFO"
        
        if (Test-Path $Config.EmailCredentialPath) {
            try {
                $credential = Import-Clixml -Path $Config.EmailCredentialPath
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
                
                if ($userName -and $hasPassword) {
                    Write-Log "Email credential verification PASSED" -Level "SUCCESS"
                    Write-Log "  - Credential file: $($Config.EmailCredentialPath)" -Level "INFO"
                }
            } catch {
                Write-Log "ERROR: Failed to load email credential: $_" -Level "ERROR"
                $checksPassed = $false
            }
        } else {
            Write-Log "ERROR: Email credential file not found at $($Config.EmailCredentialPath)" -Level "ERROR"
            Write-Log "To create credential file, run in PowerShell:" -Level "INFO"
            Write-Log "  `$cred = Get-Credential" -Level "INFO"
            Write-Log "  `$cred | Export-Clixml -Path '$($Config.EmailCredentialPath)'" -Level "INFO"
            $checksPassed = $false
        }
        
        # ====================================================================
        # STEP 5: Gmail-specific Warnings (if applicable)
        # ====================================================================
        if ($Config.SmtpServer -like "*gmail*") {
            Write-Log "GMAIL CONFIGURATION NOTES:" -Level "INFO"
            Write-Log "- Using SMTP: $($Config.SmtpServer):$($Config.SmtpPort)" -Level "INFO"
            Write-Log "- SSL Enabled: $($Config.UseSSL)" -Level "INFO"
            Write-Log "- Ensure you're using an App Password, not your regular password" -Level "INFO"
            Write-Log "- Gmail attachment limit: 25 MB total" -Level "INFO"
            Write-Log "- Enable 2-Step Verification in Google Account" -Level "INFO"
            Write-Log "- Generate App Password: https://myaccount.google.com/apppasswords" -Level "INFO"
        }
        
        # ====================================================================
        # STEP 6: Summary and Optional Test Email - MODIFIED: Skip user input
        # ====================================================================
        if ($checksPassed) {
            Write-Log "Email configuration validation COMPLETE" -Level "SUCCESS"
            Write-Log "Overall status: $(if ($detailedReport.OverallStatus) {$detailedReport.OverallStatus} else {'Unknown'})" -Level "INFO"
            Write-Log "Skipping interactive test email prompt as per configuration" -Level "INFO"
            return $true
        } else {
            Write-Log "Email configuration validation FAILED" -Level "ERROR"
            Write-Log "Emails will not be sent until configuration is fixed." -Level "ERROR"
            Write-Log "Check the MailKit status report in the log file for details." -Level "INFO"
            
            # Show quick reference for fixing common issues
            Write-Host "`nQUICK FIX REFERENCE:" -ForegroundColor Red
            Write-Host "1. MailKit Assembly: Download from https://www.nuget.org/packages/MailKit/" -ForegroundColor Yellow
            Write-Host "2. Place MailKit.dll and MimeKit.dll in: $PSScriptRoot" -ForegroundColor Yellow
            Write-Host "3. Create credential: `$cred = Get-Credential; `$cred | Export-Clixml -Path '$($Config.EmailCredentialPath)'" -ForegroundColor Yellow
            
            return $false
        }
        
    } catch {
        Write-Log "Error in Test-EmailConfiguration: $_" -Level "ERROR"
        Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
        return $false
    }
}

# ====================================================================
# SECTION 8: UI AND STATUS
# ====================================================================

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
    
    # Show MailKit status with safe property access
    try {
        $mailKitStatus = Get-MailKitStatusReport
        if ($mailKitStatus) {
            $mailKitColor = if ($mailKitStatus.OverallStatus -eq 'READY') { 'Green' } 
                            elseif ($mailKitStatus.OverallStatus -eq 'EMAIL_DISABLED') { 'Gray' }
                            else { 'Red' }
            Write-Host "MailKit Status: $($mailKitStatus.OverallStatus)" -ForegroundColor $mailKitColor
            
            if ($mailKitStatus.AssemblyStatus -and $mailKitStatus.AssemblyStatus.IsAvailable) {
                Write-Host "  Version: $(if ($mailKitStatus.AssemblyStatus.AssemblyVersion) {$mailKitStatus.AssemblyStatus.AssemblyVersion} else {'Unknown'})" -ForegroundColor White
            }
        }
    } catch {
        Write-Host "MailKit Status: ERROR" -ForegroundColor Red
    }
    Write-Host ""
    
    # Show sudden termination streak info
    if ($SuddenTerminationTracking.CurrentStreak -gt 0) {
        Write-Host "Sudden Termination Streak: $($SuddenTerminationTracking.CurrentStreak)" -ForegroundColor $(if ($SuddenTerminationTracking.CurrentStreak -ge $Config.SuddenTermination.ConsecutiveThreshold) { 'Red' } else { 'Yellow' })
        Write-Host "Threshold: $($Config.SuddenTermination.ConsecutiveThreshold)" -ForegroundColor Gray
        Write-Host ""
    }
    
    if ($status.PythonRunning) {
        Write-Host "PYTHON STATUS: RUNNING" -ForegroundColor Green
        Write-Host "  PID: $PythonPID" -ForegroundColor White
        
        # FIX: Add validation for PythonStartTime
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

# ====================================================================
# SECTION 9: RECOVERY AND ERROR HANDLING
# ====================================================================

# Enhanced error recovery counter
$Script:ErrorRecoveryCount = 0
$Script:MaxErrorRecoveryAttempts = 3

function Invoke-SafeRecovery {
    param([string]$ErrorContext)
    
    Write-Log "Attempting safe recovery for: $ErrorContext" -Level "WARN"
    
    # Increment recovery counter
    $Script:ErrorRecoveryCount++
    
    # Stop any running processes
    Stop-WorkerProcess
    
    # Clear process tracking
    $global:WorkerProcess = $null
    $global:WorkerPID = $null
    $global:PythonPID = $null
    $global:WorkerIsRunning = $false
    $global:PythonIsRunning = $false
    
    # Clean up PID file if it exists
    if (Test-Path $Config.PIDFilePath) {
        try {
            Remove-Item -Path $Config.PIDFilePath -Force -ErrorAction SilentlyContinue
            Write-Log "Cleaned up PID tracking file during recovery" -Level "INFO"
        } catch {
            Write-Log "Failed to clean up PID file during recovery: $_" -Level "WARN"
        }
    }
    
    # Wait for system stabilization
    Start-Sleep -Seconds 5
    
    # Check if we should continue or exit
    if ($Script:ErrorRecoveryCount -ge $Script:MaxErrorRecoveryAttempts) {
        Write-Log "Maximum recovery attempts ($Script:MaxErrorRecoveryAttempts) reached. Exiting." -Level "ERROR"
        Register-SuddenTermination -Reason "Max recovery attempts reached" -TerminationType "RecoveryExhausted"
        exit 1
    }
    
    Write-Log "Recovery attempt $Script:ErrorRecoveryCount completed" -Level "INFO"
    return $true
}

# ====================================================================
# SECTION 10: MAIN EXECUTION
# ====================================================================

# Call initialization ONCE at the very beginning
Initialize-ProjectPortablePaths

# Run the MailKit DLL test
Test-MailKitDLLs

# Main execution
try {
    # Create log directory if it doesn't exist
    $logDir = Split-Path $Config.LogFile -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    
    Write-Log "=============== Face Recognition Monitor Started ===============" -Level "INFO"
    Write-Log "Monitor Version: 2.1 (Enhanced with MailKit Verification)" -Level "INFO"
    
    # Initialize error recovery
    $Script:ErrorRecoveryCount = 0
    
    Write-Log "Performing early MailKit assembly verification..." -Level "INFO"
    $mailKitStatus = Get-MailKitStatusReport
    
    if ($Config.SendEmailOnCompletion) {
        if ($mailKitStatus.OverallStatus -eq "READY") {
            Write-Log "MailKit is ready for email functionality" -Level "SUCCESS"
            Write-Log "  - Assembly: $($mailKitStatus.AssemblyStatus.AssemblyLoadMethod)" -Level "INFO"
            Write-Log "  - Version: $($mailKitStatus.AssemblyStatus.AssemblyVersion)" -Level "INFO"
        } else {
            Write-Log "MailKit status: $($mailKitStatus.OverallStatus)" -Level "WARN"
            
            if ($mailKitStatus.OverallStatus -eq "MISSING_ASSEMBLY") {
                Write-Log "Email functionality will be disabled due to missing MailKit assembly" -Level "ERROR"
                $Config.SendEmailOnCompletion = $false
            }
        }
    }
    
    # Initialize sudden termination tracking and cleanup
    Initialize-CleanupOnStartup
    
    # Test email configuration ONCE at startup
    $EmailConfigValid = Test-EmailConfiguration
    if ($EmailConfigValid) {
        Write-Log "Email configuration validated successfully" -Level "SUCCESS"
    }
    
    # Load existing PID tracking
    if (Load-PIDTracking) {
        Write-Log "Resumed monitoring of existing processes" -Level "SUCCESS"
        # Update process status
        Check-ProcessStatus | Out-Null
    }

    # Load persistent tracking
    Load-PersistentTracking
    
    # Check for orphaned runs
    Check-OrphanedRuns -LastKnownFolder $global:PersistentTracking.LastKnownRunFolder    
    
    # Ensure runs base path exists
    if (-not (Test-Path $Config.RunsBasePath)) {
        Write-Log "Creating runs base directory: $($Config.RunsBasePath)" -Level "WARN"
        New-Item -ItemType Directory -Path $Config.RunsBasePath -Force | Out-Null
    }
    
    # Clear console and show initial status
    Clear-Host
    
    # Register console control handler
    Register-ConsoleControlHandler
    
    # Main monitoring loop with recovery
    while ($true) {
        # Inside the main while loop, add collection logic:
        if ($processStatus.PythonRunning -and $CurrentRunFolder -and 
            (-not $global:CollectedRunFolders.Where({ $_.RunFolder -eq $CurrentRunFolder }))) {
            # Check if the run folder has a completion summary (indicating it's done)
            $completionPath = Join-Path $CurrentRunFolder "Magick_Process_*\logs\completion_summary.txt"
            if (Test-Path $completionPath) {
                Write-Log "Detected completed run, collecting data..." -Level "DEBUG"
                $runData = Collect-RunFolderAttachments -RunFolder $CurrentRunFolder
                if ($runData.Attachments.Count -gt 0) {
                    $global:CollectedRunFolders += $runData
                    Write-Log "Collected completed run: $($runData.RunFolderName)" -Level "INFO"
                    Save-PIDTracking
                }
            }
        }

        try {
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
                Write-Log "Check: $currentTime | Window: Active | Python: Stopped" -Level "DEBUG"
                Write-Log "Time window active and no Python process running - starting worker..." -Level "INFO"
                
                # Add delay to prevent rapid restart loops
                if ($LastWorkerAttempt -and ((Get-Date) - $LastWorkerAttempt).TotalSeconds -lt 10) { # Change this to reduce the cooldown time
                    Write-Log "Skipping worker start - too soon after last attempt (10s cooldown)" -Level "DEBUG"
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
            
            # Check if end time has passed and we should stop
            elseif ($endPassed) {
                # If Python is running, stop it and send email
                if ($processStatus.PythonRunning) {
                    Write-Log "End time reached - stopping processes..." -Level "INFO"
                    Stop-WorkerProcess
                    
                    # Wait for cleanup and output generation
                    Write-Log "Waiting for output generation..." -Level "INFO"
                    Start-Sleep -Seconds 10
                    
                    # Validate the last output
                    Write-Log "Validating final worker output..." -Level "INFO"
                    $LastValidation = Validate-Output
                    
                    # Collect data from the last run if not already collected
                    if ($LastValidation -and $LastValidation.Success -and $LastValidation.RunFolder) {
                        $runData = Collect-RunFolderAttachments -RunFolder $LastValidation.RunFolder
                        if ($runData.Attachments.Count -gt 0) {
                            # Check if we already have this folder
                            $existingIndex = $global:CollectedRunFolders | 
                                Where-Object { $_.RunFolder -eq $runData.RunFolder } | 
                                Select-Object -First 1
                            
                            if (-not $existingIndex) {
                                $global:CollectedRunFolders += $runData
                                Write-Log "Added final run to collection: $($runData.RunFolderName)" -Level "SUCCESS"
                                }
                            }
                        }
                        
                        # Send completion email if we have collected runs
                        if ($global:CollectedRunFolders.Count -gt 0) {
                            if ($Config.SendEmailOnCompletion -and $EmailConfigValid) {
                                # Send email with all collected runs
                                $allAttachments = @()
                                foreach ($run in $global:CollectedRunFolders) {
                                    $allAttachments += $run.Attachments
                                }
                                
                                # Remove duplicates
                                $allAttachments = $allAttachments | Select-Object -Unique
                                
                                # Send email
                                $emailSent = Send-CompletionEmail -RunFolder $LastValidation.RunFolder -ValidationResult $LastValidation -AllAttachments $allAttachments
                                if ($emailSent) {
                                    Write-Log "Completion emails sent successfully with $($global:CollectedRunFolders.Count) collected runs." -Level "SUCCESS"
                                }
                            }
                        } else {
                        Write-Log "Pipeline completed with validation issues" -Level "WARN"
                    }
                } else {
                    # No Python process running, just log and stop
                    Write-Log "End time reached - no active processes to stop" -Level "INFO"
                }

                # Clear collected data for next day
                $global:CollectedRunFolders = @()
                Save-PersistentTracking    
                
                # Perform graceful shutdown
                Invoke-GracefulShutdown -Reason "Schedule completed"
                
                # Stop the monitor
                Write-Log "Process completed. Stopping monitor as configured..." -Level "INFO"
                break
            }

        } catch {
            Write-Log "Error in main monitoring loop: $_" -Level "ERROR"
            Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "DEBUG"
            
            # Attempt recovery
            $recoverySuccess = Invoke-SafeRecovery -ErrorContext "Main loop error: $_"
            
            if (-not $recoverySuccess) {
                throw "Recovery failed after main loop error"
            }
            
            # Reset recovery counter on successful loop iteration
            $Script:ErrorRecoveryCount = 0
        }        
        
        # Wait before next check
        Start-Sleep -Seconds $Config.ProcessCheckInterval
    }
}
catch [System.Management.Automation.Host.HostException] {
    Write-Log "Monitor interrupted by user" -Level "INFO"
    Handle-UnexpectedTermination -Reason "User interrupted (Ctrl+C)"
}
catch {
    Write-Log "FATAL ERROR: $_" -Level "ERROR"
    Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
    Handle-UnexpectedTermination -Reason "Unhandled exception: $_" -ErrorRecord $_
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
    
    # Save final persistent tracking
    Save-PersistentTracking
    
    Write-Log "=============== Face Recognition Monitor Stopped ===============" -Level "INFO"
    Write-Host "Monitor stopped. Collected $($global:CollectedRunFolders.Count) runs." -ForegroundColor Yellow
    Write-Host "Persistent tracking saved for recovery." -ForegroundColor Green
}
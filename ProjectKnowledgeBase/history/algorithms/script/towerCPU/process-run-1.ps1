# script-organized-TowerCPU-0-complete.ps1
# ==============================================
# Complete version with all functions defined
# ==============================================

# ========== CONFIGURATION ==========
$VENV_ROOT = "D:\RaihanFarid\Dokumen\faceRecog\.venv"
$PYTHON_SCRIPT = "D:\RaihanFarid\Dokumen\faceRecog\run_py\modular\entry_multi-USED-TowerCPU.py"
# Base path for all runs
$RUNS_BASE_PATH = "D:\RaihanFarid\Dokumen\faceRecog\process-run"

$POWERSHELL_SCRIPT_NAME = Split-Path -Leaf $MyInvocation.MyCommand.Path

# Python parameters
$PYTHON_PARAMS = @{
    "--multi-source" = $null
}



# Email Configuration - SECURE VERSION
$EMAIL_CONFIG = @{
    Enabled = $true  # Set to $true after configuring
    #SmtpServer = "smtp.gmail.com"
    #SmtpPort = 587
    UseSsl = $true
    SenderEmail = "ikeepmypromiz@gmail.com"
    RecipientEmail = "faridraihan17@gmail.com"
    SubjectPrefix = "[FaceRecog Process]"
    CredentialMethod = "CredentialFile"
    PasswordEnvironmentVariable = "FACE_RECOG_EMAIL_PASSWORD"
    CredentialFilePath = "$env:USERPROFILE\.face-recog\email-credential.xml"
    CredentialManagerTarget = "FaceRecogEmail"
}

# Completion File Configuration
$COMPLETION_FILE_CONFIG = @{
    Enabled = $true
    FileName = "PROCESS_COMPLETE.txt"
    CheckDelaySeconds = 30
    MaxRetries = 6
}
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

function Get-Uptime {
    try {
        $os = Get-WmiObject Win32_OperatingSystem
        $uptime = (Get-Date) - ($os.ConvertToDateTime($os.LastBootUpTime))
        return $uptime
    } catch {
        try {
            $bootTime = (Get-CimInstance -ClassName Win32_OperatingSystem).LastBootUpTime
            return (Get-Date) - $bootTime
        } catch {
            return [TimeSpan]::Zero
        }
    }
}

function Format-TimeSpanForDisplay {
    param([TimeSpan]$TimeSpan)
    
    if ($TimeSpan.Days -gt 0) {
        return "$($TimeSpan.Days)d $($TimeSpan.Hours)h $($TimeSpan.Minutes)m $($TimeSpan.Seconds)s"
    } elseif ($TimeSpan.Hours -gt 0) {
        return "$($TimeSpan.Hours)h $($TimeSpan.Minutes)m $($TimeSpan.Seconds)s"
    } elseif ($TimeSpan.Minutes -gt 0) {
        return "$($TimeSpan.Minutes)m $($TimeSpan.Seconds)s"
    } else {
        return "$($TimeSpan.Seconds)s"
    }
}

function Get-SystemTimeInfo {
    $timeInfo = @{
        LocalTime = Get-Date
        UtcTime = (Get-Date).ToUniversalTime()
        TimeZone = [System.TimeZoneInfo]::Local
        Uptime = Get-Uptime
        SystemBootTime = (Get-Date).AddSeconds(-(Get-Uptime).TotalSeconds)
    }
    
    return $timeInfo
}
# ===================================

# ========== VALIDITY CHECK FUNCTIONS ==========
function Test-PathWithDetail {
    param(
        [string]$Path,
        [string]$PathType = "Any",
        [string]$Description = "Path"
    )
    
    $result = @{
        Valid = $false
        Path = $Path
        Description = $Description
        Type = $PathType
        Error = ""
        Details = @{}
    }
    
    if ([string]::IsNullOrWhiteSpace($Path)) {
        $result.Error = "Path is null or empty"
        return $result
    }
    
    try {
        if (Test-Path $Path) {
            $item = Get-Item $Path -ErrorAction Stop
            
            switch ($PathType) {
                "File" {
                    if ($item.PSIsContainer) {
                        $result.Error = "Path is a directory, but a file was expected"
                        $result.Details.ItemType = "Directory"
                    } else {
                        $result.Valid = $true
                        $result.Details.ItemType = "File"
                        $result.Details.Size = if ($item.Length) { "$([math]::Round($item.Length/1MB, 2)) MB" } else { "0 MB" }
                        $result.Details.LastModified = $item.LastWriteTime
                    }
                }
                "Directory" {
                    if (-not $item.PSIsContainer) {
                        $result.Error = "Path is a file, but a directory was expected"
                        $result.Details.ItemType = "File"
                    } else {
                        $result.Valid = $true
                        $result.Details.ItemType = "Directory"
                        $result.Details.ItemCount = @(Get-ChildItem $Path -Force -ErrorAction SilentlyContinue).Count
                        $result.Details.LastModified = $item.LastWriteTime
                    }
                }
                "Any" {
                    $result.Valid = $true
                    $result.Details.ItemType = if ($item.PSIsContainer) { "Directory" } else { "File" }
                    $result.Details.LastModified = $item.LastWriteTime
                }
            }
            
            if ($result.Valid) {
                $result.Details.FullPath = $item.FullName
                $result.Details.CreationTime = $item.CreationTime
                $result.Details.Attributes = $item.Attributes
            }
        } else {
            $result.Error = "Path does not exist"
            
            # Check if parent directory exists
            $parentDir = Split-Path $Path -Parent
            if (Test-Path $parentDir) {
                $result.Details.ParentExists = $true
                $result.Details.ParentPath = $parentDir
            } else {
                $result.Details.ParentExists = $false
            }
        }
    } catch {
        $result.Error = "Error testing path: $($_.Exception.Message)"
    }
    
    return $result
}

function Test-SystemRequirements {
    $results = @()
    
    # Check PowerShell version
    $psVersion = $PSVersionTable.PSVersion
    $results += @{
        Valid = $psVersion -ge [Version]"5.1"
        Description = "PowerShell Version"
        Details = @{Version = $psVersion.ToString()}
        Error = if ($psVersion -lt [Version]"5.1") { "PowerShell 5.1 or higher required" } else { "" }
    }
    
    # Check execution policy
    $executionPolicy = Get-ExecutionPolicy
    $results += @{
        Valid = $executionPolicy -in @("RemoteSigned", "Unrestricted", "Bypass")
        Description = "Execution Policy"
        Details = @{Policy = $executionPolicy}
        Error = if ($executionPolicy -notin @("RemoteSigned", "Unrestricted", "Bypass")) { 
            "Execution policy too restrictive. Current: $executionPolicy" 
        } else { "" }
    }
    
    return $results
}

function Test-VenvConfiguration {
    param([string]$VenvPath)
    
    $results = @()
    
    # Check virtual environment root
    $venvRootCheck = Test-PathWithDetail -Path $VenvPath -PathType "Directory" -Description "Virtual Environment Root"
    $results += $venvRootCheck
    
    if ($venvRootCheck.Valid) {
        # Check Python executable
        $pythonExe = "$VenvPath\Scripts\python.exe"
        $pythonCheck = Test-PathWithDetail -Path $pythonExe -PathType "File" -Description "Python Executable"
        $results += $pythonCheck
        
        # Check pip
        $pipExe = "$VenvPath\Scripts\pip.exe"
        $pipCheck = Test-PathWithDetail -Path $pipExe -PathType "File" -Description "Pip Executable"
        $results += $pipCheck
    }
    
    return $results
}

function Test-PythonScriptConfiguration {
    param([string]$ScriptPath)
    
    $results = @()
    
    # Check Python script exists
    $scriptCheck = Test-PathWithDetail -Path $ScriptPath -PathType "File" -Description "Python Script"
    $results += $scriptCheck
    
    if ($scriptCheck.Valid) {
        # Check if it's a Python file
        if ($ScriptPath -notmatch '\.py$') {
            $results += @{
                Valid = $false
                Path = $ScriptPath
                Description = "Python Script Extension"
                Error = "File does not have .py extension"
            }
        }
    }
    
    return $results
}

function Test-EmailConfiguration {
    param([hashtable]$Config)
    
    $results = @()
    
    if (-not $Config.Enabled) {
        $results += @{
            Valid = $true
            Description = "Email Configuration"
            Error = ""
            Details = @{Status = "Disabled"}
        }
        return $results
    }
    
    # Check required fields
    $requiredFields = @("SmtpServer", "SenderEmail", "RecipientEmail", "CredentialMethod")
    foreach ($field in $requiredFields) {
        $isValid = -not [string]::IsNullOrWhiteSpace($Config[$field])
        $results += @{
            Valid = $isValid
            Description = "Email $field"
            Error = if (-not $isValid) { "Field is empty" } else { "" }
            Details = @{Value = $Config[$field]}
        }
    }
    
    return $results
}

function Display-CheckResults {
    param([array]$Results)
    
    foreach ($result in $Results) {
        $status = if ($result.Valid) { "✓" } else { "✗" }
        $color = if ($result.Valid) { "Green" } else { "Red" }
        
        Write-Host "  $status $($result.Description)" -ForegroundColor $color
        if (-not $result.Valid -and -not [string]::IsNullOrEmpty($result.Error)) {
            Write-Host "    Error: $($result.Error)" -ForegroundColor Yellow
        }
        if ($result.Details.Count -gt 0 -and $result.Valid) {
            foreach ($detail in $result.Details.Keys) {
                if ($detail -ne "Exception") {
                    Write-Host "    $detail: $($result.Details[$detail])" -ForegroundColor Gray
                }
            }
        }
    }
}

function Run-ComprehensiveValidityChecks {
    Write-Host "`n=================================================="
    Write-Host "RUNNING COMPREHENSIVE VALIDITY CHECKS"
    Write-Host "=================================================="
    
    $allResults = @()
    $criticalFailures = @()
    
    # 1. System Requirements
    Write-Host "`n[1] Checking System Requirements..." -ForegroundColor Cyan
    $systemChecks = Test-SystemRequirements
    $allResults += $systemChecks
    $criticalFailures += $systemChecks | Where-Object { -not $_.Valid }
    Display-CheckResults $systemChecks
    
    # 2. Virtual Environment
    Write-Host "`n[2] Checking Virtual Environment..." -ForegroundColor Cyan
    $venvChecks = Test-VenvConfiguration -VenvPath $VENV_ROOT
    $allResults += $venvChecks
    $criticalFailures += $venvChecks | Where-Object { -not $_.Valid -and $_.Description -eq "Python Executable" }
    Display-CheckResults $venvChecks
    
    # 3. Python Script
    Write-Host "`n[3] Checking Python Script..." -ForegroundColor Cyan
    $scriptChecks = Test-PythonScriptConfiguration -ScriptPath $PYTHON_SCRIPT
    $allResults += $scriptChecks
    $criticalFailures += $scriptChecks | Where-Object { -not $_.Valid -and $_.Description -eq "Python Script" }
    Display-CheckResults $scriptChecks
    
    # 4. Runs Base Path
    Write-Host "`n[4] Checking Runs Base Path..." -ForegroundColor Cyan
    $runsPathCheck = Test-PathWithDetail -Path $RUNS_BASE_PATH -PathType "Directory" -Description "Runs Base Directory"
    $allResults += $runsPathCheck
    if (-not $runsPathCheck.Valid) {
        Write-Host "  Attempting to create directory..." -ForegroundColor Yellow
        try {
            New-Item -ItemType Directory -Path $RUNS_BASE_PATH -Force | Out-Null
            $runsPathCheck.Valid = $true
            $runsPathCheck.Error = ""
            $runsPathCheck.Details.Created = $true
            Write-Host "  ✓ Created directory successfully" -ForegroundColor Green
        } catch {
            $runsPathCheck.Error = "Failed to create directory: $_"
            $criticalFailures += $runsPathCheck
        }
    }
    Display-CheckResults @($runsPathCheck)
    
    # 5. Email Configuration
    Write-Host "`n[5] Checking Email Configuration..." -ForegroundColor Cyan
    $emailChecks = Test-EmailConfiguration -Config $EMAIL_CONFIG
    $allResults += $emailChecks
    Display-CheckResults $emailChecks
    
    # Summary
    Write-Host "`n=================================================="
    Write-Host "VALIDITY CHECK SUMMARY"
    Write-Host "=================================================="
    
    $totalChecks = $allResults.Count
    $passedChecks = ($allResults | Where-Object { $_.Valid }).Count
    $failedChecks = $totalChecks - $passedChecks
    $criticalCount = $criticalFailures.Count
    
    Write-Host "Total Checks: $totalChecks" -ForegroundColor White
    Write-Host "Passed: $passedChecks" -ForegroundColor Green
    Write-Host "Failed: $failedChecks" -ForegroundColor $(if ($failedChecks -gt 0) { "Red" } else { "White" })
    Write-Host "Critical Failures: $criticalCount" -ForegroundColor $(if ($criticalCount -gt 0) { "Red" } else { "White" })
    
    if ($criticalCount -gt 0) {
        Write-Host "`nCRITICAL FAILURES:" -ForegroundColor Red
        foreach ($failure in $criticalFailures) {
            Write-Host "  • $($failure.Description): $($failure.Error)" -ForegroundColor Red
        }
        return $false
    }
    
    return $true
}
# ===================================

# ========== EMAIL FUNCTIONS ==========
function Get-EmailCredential {
    param([hashtable]$Config)
    
    if (-not $Config.Enabled) {
        return $null
    }
    
    switch ($Config.CredentialMethod) {
        "EnvironmentVariable" {
            $envVarName = $Config.PasswordEnvironmentVariable
            if ([string]::IsNullOrEmpty($envVarName)) {
                Write-Host "  ✗ Environment variable name not configured" -ForegroundColor Red
                return $null
            }
            
            $password = [System.Environment]::GetEnvironmentVariable($envVarName, "User")
            if ([string]::IsNullOrEmpty($password)) {
                Write-Host "  ✗ Environment variable '$envVarName' not found" -ForegroundColor Red
                return $null
            }
            
            $securePassword = ConvertTo-SecureString $password -AsPlainText -Force
            return New-Object System.Management.Automation.PSCredential ($Config.SenderEmail, $securePassword)
        }
        
        "CredentialFile" {
            $credentialFile = $Config.CredentialFilePath
            if (-not (Test-Path $credentialFile)) {
                Write-Host "  ✗ Credential file not found: $credentialFile" -ForegroundColor Red
                return $null
            }
            
            try {
                return Import-Clixml -Path $credentialFile
            } catch {
                Write-Host "  ✗ Failed to load credentials: $_" -ForegroundColor Red
                return $null
            }
        }
        
        "Prompt" {
            Write-Host "  Please enter email credentials for: $($Config.SenderEmail)" -ForegroundColor Yellow
            return Get-Credential -Message "Enter email password for $($Config.SenderEmail)" -UserName $Config.SenderEmail
        }
        
        default {
            Write-Host "  ✗ Unknown credential method: $($Config.CredentialMethod)" -ForegroundColor Red
            return $null
        }
    }
}

function Send-ProcessCompletionEmail {
    param(
        [hashtable]$Config,
        [string]$RunFolder,
        [string]$RunId,
        [int]$ExitCode,
        [string]$Duration,
        [string]$CompletionStatus,
        [string]$CompletionFilePath
    )
    
    if (-not $Config.Enabled) {
        Write-Host "Email notifications are disabled" -ForegroundColor Yellow
        return $false
    }
    
    Write-Host "`nPreparing email notification..." -ForegroundColor Cyan
    
    try {
        # Get credentials securely
        $credential = Get-EmailCredential -Config $Config
        if (-not $credential) {
            Write-Host "  ✗ Failed to obtain email credentials" -ForegroundColor Red
            return $false
        }
        
        # Prepare email body
        $emailBody = @"
Face Recognition Processing Report
==================================================
Run ID: $RunId
Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Status: $CompletionStatus
Exit Code: $ExitCode
Duration: $Duration

LOCATION DETAILS
==================================================
Run Folder: $RunFolder

COMPLETION FILE
==================================================
Status: $(if ($CompletionFilePath -and (Test-Path $CompletionFilePath)) { "Found" } else { "NOT FOUND" })

SYSTEM INFORMATION
==================================================
Host Name: $env:COMPUTERNAME
User: $env:USERNAME
Execution Time: $(Get-Date)

NOTES
==================================================
This is an automated notification.
"@
        
        $subject = "$($Config.SubjectPrefix) Process $CompletionStatus - $RunId"
        
        # Send email
        Send-MailMessage `
            -From $Config.SenderEmail `
            -To $Config.RecipientEmail `
            -Subject $subject `
            -Body $emailBody `
            -SmtpServer $Config.SmtpServer `
            -Port $Config.SmtpPort `
            -UseSsl:$Config.UseSsl `
            -Credential $credential `
            -ErrorAction Stop
        
        Write-Host "✓ Email notification sent successfully" -ForegroundColor Green
        return $true
        
    } catch {
        Write-Host "✗ Failed to send email: $_" -ForegroundColor Red
        return $false
    }
}

function Wait-ForCompletionFile {
    param(
        [string]$RunFolderPath,
        [hashtable]$Config
    )
    
    if (-not $Config.Enabled) {
        Write-Host "Completion file detection is disabled" -ForegroundColor Yellow
        return $null
    }
    
    $completionFile = Join-Path $RunFolderPath $Config.FileName
    $scriptOutputPath = Join-Path $RunFolderPath "script_output"
    $completionFileAlt = Join-Path $scriptOutputPath $Config.FileName
    
    Write-Host "`nWaiting for completion file..." -ForegroundColor Cyan
    Write-Host "  Check delay: $($Config.CheckDelaySeconds) seconds" -ForegroundColor Gray
    Write-Host "  Max retries: $($Config.MaxRetries)" -ForegroundColor Gray
    
    for ($i = 1; $i -le $Config.MaxRetries; $i++) {
        Write-Host "  Check attempt $i of $($Config.MaxRetries)..." -ForegroundColor Gray
        
        if (Test-Path $completionFile) {
            Write-Host "  ✓ Completion file found" -ForegroundColor Green
            return $completionFile
        }
        
        if (Test-Path $completionFileAlt) {
            Write-Host "  ✓ Completion file found in script_output" -ForegroundColor Green
            return $completionFileAlt
        }
        
        if ($i -lt $Config.MaxRetries) {
            Start-Sleep -Seconds $Config.CheckDelaySeconds
        }
    }
    
    Write-Host "  ✗ Completion file not found after $($Config.MaxRetries) attempts" -ForegroundColor Red
    return $null
}
# ===================================

# ========== MAIN EXECUTION ==========

# Get system time info at start
Write-Host "=================================================="
Write-Host "PROCESS INITIALIZATION"
Write-Host "=================================================="
$systemStartTime = Get-SystemTimeInfo
Write-Host "System Local Time: $($systemStartTime.LocalTime)" -ForegroundColor Cyan
Write-Host "System UTC Time: $($systemStartTime.UtcTime)" -ForegroundColor Cyan
Write-Host "Time Zone: $($systemStartTime.TimeZone.DisplayName)" -ForegroundColor Cyan

# Run comprehensive validity checks
$checksPassed = Run-ComprehensiveValidityChecks

if (-not $checksPassed) {
    Write-Host "`n✗ Validity checks failed. Exiting script." -ForegroundColor Red
    exit 1
}

Write-Host "`n✓ All validity checks passed!" -ForegroundColor Green

# Convert parameters to arguments
$PYTHON_ARGS = Convert-HashtableToArgs -Params $PYTHON_PARAMS

# Create runs base directory if it doesn't exist
if (-not (Test-Path $RUNS_BASE_PATH)) {
    New-Item -ItemType Directory -Path $RUNS_BASE_PATH -Force | Out-Null
    Write-Host "Created runs base directory: $RUNS_BASE_PATH" -ForegroundColor Green
}

# Generate run folder with timestamp
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$RUN_FOLDER_NAME = "Run_Process_TowerCPU_Embedding_$timestamp"
$RUN_FOLDER_PATH = Join-Path $RUNS_BASE_PATH $RUN_FOLDER_NAME

# Create run folder structure
$RUN_LOGS_PATH = Join-Path $RUN_FOLDER_PATH "logs"
$RUN_SCRIPT_OUTPUT_PATH = Join-Path $RUN_FOLDER_PATH "script_output"
$RUN_METADATA_PATH = Join-Path $RUN_FOLDER_PATH "metadata.json"

try {
    New-Item -ItemType Directory -Path $RUN_FOLDER_PATH -Force | Out-Null
    New-Item -ItemType Directory -Path $RUN_LOGS_PATH -Force | Out-Null
    New-Item -ItemType Directory -Path $RUN_SCRIPT_OUTPUT_PATH -Force | Out-Null
    Write-Host "`n✓ Created run folder structure at: $RUN_FOLDER_PATH" -ForegroundColor Green
} catch {
    Write-Host "✗ Failed to create run folder structure: $_" -ForegroundColor Red
    exit 1
}

# ========== LOG FILE SETUP ==========
$MAIN_LOG_FILE = Join-Path $RUN_LOGS_PATH "run_$timestamp.log"
$PYTHON_OUTPUT_FILE = Join-Path $RUN_LOGS_PATH "python_output.txt"
$COMPLETION_SUMMARY_FILE = Join-Path $RUN_LOGS_PATH "completion_summary.txt"

$argsString = $PYTHON_ARGS -join " "

# Write initial log header
$logHeader = @"
==================================================
RUN STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
System Local Time: $($systemStartTime.LocalTime)
System UTC Time: $($systemStartTime.UtcTime)
Time Zone: $($systemStartTime.TimeZone.DisplayName)
==================================================
Run Folder: $RUN_FOLDER_PATH
PowerShell Script: $POWERSHELL_SCRIPT_NAME
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT
Arguments: $argsString
==================================================
"@

$logHeader | Out-File $MAIN_LOG_FILE

# ========== CREATE METADATA FILE ==========
$metadata = @{
    run_id = $timestamp
    start_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    system_info = @{
        local_time = $systemStartTime.LocalTime
        utc_time = $systemStartTime.UtcTime
        timezone = $systemStartTime.TimeZone.DisplayName
    }
    powershell_script = $POWERSHELL_SCRIPT_NAME
    virtual_env = $VENV_ROOT
    python_script = $PYTHON_SCRIPT
    arguments = $PYTHON_ARGS
    run_folder = $RUN_FOLDER_PATH
}

$metadata | ConvertTo-Json -Depth 3 | Out-File $RUN_METADATA_PATH
Write-Host "✓ Created metadata file: $RUN_METADATA_PATH" -ForegroundColor Green

# ========== EXECUTION ==========
Write-Host "`n=================================================="
Write-Host "STARTING PYTHON SCRIPT EXECUTION"
Write-Host "=================================================="
Write-Host "Run folder: $RUN_FOLDER_PATH" -ForegroundColor Cyan
Write-Host "Arguments: $argsString" -ForegroundColor Cyan
Write-Host ""

$pythonExe = "$VENV_ROOT\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    $errorMsg = "ERROR: Python executable not found at $pythonExe"
    $errorMsg | Out-File $MAIN_LOG_FILE -Append
    Write-Host "✗ $errorMsg" -ForegroundColor Red
    exit 1
}

# Capture precise start time
$processStartTime = Get-Date
"`n==================================================" | Out-File $MAIN_LOG_FILE -Append
"PYTHON PROCESS STARTED: $($processStartTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append

try {
    $commandString = "`"$pythonExe`" `"$PYTHON_SCRIPT`" $argsString"
    Write-Host "Executing: $commandString" -ForegroundColor Yellow
    $commandString | Out-File $MAIN_LOG_FILE -Append
    
    Write-Host "Python output will be saved to: $PYTHON_OUTPUT_FILE" -ForegroundColor Cyan
    
    $originalLocation = Get-Location
    Set-Location $RUN_SCRIPT_OUTPUT_PATH
    
    & $pythonExe $PYTHON_SCRIPT $PYTHON_ARGS 2>&1 | Tee-Object -FilePath $PYTHON_OUTPUT_FILE
    
    $exitCode = $LASTEXITCODE
    
    Set-Location $originalLocation
    
} catch {
    $errorMessage = $_.Exception.Message
    "EXCEPTION: $errorMessage" | Out-File $MAIN_LOG_FILE -Append
    $errorMessage | Out-File $PYTHON_OUTPUT_FILE -Append
    Write-Host "✗ Exception during Python script execution: $errorMessage" -ForegroundColor Red
    $exitCode = 1
}

# Capture precise end time
$processEndTime = Get-Date
$processDuration = $processEndTime - $processStartTime
$processDurationFormatted = Format-TimeSpanForDisplay -TimeSpan $processDuration

# ========== COMPLETION FILE DETECTION ==========
$completionFile = $null
if ($COMPLETION_FILE_CONFIG.Enabled) {
    $completionFile = Wait-ForCompletionFile -RunFolderPath $RUN_FOLDER_PATH -Config $COMPLETION_FILE_CONFIG
}

# ========== POST-EXECUTION LOGGING ==========
$executionSummary = @"

==================================================
EXECUTION SUMMARY
==================================================
Python Process Start: $($processStartTime.ToString('yyyy-MM-dd HH:mm:ss'))
Python Process End: $($processEndTime.ToString('yyyy-MM-dd HH:mm:ss'))
Python Process Duration: $processDurationFormatted

PowerShell Script: $POWERSHELL_SCRIPT_NAME
Exit code: $exitCode

Completion File: $(if ($completionFile) { "Found at $completionFile" } else { "Not found" })
"@

$executionSummary | Out-File $MAIN_LOG_FILE -Append

# ========== CREATE COMPLETION SUMMARY ==========
$completionStatus = if ($exitCode -eq 0) { "SUCCESS" } else { "FAILED" }
if ($completionFile) { $completionStatus += " (With Completion File)" }

$completionSummary = @"
==================================================
RUN COMPLETION SUMMARY
==================================================
Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run ID: $timestamp
PowerShell Script: $POWERSHELL_SCRIPT_NAME
Status: $completionStatus
Exit Code: $exitCode

TIMING INFORMATION
==================================================
Python Process Duration: $processDurationFormatted

FOLDER STRUCTURE
==================================================
Run Folder: $RUN_FOLDER_PATH
├── logs\
│   ├── run_$timestamp.log
│   ├── python_output.txt
│   └── completion_summary.txt
├── script_output\
└── metadata.json

COMPLETION FILE STATUS
==================================================
$(if ($completionFile) { 
    "✓ Completion file found" 
} else { 
    if ($COMPLETION_FILE_CONFIG.Enabled) {
        "✗ Completion file not found after waiting"
    } else {
        "ℹ Completion file detection disabled"
    }
})
"@

$completionSummary | Out-File $COMPLETION_SUMMARY_FILE

# Update metadata
$completionMetadata = Get-Content $RUN_METADATA_PATH | ConvertFrom-Json
$completionMetadata | Add-Member -NotePropertyName "end_time" -NotePropertyValue (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Force
$completionMetadata | Add-Member -NotePropertyName "process_timing" -NotePropertyValue @{
    python_start = $processStartTime
    python_end = $processEndTime
    python_duration_seconds = $processDuration.TotalSeconds
} -Force
$completionMetadata | Add-Member -NotePropertyName "exit_code" -NotePropertyValue $exitCode -Force
$completionMetadata | Add-Member -NotePropertyName "completion_file" -NotePropertyValue $(if ($completionFile) { $completionFile } else { $null }) -Force
$completionMetadata | ConvertTo-Json -Depth 4 | Out-File $RUN_METADATA_PATH

# ========== EMAIL NOTIFICATION ==========
$emailSent = Send-ProcessCompletionEmail `
    -Config $EMAIL_CONFIG `
    -RunFolder $RUN_FOLDER_PATH `
    -RunId $timestamp `
    -ExitCode $exitCode `
    -Duration $processDurationFormatted `
    -CompletionStatus $completionStatus `
    -CompletionFilePath $completionFile

# Update metadata with email status
$completionMetadata = Get-Content $RUN_METADATA_PATH | ConvertFrom-Json
$completionMetadata | Add-Member -NotePropertyName "email_notification" -NotePropertyValue @{
    sent = $emailSent
    sent_time = if ($emailSent) { (Get-Date -Format "yyyy-MM-dd HH:mm:ss") } else { $null }
} -Force
$completionMetadata | ConvertTo-Json -Depth 4 | Out-File $RUN_METADATA_PATH

# ========== FINAL OUTPUT ==========
Write-Host "`n=================================================="
Write-Host "RUN COMPLETED"
Write-Host "=================================================="
Write-Host "PowerShell Script: $POWERSHELL_SCRIPT_NAME" -ForegroundColor Cyan
Write-Host "Run Folder: $RUN_FOLDER_PATH" -ForegroundColor Cyan
Write-Host "Status: $completionStatus" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
Write-Host "Exit Code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
Write-Host "Duration: $processDurationFormatted" -ForegroundColor Cyan
Write-Host ""
Write-Host "System time at completion: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "=================================================="

exit $exitCode
# stabilization.ps1
<#
.SYNOPSIS
Stabilization and validation script for the face recognition monitoring system
.DESCRIPTION
Validates all components, fixes common issues, and prepares the system for stable operation
#>

# ====================================================================
# CONFIGURATION
# ====================================================================
$ValidationConfig = @{
    ScriptsToValidate = @(
        "1_common-paths.ps1",
        "1_mask_portable.ps1", 
        "1_monitor.ps1",
        "1_email-sender.ps1",
        "1_run_after_validation.ps1"
    )
    RequiredFunctions = @(
        "Initialize-ProjectPortablePaths",
        "Write-Log",
        "Write-WorkerStatus",
        "Read-WorkerStatus",
        "Initialize-CommunicationPaths",
        "Check-Heartbeat",
        "Send-Heartbeat",
        "Acquire-Lock",
        "Release-Lock"
    )
    EmailCredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
    MaxRetries = 3
    RetryDelay = 5
}

# ====================================================================
# LOGGING
# ====================================================================
function Write-ValidationLog {
    param(
        [string]$Message,
        [string]$Level = "INFO",
        [string]$Color = "White"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    
    Write-Host $logEntry -ForegroundColor $Color
    
    # Also write to file
    $logDir = Join-Path $PSScriptRoot "validation_logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    
    $logFile = Join-Path $logDir "stabilization_$(Get-Date -Format 'yyyy-MM-dd').log"
    Add-Content -Path $logFile -Value $logEntry
}

# ====================================================================
# VALIDATION FUNCTIONS
# ====================================================================
function Validate-ScriptExistence {
    param([string]$ScriptName)
    
    $scriptPath = Join-Path $PSScriptRoot $ScriptName
    if (Test-Path $scriptPath) {
        Write-ValidationLog "✓ Found: $ScriptName" -Level "SUCCESS" -Color "Green"
        return $true
    } else {
        Write-ValidationLog "✗ Missing: $ScriptName" -Level "ERROR" -Color "Red"
        return $false
    }
}

function Validate-ScriptSyntax {
    param([string]$ScriptName)
    
    $scriptPath = Join-Path $PSScriptRoot $ScriptName
    
    try {
        $tokens = @()
        $errors = @()
        $ast = [System.Management.Automation.Language.Parser]::ParseFile(
            $scriptPath,
            [ref]$tokens,
            [ref]$errors
        )
        
        if ($errors.Count -eq 0) {
            Write-ValidationLog "✓ Syntax OK: $ScriptName" -Level "SUCCESS" -Color "Green"
            return $true
        } else {
            Write-ValidationLog "✗ Syntax errors in:" -Level "ERROR" -Color "Red"
            foreach ($error in $errors) {
                Write-ValidationLog "  - $($error.Message)" -Level "ERROR" -Color "Red"
            }
            return $false
        }
    } catch {
        Write-ValidationLog "✗ Failed to parse: $_" -Level "ERROR" -Color "Red"
        return $false
    }
}


function Validate-FunctionExistence {
    param([string]$ScriptName, [string]$FunctionName)
    
    $scriptPath = Join-Path $PSScriptRoot $ScriptName
    
    try {
        $content = Get-Content $scriptPath -Raw
        
        # Check for function definition
        if ($content -match "function $FunctionName\s*\{") {
            Write-ValidationLog "✓ Function found: $FunctionName in $ScriptName" -Level "SUCCESS" -Color "Green"
            return $true
        } else {
            Write-ValidationLog "✗ Function missing: $FunctionName in $ScriptName" -Level "WARN" -Color "Yellow"
            return $false
        }
    } catch {
        Write-ValidationLog "✗ Error checking function: $_" -Level "ERROR" -Color "Red"
        return $false
    }
}

function Fix-MissingFunctions {
    Write-ValidationLog "Creating missing function implementations..." -Level "INFO" -Color "Cyan"
    
    $fixScript = @'
# ====================================================================
# MISSING FUNCTION IMPLEMENTATIONS
# ====================================================================

function Check-Heartbeat {
    [CmdletBinding()]
    param([string]$HeartbeatFile)
    
    if (-not (Test-Path $HeartbeatFile)) {
        return $false
    }
    
    try {
        $heartbeatTime = (Get-Item $HeartbeatFile).LastWriteTime
        $ageMinutes = ((Get-Date) - $heartbeatTime).TotalMinutes
        
        # Heartbeat is considered alive if updated within last 2 minutes
        return $ageMinutes -le 2
    } catch {
        return $false
    }
}

function Send-Heartbeat {
    [CmdletBinding()]
    param([string]$HeartbeatFile)
    
    try {
        $heartbeatDir = Split-Path $HeartbeatFile -Parent
        if (-not (Test-Path $heartbeatDir)) {
            New-Item -ItemType Directory -Path $heartbeatDir -Force | Out-Null
        }
        
        Set-Content -Path $HeartbeatFile -Value (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Force
        return $true
    } catch {
        return $false
    }
}

function Acquire-Lock {
    [CmdletBinding()]
    param(
        [string]$LockFile,
        [int]$TimeoutSeconds = 30
    )
    
    $startTime = Get-Date
    $lockAcquired = $false
    
    while (((Get-Date) - $startTime).TotalSeconds -lt $TimeoutSeconds) {
        try {
            if (Test-Path $LockFile) {
                $lockTime = [DateTime]::Parse((Get-Content $LockFile -First 1))
                $lockAge = ((Get-Date) - $lockTime).TotalSeconds
                
                # If lock is older than 30 seconds, consider it stale
                if ($lockAge -gt 30) {
                    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
                }
            }
            
            # Try to create lock file
            $lockDir = Split-Path $LockFile -Parent
            if (-not (Test-Path $lockDir)) {
                New-Item -ItemType Directory -Path $lockDir -Force | Out-Null
            }
            
            $tempFile = "$LockFile.tmp"
            (Get-Date).ToString("yyyy-MM-dd HH:mm:ss") | Out-File $tempFile -Force
            Move-Item $tempFile $LockFile -Force -ErrorAction Stop
            
            $lockAcquired = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    
    return $lockAcquired
}

function Release-Lock {
    [CmdletBinding()]
    param([string]$LockFile)
    
    if (Test-Path $LockFile) {
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
    return $true
}
'@
    
    $fixPath = Join-Path $PSScriptRoot "1_missing-functions.ps1"
    $fixScript | Out-File $fixPath -Encoding UTF8
    
    Write-ValidationLog "Created missing functions at: $fixPath" -Level "SUCCESS" -Color "Green"
    return $fixPath
}

function Fix-MonitorLoading {
    Write-ValidationLog "Fixing monitor script loading issues..." -Level "INFO" -Color "Cyan"
    
    $monitorPath = Join-Path $PSScriptRoot "1_monitor.ps1"
    $monitorContent = Get-Content $monitorPath -Raw
    
    # Fix the incorrect module loading for email-sender and run_after_validation
    $fixedContent = $monitorContent -replace '(?s)\. \$emailSender.*?Write-Host "✓ Common paths module loaded"' -replace '(?s)\. \$runAfterValidate.*?Write-Host "✓ Common paths module loaded"'
    
    # Add proper loading logic
    $loadingFix = @'

# Test email sender module - only load functions, not as common paths
if (Test-Path $emailSender) {
    try {
        . $emailSender
        Write-Host "✓ Email sender module loaded" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Failed to load email sender: $_" -ForegroundColor Red
        # Continue without email functionality
    }
} else {
    Write-Host "WARN: Email sender script not found at: $emailSender" -ForegroundColor Yellow
}

# Test run after validate module - only load functions
if (Test-Path $runAfterValidate) {
    try {
        . $runAfterValidate
        Write-Host "✓ Run after validation module loaded" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Failed to load run after validation: $_" -ForegroundColor Red
        # Continue without validation functionality
    }
} else {
    Write-Host "WARN: Run after validation script not found at: $runAfterValidate" -ForegroundColor Yellow
}
'@
    
    # Find where to insert the fix
    $pattern = '# Test module load into monitor'
    $insertPoint = $fixedContent.IndexOf($pattern)
    
    if ($insertPoint -gt 0) {
        # Find the end of the existing loading section
        $endOfSection = $fixedContent.IndexOf('# ====================================================================', $insertPoint + 50)
        
        # Replace the entire loading section
        $newContent = $fixedContent.Substring(0, $insertPoint)
        $newContent += "# Test module load into monitor`n`n"
        $newContent += "if (Test-Path `$commonPathsScript) {`n"
        $newContent += "    try {`n"
        $newContent += "        . `$commonPathsScript`n"
        $newContent += "        Write-Host `"✓ Common paths module loaded`" -ForegroundColor Green`n"
        $newContent += "    } catch {`n"
        $newContent += "        Write-Host `"ERROR: Failed to load common paths: `$_`" -ForegroundColor Red`n"
        $newContent += "        exit 1`n"
        $newContent += "    }`n"
        $newContent += "} else {`n"
        $newContent += "    Write-Host `"ERROR: Common paths script not found at: `$commonPathsScript`" -ForegroundColor Red`n"
        $newContent += "    exit 1`n"
        $newContent += "}`n`n"
        $newContent += $loadingFix
        $newContent += "`n`n" + $fixedContent.Substring($endOfSection)
        
        $newContent | Out-File $monitorPath -Encoding UTF8
        Write-ValidationLog "Fixed monitor script loading" -Level "SUCCESS" -Color "Green"
        return $true
    }
    
    return $false
}

function Fix-EmailCredentials {
    Write-ValidationLog "Setting up email credentials..." -Level "INFO" -Color "Cyan"
    
    $credentialDir = Split-Path $ValidationConfig.EmailCredentialPath -Parent
    if (-not (Test-Path $credentialDir)) {
        New-Item -ItemType Directory -Path $credentialDir -Force | Out-Null
    }
    
    if (-not (Test-Path $ValidationConfig.EmailCredentialPath)) {
        Write-Host "`n=== Email Configuration Setup ===" -ForegroundColor Cyan
        Write-Host "Please enter email credentials for sending reports:" -ForegroundColor Yellow
        
        $email = Read-Host "Email address (e.g., your-email@gmail.com)"
        $password = Read-Host "App password (for Gmail use app-specific password)" -AsSecureString
        
        # Create credential object
        $credential = New-Object System.Management.Automation.PSCredential($email, $password)
        
        # Export to XML
        $credential | Export-Clixml -Path $ValidationConfig.EmailCredentialPath
        
        Write-ValidationLog "Email credentials saved securely" -Level "SUCCESS" -Color "Green"
        
        # Update email sender script
        $emailSenderPath = Join-Path $PSScriptRoot "1_email-sender.ps1"
        if (Test-Path $emailSenderPath) {
            $content = Get-Content $emailSenderPath -Raw
            $updatedContent = $content -replace 'Password = ".*?"', "Password = `"$($ValidationConfig.EmailCredentialPath)`""
            $updatedContent = $updatedContent -replace 'Username = ".*?"', "Username = `"$email`""
            $updatedContent = $updatedContent -replace 'FromAddress = ".*?"', "FromAddress = `"$email`""
            $updatedContent = $updatedContent -replace 'ToAddress = ".*?"', "ToAddress = `"$email`""
            
            $updatedContent | Out-File $emailSenderPath -Encoding UTF8
            Write-ValidationLog "Updated email sender configuration" -Level "SUCCESS" -Color "Green"
        }
    } else {
        Write-ValidationLog "Email credentials already configured" -Level "INFO" -Color "Green"
    }
}

function Test-ProcessCleanup {
    Write-ValidationLog "Testing process cleanup..." -Level "INFO" -Color "Cyan"
    
    try {
        # Check for orphaned processes
        $orphanedProcesses = @()
        
        # Check Python processes
        $pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue
        foreach ($proc in $pythonProcesses) {
            try {
                $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
                if ($cmdLine -like "*Magick*") {
                    $orphanedProcesses += "Python:$($proc.Id)"
                }
            } catch { }
        }
        
        # Check PowerShell processes
        $psProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue
        foreach ($proc in $psProcesses) {
            if ($proc.Id -ne $PID) {
                try {
                    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
                    if ($cmdLine -like "*mask_portable*" -or $cmdLine -like "*monitor*") {
                        $orphanedProcesses += "PowerShell:$($proc.Id)"
                    }
                } catch { }
            }
        }
        
        if ($orphanedProcesses.Count -gt 0) {
            Write-ValidationLog "Found orphaned processes: $($orphanedProcesses.Count)" -Level "WARN" -Color "Yellow"
            
            $cleanup = Read-Host "Clean up orphaned processes? (y/n)"
            if ($cleanup -eq 'y') {
                foreach ($proc in $orphanedProcesses) {
                    $type, $id = $proc.Split(':')
                    try {
                        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
                        Write-ValidationLog "Stopped process $type (PID: $id)" -Level "INFO" -Color "Green"
                    } catch {
                        Write-ValidationLog "Failed to stop process $type (PID: $id)" -Level "WARN" -Color "Yellow"
                    }
                }
            }
        } else {
            Write-ValidationLog "No orphaned processes found" -Level "SUCCESS" -Color "Green"
        }
        
        return $true
    } catch {
        Write-ValidationLog "Process cleanup test failed: $_" -Level "ERROR" -Color "Red"
        return $false
    }
}

function Create-RunValidationScript {
    Write-ValidationLog "Creating run validation script..." -Level "INFO" -Color "Cyan"
    
    $validationScript = @'
# run_validation.ps1
<#
.SYNOPSIS
Validates the run environment and starts the monitor
.DESCRIPTION
Performs comprehensive validation before starting the monitor
#>

Write-Host "=== Run Environment Validation ===" -ForegroundColor Cyan

# Check for required scripts
$requiredScripts = @(
    "1_common-paths.ps1",
    "1_mask_portable.ps1",
    "1_monitor.ps1"
)

$allFound = $true
foreach ($script in $requiredScripts) {
    if (Test-Path $script) {
        Write-Host "✓ Found: $script" -ForegroundColor Green
    } else {
        Write-Host "✗ Missing: $script" -ForegroundColor Red
        $allFound = $false
    }
}

if (-not $allFound) {
    Write-Host "`nERROR: Missing required scripts. Please run stabilization.ps1 first." -ForegroundColor Red
    exit 1
}

# Check Python environment
Write-Host "`n=== Python Environment Check ===" -ForegroundColor Cyan

try {
    # Load common paths to find Python
    . .\1_common-paths.ps1
    $paths = Initialize-ProjectPortablePaths -IsMonitor
    
    if (Test-Path $paths.PythonExe) {
        Write-Host "✓ Python executable: $($paths.PythonExe)" -ForegroundColor Green
        
        # Test Python
        $pythonTest = & $paths.PythonExe --version 2>&1
        Write-Host "✓ Python version: $pythonTest" -ForegroundColor Green
    } else {
        Write-Host "✗ Python executable not found" -ForegroundColor Red
        exit 1
    }
    
    if (Test-Path $paths.PythonScriptPath) {
        Write-Host "✓ Python script: $($paths.PythonScriptPath)" -ForegroundColor Green
    } else {
        Write-Host "✗ Python script not found" -ForegroundColor Red
        exit 1
    }
    
} catch {
    Write-Host "✗ Failed to check Python environment: $_" -ForegroundColor Red
    exit 1
}

# Check log directory
Write-Host "`n=== Directory Structure Check ===" -ForegroundColor Cyan

try {
    $logBase = "logs-running\magick"
    if (-not (Test-Path $logBase)) {
        New-Item -ItemType Directory -Path $logBase -Force | Out-Null
        Write-Host "✓ Created log directory: $logBase" -ForegroundColor Green
    } else {
        Write-Host "✓ Log directory exists: $logBase" -ForegroundColor Green
    }
    
    # Check for today's directory
    $today = Get-Date -Format "yyyy-MM-dd"
    $todayDir = Join-Path $logBase $today
    if (-not (Test-Path $todayDir)) {
        New-Item -ItemType Directory -Path $todayDir -Force | Out-Null
        Write-Host "✓ Created today's directory: $todayDir" -ForegroundColor Green
    } else {
        Write-Host "✓ Today's directory exists: $todayDir" -ForegroundColor Green
    }
    
} catch {
    Write-Host "✗ Directory check failed: $_" -ForegroundColor Red
    exit 1
}

# Check for running monitor
Write-Host "`n=== Process Check ===" -ForegroundColor Cyan

$monitorProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue | 
    Where-Object { 
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
            return ($cmdLine -like "*1_monitor.ps1*")
        } catch { $false }
    }

if ($monitorProcesses.Count -gt 0) {
    Write-Host "⚠ Monitor already running. PIDs: $($monitorProcesses.Id -join ', ')" -ForegroundColor Yellow
    
    $choice = Read-Host "Restart monitor? (y/n)"
    if ($choice -eq 'y') {
        foreach ($proc in $monitorProcesses) {
            try {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                Write-Host "Stopped monitor process (PID: $($proc.Id))" -ForegroundColor Green
                Start-Sleep -Seconds 2
            } catch {
                Write-Host "Failed to stop process: $($proc.Id)" -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "Exiting - monitor already running" -ForegroundColor Yellow
        exit 0
    }
}

# Start monitor
Write-Host "`n=== Starting Monitor ===" -ForegroundColor Cyan

try {
    Write-Host "Starting 1_monitor.ps1..." -ForegroundColor Green
    
    # Start monitor in a new window for better visibility
    $monitorJob = Start-Process powershell -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "1_monitor.ps1"
    ) -PassThru -NoNewWindow
    
    Write-Host "Monitor started (PID: $($monitorJob.Id))" -ForegroundColor Green
    Write-Host "`nMonitor is now running. Check log files for details." -ForegroundColor Cyan
    Write-Host "Press Ctrl+C in the monitor window to stop." -ForegroundColor Yellow
    
} catch {
    Write-Host "✗ Failed to start monitor: $_" -ForegroundColor Red
    exit 1
}
'@
    
    $scriptPath = Join-Path $PSScriptRoot "run_validation.ps1"
    $validationScript | Out-File $scriptPath -Encoding UTF8
    
    Write-ValidationLog "Created run validation script: $scriptPath" -Level "SUCCESS" -Color "Green"
    return $scriptPath
}

function Create-CleanupScript {
    Write-ValidationLog "Creating cleanup script..." -Level "INFO" -Color "Cyan"
    
    $cleanupScript = @'
# cleanup.ps1
<#
.SYNOPSIS
Cleans up orphaned processes and stale files
.DESCRIPTION
Stops all face recognition processes and cleans up temporary files
#>

Write-Host "=== System Cleanup ===" -ForegroundColor Cyan

# Stop all related processes
$processesStopped = 0

# Stop Python processes
Write-Host "Stopping Python processes..." -ForegroundColor Yellow
$pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue
foreach ($proc in $pythonProcesses) {
    try {
        $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
        if ($cmdLine -like "*Magick*") {
            $proc.Kill()
            $processesStopped++
            Write-Host "  Stopped Python (PID: $($proc.Id))" -ForegroundColor Green
        }
    } catch { }
}

# Stop PowerShell processes (except current)
Write-Host "Stopping worker/monitor processes..." -ForegroundColor Yellow
$psProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue
foreach ($proc in $psProcesses) {
    if ($proc.Id -ne $PID) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*mask_portable*" -or $cmdLine -like "*monitor*" -or $cmdLine -like "*Magick*") {
                $proc.Kill()
                $processesStopped++
                Write-Host "  Stopped PowerShell (PID: $($proc.Id))" -ForegroundColor Green
            }
        } catch { }
    }
}

Write-Host "`nTotal processes stopped: $processesStopped" -ForegroundColor Cyan

# Clean up old PID files
Write-Host "`nCleaning up stale files..." -ForegroundColor Yellow

$daysToKeep = 7
$cutoffDate = (Get-Date).AddDays(-$daysToKeep)

# Clean up old log directories
$logBase = "logs-running\magick"
if (Test-Path $logBase) {
    $logDirs = Get-ChildItem -Path $logBase -Directory
    foreach ($dir in $logDirs) {
        if ($dir.CreationTime -lt $cutoffDate) {
            try {
                Remove-Item -Path $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  Removed old log directory: $($dir.Name)" -ForegroundColor Green
            } catch { }
        }
    }
}

# Clean up PID files
$today = Get-Date -Format "yyyy-MM-dd"
$todayDir = Join-Path $logBase $today
if (Test-Path $todayDir) {
    $pidFiles = Get-ChildItem -Path $todayDir -Filter "*pid*.json" -Recurse -ErrorAction SilentlyContinue
    foreach ($file in $pidFiles) {
        try {
            Remove-Item -Path $file.FullName -Force -ErrorAction SilentlyContinue
            Write-Host "  Removed PID file: $($file.Name)" -ForegroundColor Green
        } catch { }
    }
}

Write-Host "`n=== Cleanup Complete ===" -ForegroundColor Green
Write-Host "System is now clean and ready for restart." -ForegroundColor Cyan
'@
    
    $scriptPath = Join-Path $PSScriptRoot "cleanup.ps1"
    $cleanupScript | Out-File $scriptPath -Encoding UTF8
    
    Write-ValidationLog "Created cleanup script: $scriptPath" -Level "SUCCESS" -Color "Green"
    return $scriptPath
}

# ====================================================================
# MAIN VALIDATION PROCESS
# ====================================================================
Write-Host "`n" + "="*60 -ForegroundColor Cyan
Write-Host "FACIAL RECOGNITION SYSTEM STABILIZATION" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan
Write-Host "`n"

# Step 1: Validate script existence
Write-ValidationLog "Step 1: Validating script existence..." -Level "INFO" -Color "Cyan"

$allScriptsExist = $true
foreach ($script in $ValidationConfig.ScriptsToValidate) {
    if (-not (Validate-ScriptExistence $script)) {
        $allScriptsExist = $false
    }
}

if (-not $allScriptsExist) {
    Write-ValidationLog "Missing scripts detected. Please ensure all scripts are in the same directory." -Level "ERROR" -Color "Red"
    exit 1
}

# Step 2: Validate script syntax
Write-ValidationLog "`nStep 2: Validating script syntax..." -Level "INFO" -Color "Cyan"

$syntaxValid = $true
foreach ($script in $ValidationConfig.ScriptsToValidate) {
    if (-not (Validate-ScriptSyntax $script)) {
        $syntaxValid = $false
    }
}

if (-not $syntaxValid) {
    Write-ValidationLog "Syntax errors found. Attempting to fix..." -Level "WARN" -Color "Yellow"
}

# Step 3: Fix monitor loading issues
Write-ValidationLog "`nStep 3: Fixing monitor script issues..." -Level "INFO" -Color "Cyan"

if (Fix-MonitorLoading) {
    Write-ValidationLog "Monitor script fixed successfully" -Level "SUCCESS" -Color "Green"
} else {
    Write-ValidationLog "Failed to fix monitor script" -Level "ERROR" -Color "Red"
}

# Step 4: Fix missing functions
Write-ValidationLog "`nStep 4: Checking for missing functions..." -Level "INFO" -Color "Cyan"

$missingFunctions = @()
foreach ($function in $ValidationConfig.RequiredFunctions) {
    $found = $false
    
    # Check in each script
    foreach ($script in $ValidationConfig.ScriptsToValidate) {
        if (Validate-FunctionExistence $script $function) {
            $found = $true
            break
        }
    }
    
    if (-not $found) {
        $missingFunctions += $function
        Write-ValidationLog "Missing function: $function" -Level "WARN" -Color "Yellow"
    }
}

if ($missingFunctions.Count -gt 0) {
    $fixPath = Fix-MissingFunctions
    Write-ValidationLog "Created missing functions. Please add 'if (Test-Path `"$fixPath`") { . `"$fixPath`" }' to your scripts." -Level "INFO" -Color "Yellow"
}

# Step 5: Set up email credentials
Write-ValidationLog "`nStep 5: Configuring email credentials..." -Level "INFO" -Color "Cyan"

Fix-EmailCredentials

# Step 6: Test process cleanup
Write-ValidationLog "`nStep 6: Testing process cleanup..." -Level "INFO" -Color "Cyan"

Test-ProcessCleanup

# Step 7: Create utility scripts
Write-ValidationLog "`nStep 7: Creating utility scripts..." -Level "INFO" -Color "Cyan"

$runValidationPath = Create-RunValidationScript
$cleanupPath = Create-CleanupScript

# Step 8: Final instructions
Write-Host "`n" + "="*60 -ForegroundColor Green
Write-Host "STABILIZATION COMPLETE" -ForegroundColor Green
Write-Host "="*60 -ForegroundColor Green
Write-Host "`nCreated utility scripts:" -ForegroundColor Cyan
Write-Host "  • run_validation.ps1 - Use this to start the monitor" -ForegroundColor White
Write-Host "  • cleanup.ps1 - Use this to clean up orphaned processes" -ForegroundColor White
Write-Host "  • 1_missing-functions.ps1 - Add this to your scripts if needed" -ForegroundColor White

Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Run: .\run_validation.ps1" -ForegroundColor Yellow
Write-Host "2. Monitor will start automatically" -ForegroundColor Yellow
Write-Host "3. Check log files for progress" -ForegroundColor Yellow
Write-Host "`nFor cleanup: .\cleanup.ps1" -ForegroundColor Yellow
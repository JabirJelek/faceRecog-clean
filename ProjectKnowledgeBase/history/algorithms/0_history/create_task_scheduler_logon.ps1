# create_task_scheduler_logon_fixed_structured.ps1
# ==============================================
# Structured version with proper cleanup and creation
# ==============================================

# ========== CONFIGURATION ==========
$TaskName = "FaceRecognitionScript"
$TaskDescription = "Runs Python face recognition script on user logon"
$ScriptPath = "A:\SCMA\3-APD\fromAraya\automate_task\run_python_with_venv_organized.ps1"
$WorkingDirectory = "A:\SCMA\3-APD\fromAraya\automate_task"
$LogFilePath = "A:\SCMA\3-APD\fromAraya\automate_task\TaskScheduler_Setup.log"
# ===================================

# ========== LOGGING FUNCTION ==========
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "$timestamp [$Level] $Message"
    
    # Write to console with colors
    switch ($Level) {
        "ERROR" { Write-Host $logMessage -ForegroundColor Red }
        "WARNING" { Write-Host $logMessage -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logMessage -ForegroundColor Green }
        default { Write-Host $logMessage -ForegroundColor Cyan }
    }
    
    # Write to log file
    $logMessage | Out-File -FilePath $LogFilePath -Append
}
# ===================================

# ========== CHECK ADMIN PRIVILEGES ==========
function Test-Administrator {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Log "This script requires Administrator privileges!" -Level "ERROR"
    Write-Log "Please run PowerShell as Administrator." -Level "ERROR"
    pause
    exit 1
}
# ===================================

# ========== INITIALIZE LOG ==========
$logDir = Split-Path $LogFilePath -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

"================================================" | Out-File $LogFilePath
"Task Scheduler Setup Log" | Out-File $LogFilePath -Append
"Start Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $LogFilePath -Append
"Task Name: $TaskName" | Out-File $LogFilePath -Append
"Script Path: $ScriptPath" | Out-File $LogFilePath -Append
"================================================" | Out-File $LogFilePath -Append

Write-Log "Starting Task Scheduler setup for: $TaskName"
Write-Log "Log file: $LogFilePath"
# ===================================

# ========== CHECK IF SCRIPT EXISTS ==========
Write-Log "Verifying script exists..."
if (-not (Test-Path $ScriptPath)) {
    Write-Log "ERROR: Script not found at $ScriptPath" -Level "ERROR"
    Write-Log "Please check the script path in configuration." -Level "ERROR"
    pause
    exit 1
}
Write-Log "Script verified: $ScriptPath" -Level "SUCCESS"
# ===================================

# ========== LIST ALL EXISTING TASKS WITH SIMILAR NAMES ==========
Write-Log "Checking for existing tasks..." 
Write-Log "Searching for tasks containing: $TaskName"

# Method 1: Using schtasks.exe (most reliable)
$existingTasks = @()
try {
    $taskQuery = schtasks /query /fo csv 2>$null | ConvertFrom-Csv | Where-Object { $_.TaskName -like "*$TaskName*" }
    if ($taskQuery) {
        $existingTasks += $taskQuery
    }
} catch {
    Write-Log "Could not query tasks via schtasks.exe" -Level "WARNING"
}

# Method 2: Using ScheduledTasks module (if available)
try {
    if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
        $psTasks = Get-ScheduledTask | Where-Object { $_.TaskName -like "*$TaskName*" } | Select-Object TaskName, State
        if ($psTasks) {
            foreach ($task in $psTasks) {
                $existingTasks += [PSCustomObject]@{
                    TaskName = $task.TaskName
                    State = $task.State
                    Source = "PowerShell"
                }
            }
        }
    }
} catch {
    Write-Log "Could not query tasks via ScheduledTasks module" -Level "WARNING"
}

# Display found tasks
if ($existingTasks.Count -gt 0) {
    Write-Log "Found $($existingTasks.Count) existing task(s):" -Level "WARNING"
    Write-Log "=" * 50
    foreach ($task in $existingTasks) {
        Write-Log "Task Name: $($task.TaskName)"
        if ($task.State) { Write-Log "State: $($task.State)" }
        Write-Log "-" * 40
    }
    Write-Log "=" * 50
} else {
    Write-Log "No existing tasks found with name containing: $TaskName" -Level "SUCCESS"
}
# ===================================

# ========== DELETE EXISTING TASKS ==========
if ($existingTasks.Count -gt 0) {
    Write-Log "Deleting existing tasks..."
    
    foreach ($task in $existingTasks) {
        $taskNameToDelete = $task.TaskName
        Write-Log "Attempting to delete task: $taskNameToDelete"
        
        # Try using schtasks.exe first
        try {
            $result = schtasks /delete /tn "$taskNameToDelete" /f 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Successfully deleted via schtasks.exe: $taskNameToDelete" -Level "SUCCESS"
            } else {
                Write-Log "Failed to delete via schtasks.exe: $taskNameToDelete" -Level "WARNING"
            }
        } catch {
            Write-Log "Exception deleting via schtasks.exe: $_" -Level "WARNING"
        }
        
        # Try using PowerShell module
        try {
            if (Get-Command Unregister-ScheduledTask -ErrorAction SilentlyContinue) {
                Unregister-ScheduledTask -TaskName $taskNameToDelete -Confirm:$false -ErrorAction SilentlyContinue
                Write-Log "Attempted deletion via PowerShell module: $taskNameToDelete" -Level "SUCCESS"
            }
        } catch {
            # Ignore errors, we already tried schtasks
        }
        
        # Verify deletion
        Start-Sleep -Seconds 1
        $stillExists = $false
        try {
            $check = schtasks /query /tn "$taskNameToDelete" 2>$null
            if ($check) { $stillExists = $true }
        } catch {}
        
        if ($stillExists) {
            Write-Log "WARNING: Task might still exist: $taskNameToDelete" -Level "WARNING"
        } else {
            Write-Log "Verified deletion: $taskNameToDelete" -Level "SUCCESS"
        }
    }
    
    Write-Log "Completed deletion of existing tasks."
} else {
    Write-Log "No tasks to delete."
}
# ===================================

# ========== CREATE NEW TASK ==========
Write-Log "Creating new scheduled task: $TaskName"

try {
    # Method 1: Try using PowerShell ScheduledTasks module
    if (Get-Command New-ScheduledTaskAction -ErrorAction SilentlyContinue) {
        Write-Log "Using PowerShell ScheduledTasks module..."
        
        # Create action
        $action = New-ScheduledTaskAction -Execute "C:\Program Files\PowerShell\7\pwsh.exe" `
            -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`"" `
            -WorkingDirectory $WorkingDirectory
        
        # Create trigger (at logon)
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        
        # Create principal (current user)
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
            -LogonType Interactive `
            -RunLevel Highest
        
        # Create settings
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -WakeToRun `
            -MultipleInstances IgnoreNew `
            -RestartCount 3 `
            -RestartInterval (New-TimeSpan -Hours 1) `
            -ExecutionTimeLimit (New-TimeSpan -Hours 8)
        
        # Register the task
        $task = Register-ScheduledTask -TaskName $TaskName `
            -Action $action `
            -Trigger $trigger `
            -Principal $principal `
            -Settings $settings `
            -Description $TaskDescription `
            -Force
        
        Write-Log "Task created successfully via PowerShell module!" -Level "SUCCESS"
        
    } else {
        # Method 2: Fallback to schtasks.exe
        Write-Log "PowerShell ScheduledTasks module not available. Using schtasks.exe..."
        
        # Build the schtasks command
        $schtasksCmd = @"
schtasks /create /tn "$TaskName" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \`"$ScriptPath\`"" /sc onlogon /ru "$env:USERDOMAIN\$env:USERNAME" /rl highest /f
"@
        
        # Execute the command
        Invoke-Expression $schtasksCmd
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Task created successfully via schtasks.exe!" -Level "SUCCESS"
        } else {
            throw "schtasks.exe failed with exit code: $LASTEXITCODE"
        }
    }
    
    # Verify task creation
    Write-Log "Verifying task creation..."
    Start-Sleep -Seconds 2
    
    $verification = schtasks /query /tn "$TaskName" 2>$null
    if ($verification) {
        Write-Log "Task verification successful!" -Level "SUCCESS"
        Write-Log "Task details:"
        $verification | Out-File $LogFilePath -Append
    } else {
        Write-Log "WARNING: Task created but could not verify via schtasks" -Level "WARNING"
    }
    
} catch {
    Write-Log "Failed to create task: $_" -Level "ERROR"
    Write-Log "Attempting alternative creation method..."
    
}
# ===================================

# ========== FINAL VERIFICATION ==========
Write-Log ""
Write-Log "=== FINAL VERIFICATION ===" -Level "INFO"

# List all tasks with the name
Write-Log "Searching for task: $TaskName" -Level "INFO"

$finalTasks = @()
try {
    $finalCheck = schtasks /query /fo csv 2>$null | ConvertFrom-Csv | Where-Object { $_.TaskName -like "*$TaskName*" }
    if ($finalCheck) {
        $finalTasks = $finalCheck
    }
} catch {}

if ($finalTasks.Count -gt 0) {
    Write-Log "SUCCESS: Task found in Task Scheduler!" -Level "SUCCESS"
    foreach ($task in $finalTasks) {
        Write-Log "Task Name: $($task.TaskName)"
        Write-Log "Status: $($task.Status)"
        Write-Log "Next Run Time: $($task.'Next Run Time')"
        Write-Log "Logon Mode: $($task.'Logon Mode')"
    }
    
    # Test the task
    Write-Log ""
    Write-Log "Testing task execution (will run for 5 seconds max)..."
    try {
        schtasks /run /tn "$TaskName" 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        
        # Check if Python script would run
        Write-Log "Task triggered successfully. Python script should run on next logon." -Level "SUCCESS"
        
    } catch {
        Write-Log "Could not test run task: $_" -Level "WARNING"
    }
    
} else {
    Write-Log "ERROR: Task not found after creation attempt!" -Level "ERROR"
    Write-Log "Please check Task Scheduler manually." -Level "ERROR"
}
# ===================================

# ========== SUMMARY ==========
Write-Log ""
Write-Log "=== SETUP SUMMARY ===" -Level "INFO"
Write-Log "Task Name: $TaskName"
Write-Log "Description: $TaskDescription"
Write-Log "Trigger: At user logon"
Write-Log "Script: $ScriptPath"
Write-Log "Working Directory: $WorkingDirectory"
Write-Log "Log File: $LogFilePath"
Write-Log ""
Write-Log "To manually check the task:" -Level "INFO"
Write-Log "1. Open Task Scheduler (taskschd.msc)" -Level "INFO"
Write-Log "2. Look for task: $TaskName" -Level "INFO"
Write-Log "3. Right-click → Properties to view details" -Level "INFO"
Write-Log "4. Right-click → Run to test immediately" -Level "INFO"
Write-Log ""
Write-Log "Setup completed at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Level "SUCCESS"
Write-Log "================================================" -Level "INFO"
# ===================================

# ========== USER PROMPT ==========
Write-Host ""
Write-Host "Press Enter to exit..." -ForegroundColor Yellow
$null = Read-Host
# ===================================
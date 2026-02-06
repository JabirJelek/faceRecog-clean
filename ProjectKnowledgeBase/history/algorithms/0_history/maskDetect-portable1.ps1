# secondScript.ps1 - UPDATED WITH PORTABILITY AND STABILITY FIXES
# ================================================================
# Organized version with unified folder structure
# ================================================================

# ========== ERROR HANDLING CONFIGURATION ==========
$ErrorActionPreference = "Stop"  # Make script stop on errors
Set-StrictMode -Version Latest

# ========== PORTABLE PATH INITIALIZATION ==========

function Initialize-ProjectPortablePaths {
    [CmdletBinding()]
    param()
    
    try {
        Write-Host "Initializing portable paths for maskRecog project..." -ForegroundColor Cyan
        
        # ====================================================================
        # STEP 1: FIND THE PROJECT ROOT (maskRecog directory)
        # ====================================================================
        
        $scriptPath = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
        $currentPath = $scriptPath
        $projectRoot = $null
        
        # Look for maskRecog by going UP through parent directories (max 10 levels)
        $maxDepth = 10
        $depth = 0
        
        while ($currentPath -and $depth -lt $maxDepth) {
            $currentDirName = Split-Path $currentPath -Leaf
            
            if ($currentDirName -eq "maskRecog") {
                $projectRoot = $currentPath
                Write-Host "Found project root: $projectRoot" -ForegroundColor Green
                break
            }
            
            $parentPath = Split-Path $currentPath -Parent
            # Stop if we reach drive root
            if (!$parentPath -or $parentPath -eq $currentPath -or 
                $parentPath.Length -le 3) { # Drive root like "C:\"
                break
            }
            $currentPath = $parentPath
            $depth++
        }
        
        # Alternative: Check current directory
        if (!$projectRoot) {
            $currentDir = Get-Location
            if ((Split-Path $currentDir -Leaf) -eq "maskRecog") {
                $projectRoot = $currentDir
            }
        }
        
        # Last resort - ask user
        if (!$projectRoot) {
            Write-Host "Could not automatically find 'maskRecog' directory." -ForegroundColor Yellow
            $projectRoot = Read-Host "Please enter the full path to 'maskRecog' project root"
            
            if (!(Test-Path $projectRoot)) {
                throw "Path '$projectRoot' does not exist!"
            }
        }

        # Normalize path
        $projectRoot = [System.IO.Path]::GetFullPath($projectRoot)
        
        # ====================================================================
        # STEP 2: BUILD PATHS RELATIVE TO PROJECT ROOT
        # ====================================================================
        
        # Store project root globally so all functions can use it
        $global:ProjectRoot = $projectRoot
        
        # Calculate parent paths safely
        try {
            $parent1 = Split-Path $projectRoot -Parent
            $parent2 = Split-Path $parent1 -Parent
            $global:ActiveRoot = $parent2
            $global:VENV_ROOT = Split-Path $parent2 -Parent | Split-Path -Parent
        } catch {
            Write-Warning "Could not calculate parent paths: $_"
            $global:ActiveRoot = $projectRoot
            $global:VENV_ROOT = Join-Path $env:USERPROFILE "venv"
        }
        
        # Show what we found
        Write-Host "Project Root: $ProjectRoot" -ForegroundColor Green
        Write-Host "Active Root: $ActiveRoot" -ForegroundColor Green
        Write-Host "Venv Root: $VENV_ROOT" -ForegroundColor Green
        
        # ====================================================================
        # STEP 3: CREATE DATE-BASED FOLDER STRUCTURE
        # ====================================================================
        
        $currentDate = Get-Date -Format "yyyy-MM-dd"
        $global:CurrentDateFolder = $currentDate
        
        # Create the base Magick folder
        $magickBasePath = Join-Path $ActiveRoot "logs-running\magick"
        if (-not (Test-Path $magickBasePath)) {
            New-Item -ItemType Directory -Path $magickBasePath -Force -ErrorAction Stop | Out-Null
            Write-Host "Created base magick folder: $magickBasePath" -ForegroundColor Yellow
        }
        
        # Create date-specific folder
        $dateBasedPath = Join-Path $magickBasePath $currentDate
        if (-not (Test-Path $dateBasedPath)) {
            New-Item -ItemType Directory -Path $dateBasedPath -Force -ErrorAction Stop | Out-Null
            Write-Host "Created date-based folder: $dateBasedPath" -ForegroundColor Yellow
        } else {
            Write-Host "Using existing date-based folder: $dateBasedPath" -ForegroundColor Green
        }
        
        $global:ActiveDatePath = $dateBasedPath
        
        # ====================================================================
        # STEP 4: VALIDATE CRITICAL COMPONENTS EXIST
        # ====================================================================
        
        $PYTHON_SCRIPT = Join-Path $ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
        $RUNS_BASE_PATH = $dateBasedPath
        
        Write-Host "`nValidating project components..." -ForegroundColor Yellow
        
        $criticalComponents = @(
            @{ Name = "Virtual Environment"; Path = $VENV_ROOT; IsDir = $true }
            @{ Name = "Python Script"; Path = $PYTHON_SCRIPT; IsDir = $false }
            @{ Name = "Date-Based Log Directory"; Path = $dateBasedPath; IsDir = $true }
            @{ Name = "Python Executable"; Path = "$VENV_ROOT\Scripts\python.exe"; IsDir = $false }
        )
        
        $missingComponents = @()
        $createdDirectories = @()
        
        foreach ($component in $criticalComponents) {
            if (!(Test-Path $component.Path)) {
                Write-Host "  [MISSING] $($component.Name): $($component.Path)" -ForegroundColor Red
                
                # Try to create missing directories
                if ($component.IsDir) {
                    try {
                        New-Item -ItemType Directory -Path $component.Path -Force -ErrorAction Stop | Out-Null
                        Write-Host "  [CREATED] Directory: $($component.Path)" -ForegroundColor Yellow
                        $createdDirectories += $component.Path
                    } catch {
                        $missingComponents += $component.Name
                        Write-Warning "Failed to create directory $($component.Path): $_"
                    }
                } else {
                    $missingComponents += $component.Name
                }
            } else {
                Write-Host "  [OK] $($component.Name)" -ForegroundColor Green
            }
        }
        
        # ====================================================================
        # STEP 5: SUMMARY AND ERROR HANDLING
        # ====================================================================
        
        if ($missingComponents.Count -gt 0) {
            Write-Host "`nWARNING: Missing critical components!" -ForegroundColor Red
            foreach ($missing in $missingComponents) {
                Write-Host "  - $missing" -ForegroundColor Red
            }
            
            Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
            Write-Host "1. Ensure virtual environment exists at: $VENV_ROOT" -ForegroundColor Yellow
            Write-Host "2. Check that Python script is at: $PYTHON_SCRIPT" -ForegroundColor Yellow
            Write-Host "3. Verify you have read/write permissions" -ForegroundColor Yellow
            
            if ($missingComponents -contains "Python Executable") {
                $pythonExe = Get-Command python -ErrorAction SilentlyContinue
                if ($pythonExe) {
                    Write-Host "`nFound system Python at: $($pythonExe.Source)" -ForegroundColor Yellow
                    $VENV_ROOT = Split-Path (Split-Path $pythonExe.Source -Parent) -Parent
                    Write-Host "Updated VENV_ROOT to: $VENV_ROOT" -ForegroundColor Yellow
                }
            }
            
            $continue = Read-Host "`nSome components are missing. Continue anyway? (Y/N)"
            if ($continue -notmatch '^[Yy]') {
                throw "User cancelled due to missing components"
            }
        }
        
        Write-Host "`nProject initialization complete!" -ForegroundColor Green
        
        # Return the validated paths
        return @{
            ProjectRoot = $projectRoot
            ActiveRoot = $global:ActiveRoot
            ActiveDatePath = $dateBasedPath
            VENV_ROOT = $VENV_ROOT
            PYTHON_SCRIPT = $PYTHON_SCRIPT
            RUNS_BASE_PATH = $dateBasedPath
        }
        
    } catch {
        Write-Error "Initialization failed: $_"
        throw
    }
}

# ========== HELPER FUNCTIONS ==========

function Convert-HashtableToArgs {
    param([hashtable]$Params)
    
    $argsArray = @()
    foreach ($key in $Params.Keys) {
        if ($key) {
            $argsArray += $key
            if ($Params[$key] -ne $null -and $Params[$key] -ne "") {
                $argsArray += $Params[$key]
            }
        }
    }
    return $argsArray
}

function Test-PythonEnvironment {
    param(
        [string]$PythonExe,
        [string]$PythonScript
    )
    
    try {
        # Test if Python executable works
        $pythonVersion = & $PythonExe --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Python executable test failed: $pythonVersion"
        }
        
        Write-Host "Python version: $pythonVersion" -ForegroundColor Green
        
        # Test if script can be imported
        $testCommand = @"
import sys
sys.path.append("$([System.IO.Path]::GetDirectoryName('$PythonScript').Replace('\', '\\'))")
try:
    import $( [System.IO.Path]::GetFileNameWithoutExtension('$PythonScript') )
    print("Script import test: PASSED")
except Exception as e:
    print(f"Script import test: FAILED - {e}")
    sys.exit(1)
"@
        
        $testResult = $testCommand | & $PythonExe -c "$testCommand" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Script import test failed: $testResult"
        } else {
            Write-Host $testResult -ForegroundColor Green
        }
        
        return $true
    } catch {
        Write-Error "Python environment test failed: $_"
        return $false
    }
}

# ========== MAIN EXECUTION ==========

try {
    Write-Host "=== Mask Detection Worker Script ===" -ForegroundColor Cyan
    Write-Host "Starting portable path initialization..." -ForegroundColor Cyan
    
    $paths = Initialize-ProjectPortablePaths
    
    # Extract validated paths
    $VENV_ROOT = $paths.VENV_ROOT
    $PYTHON_SCRIPT = $paths.PYTHON_SCRIPT
    $RUNS_BASE_PATH = $paths.RUNS_BASE_PATH
    $ProjectRoot = $paths.ProjectRoot
    $ActiveDatePath = $paths.ActiveDatePath
    
    # Get current script name for logging
    $POWERSHELL_SCRIPT_NAME = Split-Path -Leaf $MyInvocation.MyCommand.Path
    
    # Define Python parameters
    $PYTHON_PARAMS = @{
        "--multi-source" = $null
    }
    
    # Convert hashtable to argument array
    $PYTHON_ARGS = Convert-HashtableToArgs -Params $PYTHON_PARAMS
    
    # ========== RUN FOLDER SETUP ==========
    
    # Create runs base directory if it doesn't exist
    if (-not (Test-Path $RUNS_BASE_PATH)) {
        New-Item -ItemType Directory -Path $RUNS_BASE_PATH -Force -ErrorAction Stop | Out-Null
        Write-Host "Created runs base directory: $RUNS_BASE_PATH"
    }
    
    # Generate run folder with timestamp
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $RUN_FOLDER_NAME = "Magick_Process_MaskDetect_$timestamp"
    $RUN_FOLDER_PATH = Join-Path $RUNS_BASE_PATH $RUN_FOLDER_NAME
    
    # Create run folder structure
    $RUN_LOGS_PATH = Join-Path $RUN_FOLDER_PATH "logs"
    $RUN_SCRIPT_OUTPUT_PATH = Join-Path $RUN_FOLDER_PATH "script_output"
    $RUN_METADATA_PATH = Join-Path $RUN_FOLDER_PATH "metadata.json"
    
    try {
        # Create all directories
        New-Item -ItemType Directory -Path $RUN_FOLDER_PATH -Force -ErrorAction Stop | Out-Null
        New-Item -ItemType Directory -Path $RUN_LOGS_PATH -Force -ErrorAction Stop | Out-Null
        New-Item -ItemType Directory -Path $RUN_SCRIPT_OUTPUT_PATH -Force -ErrorAction Stop | Out-Null
        
        Write-Host "Created run folder structure at: $RUN_FOLDER_PATH" -ForegroundColor Green
    } catch {
        throw "Failed to create run folder structure: $_"
    }
    
    # ========== LOG FILE SETUP ==========
    $MAIN_LOG_FILE = Join-Path $RUN_LOGS_PATH "run_$timestamp.log"
    $PYTHON_OUTPUT_FILE = Join-Path $RUN_LOGS_PATH "python_output.txt"
    $COMPLETION_SUMMARY_FILE = Join-Path $RUN_LOGS_PATH "completion_summary.txt"
    
    # Format arguments for logging
    $argsString = $PYTHON_ARGS -join " "
    
    # Write initial log header
    $logHeader = @"
==================================================
RUN STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run Folder: $RUN_FOLDER_PATH
PowerShell Script: $POWERSHELL_SCRIPT_NAME
Project Root: $ProjectRoot
Active Date Path: $ActiveDatePath
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT
Arguments: $argsString
Number of arguments: $($PYTHON_ARGS.Count)
==================================================
"@
    
    $logHeader | Out-File $MAIN_LOG_FILE -Encoding UTF8
    
    # ========== CREATE METADATA FILE ==========
    $metadata = @{
        run_id = $timestamp
        start_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        powershell_script = $POWERSHELL_SCRIPT_NAME
        project_root = $ProjectRoot
        active_date_path = $ActiveDatePath
        virtual_env = $VENV_ROOT
        python_script = $PYTHON_SCRIPT
        arguments = $PYTHON_ARGS
        arguments_count = $PYTHON_ARGS.Count
        run_folder = $RUN_FOLDER_PATH
        system_info = @{
            computer_name = $env:COMPUTERNAME
            user_name = $env:USERNAME
            os_version = [System.Environment]::OSVersion.VersionString
            powershell_version = $PSVersionTable.PSVersion.ToString()
        }
    }
    
    $metadata | ConvertTo-Json -Depth 5 | Out-File $RUN_METADATA_PATH -Encoding UTF8
    Write-Host "Created metadata file: $RUN_METADATA_PATH" -ForegroundColor Green
    
    # ========== PYTHON ENVIRONMENT VALIDATION ==========
    Write-Host "`nValidating Python environment..." -ForegroundColor Yellow
    
    $pythonExe = "$VENV_ROOT\Scripts\python.exe"
    
    # Try alternate Python paths if primary doesn't exist
    if (-not (Test-Path $pythonExe)) {
        $alternatePaths = @(
            "$VENV_ROOT\Scripts\python3.exe",
            "$VENV_ROOT\Scripts\python",
            (Get-Command python -ErrorAction SilentlyContinue).Source,
            (Get-Command python3 -ErrorAction SilentlyContinue).Source
        )
        
        foreach ($altPath in $alternatePaths) {
            if ($altPath -and (Test-Path $altPath)) {
                $pythonExe = $altPath
                Write-Host "Using alternate Python path: $pythonExe" -ForegroundColor Yellow
                break
            }
        }
    }
    
    if (-not (Test-Path $pythonExe)) {
        throw "Python executable not found at any expected location"
    }
    
    # Test Python environment
    if (-not (Test-PythonEnvironment -PythonExe $pythonExe -PythonScript $PYTHON_SCRIPT)) {
        Write-Warning "Python environment tests failed, but continuing..."
    }
    
    # ========== EXECUTION ==========
    Write-Host "`nStarting Python script execution..." -ForegroundColor Cyan
    Write-Host "Run folder: $RUN_FOLDER_PATH"
    Write-Host "Arguments: $argsString"
    Write-Host ""
    
    # Capture start time
    $startTime = Get-Date
    "Execution started at: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append
    
    $exitCode = 0
    $pythonOutput = $null
    
    try {
        # Prepare the command for logging
        $commandString = "`"$pythonExe`" `"$PYTHON_SCRIPT`" $argsString"
        Write-Host "Executing: $commandString"
        $commandString | Out-File $MAIN_LOG_FILE -Append
        "" | Out-File $MAIN_LOG_FILE -Append
        
        Write-Host "Python output will be saved to: $PYTHON_OUTPUT_FILE"
        
        # Store original location
        $originalLocation = Get-Location
        
        try {
            # Set working directory to script_output
            Set-Location $RUN_SCRIPT_OUTPUT_PATH
            
            # Create a process info object for better control
            $processInfo = New-Object System.Diagnostics.ProcessStartInfo
            $processInfo.FileName = $pythonExe
            $processInfo.Arguments = "`"$PYTHON_SCRIPT`" $argsString"
            $processInfo.RedirectStandardOutput = $true
            $processInfo.RedirectStandardError = $true
            $processInfo.UseShellExecute = $false
            $processInfo.CreateNoWindow = $true
            $processInfo.WorkingDirectory = $RUN_SCRIPT_OUTPUT_PATH
            
            $process = New-Object System.Diagnostics.Process
            $process.StartInfo = $processInfo
            
            # Start the process
            $processStarted = $process.Start()
            if (-not $processStarted) {
                throw "Failed to start Python process"
            }
            
            # Read output asynchronously
            $stdOutBuilder = New-Object System.Text.StringBuilder
            $stdErrBuilder = New-Object System.Text.StringBuilder
            
            $stdOutJob = Register-ObjectEvent -InputObject $process -EventName OutputDataReceived -Action {
                param($sender, $e)
                if ($e.Data) {
                    $stdOutBuilder.AppendLine($e.Data) | Out-Null
                    Write-Host $e.Data
                }
            }
            
            $stdErrJob = Register-ObjectEvent -InputObject $process -EventName ErrorDataReceived -Action {
                param($sender, $e)
                if ($e.Data) {
                    $stdErrBuilder.AppendLine($e.Data) | Out-Null
                    Write-Host $e.Data -ForegroundColor Red
                }
            }
            
            $process.BeginOutputReadLine()
            $process.BeginErrorReadLine()
            
            # Wait for process to exit with timeout (6 hours)
            $timeoutMinutes = 360
            if (-not $process.WaitForExit($timeoutMinutes * 60 * 1000)) {
                $process.Kill()
                throw "Python process timed out after $timeoutMinutes minutes"
            }
            
            $exitCode = $process.ExitCode
            
            # Get the output
            $pythonOutput = $stdOutBuilder.ToString() + $stdErrBuilder.ToString()
            
            # Clean up event handlers
            Unregister-Event -SourceIdentifier $stdOutJob.Name -ErrorAction SilentlyContinue
            Unregister-Event -SourceIdentifier $stdErrJob.Name -ErrorAction SilentlyContinue
            
        } finally {
            # Always return to original location
            Set-Location $originalLocation
        }
        
        # Save output to file
        $pythonOutput | Out-File $PYTHON_OUTPUT_FILE -Encoding UTF8
        
    } catch {
        $errorMessage = $_.Exception.Message
        "EXCEPTION: $errorMessage" | Out-File $MAIN_LOG_FILE -Append
        $errorMessage | Out-File $PYTHON_OUTPUT_FILE -Append
        Write-Error "Exception during Python script execution: $errorMessage"
        $exitCode = 1
    }
    
    # Capture end time
    $endTime = Get-Date
    $duration = $endTime - $startTime
    $durationFormatted = "{0:D2}:{1:D2}:{2:D2}" -f $duration.Hours, $duration.Minutes, $duration.Seconds
    
    # ========== POST-EXECUTION LOGGING ==========
    "" | Out-File $MAIN_LOG_FILE -Append
    "==================================================" | Out-File $MAIN_LOG_FILE -Append
    "EXECUTION SUMMARY" | Out-File $MAIN_LOG_FILE -Append
    "==================================================" | Out-File $MAIN_LOG_FILE -Append
    "PowerShell Script: $POWERSHELL_SCRIPT_NAME" | Out-File $MAIN_LOG_FILE -Append
    "Project Root: $ProjectRoot" | Out-File $MAIN_LOG_FILE -Append
    "Active Date Path: $ActiveDatePath" | Out-File $MAIN_LOG_FILE -Append
    "Exit code: $exitCode" | Out-File $MAIN_LOG_FILE -Append
    "Start time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append
    "End time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append
    "Duration: $durationFormatted" | Out-File $MAIN_LOG_FILE -Append
    
    # Find what Python script created
    try {
        $createdFolders = Get-ChildItem -Path $RUN_SCRIPT_OUTPUT_PATH -Directory -ErrorAction SilentlyContinue
        if ($createdFolders) {
            "Python script created folders:" | Out-File $MAIN_LOG_FILE -Append
            foreach ($folder in $createdFolders) {
                "  - $($folder.FullName)" | Out-File $MAIN_LOG_FILE -Append
            }
        } else {
            "No folders were created by Python script in: $RUN_SCRIPT_OUTPUT_PATH" | Out-File $MAIN_LOG_FILE -Append
        }
    } catch {
        "Could not analyze created folders: $_" | Out-File $MAIN_LOG_FILE -Append
    }
    
    # ========== CREATE COMPLETION SUMMARY ==========
    $completionSummary = @"
==================================================
RUN COMPLETION SUMMARY
==================================================
Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run ID: $timestamp
PowerShell Script: $POWERSHELL_SCRIPT_NAME
Project Root: $ProjectRoot
Active Date Path: $ActiveDatePath
Status: $(if ($exitCode -eq 0) { "SUCCESS" } else { "FAILED (Exit code: $exitCode)" })

PORTABLE PATHS USED
==================================================
Project Root: $ProjectRoot
Active Date Path: $ActiveDatePath
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT

FOLDER STRUCTURE
==================================================
Run Folder: $RUN_FOLDER_PATH
├── logs\
│   ├── run_$timestamp.log          (This main log file)
│   ├── python_output.txt           (Full Python script output)
│   └── completion_summary.txt      (This summary)
├── script_output\                  (Python script's working directory)
│   └── [Output folders created by Python]
└── metadata.json                   (Run configuration metadata)

EXECUTION DETAILS
==================================================
PowerShell Script: $POWERSHELL_SCRIPT_NAME
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT
Start Time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))
End Time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))
Duration: $durationFormatted

ARGUMENTS PASSED
==================================================
$($PYTHON_ARGS | ForEach-Object { "  $_" } | Out-String)

LOG FILES
==================================================
1. Main Execution Log: $MAIN_LOG_FILE
2. Python Output: $PYTHON_OUTPUT_FILE
3. Python Exit Code: $exitCode

SCRIPT OUTPUT LOCATION
==================================================
Any folders/files created by the Python script should be located in:
$RUN_SCRIPT_OUTPUT_PATH

NOTE: This run uses portable paths that are relative to the project root.
==================================================
"@

    $completionSummary | Out-File $COMPLETION_SUMMARY_FILE -Encoding UTF8
    
    # Update metadata with completion info
    try {
        $completionMetadata = Get-Content $RUN_METADATA_PATH -Raw | ConvertFrom-Json
        $completionMetadata | Add-Member -NotePropertyName "end_time" -NotePropertyValue (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Force
        $completionMetadata | Add-Member -NotePropertyName "duration" -NotePropertyValue $durationFormatted -Force
        $completionMetadata | Add-Member -NotePropertyName "exit_code" -NotePropertyValue $exitCode -Force
        $completionMetadata | Add-Member -NotePropertyName "process_id" -NotePropertyValue $PID -Force
        $completionMetadata | ConvertTo-Json -Depth 5 | Out-File $RUN_METADATA_PATH -Encoding UTF8
    } catch {
        Write-Warning "Could not update metadata file: $_"
    }
    
    # ========== FINAL OUTPUT ==========
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "RUN COMPLETED" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "PowerShell Script: $POWERSHELL_SCRIPT_NAME"
    Write-Host "Project Root: $ProjectRoot"
    Write-Host "Active Date Path: $ActiveDatePath"
    Write-Host "Run Folder: $RUN_FOLDER_PATH"
    Write-Host "Main Log: $MAIN_LOG_FILE"
    Write-Host "Python Output: $PYTHON_OUTPUT_FILE"
    Write-Host "Completion Summary: $COMPLETION_SUMMARY_FILE"
    Write-Host "Metadata: $RUN_METADATA_PATH"
    Write-Host ""
    Write-Host "Arguments used:"
    $PYTHON_ARGS | ForEach-Object { Write-Host "  $_" }
    Write-Host ""
    Write-Host "All logs and outputs are organized in the run folder."
    Write-Host "Exit code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
    Write-Host "Duration: $durationFormatted"
    Write-Host "==================================================" -ForegroundColor Cyan
    
    # Exit with Python's exit code
    exit $exitCode
    
} catch {
    Write-Error "Script execution failed: $_"
    Write-Host "Error occurred at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Red
    
    # Try to log the error even if everything else failed
    try {
        $errorLogPath = Join-Path (Get-Location) "script_error_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
        @"
SCRIPT FAILURE REPORT
Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Error: $($_.Exception.Message)
StackTrace: $($_.Exception.StackTrace)
Script: $($MyInvocation.MyCommand.Path)
Working Directory: $(Get-Location)
"@ | Out-File $errorLogPath
        Write-Host "Error details saved to: $errorLogPath" -ForegroundColor Yellow
    } catch {
        # Last resort - output to console
        Write-Host "Could not save error log: $_" -ForegroundColor Red
    }
    
    exit 1
}
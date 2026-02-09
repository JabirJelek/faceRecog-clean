# old-worker.ps1
# ==============================================
# Organized version with unified folder structure
# ==============================================

# ========== PORTABLE PATH INITIALIZATION ==========

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
    # STEP 4: VALIDATE CRITICAL COMPONENTS EXIST
    # ====================================================================
    
    # Build portable paths
    $VENV_ROOT = "D:\RaihanFarid\Dokumen\faceRecog\.venv"  # Keep as is or make relative
    $PYTHON_SCRIPT = Join-Path $ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
    
    # Base path for all runs (using date-based structure)
    $RUNS_BASE_PATH = $dateBasedPath
    
    Write-Host "`nValidating project components..." -ForegroundColor Yellow
    
    $criticalComponents = @(
        @{ Name = "Virtual Environment"; Path = $VENV_ROOT }
        @{ Name = "Python Script"; Path = $PYTHON_SCRIPT }
        @{ Name = "Date-Based Log Directory"; Path = $dateBasedPath }
        @{ Name = "Python Executable"; Path = "$VENV_ROOT\Scripts\python.exe" }
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
    # STEP 5: SUMMARY AND ERROR HANDLING
    # ====================================================================
    
    if ($missingComponents.Count -gt 0) {
        Write-Host "`nERROR: Missing critical components!" -ForegroundColor Red
        foreach ($missing in $missingComponents) {
            Write-Host "  - $missing" -ForegroundColor Red
        }
        
        Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
        Write-Host "1. Ensure virtual environment exists at: $VENV_ROOT" -ForegroundColor Yellow
        Write-Host "2. Check that Python script is at: $PYTHON_SCRIPT" -ForegroundColor Yellow
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
    
    # Return the validated paths
    return @{
        ProjectRoot = $projectRoot
        ActiveRoot = $global:ActiveRoot
        ActiveDatePath = $dateBasedPath
        VENV_ROOT = $VENV_ROOT
        PYTHON_SCRIPT = $PYTHON_SCRIPT
        RUNS_BASE_PATH = $dateBasedPath
    }
}

# ========== MAIN EXECUTION ==========

# Initialize portable paths and get validated paths
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

# Alternative: Use hashtable for named parameters (more readable)
$PYTHON_PARAMS = @{
    # "--database" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\current_database-Copy"
    # "--input" = "D:\RaihanFarid\Dokumen\0_classified_with_deepface\temp\process-run\Run_Classified2026-01-21_15-11-08\script_output\classified_output"
    "--multi-source" = $null #Null is for Flag parameter
}

# ===================================

# Helper function to convert hashtable to argument array
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

# If using hashtable approach, convert to array
$PYTHON_ARGS = Convert-HashtableToArgs -Params $PYTHON_PARAMS

# Create runs base directory if it doesn't exist
if (-not (Test-Path $RUNS_BASE_PATH)) {
    New-Item -ItemType Directory -Path $RUNS_BASE_PATH -Force | Out-Null
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
    New-Item -ItemType Directory -Path $RUN_FOLDER_PATH -Force | Out-Null
    New-Item -ItemType Directory -Path $RUN_LOGS_PATH -Force | Out-Null
    New-Item -ItemType Directory -Path $RUN_SCRIPT_OUTPUT_PATH -Force | Out-Null
    
    Write-Host "Created run folder structure at: $RUN_FOLDER_PATH"
} catch {
    Write-Error "Failed to create run folder structure: $_"
    exit 1
}

# ========== LOG FILE SETUP ==========
$MAIN_LOG_FILE = Join-Path $RUN_LOGS_PATH "run_$timestamp.log"
$PYTHON_OUTPUT_FILE = Join-Path $RUN_LOGS_PATH "python_output.txt"
$COMPLETION_SUMMARY_FILE = Join-Path $RUN_LOGS_PATH "completion_summary.txt"

# Format arguments for logging
$argsString = $PYTHON_ARGS -join " "

# Write initial log header
"==================================================" | Out-File $MAIN_LOG_FILE
"RUN STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $MAIN_LOG_FILE -Append
"Run Folder: $RUN_FOLDER_PATH" | Out-File $MAIN_LOG_FILE -Append
"PowerShell Script: $POWERSHELL_SCRIPT_NAME" | Out-File $MAIN_LOG_FILE -Append
"Project Root: $ProjectRoot" | Out-File $MAIN_LOG_FILE -Append
"Active Date Path: $ActiveDatePath" | Out-File $MAIN_LOG_FILE -Append
"Virtual Environment: $VENV_ROOT" | Out-File $MAIN_LOG_FILE -Append
"Python Script: $PYTHON_SCRIPT" | Out-File $MAIN_LOG_FILE -Append
"Arguments: $argsString" | Out-File $MAIN_LOG_FILE -Append
"Number of arguments: $($PYTHON_ARGS.Count)" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append
"" | Out-File $MAIN_LOG_FILE -Append

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
}

$metadata | ConvertTo-Json | Out-File $RUN_METADATA_PATH
Write-Host "Created metadata file: $RUN_METADATA_PATH"

# ========== EXECUTION ==========
Write-Host "Starting Python script execution..."
Write-Host "Run folder: $RUN_FOLDER_PATH"
Write-Host "Arguments: $argsString"
Write-Host ""

$pythonExe = "$VENV_ROOT\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    $errorMsg = "ERROR: Python executable not found at $pythonExe"
    $errorMsg | Out-File $MAIN_LOG_FILE -Append
    Write-Error $errorMsg
    exit 1
}

# Capture start time
$startTime = Get-Date
"Execution started at: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append

try {
    # Prepare the command for logging
    $commandString = "`"$pythonExe`" `"$PYTHON_SCRIPT`" $argsString"
    Write-Host "Executing: $commandString"
    $commandString | Out-File $MAIN_LOG_FILE -Append
    "" | Out-File $MAIN_LOG_FILE -Append
    
    Write-Host "Python output will be saved to: $PYTHON_OUTPUT_FILE"
    
    # ========== KEY CHANGE: Run Python with working directory set to script_output ==========
    # This ensures Python creates its output folder inside our organized structure
    $originalLocation = Get-Location
    Set-Location $RUN_SCRIPT_OUTPUT_PATH
    
    # Run Python with array of arguments (PowerShell will handle them properly)
    & $pythonExe $PYTHON_SCRIPT $PYTHON_ARGS 2>&1 | Tee-Object -FilePath $PYTHON_OUTPUT_FILE
    
    $exitCode = $LASTEXITCODE
    
    # Return to original location
    Set-Location $originalLocation
    
} catch {
    $errorMessage = $_.Exception.Message
    "EXCEPTION: $errorMessage" | Out-File $MAIN_LOG_FILE -Append
    $errorMessage | Out-File $PYTHON_OUTPUT_FILE -Append
    Write-Error "Exception during Python script execution: $errorMessage"
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

# Detailed argument logging
"Arguments passed to Python script:" | Out-File $MAIN_LOG_FILE -Append
for ($i = 0; $i -lt $PYTHON_ARGS.Count; $i++) {
    "  [$i]: $($PYTHON_ARGS[$i])" | Out-File $MAIN_LOG_FILE -Append
}

# Find what Python script created (look for newly created folders in script_output)
try {
    $createdFolders = Get-ChildItem -Path $RUN_SCRIPT_OUTPUT_PATH -Directory | 
                     Where-Object { $_.CreationTime -ge $startTime } | 
                     Select-Object -ExpandProperty FullName
    
    if ($createdFolders) {
        "Python script created folders:" | Out-File $MAIN_LOG_FILE -Append
        foreach ($folder in $createdFolders) {
            "  - $folder" | Out-File $MAIN_LOG_FILE -Append
        }
    } else {
        "No new folders were created by Python script in: $RUN_SCRIPT_OUTPUT_PATH" | Out-File $MAIN_LOG_FILE -Append
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

$completionSummary | Out-File $COMPLETION_SUMMARY_FILE

# Update metadata with completion info
$completionMetadata = Get-Content $RUN_METADATA_PATH | ConvertFrom-Json
$completionMetadata | Add-Member -NotePropertyName "end_time" -NotePropertyValue (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Force
$completionMetadata | Add-Member -NotePropertyName "duration" -NotePropertyValue $durationFormatted -Force
$completionMetadata | Add-Member -NotePropertyName "exit_code" -NotePropertyValue $exitCode -Force
$completionMetadata | Add-Member -NotePropertyName "python_pid" -NotePropertyValue $PID -Force  # Store PID for monitoring
$completionMetadata | ConvertTo-Json | Out-File $RUN_METADATA_PATH

# ========== FINAL OUTPUT ==========
Write-Host ""
Write-Host "=================================================="
Write-Host "RUN COMPLETED"
Write-Host "=================================================="
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
Write-Host "Exit code: $exitCode"
Write-Host "Duration: $durationFormatted"
Write-Host "=================================================="

# Exit with Python's exit code
exit $exitCode
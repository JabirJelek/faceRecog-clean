# run_python_with_venv_organized.ps1
# ==============================================
# Organized version with unified folder structure
# ==============================================

# ========== CONFIGURATION ==========
$VENV_ROOT = "C:\raihan\dokumen\project\Computer-Vision-CV\common1"
$PYTHON_SCRIPT = "C:\raihan\dokumen\project\Computer-Vision-CV\3.1_FaceRecog\run_py\modular\entry_multi-USED-TowerCPU.py"
$ARG1 = "--multi-source"

# Base path for all runs (outside virtual environment)
$RUNS_BASE_PATH = "C:\raihan\dokumen\project\DeteksiMasker"
# ===================================

# Create runs base directory if it doesn't exist
if (-not (Test-Path $RUNS_BASE_PATH)) {
    New-Item -ItemType Directory -Path $RUNS_BASE_PATH -Force | Out-Null
    Write-Host "Created runs base directory: $RUNS_BASE_PATH"
}

# Generate run folder with timestamp
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$RUN_FOLDER_NAME = "Run_$timestamp"
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

# Write initial log header
"==================================================" | Out-File $MAIN_LOG_FILE
"RUN STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $MAIN_LOG_FILE -Append
"Run Folder: $RUN_FOLDER_PATH" | Out-File $MAIN_LOG_FILE -Append
"Virtual Environment: $VENV_ROOT" | Out-File $MAIN_LOG_FILE -Append
"Python Script: $PYTHON_SCRIPT" | Out-File $MAIN_LOG_FILE -Append
"Arguments: $ARG1" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append
"" | Out-File $MAIN_LOG_FILE -Append

# ========== CREATE METADATA FILE ==========
$metadata = @{
    run_id = $timestamp
    start_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    virtual_env = $VENV_ROOT
    python_script = $PYTHON_SCRIPT
    arguments = $ARG1
    run_folder = $RUN_FOLDER_PATH
}

$metadata | ConvertTo-Json | Out-File $RUN_METADATA_PATH
Write-Host "Created metadata file: $RUN_METADATA_PATH"

# ========== EXECUTION ==========
Write-Host "Starting Python script execution..."
Write-Host "Run folder: $RUN_FOLDER_PATH"
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
    # Prepare the command
    $command = "`"$pythonExe`" `"$PYTHON_SCRIPT`" $ARG1"
    Write-Host "Executing: $command"
    $command | Out-File $MAIN_LOG_FILE -Append
    "" | Out-File $MAIN_LOG_FILE -Append
    
    Write-Host "Python output will be saved to: $PYTHON_OUTPUT_FILE"
    
    # ========== KEY CHANGE: Run Python with working directory set to script_output ==========
    # This ensures Python creates its output folder inside our organized structure
    $originalLocation = Get-Location
    Set-Location $RUN_SCRIPT_OUTPUT_PATH
    
    # Run Python and capture ALL output
    & $pythonExe $PYTHON_SCRIPT $ARG1 2>&1 | Tee-Object -FilePath $PYTHON_OUTPUT_FILE
    
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
"Exit code: $exitCode" | Out-File $MAIN_LOG_FILE -Append
"Start time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append
"End time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append
"Duration: $durationFormatted" | Out-File $MAIN_LOG_FILE -Append

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
Status: $(if ($exitCode -eq 0) { "SUCCESS" } else { "FAILED (Exit code: $exitCode)" })

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

LOG FILES
==================================================
1. Main Execution Log: $MAIN_LOG_FILE
2. Python Output: $PYTHON_OUTPUT_FILE
3. Python Exit Code: $exitCode

EXECUTION DETAILS
==================================================
Virtual Environment: $VENV_ROOT
Python Script: $PYTHON_SCRIPT
Arguments: $ARG1
Start Time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))
End Time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))
Duration: $durationFormatted

SCRIPT OUTPUT LOCATION
==================================================
Any folders/files created by the Python script should be located in:
$RUN_SCRIPT_OUTPUT_PATH

NOTE: For debugging, check python_output.txt for detailed error messages.
==================================================
"@

$completionSummary | Out-File $COMPLETION_SUMMARY_FILE

# Update metadata with completion info
$completionMetadata = Get-Content $RUN_METADATA_PATH | ConvertFrom-Json
$completionMetadata | Add-Member -NotePropertyName "end_time" -NotePropertyValue (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Force
$completionMetadata | Add-Member -NotePropertyName "duration" -NotePropertyValue $durationFormatted -Force
$completionMetadata | Add-Member -NotePropertyName "exit_code" -NotePropertyValue $exitCode -Force
$completionMetadata | ConvertTo-Json | Out-File $RUN_METADATA_PATH

# ========== FINAL OUTPUT ==========
Write-Host ""
Write-Host "=================================================="
Write-Host "RUN COMPLETED"
Write-Host "=================================================="
Write-Host "Run Folder: $RUN_FOLDER_PATH"
Write-Host "Main Log: $MAIN_LOG_FILE"
Write-Host "Python Output: $PYTHON_OUTPUT_FILE"
Write-Host "Completion Summary: $COMPLETION_SUMMARY_FILE"
Write-Host "Metadata: $RUN_METADATA_PATH"
Write-Host ""
Write-Host "All logs and outputs are organized in the run folder."
Write-Host "Exit code: $exitCode"
Write-Host "Duration: $durationFormatted"
Write-Host "=================================================="

# Exit with Python's exit code
exit $exitCode
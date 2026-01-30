# run_python_interactive.ps1
# ==============================================
# Interactive version that shows Python input prompts and captures all output
# ==============================================

# ========== CONFIGURATION ==========
$VENV_ROOT = "D:\RaihanFarid\Dokumen\Object Detection\testVenv"
$PYTHON_SCRIPT = "D:\RaihanFarid\Dokumen\Object Detection\3.1_FaceRecog\run_py\yolo-face_2.2.py"
$RUNS_BASE_PATH = "D:\RaihanFarid\Dokumen\Process-Run"
# ===================================

# ========== SETUP RUN FOLDER ==========
# Create runs base directory if it doesn't exist
if (-not (Test-Path $RUNS_BASE_PATH)) {
    New-Item -ItemType Directory -Path $RUNS_BASE_PATH -Force | Out-Null
    Write-Host "Created runs base directory: $RUNS_BASE_PATH"
}

# Generate run folder with timestamp
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$RUN_FOLDER_NAME = "Run_$timestamp"
$RUN_FOLDER_PATH = Join-Path $RUNS_BASE_PATH $RUN_FOLDER_NAME

# Create run folder structure
$RUN_LOGS_PATH = Join-Path $RUN_FOLDER_PATH "logs"
$RUN_SCRIPT_OUTPUT_PATH = Join-Path $RUN_FOLDER_PATH "script_output"

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
$MAIN_LOG_FILE = Join-Path $RUN_LOGS_PATH "interactive_run.log"
$PYTHON_OUTPUT_FILE = Join-Path $RUN_LOGS_PATH "python_console_output.txt"

# Write initial log header
"==================================================" | Out-File $MAIN_LOG_FILE
"INTERACTIVE RUN STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $MAIN_LOG_FILE -Append
"Run Folder: $RUN_FOLDER_PATH" | Out-File $MAIN_LOG_FILE -Append
"Virtual Environment: $VENV_ROOT" | Out-File $MAIN_LOG_FILE -Append
"Python Script: $PYTHON_SCRIPT" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append
"" | Out-File $MAIN_LOG_FILE -Append

# ========== CHECK PATHS ==========
Write-Host "Checking paths..." -ForegroundColor Cyan

$pythonExe = "$VENV_ROOT\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $errorMsg = "ERROR: Python executable not found at $pythonExe"
    Write-Host $errorMsg -ForegroundColor Red
    $errorMsg | Out-File $MAIN_LOG_FILE -Append
    exit 1
}

if (-not (Test-Path $PYTHON_SCRIPT)) {
    $errorMsg = "ERROR: Python script not found at $PYTHON_SCRIPT"
    Write-Host $errorMsg -ForegroundColor Red
    $errorMsg | Out-File $MAIN_LOG_FILE -Append
    exit 1
}

Write-Host "Paths verified successfully!" -ForegroundColor Green
# ===================================

# ========== INTERACTIVE PYTHON EXECUTION ==========
Write-Host ""
Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "STARTING INTERACTIVE PYTHON SCRIPT" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Note: The Python script will now run interactively." -ForegroundColor Cyan
Write-Host "You will see all output and prompts from the Python script." -ForegroundColor Cyan
Write-Host "Console output is also being saved to: $PYTHON_OUTPUT_FILE" -ForegroundColor Cyan
Write-Host ""

# Start time
$startTime = Get-Date
"Interactive execution started at: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $MAIN_LOG_FILE -Append

# # Method 1: Using a function to capture console output in real-time
# function Invoke-InteractivePython {
#     param(
#         [string]$PythonExe,
#         [string]$ScriptPath,
#         [string]$OutputFile
#     )
    
#     Write-Host "Running: $PythonExe `"$ScriptPath`"" -ForegroundColor Gray
#     Write-Host "--------------------------------------------------" -ForegroundColor Gray
    
#     # Create a temporary file for the script command
#     $tempCmdFile = Join-Path $env:TEMP "run_python_$timestamp.cmd"
    
#     # Create a batch file that runs Python and logs everything
#     @"
# @echo off
# echo [START] Python script execution at %DATE% %TIME% > "$OutputFile"
# echo Running: $PythonExe "$ScriptPath" >> "$OutputFile"
# echo ================================================== >> "$OutputFile"

# REM Run Python script and capture ALL output (stdout and stderr)
# "$PythonExe" "$ScriptPath" 2>&1 | tee -a "$OutputFile"

# echo ================================================== >> "$OutputFile"
# echo [END] Python script execution at %DATE% %TIME% >> "$OutputFile"
# "@ | Out-File -FilePath $tempCmdFile -Encoding ASCII
    
#     try {
#         # Run the batch file
#         $process = Start-Process -FilePath "cmd.exe" `
#                                  -ArgumentList "/c `"$tempCmdFile`"" `
#                                  -NoNewWindow `
#                                  -Wait `
#                                  -PassThru
        
#         return @{
#             ExitCode = $process.ExitCode
#             Success = ($process.ExitCode -eq 0)
#         }
#     } finally {
#         # Clean up temp file
#         Remove-Item $tempCmdFile -ErrorAction SilentlyContinue
#     }
# }

# Method 2: Alternative PowerShell-based interactive execution
function Invoke-InteractivePythonPS {
    param(
        [string]$PythonExe,
        [string]$ScriptPath,
        [string]$OutputFile
    )
    
    Write-Host "Running Python interactively (PowerShell method)..." -ForegroundColor Gray
    Write-Host "--------------------------------------------------" -ForegroundColor Gray
    
    # Create a script block that runs Python and captures output
    $scriptBlock = {
        param($exe, $script, $logFile)
        
        # Redirect all output streams
        & $exe $script *>&1 | ForEach-Object {
            # Display to console
            Write-Host $_
            # Append to log file
            $_ | Out-File -FilePath $logFile -Append
        }
    }
    
    try {
        # Run in the current console
        & $scriptBlock -exe $pythonExe -script $PYTHON_SCRIPT -logFile $PYTHON_OUTPUT_FILE
        
        return @{
            ExitCode = $LASTEXITCODE
            Success = ($LASTEXITCODE -eq 0)
        }
    } catch {
        Write-Host "Error: $_" -ForegroundColor Red
        return @{
            ExitCode = 1
            Success = $false
        }
    }
}

# Method 3: Simple direct execution (best for interactive input)
function Invoke-SimpleInteractive {
    param(
        [string]$PythonExe,
        [string]$ScriptPath,
        [string]$OutputFile
    )
    
    Write-Host "Executing Python script with full console interaction..." -ForegroundColor Gray
    Write-Host "--------------------------------------------------" -ForegroundColor Gray
    
    # Create a log file header
    "==================================================" | Out-File $OutputFile
    "Interactive Python Execution" | Out-File $OutputFile -Append
    "Start Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $OutputFile -Append
    "Command: $PythonExe `"$ScriptPath`"" | Out-File $OutputFile -Append
    "==================================================" | Out-File $OutputFile -Append
    "" | Out-File $OutputFile -Append
    
    # Run Python directly in current console
    # All console output will be visible to user
    # We'll also capture it to the log file
    
    $exitCode = 0
    try {
        # This runs in the foreground, showing all prompts
        & $PythonExe $ScriptPath 2>&1 | Tee-Object -FilePath $OutputFile -Append
        $exitCode = $LASTEXITCODE
    } catch {
        Write-Host "Execution error: $_" -ForegroundColor Red
        "ERROR: $_" | Out-File $OutputFile -Append
        $exitCode = 1
    }
    
    return @{
        ExitCode = $exitCode
        Success = ($exitCode -eq 0)
    }
}

# Choose which method to use
Write-Host "Select execution method:" -ForegroundColor Yellow
Write-Host "1. Simple interactive (recommended - shows all prompts)" -ForegroundColor Cyan
Write-Host "2. PowerShell interactive" -ForegroundColor Cyan
Write-Host "3. Batch file with tee" -ForegroundColor Cyan
Write-Host ""

$methodChoice = Read-Host "Enter choice (default 1)"

# Set working directory to script_output
$originalLocation = Get-Location
try {
    Set-Location $RUN_SCRIPT_OUTPUT_PATH
    
    switch ($methodChoice) {
        "2" { $result = Invoke-InteractivePythonPS -PythonExe $pythonExe -ScriptPath $PYTHON_SCRIPT -OutputFile $PYTHON_OUTPUT_FILE }
        "3" { $result = Invoke-InteractivePython -PythonExe $pythonExe -ScriptPath $PYTHON_SCRIPT -OutputFile $PYTHON_OUTPUT_FILE }
        default { $result = Invoke-SimpleInteractive -PythonExe $pythonExe -ScriptPath $PYTHON_SCRIPT -OutputFile $PYTHON_OUTPUT_FILE }
    }
} finally {
    # Restore original location
    Set-Location $originalLocation
}
# ===================================

# ========== POST-EXECUTION ==========
$endTime = Get-Date
$duration = $endTime - $startTime
$durationFormatted = "{0:D2}:{1:D2}:{2:D2}" -f $duration.Hours, $duration.Minutes, $duration.Seconds

# Display summary
Write-Host ""
Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "EXECUTION COMPLETE" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow

if ($result.Success) {
    Write-Host "✓ Python script executed SUCCESSFULLY" -ForegroundColor Green
} else {
    Write-Host "✗ Python script execution FAILED" -ForegroundColor Red
    Write-Host "  Exit Code: $($result.ExitCode)" -ForegroundColor Red
}

Write-Host "  Start Time: $($startTime.ToString('HH:mm:ss'))" -ForegroundColor Cyan
Write-Host "  End Time: $($endTime.ToString('HH:mm:ss'))" -ForegroundColor Cyan
Write-Host "  Duration: $durationFormatted" -ForegroundColor Cyan
Write-Host ""

# Check if output file was created and show last few lines
if (Test-Path $PYTHON_OUTPUT_FILE) {
    $fileSize = (Get-Item $PYTHON_OUTPUT_FILE).Length / 1KB
    Write-Host "Console output saved to: $PYTHON_OUTPUT_FILE" -ForegroundColor Cyan
    Write-Host "  File size: {0:N2} KB" -f $fileSize -ForegroundColor Cyan
    
    # Show last 10 lines of output (excluding empty lines)
    $lastLines = Get-Content $PYTHON_OUTPUT_FILE -Tail 20 | Where-Object { $_.Trim() -ne "" }
    if ($lastLines) {
        Write-Host ""
        Write-Host "Last 10 non-empty lines of output:" -ForegroundColor Gray
        Write-Host "----------------------------------------" -ForegroundColor Gray
        foreach ($line in $lastLines) {
            Write-Host $line -ForegroundColor Gray
        }
    }
} else {
    Write-Host "WARNING: No console output file was created" -ForegroundColor Yellow
}
# ===================================

# ========== CREATE COMPLETION SUMMARY ==========
$COMPLETION_FILE = Join-Path $RUN_FOLDER_PATH "interactive_completion_summary.txt"

$completionSummary = @"
==================================================
INTERACTIVE RUN COMPLETION SUMMARY
==================================================
Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run ID: $timestamp
Status: $(if ($result.Success) { "SUCCESS" } else { "FAILED (Exit code: $($result.ExitCode))" })

FOLDER STRUCTURE
==================================================
Run Folder: $RUN_FOLDER_PATH
├── logs/
│   ├── interactive_run.log        (This main log file)
│   └── python_console_output.txt  (Full console output with input prompts)
├── script_output/                 (Python working directory)
│   └── [Output created by Python script]
└── interactive_completion_summary.txt  (This file)

EXECUTION DETAILS
==================================================
Virtual Environment: $VENV_ROOT
Python Executable: $pythonExe
Python Script: $PYTHON_SCRIPT
Start Time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))
End Time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))
Duration: $durationFormatted
Exit Code: $($result.ExitCode)

INPUT PROMPTS CAPTURED
==================================================
All Python input() prompts and user responses are captured in:
$PYTHON_OUTPUT_FILE

This file contains the complete console session, including:
1. All print() statements from Python
2. All input() prompts (e.g., "Enter camera index (default 0): ")
3. All user keyboard input
4. All error messages and tracebacks

SCRIPT OUTPUT LOCATION
==================================================
Any folders/files created by the Python script should be located in:
$RUN_SCRIPT_OUTPUT_PATH

DEBUGGING NOTES
==================================================
1. Check python_console_output.txt for complete console transcript
2. If input prompts were not visible, run with Method 1 (simple interactive)
3. For batch/automated runs, use the non-interactive version instead
==================================================
"@

$completionSummary | Out-File $COMPLETION_FILE

# Update main log
"" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append
"EXECUTION COMPLETE" | Out-File $MAIN_LOG_FILE -Append
"End Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $MAIN_LOG_FILE -Append
"Exit Code: $($result.ExitCode)" | Out-File $MAIN_LOG_FILE -Append
"Duration: $durationFormatted" | Out-File $MAIN_LOG_FILE -Append
"Completion Summary: $COMPLETION_FILE" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append
# ===================================

# ========== FINAL OUTPUT ==========
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "RUN FOLDER CREATED SUCCESSFULLY" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host "All outputs are organized in:" -ForegroundColor Cyan
Write-Host "  $RUN_FOLDER_PATH" -ForegroundColor White
Write-Host ""
Write-Host "Key files:" -ForegroundColor Cyan
Write-Host "  • Main log: $MAIN_LOG_FILE" -ForegroundColor Gray
Write-Host "  • Console output: $PYTHON_OUTPUT_FILE" -ForegroundColor Gray
Write-Host "  • Completion summary: $COMPLETION_FILE" -ForegroundColor Gray
Write-Host ""
Write-Host "To view the complete console output with input prompts:" -ForegroundColor Yellow
Write-Host "  Get-Content `"$PYTHON_OUTPUT_FILE`" | more" -ForegroundColor White
Write-Host ""

# Exit with Python's exit code
exit $result.ExitCode
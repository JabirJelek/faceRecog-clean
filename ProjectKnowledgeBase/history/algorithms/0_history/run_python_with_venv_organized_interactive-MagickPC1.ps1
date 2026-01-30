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
    Write-Host "Created runs base directory: $RUNS_BASE_PATH" -ForegroundColor Green
}

# Generate run folder with timestamp
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
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
    
    Write-Host "Created run folder structure at: $RUN_FOLDER_PATH" -ForegroundColor Green
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
Write-Host "  Python executable: $pythonExe" -ForegroundColor Gray
Write-Host "  Python script: $PYTHON_SCRIPT" -ForegroundColor Gray
# ===================================

# ========== INTERACTIVE EXECUTION SETUP ==========
Write-Host ""
Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "STARTING INTERACTIVE PYTHON SCRIPT" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "NOTE: The Python script will now run interactively." -ForegroundColor Cyan
Write-Host "      You will see all output including input() prompts." -ForegroundColor Cyan
Write-Host "      Console output is being saved to: $PYTHON_OUTPUT_FILE" -ForegroundColor Cyan
Write-Host ""

# Create a header for the console output file
"==================================================" | Out-File $PYTHON_OUTPUT_FILE
"Python Console Output - Interactive Session" | Out-File $PYTHON_OUTPUT_FILE -Append
"Start Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $PYTHON_OUTPUT_FILE -Append
"Command: $pythonExe `"$PYTHON_SCRIPT`"" | Out-File $PYTHON_OUTPUT_FILE -Append
"==================================================" | Out-File $PYTHON_OUTPUT_FILE -Append
"" | Out-File $PYTHON_OUTPUT_FILE -Append

# Log to main log
"Starting interactive Python execution at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $MAIN_LOG_FILE -Append
"Command: $pythonExe `"$PYTHON_SCRIPT`"" | Out-File $MAIN_LOG_FILE -Append
"Output file: $PYTHON_OUTPUT_FILE" | Out-File $MAIN_LOG_FILE -Append
"" | Out-File $MAIN_LOG_FILE -Append

# Save current directory
$originalLocation = Get-Location
$startTime = Get-Date

# ========== SIMPLER ALTERNATIVE: DIRECT EXECUTION ==========
# If the above method is too complex, use this simpler approach

Write-Host ""
Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "ALTERNATIVE: DIRECT INTERACTIVE EXECUTION" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "This will run Python directly in the current console." -ForegroundColor Cyan
Write-Host "All output will be visible. Input prompts will appear normally." -ForegroundColor Cyan
Write-Host ""

$response = Read-Host "Run Python directly? (Y/N, default: Y)"
if ($response -eq "" -or $response -eq "Y" -or $response -eq "y") {
    # Create output header
    "Direct Interactive Execution" | Out-File $PYTHON_OUTPUT_FILE -Append
    "==================================================" | Out-File $PYTHON_OUTPUT_FILE -Append
    
    # Log to main log
    "Starting direct interactive execution at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $MAIN_LOG_FILE -Append
    
    Write-Host ""
    Write-Host "--------------------------------------------------" -ForegroundColor Gray
    Write-Host "Starting Python script..." -ForegroundColor Green
    Write-Host "Python output will appear below:" -ForegroundColor Green
    Write-Host "--------------------------------------------------" -ForegroundColor Gray
    Write-Host ""
    
    # Run Python in the current console
    # All output will be visible, and input() prompts will work
    try {
        # Change to output directory
        Set-Location $RUN_SCRIPT_OUTPUT_PATH
        
        # Create a script block that runs Python and logs output
        $scriptBlock = {
            param($pythonPath, $scriptPath, $logFile)
            
            # Create a real-time output handler
            $outputHandler = {
                param($sender, $eventArgs)
                if ($eventArgs.Data -ne $null) {
                    $line = $eventArgs.Data
                    # Write to console
                    [System.Console]::WriteLine($line)
                    # Write to log file
                    $line | Out-File -FilePath $logFile -Append
                }
            }
            
            # Run Python
            & $pythonPath $scriptPath 2>&1 | ForEach-Object {
                # Display and log each line
                Write-Host $_
                $_ | Out-File -FilePath $logFile -Append
            }
        }
        
        # Run the script block
        & $scriptBlock -pythonPath $pythonExe -scriptPath $PYTHON_SCRIPT -logFile $PYTHON_OUTPUT_FILE
        
        $exitCode = $LASTEXITCODE
        
    } catch {
        Write-Host "Error: $_" -ForegroundColor Red
        "ERROR: $_" | Out-File $PYTHON_OUTPUT_FILE -Append
        $exitCode = 1
    } finally {
        Set-Location $originalLocation
    }
}

# ========== POST-EXECUTION ==========
$endTime = Get-Date
$duration = $endTime - $startTime
$durationFormatted = "{0:D2}:{1:D2}:{2:D2}" -f $duration.Hours, $duration.Minutes, $duration.Seconds

# Create footer in output file
"" | Out-File $PYTHON_OUTPUT_FILE -Append
"==================================================" | Out-File $PYTHON_OUTPUT_FILE -Append
"Execution completed at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $PYTHON_OUTPUT_FILE -Append
"Exit Code: $exitCode" | Out-File $PYTHON_OUTPUT_FILE -Append
"Duration: $durationFormatted" | Out-File $PYTHON_OUTPUT_FILE -Append
"==================================================" | Out-File $PYTHON_OUTPUT_FILE -Append

# Display summary
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "EXECUTION COMPLETE" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""

if ($exitCode -eq 0) {
    Write-Host "✓ Python script executed SUCCESSFULLY" -ForegroundColor Green
} else {
    Write-Host "✗ Python script execution FAILED" -ForegroundColor Red
    Write-Host "  Exit Code: $exitCode" -ForegroundColor Red
}

Write-Host "  Start Time: $($startTime.ToString('HH:mm:ss'))" -ForegroundColor Cyan
Write-Host "  End Time: $($endTime.ToString('HH:mm:ss'))" -ForegroundColor Cyan
Write-Host "  Duration: $durationFormatted" -ForegroundColor Cyan

# Show output file info
if (Test-Path $PYTHON_OUTPUT_FILE) {
    $fileSize = (Get-Item $PYTHON_OUTPUT_FILE).Length
    $lineCount = (Get-Content $PYTHON_OUTPUT_FILE | Measure-Object -Line).Lines
    
    Write-Host ""
    Write-Host "Console output saved to: $PYTHON_OUTPUT_FILE" -ForegroundColor Cyan
    Write-Host "  File size: $fileSize bytes" -ForegroundColor Gray
    Write-Host "  Line count: $lineCount lines" -ForegroundColor Gray
    
    # Show a preview of input prompts if any
    $prompts = Get-Content $PYTHON_OUTPUT_FILE | Select-String -Pattern "Enter|camera|index|input" | Select-Object -First 5
    if ($prompts) {
        Write-Host ""
        Write-Host "Input prompts captured in log:" -ForegroundColor Yellow
        foreach ($prompt in $prompts) {
            Write-Host "  - $($prompt.ToString().Trim())" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "WARNING: No console output file was created" -ForegroundColor Yellow
}

# ========== CREATE COMPLETION SUMMARY ==========
$COMPLETION_FILE = Join-Path $RUN_FOLDER_PATH "interactive_completion_summary.txt"

$completionSummary = @"
==================================================
INTERACTIVE RUN COMPLETION SUMMARY
==================================================
Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run ID: $timestamp
Status: $(if ($exitCode -eq 0) { "SUCCESS" } else { "FAILED (Exit code: $exitCode)" })

FOLDER STRUCTURE
==================================================
Run Folder: $RUN_FOLDER_PATH
├── logs/
│   ├── interactive_run.log        (Main execution log)
│   └── python_console_output.txt  (Complete console output with input prompts)
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
Exit Code: $exitCode

HOW TO VIEW RESULTS
==================================================
1. Console output (including input prompts):
   Get-Content "$PYTHON_OUTPUT_FILE" | more

2. Input prompts in the output:
   Select-String -Path "$PYTHON_OUTPUT_FILE" -Pattern "Enter|input"

3. Files created by Python script:
   Get-ChildItem "$RUN_SCRIPT_OUTPUT_PATH" -Recurse

NOTES
==================================================
• Input() prompts from Python were displayed in the console
• User responses were captured in the console session
• For batch/automated runs without interaction, use the non-interactive script
==================================================
"@

$completionSummary | Out-File $COMPLETION_FILE

# Update main log
"" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append
"EXECUTION COMPLETE" | Out-File $MAIN_LOG_FILE -Append
"End Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $MAIN_LOG_FILE -Append
"Exit Code: $exitCode" | Out-File $MAIN_LOG_FILE -Append
"Duration: $durationFormatted" | Out-File $MAIN_LOG_FILE -Append
"Completion Summary: $COMPLETION_FILE" | Out-File $MAIN_LOG_FILE -Append
"==================================================" | Out-File $MAIN_LOG_FILE -Append

# ========== FINAL OUTPUT ==========
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "RUN FOLDER CREATED" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host "All outputs are organized in:" -ForegroundColor Cyan
Write-Host "  $RUN_FOLDER_PATH" -ForegroundColor White
Write-Host ""
Write-Host "To view the captured console output:" -ForegroundColor Yellow
Write-Host "  Get-Content `"$PYTHON_OUTPUT_FILE`"" -ForegroundColor White
Write-Host ""
Write-Host "To view input prompts captured:" -ForegroundColor Yellow
Write-Host "  Select-String -Path `"$PYTHON_OUTPUT_FILE`" -Pattern `"Enter`"" -ForegroundColor White
Write-Host ""

# Exit with Python's exit code
exit $exitCode
<#
.SYNOPSIS
Creates folder structure and runs Python face recognition script
.DESCRIPTION
Sets up organized folder structure and executes Python algorithm
#>

# Import common paths module
. (Join-Path $PSScriptRoot "common-paths.ps1")

function Initialize-WorkerPaths {
    <#
    .SYNOPSIS
    Initializes paths specifically for the worker script
    #>
    
    Write-Host "=== Mask Detection Worker Script ===" -ForegroundColor Cyan
    Write-Host "Starting portable path initialization..." -ForegroundColor Cyan
    
    # Get base paths from common module
    $paths = Initialize-ProjectPortablePaths -IsWorker
    
    # Extract validated paths
    $VENV_ROOT = $paths.VenvRoot
    $PYTHON_SCRIPT = $paths.PythonScript
    $RUNS_BASE_PATH = $paths.DateBasedPath
    $ProjectRoot = $paths.ProjectRoot
    $ActiveDatePath = $paths.DateBasedPath
    
    return @{
        VENV_ROOT = $VENV_ROOT
        PYTHON_SCRIPT = $PYTHON_SCRIPT
        RUNS_BASE_PATH = $RUNS_BASE_PATH
        ProjectRoot = $ProjectRoot
        ActiveDatePath = $ActiveDatePath
    }
}

function Create-RunFolderStructure {
    <#
    .SYNOPSIS
    Creates organized folder structure for the current run
    #>
    param(
        [string]$BasePath,
        [string]$ProjectRoot,
        [string]$ActiveDatePath
    )
    
    # Generate run folder with timestamp
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $RUN_FOLDER_NAME = "Laptop_Process_MaskDetect_$timestamp"
    $RUN_FOLDER_PATH = Join-Path $BasePath $RUN_FOLDER_NAME
    
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
    
    # Set up log files
    $MAIN_LOG_FILE = Join-Path $RUN_LOGS_PATH "run_$timestamp.log"
    $PYTHON_OUTPUT_FILE = Join-Path $RUN_LOGS_PATH "python_output.txt"
    $COMPLETION_SUMMARY_FILE = Join-Path $RUN_LOGS_PATH "completion_summary.txt"
    
    return @{
        RunFolderPath = $RUN_FOLDER_PATH
        RunFolderName = $RUN_FOLDER_NAME
        LogsPath = $RUN_LOGS_PATH
        ScriptOutputPath = $RUN_SCRIPT_OUTPUT_PATH
        MetadataPath = $RUN_METADATA_PATH
        MainLogFile = $MAIN_LOG_FILE
        PythonOutputFile = $PYTHON_OUTPUT_FILE
        CompletionSummaryFile = $COMPLETION_SUMMARY_FILE
        Timestamp = $timestamp
    }
}

function Write-RunMetadata {
    <#
    .SYNOPSIS
    Creates metadata file with run information
    #>
    param(
        [hashtable]$FolderInfo,
        [hashtable]$Paths,
        [array]$PythonArgs
    )
    
    $metadata = @{
        run_id = $FolderInfo.Timestamp
        start_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        powershell_script = Split-Path -Leaf $MyInvocation.MyCommand.Path
        project_root = $Paths.ProjectRoot
        active_date_path = $Paths.ActiveDatePath
        virtual_env = $Paths.VENV_ROOT
        python_script = $Paths.PYTHON_SCRIPT
        arguments = $PythonArgs
        arguments_count = $PythonArgs.Count
        run_folder = $FolderInfo.RunFolderPath
    }
    
    $metadata | ConvertTo-Json | Out-File $FolderInfo.MetadataPath
    Write-Host "Created metadata file: $($FolderInfo.MetadataPath)"
    
    return $metadata
}

function Execute-PythonScript {
    <#
    .SYNOPSIS
    Executes the Python script with proper environment setup
    #>
    param(
        [hashtable]$Paths,
        [hashtable]$FolderInfo,
        [array]$PythonArgs
    )
    
    $pythonExe = Join-Path $Paths.VENV_ROOT "Scripts\python.exe"
    
    if (-not (Test-Path $pythonExe)) {
        $errorMsg = "ERROR: Python executable not found at $pythonExe"
        Write-Error $errorMsg
        exit 1
    }
    
    # Capture start time
    $startTime = Get-Date
    
    try {
        # Set working directory to script_output
        $originalLocation = Get-Location
        Set-Location $FolderInfo.ScriptOutputPath
        
        # Run Python with array of arguments
        & $pythonExe $Paths.PYTHON_SCRIPT $PythonArgs 2>&1 | Tee-Object -FilePath $FolderInfo.PythonOutputFile
        
        $exitCode = $LASTEXITCODE
        
        # Return to original location
        Set-Location $originalLocation
        
    } catch {
        $errorMessage = $_.Exception.Message
        Write-Error "Exception during Python script execution: $errorMessage"
        $exitCode = 1
    }
    
    return @{
        ExitCode = $exitCode
        StartTime = $startTime
        EndTime = Get-Date
    }
}

function Write-CompletionSummary {
    <#
    .SYNOPSIS
    Creates completion summary file
    #>
    param(
        [hashtable]$FolderInfo,
        [hashtable]$Paths,
        [hashtable]$ExecutionResult,
        [array]$PythonArgs
    )
    
    $duration = $ExecutionResult.EndTime - $ExecutionResult.StartTime
    $durationFormatted = "{0:D2}:{1:D2}:{2:D2}" -f $duration.Hours, $duration.Minutes, $duration.Seconds
    
    $completionSummary = @"
==================================================
RUN COMPLETION SUMMARY
==================================================
Completion Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run ID: $($FolderInfo.Timestamp)
Project Root: $($Paths.ProjectRoot)
Active Date Path: $($Paths.ActiveDatePath)
Status: $(if ($ExecutionResult.ExitCode -eq 0) { "SUCCESS" } else { "FAILED (Exit code: $($ExecutionResult.ExitCode))" })

FOLDER STRUCTURE
==================================================
Run Folder: $($FolderInfo.RunFolderPath)
├── logs\
│   ├── run_$($FolderInfo.Timestamp).log
│   ├── python_output.txt
│   └── completion_summary.txt
├── script_output\
└── metadata.json

EXECUTION DETAILS
==================================================
Virtual Environment: $($Paths.VENV_ROOT)
Python Script: $($Paths.PYTHON_SCRIPT)
Start Time: $($ExecutionResult.StartTime.ToString('yyyy-MM-dd HH:mm:ss'))
End Time: $($ExecutionResult.EndTime.ToString('yyyy-MM-dd HH:mm:ss'))
Duration: $durationFormatted
"@

    $completionSummary | Out-File $FolderInfo.CompletionSummaryFile
    
    # Update metadata with completion info
    $completionMetadata = Get-Content $FolderInfo.MetadataPath | ConvertFrom-Json
    $completionMetadata | Add-Member -NotePropertyName "end_time" -NotePropertyValue (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Force
    $completionMetadata | Add-Member -NotePropertyName "duration" -NotePropertyValue $durationFormatted -Force
    $completionMetadata | Add-Member -NotePropertyName "exit_code" -NotePropertyValue $ExecutionResult.ExitCode -Force
    $completionMetadata | Add-Member -NotePropertyName "python_pid" -NotePropertyValue $PID -Force
    $completionMetadata | ConvertTo-Json | Out-File $FolderInfo.MetadataPath
    
    return @{
        ExitCode = $ExecutionResult.ExitCode
        Duration = $durationFormatted
    }
}

# ====================================================================
# MAIN EXECUTION
# ====================================================================

# Initialize paths for worker
$paths = Initialize-WorkerPaths

# Python arguments (worker-specific)
$PYTHON_ARGS = @(
    # Add your Python arguments here
    # "--database", "path\to\database"
    # "--input", "path\to\input"
    # "--multi-source"
    "-i", "12",
    "-o", "number_13"
)

# Create run folder structure
$folderInfo = Create-RunFolderStructure -BasePath $paths.RUNS_BASE_PATH -ProjectRoot $paths.ProjectRoot -ActiveDatePath $paths.ActiveDatePath

# Write initial log header
$logHeader = @"
==================================================
RUN STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Run Folder: $($folderInfo.RunFolderPath)
Project Root: $($paths.ProjectRoot)
Active Date Path: $($paths.ActiveDatePath)
Virtual Environment: $($paths.VENV_ROOT)
Python Script: $($paths.PYTHON_SCRIPT)
Arguments: $($PYTHON_ARGS -join ' ')
==================================================
"@

$logHeader | Out-File $folderInfo.MainLogFile -Append

# Write metadata
$metadata = Write-RunMetadata -FolderInfo $folderInfo -Paths $paths -PythonArgs $PYTHON_ARGS

# Execute Python script
Write-Host "Starting Python script execution..."
Write-Host "Run folder: $($folderInfo.RunFolderPath)"
Write-Host "Arguments: $($PYTHON_ARGS -join ' ')"

$executionResult = Execute-PythonScript -Paths $paths -FolderInfo $folderInfo -PythonArgs $PYTHON_ARGS

# Create completion summary
$completion = Write-CompletionSummary -FolderInfo $folderInfo -Paths $paths -ExecutionResult $executionResult -PythonArgs $PYTHON_ARGS

# Final output
Write-Host ""
Write-Host "=================================================="
Write-Host "RUN COMPLETED"
Write-Host "=================================================="
Write-Host "Run Folder: $($folderInfo.RunFolderPath)"
Write-Host "Main Log: $($folderInfo.MainLogFile)"
Write-Host "Python Output: $($folderInfo.PythonOutputFile)"
Write-Host "Completion Summary: $($folderInfo.CompletionSummaryFile)"
Write-Host "Metadata: $($folderInfo.MetadataPath)"
Write-Host ""
Write-Host "Exit code: $($completion.ExitCode)"
Write-Host "Duration: $($completion.Duration)"
Write-Host "=================================================="

# Exit with Python's exit code
exit $completion.ExitCode
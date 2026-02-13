# 1_worker-portable.ps1
<#
.SYNOPSIS
Worker script for face recognition pipeline
.DESCRIPTION
Basic worker script that just runs Python
#>

try {
    Write-Host "=== WORKER SCRIPT STARTING ===" -ForegroundColor Cyan
    Write-Host "Worker PID: $PID" -ForegroundColor Yellow
    
    $commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
    if (-not (Test-Path $commonPathsScript)) {
        throw "Common paths script not found: $commonPathsScript"
    }
    
    . $commonPathsScript
    Write-Host "Common paths script loaded" -ForegroundColor Green
    
    $appConfig = Get-ApplicationConfig
    
    $paths = Initialize-ProjectPortablePaths -IsWorker -Silent
    if (-not $paths) {
        throw "Failed to initialize paths"
    }
    
    $PYTHON_EXE = $paths.PythonExe
    $PYTHON_SCRIPT = $paths.PythonScript
    $RUNS_BASE_PATH = $paths.DateBasedPath
    
    $RUN_FOLDER_PREFIX          = $appConfig.WorkerRunFolderPrefix
    $LOG_SUBFOLDER_NAME        = $appConfig.WorkerLogSubfolder
    $OUTPUT_SUBFOLDER_NAME     = $appConfig.WorkerOutputSubfolder
    $METADATA_FILENAME         = $appConfig.WorkerMetadataFile
    $PYTHON_OUTPUT_FILENAME_PREFIX = $appConfig.WorkerPythonOutputPrefix
    $COMPLETION_SUMMARY_FILENAME = $appConfig.WorkerCompletionSummary
    $PYTHON_ARGUMENT           = $appConfig.WorkerPythonArgument
    
    Write-Host "Python executable: $PYTHON_EXE" -ForegroundColor Green
    Write-Host "Python script: $PYTHON_SCRIPT" -ForegroundColor Green
    
    if (-not (Test-Path $PYTHON_EXE)) {
        throw "Python executable not found: $PYTHON_EXE"
    }
    
    if (-not (Test-Path $PYTHON_SCRIPT)) {
        throw "Python script not found: $PYTHON_SCRIPT"
    }
    
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $runFolder = Join-Path $RUNS_BASE_PATH "$RUN_FOLDER_PREFIX$timestamp"
    Write-Host "Creating run folder: $runFolder" -ForegroundColor Yellow
    
    New-Item -ItemType Directory -Path $runFolder -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $runFolder $LOG_SUBFOLDER_NAME) -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $runFolder $OUTPUT_SUBFOLDER_NAME) -Force | Out-Null
    
    $metadata = @{
        run_id = $timestamp
        start_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        worker_pid = $PID
        python_script = $PYTHON_SCRIPT
        python_exe = $PYTHON_EXE
        run_folder = $runFolder
    }
    
    $metadata | ConvertTo-Json | Out-File (Join-Path $runFolder $METADATA_FILENAME)
    
    Write-Host "Starting Python script..." -ForegroundColor Cyan
    
    $pythonOutputFile = Join-Path $runFolder "$LOG_SUBFOLDER_NAME\${PYTHON_OUTPUT_FILENAME_PREFIX}${timestamp}.txt"
    $workingDir = Join-Path $runFolder $OUTPUT_SUBFOLDER_NAME
    
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $PYTHON_EXE
    $processInfo.Arguments = "`"$PYTHON_SCRIPT`" $PYTHON_ARGUMENT"
    $processInfo.UseShellExecute = $false
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.CreateNoWindow = $true
    $processInfo.WorkingDirectory = $workingDir
    
    $pythonProcess = New-Object System.Diagnostics.Process
    $pythonProcess.StartInfo = $processInfo
    
    if ($pythonProcess.Start()) {
        $pythonPID = $pythonProcess.Id
        Write-Host "Python process started (PID: $pythonPID)" -ForegroundColor Green
        
        $metadata.python_pid = $pythonPID
        $metadata | ConvertTo-Json | Out-File (Join-Path $runFolder $METADATA_FILENAME) -Force
        
        Write-Host "Waiting for Python to complete..." -ForegroundColor Yellow
        
        $output = $pythonProcess.StandardOutput.ReadToEnd()
        $errorOutput = $pythonProcess.StandardError.ReadToEnd()
        $pythonProcess.WaitForExit()
        
        $exitCode = $pythonProcess.ExitCode
        
        $output | Out-File $pythonOutputFile -Force
        if ($errorOutput) {
            $errorOutput | Out-File $pythonOutputFile -Append
        }
        
        Write-Host "Python completed with exit code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
        
        # --- Add end_time to metadata and update the file ---
        $metadata.end_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $metadata | ConvertTo-Json | Out-File (Join-Path $runFolder $METADATA_FILENAME) -Force
        
        # --- Enhanced summary with explicit end time and duration ---
        $start = [datetime]::ParseExact($metadata.start_time, "yyyy-MM-dd HH:mm:ss", $null)
        $end   = [datetime]::ParseExact($metadata.end_time,   "yyyy-MM-dd HH:mm:ss", $null)
        $duration = $end - $start
        $durationStr = "{0:hh\:mm\:ss}" -f $duration   # format as HH:MM:SS
        
        $summary = @"
Run started:  $($metadata.start_time)
Run ended:    $($metadata.end_time)
Duration:     $durationStr
Exit code:    $exitCode
Run folder:   $runFolder
Worker PID:   $PID
Python PID:   $pythonPID
"@
        
        $summary | Out-File (Join-Path $runFolder "$LOG_SUBFOLDER_NAME\$COMPLETION_SUMMARY_FILENAME")
        
        Write-Host "=== WORKER SCRIPT COMPLETED ===" -ForegroundColor Green
        exit $exitCode
    } else {
        throw "Failed to start Python process"
    }
    
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
}
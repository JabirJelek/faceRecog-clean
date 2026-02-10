# 1_mask_portable.ps1
<#
.SYNOPSIS
Worker script for face recognition pipeline
.DESCRIPTION
Basic worker script that just runs Python
#>

try {
    Write-Host "=== WORKER SCRIPT STARTING ===" -ForegroundColor Cyan
    Write-Host "Worker PID: $PID" -ForegroundColor Yellow
    
    # Load common paths
    $commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
    if (-not (Test-Path $commonPathsScript)) {
        throw "Common paths script not found: $commonPathsScript"
    }
    
    . $commonPathsScript
    Write-Host "Common paths script loaded" -ForegroundColor Green
    
    # Initialize paths
    $paths = Initialize-ProjectPortablePaths -IsWorker -Silent
    if (-not $paths) {
        throw "Failed to initialize paths"
    }
    
    $PYTHON_EXE = $paths.PythonExe
    $PYTHON_SCRIPT = $paths.PythonScript
    $RUNS_BASE_PATH = $paths.DateBasedPath
    
    Write-Host "Python executable: $PYTHON_EXE" -ForegroundColor Green
    Write-Host "Python script: $PYTHON_SCRIPT" -ForegroundColor Green
    
    # Validate paths
    if (-not (Test-Path $PYTHON_EXE)) {
        throw "Python executable not found: $PYTHON_EXE"
    }
    
    if (-not (Test-Path $PYTHON_SCRIPT)) {
        throw "Python script not found: $PYTHON_SCRIPT"
    }
    
    # Create run folder
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $runFolder = Join-Path $RUNS_BASE_PATH "Magick_Process_MaskDetect_$timestamp"
    Write-Host "Creating run folder: $runFolder" -ForegroundColor Yellow
    
    New-Item -ItemType Directory -Path $runFolder -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $runFolder "logs") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $runFolder "script_output") -Force | Out-Null
    
    # Create metadata
    $metadata = @{
        run_id = $timestamp
        start_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        worker_pid = $PID
        python_script = $PYTHON_SCRIPT
        python_exe = $PYTHON_EXE
        run_folder = $runFolder
    }
    
    $metadata | ConvertTo-Json | Out-File (Join-Path $runFolder "metadata.json")
    
    # Run Python
    Write-Host "Starting Python script..." -ForegroundColor Cyan
    
    $pythonOutputFile = Join-Path $runFolder "logs\python_output_$timestamp.txt"
    $workingDir = Join-Path $runFolder "script_output"
    
    # Start Python process
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $PYTHON_EXE
    $processInfo.Arguments = "`"$PYTHON_SCRIPT`" --multi-source"
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
        
        # Update metadata
        $metadata.python_pid = $pythonPID
        $metadata | ConvertTo-Json | Out-File (Join-Path $runFolder "metadata.json") -Force
        
        # Wait for completion
        Write-Host "Waiting for Python to complete..." -ForegroundColor Yellow
        
        $output = $pythonProcess.StandardOutput.ReadToEnd()
        $errorOutput = $pythonProcess.StandardError.ReadToEnd()
        $pythonProcess.WaitForExit()
        
        $exitCode = $pythonProcess.ExitCode
        
        # Write output
        $output | Out-File $pythonOutputFile -Force
        if ($errorOutput) {
            $errorOutput | Out-File $pythonOutputFile -Append
        }
        
        Write-Host "Python completed with exit code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
        
        # Create summary
        $summary = @"
Run completed: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Exit code: $exitCode
Run folder: $runFolder
Worker PID: $PID
Python PID: $pythonPID
"@
        
        $summary | Out-File (Join-Path $runFolder "logs\completion_summary.txt")
        
        Write-Host "=== WORKER SCRIPT COMPLETED ===" -ForegroundColor Green
        exit $exitCode
    } else {
        throw "Failed to start Python process"
    }
    
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
}
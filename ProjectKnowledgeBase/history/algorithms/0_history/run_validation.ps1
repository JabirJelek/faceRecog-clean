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

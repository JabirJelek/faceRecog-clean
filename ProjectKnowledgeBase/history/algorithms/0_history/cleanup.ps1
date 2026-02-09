# cleanup.ps1
<#
.SYNOPSIS
Cleans up orphaned processes and stale files
.DESCRIPTION
Stops all face recognition processes and cleans up temporary files
#>

Write-Host "=== System Cleanup ===" -ForegroundColor Cyan

# Stop all related processes
$processesStopped = 0

# Stop Python processes
Write-Host "Stopping Python processes..." -ForegroundColor Yellow
$pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue
foreach ($proc in $pythonProcesses) {
    try {
        $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
        if ($cmdLine -like "*Magick*") {
            $proc.Kill()
            $processesStopped++
            Write-Host "  Stopped Python (PID: $($proc.Id))" -ForegroundColor Green
        }
    } catch { }
}

# Stop PowerShell processes (except current)
Write-Host "Stopping worker/monitor processes..." -ForegroundColor Yellow
$psProcesses = Get-Process -Name "powershell*" -ErrorAction SilentlyContinue
foreach ($proc in $psProcesses) {
    if ($proc.Id -ne $PID) {
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
            if ($cmdLine -like "*mask_portable*" -or $cmdLine -like "*monitor*" -or $cmdLine -like "*Magick*") {
                $proc.Kill()
                $processesStopped++
                Write-Host "  Stopped PowerShell (PID: $($proc.Id))" -ForegroundColor Green
            }
        } catch { }
    }
}

Write-Host "`nTotal processes stopped: $processesStopped" -ForegroundColor Cyan

# Clean up old PID files
Write-Host "`nCleaning up stale files..." -ForegroundColor Yellow

$daysToKeep = 7
$cutoffDate = (Get-Date).AddDays(-$daysToKeep)

# Clean up old log directories
$logBase = "logs-running\magick"
if (Test-Path $logBase) {
    $logDirs = Get-ChildItem -Path $logBase -Directory
    foreach ($dir in $logDirs) {
        if ($dir.CreationTime -lt $cutoffDate) {
            try {
                Remove-Item -Path $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  Removed old log directory: $($dir.Name)" -ForegroundColor Green
            } catch { }
        }
    }
}

# Clean up PID files
$today = Get-Date -Format "yyyy-MM-dd"
$todayDir = Join-Path $logBase $today
if (Test-Path $todayDir) {
    $pidFiles = Get-ChildItem -Path $todayDir -Filter "*pid*.json" -Recurse -ErrorAction SilentlyContinue
    foreach ($file in $pidFiles) {
        try {
            Remove-Item -Path $file.FullName -Force -ErrorAction SilentlyContinue
            Write-Host "  Removed PID file: $($file.Name)" -ForegroundColor Green
        } catch { }
    }
}

Write-Host "`n=== Cleanup Complete ===" -ForegroundColor Green
Write-Host "System is now clean and ready for restart." -ForegroundColor Cyan

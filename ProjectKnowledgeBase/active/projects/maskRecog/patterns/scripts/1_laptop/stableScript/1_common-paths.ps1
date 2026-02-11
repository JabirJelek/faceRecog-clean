# 1_common-paths.ps1

<#
.SYNOPSIS
Common path initialization module shared by monitor and worker scripts
.DESCRIPTION
Handles portable path discovery and date-based folder creation
#>

# ====================================================================
# Module Configuration - MODIFIABLE SECTION
# ====================================================================
$Script:CommonConfig = @{
    ProjectName = "maskRecog"
    LogBasePath = "logs-running\laptop"
    DateFormat = "yyyy-MM-dd"
    DateTimeFormat = "yyyy-MM-dd_HH-mm-ss"
    LogDateTimeFormat = "yyyy-MM-dd HH:mm:ss"
    
    # ====================== EXTRACTED FILE PATHS ======================
    # File paths for monitor script
    MonitorFilePaths = @{
        WorkerScript = "patterns\scripts\1_laptop\1_mask_portable.ps1"
        PythonScriptPath = "patterns\algorithm\entry_multi-USED-Laptop.py"
        PIDFileName = "monitor_pid_Laptop.json"
        LogFileName = "monitor_Laptop.log"
    }
    
    # File paths for worker script
    WorkerFilePaths = @{
        PythonScript = "patterns\algorithm\entry_multi-USED-Laptop.py"
    }
    
    # Common file paths
    CommonFilePaths = @{
        PythonExe = ".venv\Scripts\python.exe"
        CommunicationDirName = "communication"
        WorkerPIDFileName = "worker_pid.txt"
        WorkerStatusFileName = "worker_status.json"
    }
}

# ====================================================================
# Initialize Project Paths
# ====================================================================
function Initialize-ProjectPortablePaths {
    [CmdletBinding()]
    param(
        [switch]$IsMonitor,
        [switch]$IsWorker,
        [switch]$Silent = $false
    )
    
    if (-not $Silent) {
        Write-Host "Initializing portable paths for $($Script:CommonConfig.ProjectName) project..." -ForegroundColor Cyan
    }
    
    # Find the project root
    $projectRoot = Find-ProjectRoot -Silent:$Silent
    if (-not $projectRoot) {
        throw "Project root directory '$($Script:CommonConfig.ProjectName)' not found"
    }
    
    # Build paths relative to project root
    $paths = Build-ProjectPaths -ProjectRoot $projectRoot
    
    # Create date-based folder structure
    $dateBasedPath = Initialize-DateBasedStructure -Paths $paths
    
    # Add script-specific paths
    $paths = Add-ScriptSpecificPaths -Paths $paths -DateBasedPath $dateBasedPath -IsMonitor:$IsMonitor -IsWorker:$IsWorker
    
    return $paths
}

# ====================================================================
# Helper Functions
# ====================================================================

function Find-ProjectRoot {
    [CmdletBinding()]
    param([switch]$Silent)
    
    $scriptPath = $PSScriptRoot
    $currentPath = $scriptPath
    
    # Look for maskRecog directory by going up
    while ($currentPath -and (Split-Path $currentPath -Parent)) {
        $currentDirName = Split-Path $currentPath -Leaf
        if ($currentDirName -eq $Script:CommonConfig.ProjectName) {
            if (-not $Silent) {
                Write-Host "Found project root: $currentPath" -ForegroundColor Green
            }
            return $currentPath
        }
        $currentPath = Split-Path $currentPath -Parent
    }
    
    # Check current directory
    $currentDir = Get-Location
    if ((Split-Path $currentDir -Leaf) -eq $Script:CommonConfig.ProjectName) {
        return $currentDir
    }
    
    return $null
}

function Build-ProjectPaths {
    [CmdletBinding()]
    param([string]$ProjectRoot)
    
    # Calculate paths
    $ActiveRoot = Split-Path $ProjectRoot -Parent | Split-Path -Parent
    $VenvRoot = Split-Path $ProjectRoot -Parent | Split-Path -Parent | Split-Path -Parent | Split-Path -Parent
    $currentDate = Get-Date -Format $Script:CommonConfig.DateFormat
    
    return @{
        ProjectRoot = $ProjectRoot
        ActiveRoot = $ActiveRoot
        VenvRoot = $VenvRoot
        CurrentDate = $currentDate
    }
}

function Initialize-DateBasedStructure {
    [CmdletBinding()]
    param([hashtable]$Paths)
    
    # Create base folder
    $laptopBasePath = Join-Path $Paths.ActiveRoot $Script:CommonConfig.LogBasePath
    if (-not (Test-Path $laptopBasePath)) {
        New-Item -ItemType Directory -Path $laptopBasePath -Force | Out-Null
    }
    
    # Create date-specific folder
    $dateBasedPath = Join-Path $laptopBasePath $Paths.CurrentDate
    if (-not (Test-Path $dateBasedPath)) {
        New-Item -ItemType Directory -Path $dateBasedPath -Force | Out-Null
    }
    
    return $dateBasedPath
}

function Add-ScriptSpecificPaths {
    [CmdletBinding()]
    param(
        [hashtable]$Paths,
        [string]$DateBasedPath,
        [switch]$IsMonitor,
        [switch]$IsWorker
    )
    
    $Paths.DateBasedPath = $DateBasedPath
    
    if ($IsMonitor) {
        $Paths.WorkerScript = Join-Path $Paths.ProjectRoot $Script:CommonConfig.MonitorFilePaths.WorkerScript
        $Paths.PythonScriptPath = Join-Path $Paths.ProjectRoot $Script:CommonConfig.MonitorFilePaths.PythonScriptPath
        $Paths.PIDFilePath = Join-Path $DateBasedPath $Script:CommonConfig.MonitorFilePaths.PIDFileName
        $Paths.LogFile = Join-Path $DateBasedPath $Script:CommonConfig.MonitorFilePaths.LogFileName
        $Paths.PythonExe = Join-Path $Paths.VenvRoot $Script:CommonConfig.CommonFilePaths.PythonExe
    }
    
    if ($IsWorker) {
        $Paths.PythonScript = Join-Path $Paths.ProjectRoot $Script:CommonConfig.WorkerFilePaths.PythonScript
        $Paths.PythonExe = Join-Path $Paths.VenvRoot $Script:CommonConfig.CommonFilePaths.PythonExe
    }
    
    return $Paths
}

# ====================================================================
# MISSING FUNCTION IMPLEMENTATIONS
# ====================================================================

function Check-Heartbeat {
    [CmdletBinding()]
    param([string]$HeartbeatFile)
    
    if (-not (Test-Path $HeartbeatFile)) {
        return $false
    }
    
    try {
        $heartbeatTime = (Get-Item $HeartbeatFile).LastWriteTime
        $ageMinutes = ((Get-Date) - $heartbeatTime).TotalMinutes
        
        # Heartbeat is considered alive if updated within last 2 minutes
        return $ageMinutes -le 2
    } catch {
        return $false
    }
}

function Send-Heartbeat {
    [CmdletBinding()]
    param([string]$HeartbeatFile)
    
    try {
        $heartbeatDir = Split-Path $HeartbeatFile -Parent
        if (-not (Test-Path $heartbeatDir)) {
            New-Item -ItemType Directory -Path $heartbeatDir -Force | Out-Null
        }
        
        Set-Content -Path $HeartbeatFile -Value (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Force
        return $true
    } catch {
        return $false
    }
}

function Acquire-Lock {
    [CmdletBinding()]
    param(
        [string]$LockFile,
        [int]$TimeoutSeconds = 30
    )
    
    $startTime = Get-Date
    $lockAcquired = $false
    
    while (((Get-Date) - $startTime).TotalSeconds -lt $TimeoutSeconds) {
        try {
            if (Test-Path $LockFile) {
                $lockTime = [DateTime]::Parse((Get-Content $LockFile -First 1))
                $lockAge = ((Get-Date) - $lockTime).TotalSeconds
                
                # If lock is older than 30 seconds, consider it stale
                if ($lockAge -gt 30) {
                    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
                }
            }
            
            # Try to create lock file
            $lockDir = Split-Path $LockFile -Parent
            if (-not (Test-Path $lockDir)) {
                New-Item -ItemType Directory -Path $lockDir -Force | Out-Null
            }
            
            $tempFile = "$LockFile.tmp"
            (Get-Date).ToString("yyyy-MM-dd HH:mm:ss") | Out-File $tempFile -Force
            Move-Item $tempFile $LockFile -Force -ErrorAction Stop
            
            $lockAcquired = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    
    return $lockAcquired
}

function Release-Lock {
    [CmdletBinding()]
    param([string]$LockFile)
    
    if (Test-Path $LockFile) {
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
    return $true
}

function Write-Log {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$Message,
        [string]$Level = "INFO",
        [string]$LogFile,
        [switch]$NoConsole
    )
    
    $currentTimestamp = Get-Date -Format $Script:CommonConfig.LogDateTimeFormat
    $logEntry = "[$currentTimestamp] [$Level] $Message"
    
    if ($LogFile -and (-not [string]::IsNullOrEmpty($LogFile))) {
        try {
            $logDir = Split-Path $LogFile -Parent
            if (-not (Test-Path $logDir)) {
                New-Item -ItemType Directory -Path $logDir -Force | Out-Null
            }
            Add-Content -Path $LogFile -Value $logEntry -ErrorAction Stop
        } catch {
            if (-not $NoConsole) {
                Write-Host "Log file write failed: $_" -ForegroundColor Yellow
            }
        }
    }
    
    if (-not $NoConsole) {
        $color = switch ($Level) {
            "ERROR"   { "Red" }
            "WARN"    { "Yellow" }
            "SUCCESS" { "Green" }
            "DEBUG"   { "Gray" }
            default   { "White" }
        }
        Write-Host $logEntry -ForegroundColor $color
    }
    
    return $logEntry
}

# ====================================================================
# Communication Functions (Basic)
# ====================================================================

function Initialize-CommunicationPaths {
    [CmdletBinding()]
    param(
        [hashtable]$Paths,
        [switch]$IsMonitor,
        [switch]$IsWorker
    )
    
    if (-not $Paths -or -not $Paths.DateBasedPath) {
        return $null
    }
    
    $communicationPaths = @{}
    
    try {
        $commDir = Join-Path $Paths.DateBasedPath $Script:CommonConfig.CommonFilePaths.CommunicationDirName
        if (-not (Test-Path $commDir)) {
            New-Item -ItemType Directory -Path $commDir -Force -ErrorAction Stop | Out-Null
        }
        
        $communicationPaths.CommunicationDir = $commDir
        $communicationPaths.StatusFile = Join-Path $commDir $Script:CommonConfig.CommonFilePaths.WorkerStatusFileName
        
        if ($IsWorker) {
            $communicationPaths.PIDFile = Join-Path $commDir $Script:CommonConfig.CommonFilePaths.WorkerPIDFileName
        }
        
        return $communicationPaths
    } catch {
        return $null
    }
}

function Write-WorkerStatus {
    [CmdletBinding()]
    param(
        [string]$StatusFile,
        [string]$Status,
        [int]$WorkerPID,
        [int]$PythonPID = 0,
        [string]$Message = ""
    )
    
    $statusData = @{
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Status = $Status
        WorkerPID = $WorkerPID
        PythonPID = $PythonPID
        Message = $Message
    }
    
    try {
        $statusData | ConvertTo-Json | Out-File $StatusFile -Force
        return $true
    } catch {
        return $false
    }
}

function Read-WorkerStatus {
    [CmdletBinding()]
    param([string]$StatusFile)
    
    if (-not (Test-Path $StatusFile)) {
        return @{ Status = "NOT_FOUND"; WorkerPID = 0; PythonPID = 0 }
    }
    
    try {
        $content = Get-Content $StatusFile -Raw
        return $content | ConvertFrom-Json -AsHashtable
    } catch {
        return @{ Status = "ERROR"; Error = $_; WorkerPID = 0; PythonPID = 0 }
    }
}
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
    LogBasePath = "logs-running\towerCPU"
    DateFormat = "yyyy-MM-dd"
    DateTimeFormat = "yyyy-MM-dd_HH-mm-ss"
    LogDateTimeFormat = "yyyy-MM-dd HH:mm:ss"
    
    # File paths for monitor script
    MonitorFilePaths = @{
        WorkerScript = "patterns\scripts\1_towerCPU\stableScript\1_worker_portable.ps1"
        PythonScriptPath = "patterns\algorithm\entry_multi-USED-TowerCPU.py"
        PIDFileName = "monitor_pid_TowerCPU.json"
        LogFileName = "monitor_TowerCPU.log"
        EmailSendScript = "patterns\scripts\1_towerCPU\stableScript\1_email-sender-stable.ps1"
    }
    
    # File paths for worker script
    WorkerFilePaths = @{
        PythonScript = "patterns\algorithm\entry_multi-USED-TowerCPU.py"
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
# NEW: Centralised Application Configuration
# ====================================================================
$Script:ApplicationConfig = @{
    # ---------------------- Monitor Settings ----------------------
    EveryStartTime       = "08:40"
    EveryEndTime         = "11:12"
    MonitorProcessCheckInterval = 5
    MonitorMaxPIDFileAgeMinutes = 120
    MonitorPIDTrackingFile = "pid_tracking.json"
    MonitorLogPattern      = "monitor_TowerCPU_{0}.log"
    
    # ---------------------- Worker Settings ----------------------
    WorkerRunFolderPrefix  = "TowerCPU_Process_MaskDetect_"
    WorkerLogSubfolder     = "logs"
    WorkerOutputSubfolder  = "script_output"
    WorkerMetadataFile     = "metadata.json"
    WorkerPythonOutputPrefix = "python_output_"
    WorkerCompletionSummary = "completion_summary.txt"
    WorkerPythonArgument   = "--multi-source"
    
    # ---------------------- Email Sender Settings ----------------
    EmailCredentialPath    = "$env:USERPROFILE\.face-recog\email-credential.xml"
    EmailRunFolderFilter   = "TowerCPU_Process_MaskDetect_*"
    EmailCompletionSummaryFile = "completion_summary.txt"
    EmailMetadataFile      = "metadata.json"
    EmailLogsFolder        = "logs"
    EmailLogFileFilter     = "*.txt"
    EmailCommonPathsScript = "1_common-paths.ps1"
    EmailMaxRunsToCollect  = 10
    EmailDefaultHoursBack  = 24
    EmailMaxAttachmentSizeMB = 3
    EmailSmtpServer        = "smtp.gmail.com"
    EmailSmtpPort          = 587
    EmailUseSsl            = $true
    EmailSubjectPrefix     = "[FaceRecog]"
    EmailSenderScript      = "1_email-sender-stable.ps1"
    
    # ---------------------- Capture Script Settings --------------
    # CaptureStartTime       = "10:00"
    # CaptureEndTime         = "11:04"
    CaptureRunsDirectory   = "runs"
    CaptureLogsDirectory   = "logs"
    CaptureOutputFolderPattern = "TowerCPU_Process_MaskDetect_*"
    CaptureLogFilePattern  = "capture_collected_runs_{0}.log"
    CaptureDateFormat      = "yyyy-MM-dd"
    CaptureDateTimeFormat  = "yyyy-MM-dd HH:mm"
    CaptureFileTimestampFormat = "yyyyMMdd_HHmmss"
    
    # ---------------------- Shared Validation Settings -----------
    ExpectedSubfolders     = @("logs", "script_output")
    ExpectedFiles          = @("metadata.json")
    MaxValidationRetries   = 5
    RetryDelaySeconds      = 10
}

function Get-ApplicationConfig {
    return $Script:ApplicationConfig
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
    $towerCPUBasePath = Join-Path $Paths.ActiveRoot $Script:CommonConfig.LogBasePath
    if (-not (Test-Path $towerCPUBasePath)) {
        New-Item -ItemType Directory -Path $towerCPUBasePath -Force | Out-Null
    }
    
    # Create date-specific folder
    $dateBasedPath = Join-Path $towerCPUBasePath $Paths.CurrentDate
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
        $paths.EmailSendScript = Join-Path $Paths.ProjectRoot $Script:CommonConfig.MonitorFilePaths.EmailSendScript
    }
    
    if ($IsWorker) {
        $Paths.PythonScript = Join-Path $Paths.ProjectRoot $Script:CommonConfig.WorkerFilePaths.PythonScript
        $Paths.PythonExe = Join-Path $Paths.VenvRoot $Script:CommonConfig.CommonFilePaths.PythonExe
    }
    
    return $Paths
}


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

function Write-CommonLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Message,
        [string]$Level = "INFO",
        [string]$LogFile,
        [switch]$NoConsole
    )
    $timestamp = Get-Date -Format $Script:CommonConfig.LogDateTimeFormat
    $entry = "[$timestamp] [$Level] $Message"
    if ($LogFile) {
        $dir = Split-Path $LogFile -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Add-Content -Path $LogFile -Value $entry -ErrorAction SilentlyContinue
    }
    if (-not $NoConsole) {
        $color = @{ ERROR='Red'; WARN='Yellow'; SUCCESS='Green'; DEBUG='Gray'; SHUTDOWN='Blue' }[$Level]
        # Replace null-coalescing operator for PowerShell 5 compatibility
        $foregroundColor = if ($null -ne $color) { $color } else { 'White' }
        Write-Host $entry -ForegroundColor $foregroundColor
    }
}

# ====================================================================
# SHARED VALIDATION & COLLECTION – NEW / MOVED HERE
# ====================================================================
function Test-RunFolder {
    [CmdletBinding()]
    param(
        [string]$FolderPath,
        [switch]$Detailed
    )
    $cfg = Get-ApplicationConfig
    $result = @{
        Success = $false
        FolderPath = $FolderPath
        FolderName = Split-Path $FolderPath -Leaf
        CreationTime = $null
        MissingItems = @()
        Errors = @()
        Warnings = @()
        Details = @{}
    }
    try {
        $folder = Get-Item -Path $FolderPath -ErrorAction Stop
        $result.CreationTime = $folder.CreationTime
        foreach ($sub in $cfg.ExpectedSubfolders) {
            if (-not (Test-Path (Join-Path $FolderPath $sub))) {
                $result.MissingItems += $sub
                $result.Warnings += "Missing subfolder: $sub"
            }
        }
        foreach ($file in $cfg.ExpectedFiles) {
            if (-not (Test-Path (Join-Path $FolderPath $file))) {
                $result.MissingItems += $file
                $result.Warnings += "Missing file: $file"
            }
        }
        $result.Success = ($result.MissingItems.Count -eq 0) -and ($result.Errors.Count -eq 0)
    } catch {
        $result.Errors += "Error validating folder: $_"
    }
    return $result
}

function Get-RunFoldersInWindow {
    [CmdletBinding()]
    param(
        [string]$BasePath,
        [DateTime]$WindowStart,
        [DateTime]$WindowEnd,
        [string]$FolderFilter = (Get-ApplicationConfig).WorkerRunFolderPrefix
    )
    if (-not (Test-Path $BasePath)) { return @() }
    $folders = Get-ChildItem -Path $BasePath -Directory -Filter "$FolderFilter*" -ErrorAction SilentlyContinue |
               Where-Object { $_.CreationTime -ge $WindowStart -and $_.CreationTime -le $WindowEnd }
    return $folders
}

function Get-LatestRunFolder {
    [CmdletBinding()]
    param(
        [string]$BasePath,
        [string]$FolderFilter = (Get-ApplicationConfig).WorkerRunFolderPrefix
    )
    if (-not (Test-Path $BasePath)) { return $null }
    return Get-ChildItem -Path $BasePath -Directory -Filter "$FolderFilter*" -ErrorAction SilentlyContinue |
           Sort-Object CreationTime -Descending | Select-Object -First 1
}

function Collect-RunsFromTimeWindow {
    [CmdletBinding()]
    param(
        [string]$BasePath,
        [DateTime]$WindowStart,
        [DateTime]$WindowEnd,
        [switch]$ValidateEach
    )
    $runs = Get-RunFoldersInWindow -BasePath $BasePath -WindowStart $WindowStart -WindowEnd $WindowEnd
    $collected = @()
    foreach ($run in $runs) {
        $validation = if ($ValidateEach) { Test-RunFolder -FolderPath $run.FullName } else { $null }
        $collected += @{
            Folder       = $run.FullName
            Name         = $run.Name
            CreationTime = $run.CreationTime
            Validation   = $validation
            Status       = if ($validation -and $validation.Success) { "VALID" } elseif ($validation) { "INVALID" } else { "COLLECTED" }
        }
    }
    return $collected
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
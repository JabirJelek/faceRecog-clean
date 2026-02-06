<#
.SYNOPSIS
Common path initialization module shared by monitor and folder creation scripts
.DESCRIPTION
Handles portable path discovery and date-based folder creation
#>

function Initialize-ProjectPortablePaths {
    [CmdletBinding()]
    param(
        [switch]$IsMonitor,
        [switch]$IsWorker
    )
    
    Write-Host "Initializing portable paths for maskRecog project..." -ForegroundColor Cyan
    
    # ====================================================================
    # STEP 1: FIND THE PROJECT ROOT (maskRecog directory)
    # ====================================================================
    
    # Method A: Check if we're already IN maskRecog directory
    $scriptPath = $PSScriptRoot  # Where this script is located
    $currentPath = $scriptPath
    
    # Look for maskRecog by going UP through parent directories
    while ($currentPath -and (Split-Path $currentPath -Parent)) {
        $currentDirName = Split-Path $currentPath -Leaf
        
        if ($currentDirName -eq "maskRecog") {
            $projectRoot = $currentPath
            break
        }
        
        $parentPath = Split-Path $currentPath -Parent
        # Stop if we reach drive root (like D:\) or can't go further
        if (!$parentPath -or $parentPath -eq $currentPath) {
            break
        }
        $currentPath = $parentPath
    }
    
    # Method B: If not found above, check current directory name
    if (!$projectRoot) {
        $currentDir = Get-Location
        if ((Split-Path $currentDir -Leaf) -eq "maskRecog") {
            $projectRoot = $currentDir
        }
    }
    
    # Method C: Last resort - ask user
    if (!$projectRoot) {
        Write-Host "Could not automatically find 'maskRecog' directory." -ForegroundColor Yellow
        $projectRoot = Read-Host "Please enter the full path to 'maskRecog' project root"
        
        if (!(Test-Path $projectRoot)) {
            Write-Host "ERROR: Path '$projectRoot' does not exist!" -ForegroundColor Red
            exit 1
        }
    }
    
    # ====================================================================
    # STEP 2: BUILD PATHS RELATIVE TO PROJECT ROOT
    # ====================================================================
    
    $global:ProjectRoot = $projectRoot
    $global:ActiveRoot = Split-Path $projectRoot -Parent | Split-Path -Parent
    $global:VenvRoot = Split-Path $projectRoot -Parent | Split-Path -Parent | Split-Path -Parent | Split-Path -Parent
    
    # ====================================================================
    # STEP 3: CREATE DATE-BASED FOLDER STRUCTURE
    # ====================================================================
    
    $currentDate = Get-Date -Format "yyyy-MM-dd"
    $global:CurrentDateFolder = $currentDate
    
    # Create the base Laptop folder if it doesn't exist
    $laptopBasePath = Join-Path $ActiveRoot "logs-running\laptop"
    if (-not (Test-Path $laptopBasePath)) {
        New-Item -ItemType Directory -Path $laptopBasePath -Force | Out-Null
        Write-Host "Created base Laptop folder: $laptopBasePath" -ForegroundColor Yellow
    }
    
    # Create date-specific folder
    $dateBasedPath = Join-Path $laptopBasePath $currentDate
    if (-not (Test-Path $dateBasedPath)) {
        New-Item -ItemType Directory -Path $dateBasedPath -Force | Out-Null
        Write-Host "Created date-based folder: $dateBasedPath" -ForegroundColor Yellow
    } else {
        Write-Host "Using existing date-based folder: $dateBasedPath" -ForegroundColor Green
    }
    
    # Store the active date path globally
    $global:ActiveDatePath = $dateBasedPath
    
    # ====================================================================
    # STEP 4: RETURN PATHS BASED ON SCRIPT TYPE
    # ====================================================================
    
    $paths = @{
        ProjectRoot = $projectRoot
        ActiveRoot = $ActiveRoot
        VenvRoot = $VenvRoot
        DateBasedPath = $dateBasedPath
        CurrentDate = $currentDate
    }
    
    # Monitor-specific paths
    if ($IsMonitor) {
        $paths.WorkerScript = Join-Path $projectRoot "patterns\scripts\1_laptop\1_mask_portable.ps1"
        $paths.PythonScriptPath = Join-Path $projectRoot "patterns\algorithm\entry_multi_USED-Laptop.py"
        $paths.PIDFilePath = Join-Path $dateBasedPath "monitor_pid_Laptop.json"
        $paths.LogFile = Join-Path $dateBasedPath "monitor_Laptop.log"
    }
    
    # Worker-specific paths
    if ($IsWorker) {
        $paths.PythonScript = Join-Path $projectRoot "patterns\algorithm\py-test.py"
        $paths.PythonExe = Join-Path $VenvRoot "Scripts\python.exe"
    }
    
    return $paths
}

function Get-DateBasedPath {
    <#
    .SYNOPSIS
    Gets or creates a date-based folder path for the current day
    #>
    param(
        [string]$BasePath = (Join-Path $ActiveRoot "logs-running\laptop"),
        [DateTime]$Date = (Get-Date)
    )
    
    $dateString = $Date.ToString("yyyy-MM-dd")
    $datePath = Join-Path $BasePath $dateString
    
    # Create the directory if it doesn't exist
    if (-not (Test-Path $datePath)) {
        try {
            New-Item -ItemType Directory -Path $datePath -Force | Out-Null
            Write-Log "Created date-based folder: $datePath" -Level "INFO"
        } catch {
            Write-Log "Failed to create date-based folder: $_" -Level "ERROR"
            throw
        }
    }
    
    return $datePath
}
# 1_common-paths.ps1
<#
.SYNOPSIS
Common path initialization module shared by monitor and worker scripts
.DESCRIPTION
Handles portable path discovery and date-based folder creation with enhanced integration
.NOTES
Updated to support both monitor and worker script requirements - STABILIZED VERSION
#>

# ====================================================================
# ENHANCED: Module Configuration - REMOVED Export-ModuleMember
# ====================================================================
$Script:CommonConfig = @{
    ProjectName = "maskRecog"
    LogBasePath = "logs-running\magick"
    DateFormat = "yyyy-MM-dd"
    DateTimeFormat = "yyyy-MM-dd_HH-mm-ss"
    LogDateTimeFormat = "yyyy-MM-dd HH:mm:ss"
}

# ====================================================================
# ENHANCED: Initialize Project Paths with improved validation
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
    
    # ====================================================================
    # STEP 1: FIND THE PROJECT ROOT (maskRecog directory)
    # ====================================================================
    
    $projectRoot = Find-ProjectRoot -Silent:$Silent
    
    if (-not $projectRoot) {
        if (-not $Silent) {
            Write-Host "ERROR: Could not find project root directory '$($Script:CommonConfig.ProjectName)'" -ForegroundColor Red
        }
        throw "Project root directory '$($Script:CommonConfig.ProjectName)' not found"
    }
    
    # ====================================================================
    # STEP 2: BUILD PATHS RELATIVE TO PROJECT ROOT
    # ====================================================================
    
    $paths = Build-ProjectPaths -ProjectRoot $projectRoot
    
    # ====================================================================
    # STEP 3: CREATE DATE-BASED FOLDER STRUCTURE
    # ====================================================================
    
    $dateBasedPath = Initialize-DateBasedStructure -Paths $paths
    
    # ====================================================================
    # STEP 4: ADD SCRIPT-SPECIFIC PATHS
    # ====================================================================
    
    $paths = Add-ScriptSpecificPaths -Paths $paths -DateBasedPath $dateBasedPath -IsMonitor:$IsMonitor -IsWorker:$IsWorker
    
    # ====================================================================
    # STEP 5: VALIDATE CRITICAL PATHS
    # ====================================================================
    
    if (-not $Silent) {
        Validate-CriticalPaths -Paths $paths -IsMonitor:$IsMonitor -IsWorker:$IsWorker
    }
    
    return $paths
}

# ====================================================================
# ENHANCED: Helper Functions - STABILIZED
# ====================================================================

function Find-ProjectRoot {
    [CmdletBinding()]
    param([switch]$Silent)
    
    # Method A: Check if we're already IN maskRecog directory
    $scriptPath = $PSScriptRoot
    $currentPath = $scriptPath
    
    # Look for maskRecog by going UP through parent directories
    while ($currentPath -and (Split-Path $currentPath -Parent)) {
        $currentDirName = Split-Path $currentPath -Leaf
        
        if ($currentDirName -eq $Script:CommonConfig.ProjectName) {
            if (-not $Silent) {
                Write-Host "Found project root in current path: $currentPath" -ForegroundColor Green
            }
            return $currentPath
        }
        
        $parentPath = Split-Path $currentPath -Parent
        # Stop if we reach drive root (like D:\) or can't go further
        if (!$parentPath -or $parentPath -eq $currentPath) {
            break
        }
        $currentPath = $parentPath
    }
    
    # Method B: If not found above, check current directory name
    $currentDir = Get-Location
    if ((Split-Path $currentDir -Leaf) -eq $Script:CommonConfig.ProjectName) {
        if (-not $Silent) {
            Write-Host "Found project root in current directory: $currentDir" -ForegroundColor Green
        }
        return $currentDir
    }
    
    # Method C: Last resort - ask user
    if (-not $Silent) {
        Write-Host "Could not automatically find '$($Script:CommonConfig.ProjectName)' directory." -ForegroundColor Yellow
        $projectRoot = Read-Host "Please enter the full path to '$($Script:CommonConfig.ProjectName)' project root"
        
        if (!(Test-Path $projectRoot)) {
            Write-Host "ERROR: Path '$projectRoot' does not exist!" -ForegroundColor Red
            return $null
        }
        
        if ((Split-Path $projectRoot -Leaf) -ne $Script:CommonConfig.ProjectName) {
            Write-Host "WARNING: Directory name does not match '$($Script:CommonConfig.ProjectName)'" -ForegroundColor Yellow
        }
        
        return $projectRoot
    }
    
    return $null
}

function Build-ProjectPaths {
    [CmdletBinding()]
    param([string]$ProjectRoot)
    
    # Store project root globally so all functions can use it
    $global:ProjectRoot = $ProjectRoot
    
    # Calculate ActiveRoot (two levels up from ProjectRoot)
    $global:ActiveRoot = Split-Path $ProjectRoot -Parent | Split-Path -Parent
    
    # Calculate VenvRoot (four levels up from ProjectRoot)
    $global:VenvRoot = Split-Path $ProjectRoot -Parent | Split-Path -Parent | Split-Path -Parent | Split-Path -Parent 
    
    # Get current date for folder structure
    $currentDate = Get-Date -Format $Script:CommonConfig.DateFormat
    $global:CurrentDateFolder = $currentDate
    
    return @{
        ProjectRoot = $ProjectRoot
        ActiveRoot = $global:ActiveRoot
        VenvRoot = $global:VenvRoot
        CurrentDate = $currentDate
    }
}

function Initialize-DateBasedStructure {
    [CmdletBinding()]
    param([hashtable]$Paths)
    
    # Create the base Magick folder if it doesn't exist
    $magickBasePath = Join-Path $Paths.ActiveRoot $Script:CommonConfig.LogBasePath
    if (-not (Test-Path $magickBasePath)) {
        try {
            New-Item -ItemType Directory -Path $magickBasePath -Force | Out-Null
            Write-Host "Created base Magick folder: $magickBasePath" -ForegroundColor Yellow
        } catch {
            Write-Host "ERROR: Failed to create base Magick folder: $_" -ForegroundColor Red
            throw
        }
    }
    
    # Create date-specific folder
    $dateBasedPath = Join-Path $magickBasePath $Paths.CurrentDate
    if (-not (Test-Path $dateBasedPath)) {
        try {
            New-Item -ItemType Directory -Path $dateBasedPath -Force | Out-Null
            Write-Host "Created date-based folder: $dateBasedPath" -ForegroundColor Yellow
        } catch {
            Write-Host "ERROR: Failed to create date-based folder: $_" -ForegroundColor Red
            throw
        }
    } else {
        Write-Host "Using existing date-based folder: $dateBasedPath" -ForegroundColor Green
    }
    
    # Store the active date path globally
    $global:ActiveDatePath = $dateBasedPath
    
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
    
    # Add date-based path to common paths
    $Paths.DateBasedPath = $DateBasedPath
    $Paths.ActiveDatePath = $DateBasedPath
    
    # Monitor-specific paths
    if ($IsMonitor) {
        $Paths.WorkerScript = Join-Path $Paths.ProjectRoot "patterns\scripts\1_magick\1_mask_portable.ps1"
        $Paths.PythonScriptPath = Join-Path $Paths.ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
        $Paths.PIDFilePath = Join-Path $DateBasedPath "monitor_pid_Magick.json"
        $Paths.LogFile = Join-Path $DateBasedPath "monitor_Magick.log"
        $Paths.OutputFolderPattern = "Magick_Process_MaskDetect_*"
        
        # Enhanced: Additional monitor paths
        $Paths.SuddenTerminationTrackingFile = Join-Path $DateBasedPath "sudden_termination_tracking.json"
        $Paths.PersistentTrackingFile = Join-Path $DateBasedPath "persistent_tracking.json"
        $Paths.PythonExe = Join-Path $Paths.VenvRoot ".venv\Scripts\python.exe"        
    }
    
    # Worker-specific paths
    if ($IsWorker) {
        $Paths.PythonScript = Join-Path $Paths.ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
        $Paths.PythonExe = Join-Path $Paths.VenvRoot ".venv\Scripts\python.exe"
        
        # Enhanced: Additional worker paths
        $Paths.WorkerLogPattern = "worker_*.log"
        $Paths.RunFolderPattern = "Magick_Process_MaskDetect_*"
    }
    
    return $Paths
}

function Validate-CriticalPaths {
    [CmdletBinding()]
    param(
        [hashtable]$Paths,
        [switch]$IsMonitor,
        [switch]$IsWorker
    )
    
    $criticalPaths = @()
    $missingPaths = @()
    $warnings = @()
    
    # Common critical paths
    $criticalPaths += @{ Name = "Project Root"; Path = $Paths.ProjectRoot }
    $criticalPaths += @{ Name = "Active Root"; Path = $Paths.ActiveRoot }
    $criticalPaths += @{ Name = "Date-Based Path"; Path = $Paths.DateBasedPath }
    
    # Monitor-specific critical paths
    if ($IsMonitor) {
        $criticalPaths += @{ Name = "Worker Script"; Path = $Paths.WorkerScript }
        $criticalPaths += @{ Name = "Python Script (Monitor)"; Path = $Paths.PythonScriptPath }
        $criticalPaths += @{ Name = "PID File Path"; Path = $Paths.PIDFilePath }
        $criticalPaths += @{ Name = "Log File"; Path = $Paths.LogFile }
        $criticalPaths += @{ Name = "Venv path"; Path = $Paths.VenvRoot }       
        $criticalPaths += @{ Name = "Python from venv"; Path = $Paths.PythonExe }                
    }
    
    # Worker-specific critical paths
    if ($IsWorker) {
        $criticalPaths += @{ Name = "Python Script (Worker)"; Path = $Paths.PythonScript }
        $criticalPaths += @{ Name = "Python Executable"; Path = $Paths.PythonExe }
    }
    
    Write-Host "`nValidating critical paths..." -ForegroundColor Yellow
    
    foreach ($item in $criticalPaths) {
        if (Test-Path $item.Path) {
            Write-Host "  [✓] $($item.Name): $($item.Path)" -ForegroundColor Green
        } else {
            # Check if it's a file that might be created later
            if ($item.Name -match "File") {
                $parentDir = Split-Path $item.Path -Parent
                if (Test-Path $parentDir) {
                    Write-Host "  [?] $($item.Name): $($item.Path) (Directory exists, file will be created)" -ForegroundColor Yellow
                    $warnings += $item.Name
                } else {
                    Write-Host "  [✗] $($item.Name): $($item.Path)" -ForegroundColor Red
                    $missingPaths += $item.Name
                }
            } else {
                Write-Host "  [✗] $($item.Name): $($item.Path)" -ForegroundColor Red
                $missingPaths += $item.Name
            }
        }
    }
    
    # Summary
    if ($missingPaths.Count -gt 0) {
        Write-Host "`nERROR: Missing critical paths!" -ForegroundColor Red
        foreach ($missing in $missingPaths) {
            Write-Host "  - $missing" -ForegroundColor Red
        }
        
        if ($IsWorker) {
            Write-Host "`nTroubleshooting for Worker:" -ForegroundColor Yellow
            Write-Host "1. Check virtual environment exists at: $($Paths.VenvRoot)" -ForegroundColor Yellow
            Write-Host "2. Verify Python script location: $($Paths.PythonScript)" -ForegroundColor Yellow
        }
        
        if ($IsMonitor) {
            Write-Host "`nTroubleshooting for Monitor:" -ForegroundColor Yellow
            Write-Host "1. Verify worker script location: $($Paths.WorkerScript)" -ForegroundColor Yellow
            Write-Host "2. Check Python script location: $($Paths.PythonScriptPath)" -ForegroundColor Yellow
        }
    }
    
    if ($warnings.Count -gt 0) {
        Write-Host "`nWarnings: $($warnings.Count) path(s) will be created during execution" -ForegroundColor Yellow
    }
    
    if ($missingPaths.Count -eq 0) {
        Write-Host "`nAll critical paths validated successfully!" -ForegroundColor Green
    }
}

# ====================================================================
# ENHANCED: Get-DateBasedPath with improved functionality
# ====================================================================

function Get-DateBasedPath {
    <#
    .SYNOPSIS
    Gets or creates a date-based folder path for the current or specified day
    .DESCRIPTION
    Enhanced version with better error handling and date flexibility
    #>
    [CmdletBinding()]
    param(
        [string]$BasePath = (Join-Path $global:ActiveRoot $Script:CommonConfig.LogBasePath),
        [DateTime]$Date = (Get-Date),
        [switch]$CreateIfNotExist = $true
    )
    
    try {
        $dateString = $Date.ToString($Script:CommonConfig.DateFormat)
        $datePath = Join-Path $BasePath $dateString
        
        # Create the directory if it doesn't exist and flag is set
        if (-not (Test-Path $datePath) -and $CreateIfNotExist) {
            try {
                # Ensure base directory exists
                if (-not (Test-Path $BasePath)) {
                    New-Item -ItemType Directory -Path $BasePath -Force | Out-Null
                    Write-Host "Created base directory: $BasePath" -ForegroundColor Yellow
                }
                
                New-Item -ItemType Directory -Path $datePath -Force | Out-Null
                Write-Host "Created date-based folder: $datePath" -ForegroundColor Yellow
            } catch {
                Write-Host "ERROR: Failed to create date-based folder: $_" -ForegroundColor Red
                throw
            }
        } elseif (Test-Path $datePath) {
            Write-Host "Using existing date-based folder: $datePath" -ForegroundColor Green
        } elseif (-not $CreateIfNotExist) {
            Write-Host "Date-based folder does not exist: $datePath" -ForegroundColor Yellow
        }
        
        return $datePath
    } catch {
        Write-Host "ERROR in Get-DateBasedPath: $_" -ForegroundColor Red
        throw
    }
}

# ====================================================================
# ENHANCED: Logging function with flexible output - STABILIZED
# ====================================================================

function Write-Log {
    <#
    .SYNOPSIS
    Enhanced logging function for common module with multiple output options
    .DESCRIPTION
    Supports console output, file logging, and different log levels
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$Message,
        
        [ValidateSet("INFO", "DEBUG", "WARN", "ERROR", "SUCCESS")]
        [string]$Level = "INFO",
        
        [string]$LogFile,
        
        [switch]$NoConsole
    )
    
    $currentTimestamp = Get-Date -Format $Script:CommonConfig.LogDateTimeFormat
    $logEntry = "[$currentTimestamp] [$Level] $Message"
    
    # Write to log file if specified
    if ($LogFile -and (-not [string]::IsNullOrEmpty($LogFile))) {
        try {
            # Ensure directory exists
            $logDir = Split-Path $LogFile -Parent
            if (-not (Test-Path $logDir)) {
                New-Item -ItemType Directory -Path $logDir -Force | Out-Null
            }
            
            Add-Content -Path $LogFile -Value $logEntry -ErrorAction Stop
        } catch {
            # Fallback to console if file write fails
            if (-not $NoConsole) {
                Write-Host "Log file write failed: $_" -ForegroundColor Yellow
            }
        }
    }
    
    # Color-coded console output (unless suppressed)
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
# ENHANCED: Utility Functions - REMOVED Export-ModuleMember dependencies
# ====================================================================

function Get-RunFolderPattern {
    <#
    .SYNOPSIS
    Returns the pattern for run folders based on current configuration
    #>
    param([string]$Pattern = "Magick_Process_MaskDetect_*")
    return $Pattern
}

function Get-WorkerScriptPath {
    <#
    .SYNOPSIS
    Returns the path to the worker script
    #>
    param([string]$ProjectRoot = $global:ProjectRoot)
    
    if (-not $ProjectRoot) {
        Write-Host "ERROR: ProjectRoot not initialized" -ForegroundColor Red
        return $null
    }
    
    $workerScript = Join-Path $ProjectRoot "patterns\scripts\1_magick\1_mask_portable.ps1"
    
    if (Test-Path $workerScript) {
        return $workerScript
    } else {
        Write-Host "WARNING: Worker script not found at: $workerScript" -ForegroundColor Yellow
        return $null
    }
}

function Get-PythonPaths {
    <#
    .SYNOPSIS
    Returns Python-related paths (script and executable)
    #>
    param(
        [string]$ProjectRoot = $global:ProjectRoot,
        [string]$VenvRoot = $global:VenvRoot
    )
    
    if (-not $ProjectRoot -or -not $VenvRoot) {
        Write-Host "ERROR: ProjectRoot or VenvRoot not initialized" -ForegroundColor Red
        return $null
    }
    
    $pythonScript = Join-Path $ProjectRoot "patterns\algorithm\entry_multi-USED-Magick.py"
    $pythonExe = Join-Path $VenvRoot ".venv\Scripts\python.exe"
    
    return @{
        PythonScript = $pythonScript
        PythonExe = $pythonExe
    }
}

function Test-ProjectStructure {
    <#
    .SYNOPSIS
    Tests if the project structure is valid
    #>
    [CmdletBinding()]
    param()
    
    try {
        $paths = Initialize-ProjectPortablePaths -Silent
        
        if (-not $paths) {
            return $false
        }
        
        # Test critical paths
        $criticalTests = @(
            @{ Path = $paths.ProjectRoot; Type = "Directory" }
            @{ Path = $paths.ActiveRoot; Type = "Directory" }
            @{ Path = $paths.DateBasedPath; Type = "Directory" }
        )
        
        foreach ($test in $criticalTests) {
            if ($test.Type -eq "Directory") {
                if (-not (Test-Path $test.Path -PathType Container)) {
                    Write-Host "Missing directory: $($test.Path)" -ForegroundColor Red
                    return $false
                }
            }
        }
        
        return $true
    } catch {
        Write-Host "Project structure test failed: $_" -ForegroundColor Red
        return $false
    }
}

# ====================================================================
# STABILIZATION: Global Variable Initialization
# ====================================================================

# Initialize global variables to prevent null reference errors
if (-not $global:ProjectRoot) { $global:ProjectRoot = $null }
if (-not $global:ActiveRoot) { $global:ActiveRoot = $null }
if (-not $global:VenvRoot) { $global:VenvRoot = $null }
if (-not $global:ActiveDatePath) { $global:ActiveDatePath = $null }
if (-not $global:CurrentDateFolder) { $global:CurrentDateFolder = $null }

# ====================================================================
# STABILIZATION: Main Execution Block for Testing
# ====================================================================

<#
This script is designed to be dot-sourced by other scripts.
When run directly, it will test the initialization functions.
#>

if ($MyInvocation.InvocationName -ne '.') {
    Write-Host "=== Common Paths Module Test ===" -ForegroundColor Cyan
    Write-Host "This script is designed to be dot-sourced by other scripts." -ForegroundColor Yellow
    Write-Host "Example usage in monitor script:" -ForegroundColor White
    Write-Host "  . `"$PSScriptRoot\1_common-paths.ps1`"" -ForegroundColor White
    Write-Host "  `$paths = Initialize-ProjectPortablePaths -IsMonitor" -ForegroundColor White
    Write-Host ""
    Write-Host "Example usage in worker script:" -ForegroundColor White
    Write-Host "  . `"$PSScriptRoot\1_common-paths.ps1`"" -ForegroundColor White
    Write-Host "  `$paths = Initialize-ProjectPortablePaths -IsWorker" -ForegroundColor White
    Write-Host ""
    
    # Test the functions
    try {
        Write-Host "Testing project structure..." -ForegroundColor Cyan
        $testResult = Test-ProjectStructure
        if ($testResult) {
            Write-Host "✓ Project structure test passed" -ForegroundColor Green
        } else {
            Write-Host "✗ Project structure test failed" -ForegroundColor Red
        }
    } catch {
        Write-Host "Error during test: $_" -ForegroundColor Red
    }
}
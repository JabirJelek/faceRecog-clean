# compress-folders.ps1
# Advanced multi-folder compression with progress monitoring


# Here is how to utilize this script for backup purposes

# # Single folder with default settings
# pwsh -ExecutionPolicy Bypass -File "compress-folders.ps1" -SourcePaths "C:\raihan\dokumen\project\global-env\faceRecog\process-run\Run_Process_laptop2026-01-22_15-33-4"

# # Specify output location
# pwsh -ExecutionPolicy Bypass -File "compress-folders.ps1" -SourcePaths "C:\raihan\dokumen\project\global-env\faceRecog\process-run\Run_Process_laptop2026-01-22_15-33-4" -OutputPath "C:\raihan\dokumen\project\global-env\faceRecog\backup.7z"

# # Maximum compression
# pwsh -ExecutionPolicy Bypass -File "compress-folders.ps1" -SourcePaths "C:\raihan\dokumen\project\global-env\faceRecog\process-run\Run_Process_laptop2026-01-22_15-33-4" -CompressionLevel 9 -UseMaximumCompression

# # With verification
# pwsh -ExecutionPolicy Bypass -File "compress-folders.ps1" -SourcePaths "C:\raihan\dokumen\project\global-env\faceRecog\process-run\Run_Process_laptop2026-01-22_15-33-4" -VerifyArchive



param(
    [Parameter(Mandatory=$true, Position=0)]
    [string[]]$SourcePaths,
    
    [Parameter(Position=1)]
    [string]$OutputPath = "$PSScriptRoot\archive_$(Get-Date -Format 'yyyyMMdd_HHmmss').7z",
    
    [ValidateRange(1, 22)]
    [int]$CompressionLevel = 7,
    
    [switch]$UseZstd,
    [switch]$UseMaximumCompression,
    [switch]$VerifyArchive,
    [int]$Threads = 0,
    
    [switch]$IncludeSubfolders = $true,
    [switch]$ShowDetailedProgress
)

# Configuration
$ErrorActionPreference = 'Stop'
$host.UI.RawUI.ForegroundColor = "White"

# Display header
Write-Host "=== Advanced Folder Compressor ===" -ForegroundColor Yellow
Write-Host "Optimized for Large Data Sets" -ForegroundColor Green
Write-Host ""

# Function to check and install required tools
function Test-7ZipInstalled {
    $paths = @(
        "${env:ProgramFiles}\7-Zip\7z.exe",
        "${env:ProgramFiles(x86)}\7-Zip\7z.exe",
        "$env:ProgramData\chocolatey\bin\7z.exe"
    )
    
    foreach ($path in $paths) {
        if (Test-Path $path) {
            $script:7zipPath = $path
            return $true
        }
    }
    return $false
}

function Install-7Zip {
    Write-Host "7-Zip not found. Installing..." -ForegroundColor Yellow
    
    # Try winget first
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install 7zip.7zip -e --accept-package-agreements --accept-source-agreements
        if (Test-7ZipInstalled) {
            Write-Host "7-Zip installed successfully via winget." -ForegroundColor Green
            return
        }
    }
    
    # Try chocolatey
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install 7zip -y
        if (Test-7ZipInstalled) {
            Write-Host "7-Zip installed successfully via Chocolatey." -ForegroundColor Green
            return
        }
    }
    
    # Manual download
    Write-Host "Please install 7-Zip manually from: https://www.7-zip.org/" -ForegroundColor Red
    Write-Host "Or run: winget install 7zip.7zip" -ForegroundColor Yellow
    exit 1
}

# Function to calculate folder size
function Get-FolderSize {
    param(
        [string]$Path,
        [switch]$Recursive
    )
    
    if (-not (Test-Path $Path)) {
        return [PSCustomObject]@{
            TotalBytes = 0
            TotalFiles = 0
            TotalFolders = 0
        }
    }
    
    $item = Get-Item $Path
    
    if ($item.PSIsContainer) {
        Write-Host "  Scanning: $([System.IO.Path]::GetFileName($Path))..." -ForegroundColor Gray -NoNewline
        
        # Get all files recursively
        if ($Recursive) {
            $files = Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue
        } else {
            $files = Get-ChildItem -Path $Path -File -ErrorAction SilentlyContinue
        }
        
        $totalSize = ($files | Measure-Object -Property Length -Sum).Sum
        $totalFiles = $files.Count
        
        # Get folder count
        if ($Recursive) {
            $folders = Get-ChildItem -Path $Path -Recurse -Directory -ErrorAction SilentlyContinue
            $totalFolders = $folders.Count + 1  # Include the root folder
        } else {
            $totalFolders = 1
        }
        
        Write-Host " Done" -ForegroundColor Green
        
        return [PSCustomObject]@{
            TotalBytes = if ($totalSize) { $totalSize } else { 0 }
            TotalFiles = $totalFiles
            TotalFolders = $totalFolders
        }
    } else {
        # It's a file
        return [PSCustomObject]@{
            TotalBytes = $item.Length
            TotalFiles = 1
            TotalFolders = 0
        }
    }
}

# Main compression function
function Compress-With7Zip {
    param(
        [string[]]$Paths,
        [string]$OutputFile,
        [int]$Level,
        [int]$ThreadCount,
        [switch]$MaximumCompression
    )
    
    # Ensure output directory exists
    $outputDir = Split-Path $OutputFile -Parent
    if (-not (Test-Path $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }
    
    # Build 7-Zip arguments
    $7zArgs = @(
        "a",                    # Add to archive
        "`"$OutputFile`"",      # Output file
        "`"$($Paths -join '" "')`"",  # Source paths
        "-t7z",                 # Archive type
        "-mx=$Level",           # Compression level
        "-bsp1"                 # Show progress percents
    )
    
    # Add threading if specified
    if ($ThreadCount -eq 0) {
        $7zArgs += "-mmt=on"
    } elseif ($ThreadCount -gt 1) {
        $7zArgs += "-mmt=$ThreadCount"
    }
    
    # Add maximum compression settings if requested
    if ($MaximumCompression) {
        $7zArgs += "-m0=LZMA2:d27m:fb128:mc10000"
        $7zArgs += "-mfb=273"
        $7zArgs += "-md=1536m"
    }
    
    # Add recursive flag for subfolders
    if ($IncludeSubfolders) {
        $7zArgs += "-r"
    }
    
    Write-Host "Starting compression with 7-Zip..." -ForegroundColor Yellow
    Write-Host "Command: $7zipPath $($7zArgs -join ' ')" -ForegroundColor Gray
    
    # Execute 7-Zip
    $process = Start-Process -FilePath $7zipPath -ArgumentList $7zArgs -NoNewWindow -Wait -PassThru
    
    return $process.ExitCode
}

# Main execution
try {
    # Check for 7-Zip
    if (-not (Test-7ZipInstalled)) {
        Install-7Zip
    }
    
    # Validate source paths
    Write-Host "Validating source paths..." -ForegroundColor Cyan
    $validPaths = @()
    
    foreach ($path in $SourcePaths) {
        if (Test-Path $path) {
            $resolvedPath = Resolve-Path $path
            $validPaths += $resolvedPath.Path
            Write-Host "  ✓ Found: $([System.IO.Path]::GetFileName($path))" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Not found: $path" -ForegroundColor Red
        }
    }
    
    if ($validPaths.Count -eq 0) {
        Write-Host "No valid paths found. Exiting." -ForegroundColor Red
        exit 1
    }
    
    # Calculate total size
    Write-Host "`nCalculating total size..." -ForegroundColor Cyan
    $totalSize = 0
    $totalFiles = 0
    $totalFolders = 0
    
    foreach ($path in $validPaths) {
        $sizeInfo = Get-FolderSize -Path $path -Recursive:$IncludeSubfolders
        $totalSize += $sizeInfo.TotalBytes
        $totalFiles += $sizeInfo.TotalFiles
        $totalFolders += $sizeInfo.TotalFolders
    }
    
    # Format size for display
    $sizeGB = [math]::Round($totalSize / 1GB, 2)
    $sizeMB = [math]::Round($totalSize / 1MB, 2)
    
    if ($totalSize -gt 1GB) {
        $sizeDisplay = "$sizeGB GB"
    } else {
        $sizeDisplay = "$sizeMB MB"
    }
    
    # Display summary
    Write-Host "`n=== Compression Summary ===" -ForegroundColor Yellow
    Write-Host "Source Paths: $($validPaths.Count)" -ForegroundColor White
    Write-Host "Total Files: $totalFiles" -ForegroundColor White
    Write-Host "Total Folders: $totalFolders" -ForegroundColor White
    Write-Host "Total Data Size: $sizeDisplay" -ForegroundColor White
    Write-Host "Output File: $OutputPath" -ForegroundColor White
    Write-Host "Compression Level: $CompressionLevel" -ForegroundColor White
    
    if ($UseMaximumCompression) {
        Write-Host "Maximum Compression: Enabled" -ForegroundColor Cyan
    }
    
    Write-Host ""
    
    # Ask for confirmation
    $confirmation = Read-Host "Proceed with compression? (Y/N)"
    if ($confirmation -notin @('Y', 'y')) {
        Write-Host "Compression cancelled." -ForegroundColor Yellow
        exit 0
    }
    
    Write-Host "Starting compression..." -ForegroundColor Green
    $startTime = Get-Date
    
    # Perform compression
    $exitCode = Compress-With7Zip -Paths $validPaths -OutputFile $OutputPath `
        -Level $CompressionLevel -ThreadCount $Threads -MaximumCompression:$UseMaximumCompression
    
    $endTime = Get-Date
    $duration = $endTime - $startTime
    
    # Check result
    if ($exitCode -eq 0 -and (Test-Path $OutputPath)) {
        # Get compressed size
        $compressedSize = (Get-Item $OutputPath).Length
        $compressedGB = [math]::Round($compressedSize / 1GB, 2)
        $compressedMB = [math]::Round($compressedSize / 1MB, 2)
        
        if ($compressedSize -gt 1GB) {
            $compressedDisplay = "$compressedGB GB"
        } else {
            $compressedDisplay = "$compressedMB MB"
        }
        
        # Calculate savings
        if ($totalSize -gt 0) {
            $savings = [math]::Round((1 - $compressedSize / $totalSize) * 100, 2)
        } else {
            $savings = 0
        }
        
        # Format duration
        $durationStr = "{0:hh\:mm\:ss}" -f $duration
        
        # Display results
        Write-Host "`n=== Compression Complete ===" -ForegroundColor Green
        Write-Host "Original Size: $sizeDisplay" -ForegroundColor White
        Write-Host "Compressed Size: $compressedDisplay" -ForegroundColor White
        Write-Host "Space Saved: $savings%" -ForegroundColor Cyan
        Write-Host "Duration: $durationStr" -ForegroundColor White
        Write-Host "Archive: $OutputPath" -ForegroundColor Green
        
        # Verify if requested
        if ($VerifyArchive) {
            Write-Host "`nVerifying archive integrity..." -ForegroundColor Yellow
            & $7zipPath "t" "`"$OutputPath`""
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Archive verification passed!" -ForegroundColor Green
            } else {
                Write-Host "Archive verification failed!" -ForegroundColor Red
            }
        }
        
    } else {
        Write-Host "Compression failed with exit code: $exitCode" -ForegroundColor Red
        exit 1
    }
    
}
catch {
    Write-Host "`nError occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "`nStack Trace:" -ForegroundColor DarkRed
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    exit 1
}
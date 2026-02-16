# decompress-folders.ps1
# Fixed version - Simple script for decompressing archives


# Here are several usage of this decompression

# # Basic extraction (creates subfolder)
# pwsh -ExecutionPolicy Bypass -File "decompress-folders.ps1" -ArchiveFile "C:\raihan\dokumen\project\global-env\faceRecog\backup\backup.7z" -OutputFolder "C:\raihan\dokumen\project\global-env\faceRecog\backup"

# # Extract directly without subfolder
# pwsh -ExecutionPolicy Bypass -File "decompress-folders.ps1" -ArchiveFile "C:\raihan\dokumen\project\global-env\faceRecog\backup\backup.7z" -OutputFolder "C:\raihan\dokumen\project\global-env\faceRecog\backup" -ExtractHere

# # Overwrite existing files
# pwsh -ExecutionPolicy Bypass -File "decompress-folders.ps1" -ArchiveFile "C:\raihan\dokumen\project\global-env\faceRecog\backup\backup.7z" -OutputFolder "C:\raihan\dokumen\project\global-env\faceRecog\backup" -Overwrite

# # List contents only
# pwsh -ExecutionPolicy Bypass -File "decompress-folders.ps1" -ArchiveFile "C:\raihan\dokumen\project\global-env\faceRecog\backup\backup.7z" -ListContents

# # Verify archive only
# pwsh -ExecutionPolicy Bypass -File "decompress-folders.ps1" -ArchiveFile "C:\raihan\dokumen\project\global-env\faceRecog\backup\backup.7z" -VerifyOnly



param(
    [Parameter(Mandatory=$true)]
    [string]$ArchiveFile,
    
    [string]$OutputFolder,
    
    [switch]$Overwrite,
    [switch]$VerifyOnly,
    [switch]$ListContents,
    [switch]$ExtractHere,
    [switch]$CreateSubfolder = $true
)

# Check 7-Zip
$7zipPath = "${env:ProgramFiles}\7-Zip\7z.exe"
if (-not (Test-Path $7zipPath)) {
    Write-Host "7-Zip not found. Installing..." -ForegroundColor Yellow
    winget install 7zip.7zip -e --accept-package-agreements --accept-source-agreements
    $7zipPath = "${env:ProgramFiles}\7-Zip\7z.exe"
}

# Validate archive file
if (-not (Test-Path $ArchiveFile)) {
    Write-Host "Archive file not found: $ArchiveFile" -ForegroundColor Red
    exit 1
}

# Get archive information
Write-Host "=== Archive Extractor ===" -ForegroundColor Yellow
Write-Host "Reading archive information..." -ForegroundColor Cyan

$archiveFileInfo = Get-Item $ArchiveFile
$archiveSize = $archiveFileInfo.Length
$archiveSizeMB = [math]::Round($archiveSize / 1MB, 2)

Write-Host "Archive: $($archiveFileInfo.Name)" -ForegroundColor White
Write-Host "Size: $archiveSizeMB MB" -ForegroundColor White

# If only listing contents
if ($ListContents) {
    Write-Host "`nListing archive contents..." -ForegroundColor Yellow
    & $7zipPath l "$ArchiveFile"
    exit 0
}

# If only verifying
if ($VerifyOnly) {
    Write-Host "`nVerifying archive..." -ForegroundColor Yellow
    & $7zipPath t "$ArchiveFile"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Archive is valid!" -ForegroundColor Green
    } else {
        Write-Host "Archive is corrupted!" -ForegroundColor Red
    }
    exit $LASTEXITCODE
}

# Determine output folder
if ([string]::IsNullOrEmpty($OutputFolder)) {
    $OutputFolder = $PSScriptRoot
}

# Clean up the output folder path (remove trailing backslash if present)
$OutputFolder = $OutputFolder.TrimEnd('\')

# Check if output folder exists
if (-not (Test-Path $OutputFolder)) {
    Write-Host "Creating output folder: $OutputFolder" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
}

# Check if we should extract directly or into a subfolder
$extractPath = $OutputFolder
if ($ExtractHere) {
    # Extract directly to output folder
    $CreateSubfolder = $false
} elseif ($CreateSubfolder) {
    # Extract to a subfolder named after the archive (without extension)
    $archiveName = [System.IO.Path]::GetFileNameWithoutExtension($ArchiveFile)
    $extractPath = Join-Path $OutputFolder $archiveName
    
    # Clean the path
    $extractPath = $extractPath.TrimEnd('\')
    
    # Check if subfolder already exists
    if (Test-Path $extractPath) {
        if ($Overwrite) {
            Write-Host "Cleaning existing folder: $extractPath" -ForegroundColor Yellow
            Remove-Item -Path $extractPath -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            # Append timestamp
            $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
            $extractPath = Join-Path $OutputFolder "${archiveName}_$timestamp"
            Write-Host "Folder exists, extracting to: $extractPath" -ForegroundColor Yellow
        }
    }
}

# Create extraction folder if it doesn't exist
if (-not (Test-Path $extractPath)) {
    New-Item -ItemType Directory -Path $extractPath -Force | Out-Null
}

Write-Host "`nExtraction Details:" -ForegroundColor Cyan
Write-Host "Source: $ArchiveFile" -ForegroundColor White
Write-Host "Destination: $extractPath" -ForegroundColor White

if ($CreateSubfolder) {
    Write-Host "Mode: Extract to subfolder" -ForegroundColor White
} else {
    Write-Host "Mode: Extract directly" -ForegroundColor White
}

if ($Overwrite) {
    Write-Host "Overwrite: Enabled" -ForegroundColor Yellow
} else {
    Write-Host "Overwrite: Disabled (skip existing)" -ForegroundColor Gray
}

# Check disk space
$drive = (Get-Item $extractPath).PSDrive.Name
$driveInfo = Get-PSDrive $drive
$freeSpaceGB = [math]::Round($driveInfo.Free / 1GB, 2)

Write-Host "Available space: $freeSpaceGB GB" -ForegroundColor White

# Confirm before extraction
Write-Host ""
$confirmation = Read-Host "Proceed with extraction? (Y/N)"
if ($confirmation -notin @('Y', 'y')) {
    Write-Host "Extraction cancelled." -ForegroundColor Yellow
    exit 0
}

# Prepare 7-Zip arguments
$7zArgs = @()

if ($Overwrite) {
    $7zArgs += "-aoa"  # Overwrite All existing files without prompt
} else {
    $7zArgs += "-aos"  # Skip extracting of existing files
}

# Add multithreading
$7zArgs += "-mmt=on"

# Start extraction
Write-Host "`nExtracting..." -ForegroundColor Green
$startTime = Get-Date

# Build and execute the 7-Zip command
$command = "& `"$7zipPath`" x `"$ArchiveFile`" -o`"$extractPath`" $($7zArgs -join ' ')"
Write-Host "Command: $command" -ForegroundColor Gray

try {
    Invoke-Expression $command
    
    if ($LASTEXITCODE -eq 0) {
        $endTime = Get-Date
        $duration = $endTime - $startTime
        
        # Calculate extracted size
        if (Test-Path $extractPath) {
            $extractedItems = Get-ChildItem -Path $extractPath -Recurse -ErrorAction SilentlyContinue
            $extractedFiles = $extractedItems | Where-Object { -not $_.PSIsContainer }
            $extractedFolders = $extractedItems | Where-Object { $_.PSIsContainer }
            
            $extractedSize = ($extractedFiles | Measure-Object -Property Length -Sum).Sum
            $extractedSizeMB = [math]::Round($extractedSize / 1MB, 2)
            
            Write-Host "`n=== Extraction Complete ===" -ForegroundColor Green
            Write-Host "Destination: $extractPath" -ForegroundColor White
            Write-Host "Files extracted: $($extractedFiles.Count)" -ForegroundColor White
            Write-Host "Folders created: $($extractedFolders.Count)" -ForegroundColor White
            Write-Host "Total size: $extractedSizeMB MB" -ForegroundColor White
            Write-Host "Duration: $($duration.ToString('hh\:mm\:ss'))" -ForegroundColor White
            
            # Show first few extracted items
            $topItems = $extractedItems | Select-Object -First 5
            if ($topItems) {
                Write-Host "`nFirst few items:" -ForegroundColor Gray
                foreach ($item in $topItems) {
                    Write-Host "  $($item.Name)" -ForegroundColor Gray
                }
                if ($extractedItems.Count -gt 5) {
                    Write-Host "  ... and $($extractedItems.Count - 5) more" -ForegroundColor DarkGray
                }
            }
        } else {
            Write-Host "Extraction completed but no files found at destination." -ForegroundColor Yellow
        }
    } else {
        Write-Host "`nExtraction failed with error code: $LASTEXITCODE" -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "`nError during extraction: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
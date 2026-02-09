# 1_run_after_validation.ps1
<#
.SYNOPSIS
Runs after validation to send email reports using stable email sender
.DESCRIPTION
Collects and sends run summaries via email after each validation
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$RunFolder,
    
    [Parameter(Mandatory=$false)]
    [hashtable]$ValidationResult = @{},
    
    [Parameter(Mandatory=$false)]
    [switch]$TestMode = $false
)

Write-Host "`n" + "="*60 -ForegroundColor Cyan
Write-Host "POST-VALIDATION EMAIL REPORT" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""

# Load stable email sender
$emailSenderScript = Join-Path $PSScriptRoot "1_email-sender-stable.ps1"
if (-not (Test-Path $emailSenderScript)) {
    Write-Host "✗ Stable email sender not found: $emailSenderScript" -ForegroundColor Red
    exit 1
}

try {
    . $emailSenderScript
    Write-Host "✓ Stable email sender loaded" -ForegroundColor Green
    
    # Determine base path from RunFolder or find latest
    $basePath = $null
    if ($RunFolder -and (Test-Path $RunFolder)) {
        $basePath = Split-Path $RunFolder -Parent
    } else {
        # Try to find the base path from common paths
        $commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
        if (Test-Path $commonPathsScript) {
            . $commonPathsScript
            $paths = Initialize-ProjectPortablePaths -IsMonitor -Silent
            if ($paths -and $paths.DateBasedPath) {
                $basePath = $paths.DateBasedPath
            }
        }
    }
    
    if (-not $basePath -or -not (Test-Path $basePath)) {
        Write-Host "✗ Could not determine base path for email report" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Base path: $basePath" -ForegroundColor Green
    
    # Custom configuration for validation emails
    $emailConfig = @{
        SubjectPrefix = "[Validation] FaceRecog"
    }
    
    # Send immediate report for last 30 minutes
    Write-Host "Sending validation report..." -ForegroundColor Cyan
    
    $result = Send-RunReport -BasePath $basePath -ConfigOverride $emailConfig -TestMode:$TestMode
    
    if ($result) {
        Write-Host "✓ Validation email report sent successfully" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "✗ Failed to send validation email report" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Error in post-validation email: $_" -ForegroundColor Red
    exit 1
}

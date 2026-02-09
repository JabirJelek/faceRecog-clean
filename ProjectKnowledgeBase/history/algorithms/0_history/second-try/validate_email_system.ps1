# validate_email_system.ps1
<#
.SYNOPSIS
Validates the email sending system and tests configuration
.DESCRIPTION
Tests email credentials, configuration, and sends a test email
#>

Write-Host "`n" + "="*60 -ForegroundColor Cyan
Write-Host "EMAIL SYSTEM VALIDATION" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""

# Step 1: Check for required scripts
Write-Host "Step 1: Checking required scripts..." -ForegroundColor Yellow
$requiredScripts = @(
    "1_common-paths.ps1",
    "1_email-sender-stable.ps1"
)

$allFound = $true
foreach ($script in $requiredScripts) {
    $scriptPath = Join-Path $PSScriptRoot $script
    if (Test-Path $scriptPath) {
        Write-Host "  ✓ Found: $script" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Missing: $script" -ForegroundColor Red
        $allFound = $false
    }
}

if (-not $allFound) {
    Write-Host "`nMissing required scripts. Please run stabilization_email.ps1 first." -ForegroundColor Red
    exit 1
}

# Step 2: Test credential loading
Write-Host "`nStep 2: Testing credential loading..." -ForegroundColor Yellow

$credentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
if (Test-Path $credentialPath) {
    try {
        $credential = Import-Clixml -Path $credentialPath
        $username = $credential.GetNetworkCredential().UserName
        Write-Host "  ✓ Credentials loaded for: $username" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Failed to load credentials: $_" -ForegroundColor Red
    }
} else {
    Write-Host "  ⚠ Credential file not found: $credentialPath" -ForegroundColor Yellow
    Write-Host "    Run with -SetupCredentials to create credentials." -ForegroundColor Cyan
}

# Step 3: Test email sender functionality
Write-Host "`nStep 3: Testing email sender..." -ForegroundColor Yellow

try {
    . .\1_email-sender-stable.ps1
    Write-Host "  ✓ Email sender loaded successfully" -ForegroundColor Green
    
    # Initialize paths for testing
    . .\1_common-paths.ps1
    $paths = Initialize-ProjectPortablePaths -IsMonitor -Silent
    
    if ($paths -and $paths.DateBasedPath) {
        Write-Host "  ✓ Paths initialized: $($paths.DateBasedPath)" -ForegroundColor Green
        
        # Test configuration
        Write-Host "`nStep 4: Testing email configuration..." -ForegroundColor Yellow
        
        $testConfig = @{
            SubjectPrefix = "[Test] FaceRecog Validation"
        }
        
        # Run in test mode
        $result = Send-RunReport -BasePath $paths.DateBasedPath -ConfigOverride $testConfig -TestMode
        
        if ($result) {
            Write-Host "  ✓ Email system validation passed!" -ForegroundColor Green
            
            Write-Host "`nNext steps:" -ForegroundColor Cyan
            Write-Host "1. To send a real test email, run:" -ForegroundColor White
            Write-Host "   .\1_email-sender-stable.ps1" -ForegroundColor Yellow
            Write-Host "2. Or run this script with -SendTest parameter" -ForegroundColor Yellow
            Write-Host "`nEmail system is ready for use!" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Email system validation failed" -ForegroundColor Red
        }
    } else {
        Write-Host "  ✗ Failed to initialize paths" -ForegroundColor Red
    }
} catch {
    Write-Host "  ✗ Error testing email sender: $_" -ForegroundColor Red
}

Write-Host "`n" + "="*60 -ForegroundColor Cyan
Write-Host "VALIDATION COMPLETE" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan

# Handle parameters
param(
    [switch]$SetupCredentials,
    [switch]$SendTest
)

if ($SetupCredentials) {
    Write-Host "`nSetting up email credentials..." -ForegroundColor Cyan
    . .\1_email-sender-stable.ps1
    Initialize-EmailConfig
}

if ($SendTest) {
    Write-Host "`nSending test email..." -ForegroundColor Cyan
    . .\1_common-paths.ps1
    . .\1_email-sender-stable.ps1
    
    $paths = Initialize-ProjectPortablePaths -IsMonitor -Silent
    if ($paths -and $paths.DateBasedPath) {
        $testConfig = @{
            SubjectPrefix = "[Live Test] FaceRecog"
        }
        
        Send-RunReport -BasePath $paths.DateBasedPath -ConfigOverride $testConfig
    }
}

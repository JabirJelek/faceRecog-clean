# setup_email_credentials.ps1
<#
.SYNOPSIS
Interactive script to set up email credentials for the monitoring system
.DESCRIPTION
Guides user through setting up email credentials and tests the configuration
#>

Write-Host "`n" + "="*60 -ForegroundColor Cyan
Write-Host "EMAIL CREDENTIAL SETUP" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""

Write-Host "This script will help you set up email credentials for the Face Recognition Monitoring System." -ForegroundColor White
Write-Host "`nPrerequisites:" -ForegroundColor Yellow
Write-Host "• Gmail account with 2-factor authentication enabled" -ForegroundColor White
Write-Host "• App-specific password generated from Google Account" -ForegroundColor White
Write-Host ""

$proceed = Read-Host "Do you want to proceed with email setup? (y/n)"
if ($proceed -ne 'y') {
    Write-Host "Setup cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host "`n" + "-"*40 -ForegroundColor Cyan
Write-Host "STEP 1: Enter Email Credentials" -ForegroundColor Cyan
Write-Host "-"*40 -ForegroundColor Cyan
Write-Host ""

$email = Read-Host "Enter your Gmail address (e.g., yourname@gmail.com)"
Write-Host "`nNote: For Gmail, you need to use an app-specific password, not your regular password." -ForegroundColor Yellow
Write-Host "To generate an app-specific password:" -ForegroundColor White
Write-Host "1. Go to https://myaccount.google.com/" -ForegroundColor White
Write-Host "2. Go to Security > 2-Step Verification > App passwords" -ForegroundColor White
Write-Host "3. Generate a password for 'Mail' on 'Windows Computer'" -ForegroundColor White
Write-Host ""

$appPassword = Read-Host "Enter your app-specific password" -AsSecureString

# Convert secure string to plain text
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($appPassword)
$plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)

Write-Host "`n" + "-"*40 -ForegroundColor Cyan
Write-Host "STEP 2: Save Credentials" -ForegroundColor Cyan
Write-Host "-"*40 -ForegroundColor Cyan
Write-Host ""

# Create credential directory
$credentialDir = "$env:USERPROFILE\.face-recog"
if (-not (Test-Path $credentialDir)) {
    New-Item -ItemType Directory -Path $credentialDir -Force | Out-Null
    Write-Host "Created credential directory: $credentialDir" -ForegroundColor Green
}

# Save credentials securely
$securePassword = ConvertTo-SecureString $plainPassword -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($email, $securePassword)
$credentialPath = Join-Path $credentialDir "email-credential.xml"

try {
    $credential | Export-Clixml -Path $credentialPath
    Write-Host "✓ Credentials saved securely to: $credentialPath" -ForegroundColor Green
} catch {
    Write-Host "✗ Failed to save credentials: $_" -ForegroundColor Red
    exit 1
}

Write-Host "`n" + "-"*40 -ForegroundColor Cyan
Write-Host "STEP 3: Test Configuration" -ForegroundColor Cyan
Write-Host "-"*40 -ForegroundColor Cyan
Write-Host ""

Write-Host "Testing email configuration..." -ForegroundColor Cyan

# Load and test the email sender
$emailSenderScript = Join-Path $PSScriptRoot "1_email-sender-stable.ps1"
if (-not (Test-Path $emailSenderScript)) {
    Write-Host "✗ Email sender script not found. Please run stabilization_email.ps1 first." -ForegroundColor Red
    exit 1
}

try {
    . $emailSenderScript
    
    # Test SMTP connection
    Write-Host "Testing SMTP connection to Gmail..." -ForegroundColor White
    
    $testConfig = @{
        SmtpServer = "smtp.gmail.com"
        SmtpPort = 587
        UseSsl = $true
        Username = $email
        Password = $plainPassword
        FromAddress = $email
        ToAddress = $email
    }
    
    # Create a simple test email
    $testSubject = "[Test] Face Recognition Email Setup"
    $testBody = @"
<html>
<body>
    <h2>Email Setup Successful!</h2>
    <p>This test email confirms that your Face Recognition Monitoring System email configuration is working correctly.</p>
    <p>Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>
    <p>System: maskRecog</p>
</body>
</html>
"@
    
    Write-Host "Attempting to send test email..." -ForegroundColor White
    
    $result = Send-EmailWithAttachments -Subject $testSubject -Body $testBody -Config $testConfig
    
    if ($result) {
        Write-Host "`n" + "="*60 -ForegroundColor Green
        Write-Host "SETUP COMPLETE!" -ForegroundColor Green
        Write-Host "="*60 -ForegroundColor Green
        Write-Host ""
        Write-Host "✓ Email credentials saved successfully" -ForegroundColor Green
        Write-Host "✓ Test email sent to: $email" -ForegroundColor Green
        Write-Host "✓ Email system is ready for use" -ForegroundColor Green
        Write-Host ""
        Write-Host "The monitoring system will now be able to send email reports automatically." -ForegroundColor White
    } else {
        Write-Host "✗ Test email failed to send" -ForegroundColor Red
        Write-Host "Please check your credentials and internet connection." -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "✗ Error during email test: $_" -ForegroundColor Red
    Write-Host "`nTroubleshooting tips:" -ForegroundColor Yellow
    Write-Host "1. Ensure 2-factor authentication is enabled on your Google account" -ForegroundColor White
    Write-Host "2. Generate a new app-specific password" -ForegroundColor White
    Write-Host "3. Check that 'Less secure app access' is NOT enabled (use app passwords instead)" -ForegroundColor White
    Write-Host "4. Verify your internet connection" -ForegroundColor White
}

Write-Host "`n" + "="*60 -ForegroundColor Cyan
Write-Host "SETUP FINISHED" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "1. Run the monitor: .\1_monitor.ps1" -ForegroundColor Yellow
Write-Host "2. Test email reports: .\validate_email_system.ps1 -SendTest" -ForegroundColor Yellow
Write-Host "3. Monitor logs: Check logs-running\magick\[date]\monitor_Magick.log" -ForegroundColor Yellow

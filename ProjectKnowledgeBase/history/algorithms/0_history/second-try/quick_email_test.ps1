# quick_email_test.ps1
Write-Host "Quick email test..." -ForegroundColor Cyan

$emailSender = Join-Path $PSScriptRoot "1_email-sender-stable.ps1"
if (Test-Path $emailSender) {
    . $emailSender
    Write-Host "Email sender loaded. Testing credentials..." -ForegroundColor Green
    
    $credentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
    if (Test-Path $credentialPath) {
        Write-Host "✓ Credentials found" -ForegroundColor Green
    } else {
        Write-Host "⚠ No credentials found. Run setup_email_credentials.ps1" -ForegroundColor Yellow
    }
} else {
    Write-Host "✗ Email sender not found" -ForegroundColor Red
}

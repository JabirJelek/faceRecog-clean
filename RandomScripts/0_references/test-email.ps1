# test-email.ps1
$CredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"

if (Test-Path $CredentialPath) {
    $credential = Import-Clixml -Path $CredentialPath
    
    Write-Host "Testing email credentials..." -ForegroundColor Cyan
    Write-Host "Username: $($credential.UserName)" -ForegroundColor White
    
    # Try to send a test email
    $testParams = @{
        From = $credential.UserName
        To = $credential.UserName  # Send to yourself for testing
        Subject = "Test Email from PowerShell"
        Body = "This is a test email sent at $(Get-Date)"
        SmtpServer = "smtp.gmail.com"
        Port = 587
        UseSsl = $true
        Credential = $credential
    }
    
    try {
        Send-MailMessage @testParams
        Write-Host "✓ Test email sent successfully!" -ForegroundColor Green
    } catch {
        Write-Host "✗ Failed to send email: $_" -ForegroundColor Red
    }
} else {
    Write-Host "Credential file not found: $CredentialPath" -ForegroundColor Red
}
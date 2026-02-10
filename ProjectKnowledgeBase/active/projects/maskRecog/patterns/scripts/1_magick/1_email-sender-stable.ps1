# 1_email-sender-stable.ps1
<#
.SYNOPSIS
Stable email sender for face recognition run reports
.DESCRIPTION
Collects run completion summaries and sends them via email
#>

# ====================================================================
# Configuration - Loaded from credentials or environment
# ====================================================================
$EmailConfig = @{
    SmtpServer = "smtp.gmail.com"
    SmtpPort = 587
    UseSsl = $true
    Username = ""
    Password = ""
    FromAddress = ""
    ToAddress = ""
    SubjectPrefix = "[FaceRecog]"
}

# ====================================================================
# Initialize Email Configuration
# ====================================================================
function Initialize-EmailConfig {
    [CmdletBinding()]
    param(
        [string]$CredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml",
        [hashtable]$OverrideConfig = @{}
    )
    
    Write-Host "Initializing email configuration..." -ForegroundColor Cyan
    
    # Check if credentials file exists
    if (Test-Path $CredentialPath) {
        try {
            $credential = Import-Clixml -Path $CredentialPath -ErrorAction Stop
            $EmailConfig.Username = $credential.GetNetworkCredential().UserName
            $EmailConfig.Password = $credential.GetNetworkCredential().Password
            $EmailConfig.FromAddress = $credential.GetNetworkCredential().UserName
            $EmailConfig.ToAddress = $credential.GetNetworkCredential().UserName
            
            Write-Host "✓ Email credentials loaded from: $CredentialPath" -ForegroundColor Green
        } catch {
            Write-Host "✗ Failed to load credentials: $_" -ForegroundColor Red
            return $false
        }
    } else {
        Write-Host "✗ Credential file not found: $CredentialPath" -ForegroundColor Red
        
        # Prompt for credentials
        Write-Host "`nPlease enter email configuration:" -ForegroundColor Yellow
        $EmailConfig.Username = Read-Host "Email address"
        $EmailConfig.Password = Read-Host "App password" -AsSecureString
        
        # Convert secure string to plain text (not recommended for production)
        $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($EmailConfig.Password)
        $EmailConfig.Password = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)
        
        $EmailConfig.FromAddress = $EmailConfig.Username
        $EmailConfig.ToAddress = $EmailConfig.Username
        
        # Save credentials for future use
        $credentialDir = Split-Path $CredentialPath -Parent
        if (-not (Test-Path $credentialDir)) {
            New-Item -ItemType Directory -Path $credentialDir -Force | Out-Null
        }
        
        $securePassword = ConvertTo-SecureString $EmailConfig.Password -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential($EmailConfig.Username, $securePassword)
        $credential | Export-Clixml -Path $CredentialPath
        
        Write-Host "✓ Credentials saved to: $CredentialPath" -ForegroundColor Green
    }
    
    # Apply any overrides
    foreach ($key in $OverrideConfig.Keys) {
        $EmailConfig[$key] = $OverrideConfig[$key]
    }
    
    return $true
}

# ====================================================================
# Collect Run Summaries
# ====================================================================
function Get-RunSummaries {
    [CmdletBinding()]
    param(
        [string]$BasePath,
        [datetime]$Since,
        [int]$MaxRuns = 10
    )
    
    $summaries = @()
    
    try {
        # Find all run folders
        $runFolders = Get-ChildItem -Path $BasePath -Directory -Filter "Magick_Process_MaskDetect_*" -ErrorAction SilentlyContinue | 
            Sort-Object CreationTime -Descending |
            Select-Object -First $MaxRuns
        
        Write-Host "Found $($runFolders.Count) run folders" -ForegroundColor Cyan
        
        foreach ($folder in $runFolders) {
            # Check if folder was created after the specified time
            if ($folder.CreationTime -ge $Since) {
                $summaryPath = Join-Path $folder.FullName "logs\completion_summary.txt"
                
                if (Test-Path $summaryPath) {
                    $summaryContent = Get-Content $summaryPath -Raw
                    
                    # Parse the summary for exit code
                    $exitCode = "UNKNOWN"
                    if ($summaryContent -match "Exit code: (\d+)") {
                        $exitCode = $matches[1]
                    }
                    
                    # Get metadata if available
                    $metadata = $null
                    $metadataPath = Join-Path $folder.FullName "metadata.json"
                    if (Test-Path $metadataPath) {
                        try {
                            $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
                        } catch { }
                    }
                    
                    $summary = @{
                        FolderPath = $folder.FullName
                        FolderName = $folder.Name
                        CreationTime = $folder.CreationTime
                        ExitCode = $exitCode
                        SummaryText = $summaryContent
                        Metadata = $metadata
                        LogFiles = @()
                        Status = if ($exitCode -eq "0") { "SUCCESS" } else { "FAILED" }
                    }
                    
                    # Find log files
                    $logDir = Join-Path $folder.FullName "logs"
                    if (Test-Path $logDir) {
                        $logFiles = Get-ChildItem -Path $logDir -File -Filter "*.txt" -ErrorAction SilentlyContinue
                        foreach ($logFile in $logFiles) {
                            $summary.LogFiles += @{
                                Path = $logFile.FullName
                                Name = $logFile.Name
                                Size = "$([math]::Round($logFile.Length / 1KB, 2)) KB"
                            }
                        }
                    }
                    
                    $summaries += $summary
                    Write-Host "  ✓ Collected: $($folder.Name) (Exit: $exitCode)" -ForegroundColor Green
                } else {
                    Write-Host "  ⚠ No summary found: $($folder.Name)" -ForegroundColor Yellow
                }
            }
        }
    } catch {
        Write-Host "Error collecting run summaries: $_" -ForegroundColor Red
    }
    
    return $summaries
}

# ====================================================================
# Send Email with Send-MailMessage (No External Dependencies)
# ====================================================================
function Send-EmailWithAttachments {
    [CmdletBinding()]
    param(
        [string]$Subject,
        [string]$Body,
        [array]$Attachments = @(),
        [hashtable]$Config
    )
    
    try {
        Write-Host "Preparing email with $($Attachments.Count) attachments..." -ForegroundColor Cyan
        
        # Create secure password
        $securePassword = ConvertTo-SecureString $Config.Password -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential($Config.Username, $securePassword)
        
        # Prepare email parameters
        $mailParams = @{
            SmtpServer = $Config.SmtpServer
            Port = $Config.SmtpPort
            UseSsl = $Config.UseSsl
            Credential = $credential
            From = $Config.FromAddress
            To = $Config.ToAddress
            Subject = $Subject
            Body = $Body
            BodyAsHtml = $true
            ErrorAction = "Stop"
        }
        
        # Add attachments if any
        if ($Attachments.Count -gt 0) {
            $mailParams.Attachments = @()
            foreach ($attachment in $Attachments) {
                if (Test-Path $attachment) {
                    $mailParams.Attachments += $attachment
                    Write-Host "  ✓ Attached: $(Split-Path $attachment -Leaf)" -ForegroundColor Green
                }
            }
        }
        
        # Send email
        Write-Host "Sending email via $($Config.SmtpServer)..." -ForegroundColor Cyan
        Send-MailMessage @mailParams
        
        Write-Host "✓ Email sent successfully!" -ForegroundColor Green
        return $true
        
    } catch {
        Write-Host "✗ Failed to send email: $_" -ForegroundColor Red
        return $false
    }
}

# ====================================================================
# Create Email Body
# ====================================================================
function Create-EmailBody {
    [CmdletBinding()]
    param(
        [array]$RunSummaries,
        [hashtable]$Config
    )
    
    $runCount = $RunSummaries.Count
    $successCount = ($RunSummaries | Where-Object { $_.Status -eq "SUCCESS" }).Count
    $failedCount = $runCount - $successCount
    
    $htmlBody = @"
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        h2 { color: #34495e; margin-top: 25px; }
        .summary-box { background: #ecf0f1; padding: 15px; border-radius: 5px; margin: 15px 0; }
        .run-card { 
            background: #f8f9fa; 
            padding: 15px; 
            margin: 10px 0; 
            border-left: 4px solid #0078d4;
            border-radius: 3px;
        }
        .run-success { border-left-color: #27ae60; }
        .run-failed { border-left-color: #e74c3c; }
        .status-badge { 
            display: inline-block; 
            padding: 3px 8px; 
            border-radius: 12px; 
            font-size: 12px; 
            font-weight: bold;
            margin-right: 10px;
        }
        .status-success { background: #d4edda; color: #155724; }
        .status-failed { background: #f8d7da; color: #721c24; }
        .metadata { font-size: 12px; color: #7f8c8d; margin-top: 5px; }
        .timestamp { color: #95a5a6; font-size: 11px; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .footer { margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; font-size: 12px; color: #7f8c8d; }
        .highlight { background-color: #fff3cd; padding: 10px; border-radius: 5px; margin: 15px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1> === Face Recognition Run Report === </h1>
        
        <div class="summary-box">
            <h2> === Summary === </h2>
            <p><strong>Total Runs:</strong> $runCount</p>
            <p><strong>Successful:</strong> <span style="color: #27ae60;">$successCount</span></p>
            <p><strong>Failed:</strong> <span style="color: #e74c3c;">$failedCount</span></p>
            <p><strong>Report Time:</strong> $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>
        </div>
        
        <h2> === Recent Runs === </h2>
"@

    foreach ($summary in $RunSummaries) {
        $statusClass = if ($summary.Status -eq "SUCCESS") { "run-success" } else { "run-failed" }
        $statusBadge = if ($summary.Status -eq "SUCCESS") { "status-success" } else { "status-failed" }
        
        $htmlBody += @"
        <div class="run-card $statusClass">
            <div>
                <span class="status-badge $statusBadge">$($summary.Status)</span>
                <strong>$($summary.FolderName)</strong>
            </div>
            <div class="timestamp">Created: $($summary.CreationTime.ToString('yyyy-MM-dd HH:mm:ss'))</div>
            <div class="metadata">
                Exit Code: $($summary.ExitCode)<br>
                $(if ($summary.Metadata -and $summary.Metadata.worker_pid) { "Worker PID: $($summary.Metadata.worker_pid)<br>" })
                $(if ($summary.Metadata -and $summary.Metadata.python_pid) { "Python PID: $($summary.Metadata.python_pid)" })
            </div>
        </div>
"@
    }

    $htmlBody += @"
        
        <div class="footer">
            <p><em>This report was automatically generated by the Face Recognition Monitoring System.</em></p>
            <p>System: maskRecog | Version: $(Get-Date -Format 'yyyy.MM.dd')</p>
        </div>
    </div>
</body>
</html>
"@
    
    return $htmlBody
}

# ====================================================================
# Main Email Sending Function
# ====================================================================
function Send-RunReport {
    [CmdletBinding()]
    param(
        [string]$BasePath,
        [hashtable]$ConfigOverride = @{},
        [switch]$TestMode = $false
    )
    
    Write-Host "`n" + "="*60 -ForegroundColor Cyan
    Write-Host "FACE RECOGNITION EMAIL REPORT" -ForegroundColor Cyan
    Write-Host "="*60 -ForegroundColor Cyan
    Write-Host ""
    
    # Initialize configuration
    if (-not (Initialize-EmailConfig -OverrideConfig $ConfigOverride)) {
        return $false
    }
    
    # Determine time range (last 24 hours by default)
    $since = (Get-Date).AddHours(-24)
    
    # Collect run summaries
    Write-Host "Collecting run summaries from: $BasePath" -ForegroundColor Cyan
    $summaries = Get-RunSummaries -BasePath $BasePath -Since $since -MaxRuns 10
    
    if ($summaries.Count -eq 0) {
        Write-Host "No runs found to report." -ForegroundColor Yellow
        
        # Still send a summary email if needed
        if (-not $TestMode) {
            $subject = "$($EmailConfig.SubjectPrefix) No Runs Found - $(Get-Date -Format 'yyyy-MM-dd')"
            $body = Create-EmailBody -RunSummaries @() -Config $EmailConfig
            return Send-EmailWithAttachments -Subject $subject -Body $body -Config $EmailConfig
        }
        return $true
    }
    
    # Prepare attachments (limit to 3 MB total to avoid email size limits)
    $attachments = @()
    $totalSize = 0
    $maxSize = 3 * 1024 * 1024  # 3 MB
    
    foreach ($summary in $summaries) {
        foreach ($logFile in $summary.LogFiles) {
            if ($totalSize + $logFile.SizeKB -lt $maxSize) {
                $attachments += $logFile.Path
                $totalSize += $logFile.SizeKB
            }
        }
    }
    
    # Create email
    $runCount = $summaries.Count
    $subject = "$($EmailConfig.SubjectPrefix) $runCount Runs - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    $body = Create-EmailBody -RunSummaries $summaries -Config $EmailConfig
    
    Write-Host "`nEmail Details:" -ForegroundColor Cyan
    Write-Host "  Subject: $subject" -ForegroundColor White
    Write-Host "  To: $($EmailConfig.ToAddress)" -ForegroundColor White
    Write-Host "  Runs: $runCount" -ForegroundColor White
    Write-Host "  Attachments: $($attachments.Count) files (~$([math]::Round($totalSize/1024, 2)) MB)" -ForegroundColor White
    
    if ($TestMode) {
        Write-Host "`nTest Mode: Email would be sent with above details." -ForegroundColor Yellow
        return $true
    }
    
    # Send email
    return Send-EmailWithAttachments -Subject $subject -Body $body -Attachments $attachments -Config $EmailConfig
}

# ====================================================================
# Monitor Integration Functions
# ====================================================================
function Register-StableEmailSender {
    [CmdletBinding()]
    param(
        [hashtable]$MonitorConfig,
        [hashtable]$CustomEmailConfig = @{}
    )
    
    # Create global email sender object
    $global:StableEmailSender = @{
        Config = $CustomEmailConfig
        LastSent = $null
        MonitorConfig = $MonitorConfig
        Enabled = $true
        CredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
    }
    
    #Write-Host "Stable email sender registered" -Level "SUCCESS"
    return $true
}

function Invoke-StableEmailReport {
    [CmdletBinding()]
    param(
        [switch]$Force = $false,
        [int]$HoursBack = 1
    )
    
    if (-not $global:StableEmailSender -or -not $global:StableEmailSender.Enabled) {
        Write-Host "Stable email sender not registered or disabled" -ForegroundColor Yellow
        return $false
    }
    
    # Determine if we should send (every hour or if forced)
    $shouldSend = $Force -or (
        $global:StableEmailSender.LastSent -eq $null -or 
        ((Get-Date) - $global:StableEmailSender.LastSent).TotalHours -ge 1
    )
    
    if ($shouldSend) {
        Write-Host "Scheduled email report triggered..." -ForegroundColor Cyan
        
        $success = Send-RunReport -BasePath $global:StableEmailSender.MonitorConfig.RunsBasePath `
            -ConfigOverride $global:StableEmailSender.Config
        
        if ($success) {
            $global:StableEmailSender.LastSent = Get-Date
        }
        
        return $success
    }
    
    return $true
}

# ====================================================================
# Direct Execution
# ====================================================================
if ($MyInvocation.InvocationName -ne '.') {
    # This script is being run directly
    Write-Host "`n" + "="*60 -ForegroundColor Cyan
    Write-Host "DIRECT EMAIL REPORT TEST" -ForegroundColor Cyan
    Write-Host "="*60 -ForegroundColor Cyan
    Write-Host ""
    
    # Get base path from common paths
    $commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
    if (Test-Path $commonPathsScript) {
        try {
            . $commonPathsScript
            $paths = Initialize-ProjectPortablePaths -IsMonitor -Silent
            if ($paths -and $paths.DateBasedPath) {
                Write-Host "Found base path: $($paths.DateBasedPath)" -ForegroundColor Green
                
                # Test email sending
                $testConfig = @{
                    SubjectPrefix = "[Test] FaceRecog"
                }
                
                $result = Send-RunReport -BasePath $paths.DateBasedPath -ConfigOverride $testConfig -TestMode
                
                if ($result) {
                    Write-Host "`n✓ Email test completed successfully!" -ForegroundColor Green
                    Write-Host "   Run with -TestMode:$false to send actual email." -ForegroundColor Yellow
                } else {
                    Write-Host "`n✗ Email test failed" -ForegroundColor Red
                }
            } else {
                Write-Host "Could not initialize paths" -ForegroundColor Red
            }
        } catch {
            Write-Host "Error: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "Common paths script not found at: $commonPathsScript" -ForegroundColor Red
    }
}

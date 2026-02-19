# 1_email-sender-stable.ps1
<#
.SYNOPSIS
Stable email sender for face recognition run reports
#>

# ====================================================================
# LOAD COMMON MODULE
# ====================================================================
$commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
if (-not (Test-Path $commonPathsScript)) { throw "Common paths script not found" }
. $commonPathsScript

$appConfig = Get-ApplicationConfig

# ====================================================================
# Email Configuration – now sourced entirely from $appConfig
# ====================================================================
$EmailConfig = @{
    SmtpServer   = $appConfig.EmailSmtpServer
    SmtpPort     = $appConfig.EmailSmtpPort
    UseSsl       = $appConfig.EmailUseSsl
    Username     = ""   # loaded from credential file
    Password     = ""   # loaded from credential file
    FromAddress  = ""   # loaded from credential file
    ToAddress    = ""   # loaded from credential file
    SubjectPrefix = $appConfig.EmailSubjectPrefix
}

# ====================================================================
# Logging – use common logger, accept log file parameter
# ====================================================================
$script:EmailLogFile = $null
function Write-EmailLog {
    param([string]$Message, [string]$Level = "INFO")
    if ($script:EmailLogFile) {
        Write-CommonLog -Message $Message -Level $Level -LogFile $script:EmailLogFile
    } else {
        Write-CommonLog -Message $Message -Level $Level -NoConsole:$false
    }
}

# ====================================================================
# Initialize Email Configuration   
# ====================================================================
function Initialize-EmailConfig {
    [CmdletBinding()]
    param(
        [string]$CredentialPath = $appConfig.EmailCredentialPath,
        [hashtable]$OverrideConfig = @{}
    )
    Write-EmailLog "Initializing email configuration..." -Level "INFO"
    
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
        Write-Host "`nPlease enter email configuration:" -ForegroundColor Yellow
        $EmailConfig.Username = Read-Host "Email address"
        $EmailConfig.Password = Read-Host "App password" -AsSecureString
        $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($EmailConfig.Password)
        $EmailConfig.Password = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)
        $EmailConfig.FromAddress = $EmailConfig.Username
        $EmailConfig.ToAddress = $EmailConfig.Username
        $credentialDir = Split-Path $CredentialPath -Parent
        if (-not (Test-Path $credentialDir)) {
            New-Item -ItemType Directory -Path $credentialDir -Force | Out-Null
        }
        $securePassword = ConvertTo-SecureString $EmailConfig.Password -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential($EmailConfig.Username, $securePassword)
        $credential | Export-Clixml -Path $CredentialPath
        Write-Host "✓ Credentials saved to: $CredentialPath" -ForegroundColor Green
    }
    
    foreach ($key in $OverrideConfig.Keys) { $EmailConfig[$key] = $OverrideConfig[$key] }
    return $true
}

# ====================================================================
# Collect Run Summaries – now using shared Collect-RunsFromTimeWindow
# ====================================================================
function Get-RunSummaries {
    param(
        [string]$BasePath,
        [datetime]$Since,
        [int]$MaxRuns = $appConfig.EmailMaxRunsToCollect,
        [DateTime]$ScheduleStart = $null,
        [DateTime]$ScheduleEnd = $null,
        [switch]$TimeWindowMode = $false
    )
    
    $summaries = @()
    try {
        # Use shared function to get run folders in the time window
        if ($TimeWindowMode -and $ScheduleStart -and $ScheduleEnd) {
            $windowStart = $ScheduleStart
            $windowEnd   = $ScheduleEnd
            Write-EmailLog "Using schedule time window: $($windowStart.ToString('HH:mm')) to $($windowEnd.ToString('HH:mm'))" -Level "INFO"
        } else {
            $windowStart = $Since
            $windowEnd   = Get-Date
            Write-EmailLog "Using rolling window since $($Since.ToString('yyyy-MM-dd HH:mm'))" -Level "INFO"
        }
        
        $collectedRuns = Collect-RunsFromTimeWindow -BasePath $BasePath -WindowStart $windowStart -WindowEnd $windowEnd -ValidateEach
        Write-EmailLog "Found $($collectedRuns.Count) run folders in window" -Level "INFO"
        
        # Enrich each run with summary/metadata details
        foreach ($run in $collectedRuns) {
            $folderPath = $run.Folder
            $summaryPath = Join-Path $folderPath "$($appConfig.EmailLogsFolder)\$($appConfig.EmailCompletionSummaryFile)"
            $hasSummary = Test-Path $summaryPath
            $metadataPath = Join-Path $folderPath $appConfig.EmailMetadataFile
            $hasMetadata = Test-Path $metadataPath
            $metadata = $null
            if ($hasMetadata) {
                try { $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json } catch { $hasMetadata = $false }
            }
            
            $summary = @{
                FolderPath = $folderPath
                FolderName = $run.Name
                CreationTime = $run.CreationTime
                ExitCode = "UNKNOWN"
                SummaryText = $null
                Metadata = $metadata
                LogFiles = @()
                HasSummary = $hasSummary
                HasMetadata = $hasMetadata
                CollectionType = if ($hasSummary) { "SUMMARY_METADATA" } elseif ($hasMetadata) { "METADATA_ONLY" } else { "NO_DATA" }
                Status = $run.Status   # VALID/INVALID/COLLECTED from shared validation
            }
            
            if ($hasSummary) {
                $summaryContent = Get-Content $summaryPath -Raw
                $summary.SummaryText = $summaryContent
                if ($summaryContent -match "Exit code: (\d+)") {
                    $summary.ExitCode = $matches[1]
                    $summary.Status = if ($matches[1] -eq "1") { "FAILED" } else { "SUCCESS" }
                }
            } elseif ($hasMetadata -and $metadata.worker_exit_code) {
                $summary.ExitCode = $metadata.worker_exit_code
                $summary.Status = if ($metadata.worker_exit_code -eq "1") { "FAILED" } else { "SUCCESS" }
            }
            
            # Collect log files
            $logDir = Join-Path $folderPath $appConfig.EmailLogsFolder
            if (Test-Path $logDir) {
                $logFiles = Get-ChildItem -Path $logDir -File -Filter $appConfig.EmailLogFileFilter -ErrorAction SilentlyContinue
                foreach ($logFile in $logFiles) {
                    $sizeInKB = [math]::Round($logFile.Length / 1KB, 2)
                    $summary.LogFiles += @{
                        Path = $logFile.FullName
                        Name = $logFile.Name
                        Size = "$sizeInKB KB"
                        SizeBytes = $logFile.Length
                        SizeKB = $sizeInKB
                    }
                }
            }
            
            # Compress folder (if not too large)
            $tempDir = [System.IO.Path]::GetTempPath()
            $compressedFolder = Compress-RunFolder -FolderPath $folderPath -DestinationPath $tempDir
            if ($compressedFolder) { $summary.CompressedFolder = $compressedFolder }
            
            $summaries += $summary
        }
        
        # Apply MaxRuns limit (newest first)
        $summaries = $summaries | Sort-Object CreationTime -Descending | Select-Object -First $MaxRuns
        Write-EmailLog "After limiting to $MaxRuns most recent runs, collected $($summaries.Count) summaries" -Level "INFO"
        
    } catch {
        Write-EmailLog "Error collecting run summaries: $_" -Level "ERROR"
    }
    
    return $summaries
}

# ====================================================================
# Helper: Compress Run Folder
# ====================================================================
function Compress-RunFolder {
    [CmdletBinding()]
    param(
        [string]$FolderPath,
        [string]$DestinationPath
    )
    
    try {
        $folderName = Split-Path $FolderPath -Leaf
        $zipPath = Join-Path $DestinationPath "$folderName.zip"
        Compress-Archive -Path "$FolderPath\*" -DestinationPath $zipPath -CompressionLevel Optimal -Force
        $zipFile = Get-Item $zipPath
        return @{
            Path = $zipFile.FullName
            Name = $zipFile.Name
            Size = "$([math]::Round($zipFile.Length / 1KB, 2)) KB"
            SizeBytes = $zipFile.Length
            SizeKB = [math]::Round($zipFile.Length / 1KB, 2)
            SourceFolder = $FolderPath
        }
    } catch {
        Write-Host "  ✗ Failed to compress folder $($FolderPath): $_" -ForegroundColor Red
        return $null
    }
}

# ====================================================================
# Send Email with MailKit Library (Stable version)
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
        
        $currentLocation = $PSScriptRoot
        $mailKitPath = Join-Path $currentLocation "MailKit.dll"
        $mimeKitPath = Join-Path $currentLocation "MimeKit.dll"
        
        if (-not (Test-Path $mailKitPath)) {
            throw "MailKit.dll not found in current location: $currentLocation"
        }
        if (-not (Test-Path $mimeKitPath)) {
            throw "MimeKit.dll not found in current location: $currentLocation"
        }
        
        Add-Type -Path $mailKitPath
        Add-Type -Path $mimeKitPath
        
        $message = New-Object MimeKit.MimeMessage
        $message.From.Add([MimeKit.MailboxAddress]::Parse($Config.FromAddress))
        $message.To.Add([MimeKit.MailboxAddress]::Parse($Config.ToAddress))
        $message.Subject = $Subject
        
        $bodyBuilder = New-Object MimeKit.BodyBuilder
        $bodyBuilder.HtmlBody = $Body
        $bodyBuilder.TextBody = [System.Text.RegularExpressions.Regex]::Replace($Body, "<[^>]*>", "")
        
        $attachmentStreams = @()
        
        try {
            if ($Attachments.Count -gt 0) {
                foreach ($attachmentPath in $Attachments) {
                    if (Test-Path $attachmentPath) {
                        $fileName = Split-Path $attachmentPath -Leaf
                        try {
                            $attachmentStream = [System.IO.File]::OpenRead($attachmentPath)
                            $attachmentStreams += $attachmentStream
                            $bodyBuilder.Attachments.Add($fileName, $attachmentStream, [MimeKit.ContentType]::Parse("application/zip"))
                            Write-Host "  ✓ Attached: $fileName" -ForegroundColor Green
                        } catch {
                            Write-Host "  ⚠ Warning: Could not attach: $_" -ForegroundColor Yellow
                        }
                    }
                }
            }
            
            $message.Body = $bodyBuilder.ToMessageBody()
            
            Write-Host "Sending email via $($Config.SmtpServer):$($Config.SmtpPort)..." -ForegroundColor Cyan
            
            $smtpClient = New-Object MailKit.Net.Smtp.SmtpClient
            try {
                $socketOptions = [MailKit.Security.SecureSocketOptions]::Auto
                if ($Config.SmtpPort -eq 465) {
                    $socketOptions = [MailKit.Security.SecureSocketOptions]::SslOnConnect
                } elseif ($Config.SmtpPort -eq 587) {
                    $socketOptions = [MailKit.Security.SecureSocketOptions]::StartTls
                } else {
                    $socketOptions = if ($Config.UseSsl) { 
                        [MailKit.Security.SecureSocketOptions]::SslOnConnect 
                    } else { 
                        [MailKit.Security.SecureSocketOptions]::None 
                    }
                }
                
                $smtpClient.Connect($Config.SmtpServer, $Config.SmtpPort, $socketOptions)
                $smtpClient.Authenticate($Config.Username, $Config.Password)
                $smtpClient.Send($message)
                $smtpClient.Disconnect($true)
                
                Write-Host "✓ Email sent successfully using MailKit!" -ForegroundColor Green
            } finally {
                if ($smtpClient -and $smtpClient.IsConnected) {
                    $smtpClient.Disconnect($true)
                }
                if ($smtpClient) {
                    $smtpClient.Dispose()
                }
            }
            
            foreach ($attachment in $Attachments) {
                if ($attachment -like "*.zip") {
                    try {
                        Remove-Item $attachment -Force -ErrorAction SilentlyContinue
                        Write-Host "  ✓ Cleaned up temporary zip: $(Split-Path $attachment -Leaf)" -ForegroundColor Gray
                    } catch { }
                }
            }
            return $true
            
        } finally {
            foreach ($stream in $attachmentStreams) {
                try { $stream.Dispose() } catch { }
            }
        }
        
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
        [hashtable]$Config,
        [string]$ScheduleStart = $null,
        [string]$ScheduleEnd = $null
    )
    
    $runCount = $RunSummaries.Count
    $summaryCount = ($RunSummaries | Where-Object { $_.CollectionType -eq "SUMMARY_METADATA" }).Count
    $metadataOnlyCount = ($RunSummaries | Where-Object { $_.CollectionType -eq "METADATA_ONLY" }).Count
    $noDataCount = $runCount - $summaryCount - $metadataOnlyCount
    
    $successCount = ($RunSummaries | Where-Object { $_.Status -eq "SUCCESS" }).Count
    $failedCount = ($RunSummaries | Where-Object { $_.Status -eq "FAILED" }).Count
    $unknownCount = $runCount - $successCount - $failedCount
    
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
        .run-unknown { border-left-color: #95a5a6; }
        .run-metadata-only { border-left-color: #f39c12; }
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
        .status-unknown { background: #d1ecf1; color: #0c5460; }
        .collection-badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 10px;
            margin-left: 8px;
        }
        .collection-summary { background: #28a745; color: white; }
        .collection-metadata { background: #ffc107; color: black; }
        .metadata { font-size: 12px; color: #7f8c8d; margin-top: 5px; }
        .timestamp { color: #95a5a6; font-size: 11px; }
        .footer { margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; font-size: 12px; color: #7f8c8d; }
    </style>
</head>
<body>
    <div class="container">
        <h1> === Face Recognition Run Report === </h1>
        
        <div class="summary-box">
            <h2> === Summary === </h2>
            <p><strong>Total Runs:</strong> $runCount</p>
            <p><strong>With Completion Summary:</strong> <span style="color: #28a745;">$summaryCount</span></p>
            <p><strong>Metadata Only:</strong> <span style="color: #ffc107;">$metadataOnlyCount</span></p>
            <p><strong>No Data:</strong> <span style="color: #dc3545;">$noDataCount</span></p>
            <p><strong>Successful:</strong> <span style="color: #28a745;">$successCount</span></p>
            <p><strong>Failed:</strong> <span style="color: #dc3545;">$failedCount</span></p>
            <p><strong>Unknown Status:</strong> <span style="color: #6c757d;">$unknownCount</span></p>
"@

    if ($ScheduleStart -and $ScheduleEnd) {
        $htmlBody += @"
            <p><strong>Schedule Window:</strong> $ScheduleStart to $ScheduleEnd</p>
"@
    }
    
    $htmlBody += @"
            <p><strong>Report Time:</strong> $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>
        </div>
        
        <h2> === Run Details === </h2>
"@

    foreach ($summary in $RunSummaries) {
        $statusClass = "run-unknown"
        $statusBadge = "status-unknown"
        $statusText = "UNKNOWN"
        
        if ($summary.Status -eq "SUCCESS") { 
            $statusClass = "run-success"
            $statusBadge = "status-success"
            $statusText = "SUCCESS"
        } elseif ($summary.Status -eq "FAILED") { 
            $statusClass = "run-failed"
            $statusBadge = "status-failed"
            $statusText = "FAILED"
        }
        
        if ($summary.CollectionType -eq "METADATA_ONLY") {
            $statusClass = "run-metadata-only"
        }
        
        $collectionBadge = ""
        $collectionText = ""
        if ($summary.CollectionType -eq "SUMMARY_METADATA") {
            $collectionBadge = "collection-summary"
            $collectionText = "Full Data"
        } elseif ($summary.CollectionType -eq "METADATA_ONLY") {
            $collectionBadge = "collection-metadata"
            $collectionText = "Metadata Only"
        }
        
        $htmlBody += @"
        <div class="run-card $statusClass">
            <div>
                <span class="status-badge $statusBadge">$statusText</span>
                <strong>$($summary.FolderName)</strong>
                $(if ($collectionBadge) { "<span class='collection-badge $collectionBadge'>$collectionText</span>" })
            </div>
            <div class="timestamp">Created: $($summary.CreationTime.ToString('yyyy-MM-dd HH:mm:ss'))</div>
            <div class="metadata">
                Exit Code: $($summary.ExitCode)<br>
"@
        
        if ($summary.Metadata) {
            if ($summary.Metadata.worker_pid) {
                $htmlBody += "Worker PID: $($summary.Metadata.worker_pid)<br>"
            }
            if ($summary.Metadata.python_pid) {
                $htmlBody += "Python PID: $($summary.Metadata.python_pid)<br>"
            }
            if ($summary.Metadata.start_time) {
                $htmlBody += "Start Time: $($summary.Metadata.start_time)<br>"
            }
            if ($summary.Metadata.end_time) {
                $htmlBody += "End Time: $($summary.Metadata.end_time)<br>"
            }
        }
        
        $htmlBody += @"
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
# Main Email Sending Function – now accepts log file parameter
# ====================================================================
function Send-RunReport {
    [CmdletBinding()]
    param(
        [string]$BasePath,
        [hashtable]$ConfigOverride = @{},
        [switch]$TestMode = $false,
        [string]$ScheduleStartTime = $null,
        [string]$ScheduleEndTime = $null,
        [switch]$UseTimeWindow = $false,
        [string]$LogFile = $null   # new parameter
    )
    
    $script:EmailLogFile = $LogFile   # set global log file for Write-EmailLog
    
    Write-EmailLog "==============================" -Level "INFO"
    Write-EmailLog "FACE RECOGNITION EMAIL REPORT" -Level "INFO"
    Write-EmailLog "==============================" -Level "INFO"
    
    if (-not (Initialize-EmailConfig -OverrideConfig $ConfigOverride)) { return $false }
    
    $since = (Get-Date).AddHours(-$appConfig.EmailDefaultHoursBack)
    
    $windowStart = $null; $windowEnd = $null
    if ($UseTimeWindow -and $ScheduleStartTime -and $ScheduleEndTime) {
        try {
            $today = Get-Date -Format "yyyy-MM-dd"
            $windowStart = [DateTime]::ParseExact("$today $ScheduleStartTime", "yyyy-MM-dd HH:mm", $null)
            $windowEnd   = [DateTime]::ParseExact("$today $ScheduleEndTime",   "yyyy-MM-dd HH:mm", $null)
        } catch {
            Write-EmailLog "Failed to parse schedule times, using default $($appConfig.EmailDefaultHoursBack)-hour window." -Level "WARN"
            $UseTimeWindow = $false
        }
    }
    
    Write-EmailLog "Collecting run summaries from: $BasePath" -Level "INFO"
    $summaries = Get-RunSummaries -BasePath $BasePath -Since $since `
        -MaxRuns $appConfig.EmailMaxRunsToCollect `
        -ScheduleStart $windowStart -ScheduleEnd $windowEnd -TimeWindowMode:$UseTimeWindow

    
    if ($summaries.Count -eq 0) {
        Write-Host "No runs found to report." -ForegroundColor Yellow
        if (-not $TestMode) {
            $subject = "$($EmailConfig.SubjectPrefix) No Runs Found - $(Get-Date -Format 'yyyy-MM-dd')"
            if ($UseTimeWindow) {
                $subject = "$($EmailConfig.SubjectPrefix) No Runs in Window $ScheduleStartTime-$ScheduleEndTime - $(Get-Date -Format 'yyyy-MM-dd')"
            }
            $body = Create-EmailBody -RunSummaries @() -Config $EmailConfig -ScheduleStart $ScheduleStartTime -ScheduleEnd $ScheduleEndTime
            return Send-EmailWithAttachments -Subject $subject -Body $body -Config $EmailConfig
        }
        return $true
    }

    $totalCollected = $summaries.Count
    $calcSummaryCount = ($summaries | Where-Object { $_.CollectionType -eq "SUMMARY_METADATA" }).Count
    $calcMetadataOnlyCount = ($summaries | Where-Object { $_.CollectionType -eq "METADATA_ONLY" }).Count
    $calcNoDataCount = ($summaries | Where-Object { $_.CollectionType -eq "NO_DATA" }).Count
    
    $calculatedTotal = $calcSummaryCount + $calcMetadataOnlyCount + $calcNoDataCount
    if ($calculatedTotal -ne $totalCollected) {
        Write-Host "Warning: Count mismatch! Calculated: $calculatedTotal, Actual: $totalCollected" -ForegroundColor Red
        Write-Host "  Adjusting counts to match actual total..." -ForegroundColor Yellow
        $summaryCount = $calcSummaryCount
        $metadataOnlyCount = $calcMetadataOnlyCount
        $noDataCount = $calcNoDataCount
    }    
    
    $attachments = @()
    $totalSize = 0
    $maxSize = $appConfig.EmailMaxAttachmentSizeMB * 1024 * 1024
    
    $summaryCount = ($summaries | Where-Object { $_.CollectionType -eq "SUMMARY_METADATA" }).Count
    $metadataOnlyCount = ($summaries | Where-Object { $_.CollectionType -eq "METADATA_ONLY" }).Count
    $noDataCount = ($summaries | Where-Object { $_.CollectionType -eq "NO_DATA" }).Count
    
    foreach ($summary in $summaries) {
        if ($summary.CompressedFolder) {
            $zipFile = $summary.CompressedFolder
            $sizeInBytes = $zipFile.SizeBytes
            if (($totalSize + $sizeInBytes) -lt $maxSize) {
                $attachments += $zipFile.Path
                $totalSize += $sizeInBytes
                Write-Host "  ✓ Will attach compressed folder: $($zipFile.Name) ($($zipFile.Size))" -ForegroundColor Green
            }
        } else {
            foreach ($logFile in $summary.LogFiles) {
                $sizeInBytes = if ($logFile.SizeBytes) {
                    $logFile.SizeBytes
                } elseif ($logFile.SizeKB) {
                    $logFile.SizeKB * 1024
                } else {
                    0
                }
                if (($totalSize + $sizeInBytes) -lt $maxSize) {
                    $attachments += $logFile.Path
                    $totalSize += $sizeInBytes
                }
            }
        }
    }
    
    $runCount = $summaries.Count
    $subject = "$($EmailConfig.SubjectPrefix) $runCount Runs - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    if ($UseTimeWindow) {
        $subject = "$($EmailConfig.SubjectPrefix) $runCount Runs ($ScheduleStartTime-$ScheduleEndTime) - $(Get-Date -Format 'yyyy-MM-dd')"
    }
    
    $body = Create-EmailBody -RunSummaries $summaries -Config $EmailConfig -ScheduleStart $ScheduleStartTime -ScheduleEnd $ScheduleEndTime
    
    Write-Host "`nEmail Details:" -ForegroundColor Cyan
    Write-Host "  Subject: $subject" -ForegroundColor White
    Write-Host "  To: $($EmailConfig.ToAddress)" -ForegroundColor White
    Write-Host "  Total runs in collection: $($summaries.Count)" -ForegroundColor White
    Write-Host "  With summary: $summaryCount" -ForegroundColor Green
    Write-Host "  Metadata only: $metadataOnlyCount" -ForegroundColor Yellow
    Write-Host "  No data: $noDataCount" -ForegroundColor Gray
    Write-Host "  Attachments: $($attachments.Count) files (~$([math]::Round($totalSize/1MB, 2)) MB)" -ForegroundColor White
    $compressedCount = ($summaries | Where-Object { $_.CompressedFolder }).Count
    Write-Host "  Compressed folders: $compressedCount" -ForegroundColor Cyan
    if ($UseTimeWindow) {
        Write-Host "  Time window: $ScheduleStartTime to $ScheduleEndTime" -ForegroundColor Cyan
    }
    
    if ($TestMode) {
        Write-Host "`nTest Mode: Email would be sent with above details." -ForegroundColor Yellow
        return $true
    }
    
    return Send-EmailWithAttachments -Subject $subject -Body $body -Attachments $attachments -Config $EmailConfig
}

# ====================================================================
# Monitor Integration Functions – now use Write-EmailLog
# ====================================================================
function Register-StableEmailSender {
    param(
        [hashtable]$MonitorConfig,
        [hashtable]$CustomEmailConfig = @{}
    )
    $global:StableEmailSender = @{
        Config         = $CustomEmailConfig
        LastSent       = $null
        MonitorConfig  = $MonitorConfig
        Enabled        = $true
        CredentialPath = $appConfig.EmailCredentialPath
    }
    return $true
}

function Invoke-StableEmailReport {
    [CmdletBinding()]
    param(
        [switch]$Force = $false
    )
    
    if (-not $global:StableEmailSender -or -not $global:StableEmailSender.Enabled) {
        Write-Host "Stable email sender not registered or disabled" -ForegroundColor Yellow
        return $false
    }
    
    $shouldSend = $Force -or (
        $global:StableEmailSender.LastSent -eq $null -or 
        ((Get-Date) - $global:StableEmailSender.LastSent).TotalHours -ge 1
    )
    
    if ($shouldSend) {
        Write-Host "Sending email report..." -ForegroundColor Cyan
        Write-Host "Time: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Gray
        
        if (-not $global:StableEmailSender.Config -or $global:StableEmailSender.Config.Count -eq 0) {
            $global:StableEmailSender.Config = @{ SubjectPrefix = "[FaceRecog]" }
        }
        
        $scheduleStart = $global:StableEmailSender.Config.ScheduleStartTime
        $scheduleEnd = $global:StableEmailSender.Config.ScheduleEndTime
        $useTimeWindow = ($scheduleStart -and $scheduleEnd)
        
        if ($useTimeWindow) {
            Write-Host "Using schedule window: $scheduleStart to $scheduleEnd" -ForegroundColor White
        }
        
        $success = Send-RunReport -BasePath $global:StableEmailSender.MonitorConfig.RunsBasePath `
            -ConfigOverride $global:StableEmailSender.Config `
            -ScheduleStartTime $scheduleStart -ScheduleEndTime $scheduleEnd -UseTimeWindow:$useTimeWindow `
            -LogFile $global:StableEmailSender.MonitorConfig.LogFile   # <-- new
        
        if ($success) {
            $global:StableEmailSender.LastSent = Get-Date
            Write-Host "Email sent successfully at $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Green
        } else {
            Write-Host "Failed to send email" -ForegroundColor Red
        }
        return $success
    } else {
        Write-Host "Email report not sent (recently sent at $($global:StableEmailSender.LastSent.ToString('HH:mm:ss')))" -ForegroundColor Gray
        return $true
    }
}

# ====================================================================
# Direct Execution – now uses shared path initialisation
# ====================================================================
if ($MyInvocation.InvocationName -ne '.') {
    Write-Host "==============================" -ForegroundColor Cyan
    Write-Host "DIRECT EMAIL REPORT TEST" -ForegroundColor Cyan
    Write-Host "==============================" -ForegroundColor Cyan
    Write-Host ""
    
    # Get base path from common paths
    $commonPathsScript = Join-Path $PSScriptRoot $appConfig.EmailCommonPathsScript
    if (Test-Path $commonPathsScript) {
        try {
            $paths = Initialize-ProjectPortablePaths -IsMonitor -Silent
            if ($paths -and $paths.DateBasedPath) {
                Write-Host "Found base path: $($paths.DateBasedPath)" -ForegroundColor Green
                $testConfig = @{ SubjectPrefix = "[Test] FaceRecog" }
                # In test mode we still want console output, so no log file
                $result = Send-RunReport -BasePath $paths.DateBasedPath -ConfigOverride $testConfig -TestMode
                if ($result) {
                    Write-Host "`n✓ Email test completed successfully!" -ForegroundColor Green
                    Write-Host "   Run with -TestMode:`$false to send actual email." -ForegroundColor Yellow
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
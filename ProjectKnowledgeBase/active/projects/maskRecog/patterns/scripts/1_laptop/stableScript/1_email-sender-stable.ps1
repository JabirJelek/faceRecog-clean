# 1_email-sender-stable.ps1
<#
.SYNOPSIS
Stable email sender for face recognition run reports
.DESCRIPTION
Collects run completion summaries and sends them via email
#>

# ====================================================================
# CONFIGURATION - MODIFY THESE VALUES AS NEEDED
# ====================================================================
$ScriptConfig = @{
    # Credentials file location
    CredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
    
    # Run folder naming pattern
    RunFolderFilter = "Laptop_Process_MaskDetect_*"
    
    # File and folder names
    CompletionSummaryFile = "completion_summary.txt"
    MetadataFile = "metadata.json"
    LogsFolder = "logs"
    LogFileFilter = "*.txt"
    
    # Common paths script (if used)
    CommonPathsScript = "1_common-paths.ps1"
    
    # Default collection settings
    MaxRunsToCollect = 10
    DefaultHoursBack = 24
    MaxAttachmentSizeMB = 3
}

# ====================================================================
# Email Configuration - Loaded from credentials or environment
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
        [string]$CredentialPath = $ScriptConfig.CredentialPath,
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
        [int]$MaxRuns = $ScriptConfig.MaxRunsToCollect,
        [DateTime]$ScheduleStart = $null,
        [DateTime]$ScheduleEnd = $null,
        [switch]$TimeWindowMode = $false
    )
    
    $summaries = @()
    
    try {
        # Find all run folders
        $runFolders = Get-ChildItem -Path $BasePath -Directory -Filter $ScriptConfig.RunFolderFilter -ErrorAction SilentlyContinue | 
            Sort-Object CreationTime -Descending |
            Select-Object -First $MaxRuns
        
        Write-Host "Found $($runFolders.Count) run folders" -ForegroundColor Cyan
        
        $collectedWithSummary = 0
        $collectedMetadataOnly = 0
        $outsideTimeWindow = 0
        
        foreach ($folder in $runFolders) {
            # If TimeWindowMode is enabled, filter by schedule time
            $inTimeWindow = $true
            if ($TimeWindowMode -and $ScheduleStart -and $ScheduleEnd) {
                $inTimeWindow = ($folder.CreationTime -ge $ScheduleStart -and $folder.CreationTime -le $ScheduleEnd)
                if (-not $inTimeWindow) {
                    $outsideTimeWindow++
                    continue
                }
            }
            
            # Check if folder was created after the specified time
            if ($folder.CreationTime -ge $Since) {
                $summaryPath = Join-Path $folder.FullName "$($ScriptConfig.LogsFolder)\$($ScriptConfig.CompletionSummaryFile)"
                $hasSummary = Test-Path $summaryPath
                
                # Get metadata if available
                $metadata = $null
                $metadataPath = Join-Path $folder.FullName $ScriptConfig.MetadataFile
                $hasMetadata = Test-Path $metadataPath
                
                if ($hasMetadata) {
                    try {
                        $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
                    } catch { 
                        $hasMetadata = $false
                    }
                }
                
                # Create summary object
                $summary = @{
                    FolderPath = $folder.FullName
                    FolderName = $folder.Name
                    CreationTime = $folder.CreationTime
                    ExitCode = "UNKNOWN"
                    SummaryText = $null
                    Metadata = $metadata
                    LogFiles = @()
                    HasSummary = $hasSummary
                    HasMetadata = $hasMetadata
                    CollectionType = "UNKNOWN"
                    Status = "UNKNOWN"
                }
                
                if ($hasSummary) {
                    $summaryContent = Get-Content $summaryPath -Raw
                    $summary.SummaryText = $summaryContent
                    
                    # Parse the summary for exit code
                    if ($summaryContent -match "Exit code: (\d+)") {
                        $summary.ExitCode = $matches[1]
                        $summary.Status = if ($matches[1] -eq "1") { "FAILED" } else { "SUCCESS" } # This logic is to determine the success and failed status of the system.
                    }
                    $summary.CollectionType = "SUMMARY_METADATA"
                    $collectedWithSummary++
                    Write-Host "  ✓ Collected with summary: $($folder.Name) (Exit: $($summary.ExitCode))" -ForegroundColor Green
                } elseif ($hasMetadata) {
                    # Try to get exit code from metadata
                    if ($metadata -and $metadata.worker_exit_code) {
                        $summary.ExitCode = $metadata.worker_exit_code
                        $summary.Status = if ($metadata.worker_exit_code -eq "1") { "FAILED" } else { "SUCCESS" } # This logic is to determine the success and failed status of the system.
                    }
                    $summary.CollectionType = "METADATA_ONLY"
                    $collectedMetadataOnly++
                    Write-Host "  ⚠ Collected metadata only: $($folder.Name) (Exit: $($summary.ExitCode))" -ForegroundColor Yellow
                } else {
                    # No summary or metadata
                    $summary.CollectionType = "NO_DATA"
                    Write-Host "  ✗ No data found: $($folder.Name)" -ForegroundColor Red
                }
                
                # Find log files (even if no summary, we might still have logs)
                $logDir = Join-Path $folder.FullName $ScriptConfig.LogsFolder
                if (Test-Path $logDir) {
                    $logFiles = Get-ChildItem -Path $logDir -File -Filter $ScriptConfig.LogFileFilter -ErrorAction SilentlyContinue
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
                
                # Create compressed zip for the entire run folder
                $tempDir = [System.IO.Path]::GetTempPath()
                $compressedFolder = Compress-RunFolder -FolderPath $folder.FullName -DestinationPath $tempDir
                if ($compressedFolder) {
                    $summary.CompressedFolder = $compressedFolder
                }

                
                $summaries += $summary
            }
        }
        
        # Calculate final counts correctly
        $totalInWindow = $runFolders.Count - $outsideTimeWindow
        $noDataCount = ($summaries | Where-Object { $_.CollectionType -eq "NO_DATA" }).Count
        
        Write-Host "`nCollection Summary:" -ForegroundColor Cyan
        Write-Host "  Total folders checked: $($runFolders.Count)" -ForegroundColor White
        Write-Host "  Runs in time window: $totalInWindow" -ForegroundColor White
        Write-Host "  With completion summary: $collectedWithSummary" -ForegroundColor Green
        Write-Host "  Metadata only: $collectedMetadataOnly" -ForegroundColor Yellow
        Write-Host "  No data available: $noDataCount" -ForegroundColor Red
        if ($TimeWindowMode) {
            Write-Host "  Outside time window: $outsideTimeWindow" -ForegroundColor Gray
        }
        
    } catch {
        Write-Host "Error collecting run summaries: $_" -ForegroundColor Red
    }
    
    return $summaries
}

# ====================================================================
# Send Email with Send-MailMessage (No External Dependencies)
# ====================================================================

# Add this function to handle folder compression
function Compress-RunFolder {
    [CmdletBinding()]
    param(
        [string]$FolderPath,
        [string]$DestinationPath
    )
    
    try {
        # Create zip file name based on folder name
        $folderName = Split-Path $FolderPath -Leaf
        $zipPath = Join-Path $DestinationPath "$folderName.zip"
        
        # Use Compress-Archive to create zip
        Compress-Archive -Path "$FolderPath\*" -DestinationPath $zipPath -CompressionLevel Optimal -Force
        
        # Return zip file info
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
        
        # Load MailKit and MimeKit assemblies
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
        
        # Create MIME message
        $message = New-Object MimeKit.MimeMessage
        $message.From.Add([MimeKit.MailboxAddress]::Parse($Config.FromAddress))
        $message.To.Add([MimeKit.MailboxAddress]::Parse($Config.ToAddress))
        $message.Subject = $Subject
        
        # Create message body with HTML content
        $bodyBuilder = New-Object MimeKit.BodyBuilder
        $bodyBuilder.HtmlBody = $Body
        $bodyBuilder.TextBody = [System.Text.RegularExpressions.Regex]::Replace($Body, "<[^>]*>", "")
        
        # Track opened streams for proper cleanup
        $attachmentStreams = @()
        
        try {
            # Add attachments if any
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
            
            # Send using MailKit SmtpClient with correct SSL/TLS options
            Write-Host "Sending email via $($Config.SmtpServer):$($Config.SmtpPort)..." -ForegroundColor Cyan
            
            $smtpClient = New-Object MailKit.Net.Smtp.SmtpClient
            try {
                # Determine secure socket options based on port and config
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
            
            # Clean up temporary zip files
            foreach ($attachment in $Attachments) {
                if ($attachment -like "*.zip") {
                    try {
                        Remove-Item $attachment -Force -ErrorAction SilentlyContinue
                        Write-Host "  ✓ Cleaned up temporary zip: $(Split-Path $attachment -Leaf)" -ForegroundColor Gray
                    } catch {
                        # Silent cleanup - don't fail if cleanup fails
                    }
                }
            }
            
            return $true
            
        } finally {
            # Ensure all attachment streams are disposed
            foreach ($stream in $attachmentStreams) {
                try {
                    $stream.Dispose()
                } catch {
                    # Silently continue
                }
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
        # Determine status class and badge
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
        
        # Add metadata-only styling
        if ($summary.CollectionType -eq "METADATA_ONLY") {
            $statusClass = "run-metadata-only"
        }
        
        # Determine collection badge
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
# Main Email Sending Function
# ====================================================================
function Send-RunReport {
    [CmdletBinding()]
    param(
        [string]$BasePath,
        [hashtable]$ConfigOverride = @{},
        [switch]$TestMode = $false,
        [string]$ScheduleStartTime = $null,
        [string]$ScheduleEndTime = $null,
        [switch]$UseTimeWindow = $false
    )
    
    Write-Host "==============================" -ForegroundColor Cyan
    Write-Host "FACE RECOGNITION EMAIL REPORT" -ForegroundColor Cyan
    Write-Host "==============================" -ForegroundColor Cyan
    Write-Host ""
    
    # Initialize configuration
    if (-not (Initialize-EmailConfig -OverrideConfig $ConfigOverride)) {
        return $false
    }
    
    # Determine time range based on mode
    $since = (Get-Date).AddHours(-$ScriptConfig.DefaultHoursBack)  # Default: last 24 hours
    
    # If using schedule time window, parse the times
    $windowStart = $null
    $windowEnd = $null
    if ($UseTimeWindow -and $ScheduleStartTime -and $ScheduleEndTime) {
        try {
            $today = Get-Date -Format "yyyy-MM-dd"
            $windowStart = [DateTime]::ParseExact("$today $ScheduleStartTime", "yyyy-MM-dd HH:mm", $null)
            $windowEnd = [DateTime]::ParseExact("$today $ScheduleEndTime", "yyyy-MM-dd HH:mm", $null)
            
            Write-Host "Using schedule time window:" -ForegroundColor Cyan
            Write-Host "  Start: $ScheduleStartTime" -ForegroundColor White
            Write-Host "  End: $ScheduleEndTime" -ForegroundColor White
            Write-Host "  Window: $($windowStart.ToString('HH:mm')) to $($windowEnd.ToString('HH:mm'))" -ForegroundColor White
        } catch {
            Write-Host "Warning: Failed to parse schedule times. Using default $($ScriptConfig.DefaultHoursBack)-hour window." -ForegroundColor Yellow
            Write-Host "  Error: $_" -ForegroundColor Red
            $UseTimeWindow = $false
        }
    }
    
    # Collect run summaries
    Write-Host "Collecting run summaries from: $BasePath" -ForegroundColor Cyan
    $summaries = Get-RunSummaries -BasePath $BasePath -Since $since -MaxRuns $ScriptConfig.MaxRunsToCollect `
        -ScheduleStart $windowStart -ScheduleEnd $windowEnd -TimeWindowMode:$UseTimeWindow
    
    if ($summaries.Count -eq 0) {
        Write-Host "No runs found to report." -ForegroundColor Yellow
        
        # Still send a summary email if needed
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

    # Validate the counts
    $totalCollected = $summaries.Count
    $calcSummaryCount = ($summaries | Where-Object { $_.CollectionType -eq "SUMMARY_METADATA" }).Count
    $calcMetadataOnlyCount = ($summaries | Where-Object { $_.CollectionType -eq "METADATA_ONLY" }).Count
    $calcNoDataCount = ($summaries | Where-Object { $_.CollectionType -eq "NO_DATA" }).Count
    
    # Verify counts add up
    $calculatedTotal = $calcSummaryCount + $calcMetadataOnlyCount + $calcNoDataCount
    if ($calculatedTotal -ne $totalCollected) {
        Write-Host "Warning: Count mismatch! Calculated: $calculatedTotal, Actual: $totalCollected" -ForegroundColor Red
        Write-Host "  Adjusting counts to match actual total..." -ForegroundColor Yellow
        $summaryCount = $calcSummaryCount
        $metadataOnlyCount = $calcMetadataOnlyCount
        $noDataCount = $calcNoDataCount
    }    
    
    # Prepare attachments - only attach from runs that have data
    $attachments = @()
    $totalSize = 0
    $maxSize = $ScriptConfig.MaxAttachmentSizeMB * 1024 * 1024  # Convert MB to bytes
    
    # Calculate counts correctly
    $summaryCount = ($summaries | Where-Object { $_.CollectionType -eq "SUMMARY_METADATA" }).Count
    $metadataOnlyCount = ($summaries | Where-Object { $_.CollectionType -eq "METADATA_ONLY" }).Count
    $noDataCount = ($summaries | Where-Object { $_.CollectionType -eq "NO_DATA" }).Count
    
    foreach ($summary in $summaries) {
        # Use compressed folder if available, otherwise fall back to individual files
        if ($summary.CompressedFolder) {
            $zipFile = $summary.CompressedFolder
            $sizeInBytes = $zipFile.SizeBytes
            
            if (($totalSize + $sizeInBytes) -lt $maxSize) {
                $attachments += $zipFile.Path
                $totalSize += $sizeInBytes
                Write-Host "  ✓ Will attach compressed folder: $($zipFile.Name) ($($zipFile.Size))" -ForegroundColor Green
            }
        } else {
            # Fallback to individual files if compression failed
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
    
    # Create email
    $runCount = $summaries.Count
    $subject = "$($EmailConfig.SubjectPrefix) $runCount Runs - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    
    if ($UseTimeWindow) {
        $subject = "$($EmailConfig.SubjectPrefix) $runCount Runs ($ScheduleStartTime-$ScheduleEndTime) - $(Get-Date -Format 'yyyy-MM-dd')"
    }
    
    $body = Create-EmailBody -RunSummaries $summaries -Config $EmailConfig -ScheduleStart $ScheduleStartTime -ScheduleEnd $ScheduleEndTime
    
    # Update the email details display to show compression info
    # Find this section in Send-RunReport function (around line 380-390):
    Write-Host "`nEmail Details:" -ForegroundColor Cyan
    Write-Host "  Subject: $subject" -ForegroundColor White
    Write-Host "  To: $($EmailConfig.ToAddress)" -ForegroundColor White
    Write-Host "  Total runs in collection: $($summaries.Count)" -ForegroundColor White
    Write-Host "  With summary: $summaryCount" -ForegroundColor Green
    Write-Host "  Metadata only: $metadataOnlyCount" -ForegroundColor Yellow
    Write-Host "  No data: $noDataCount" -ForegroundColor Gray
    Write-Host "  Attachments: $($attachments.Count) files (~$([math]::Round($totalSize/1MB, 2)) MB)" -ForegroundColor White

    # Add a line to show compression status:
    $compressedCount = ($summaries | Where-Object { $_.CompressedFolder }).Count
    Write-Host "  Compressed folders: $compressedCount" -ForegroundColor Cyan
    if ($UseTimeWindow) {
        Write-Host "  Time window: $ScheduleStartTime to $ScheduleEndTime" -ForegroundColor Cyan
    }
    
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
        CredentialPath = $ScriptConfig.CredentialPath
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
    
    # Determine if we should send (every hour or if forced)
    $shouldSend = $Force -or (
        $global:StableEmailSender.LastSent -eq $null -or 
        ((Get-Date) - $global:StableEmailSender.LastSent).TotalHours -ge 1
    )
    
    if ($shouldSend) {
        Write-Host "Sending email report..." -ForegroundColor Cyan
        Write-Host "Time: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Gray
        
        # Initialize the configuration if needed
        if (-not $global:StableEmailSender.Config -or $global:StableEmailSender.Config.Count -eq 0) {
            $global:StableEmailSender.Config = @{
                SubjectPrefix = "[FaceRecog]"
            }
        }
        
        # Extract schedule times from config
        $scheduleStart = $global:StableEmailSender.Config.ScheduleStartTime
        $scheduleEnd = $global:StableEmailSender.Config.ScheduleEndTime
        
        # Send the report with time window if schedule times are available
        $useTimeWindow = ($scheduleStart -and $scheduleEnd)
        
        if ($useTimeWindow) {
            Write-Host "Using schedule window: $scheduleStart to $scheduleEnd" -ForegroundColor White
        }
        
        $success = Send-RunReport -BasePath $global:StableEmailSender.MonitorConfig.RunsBasePath `
            -ConfigOverride $global:StableEmailSender.Config `
            -ScheduleStartTime $scheduleStart `
            -ScheduleEndTime $scheduleEnd `
            -UseTimeWindow:$useTimeWindow
        
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
# Direct Execution
# ====================================================================
if ($MyInvocation.InvocationName -ne '.') {
    # This script is being run directly
    Write-Host "==============================" -ForegroundColor Cyan
    Write-Host "DIRECT EMAIL REPORT TEST" -ForegroundColor Cyan
    Write-Host "==============================" -ForegroundColor Cyan
    Write-Host ""
    
    # Get base path from common paths
    $commonPathsScript = Join-Path $PSScriptRoot $ScriptConfig.CommonPathsScript
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
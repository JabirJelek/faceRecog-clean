#### Important

- Maintain the query requirement.
- Check explanation in every ####
- DO NOT INTRODUCES unused solution that does not relate to the query.
- Focus on what is being queried in the instructions, only take note other non-related with instructions unless user asks for it.
- Small and effective changes

#### Instructions

Update the codebase, so that the error is fixed and the debug can be easily readable, and the flow of the system integrate much more stable.

#### Output of the codebase

[2026-02-10 13:25:13] [SHUTDOWN] End time reached - initiating shutdown sequence...
[2026-02-10 13:25:13] [INFO] Time window for validation: 13:12 to 13:25
[2026-02-10 13:25:13] [INFO] Current time: 13:25:13
[2026-02-10 13:25:13] [INFO] Validating ALL runs from today's monitoring window...
[2026-02-10 13:25:13] [INFO] Validating face recognition output structure...
[2026-02-10 13:25:13] [INFO] Using enhanced collection mode for all runs in time window
[2026-02-10 13:25:13] [INFO] Collecting runs from 13:12 to 13:25...
[2026-02-10 13:25:13] [INFO] Time window for collection: 13:12 to 13:25
[2026-02-10 13:25:13] [DEBUG] Integrated collection called with StartTime: '13:12', EndTime: '13:25'
[2026-02-10 13:25:13] [INFO] Found 24 total run folders
[2026-02-10 13:25:13] [INFO] Time window parsed: 2026-02-10 13:12:00 to 2026-02-10 13:25:00
[2026-02-10 13:25:13] [DEBUG] Validating folder: D:\RaihanFarid\Dokumen\faceRecog\ProjectKnowledgeBase\active\logs-running\magick\2026-02-10\Magick_Process_MaskDetect_2026-02-10_13-21-24
[2026-02-10 13:25:13] [INFO] ✓ Collected: Magick_Process_MaskDetect_2026-02-10_13-21-24
[2026-02-10 13:25:13] [DEBUG] Validating folder: D:\RaihanFarid\Dokumen\faceRecog\ProjectKnowledgeBase\active\logs-running\magick\2026-02-10\Magick_Process_MaskDetect_2026-02-10_13-24-10
[2026-02-10 13:25:13] [INFO] ✓ Collected: Magick_Process_MaskDetect_2026-02-10_13-24-10
[2026-02-10 13:25:13] [INFO] Collection complete. Found 2 runs within time window.
[2026-02-10 13:25:13] [INFO] Collection completed: 2/2 valid runs
[2026-02-10 13:25:13] [SUCCESS] All runs validation successful: 2/2 valid
[2026-02-10 13:25:13] [INFO] Sending final daily email report...
[2026-02-10 13:25:13] [INFO] Scheduled email report triggered...
[2026-02-10 13:25:13] [DEBUG] Email configuration:
[2026-02-10 13:25:13] [DEBUG] Start time: 13:12
[2026-02-10 13:25:14] [DEBUG] End time: 13:25
[2026-02-10 13:25:14] [DEBUG] Runs base path: D:\RaihanFarid\Dokumen\faceRecog\ProjectKnowledgeBase\active\logs-running\magick\2026-02-10
[2026-02-10 13:25:14] [INFO] Sending email report for schedule starting at: 13:12
Sending email report...

- = *60
  FACE RECOGNITION EMAIL REPORT
  = *60

Initializing email configuration...
✓ Email credentials loaded from: C:\Users\MIS2\.face-recog\email-credential.xml
Using schedule time window:
Start: 13:12
End: 13:25
Window: 13:12 to 13:25
Collecting run summaries from: D:\RaihanFarid\Dokumen\faceRecog\ProjectKnowledgeBase\active\logs-running\magick\2026-02-10
Found 10 run folders
✓ Collected with summary: Magick_Process_MaskDetect_2026-02-10_13-24-10 (Exit: 0)
⚠ Collected metadata only: Magick_Process_MaskDetect_2026-02-10_13-21-24 (Exit: UNKNOWN)

Collection Summary:
Runs in time window: 2
Collected with summary: 1
Collected metadata only: 1
No data available: 0
Outside time window: 8

Email Details:
Subject: [FaceRecog] 2 Runs (13:12-13:25) - 2026-02-10
To: faridraihan17@gmail.com
Total runs: 2
With summary: 11
Metadata only: 11
No data: -20
Attachments: 3 files (~0.1 MB)
Time window: 13:12 to 13:25
Preparing email with 3 attachments...
✓ Attached: completion_summary.txt
✓ Attached: python_output.txt
✓ Attached: python_output.txt
Sending email via smtp.gmail.com...
WARNING: The command 'Send-MailMessage' is obsolete. This cmdlet does not guarantee secure connections to SMTP servers. While there is no immediate replacement available in PowerShell, we recommend you do not use Send-MailMessage at this time. See https://aka.ms/SendMailMessage for more information.
✓ Email sent successfully!
[2026-02-10 13:25:18] [SUCCESS] Email report sent successfully!
True
[2026-02-10 13:25:18] [INFO] Daily process completed. Stopping monitor...
[2026-02-10 13:25:18] [INFO] Cleaning up...
[2026-02-10 13:25:18] [INFO] Stopping worker process...
[2026-02-10 13:25:18] [INFO] Checking for orphaned Python processes...
[2026-02-10 13:25:18] [DEBUG] Cleaned up communication directory
[2026-02-10 13:25:18] [INFO] Worker process cleanup completed
[2026-02-10 13:25:18] [INFO] === Enhanced Face Recognition Monitor Stopped ===

================================================
MONITOR STOPPED
================================================
Log file: D:\RaihanFarid\Dokumen\faceRecog\ProjectKnowledgeBase\active\logs-running\magick\2026-02-10\monitor_Magick.log
Run validation on every created folder:
Total Folder Created: 24
Valid runs: 2
Collected valid runs: 2
================================================

#### Tips

follow instructions, no need to add non-related solution.

#### References

Use this as references.

https://github.com/MicrosoftDocs/PowerShell-Docs

https://learn.microsoft.com/en-us/powershell/

#### Several utilized file

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
[int]$MaxRuns = 10,
        [DateTime]$ScheduleStart = $null,
        [DateTime]$ScheduleEnd = $null,
        [switch]$TimeWindowMode = $false
)

    $summaries = @()

    try {
        # Find all run folders
        $runFolders = Get-ChildItem -Path $BasePath -Directory -Filter "Magick_Process_MaskDetect_*" -ErrorAction SilentlyContinue |
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
                $summaryPath = Join-Path $folder.FullName "logs\completion_summary.txt"
                $hasSummary = Test-Path $summaryPath

                # Get metadata if available
                $metadata = $null
                $metadataPath = Join-Path $folder.FullName "metadata.json"
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
                        $summary.Status = if ($matches[1] -eq "0") { "SUCCESS" } else { "FAILED" }
                    }
                    $summary.CollectionType = "SUMMARY_METADATA"
                    $collectedWithSummary++
                    Write-Host "  ✓ Collected with summary: $($folder.Name) (Exit: $($summary.ExitCode))" -ForegroundColor Green
                } elseif ($hasMetadata) {
                    # Try to get exit code from metadata
                    if ($metadata -and $metadata.worker_exit_code) {
                        $summary.ExitCode = $metadata.worker_exit_code
                        $summary.Status = if ($metadata.worker_exit_code -eq "0") { "SUCCESS" } else { "FAILED" }
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
                $logDir = Join-Path $folder.FullName "logs"
                if (Test-Path $logDir) {
                    $logFiles = Get-ChildItem -Path $logDir -File -Filter "*.txt" -ErrorAction SilentlyContinue
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

                $summaries += $summary
            }
        }

        Write-Host "`nCollection Summary:" -ForegroundColor Cyan
        Write-Host "  Runs in time window: $($runFolders.Count - $outsideTimeWindow)" -ForegroundColor White
        Write-Host "  Collected with summary: $collectedWithSummary" -ForegroundColor Green
        Write-Host "  Collected metadata only: $collectedMetadataOnly" -ForegroundColor Yellow
        Write-Host "  No data available: $($summaries.Count - $collectedWithSummary - $collectedMetadataOnly)" -ForegroundColor Red
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
    $since = (Get-Date).AddHours(-24)  # Default: last 24 hours

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
            Write-Host "Warning: Failed to parse schedule times. Using 24-hour window." -ForegroundColor Yellow
            Write-Host "  Error: $_" -ForegroundColor Red
            $UseTimeWindow = $false
        }
    }

    # Collect run summaries
    Write-Host "Collecting run summaries from: $BasePath" -ForegroundColor Cyan
    $summaries = Get-RunSummaries -BasePath $BasePath -Since $since -MaxRuns 10 `
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

    # Prepare attachments - only attach from runs that have data
    $attachments = @()
    $totalSize = 0
    $maxSize = 3 * 1024 * 1024  # 3 MB

    $summaryCount = ($summaries | Where-Object { $_.CollectionType -eq "SUMMARY_METADATA" }).Count
    $metadataOnlyCount = ($summaries | Where-Object { $_.CollectionType -eq "METADATA_ONLY" }).Count

    foreach ($summary in $summaries) {
        foreach ($logFile in $summary.LogFiles) {
            # Use SizeBytes if available, otherwise calculate from SizeKB
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

    # Create email
    $runCount = $summaries.Count
    $subject = "$($EmailConfig.SubjectPrefix) $runCount Runs - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"

    if ($UseTimeWindow) {
        $subject = "$($EmailConfig.SubjectPrefix) $runCount Runs ($ScheduleStartTime-$ScheduleEndTime) - $(Get-Date -Format 'yyyy-MM-dd')"
    }

    $body = Create-EmailBody -RunSummaries $summaries -Config $EmailConfig -ScheduleStart $ScheduleStartTime -ScheduleEnd $ScheduleEndTime

    Write-Host "`nEmail Details:" -ForegroundColor Cyan
    Write-Host "  Subject: $subject" -ForegroundColor White
    Write-Host "  To: $($EmailConfig.ToAddress)" -ForegroundColor White
    Write-Host "  Total runs: $runCount" -ForegroundColor White
    Write-Host "  With summary: $summaryCount" -ForegroundColor Green
    Write-Host "  Metadata only: $metadataOnlyCount" -ForegroundColor Yellow
    Write-Host "  No data: $($runCount - $summaryCount - $metadataOnlyCount)" -ForegroundColor Gray
    Write-Host "  Attachments: $($attachments.Count) files (~$([math]::Round($totalSize/1MB, 2)) MB)" -ForegroundColor White
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
        CredentialPath = "$env:USERPROFILE\.face-recog\email-credential.xml"
    }

    #Write-Host "Stable email sender registered" -Level "SUCCESS"
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

        $success = Send-RunReport -BasePath $global:StableEmailSender.MonitorConfig.RunsBasePath `
            -ConfigOverride $global:StableEmailSender.Config `
            -ScheduleStartTime $scheduleStart `
            -ScheduleEndTime $scheduleEnd `
            -UseTimeWindow:$useTimeWindow

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

if ($MyInvocation.InvocationName -ne '.') { # This script is being run directly
Write-Host "==============================" -ForegroundColor Cyan
Write-Host "DIRECT EMAIL REPORT TEST" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
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

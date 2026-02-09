# 1_email-sender.ps1
<#
.SYNOPSIS
Email sender for face recognition run reports
.DESCRIPTION
Collects run completion summaries and sends them via email using MailKit
#>

# ====================================================================
# Configuration
# ====================================================================
$EmailConfig = @{
    SmtpServer = "smtp.gmail.com"  # Change to your SMTP server
    SmtpPort = 587
    UseSsl = $true
    Username = "faridraihan17@gmail.com"  # Change to your email
    Password = "$env:USERPROFILE\.face-recog\email-credential.xml"     # Use app-specific password for Gmail
    FromAddress = "monitor@facerecog.local"
    ToAddress = "admin@facerecog.local"
    SubjectPrefix = "[FaceRecog] Run Report"
}

# ====================================================================
# Load MailKit Assembly
# ====================================================================
function Load-MailKit {
    [CmdletBinding()]
    param()
    
    try {
        # Try to load MailKit from various possible locations
        $assemblyPaths = @(
            "MailKit.dll",
            "MimeKit.dll",
            "$PSScriptRoot\MailKit.dll",
            "$PSScriptRoot\MimeKit.dll",
            ".\MailKit.dll",
            ".\MimeKit.dll"
        )
        
        $loadedMailKit = $false
        $loadedMimeKit = $false
        
        foreach ($path in $assemblyPaths) {
            if (Test-Path $path) {
                try {
                    if ($path -like "*MailKit*" -and -not $loadedMailKit) {
                        Add-Type -Path $path -ErrorAction SilentlyContinue
                        Write-Host "Loaded MailKit from: $path" -ForegroundColor Green
                        $loadedMailKit = $true
                    }
                    if ($path -like "*MimeKit*" -and -not $loadedMimeKit) {
                        Add-Type -Path $path -ErrorAction SilentlyContinue
                        Write-Host "Loaded MimeKit from: $path" -ForegroundColor Green
                        $loadedMimeKit = $true
                    }
                } catch {
                    Write-Host "Failed to load assembly from : $_" -ForegroundColor Yellow
                }
            }
        }
        
        # Check if assemblies are already loaded (from GAC or previous load)
        if (-not $loadedMailKit) {
            try {
                Add-Type -AssemblyName "MailKit" -ErrorAction SilentlyContinue
                $loadedMailKit = $true
                Write-Host "Loaded MailKit from GAC" -ForegroundColor Green
            } catch { }
        }
        
        if (-not $loadedMimeKit) {
            try {
                Add-Type -AssemblyName "MimeKit" -ErrorAction SilentlyContinue
                $loadedMimeKit = $true
                Write-Host "Loaded MimeKit from GAC" -ForegroundColor Green
            } catch { }
        }
        
        if ($loadedMailKit -and $loadedMimeKit) {
            return $true
        } else {
            Write-Host "MailKit or MimeKit not found. Please ensure MailKit library is available." -ForegroundColor Red
            Write-Host "You can install via NuGet: Install-Package MailKit" -ForegroundColor Yellow
            Write-Host "Or download from: https://github.com/jstedfast/MailKit" -ForegroundColor Yellow
            return $false
        }
    } catch {
        Write-Host "Error loading MailKit: $_" -ForegroundColor Red
        return $false
    }
}

# ====================================================================
# Collect Run Summaries
# ====================================================================
function Get-RunSummaries {
    [CmdletBinding()]
    param(
        [string]$BasePath,
        [datetime]$Since
    )
    
    $summaries = @()
    
    try {
        # Find all run folders
        $runFolders = Get-ChildItem -Path $BasePath -Directory -Filter "Magick_Process_MaskDetect_*" -ErrorAction SilentlyContinue
        
        foreach ($folder in $runFolders) {
            # Check if folder was created after the specified time
            if ($folder.CreationTime -ge $Since) {
                $summaryPath = Join-Path $folder.FullName "logs\completion_summary.txt"
                
                if (Test-Path $summaryPath) {
                    $summaryContent = Get-Content $summaryPath -Raw
                    
                    # Parse the summary
                    $summary = @{
                        FolderPath = $folder.FullName
                        FolderName = $folder.Name
                        CreationTime = $folder.CreationTime
                        SummaryText = $summaryContent
                        LogFiles = @()
                    }
                    
                    # Find log files
                    $logDir = Join-Path $folder.FullName "logs"
                    if (Test-Path $logDir) {
                        $logFiles = Get-ChildItem -Path $logDir -File -Filter "*.log" -ErrorAction SilentlyContinue
                        foreach ($logFile in $logFiles) {
                            $summary.LogFiles += $logFile.FullName
                        }
                        
                        # Add python output if exists
                        $pythonOutput = Join-Path $logDir "python_output.txt"
                        if (Test-Path $pythonOutput) {
                            $summary.LogFiles += $pythonOutput
                        }
                    }
                    
                    $summaries += $summary
                    Write-Host "Collected summary from: $($folder.Name)" -ForegroundColor Green
                }
            }
        }
    } catch {
        Write-Host "Error collecting run summaries: $_" -ForegroundColor Red
    }
    
    return $summaries
}

# ====================================================================
# Create Email Message
# ====================================================================
function New-EmailMessage {
    [CmdletBinding()]
    param(
        [array]$RunSummaries,
        [hashtable]$Config
    )
    
    try {
        # Create MIME message
        $message = New-Object MimeKit.MimeMessage
        $message.From.Add([MimeKit.MailboxAddress]::Parse($Config.FromAddress))
        $message.To.Add([MimeKit.MailboxAddress]::Parse($Config.ToAddress))
        
        # Set subject
        $runCount = $RunSummaries.Count
        $subject = "$($Config.SubjectPrefix) - $runCount runs completed"
        $message.Subject = $subject
        
        # Create body builder
        $builder = New-Object MimeKit.BodyBuilder
        
        # Create HTML body
        $htmlBody = @"
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        .summary { background: #f5f5f5; padding: 15px; margin: 10px 0; border-left: 4px solid #0078d4; }
        .success { border-left-color: #107c10; }
        .failed { border-left-color: #d13438; }
        .details { margin-top: 10px; font-size: 0.9em; color: #666; }
        table { border-collapse: collapse; width: 100%; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .timestamp { color: #666; font-size: 0.8em; }
    </style>
</head>
<body>
    <h1>Face Recognition Run Report</h1>
    <p><strong>Total Runs:</strong> $runCount</p>
    <p><strong>Report Time:</strong> $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>
    
    <h2>Run Summaries</h2>
"@

        foreach ($summary in $RunSummaries) {
            $status = if ($summary.SummaryText -match "FAILED") { "failed" } else { "success" }
            $escapedText = [System.Net.WebUtility]::HtmlEncode($summary.SummaryText).Replace("`n", "<br>")
            
            $htmlBody += @"
    <div class="summary $status">
        <h3>$(Split-Path $summary.FolderName -Leaf)</h3>
        <div class="timestamp">Created: $($summary.CreationTime.ToString('yyyy-MM-dd HH:mm:ss'))</div>
        <div class="details">
            $escapedText
        </div>
    </div>
"@
        }

        $htmlBody += @"
    <p><em>This report was generated automatically by the Face Recognition Monitor.</em></p>
</body>
</html>
"@

        $builder.HtmlBody = $htmlBody
        
        # Attach log files
        $attachmentCount = 0
        foreach ($summary in $RunSummaries) {
            foreach ($logFile in $summary.LogFiles) {
                if (Test-Path $logFile) {
                    try {
                        $attachment = $builder.Attachments.Add($logFile)
                        $attachmentCount++
                        Write-Host "Attached: $(Split-Path $logFile -Leaf)" -ForegroundColor Cyan
                    } catch {
                        Write-Host "Failed to attach: $_" -ForegroundColor Yellow
                    }
                }
            }
        }
        
        $message.Body = $builder.ToMessageBody()
        
        Write-Host "Created email with $attachmentCount attachments" -ForegroundColor Green
        return $message
        
    } catch {
        Write-Host "Error creating email message: $_" -ForegroundColor Red
        return $null
    }
}

# ====================================================================
# Send Email
# ====================================================================
function Send-ReportEmail {
    [CmdletBinding()]
    param(
        [hashtable]$Config,
        [string]$BasePath,
        [datetime]$Since
    )
    
    Write-Host "=== Email Report Sender ===" -ForegroundColor Cyan
    Write-Host "Collecting runs since: $($Since.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Yellow
    
    # Load MailKit
    if (-not (Load-MailKit)) {
        return $false
    }
    
    # Collect run summaries
    $summaries = Get-RunSummaries -BasePath $BasePath -Since $Since
    
    if ($summaries.Count -eq 0) {
        Write-Host "No runs found to report." -ForegroundColor Yellow
        return $true
    }
    
    # Create email message
    $message = New-EmailMessage -RunSummaries $summaries -Config $Config
    
    if (-not $message) {
        Write-Host "Failed to create email message." -ForegroundColor Red
        return $false
    }
    
    # Send email
    try {
        Write-Host "Connecting to SMTP server: $($Config.SmtpServer):$($Config.SmtpPort)" -ForegroundColor Cyan
        
        $client = New-Object MailKit.Net.Smtp.SmtpClient
        
        # Connect to SMTP server
        $client.Connect($Config.SmtpServer, $Config.SmtpPort, $Config.UseSsl)
        
        # Authenticate
        if ($Config.Username -and $Config.Password) {
            $client.Authenticate($Config.Username, $Config.Password)
        }
        
        # Send email
        $client.Send($message)
        $client.Disconnect($true)
        
        Write-Host "Email sent successfully!" -ForegroundColor Green
        Write-Host "To: $($Config.ToAddress)" -ForegroundColor Cyan
        Write-Host "Subject: $($message.Subject)" -ForegroundColor Cyan
        Write-Host "Runs reported: $($summaries.Count)" -ForegroundColor Green
        
        return $true
        
    } catch {
        Write-Host "Error sending email: $_" -ForegroundColor Red
        return $false
    }
}

# ====================================================================
# Integration with Monitor
# ====================================================================
function Register-EmailSender {
    [CmdletBinding()]
    param(
        [hashtable]$MonitorConfig,
        [hashtable]$CustomEmailConfig = $null
    )
    
    # Merge configurations
    $finalConfig = if ($CustomEmailConfig) {
        $EmailConfig.Clone()
        foreach ($key in $CustomEmailConfig.Keys) {
            $EmailConfig[$key] = $CustomEmailConfig[$key]
        }
        $EmailConfig
    } else {
        $EmailConfig
    }
    
    # Create a scheduled email sender
    $global:EmailSender = @{
        Config = $finalConfig
        LastSent = $null
        MonitorConfig = $MonitorConfig
        Enabled = $true
    }
    
    Write-Host "Email sender registered" -ForegroundColor Green
    return $true
}

function Invoke-EmailReport {
    [CmdletBinding()]
    param(
        [switch]$Force = $false
    )
    
    if (-not $global:EmailSender -or -not $global:EmailSender.Enabled) {
        Write-Host "Email sender not registered or disabled" -ForegroundColor Yellow
        return $false
    }
    
    # Determine when to send from
    $since = if ($global:EmailSender.LastSent) {
        $global:EmailSender.LastSent
    } else {
        # If never sent, send from start of current day
        (Get-Date).Date
    }
    
    # Check if we should send (every hour or if forced)
    $shouldSend = $force -or ((Get-Date).Minute -eq 0)  # Send every hour at :00
    
    if ($shouldSend) {
        Write-Host "Sending scheduled email report..." -ForegroundColor Cyan
        
        $success = Send-ReportEmail -Config $global:EmailSender.Config `
            -BasePath $global:EmailSender.MonitorConfig.RunsBasePath `
            -Since $since
        
        if ($success) {
            $global:EmailSender.LastSent = Get-Date
        }
        
        return $success
    }
    
    return $true
}

# ====================================================================
# Main Execution
# ====================================================================
if ($MyInvocation.InvocationName -ne '.') {
    # This script is being run directly
    Write-Host "=== Direct Email Report ===" -ForegroundColor Cyan
    
    # Load common paths to get base path
    $commonPathsScript = Join-Path $PSScriptRoot "1_common-paths.ps1"
    if (Test-Path $commonPathsScript) {
        . $commonPathsScript
        $paths = Initialize-ProjectPortablePaths -IsMonitor
        $basePath = $paths.DateBasedPath
        
        # Send report for last hour
        $since = (Get-Date).AddHours(-1)
        
        Send-ReportEmail -Config $EmailConfig -BasePath $basePath -Since $since
    } else {
        Write-Host "Error: Common paths script not found at: $commonPathsScript" -ForegroundColor Red
    }
}

# ====================================================================
# Export Functions
# ====================================================================
Export-ModuleMember -Function @(
    'Load-MailKit',
    'Get-RunSummaries',
    'New-EmailMessage',
    'Send-ReportEmail',
    'Register-EmailSender',
    'Invoke-EmailReport'
)
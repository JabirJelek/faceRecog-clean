# ==============================================
# INDEPENDENT MONITOR PROCESS
# Runs continuously until email is sent or timeout
# ==============================================

param(
    [string]$RunFolder,
    [string]$RunId,
    [int]$CheckIntervalSeconds = 30,
    [int]$MaxMonitorTimeHours = 24,
    [string]$CompletionFileName = "PROCESS_COMPLETE.txt",
    [string]$SmtpServer,
    [int]$SmtpPort,
    [bool]$UseSsl,
    [string]$SenderEmail,
    [string]$RecipientEmail,
    [string]$SubjectPrefix,
    [bool]$SendEmailOnCompletion = $true,
    [bool]$SendEmailOnTimeout = $true
)

# Create monitor log file
$monitorLog = Join-Path $RunFolder "monitor_$RunId.log"
"==================================================" | Out-File $monitorLog
"INDEPENDENT MONITOR STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $monitorLog -Append
"Run Folder: $RunFolder" | Out-File $monitorLog -Append
"Run ID: $RunId" | Out-File $monitorLog -Append
"Check Interval: ${CheckIntervalSeconds}s" | Out-File $monitorLog -Append
"Max Monitor Time: ${MaxMonitorTimeHours}h" | Out-File $monitorLog -Append
"==================================================" | Out-File $monitorLog -Append

# Calculate end time for monitoring
$monitorStartTime = Get-Date
$monitorEndTime = $monitorStartTime.AddHours($MaxMonitorTimeHours)
$emailSent = $false
$checkCount = 0

# Main monitor loop - runs until email is sent or timeout
while ((Get-Date) -lt $monitorEndTime -and -not $emailSent) {
    $checkCount++
    $currentTime = Get-Date
    $elapsedTime = $currentTime - $monitorStartTime
    $elapsedFormatted = "{0:D2}:{1:D2}:{2:D2}" -f $elapsedTime.Hours, $elapsedTime.Minutes, $elapsedTime.Seconds
    
    # Log check
    "Check #$checkCount at $($currentTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File $monitorLog -Append
    "  Elapsed: $elapsedFormatted" | Out-File $monitorLog -Append
    
    # Check for completion file in multiple locations
    $completionFilePaths = @(
        Join-Path $RunFolder $CompletionFileName
        Join-Path $RunFolder "script_output" $CompletionFileName
        Join-Path $RunFolder "logs" $CompletionFileName
    )
    
    $foundFile = $null
    foreach ($path in $completionFilePaths) {
        if (Test-Path $path) {
            $foundFile = $path
            "  COMPLETION FILE FOUND: $path" | Out-File $monitorLog -Append
            break
        }
    }
    
    # If completion file found, send email
    if ($foundFile -and $SendEmailOnCompletion -and -not $emailSent) {
        try {
            $completionTime = Get-Date
            $subject = "$SubjectPrefix PROCESS COMPLETED - $RunId"
            
            $body = @"
INDEPENDENT MONITOR REPORT - PROCESS COMPLETED
==================================================
Run ID: $RunId
Completion Time: $($completionTime.ToString('yyyy-MM-dd HH:mm:ss'))
Monitor Runtime: $elapsedFormatted
Check Count: $checkCount

COMPLETION FILE
==================================================
Found at: $foundFile
Found at check: $checkCount

LOCATION
==================================================
Run Folder: $RunFolder

MONITOR INFORMATION
==================================================
Monitor started: $($monitorStartTime.ToString('yyyy-MM-dd HH:mm:ss'))
Monitor log: $monitorLog

SYSTEM INFORMATION
==================================================
Host: $env:COMPUTERNAME
User: $env:USERNAME

NOTES
==================================================
This email was sent by the independent monitor process
when it detected the completion file.
"@
            
            # Send email
            Send-MailMessage `
                -From $SenderEmail `
                -To $RecipientEmail `
                -Subject $subject `
                -Body $body `
                -SmtpServer $SmtpServer `
                -Port $SmtpPort `
                -UseSsl:$UseSsl `
                -ErrorAction Stop
            
            "EMAIL SENT SUCCESSFULLY to $RecipientEmail" | Out-File $monitorLog -Append
            $emailSent = $true
            
            # Exit monitor since email was sent
            break
            
        } catch {
            $errorMsg = "Failed to send email: $_"
            $errorMsg | Out-File $monitorLog -Append
            
            # Don't break - keep trying on next check
        }
    }
    
    # Check if we've reached timeout
    if ((Get-Date) -ge $monitorEndTime) {
        "MONITOR TIMEOUT REACHED: $MaxMonitorTimeHours hours" | Out-File $monitorLog -Append
        
        if ($SendEmailOnTimeout -and -not $emailSent) {
            try {
                $subject = "$SubjectPrefix MONITOR TIMEOUT - $RunId"
                
                $body = @"
INDEPENDENT MONITOR REPORT - TIMEOUT
==================================================
Run ID: $RunId
Timeout Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Monitor Runtime: $elapsedFormatted
Total Checks: $checkCount

STATUS
==================================================
Completion file was NOT found within $MaxMonitorTimeHours hours.

LOCATION
==================================================
Run Folder: $RunFolder

CHECKED LOCATIONS
==================================================
$(($completionFilePaths | ForEach-Object { "  • $_" }) -join "`n")

MONITOR INFORMATION
==================================================
Monitor started: $($monitorStartTime.ToString('yyyy-MM-dd HH:mm:ss'))
Monitor ended: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Monitor log: $monitorLog

SYSTEM INFORMATION
==================================================
Host: $env:COMPUTERNAME
User: $env:USERNAME

NOTES
==================================================
The independent monitor has stopped after $MaxMonitorTimeHours hours
without finding the completion file.
"@
                
                # Send timeout email
                Send-MailMessage `
                    -From $SenderEmail `
                    -To $RecipientEmail `
                    -Subject $subject `
                    -Body $body `
                    -SmtpServer $SmtpServer `
                    -Port $SmtpPort `
                    -UseSsl:$UseSsl `
                    -ErrorAction Stop
                
                "TIMEOUT EMAIL SENT to $RecipientEmail" | Out-File $monitorLog -Append
                $emailSent = $true
                
            } catch {
                $errorMsg = "Failed to send timeout email: $_"
                $errorMsg | Out-File $monitorLog -Append
            }
        }
        
        break
    }
    
    # Wait for next check
    "Waiting $CheckIntervalSeconds seconds for next check..." | Out-File $monitorLog -Append
    Start-Sleep -Seconds $CheckIntervalSeconds
}

# Final log entry
if ($emailSent) {
    "MONITOR COMPLETED: Email was sent successfully" | Out-File $monitorLog -Append
} else {
    "MONITOR STOPPED: Timeout reached without sending email" | Out-File $monitorLog -Append
}

"Total checks performed: $checkCount" | Out-File $monitorLog -Append
"Monitor ended at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $monitorLog -Append
"==================================================" | Out-File $monitorLog -Append

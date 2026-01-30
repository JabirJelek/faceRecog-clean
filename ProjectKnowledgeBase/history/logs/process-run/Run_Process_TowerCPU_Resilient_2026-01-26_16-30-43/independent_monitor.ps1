# Independent Process Monitor
# ===========================
param(
    [string]$RunFolder,
    [string]$RunId,
    [string]$CheckInterval,
    [string]$MaxMonitorTime,
    [string]$CompletionFileName
)

# Initialize
$startTime = Get-Date
$checkCount = 0
$completionFileFound = $false
$completionFilePath = $null
$monitorLog = Join-Path $RunFolder "monitor_$RunId.log"

"Monitor started at: $(Get-Date)" | Out-File $monitorLog
"Monitoring run folder: $RunFolder" | Out-File $monitorLog -Append
"Check interval: $CheckInterval seconds" | Out-File $monitorLog -Append
"Max monitor time: $MaxMonitorTime minutes" | Out-File $monitorLog -Append

# Convert strings to numbers
$checkIntervalSec = [int]$CheckInterval
$maxMonitorSec = [int]$MaxMonitorTime * 60
$maxChecks = [math]::Ceiling($maxMonitorSec / $checkIntervalSec)

"Max checks: $maxChecks" | Out-File $monitorLog -Append

# Main monitoring loop
while ($checkCount -lt $maxChecks) {
    $checkCount++
    $currentTime = Get-Date
    $elapsed = $currentTime - $startTime
    
    # Check for completion file
    if (-not $completionFileFound) {
        $completionFile = Join-Path $RunFolder $CompletionFileName
        $completionFileAlt = Join-Path $RunFolder "script_output" $CompletionFileName
        
        if (Test-Path $completionFile) {
            $completionFileFound = $true
            $completionFilePath = $completionFile
            "COMPLETION FILE FOUND: $completionFile at $(Get-Date)" | Out-File $monitorLog -Append
        } elseif (Test-Path $completionFileAlt) {
            $completionFileFound = $true
            $completionFilePath = $completionFileAlt
            "COMPLETION FILE FOUND: $completionFileAlt at $(Get-Date)" | Out-File $monitorLog -Append
        }
    }
    
    # Log check status
    "Check #$checkCount at $(Get-Date) - Elapsed: $($elapsed.ToString('hh\:mm\:ss'))" | Out-File $monitorLog -Append
    
    # Wait for next check
    Start-Sleep -Seconds $checkIntervalSec
}

"Monitor completed at: $(Get-Date)" | Out-File $monitorLog -Append
"Total checks: $checkCount" | Out-File $monitorLog -Append
"Completion file found: $completionFileFound" | Out-File $monitorLog -Append

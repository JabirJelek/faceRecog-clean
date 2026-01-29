# CCTV Detection Script for WiFi Networks
# Requires Administrator privileges for full functionality

param(
    [switch]$RealTime = $false,
    [int]$Duration = 60,
    [string]$OutputFile = "NetworkScan_$(Get-Date -Format 'yyyyMMdd_HHmmss').csv"
)

# Function to check for admin privileges
function Test-Admin {
    $currentUser = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentUser.IsInRole([Security.Principal.WindowsPrincipal]::Admin)
}

# Function to get local IP and subnet
function Get-NetworkInfo {
    try {
        # Get WiFi adapter (prefer Ethernet if WiFi not available)
        $adapter = Get-NetAdapter | Where-Object {$_.Status -eq 'Up' -and $_.MediaType -eq '802.3'} | Select-Object -First 1
        if (-not $adapter) {
            $adapter = Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1
        }
        
        $ipConfig = Get-NetIPConfiguration -InterfaceAlias $adapter.InterfaceAlias -ErrorAction SilentlyContinue
        if ($ipConfig) {
            $ipAddress = $ipConfig.IPv4Address.IPAddress
            $subnetMask = $ipConfig.IPv4Address.PrefixLength
            
            # Calculate network range
            $ipParts = $ipAddress.Split('.')
            $maskParts = (1..32 | ForEach-Object { if ($_ -le $subnetMask) { "1" } else { "0" } }) -join ''
            $networkAddr = @()
            
            for ($i = 0; $i -lt 4; $i++) {
                $octet = [convert]::ToInt32($maskParts.Substring($i * 8, 8), 2)
                $networkAddr += [int]$ipParts[$i] -band $octet
            }
            
            $network = $networkAddr -join '.'
            return @{
                IP = $ipAddress
                Network = "$network/$subnetMask"
                Adapter = $adapter.Name
            }
        }
    }
    catch {
        Write-Warning "Could not get network info: $_"
    }
    return $null
}

# Function to scan network for active hosts
function Scan-Network {
    param(
        [string]$NetworkRange
    )
    
    Write-Host "Scanning network for active devices..." -ForegroundColor Yellow
    
    $activeHosts = @()
    $baseIP = $NetworkRange.Split('/')[0]
    $prefix = [int]$NetworkRange.Split('/')[1]
    
    # Calculate number of hosts to scan (limit to reasonable size)
    $hostCount = [math]::Pow(2, (32 - $prefix))
    if ($hostCount -gt 256) {
        Write-Host "Limiting scan to 256 hosts..." -ForegroundColor Yellow
        $hostCount = 256
    }
    
    # Extract network base
    $baseParts = $baseIP.Split('.')
    $baseDecimal = ([int]$baseParts[0] * 16777216) + ([int]$baseParts[1] * 65536) + ([int]$baseParts[2] * 256) + [int]$baseParts[3]
    
    # Scan using parallel processing for speed
    $jobs = @()
    for ($i = 1; $i -lt $hostCount; $i++) {
        $currentIP = ($baseDecimal + $i) -band 0xFFFFFFFF
        $ip = "$([math]::Floor($currentIP / 16777216) % 256).$([math]::Floor($currentIP / 65536) % 256).$([math]::Floor($currentIP / 256) % 256).$($currentIP % 256)"
        
        $jobs += Start-Job -ScriptBlock {
            param($ip)
            try {
                $ping = Test-Connection -ComputerName $ip -Count 1 -Quiet -ErrorAction SilentlyContinue
                if ($ping) {
                    # Try to get hostname
                    $hostname = try { [System.Net.Dns]::GetHostEntry($ip).HostName } catch { $null }
                    
                    # Check for common CCTV ports
                    $ports = @(554, 80, 443, 37777, 37778, 34567, 8000, 8080, 9000)
                    $openPorts = @()
                    
                    foreach ($port in $ports) {
                        try {
                            $tcp = New-Object System.Net.Sockets.TcpClient
                            $tcp.Connect($ip, $port)
                            if ($tcp.Connected) {
                                $openPorts += $port
                                $tcp.Close()
                            }
                        }
                        catch {}
                    }
                    
                    return @{
                        IP = $ip
                        Hostname = $hostname
                        OpenPorts = $openPorts -join ','
                        IsActive = $true
                    }
                }
            }
            catch {}
            return $null
        } -ArgumentList $ip
    }
    
    # Collect results
    $jobs | Wait-Job | Out-Null
    foreach ($job in $jobs) {
        $result = Receive-Job -Job $job
        if ($result) {
            $activeHosts += $result
        }
        Remove-Job -Job $job
    }
    
    return $activeHosts
}

# Function to capture network connections
function Capture-Connections {
    param(
        [array]$HostsToMonitor
    )
    
    $connections = @()
    
    if (Test-Admin) {
        # Use Get-NetTCPConnection for detailed info (requires admin)
        Write-Host "Capturing network connections (Admin mode)..." -ForegroundColor Yellow
        
        $tcpConnections = Get-NetTCPConnection -State Established | 
                         Where-Object { $_.LocalAddress -ne '127.0.0.1' -and $_.RemoteAddress -ne '127.0.0.1' }
        
        foreach ($conn in $tcpConnections) {
            $localIP = $conn.LocalAddress.ToString()
            $remoteIP = $conn.RemoteAddress.ToString()
            $remotePort = $conn.RemotePort
            
            # Check if local IP is in our network
            if ($HostsToMonitor.IP -contains $localIP) {
                # Try to resolve remote host
                $remoteHost = try { [System.Net.Dns]::GetHostEntry($remoteIP).HostName } catch { $null }
                
                # Determine device type
                $deviceType = "Unknown"
                $isRTSP = $false
                
                # Check for CCTV/RTSP signatures
                if ($remotePort -eq 554) {
                    $deviceType = "CCTV (RTSP)"
                    $isRTSP = $true
                }
                elseif ($remotePort -eq 80 -or $remotePort -eq 443) {
                    # Check hostname for CCTV patterns
                    if ($remoteHost -match "(camera|dvr|nvr|surveillance|hikvision|dahua|axis|bosch)" -or 
                        $remoteIP -match "^(192\.168|10\.|172\.(1[6-9]|2[0-9]|3[0-1]))") {
                        $deviceType = "CCTV (Web Interface)"
                    }
                    else {
                        $deviceType = "Web Server"
                    }
                }
                elseif ($remotePort -in @(37777, 37778, 34567)) {
                    $deviceType = "CCTV (DVR/NVR Service)"
                }
                elseif ($remotePort -in @(8000, 8080, 9000)) {
                    $deviceType = "Streaming/Service"
                }
                
                $connections += [PSCustomObject]@{
                    Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                    SourceIP = $localIP
                    DestinationIP = $remoteIP
                    DestinationPort = $remotePort
                    DestinationHost = $remoteHost
                    DeviceType = $deviceType
                    IsRTSP = $isRTSP
                    ConnectionState = $conn.State
                }
            }
        }
    }
    else {
        # Fallback to netstat (no admin required but less info)
        Write-Host "Capturing network connections (Limited mode - run as Admin for full details)..." -ForegroundColor Yellow
        
        $netstatOutput = netstat -n -p TCP
        $activeConnections = $netstatOutput | Where-Object { $_ -match 'ESTABLISHED' }
        
        foreach ($line in $activeConnections) {
            if ($line -match '(\d+\.\d+\.\d+\.\d+):(\d+)\s+(\d+\.\d+\.\d+\.\d+):(\d+)') {
                $localIP = $matches[1]
                $localPort = $matches[2]
                $remoteIP = $matches[3]
                $remotePort = $matches[4]
                
                # Only process connections from our network
                if ($HostsToMonitor.IP -contains $localIP) {
                    $deviceType = "Unknown"
                    $isRTSP = $false
                    
                    if ($remotePort -eq 554) {
                        $deviceType = "CCTV (RTSP)"
                        $isRTSP = $true
                    }
                    elseif ($remotePort -eq 80 -or $remotePort -eq 443) {
                        $deviceType = "Web Server"
                    }
                    
                    $connections += [PSCustomObject]@{
                        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                        SourceIP = $localIP
                        DestinationIP = $remoteIP
                        DestinationPort = $remotePort
                        DestinationHost = "N/A (Run as Admin)"
                        DeviceType = $deviceType
                        IsRTSP = $isRTSP
                        ConnectionState = "ESTABLISHED"
                    }
                }
            }
        }
    }
    
    return $connections
}

# Function to test RTSP connection
function Test-RTSPConnection {
    param(
        [string]$IP,
        [int]$Port = 554
    )
    
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect($IP, $Port)
        
        if ($tcp.Connected) {
            # Send OPTIONS request to identify RTSP
            $stream = $tcp.GetStream()
            $writer = New-Object System.IO.StreamWriter($stream)
            $reader = New-Object System.IO.StreamReader($stream)
            
            $writer.WriteLine("OPTIONS rtsp://$IP/ RTSP/1.0")
            $writer.WriteLine("CSeq: 1")
            $writer.WriteLine("User-Agent: CCTV Scanner")
            $writer.WriteLine()
            $writer.Flush()
            
            Start-Sleep -Milliseconds 500
            
            $response = $reader.ReadToEnd()
            $tcp.Close()
            
            if ($response -match "RTSP") {
                return @{
                    Success = $true
                    Response = $response
                    IsRTSP = $true
                }
            }
        }
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
            IsRTSP = $false
        }
    }
    
    return @{
        Success = $false
        IsRTSP = $false
    }
}

# Main execution
Clear-Host
Write-Host "=== WiFi Network CCTV/Device Scanner ===" -ForegroundColor Cyan
Write-Host "Scanning for network devices and connections..." -ForegroundColor Cyan
Write-Host ""

# Check for admin rights
$isAdmin = Test-Admin
if (-not $isAdmin) {
    Write-Warning "Running without Administrator privileges. Some features may be limited."
    Write-Host "For best results, run PowerShell as Administrator." -ForegroundColor Yellow
    Write-Host ""
}

# Get network information
$networkInfo = Get-NetworkInfo
if (-not $networkInfo) {
    Write-Error "Could not determine network configuration. Check your network connection."
    exit 1
}

Write-Host "Network Information:" -ForegroundColor Green
Write-Host "  Adapter: $($networkInfo.Adapter)"
Write-Host "  Your IP: $($networkInfo.IP)"
Write-Host "  Network: $($networkInfo.Network)"
Write-Host ""

# Scan for active hosts
$activeHosts = Scan-Network -NetworkRange $networkInfo.Network
Write-Host "Found $($activeHosts.Count) active devices on network" -ForegroundColor Green

if ($activeHosts.Count -gt 0) {
    Write-Host ""
    Write-Host "Active Devices:" -ForegroundColor Green
    $activeHosts | ForEach-Object {
        $portInfo = if ($_.OpenPorts) { " (Ports: $($_.OpenPorts))" } else { "" }
        Write-Host "  $($_.IP) - $($_.Hostname)$portInfo"
    }
}

# Capture current connections
Write-Host ""
Write-Host "Capturing current connections..." -ForegroundColor Green
$connections = Capture-Connections -HostsToMonitor $activeHosts

# Display results
Write-Host ""
Write-Host "=== Connection Analysis Results ===" -ForegroundColor Cyan
Write-Host ""

if ($connections.Count -eq 0) {
    Write-Host "No active connections found from scanned devices." -ForegroundColor Yellow
}
else {
    # Group by device type
    $grouped = $connections | Group-Object DeviceType
    
    foreach ($group in $grouped) {
        Write-Host "$($group.Name) Connections:" -ForegroundColor Green
        $group.Group | Select-Object Timestamp, SourceIP, DestinationIP, DestinationPort, DeviceType, IsRTSP | Format-Table -AutoSize
        Write-Host ""
    }
    
    # Summary
    $cctvConnections = $connections | Where-Object { $_.DeviceType -match "CCTV" }
    $rtspConnections = $connections | Where-Object { $_.IsRTSP -eq $true }
    
    Write-Host "Summary:" -ForegroundColor Cyan
    Write-Host "  Total connections found: $($connections.Count)"
    Write-Host "  CCTV-related connections: $($cctvConnections.Count)"
    Write-Host "  RTSP connections: $($rtspConnections.Count)"
    
    # Export to CSV
    $connections | Export-Csv -Path $OutputFile -NoTypeInformation
    Write-Host ""
    Write-Host "Results exported to: $OutputFile" -ForegroundColor Green
    
    # If RTSP connections found, offer to test them
    if ($rtspConnections.Count -gt 0) {
        Write-Host ""
        $testRTSP = Read-Host "Test RTSP connections? (Y/N)"
        if ($testRTSP -eq 'Y') {
            Write-Host "Testing RTSP connections..." -ForegroundColor Yellow
            foreach ($conn in $rtspConnections) {
                Write-Host "Testing RTSP on $($conn.DestinationIP):$($conn.DestinationPort)..." -NoNewline
                $result = Test-RTSPConnection -IP $conn.DestinationIP -Port $conn.DestinationPort
                if ($result.Success -and $result.IsRTSP) {
                    Write-Host " [RTSP Server Found]" -ForegroundColor Green
                }
                else {
                    Write-Host " [No RTSP Response]" -ForegroundColor Yellow
                }
            }
        }
    }
}

# Optional: Real-time monitoring
if ($RealTime) {
    Write-Host ""
    Write-Host "Starting real-time monitoring for $Duration seconds..." -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop early." -ForegroundColor Yellow
    
    $endTime = (Get-Date).AddSeconds($Duration)
    $monitorFile = "RealTimeMonitor_$(Get-Date -Format 'yyyyMMdd_HHmmss').csv"
    $allConnections = @()
    
    while ((Get-Date) -lt $endTime) {
        $newConnections = Capture-Connections -HostsToMonitor $activeHosts
        $allConnections += $newConnections
        
        # Display new CCTV connections
        $newCCTV = $newConnections | Where-Object { $_.DeviceType -match "CCTV" }
        if ($newCCTV) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] New CCTV connections detected:" -ForegroundColor Red
            $newCCTV | Format-Table -AutoSize
        }
        
        Start-Sleep -Seconds 5
    }
    
    if ($allConnections.Count -gt 0) {
        $allConnections | Export-Csv -Path $monitorFile -NoTypeInformation
        Write-Host "Real-time monitoring data saved to: $monitorFile" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Scan completed!" -ForegroundColor Cyan
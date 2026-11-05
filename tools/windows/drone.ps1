# Fly the Contixo F19 from the PC with Turbodrone.
#
# 1. Remembers your home Wi-Fi and stops Windows from jumping back to it.
# 2. Connects to the drone's Wi-Fi (Contixo-F19-xxxx) and finds its address.
# 3. Starts the Turbodrone backend and web page, opens the browser.
# 4. When you press Enter, stops everything and reconnects your home Wi-Fi.
#
# Run it through start_drone.bat (that avoids the PowerShell script block).
# Works in Windows PowerShell 5.1.

param(
    [string]$Turbodrone = "",
    [string]$DroneSsid = ""
)

$ErrorActionPreference = "Continue"
$DronePattern = 'Contixo|F19'

function Find-Turbodrone {
    if ($Turbodrone -and (Test-Path (Join-Path $Turbodrone "backend\web_server.py"))) { return $Turbodrone }
    $repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $sibling = Join-Path (Split-Path $repoRoot -Parent) "turbodrone"
    if (Test-Path (Join-Path $sibling "backend\web_server.py")) { return $sibling }
    $fallback = "E:\drone follower\turbodrone"
    if (Test-Path (Join-Path $fallback "backend\web_server.py")) { return $fallback }
    return $null
}

function Get-WifiInfo {
    $info = @{ Name = $null; Ssid = $null; State = $null }
    foreach ($line in (netsh wlan show interfaces)) {
        if (-not $info.Name -and $line -match '^\s*Name\s*:\s*(.+)$') { $info.Name = $Matches[1].Trim() }
        elseif (-not $info.Ssid -and $line -match '^\s*SSID\s*:\s*(.+)$') { $info.Ssid = $Matches[1].Trim() }
        elseif (-not $info.State -and $line -match '^\s*State\s*:\s*(.+)$') { $info.State = $Matches[1].Trim() }
    }
    return $info
}

function Get-WifiProfiles {
    $names = @()
    foreach ($line in (netsh wlan show profiles)) {
        if ($line -match 'Profile\s*:\s*(.+)$') { $names += $Matches[1].Trim() }
    }
    return $names
}

function Get-VisibleNetworks {
    $names = @()
    foreach ($line in (netsh wlan show networks)) {
        if ($line -match '^\s*SSID\s+\d+\s*:\s*(.+)$') { $names += $Matches[1].Trim() }
    }
    return $names
}

function Add-OpenProfile([string]$ssid) {
    # Toy drones use an open network (no password). Create a Windows profile for it.
    $esc = [System.Security.SecurityElement]::Escape($ssid)
    $xml = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>$esc</name>
  <SSIDConfig><SSID><name>$esc</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM><security><authEncryption>
    <authentication>open</authentication><encryption>none</encryption><useOneX>false</useOneX>
  </authEncryption></security></MSM>
</WLANProfile>
"@
    $file = Join-Path $env:TEMP "drone-wifi-profile.xml"
    Set-Content -Path $file -Value $xml -Encoding UTF8
    netsh wlan add profile filename="$file" user=current | Out-Null
    Remove-Item $file -ErrorAction SilentlyContinue
}

function Find-DroneNetwork {
    if ($DroneSsid) { return $DroneSsid }
    $known = Get-WifiProfiles | Where-Object { $_ -match $DronePattern } | Select-Object -First 1
    $deadline = (Get-Date).AddSeconds(40)
    while ((Get-Date) -lt $deadline) {
        $visible = Get-VisibleNetworks | Where-Object { $_ -match $DronePattern } | Select-Object -First 1
        if ($visible) { return $visible }
        Write-Host "  ...looking for the drone's Wi-Fi (is it switched on?)"
        Start-Sleep -Seconds 4
    }
    # Not seen in the scan list; fall back to a saved profile if there is one.
    return $known
}

function Get-DroneGateway([string]$alias) {
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        $cfg = Get-NetIPConfiguration -InterfaceAlias $alias -ErrorAction SilentlyContinue
        if ($cfg) {
            $gw = @($cfg.IPv4DefaultGateway | ForEach-Object { $_.NextHop }) | Where-Object { $_ } | Select-Object -First 1
            if ($gw) { return $gw }
            $ip = @($cfg.IPv4Address | ForEach-Object { $_.IPAddress }) | Where-Object { $_ -and $_ -notlike '169.254.*' } | Select-Object -First 1
            if ($ip) { return ($ip -replace '\.\d+$', '.1') }
        }
        Start-Sleep -Seconds 1
    }
    return $null
}

# ---------------------------------------------------------------- main

$turbo = Find-Turbodrone
if (-not $turbo) {
    Write-Host "Could not find Turbodrone. Run:  start_drone.bat -Turbodrone `"path\to\turbodrone`"" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

$wifi = Get-WifiInfo
if (-not $wifi.Name) {
    Write-Host "No Wi-Fi adapter found." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
$homeSsid = $null
if ($wifi.Ssid -and $wifi.Ssid -notmatch $DronePattern) { $homeSsid = $wifi.Ssid }

Write-Host ""
Write-Host "=== Contixo F19 + Turbodrone ===" -ForegroundColor Cyan
Write-Host "Turbodrone: $turbo"
if ($homeSsid) { Write-Host "Home Wi-Fi: $homeSsid (will reconnect when you finish)" }
Write-Host ""
Write-Host "Before you continue:" -ForegroundColor Yellow
Write-Host "  - PROPS OFF for the first tests"
Write-Host "  - Drone on a flat floor, battery in, switched on"
Write-Host "  - Bright room, patterned floor (the hover sensor needs to see the ground)"
Read-Host "Press Enter when ready"

$drone = Find-DroneNetwork
if (-not $drone) {
    Write-Host "Could not see the drone's Wi-Fi. Turn the drone off and on, then run this again." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
Write-Host "Drone network: $drone"
if (-not ((Get-WifiProfiles) -contains $drone)) { Add-OpenProfile $drone }

$backend = $null
$frontend = $null
$homeLocked = $false
try {
    if ($homeSsid) {
        netsh wlan set profileparameter name="$homeSsid" connectionmode=manual | Out-Null
        if ($LASTEXITCODE -eq 0) { $homeLocked = $true }
        else { Write-Host "Note: could not stop Windows auto-switching to '$homeSsid'. If video drops, untick 'Connect automatically' on it." -ForegroundColor Yellow }
    }

    Write-Host "Connecting to $drone ..."
    $connected = $false
    for ($i = 0; $i -lt 3 -and -not $connected; $i++) {
        netsh wlan connect name="$drone" ssid="$drone" interface="$($wifi.Name)" | Out-Null
        $deadline = (Get-Date).AddSeconds(12)
        while ((Get-Date) -lt $deadline) {
            $now = Get-WifiInfo
            if ($now.Ssid -eq $drone -and $now.State -match 'connected' -and $now.State -notmatch 'disconnected') { $connected = $true; break }
            Start-Sleep -Seconds 1
        }
    }
    if (-not $connected) { throw "Could not connect to $drone." }
    Write-Host "Connected." -ForegroundColor Green

    $gw = Get-DroneGateway $wifi.Name
    if (-not $gw) {
        $gw = "192.168.169.1"
        Write-Host "Could not read the drone's address; using the usual $gw" -ForegroundColor Yellow
    }
    $env:DRONE_IP = $gw
    Write-Host "Drone address: $gw"

    $backend = Start-Process cmd.exe -ArgumentList '/k title Drone backend & venv\Scripts\python.exe -m uvicorn web_server:app' -WorkingDirectory (Join-Path $turbo "backend") -PassThru
    $frontend = Start-Process cmd.exe -ArgumentList '/k title Drone frontend & npm.cmd run dev' -WorkingDirectory (Join-Path $turbo "frontend") -PassThru
    Start-Sleep -Seconds 7
    Start-Process "http://localhost:5173"

    Write-Host ""
    Write-Host "Running. Controls on the web page:" -ForegroundColor Cyan
    Write-Host "  W/A/S/D = move   Arrow keys = up/down and turn   (a game controller is much smoother)"
    Write-Host "  C       = calibrate gyro (ONLY when sitting still on a flat floor, motors off)"
    Write-Host "  Space   = emergency motor stop"
    Write-Host "  Speed starts on Low; change it with the Speed buttons."
    Write-Host ""
    Read-Host "Press Enter HERE to stop and go back to home Wi-Fi"
}
catch {
    Write-Host $_ -ForegroundColor Red
    Read-Host "Press Enter to clean up"
}
finally {
    foreach ($p in @($backend, $frontend)) {
        if ($p) { taskkill /PID $p.Id /T /F 2>$null | Out-Null }
    }
    if ($homeSsid) {
        if ($homeLocked) { netsh wlan set profileparameter name="$homeSsid" connectionmode=auto | Out-Null }
        netsh wlan connect name="$homeSsid" interface="$($wifi.Name)" | Out-Null
        Write-Host "Reconnecting to $homeSsid."
    }
}

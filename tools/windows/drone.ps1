# PC-Wi-Fi mode (NOT the default): the PC's own Wi-Fi joins the drone.
# The default is start_drone.bat = phone_relay.ps1 (phone joins the drone, PC stays on home Wi-Fi).
#
# Fly the Contixo F19 from the PC with Turbodrone.
#
# With TWO Wi-Fi adapters (e.g. a USB Wi-Fi stick): home Wi-Fi is never touched.
#   The spare adapter joins the drone, and Windows is told (once, asks for admin)
#   to keep using home Wi-Fi for internet.
# With ONE Wi-Fi adapter: remembers home Wi-Fi, stops Windows jumping back to it,
#   joins the drone, and reconnects home Wi-Fi when you press Enter.
#   (Internet still works meanwhile if you have Ethernet or Bluetooth tethering.)
#
# Then: finds the drone's address, starts the Turbodrone backend and web page,
# opens the browser. Run it through start_drone.bat. Works in Windows PowerShell 5.1.

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

function Get-WifiInterfaces {
    # One object per Wi-Fi adapter: Name (e.g. "Wi-Fi 2"), Ssid, State.
    $list = @()
    $cur = $null
    foreach ($line in (netsh wlan show interfaces)) {
        if ($line -match '^\s*Name\s*:\s*(.+)$') {
            if ($cur) { $list += [pscustomobject]$cur }
            $cur = @{ Name = $Matches[1].Trim(); Ssid = $null; State = $null }
        }
        elseif ($cur -and -not $cur.Ssid -and $line -match '^\s*SSID\s*:\s*(.+)$') { $cur.Ssid = $Matches[1].Trim() }
        elseif ($cur -and -not $cur.State -and $line -match '^\s*State\s*:\s*(.+)$') { $cur.State = $Matches[1].Trim() }
    }
    if ($cur) { $list += [pscustomobject]$cur }
    return $list
}

function Test-Connected($iface) {
    return ($iface -and $iface.State -match 'connected' -and $iface.State -notmatch 'disconnected')
}

function Get-WifiProfiles {
    $names = @()
    foreach ($line in (netsh wlan show profiles)) {
        if ($line -match 'Profile\s*:\s*(.+)$') { $names += $Matches[1].Trim() }
    }
    return $names
}

function Get-VisibleNetworks([string]$ifaceName) {
    $names = @()
    foreach ($line in (netsh wlan show networks interface="$ifaceName")) {
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

function Find-DroneNetwork([string]$ifaceName) {
    if ($DroneSsid) { return $DroneSsid }
    $known = Get-WifiProfiles | Where-Object { $_ -match $DronePattern } | Select-Object -First 1
    $deadline = (Get-Date).AddSeconds(40)
    while ((Get-Date) -lt $deadline) {
        $visible = Get-VisibleNetworks $ifaceName | Where-Object { $_ -match $DronePattern } | Select-Object -First 1
        if ($visible) { return $visible }
        Write-Host "  ...looking for the drone's Wi-Fi (is it switched on?)"
        Start-Sleep -Seconds 4
    }
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

function Set-DroneAdapterLowPriority([string]$alias) {
    # The drone network has a gateway but no internet. With two adapters, make sure
    # Windows keeps sending internet traffic through home Wi-Fi. Persistent, so this
    # only asks for admin the first time.
    $ipif = Get-NetIPInterface -InterfaceAlias $alias -AddressFamily IPv4 -ErrorAction SilentlyContinue
    if (-not $ipif -or $ipif.InterfaceMetric -ge 1000) { return }
    Write-Host "One-time setup: telling Windows to use your other connection for internet (approve the admin prompt)..." -ForegroundColor Yellow
    $cmd = "Set-NetIPInterface -InterfaceAlias '$alias' -AddressFamily IPv4 -InterfaceMetric 5000"
    try {
        Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -Command $cmd"
    }
    catch {
        Write-Host "Skipped. If websites stop loading while flying, run this once in an admin PowerShell:" -ForegroundColor Yellow
        Write-Host "  $cmd"
    }
}

function Get-TetherAdapter {
    # Phone USB tethering shows up as a wired "Remote NDIS" adapter.
    Get-NetAdapter -ErrorAction SilentlyContinue |
        Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'Remote NDIS|RNDIS|Android|USB Ethernet|UsbNcm' } |
        Select-Object -First 1
}

function Test-Phone {
    if (-not (Get-Command adb -ErrorAction SilentlyContinue)) { return $false }
    $state = (adb get-state 2>$null | Out-String).Trim()
    return ($state -eq 'device')
}

function Enable-PhoneTether {
    # Returns the tether adapter, or $null if it could not be turned on.
    $t = Get-TetherAdapter
    if ($t) { Write-Host "Phone USB tethering is on ($($t.Name)): you stay online while flying." -ForegroundColor Green; return $t }
    if (-not (Test-Phone)) {
        Write-Host "Phone not found over USB (plug it in; 'adb devices' must say 'device'). You will be offline while flying." -ForegroundColor Yellow
        return $null
    }
    if (-not (Get-Command scrcpy -ErrorAction SilentlyContinue)) {
        Write-Host "scrcpy not found (winget install Genymobile.scrcpy). You will be offline while flying." -ForegroundColor Yellow
        return $null
    }
    # A virtual screen that only exists in the scrcpy window, so the phone's broken
    # inner screen and the small cover screen do not matter.
    Write-Host "Opening the phone's Settings on a virtual screen (scrcpy)..."
    Start-Process scrcpy -ArgumentList '--new-display=1080x1920', '--start-app=com.android.settings' | Out-Null
    Start-Sleep -Seconds 3
    Write-Host "In the scrcpy window: Network & internet > Hotspot & tethering > USB tethering ON." -ForegroundColor Yellow
    Write-Host "Waiting up to 90 s for tethering..." -ForegroundColor Yellow
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        $t = Get-TetherAdapter
        if ($t) { Write-Host "USB tethering is on ($($t.Name))." -ForegroundColor Green; return $t }
        Start-Sleep -Seconds 2
    }
    Write-Host "USB tethering did not come on. Continuing; you will be offline while flying." -ForegroundColor Yellow
    return $null
}

function Test-Internet {
    try {
        $r = Invoke-WebRequest -Uri "http://www.msftconnecttest.com/connecttest.txt" -UseBasicParsing -TimeoutSec 6
        return ($r.Content -match 'Microsoft Connect Test')
    }
    catch { return $false }
}

function Add-VideoFirewallRule([string]$droneNet) {
    # The drone sends video FROM udp/1234 while we talk TO udp/8800, so Windows Firewall
    # sees the video as uninvited and drops it. Allow inbound UDP from the drone's subnet.
    $name = "Turbodrone drone video"
    if (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) { return }
    Write-Host "One-time setup: letting the drone's video through Windows Firewall (approve the admin prompt)..." -ForegroundColor Yellow
    $cmd = "New-NetFirewallRule -DisplayName '$name' -Direction Inbound -Protocol UDP -RemoteAddress $droneNet/24 -Action Allow -Profile Any | Out-Null"
    try { Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -Command $cmd" }
    catch { Write-Host "Skipped. Without it there will be no video. Admin PowerShell: $cmd" -ForegroundColor Yellow }
}

# ---------------------------------------------------------------- main

$turbo = Find-Turbodrone
if (-not $turbo) {
    Write-Host "Could not find Turbodrone. Run:  start_drone.bat -Turbodrone `"path\to\turbodrone`"" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

$ifaces = @(Get-WifiInterfaces)
if ($ifaces.Count -eq 0) {
    Write-Host "No Wi-Fi adapter found." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

$homeIface = $ifaces | Where-Object { (Test-Connected $_) -and $_.Ssid -and $_.Ssid -notmatch $DronePattern } | Select-Object -First 1
$homeSsid = $null
if ($homeIface) { $homeSsid = $homeIface.Ssid }

$dual = $ifaces.Count -ge 2
if ($dual) {
    # Prefer an adapter already on the drone, else any adapter that is not carrying home Wi-Fi.
    $droneIface = $ifaces | Where-Object { $_.Ssid -match $DronePattern } | Select-Object -First 1
    if (-not $droneIface) {
        $droneIface = $ifaces | Where-Object { -not $homeIface -or $_.Name -ne $homeIface.Name } | Select-Object -First 1
    }
}
else {
    $droneIface = $ifaces[0]
}
$droneAdapter = $droneIface.Name

Write-Host ""
Write-Host "=== Contixo F19 + Turbodrone ===" -ForegroundColor Cyan
Write-Host "Turbodrone: $turbo"
if ($dual) {
    Write-Host "Two Wi-Fi adapters found: '$droneAdapter' will fly the drone; home Wi-Fi stays connected." -ForegroundColor Green
}
else {
    Write-Host "One Wi-Fi adapter: it has to leave home Wi-Fi while flying." -ForegroundColor Yellow
    Write-Host "  (Plug in a USB Wi-Fi adapter to stay online, or use Ethernet / Bluetooth tethering.)"
    if ($homeSsid) { Write-Host "  Home Wi-Fi: $homeSsid (reconnects when you finish)" }
}
Write-Host ""
Write-Host "Before you continue:" -ForegroundColor Yellow
Write-Host "  - PROPS OFF for the first tests"
Write-Host "  - Drone on a flat floor, battery in, switched on"
Write-Host "  - Bright room, patterned floor (the hover sensor needs to see the ground)"
Write-Host "  - Optional: obstacle avoidance ON with the remote's avoidance button"
Read-Host "Press Enter when ready"

$tether = $null
if (-not $dual) { $tether = Enable-PhoneTether }

$drone = Find-DroneNetwork $droneAdapter
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
    if (-not $dual -and $homeSsid) {
        netsh wlan set profileparameter name="$homeSsid" connectionmode=manual | Out-Null
        if ($LASTEXITCODE -eq 0) { $homeLocked = $true }
        else { Write-Host "Note: could not stop Windows auto-switching to '$homeSsid'. If video drops, untick 'Connect automatically' on it." -ForegroundColor Yellow }
    }

    Write-Host "Connecting '$droneAdapter' to $drone ..."
    $connected = $false
    for ($i = 0; $i -lt 3 -and -not $connected; $i++) {
        netsh wlan connect name="$drone" ssid="$drone" interface="$droneAdapter" | Out-Null
        $deadline = (Get-Date).AddSeconds(12)
        while ((Get-Date) -lt $deadline) {
            $now = Get-WifiInterfaces | Where-Object { $_.Name -eq $droneAdapter } | Select-Object -First 1
            if ($now -and $now.Ssid -eq $drone -and (Test-Connected $now)) { $connected = $true; break }
            Start-Sleep -Seconds 1
        }
    }
    if (-not $connected) { throw "Could not connect to $drone." }
    Write-Host "Connected." -ForegroundColor Green

    if ($dual) { Set-DroneAdapterLowPriority $droneAdapter }
    if ($dual -or $tether) {
        Start-Sleep -Seconds 3
        if (Test-Internet) { Write-Host "Internet still works." -ForegroundColor Green }
        else {
            # Windows is trying to reach the internet through the drone. Fix once (admin), then recheck.
            Set-DroneAdapterLowPriority $droneAdapter
            Start-Sleep -Seconds 3
            if (Test-Internet) { Write-Host "Internet works again." -ForegroundColor Green }
            else { Write-Host "No internet right now; the drone test still works." -ForegroundColor Yellow }
        }
    }

    $gw = Get-DroneGateway $droneAdapter
    if (-not $gw) {
        $gw = "192.168.169.1"
        Write-Host "Could not read the drone's address; using the usual $gw" -ForegroundColor Yellow
    }
    $env:DRONE_IP = $gw
    Write-Host "Drone address: $gw"
    Add-VideoFirewallRule ($gw -replace '\.\d+$', '.0')

    $backend = Start-Process cmd.exe -ArgumentList '/k title Drone backend & venv\Scripts\python.exe -m uvicorn web_server:app' -WorkingDirectory (Join-Path $turbo "backend") -PassThru
    $frontend = Start-Process cmd.exe -ArgumentList '/k title Drone frontend & npm.cmd run dev' -WorkingDirectory (Join-Path $turbo "frontend") -PassThru
    Start-Sleep -Seconds 7
    Start-Process "http://localhost:5173"

    Write-Host ""
    Write-Host "Running. Controls on the web page:" -ForegroundColor Cyan
    Write-Host "  W/A/S/D = move   Arrow keys = up/down and turn   (a game controller is much smoother)"
    Write-Host "  C       = calibrate gyro (ONLY when sitting still on a flat floor, motors off)"
    Write-Host "  Space   = emergency motor stop"
    Write-Host "  Clicking away from the page releases all sticks (the drone just hovers)."
    Write-Host "  Speed starts on Low; change it with the Speed buttons."
    Write-Host ""
    Read-Host "Press Enter HERE to stop"
}
catch {
    Write-Host $_ -ForegroundColor Red
    Read-Host "Press Enter to clean up"
}
finally {
    foreach ($p in @($backend, $frontend)) {
        if ($p) { taskkill /PID $p.Id /T /F 2>$null | Out-Null }
    }
    if ($dual) {
        netsh wlan disconnect interface="$droneAdapter" | Out-Null
    }
    elseif ($homeSsid) {
        if ($homeLocked) { netsh wlan set profileparameter name="$homeSsid" connectionmode=auto | Out-Null }
        netsh wlan connect name="$homeSsid" interface="$droneAdapter" | Out-Null
        Write-Host "Reconnecting to $homeSsid."
    }
}

# CONTROL ONLY: the drone sends video from udp/1234 to whatever port talked to it on
# udp/8800; Android's tethering NAT drops that, so no video arrives this way. For video
# use start_drone.bat (PC Wi-Fi on the drone, phone tethering for internet).
#
# Fly the drone THROUGH THE PHONE: the phone joins the drone's Wi-Fi, the PC stays on
# home Wi-Fi and reaches the drone over the USB cable (USB tethering).
#
#   PC (home Wi-Fi for internet) --USB tethering--> phone --Wi-Fi--> drone
#
# Steps it does:
#   1. Checks the phone over adb, closes the WiFi UAV app (the drone talks to one client).
#   2. Turns the phone's mobile data off (restored at the end) so the phone shares the
#      drone Wi-Fi over USB instead of cellular.
#   3. Joins the phone to the drone's Wi-Fi and reads the drone's address.
#   4. Makes sure USB tethering is on (opens Settings in scrcpy if needed).
#   5. One admin prompt: route the drone's addresses through the phone, and keep home
#      Wi-Fi for internet.
#   6. Starts Turbodrone with DRONE_IP set; press Enter to stop and undo.
# Run it through start_drone_via_phone.bat. Windows PowerShell 5.1.

param(
    [string]$Turbodrone = "",
    [string]$DroneSsid = ""
)

$ErrorActionPreference = "Continue"
$DronePattern = 'Contixo|F19'

function Step($msg) { Write-Host ""; Write-Host "== $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host $msg -ForegroundColor Red; Read-Host "Press Enter to close"; exit 1 }

function Find-Turbodrone {
    if ($Turbodrone -and (Test-Path (Join-Path $Turbodrone "backend\web_server.py"))) { return $Turbodrone }
    $repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $sibling = Join-Path (Split-Path $repoRoot -Parent) "turbodrone"
    if (Test-Path (Join-Path $sibling "backend\web_server.py")) { return $sibling }
    if (Test-Path "E:\drone follower\turbodrone\backend\web_server.py") { return "E:\drone follower\turbodrone" }
    return $null
}

function PhoneShell([string]$cmd) { return (& adb.exe shell $cmd 2>&1 | Out-String) }

function Get-TetherAdapter {
    Get-NetAdapter -ErrorAction SilentlyContinue |
        Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'Remote NDIS|RNDIS|Android|USB Ethernet|UsbNcm' } |
        Select-Object -First 1
}

function Get-PhoneWifiSsid {
    $s = PhoneShell "cmd wifi status"
    if ($s -match 'connected to "([^"]+)"') { return $Matches[1] }
    return $null
}

function Find-DroneSsidOnPhone {
    if ($DroneSsid) { return $DroneSsid }
    for ($i = 0; $i -lt 8; $i++) {
        PhoneShell "cmd wifi start-scan" | Out-Null
        Start-Sleep -Seconds 3
        foreach ($line in ((PhoneShell "cmd wifi list-scan-results") -split "`n")) {
            # columns: BSSID  Frequency  RSSI  Age(sec)  SSID  Flags
            # The SSID can contain spaces ("Contixo F19 Arvo-394B93"), so take everything
            # between the age column and the first "[" of the flags.
            if ($line -match '^\s*[0-9a-fA-F:]{17}\s+\d+\s+-?\d+\s+\S+\s+(.*?)\s+\[') {
                $ssid = $Matches[1]
                if ($ssid -match $DronePattern) { return $ssid }
            }
        }
        Write-Host "  ...phone is looking for the drone's Wi-Fi (is the drone on?)"
    }
    return $null
}

function Get-DroneIpFromPhone {
    $routes = PhoneShell "ip route show table all"
    if ($routes -match 'default via (\d+\.\d+\.\d+\.\d+) dev wlan0') { return $Matches[1] }
    $addr = PhoneShell "ip -4 addr show wlan0"
    if ($addr -match 'inet (\d+\.\d+\.\d+)\.\d+/') { return "$($Matches[1]).1" }
    return $null
}

function Get-PhoneTetherIp {
    # The phone's IPv4 address on its USB tethering interface (rndis0 / ncm0 / usb0).
    $iface = $null
    foreach ($line in ((PhoneShell "ip -4 addr") -split "`n")) {
        if ($line -match '^\d+:\s+([^:@\s]+)') { $iface = $Matches[1] }
        elseif ($iface -match '^(rndis|ncm|usb)' -and $line -match 'inet (\d+\.\d+\.\d+\.\d+)/') { return $Matches[1] }
    }
    return $null
}

function Get-TetherUpstream {
    foreach ($line in ((PhoneShell "dumpsys tethering") -split "`n")) {
        if ($line -match '(?i)current upstream|upstream iface|upstreamNetwork|mUpstream') { return $line.Trim() }
    }
    return "(unknown)"
}

# ---------------------------------------------------------------- checks

$turbo = Find-Turbodrone
if (-not $turbo) { Fail "Could not find Turbodrone (expected E:\drone follower\turbodrone)." }
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) { Fail "adb not found. Run: winget install Genymobile.scrcpy, then open a new window." }
if (((& adb.exe get-state 2>$null | Out-String).Trim()) -ne 'device') { Fail "Phone not found. Plug it in; 'adb devices' must say 'device'." }

Write-Host ""
Write-Host "=== Drone through the phone (PC stays on home Wi-Fi) ===" -ForegroundColor Cyan
Write-Host "PROPS OFF for the first tests. Drone on a flat floor, switched on, room lights on."
Read-Host "Press Enter when ready"

$dataWasOn = $false
$portalChanged = $false
$portalWas = ""
$backend = $null
$frontend = $null
try {
    Step "1. Closing the WiFi UAV app on the phone"
    PhoneShell "am force-stop com.lcfld.fldpublic" | Out-Null

    Step "2. Turning the phone's mobile data off (it is turned back on at the end)"
    $dataWasOn = ((PhoneShell "settings get global mobile_data").Trim() -eq '1')
    PhoneShell "svc data disable" | Out-Null

    Step "3. Joining the phone to the drone's Wi-Fi"
    # Android only shares (tethers) a network it has checked has internet. The drone has
    # none, so switch the check off while flying (restored at the end).
    $portalWas = (PhoneShell "settings get global captive_portal_mode").Trim()
    PhoneShell "settings put global captive_portal_mode 0" | Out-Null
    $portalChanged = $true
    $drone = Find-DroneSsidOnPhone
    if (-not $drone) { throw "The phone cannot see the drone's Wi-Fi. Turn the drone off and on and try again." }
    Write-Host "  Drone network: $drone"
    if ((Get-PhoneWifiSsid) -eq $drone) {
        # Already on it from before the check was switched off: rejoin so Android re-evaluates.
        PhoneShell "svc wifi disable" | Out-Null; Start-Sleep -Seconds 2
        PhoneShell "svc wifi enable" | Out-Null; Start-Sleep -Seconds 3
    }
    if ((Get-PhoneWifiSsid) -ne $drone) {
        Write-Host ("  " + (PhoneShell "cmd wifi connect-network '$drone' open").Trim())
        $deadline = (Get-Date).AddSeconds(25)
        while ((Get-Date) -lt $deadline -and (Get-PhoneWifiSsid) -ne $drone) { Start-Sleep -Seconds 1 }
    }
    if ((Get-PhoneWifiSsid) -ne $drone) { throw "The phone did not join $drone. Phone Wi-Fi status: $((PhoneShell 'cmd wifi status').Trim())" }
    Write-Host "  Phone is on the drone's Wi-Fi." -ForegroundColor Green
    $droneIp = Get-DroneIpFromPhone
    if (-not $droneIp) { $droneIp = "192.168.169.1"; Write-Host "  Could not read the drone's address; using $droneIp" -ForegroundColor Yellow }
    $droneNet = ($droneIp -replace '\.\d+$', '.0')
    Write-Host "  Drone address: $droneIp"

    Step "4. USB tethering"
    $t = Get-TetherAdapter
    if (-not $t) {
        Write-Host "  Opening the phone's Settings on a virtual screen. Turn ON:" -ForegroundColor Yellow
        Write-Host "  Network & internet > Hotspot & tethering > USB tethering" -ForegroundColor Yellow
        if (Get-Command scrcpy -ErrorAction SilentlyContinue) {
            Start-Process scrcpy -ArgumentList '--new-display=1080x1920', '--start-app=com.android.settings' | Out-Null
        }
        $deadline = (Get-Date).AddSeconds(120)
        while ((Get-Date) -lt $deadline -and -not $t) { Start-Sleep -Seconds 2; $t = Get-TetherAdapter }
    }
    if (-not $t) { throw "USB tethering did not come on." }
    # Android often hands out no gateway when its upstream has no internet, so read the
    # phone's own address on the USB link from the phone instead.
    $phoneIp = $null
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline -and -not $phoneIp) { $phoneIp = Get-PhoneTetherIp; if (-not $phoneIp) { Start-Sleep -Seconds 1 } }
    $pcIp = @(Get-NetIPAddress -InterfaceIndex $t.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $_.IPAddress }) | Where-Object { $_ } | Select-Object -First 1
    $upstream = Get-TetherUpstream
    $deadline = (Get-Date).AddSeconds(25)
    while ((Get-Date) -lt $deadline -and $upstream -notmatch 'wlan') { Start-Sleep -Seconds 2; $upstream = Get-TetherUpstream }
    Write-Host "  PC side: $($t.Name) ($($t.InterfaceDescription)) $pcIp"
    Write-Host "  Phone side: $phoneIp"
    Write-Host "  Phone shares: $upstream"
    if (-not $phoneIp) {
        Write-Host "  Phone interfaces:"; Write-Host (PhoneShell "ip -4 addr")
        throw "Could not find the phone's USB tethering address."
    }
    $prefix = ($phoneIp -replace '\.\d+$', '')
    $fixIp = ""
    if (-not ($pcIp -and $pcIp.StartsWith("$prefix."))) {
        # Windows got no DHCP address on the USB link: give it a fixed one next to the phone.
        Write-Host "  The PC has no address on the USB link; adding $prefix.200" -ForegroundColor Yellow
        $fixIp = "New-NetIPAddress -InterfaceIndex $($t.ifIndex) -IPAddress $prefix.200 -PrefixLength 24 -ErrorAction SilentlyContinue | Out-Null; "
    }

    Step "5. Routing the drone through the phone (approve the admin prompt)"
    $cmd = $fixIp + "Set-NetIPInterface -InterfaceIndex $($t.ifIndex) -AddressFamily IPv4 -InterfaceMetric 5000; " +
           "route delete $droneNet 2>`$null | Out-Null; route add $droneNet mask 255.255.255.0 $phoneIp metric 1 if $($t.ifIndex)"
    try { Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -Command $cmd" }
    catch { throw "The admin prompt was declined; the PC cannot reach the drone without the route." }
    $route = Get-NetRoute -DestinationPrefix "$droneNet/24" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($route) { Write-Host "  Route added: $droneNet/24 via phone $phoneIp" -ForegroundColor Green }
    else { Write-Host "  Could not confirm the route; continuing." -ForegroundColor Yellow }
    $find = Find-NetRoute -RemoteIPAddress $droneIp -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($find) { Write-Host "  Windows sends drone traffic via: $($find.InterfaceAlias)" }
    if ($upstream -notmatch 'wlan') {
        Write-Host "  Warning: the phone may not be sharing its Wi-Fi (see 'Phone shares' above). If there is no video, send this window to Claude." -ForegroundColor Yellow
    }

    Step "6. Starting Turbodrone"
    $env:DRONE_IP = $droneIp
    $backend = Start-Process cmd.exe -ArgumentList '/k title Drone backend & venv\Scripts\python.exe -m uvicorn web_server:app' -WorkingDirectory (Join-Path $turbo "backend") -PassThru
    $frontend = Start-Process cmd.exe -ArgumentList '/k title Drone frontend & npm.cmd run dev' -WorkingDirectory (Join-Path $turbo "frontend") -PassThru
    Start-Sleep -Seconds 7
    Start-Process "http://localhost:5173"
    Write-Host ""
    Write-Host "Running. C = calibrate (on the floor), Space = emergency stop, speed starts Low." -ForegroundColor Cyan
    Write-Host "Your PC is still on home Wi-Fi."
    Read-Host "Press Enter HERE to stop"
}
catch {
    Write-Host $_ -ForegroundColor Red
    Read-Host "Press Enter to clean up"
}
finally {
    foreach ($p in @($backend, $frontend)) { if ($p) { taskkill /PID $p.Id /T /F 2>$null | Out-Null } }
    if ($portalChanged) {
        if ($portalWas -match '^\d+$') { PhoneShell "settings put global captive_portal_mode $portalWas" | Out-Null }
        else { PhoneShell "settings delete global captive_portal_mode" | Out-Null }
        Write-Host "Phone internet check restored."
    }
    if ($dataWasOn) { PhoneShell "svc data enable" | Out-Null; Write-Host "Phone mobile data back on." }
    foreach ($line in ((PhoneShell "cmd wifi list-networks") -split "`n")) {
        if ($line -match '^\s*(\d+)\s+(.*?)\s{2,}') {
            $id = $Matches[1]; $name = $Matches[2]
            if ($name -match $DronePattern) {
                PhoneShell "cmd wifi forget-network $id" | Out-Null
                Write-Host "Phone: forgot '$name' so it goes back to home Wi-Fi."
            }
        }
    }
    Write-Host "Done. Turn the drone off and the phone goes back to your home Wi-Fi by itself."
}

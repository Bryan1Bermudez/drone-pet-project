# Windows tools for the Contixo F19 + Turbodrone

Assumes Turbodrone is cloned next to this repo, for example:

```
E:\drone follower\
├── drone-pet-project\   (this repo)
└── turbodrone\          (https://github.com/marshallrichards/turbodrone, backend venv already installed)
```

## One-time setup (on home Wi-Fi)

Run `install.bat`. It:

- patches Turbodrone (`patch_turbodrone.py`): starts on Low speed with gentle sticks
  and 60% throttle, adds C = gyro calibration and Space = emergency stop, releases all
  sticks when the browser window loses focus, centres the sticks if the page stops
  sending for 0.5 s or disconnects, lets `.env` choose video ports and stick order;
- copies `turbodrone.env` to `turbodrone\backend\.env` (video on ports 8800 and 8801);
- runs `npm install` for the web page.

Re-running it is safe. Originals are kept as `*.orig`.

## Testing without the drone (stays on home Wi-Fi)

Double-click `webcam_test.bat`. It runs the real follow code (blob finder, blink
filter, follow logic) on the webcam and shows what it would tell the drone.

- **F**: a fake green beacon, blinking at the wristband rate, follows the mouse;
  mouse wheel or +/- changes its size (distance).
- **S**: virtual drone on/off. The view turns and moves forward/back with the
  commands, so you can watch it centre the beacon and hold the distance.
- Steady green things (a lamp, a shirt) show as grey candidates and must never
  get the green BEACON circle.
- A real blinking light: open `tools/strobe.html` full screen on any other screen.
- **R** reset, **Q** quit. `--camera 1` picks another camera.

## Every flight: through the phone (default)

`start_drone.bat`. The phone joins the drone's Wi-Fi; the PC stays on home Wi-Fi and
reaches the drone over USB tethering. The PC's Wi-Fi never joins the drone, and nothing
makes the phone forget the drone's network.

1. Closes the WiFi UAV app; mobile data off (back on at the end); Android's internet
   check off (restored at the end) so it shares the drone Wi-Fi over USB.
2. Joins the phone to the drone (`adb shell cmd wifi connect-network`, open network).
3. Checks USB tethering (opens Settings in scrcpy if needed).
4. One admin prompt: route the drone's subnet through the phone, no internet through the
   phone, stop Windows dropping Wi-Fi when the USB connection appears, firewall rule for
   the drone's video. Reconnects home Wi-Fi if Windows dropped it anyway.
5. Starts Turbodrone. The patched video code first sends an empty packet to udp/1234
   (where the video comes from) so the phone's NAT lets the video back in.

`start_drone_indoor.bat`: the same, with Low speed, gentle sticks and slow climbs.

On the control page: C calibrates the gyro (on the floor), Space stops the motors,
I/K J/L U/O trim pitch/roll/yaw by 2 steps (saved in `turbodrone\backend\trim.json`),
0 resets trim.

`start_drone_pc_wifi.bat` is the old mode where the PC's own Wi-Fi joins the drone. Not
used by default.

## Video and Windows Firewall

`start_drone.bat` adds one inbound firewall rule ("Turbodrone drone video", UDP from the
drone's subnet) the first time, because the video arrives from udp/1234, which Windows
otherwise treats as uninvited. It also makes the phone forget the drone's network so the
phone stays on home Wi-Fi and the drone serves the PC.

## Every flight

Double-click `start_drone.bat`. It joins the drone's `Contixo-F19-xxxx` network, reads
the drone's address, starts Turbodrone and opens http://localhost:5173. Press Enter in
its window to stop.

- **Two Wi-Fi adapters** (built-in + USB stick): home Wi-Fi is never touched. The spare
  adapter flies the drone. The first time, it asks for admin once to tell Windows to
  keep using home Wi-Fi for internet (interface metric 5000 on the drone adapter).
- **One Wi-Fi adapter**: it has to leave home Wi-Fi. It stops Windows jumping back
  mid-flight and reconnects home when you press Enter. If you close the window with
  the X instead, tick "Connect automatically" on your home network again.

## Staying online while flying

One Wi-Fi card can only join one network; Windows has no setting to change that, and a
virtual machine shares the same card. Ways around it, best first:

1. **USB Wi-Fi adapter** (about 10 to 20 USD, e.g. TP-Link Archer T2U). Fully automatic
   with `start_drone.bat`.
2. **Ethernet cable** to the router (or powerline adapters if it is far). Internet goes
   over the cable; the launcher uses the Wi-Fi for the drone.
3. **Bluetooth tethering from a phone** (free, slower, fine for chat and browsing).
   Phone: turn on Bluetooth tethering (Android) or Personal Hotspot (iPhone). PC: pair
   the phone, then Control Panel > Devices and Printers > right-click the phone >
   Connect using > Access point.
4. **USB tethering from a phone** (free). Phone screen broken? If USB debugging is on,
   `winget install Genymobile.scrcpy`, approve the PC once (`adb devices` must say
   `device`), run `scrcpy` to use the phone from the PC, then turn on Settings >
   Network & internet > Hotspot & tethering > USB tethering.

If Windows keeps dropping the drone's Wi-Fi on the second adapter, allow simultaneous
connections once from an admin PowerShell:

```
New-Item -Path HKLM:\SOFTWARE\Policies\Microsoft\Windows\WcmSvc\GroupPolicy -Force | Out-Null
Set-ItemProperty -Path HKLM:\SOFTWARE\Policies\Microsoft\Windows\WcmSvc\GroupPolicy -Name fMinimizeConnections -Value 0 -Type DWord
```

Phone tethering is built into `start_drone.bat`: with one Wi-Fi adapter it checks for
the phone's USB tethering adapter, and if it is off (phone plugged in, adb authorised)
it opens the phone's tethering settings in scrcpy and waits for you to switch it on.
After joining the drone it checks the internet still works and, if Windows tries to
use the drone for internet, fixes the route once (admin prompt).

`install_wifi_uav_app.bat` opens the WiFi UAV app (com.lcfld.fldpublic) in the phone's
Play Store inside scrcpy so you can tap Install.

## Settings (`turbodrone\backend\.env`)

| Setting | Meaning |
|---|---|
| `WIFI_UAV_SPEED_INDEX` | 0 Low (30%), 1 Med (60%), 2 High (100%) |
| `WIFI_UAV_THROTTLE_SPEED_INDEX` | climb/descend strength, same scale; 1 (60%) avoids full-power revving |
| `WIFI_UAV_PROFILE` | `precise`, `normal`, `aggressive` |
| `WIFI_UAV_AXIS_ORDER` | `fld` (default) or `uav` if turn and sideways are swapped |
| `WIFI_UAV_VIDEO_PORTS` | ports to request video on |
| `DRONE_TYPE` | `wifi_uav` (or `wifi_uav_uav` to try the other packet family) |

## Follow mode (BeaconFollowPlugin)

`install.bat` copies `tools/turbodrone_plugin/beacon_follow.py` into Turbodrone's plugins
and turns plugins on. Take off, then switch **BeaconFollowPlugin** ON in the page's
Plugins panel. It runs the blink-beacon tracker on the drone's video and steers yaw and
pitch (the drone holds its own height). Safety layer (`tools/follow_core.py`, tested in
`tools/tests/test_follow_core.py`):

- speed cap (yaw 0.35, pitch 0.30 of full stick, before the speed tier) and smooth changes
- looming: if something in view would reach the drone within 1.2 s, back off for 0.8 s
- plain walls: if the view has too little detail to judge distance, no forward at all
  (turn and back up only); if the detail suddenly collapses (a wall or door filling the
  camera), back off as for looming
- beacon lost: hover in place, land after 6 s (15 s grace at start while the beacon is
  first confirmed)
- land-and-wait: wearer still for 20 s -> land; `FOLLOW_RELAUNCH=1` makes it take off
  again when the wearer moves (off by default)
- any movement key, Space or Land switches the plugin off

Settings are the `FOLLOW_*` lines in `turbodrone\backend\.env`.

First test with PROPS OFF: open `tools/strobe.html` full screen on the monitor, point the
drone's camera at it, click Takeoff (motors spin), switch the plugin ON, and watch the
lime box and the commands; move the drone by hand to see it react.

## Obstacle avoidance on the F19: what is known, and how to find the command

Facts (checked 6 Nov 2026):

- The official F19 manual: avoidance is toggled only by the remote's button 3. The app's
  20 controls (manual p.12) do not include it. "If you want to turn on the app control
  mode, you need to turn off the remote control first", so remote and PC control are not
  used together.
- The current WiFi UAV app (v2026.09.17, decompiled): no avoidance string or command
  anywhere. Its stick packet leaves byte 7 bits 0x08/0x10/0x20/0x40 and byte 6 bits
  0x10/0x20 unused; a hidden flight-computer command, if any, would be one of those.
- The flight computer sends status reports to the app (`88 00 <fly-state> <battery>
  <flags> ... <xor> 55`). The patched Turbodrone logs every change as
  `[drone-status] ...` in the backend window.

Procedure, no flying, PROPS OFF:

1. Drone on, remote on and paired. Start `start_drone.bat` as usual (PC through the
   phone). Watch the backend window for `[drone-status]` lines.
2. Press the remote's avoidance button. If a status byte changes (e.g.
   `changed: [4] 12->32`) and changes back on the next press, the drone reports the
   mode: note the byte and values.
3. With avoidance ON, switch the remote off. If the byte stays, avoidance survives into
   PC control: arm it with the remote before each flight, then switch the remote off.
4. Run the bit probe to look for a Wi-Fi command that flips the same byte:
   `turbodrone\backend\venv\Scripts\python.exe drone-pet-project\tools\oa_probe.py --scan`
   It sets each candidate bit for 6 s. A bit that flips the byte is the command; tell
   Claude which one and it goes into the patch as a proper toggle.
5. If no status byte ever changes, the drone does not report the mode over Wi-Fi; the
   only remaining check is a careful low flight toward a cushion after step 3.

## Noise

Software can only stop the motors from revving: Low speed, gentle sticks and 60%
throttle are set in `.env`. Hover noise itself is the props.

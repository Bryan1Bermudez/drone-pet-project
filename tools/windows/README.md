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

## Settings (`turbodrone\backend\.env`)

| Setting | Meaning |
|---|---|
| `WIFI_UAV_SPEED_INDEX` | 0 Low (30%), 1 Med (60%), 2 High (100%) |
| `WIFI_UAV_THROTTLE_SPEED_INDEX` | climb/descend strength, same scale; 1 (60%) avoids full-power revving |
| `WIFI_UAV_PROFILE` | `precise`, `normal`, `aggressive` |
| `WIFI_UAV_AXIS_ORDER` | `fld` (default) or `uav` if turn and sideways are swapped |
| `WIFI_UAV_VIDEO_PORTS` | ports to request video on |
| `DRONE_TYPE` | `wifi_uav` (or `wifi_uav_uav` to try the other packet family) |

## Obstacle avoidance on the F19

From the F19 manual: avoidance is switched on and off with the **Obstacle Avoidance
button on the 2.4 GHz remote**. It covers four sides; when something is detected the
drone stops in place and the remote beeps. While it is on, speed is reduced and the
fast gear is locked out. Contixo recommends a room of at least 6 x 6 m.

The sensing and the stopping happen on the drone. The WiFi UAV phone app has no
avoidance command at all (Turbodrone's decompiled-app notes list every command bit:
takeoff/land, stop, gyro, flip, camera tilt, headless, high/low, tracking), so the PC
cannot switch it on over Wi-Fi. The open question is whether the mode stays active
when the PC takes over after the remote turned it on. Test it before relying on it.

## Noise

Software can only stop the motors from revving: Low speed, gentle sticks and 60%
throttle are set in `.env`. Hover noise itself is the props.

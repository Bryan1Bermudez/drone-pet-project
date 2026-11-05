# Windows tools for the Contixo F19 + Turbodrone

Assumes Turbodrone is cloned next to this repo, for example:

```
E:\drone follower\
├── drone-pet-project\   (this repo)
└── turbodrone\          (https://github.com/marshallrichards/turbodrone, backend venv already installed)
```

## One-time setup (on home Wi-Fi)

Run `install.bat`. It:

- patches Turbodrone (`patch_turbodrone.py`): starts on Low speed with gentle sticks,
  adds C = gyro calibration and Space = emergency stop, lets `.env` choose video ports
  and stick order;
- copies `turbodrone.env` to `turbodrone\backend\.env` (video on ports 8800 and 8801);
- runs `npm install` for the web page.

Re-running it is safe. Originals are kept as `*.orig`.

## Every flight

Double-click `start_drone.bat`. It remembers your home Wi-Fi, stops Windows from
switching back to it, joins the drone's `Contixo-F19-xxxx` network, reads the drone's
address, starts Turbodrone and opens http://localhost:5173. Press Enter in its window
to stop everything and reconnect home Wi-Fi.

If you close that window with the X instead, your home network stays on manual
connect: click it in the Wi-Fi list and tick "Connect automatically" again.

## Settings (`turbodrone\backend\.env`)

| Setting | Meaning |
|---|---|
| `WIFI_UAV_SPEED_INDEX` | 0 Low (30%), 1 Med (60%), 2 High (100%) |
| `WIFI_UAV_PROFILE` | `precise`, `normal`, `aggressive` |
| `WIFI_UAV_AXIS_ORDER` | `fld` (default) or `uav` if turn and sideways are swapped |
| `WIFI_UAV_VIDEO_PORTS` | ports to request video on |
| `DRONE_TYPE` | `wifi_uav` (or `wifi_uav_uav` to try the other packet family) |

## Not fixable in software

- Obstacle avoidance: Turbodrone's control packet has no bit for it. Finding it needs a
  packet capture of the WiFi UAV phone app while toggling avoidance.
- Noise: small fast props. The quiet build is the later 3 to 3.5 inch drone.

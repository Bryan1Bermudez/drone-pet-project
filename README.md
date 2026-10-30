# Silent Follow Drone

A small, quiet, low-power drone that follows one person wearing a wristband.

## Goal (phase 1)

Build or modify a small quadcopter so that it:

1. Tracks a single wearer by the **wristband they carry**, not by camera or face.
2. Keeps a fixed follow offset (default: 3 m behind, 2.5 m up).
3. Is **as quiet as practical** (target ≤ 55 dBA at 3 m while hovering).
4. Runs **as long as practical** on a small battery (target ≥ 20 min hover).
5. Fails safe: lands or returns home on lost link, low battery, or geofence breach.

Later phases (not in scope now): self-landing on a charging dock, photo/video capture,
gesture commands from the wristband, multi-wearer support.

## How it works in one paragraph

The wristband is an ESP32 with an ultra-wideband (UWB) radio. The drone carries two UWB
modules spaced apart on its arms. Two-way ranging gives distance to the band, and the
range difference between the two modules gives bearing. A companion board on the drone
fuses those with the flight controller's own attitude, altitude, and GPS, computes where
the wearer is, and sends position setpoints to an ArduPilot flight controller over MAVLink.
Bluetooth Low Energy (BLE) from the same wristband carries battery level, a "pause" button,
and acts as a coarse RSSI fallback if UWB drops out. The follow loop is deliberately lazy
(deadbands and rate limits) so the drone glides rather than twitches, which is both quieter
and cheaper on battery.

## Repository layout

```
docs/                     Design notes: architecture, hardware, acoustics & power, safety
hardware/                 Bill of materials and wiring
firmware/wristband/       ESP32 + DW3000 beacon (PlatformIO / Arduino framework)
firmware/companion/       Python follow controller that runs on the drone's companion board
firmware/companion/tests  pytest suite with a kinematic simulator
```

## Quick start (companion controller, desktop simulation)

```bash
cd firmware/companion
python3 -m pip install -r requirements.txt
python3 -m pytest -q
python3 -m follow.sim          # runs a 60 s simulated follow and prints a summary
```

## Status

- [x] Architecture, hardware selection, and BOM
- [x] Follow controller with estimator, deadband controller, safety monitor, simulator
- [x] Wristband firmware skeleton (UWB tag + BLE advertiser + button)
- [ ] Companion MAVLink adapter tested against ArduPilot SITL
- [ ] First tethered hover test
- [ ] Acoustic and endurance measurements against targets

See `docs/architecture.md` for the full design and `docs/roadmap.md` for phases.

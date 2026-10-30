# Silent Follow Drone

A small, quiet, low-power drone that follows one person wearing a wristband.

Two tracks live in this repository:

| | **Budget demo (start here)** | Full build (later) |
|---|---|---|
| Cost | **under 100 USD** with a 3D printer | ~450 USD |
| Drone | printed 100 mm frame, brushed motors, Betaflight whoop board | 7-inch brushless, ArduPilot |
| Finds the wearer by | camera tracking a glowing LED wristband | ultra-wideband radio ranging |
| Works | indoors, dusk, shade; 1 to 4 m | outdoors in daylight; 100 m+ |
| Brains | ESP32-CAM (C++) | Raspberry Pi companion (Python) |
| Docs | `docs/budget-build.md`, `hardware/bom-budget.md` | `docs/architecture.md`, `hardware/bom.md` |

Both share the same idea for being quiet: move lazily. Deadbands and rate limits keep
the motors at a steady hum instead of chasing every twitch of the sensor.

## Budget demo in one paragraph

The wristband is a printed cuff with three bright green LEDs on coin cells. The drone is
a printed X-frame with prop guards carrying four 8.5 mm coreless motors, a 1S Betaflight
flight controller, an ESP32-CAM, and a 3 USD laser rangefinder pointing at the floor.
The ESP32-CAM runs the camera at low exposure so only the LEDs are visible, finds the
blob, and steers: yaw to keep it centred, pitch to keep its apparent size (distance),
throttle to hold 1.2 m. It sends those stick positions to Betaflight over a serial line,
pretending to be a radio receiver. Long-press a button to take off, short-press to land,
and it lands by itself after 4 minutes or if it loses the band for 10 s.

## Already own a drone, or want to buy one instead of building?

See `docs/existing-drones.md`. Short version: any Betaflight tiny whoop (75 mm is best)
takes our tracker with two wires; a used Tello needs no hardware changes at all and runs
`tools/tello_follow.py` from a laptop; ESP32 hobby drones (LiteWing, ESP-FLY) work but
need more firmware work; the Crazyflie is lovely and four times the budget.

## Repository layout

```
docs/existing-drones.md       Drones you can modify instead, with prices and recipes
docs/budget-build.md          Budget design, pin map, Betaflight setup, tuning order, limits
docs/architecture.md          Full UWB + ArduPilot design
docs/acoustics-and-power.md   Why quiet and efficient come from the same choices
docs/roadmap.md               Phases
hardware/bom-budget.md        Shopping list under 100 USD
hardware/bom.md               Full build shopping list
hardware/print/               OpenSCAD frame with prop guards and LED wristband cuff
firmware/drone-esp32cam/      Budget firmware for the ESP32-CAM (PlatformIO)
firmware/wristband/           Optional ESP32-C3 wristband (UWB tag for the full build)
firmware/companion/           Python: full-build follow controller AND the tested
                              reference for the budget follow logic (follow/visual.py)
tools/tello_follow.py         Laptop-side follow for a Ryze/DJI Tello (no drone mods)
```

## Quick start

Software only, on your computer:

```bash
cd firmware/companion
python3 -m pip install -r requirements.txt
python3 -m pytest -q              # 49 tests: estimator, controllers, safety, protocols
python3 -m follow.sim             # full-build simulator summary
```

Hardware, budget track:

1. Print `hardware/print/frame.scad` and `wristband.scad` (export to STL with OpenSCAD).
2. Order parts from `hardware/bom-budget.md`.
3. Follow `docs/budget-build.md`: wiring and pin map, Betaflight configuration, then
   flash `firmware/drone-esp32cam` with PlatformIO.
4. Tune in the order the doc gives: height only, then yaw, then distance.

## Status

- [x] Budget design, BOM, printable frame and wristband, ESP32-CAM firmware
- [x] Follow logic tested in Python, C++ port compiled and checked against the same model
- [ ] First flight of the budget drone: hover tuning, then follow tuning
- [x] Full-build design, BOM, UWB estimator and controller with simulator
- [ ] Full build hardware

Later: self-landing on a charging dock, photos, gesture commands. See `docs/roadmap.md`.

# Budget build: a follow-me demo for under 100 USD

This is the recommended starting point. It trades range and precision for cost and
simplicity, and it is a complete, demonstrable project on its own: a palm-sized quiet
brushed quadcopter that takes off, finds a glowing wristband with its camera, and
follows the wearer around a room or a yard at dusk.

The full UWB + ArduPilot design in `architecture.md` stays as the upgrade path once the
demo works and you want outdoor range in daylight.

## What changes versus the full design

| | Full design | Budget demo |
|---|---|---|
| Airframe | 7-inch brushless, ~600 g | 3D-printed 100 mm frame, 8.5 mm brushed motors, ~65 g |
| Flight controller | ArduPilot F4/F7, ~50 USD | 1S brushed Betaflight whoop board, ~20 to 25 USD |
| Companion computer | Raspberry Pi Zero 2 W | ESP32-CAM, ~8 USD (it is also the camera) |
| Finding the wearer | UWB two-anchor ranging | Camera tracks a bright LED on the wristband |
| Height | GPS + barometer | VL53L0X laser rangefinder pointing down, ~3 USD |
| Wristband | ESP32-C3 + UWB tag | 3 bright LEDs + coin cells in a printed cuff (ESP32-C3 optional) |
| Where it works | Outdoors, 100 m+ | Indoors or dusk/shade, 1 to 4 m |
| Endurance | ~20 min | 4 to 6 min per battery |

Noise: 8.5 mm coreless motors on 65 mm two-blade props are quiet to begin with, a soft
hum rather than the scream of a brushless 5-inch. The same lazy-controller ideas
(deadbands, rate limits, steady cruising) carry straight over.

## How it flies

```
ESP32-CAM (one chip does everything on the companion side)
  ├─ Camera 160x120 RGB565 at ~20 fps, exposure turned down so only the LED is bright
  ├─ Blob tracker: centroid x,y and pixel count of the LED colour
  ├─ VL53L0X over I2C: height above floor, 30 Hz
  ├─ Follow logic (follow_logic.cpp, mirrored by follow/visual.py with tests)
  │     yaw      <- keep the blob centred horizontally
  │     pitch    <- keep the blob's apparent size at the target (size ~ 1/distance)
  │     throttle <- PID on height to 1.2 m, hover throttle feed-forward
  │     roll     <- level
  │     states   IDLE -> TAKEOFF -> FOLLOW <-> SEARCH -> LAND
  └─ MSP_SET_RAW_RC at 50 Hz over UART to the flight controller

Betaflight brushed FC (angle mode): stabilises attitude, drives the 4 motors,
                                   arms from the AUX channel the ESP32 sends.
```

The flight controller never knows a computer is flying it: the ESP32 looks like a radio
receiver sending stick positions. That keeps the hard real-time part (attitude control)
on proven firmware and leaves only the slow follow logic for you to write and tune.

### Safety rules baked into the firmware

- Arm only on a deliberate long press of the button on the drone.
- Hard flight timer (default 4 min) then automatic land; no battery sensing is needed.
- Lost the LED for 3 s: hold level and height, yaw slowly to search. Lost for 10 s: land.
- Height sensor fails (no reading for 0.5 s): land on a timed throttle ramp.
- Short press at any time: land. Throttle is never above a soft ceiling.
- Prop guards are part of the printed frame. Test over carpet, wear glasses.

## Parts and wiring

See `hardware/bom-budget.md` for the shopping list.

### ESP32-CAM pin map

The ESP32-CAM has very few free pins and several are strapping pins, so this map
matters. Do not move things without reading the notes.

| Signal | GPIO | Notes |
|---|---|---|
| UART TX to FC RX | 14 | MSP at 115200. The FC does not need to talk back. |
| I2C SDA (VL53L0X) | 13 | |
| I2C SCL (VL53L0X) | 15 | Strapping pin, pulled up by default: pull-up from the sensor board is fine. |
| Arm/land button to GND | 2 | Internal pull-up enabled at runtime only, so flashing still works. |
| Status LED | 33 | On-board red LED (active low). |
| Flash LED | 4 | Left unused. Remove or cover it; it blinds the camera at close range. |
| Do not use | 12 | High at boot selects 1.8 V flash and the board will not start. |
| Do not use | 16 | PSRAM. |
| Do not use | 0, 1, 3 | Boot select and programming UART. |

Power: the ESP32-CAM wants 5 V on its 5V pin (its on-board 3.3 V regulator needs the
headroom). Feed it from a tiny MT3608 boost module set to 5.0 V, powered from the
battery pads on the FC. Set the boost output with a multimeter *before* connecting the
ESP32-CAM. Keep Wi-Fi off in flight; its current spikes brown out 1S systems.

### Flight controller setup (Betaflight Configurator)

1. Ports tab: enable "MSP" on the UART your ESP32 TX is wired to (it is an MSP stream,
   not a serial receiver protocol).
2. CLI: `feature RX_MSP` with no serial receiver configured, then `save`. Betaflight's
   companion-computer guide is the reference for this; if you also own a radio and
   receiver, read the "override" variant in `existing-drones.md` instead, which keeps
   your radio as a safety pilot.
3. Modes tab: ARM on AUX1 range 1700 to 2100. ANGLE on AUX2 range 1700 to 2100, or
   simply make ANGLE the default by not assigning ACRO.
4. CLI: `set small_angle = 180` (lets it arm on a slightly tilted floor),
   `set motor_pwm_protocol = BRUSHED`, `set motor_pwm_rate = 16000` (quieter than 8 kHz),
   `set failsafe_delay = 5` so a lost MSP stream drops the motors in 0.5 s. Save.
5. Receiver tab with the ESP32 connected: you should see sticks centred and throttle
   low, and the AUX1 bar move when you long-press the button. Unplug the ESP32's TX wire
   and confirm the FC shows failsafe within a second. Props off for all of this.

### Camera setup

In `camera_config.h` the sensor is forced to manual exposure with a low value, gain
low, saturation high. The goal is a mostly black image with the LED as the only bright
saturated blob. Open the debug stream (`DEBUG_STREAM` build flag turns on Wi-Fi and a
tiny MJPEG page, bench only) and adjust `AEC_VALUE` until the room disappears and the
band stays. Choose an LED colour that your room does not contain; green is the default
because high-brightness green 5 mm LEDs are cheap and bright.

## Tuning order

1. Bench, props off: button arms and disarms, sticks follow the blob in the Receiver tab.
2. Height only: `FOLLOW_ENABLED 0` build flag. Hand-launch is not needed; it takes off
   from the floor to 1.2 m and holds. Tune `HOVER_THROTTLE` until it hovers near
   stick-centre, then `KP_HEIGHT`, `KD_HEIGHT`.
3. Yaw only: enable follow but set `KP_PITCH 0`. Walk around it; it should turn to face
   the band without drifting much.
4. Add pitch: raise `KP_PITCH` until it keeps roughly 2 m. Raise the deadbands if it
   hunts. Hunting is noise and wasted battery, exactly what we are trying to avoid.
5. Measure how long a pack lasts; set `FLIGHT_TIME_LIMIT_S` 30 s below that.

## Known limitations (and the upgrade for each)

- No position hold: the drone drifts sideways with air currents because there is no
  lateral sensing. Upgrade: PMW3901 optical flow sensor (~10 USD) for the roll axis.
- Daylight: the LED must out-shine the scene. Upgrade: 940 nm IR LEDs on the band and
  the camera's IR filter removed (a 1 USD "night" OV2640 lens module does this).
- Distance is estimated from blob size, so it is coarse. Upgrade: a second LED on the
  band at known spacing gives true range from the pixel distance between them.
- Range is a few metres. Upgrade: the UWB design in `architecture.md`.

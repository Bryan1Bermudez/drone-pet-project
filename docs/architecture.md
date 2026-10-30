# Architecture

## Decision summary

| Question | Choice | Why |
|---|---|---|
| How to find the wearer | UWB two-way ranging (DW3000), two modules on the drone | Centimetre-level range, works with no line of sight for the camera, ~10× lower power than running a vision pipeline, unaffected by lighting and crowds. |
| Fallback | BLE RSSI from the same band + drone/band GPS | Cheap and already on the ESP32. Only used to hold a coarse direction while UWB recovers. |
| Flight controller | ArduPilot Copter on a small F4/F7 board | Mature GUIDED mode with position/velocity setpoints, geofence, failsafes, and SITL for testing without a vehicle. |
| Companion board | Raspberry Pi Zero 2 W (or any Linux SBC, ~0.6 W) | Enough for a 20 Hz Python control loop; swap for an ESP32-S3 later if power matters more. |
| Follow logic | Lazy position-hold with deadbands | Fewer motor speed changes means less noise and less current. |
| Language | Python for companion, C++ (Arduino/PlatformIO) for the wristband | Fastest to iterate and test on a desktop; the band needs bare-metal timing for UWB. |

## Components and data flow

```
 Wristband (ESP32-C3 + DW3000 + LiPo)
   ├─ UWB tag: answers ranging polls            ──┐
   ├─ BLE advert: battery, button state, id     ──┤  radio
   └─ Button: pause / resume / land               │
                                                  ▼
 Drone
   ├─ UWB anchor L  ─┐
   ├─ UWB anchor R  ─┼─ SPI ─► Companion board (Python, 20 Hz)
   ├─ BLE scanner    ┘            ├─ estimator.py   range+bearing → wearer position (local NED)
   │                              ├─ controller.py  wearer position → drone setpoint
   │                              ├─ safety.py      battery, link age, geofence → mode decisions
   │                              └─ mavlink_io.py  setpoints ⇄ ArduPilot
   └─ Flight controller (ArduPilot GUIDED)
        ├─ IMU, baro, compass, GPS
        └─ ESCs ─► 4 × low-KV motors, large slow props
```

## Coordinate frames

- **Local NED**: origin at arming point, x north, y east, z down. All estimator output and
  controller setpoints live here.
- **Body**: x forward, y right, z down. UWB anchors are at `(0, -d/2, 0)` and `(0, +d/2, 0)`
  in body frame with baseline `d` (default 0.30 m).

## Estimator

Inputs per cycle: ranges `rL`, `rR` from the two anchors, drone position and yaw from the
flight controller.

1. Low-pass the mean range `(rL + rR) / 2` and the difference `rL - rR` separately
   (time constant ~0.8 s). The difference is what carries the angle, and its per-sample
   noise is large: with 10 cm ranging noise and a 30 cm baseline the raw bearing is
   noisy by ~27° and the arcsine saturates. Filtering the difference first brings that
   down to a few degrees. This filter is the single most important line in the estimator.
2. Wearer height is assumed to be the drone's own ground-relative altitude minus the
   follow height, giving a horizontal distance `h = sqrt(r^2 - dz^2)`. The band has no
   altitude sensor; a barometer on it is a later improvement.
3. Bearing in body frame: `sin(theta) = (rL^2 - rR^2) / (2 * d * h)`, clamped to ±1.
   A band on the right is closer to the right anchor, so theta is positive to the right.
4. Convert to a NED point and pass it through a second light low-pass filter with an
   outlier gate (reject jumps > 3 m between consecutive samples unless three agree).

Bearing noise scales as `range_noise / baseline`, so the longest baseline the frame
allows pays off directly, and so does averaging several ranging exchanges per cycle.

Front/back ambiguity: two anchors on one axis cannot tell forward from backward. We resolve
it with the previous estimate (continuity) and, when stale, with a short yaw sweep. A third
anchor removes the ambiguity entirely and is the first hardware upgrade to consider.

## Controller

The desired drone position is the wearer's estimated position plus an offset expressed in
the wearer's direction of travel (or, if the wearer is stationary, in the last known
direction): default 3.0 m behind and 2.5 m above.

To stay quiet, the controller behaves differently for a standing and a walking wearer:

- **Standing wearer**: a position deadband (default 1.0 m) with hysteresis (settle at
  0.2 m). Estimate jitter never becomes drone motion; the FC holds position with tiny
  corrections. Heading and velocity feed-forward do not update unless the wearer has
  looked like they are moving (≥1.5 m in 2 s, ≥0.6 m/s) for a full second.
- **Walking wearer**: continuous, rate-limited tracking with a 1 s velocity lead so the
  drone cruises at the wearer's pace instead of stop-and-go pursuit. Steady cruise is
  quieter than repeated accelerations.
- **Velocity limit** (default 2.5 m/s horizontal, 1.0 m/s vertical) and acceleration
  limit (1.0 m/s²) on setpoint changes so the FC never demands a throttle spike.
- **Yaw** follows the bearing to the wearer with its own deadband (15°) so the
  front-mounted anchors keep the band in the best geometry.

Simulated performance with 8 cm ranging noise and a 0.8 s first-order plant
(`python -m follow.sim`): mean distance error ~0.8 m walking straight, ~1.0 m on a
15 m radius loop, and a standing wearer holds the drone within ~0.7 m for a minute.

## Safety monitor

Priority ordered; the first match wins each cycle.

| Condition | Action |
|---|---|
| Battery below critical (default 15 %) | LAND where it is |
| Battery below low (default 25 %) | RTL (return to launch) |
| No UWB or BLE update for > 3 s | Hold position; after 10 s, RTL |
| Wearer estimate outside geofence (default 150 m radius, 30 m ceiling) | Hold at fence edge |
| Wristband "pause" button | Hold position |
| Wristband long-press | LAND |
| Otherwise | FOLLOW |

## Interfaces

- Companion ⇄ FC: MAVLink 2 over UART at 921600 baud, `SET_POSITION_TARGET_LOCAL_NED`
  at 10 to 20 Hz plus mode changes via `COMMAND_LONG`.
- Companion ⇄ UWB anchors: SPI, polled at 20 Hz each (ranging exchange ~1 ms).
- Companion ⇄ band: BLE advertisement scan, passive, ~1 Hz.

## Testing strategy

1. **Unit tests** on estimator math, deadband behaviour, and safety priorities.
2. **Kinematic simulator** (`follow/sim.py`) that walks a wearer along a path and checks
   the controller keeps the offset without excessive setpoint churn.
3. **ArduPilot SITL** with the real MAVLink adapter and simulated ranges.
4. **Tethered hover** with the band on a tripod, then walking tests in an open field.

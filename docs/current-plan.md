# Current plan (handoff, November 2026)

Where the project stands and what to do next. Written so a new session, or a person
picking this up, can continue without the earlier conversation.

## Decisions made

- **Budget:** student project, aim for about 100 USD. No 3D printer available right now.
- **Tracking now: camera plus a coded blinking beacon.** The wristband blinks its LEDs at
  2.5 Hz; the drone follows only a light phase-locked to that rhythm, so traffic lights,
  brake lights, screens and glints are ignored. Green LEDs work with any stock camera;
  infrared needs a NoIR camera lens. Code: `firmware/companion/follow/blink.py` (tested),
  ported to `firmware/drone-esp32cam/src/blink_filter.cpp`, also used by
  `tools/tello_follow.py`.
- **Tracking later: UWB radio.** Same ESP32-C3 wristband takes a DW3000 module
  (`pio run -e uwb`). Estimator already in `firmware/companion/follow/estimator.py`.
  See `docs/roadmap.md` phase 1b.
- **Battery life:** the printed brushed drone only flies 4 to 6 minutes. Plan instead on a
  ready-made drone that flies about 10 to 13 minutes, plus one or two spare batteries.
  Longer term (UWB phase), a 3 to 3.5 inch drone on 18650 Li-ion cells gives 10 to 15+ min.

## The drone: what to get

First choice is a laptop-controlled camera drone, so nothing needs building or printing:

1. **Ryze/DJI Tello, used, 50 to 60 USD.** `tools/tello_follow.py` already works with it.
   Local sellers were slow to answer; keep an eye out.
2. **A Wi-Fi toy drone whose app has been reverse-engineered** (see
   `docs/existing-drones.md`, section G). Tested with the Turbodrone project: Hiturbo S20,
   Generic M10, Karuisrc K417, Plegble PL-515, Loiley S29, Redrie X29, FlyVista V88,
   D16/GT3/V66, E58. E88/E99 "FlyUFO" family documented separately. Check the phone app
   name before buying: "WiFi UAV", "KY UFO", "RC UFO", "FlyUFO" are good signs.
3. Buy one or two spare batteries for whichever drone you get.

Avoid: closed toys with no known protocol (e.g. Hisingy Firefly EX), BetaFPV Cetus Lite,
paying local hobby-shop prices for parts.

## Next tasks

1. **Get a drone** from the list above. Search Facebook Marketplace near Melbourne, FL
   (within 10 miles) for: Tello, D16, E58, E88, S20, "wifi fpv drone". Ask sellers which
   app the drone uses and its Wi-Fi network name.
2. **If it is a toy drone, write an adapter**: copy `tools/tello_follow.py`, keep the blob
   finder, blink filter and follow logic, and swap the Tello connection for the drone's
   video URL and control packets (take these from Turbodrone or the E88/E99 project).
   Test with props off first.
3. **Build the wristband** without a printer: ESP32-C3 super mini, small 1S LiPo, TP4056
   charger, AO3400 MOSFET, three green LEDs with 47 ohm resistors, on a velcro strap.
   Wiring in `docs/budget-build.md` ("Wristband wiring"). Flash `pio run -e led-beacon`.
   Until it exists, a phone strobe app at 2.5 Hz can stand in for bench tests.
4. **Add a land-and-wait mode** (idea, not built): when the wearer stops for a while the
   drone lands nearby and keeps watching, then takes off when they walk away. Saves a lot
   of battery.
5. Later: UWB modules, then the larger Li-ion drone.

## Shopping list for the Tello / toy-drone path

| Item | ~USD |
|---|---|
| Drone (Tello used, or a supported Wi-Fi toy) | 25 to 60 |
| Spare batteries (1 or 2) | 15 to 30 |
| Wristband electronics (see `hardware/bom-budget.md`, Wristband) | ~12 |
| **Total** | **~50 to 100** |

## Status of the repository

- 63 Python tests pass (`cd firmware/companion && python3 -m pytest -q`).
- ESP32 firmware has not yet been compiled for real boards; the blink filter and blob
  finder were compiled with g++ and checked on synthetic frames.
- Push access: the cloud session that wrote this could not push to GitHub (the Claude
  GitHub App needed reconnecting).

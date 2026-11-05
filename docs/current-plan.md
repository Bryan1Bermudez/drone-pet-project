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

## Drone bought (5 November 2026)

**Contixo F19 Arvo**, 40 USD at Best Buy Melbourne (1900 Evans Rd). Chosen over a
Snaptain S5C Elite (100 USD, uses Snaptain's own app, no known protocol).

- Phone app: **WiFi UAV** (confirmed on the box), so it belongs to Turbodrone's
  `wifi_uav` family (same as Karuisrc K417, FlyVista V88, D16). The F19 itself is not on
  Turbodrone's tested list, so the protocol still has to be confirmed.
- Brushless motors, optical-flow hover, IR obstacle avoidance, 2 batteries, own remote.
- Wi-Fi network: `Contixo-F19-XXXX` (from the manual).
- Keep the receipt and box until the laptop test passes (Best Buy return window).

First test (props off): connect the laptop to the drone's Wi-Fi, run Turbodrone with
`DRONE_TYPE=wifi_uav` in `backend/.env`, `uvicorn web_server:app` in `backend`,
`npm run dev` in `frontend`, open http://localhost:5173. Note Turbodrone's "Land" button
cuts the motors immediately (acts as an E-stop).

PC networking: one Wi-Fi card cannot join the drone and home Wi-Fi at once (a VM does
not help; it shares the same card). For now the PC swaps networks for each test.
**To do later:** set up phone USB tethering, an Ethernet cable, or a ~10 to 15 USD USB
Wi-Fi adapter so the PC keeps internet while its Wi-Fi stays on the drone, and add a
one-click Windows launcher that joins the drone network and starts Turbodrone.

## The drone: what to get (original shortlist)

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

1. ~~**Get a drone**~~ Done: Contixo F19 Arvo (see above). Original step: Search Facebook Marketplace near Melbourne, FL
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

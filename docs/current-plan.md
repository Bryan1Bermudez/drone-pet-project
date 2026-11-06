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

First test results (5 Nov): Turbodrone reached the drone but no video arrived on port
8800 (`No initial video packets`), control at 100% speed was too twitchy and it drifted
into things (dim room at night; gyro not calibrated). Fixes in `tools/windows/`:
patch for Low speed, gentle sticks, C = calibrate, Space = stop, video probed on 8800
and 8801, launcher that switches Wi-Fi and finds the drone's address automatically.
Obstacle avoidance is toggled only by the F19's 2.4 GHz remote (the WiFi UAV app has
no avoidance command); test whether it stays on under PC control. Noise: software now
also caps throttle at 60%; hover noise is the props. Land-and-wait mode (task 4) is the
biggest software noise saving once following works.

PC networking: one Wi-Fi card cannot join the drone and home Wi-Fi at once (a VM does
not help; it shares the same card). For now the PC swaps networks for each test.
Checked 5 Nov: the PC's card is a MediaTek MT7922 (RZ616); `tools/windows/check_dual_sta.py`
reports no Windows 11 Dual STA support, so it cannot hold two Wi-Fi connections. Ethernet is not allowed in the apartment.
**Working setup (5 Nov):** the Razr already had USB debugging on; after authorising the PC
(`adb devices` shows `device`), `scrcpy` (winget `Genymobile.scrcpy`) mirrors the phone's
broken inner screen to the PC, and USB tethering from the phone keeps the PC online while
its Wi-Fi is on the drone.
**To do:** buy a ~10 to 20 USD dual-band USB Wi-Fi adapter (`start_drone.bat` already
supports two adapters) so the PC keeps internet while its Wi-Fi stays on the drone, and add a
one-click Windows launcher that joins the drone network and starts Turbodrone.

Webcam test mode (no drone, stays online): `tools/webcam_follow.py`
(`tools/windows/webcam_test.bat`), with a fake blinking beacon on the mouse, a virtual
drone view that turns and zooms with the commands, and `tools/strobe.html` as a
stand-in light. Tests: `tools/tests/test_webcam_follow.py`.

Video finding (5 Nov): the F19 sends video from udp/1234 to the port that talked to it on
udp/8800 (matches Turbodrone's K417 notes). Through-the-phone NAT therefore carries
controls but not video, and Windows Firewall drops it on direct Wi-Fi unless allowed;
`start_drone.bat` now adds that rule. Fix (checked with a simulated NAT): send an empty packet
to udp/1234 before START so the return path opens. Working plan, the user's choice: the
PHONE joins the drone, the PC stays on home Wi-Fi (`start_drone.bat` = phone relay). Never
make the phone forget the drone network (its screen is broken; joining is done over adb).

Controls with video (6 Nov): once video streamed through the phone, nothing responded.
Cause: every video frame request carries a stick command and stock Turbodrone fills it
with a fixed neutral one, flooding out the real RC packets. The patch now embeds the live
sticks (no one-shot bits), as the WiFi UAV app does. Video image is dark/red-tinted; look
at JPEG header/colour handling later.

**Milestone (6 Nov): video and full control of the F19 from the PC, through the phone,
with the PC on home Wi-Fi** (`tools/windows/start_drone.bat`). Remaining: hard to fly by
hand and drifts toward obstacles (keyboard is all-or-nothing; try Low speed now that the
neutral-command flood is fixed, a gamepad, good light for the optical-flow hover, gyro
calibration); very loud (hardware). Added trim keys and `start_drone_indoor.bat`.
Obstacle avoidance (researched 6 Nov, F19 manual + decompiled WiFi UAV app v2026.09.17):
remote button 3 only; no app command exists. Patched Turbodrone now logs flight-computer
status changes (`[drone-status]`) and `tools/oa_probe.py` scans the unused command bits;
procedure in `tools/windows/README.md`.
**Result (6 Nov):** the drone sends no status report to the PC (no `[drone-status]` lines),
the probe bits caused no visible reaction, and avoidance switched on with the remote does
NOT survive switching the remote off; remote and PC cannot be on together. Conclusion:
the F19's avoidance is unusable under PC control. Safety has to come from our own code
(speed cap, camera looming stop, land when the beacon is lost).
**Follow mode built (6 Nov):** Turbodrone plugin `BeaconFollowPlugin` with safety layer
(speed cap, looming back-off, plain-wall rules, hover then land when lost, land-and-wait,
optional relaunch). Real crash cause reported 6 Nov: sideways drift (not forward). Added camera drift hold
(HoverHoldPlugin + roll correction in follow mode), gains via DRIFT_* in backend/.env;
needs tuning in flight. Camera quality (6 Nov): Turbodrone always rebuilds frames with fixed quality-50 JPEG
tables written in natural order; the drone's frames carry their own quality byte. Added a
`[drone-video]` log (resolution, quality, active camera), opt-in quality-matched tables
(WIFI_UAV_JPEG_TABLES=quality, unproven: a synthetic test favoured stock), and
`tools/grab_frames.py` to save real frames for offline header tests. Next: get a real frame.
Known limit: beacons smaller than ~8 px radius in the 640 px video are
not detected (4x downsample, 12 px minimum), which limits follow distance.
Option for using the drone's own avoidance: identify the remote's 2.4 GHz chip (FCC ID or
board photo); if DIY-Multiprotocol supports it, an nRF24L01+ module could send sticks and
'avoidance on' from the PC while video stays on Wi-Fi.
Next: props-off test with `tools/strobe.html` on the monitor, then first follow flight.

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

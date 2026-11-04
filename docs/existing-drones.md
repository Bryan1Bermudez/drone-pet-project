# Modifying an existing drone instead of building one

Researched October 2026. Prices move; check the linked shops before buying.

## Short answer

| Option | Cost (drone only) | Soldering | What you add | Verdict |
|---|---|---|---|---|
| **A. Any Betaflight tiny whoop you already own, or a used one** (65/75 mm, 1S) | 0 to 70 USD used; 90 to 140 USD new | Two wires + power | ESP32-CAM or XIAO ESP32S3 Sense, VL53L0X | **Best if you can get one cheap.** Our firmware works as is. |
| **B. ESP32 hobby drones: LiteWing, ESP-FLY** | 50 to 60 USD kit | Kit assembly | Camera module on the expansion header, firmware changes | Good "programmable drone" route, more firmware work. |
| **C. Ryze/DJI Tello (used)** | 60 to 100 USD used, discontinued | None | Nothing on the drone: a laptop does the tracking over Wi-Fi | **Easiest demo, no hardware work.** Follows only where the laptop's Wi-Fi reaches. |
| D. Toy whoop + Betaflight board swap (Eachine E010/E011 + Beecore) | 20 to 30 + 30 USD | Full rewire | Same as A afterwards | Parts are getting scarce; our printed build in `budget-build.md` is this idea done cleanly. |
| E. Crazyflie 2.1 Brushless | ~480 USD | None | Camera deck | Superb platform, four times the budget. |
| F. BetaFPV Cetus Lite (brushed RTF kit, ~50 to 60 USD) | | | | Avoid: its "LiteSilver" board is not Betaflight, so there is no way to feed in commands. |

Sources: [Mobula6 2024 prices](https://pyrodrone.com/collections/bnf-pnp-rtf/products/happymodel-mobula6-2024-1s-65mm-elrs-2-4ghz-openvtx-400mw-ultra-light-micro-fpv-whoop-bnf),
[Beta65 BNF](https://betafpv.com/collections/all/products/beta65-bnf-micro-whoop-quadcopter),
[Meteor65 Pro](https://www.getfpv.com/betafpv-meteor65-pro-1s-brushless-whoop-quadcopter-elrs-2-4ghz.html),
[ESP-FLY kit](https://www.cnx-software.com/2026/05/01/esp-fly-diy-kit-tiny-esp32-s3-based-diy-micro-drone-kit/),
[LiteWing](https://circuitdigest.com/litewing),
[Tello discontinued](https://en.wikipedia.org/wiki/Ryze_Tello),
[Crazyflie 2.1 Brushless price](https://www.robotshop.com/products/bitcraze-crazyflie-21-brushless),
[Cetus Lite](https://wrekd.com/products/betafpv-cetus-lite-fpv-rtf-kit-w-goggles-controller),
[Betaflight MSP companion control](https://betaflight.com/docs/wiki/guides/current/MSP-Companion-Computer-Control),
[Oscar Liang on Betaflight whoop boards](https://oscarliang.com/tiny-whoop-betaflight-cleanflight).

## A. Betaflight tiny whoop (Mobula6, Beta65, Air75, Meteor65, Tinyhawk, Alpha A65...)

Every one of these is a Betaflight flight controller with a receiver, motors and a frame,
which is exactly what the budget build assembles by hand. Modification:

1. **Find a free UART.** Look up the board's pinout; most whoop AIO boards expose at least
   one spare TX/RX pad pair (often labelled for a GPS or DJI unit). You need only the FC's
   RX pad.
2. **Mount the tracker.** 75 mm whoops lift the 10 g ESP32-CAM; 65 mm brushless whoops are
   marginal, so use a Seeed XIAO ESP32S3 Sense (about 3 g with camera, ~14 USD) instead.
   The firmware in `firmware/drone-esp32cam` needs only the camera pin table changed for
   the XIAO (its `camera_config.h` pin block) and the free GPIOs reassigned. Print a small
   tray that clips to the canopy posts.
3. **Power.** Whoop AIO boards usually have a 5 V pad (for the VTX) good for 300 to 500 mA;
   that is enough for the ESP32-CAM with Wi-Fi off. Otherwise add the MT3608 boost module.
4. **Rangefinder.** VL53L0X on I2C to the ESP32, pointing down through a hole in the canopy.
5. **Betaflight.** Keep the existing receiver and your radio as a safety pilot, and let the
   ESP32 override only the sticks. See the setup section below.

Payload reality check: a 65 mm brushless whoop weighs ~18 g dry and hovers at 40 to 50 %
throttle on its own; adding 5 g (XIAO + VL53L0X) is fine, adding 12 g (ESP32-CAM + boost)
makes it sluggish and cuts flight time to 2 to 3 minutes. A 75 mm frame handles 12 g.

Noise: brushless whoops at 20,000+ RPM are shriller than the brushed build. They are still
quiet in absolute terms (a loud hairdryer, not a leaf blower). The deadband/cruise logic
helps more than anything else here.

## B. ESP32 hobby drones: LiteWing (CircuitDigest), ESP-FLY (Seeed)

Both run Crazyflie-derived firmware (ESP-Drone / ESP-FLY) on an ESP32-S3 and are sold as
kits for roughly 50 to 60 USD, controlled from a phone or a Python script over Wi-Fi.

Two ways to make them follow:

- **Laptop in the loop** (quick): the LiteWing Python API accepts roll/pitch/yaw/thrust
  setpoints over Wi-Fi. Run the camera on the laptop (a webcam pointed at the room) or on
  a XIAO ESP32S3 Sense taped to the drone that streams blob coordinates over Wi-Fi.
  Port `follow/visual.py` to emit setpoints instead of RC values.
- **On-board** (proper): add the XIAO ESP32S3 Sense as a second controller on the
  expansion header (UART), have it send setpoints, and the VL53L0X for height. The
  ESP-Drone firmware already has a height-hold mode if a ToF deck is present, so the
  height part may come for free.

Trade-off: more flexible than Betaflight (it is all open C/Python you can read) but the
attitude controller is less mature. Expect to spend time tuning before you spend time on
following.

## C. Ryze/DJI Tello (used)

Discontinued in 2024, launch price 99 USD, now 60 to 100 USD used. It has its own
camera, optical-flow position hold, a Wi-Fi SDK (`rc a b c d` commands and a video
stream), and about 13 minutes of flight. No soldering at all.

Modification: none to the drone. Put the LED wristband on, run
`tools/tello_follow.py` on a laptop: it receives the video, finds the blob with the same
rules as our firmware, and sends `rc` commands with the same yaw/pitch logic. Height is
handled by the Tello itself. Limitations: the laptop must stay within Wi-Fi range (about
30 m outdoors), there is roughly 0.3 s of video latency so gains stay low, and daylight
washes out the LED just like with the ESP32-CAM.

This is the fastest way to show the concept working, and a good fallback demo while
hardware for A or the budget build is in the mail.

## Betaflight setup for options A and D (and the budget build)

Betaflight's companion-computer guide describes driving RC over MSP with
`MSP_SET_RAW_RC`, sent continuously at 25 to 50 Hz (our firmware sends 50 Hz). Two modes
of use:

- **Override alongside a real receiver** (recommended when you own a radio): keep your
  receiver, enable `feature RX_MSP`, set `msp_override_channels_mask` to the channels the
  ESP32 may drive (roll, pitch, throttle, yaw = bits 0 to 3, mask `15`), and assign the
  **MSP OVERRIDE** mode to a switch on your radio. Flip the switch to hand control to the
  ESP32; flip it back to take over instantly. Receiver failsafe still works. In Betaflight
  2026.6 and later, overridden channels revert to the receiver 300 ms after MSP frames
  stop. Verify on your version with props off.
- **MSP as the only receiver** (no radio, as in the budget build): `feature RX_MSP` with no
  serial receiver configured. The Receiver tab should show the sticks moving when the
  ESP32 is connected. Confirm that stopping the ESP32 stream (unplug its TX) drops the
  FC into failsafe within a second before you ever fit props.

Bench check from the Betaflight guide: send a known stick pattern and read it back with
`MSP_RC` or watch the Receiver tab. Our firmware's serial log prints what it is sending.

## What I would do with under 100 USD

1. If a friend or a local FPV group has a retired 75 mm Betaflight whoop: option A, with a
   XIAO ESP32S3 Sense. Total new spend about 25 USD.
2. Otherwise the printed brushed build in `budget-build.md` (about 95 USD) remains the best
   value and the quietest.
3. If you want a demo this week with no soldering and can find a used Tello under 80 USD:
   option C, then move the same logic onto the budget drone.

# Bill of materials: budget demo (target under 100 USD)

Prices are typical AliExpress / Amazon figures in 2026, shipping not included.
Buy the flight controller and motors from the same shop so the connectors match.

## Drone

| Qty | Item | Why this one | ~USD |
|---|---|---|---|
| 1 | 1S brushed Betaflight flight controller, F4, with 4 motor ports and PH2.0 battery lead (for example BetaFPV "Matrix 1S brushed" or "F4 1S brushed", or an unbranded "whoop F4 brushed FC") | Runs Betaflight, accepts MSP receiver input over UART, has an accelerometer/gyro, weighs ~4 g. Avoid boards with a built-in VTX; you will not use it and it costs money. | 35 |
| 4 | 8.5 x 20 mm coreless brushed motors, 2 CW + 2 CCW, with 1.0 mm shaft (sold as 4-packs) | Quiet, cheap, 25 to 30 g thrust each on 65 mm props. | 10 |
| 2 sets | 65 mm two-blade props for 1.0 mm shaft (one spare set) | Two blades and the largest diameter the frame allows: quietest option. | 3 |
| 2 | 1S 600 mAh LiPo, PH2.0 connector, 30C+ | 4 to 6 min each. Two packs let you fly while one charges. | 10 |
| 1 | 1S USB LiPo charger (PH2.0), 4- or 6-port | Skip if you already have one. | 6 |
| 1 | ESP32-CAM board with OV2640 camera (AI-Thinker style) | Camera plus a dual-core MCU for ~8 USD. | 8 |
| 1 | ESP32-CAM-MB USB programmer base, or any 3.3 V USB-UART adapter | One-time programming. | 2 |
| 1 | VL53L0X laser rangefinder breakout | Height above floor to 1.2 m, I2C, 1 g. | 3 |
| 1 | MT3608 mini boost converter | 3.7 V battery to 5 V for the ESP32-CAM. | 1 |
| 1 | 6 x 6 mm tactile button | Arm / land. | 0.2 |
| 1 | 30 AWG silicone wire assortment, heat shrink, a few M2 x 6 screws | | 4 |
| | Filament for the frame and guards (~25 g PLA or PETG) | | 1 |
| | **Drone subtotal** | | **~83** |

## Wristband

| Qty | Item | ~USD |
|---|---|---|
| 1 | ESP32-C3 "super mini" board (often sold in 3-packs for ~10 USD) | 4 |
| 1 | 1S LiPo, 300 to 500 mAh, flat pouch (for example 402030 or 502030) | 5 |
| 1 | TP4056 USB-C charger board with protection | 1 |
| 1 | AO3400 N-MOSFET (SOT-23) or a 2N7000, plus 1 kΩ gate resistor | 0.5 |
| 3 | 5 mm LEDs: high-brightness green (stock camera), or 850/940 nm infrared (NoIR camera) | 1 |
| 3 | 47 Ω LED resistors (suits both green and infrared) | 0.1 |
| 2 | 100 kΩ resistors for the battery divider | 0.1 |
| 1 | 6 x 6 mm tactile button | 0.2 |
| | Filament for the cuff | 0.5 |
| | **Wristband subtotal** | **~12** |

Infrared only: an OV2640 lens module without IR-cut filter for the ESP32-CAM, ~5 USD.

The same ESP32-C3 later takes the DW3000 UWB module (~28 USD), so nothing here is
thrown away when the project moves to UWB.

## Total: about 95 USD (drone ~83 + wristband ~12), before shipping

Earlier versions of this list assumed a 20 to 25 USD flight controller. In late 2026
the BetaFPV brushed boards were listed at about 35 USD and showed as unavailable on
Amazon, so budget for that.

## Optional upgrades, in the order they help most

| Item | ~USD | What it fixes |
|---|---|---|
| PMW3901 optical flow breakout | 10 | Sideways drift: gives the roll axis something to hold against. |
| DW3000 UWB modules (3: one on the band, two on the drone) | ~85 | The planned next step: radio ranging and bearing, no light needed. |
| Second 1S charger port / more batteries | 5 each | More flying per session. |

## Tools you need

3D printer (you have one), soldering iron with a fine tip, multimeter, small Phillips
screwdriver, a computer with Betaflight Configurator and PlatformIO (VS Code extension).

## Things that look like bargains but are not

- Toy drones with their own sealed flight controller: no way to feed stick commands in.
- A whoop frame + "all in one" FC with built-in receiver only (no spare UART): check the
  board has at least one free UART pad before buying.
- Cheaper 7 mm motors and 55 mm props: not enough thrust to lift the ESP32-CAM.
- Two-cell (2S) brushless boards: more thrust, far louder, and the budget is gone.

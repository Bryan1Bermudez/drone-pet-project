# Bill of materials: budget demo (target under 100 USD)

Prices are typical AliExpress / Amazon figures in 2026, shipping not included.
Buy the flight controller and motors from the same shop so the connectors match.

## Drone

| Qty | Item | Why this one | ~USD |
|---|---|---|---|
| 1 | 1S brushed Betaflight flight controller, F4, with 4 motor ports and PH2.0 battery lead (for example "Crazybee F4 Lite 1S brushed", "BetaFPV F4 1S brushed" or an unbranded "whoop F4 brushed FC") | Runs Betaflight, accepts MSP receiver input over UART, has an accelerometer/gyro, weighs ~4 g. Avoid boards with a built-in VTX; you will not use it and it costs money. | 22 |
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
| | **Drone subtotal** | | **~70** |

## Wristband

| Qty | Item | ~USD |
|---|---|---|
| 3 | 5 mm high-brightness green LEDs (15,000 mcd or more, clear lens) | 1 |
| 3 | 100 ohm resistors (one per LED, 2 cells in series = 6 V) | 0.1 |
| 1 | 2 x CR2032 holder with slide switch | 1.5 |
| 2 | CR2032 cells | 1 |
| | Filament for the cuff | 0.5 |
| | **Wristband subtotal** | **~4** |

## Total: about 75 USD, leaving ~25 USD for shipping, a spare motor set, or the upgrades below

## Optional upgrades, in the order they help most

| Item | ~USD | What it fixes |
|---|---|---|
| PMW3901 optical flow breakout | 10 | Sideways drift: gives the roll axis something to hold against. |
| ESP32-C3 "super mini" for the wristband | 3 | Blinking LED pattern for far more robust detection, BLE pause/land button. |
| 940 nm IR LEDs + "night vision" OV2640 lens (IR filter removed) | 3 | Daylight use. |
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

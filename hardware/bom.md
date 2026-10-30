# Bill of materials: full build (phase 1b, ~450 USD)

For the under-100 USD student demo see `bom-budget.md`.

Prices are rough 2026 hobby-retail figures and will vary. Quantities are per build.

## Drone

| Qty | Item | Notes | ~USD |
|---|---|---|---|
| 1 | 7-inch "long range" quad frame, carbon, ~150 g | Arms must accept 7-inch props; room for companion board and two UWB modules on the front arms | 45 |
| 4 | Low-KV brushless motors, 2004 to 2006 size, 1700 to 2000 KV (4S) | Lower KV + bigger prop = quieter and more efficient | 80 |
| 4 (+4 spare) | 7×3.5 two-blade endurance propellers | Balance them | 15 |
| 1 | 4-in-1 ESC, 35 to 45 A, BLHeli_32 or AM32 | Enable bidirectional DShot for RPM filtering (reduces vibration noise) | 45 |
| 1 | Flight controller, STM32 F4/F7, ArduPilot supported | For example a Matek or Holybro board on the ArduPilot hardware list | 50 |
| 1 | GPS + compass module (M10 class) | Needed for RTL and the coarse fallback | 30 |
| 1 | RC receiver (ELRS or similar) | Manual override is mandatory | 20 |
| 1 | Raspberry Pi Zero 2 W + 5 V 3 A BEC | Companion board | 30 |
| 2 | DW3000-based UWB modules (SPI) | Mounted at the tips of the two front arms, ~30 cm apart | 40 |
| 1 | 4S 2200 mAh LiPo (later: 4S1P 21700 Li-ion) | See acoustics-and-power.md | 30 |
| 1 | Soft motor mounts, battery strap, XT60, wiring | | 15 |
| | **Drone subtotal** | | **~400** |

## Wristband

| Qty | Item | Notes | ~USD |
|---|---|---|---|
| 1 | ESP32-C3 mini dev board | BLE 5 + enough GPIO; low sleep current | 6 |
| 1 | DW3000 UWB module (SPI) | Same family as the drone anchors | 20 |
| 1 | 1S 500 mAh LiPo + TP4056 USB-C charger board | | 8 |
| 1 | Tactile button, LED | Pause / land commands, status | 2 |
| 1 | 3D-printed case + silicone strap | STL to be added in `hardware/wristband-case/` | 5 |
| | **Wristband subtotal** | | **~40** |

## Bench and test

| Item | Notes |
|---|---|
| Sound level meter (or calibrated phone app) | Acoustic target verification |
| Prop balancer | |
| Tether kit (line + weight) | First hover tests |
| USB-UART adapter | Companion ⇄ FC bring-up |

## Modifying an existing drone instead of building

If you already own a small quad, the minimum changes are:

1. Flash ArduPilot (if the FC is supported) or confirm your FC exposes a MAVLink
   GUIDED-equivalent interface.
2. Fit the lowest-KV motors and the largest two-blade props the frame allows.
3. Add the companion board and the two UWB modules on the front arms.
4. Add a 5 V BEC for the companion if the FC cannot supply ~1.5 A.

A sub-250 g "whoop" style frame is too small for this: there is no room for two UWB
modules with a useful baseline, and tiny high-RPM props are inherently loud.

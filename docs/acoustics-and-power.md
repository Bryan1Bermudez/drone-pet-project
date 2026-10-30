# Acoustics and power

Noise and endurance are decided almost entirely by the propulsion choice, so this is the
part to get right before writing more software.

## Where the noise comes from

A multirotor's noise is dominated by blade tip speed and by rapid throttle changes.
Sound power scales roughly with tip speed to the fifth or sixth power, so a modest drop
in RPM buys a large drop in noise. Tonal "whine" is the blade-pass frequency
(RPM / 60 × blade count) and its harmonics; broadband "hiss" comes from turbulence at
the tips.

## Rules we follow

1. **Largest propeller the frame can carry, lowest KV motor that still hovers at
   40 to 50 % throttle.** Example for a ~600 g all-up-weight 5-inch class build:
   7-inch props on 1404 to 1507 motors around 2750 to 3000 KV on 4S, or 2004/2006 motors
   around 1700 to 2000 KV. Hover RPM lands near 8 to 10 k instead of 20 k+.
2. **Two-blade props** over three-blade: fewer blade passes, less noise, better efficiency.
   Prefer low-pitch, wide-chord "endurance" props (for example 7×3.5).
3. **Balance every prop** and use soft-mounted motors. Imbalance adds a loud tonal spike.
4. **Keep the frame rigid and avoid flat panels near the props**; panels re-radiate
   pressure pulses from the blades.
5. **Fly slowly and smoothly.** The follow controller's deadbands and rate limits exist
   for this reason. A drone that drifts gently is quieter than one that stops and starts.
6. **Stay higher rather than closer.** Doubling distance drops perceived level ~6 dB.
   The default 2.5 m follow height is a compromise; 4 m is noticeably quieter for the
   wearer.

## Endurance

Hover current is set by disc loading and propulsion efficiency. For a quick estimate:

```
thrust per motor (g)  = AUW / 4
grams per watt (g/W)  = look up on the motor/prop thrust table at that thrust
hover power (W)       = AUW / (g/W)
flight time (min)     = battery Wh × 0.8 (usable) / (hover power + avionics W) × 60
```

Worked example, 600 g AUW, 7-inch endurance prop giving ~9 g/W at 150 g per motor:
hover ≈ 67 W, avionics ≈ 4 W (FC, companion, 2 × UWB, GPS, radio), 4S 2200 mAh
(32.6 Wh) → 32.6 × 0.8 / 71 × 60 ≈ **22 min**. That meets the 20 min target with no
margin, so start with that battery and measure.

Li-ion packs (for example 4S1P 21700) roughly double Wh per gram versus LiPo if the
hover current stays under about 10 A continuous, which it does for this build. That is
the single best upgrade for endurance once the airframe is proven.

## Avionics power budget

| Item | Typical draw | Notes |
|---|---|---|
| Flight controller + GPS + receiver | 1.0 W | |
| Companion: Raspberry Pi Zero 2 W | 0.6 to 1.5 W | Headless, Wi-Fi off in flight |
| 2 × DW3000 UWB modules | 0.3 W active, 20 Hz duty-cycled | Idle in between polls |
| BLE scan | 0.05 W | Part of the companion or a small ESP32 |
| Total | ~2 to 3 W | Under 5 % of hover power |

## Wristband power budget

ESP32-C3 in light sleep between events, UWB tag answering 20 polls per second, BLE
advert at 1 Hz: roughly 25 to 40 mA average. A 500 mAh single-cell LiPo gives a full day
of use. Charging over USB-C through a TP4056 or similar.

## Measurement plan

- Hover at 1.5 m over grass, calibrated sound level meter (or a phone app with a
  known offset) at 3 m horizontal, A-weighted, slow response. Record dBA for several
  prop/motor combinations.
- Log battery voltage and current from the FC, hover until 3.6 V per cell under load,
  compute real usable Wh and flight time.
- Repeat with the follow controller active while a person walks a 100 m loop.

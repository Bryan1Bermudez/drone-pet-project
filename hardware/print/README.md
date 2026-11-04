# Printed parts

Both parts are OpenSCAD source so you can change dimensions and export STL yourself
(`openscad -o frame.stl frame.scad`). Free download at openscad.org.

## frame.scad

A 100 mm (motor to motor, diagonal) X-frame with built-in prop guards.

- Motor holders for 8.5 mm coreless motors (press fit, adjust `motor_d` if your motors
  are 8.4 or 8.6 mm; print a test holder first).
- Centre plate with a 25.5 mm whoop flight-controller hole pattern.
- ESP32-CAM tray on top, camera facing forward and tilted 10° down.
- Slot for a VL53L0X breakout underneath, sensor facing the floor.
- Battery strap slot under the centre plate (use a 10 mm Velcro strap or two zip ties).

Print settings: PLA or PETG, 0.2 mm layers, 3 walls, 20 % infill, no supports when
printed flat (guards and arms are in one plane). Target weight: 9 to 11 g. If your print
is heavier than 12 g, lower `arm_w` or `guard_h` a little.

## wristband.scad

An open cuff with three 5 mm LED pockets across the top and an electronics bay for the
ESP32-C3 board, a small 1S LiPo and its USB-C charger (wiring in
`docs/budget-build.md`). Print in flexible TPU for comfort, or PLA with the cuff split
and a Velcro strap through the two slots. For the UWB upgrade, raise `holder_h` by about
4 mm to fit the DW3000 module and reprint.

Point the LEDs outward/upward: the drone looks down at you from about 1.2 m.

## Hints

- Press-fit motors can crack a PLA holder; a hair of hot glue in the socket is enough.
- Mark the front arm. The camera tray only fits one way but the motors do not care, and
  Betaflight does: motor order is 1 rear-right, 2 front-right, 3 rear-left, 4 front-left
  when viewed from above with the camera forward.

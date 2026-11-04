# Roadmap

## Phase 1a: budget demo (under 100 USD)

- [x] Design, BOM, pin map, Betaflight setup notes
- [x] OpenSCAD frame with prop guards, LED wristband cuff
- [x] ESP32-CAM firmware: blob tracker, height hold, follow state machine, MSP output
- [x] Follow logic unit-tested in Python and mirrored in C++
- [x] Coded blinking beacon: multi-blob finder and blink filter (ignores traffic lights,
      screens, glints), green or infrared LEDs, ESP32-C3 wristband ready for UWB
- [ ] Print and assemble; weigh the frame (target under 12 g)
- [ ] Bench: button arms/disarms, sticks move in Betaflight's Receiver tab
- [ ] Height-hold flight, tune hover throttle and PD gains
- [ ] Yaw-only follow, then add pitch (distance)
- [ ] Measure flight time per pack, set the flight timer
- [ ] Record a demo video

## Phase 1b: UWB on the budget drone (planned next)

- [ ] Two DW3000 modules: bench ranging between the wristband and one anchor
- [ ] Wristband UWB build (`pio run -e uwb`) on the same ESP32-C3 board
- [ ] Two anchors on the drone's front arms; port `follow/estimator.py` bearing logic
      to the ESP32 and feed it to the existing follow state machine
- [ ] Keep the blinking beacon as a fallback when UWB drops out

## Phase 1c: full build (UWB + ArduPilot)

- [x] Design docs, BOM
- [x] Follow controller (estimator, controller, safety) with simulator and tests
- [x] Wristband UWB tag firmware skeleton
- [ ] UWB ranging bring-up on the bench
- [ ] Companion MAVLink adapter against ArduPilot SITL
- [ ] Airframe build, acoustic and endurance measurements, field test

## Phase 2: self-landing on a charging dock

- Precision landing with the downward camera or an IR beacon on the dock
- Dock with contact or wireless charging
- Automatic take-off when the band leaves a home radius

## Phase 3: capture and interaction

- Photo on wristband button press (the ESP32-CAM already has the camera)
- Short clips when the wearer stops moving
- Gesture or double-tap commands from an IMU on the band
- Phone app for configuration and media download

## Phase 4: hardening

- Optical flow for position hold (budget) / third UWB anchor (full)
- IR LEDs + IR camera for daylight (budget) / barometer on the band (full)
- Obstacle avoidance

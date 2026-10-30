# Roadmap

## Phase 1: silent follow (this repository's current scope)

- [x] Design docs, BOM
- [x] Follow controller (estimator, controller, safety) with simulator and tests
- [x] Wristband firmware skeleton
- [ ] UWB ranging bring-up between the band and one anchor on the bench
- [ ] Two-anchor bearing test on the bench, verify sign and resolution
- [ ] Companion MAVLink adapter against ArduPilot SITL
- [ ] Airframe build, prop balancing, first hover (tethered)
- [ ] Acoustic measurement, pick final motor/prop combo
- [ ] Endurance measurement
- [ ] Field follow test with a walking wearer

## Phase 2: self-landing on a charging dock

- Precision landing with a downward camera or IR beacon on the dock
- Dock design with contact or wireless charging
- Automatic take-off when the band leaves a home radius

## Phase 3: capture and interaction

- Camera module, photo on wristband button press
- Short video clips when the wearer stops moving
- Gesture or double-tap commands from the band's IMU
- Mobile app for configuration and media download

## Phase 4: hardening

- Third UWB anchor to remove front/back ambiguity
- Barometer on the band for wearer altitude
- Obstacle avoidance (rangefinders or stereo camera)
- Multi-wearer handoff

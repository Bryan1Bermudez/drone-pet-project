# ESP32-CAM follow-me firmware

Build and flash with PlatformIO (VS Code extension, or `pio run -t upload`).

```
src/main.cpp         loop: camera -> blob -> height -> follow logic -> MSP
src/camera_config.h  pin map and low-exposure sensor settings
src/blob_tracker.*   colour blob centroid on RGB565 frames
src/follow_logic.*   state machine and control law (port of follow/visual.py)
src/msp.*            MSP_SET_RAW_RC sender
```

Tuning knobs are build flags in `platformio.ini` (`HOVER_THROTTLE`, `TARGET_HEIGHT_M`,
`FOLLOW_ENABLED`, `AEC_VALUE`) and the defaults in `follow_logic.h`. Change control
parameters in `firmware/companion/follow/visual.py` first, run its tests, then copy the
value here.

Bench-only debug: build with `-DDEBUG_STREAM=1` and your Wi-Fi credentials; open the
printed URL for live blob numbers and `/jpg` for a frame. Never fly with this on.

Serial log at 115200 prints state, height, blob and sticks twice a second.

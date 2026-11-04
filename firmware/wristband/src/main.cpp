// Wristband firmware: blinking camera beacon + BLE status + button, UWB optional.
//
// Responsibilities
//   1. Blink the beacon LEDs at BLINK_HZ, 50 % duty. The drone's camera follows only a
//      light blinking at exactly this rate, which rejects traffic lights, brake lights,
//      screens and reflections (see firmware/companion/follow/blink.py).
//   2. Advertise over BLE once per second: band id, battery %, button state.
//   3. Debounce the button: short press toggles PAUSE, long press (>2 s) requests LAND.
//   4. With UWB_ENABLED=1 (later upgrade, `pio run -e uwb`): also answer UWB ranging
//      polls from the drone's anchors. Same board, add a DW3000 module.
//
// The DW3000 calls are isolated behind the `uwb_*` functions so the driver can be
// swapped without touching the rest of the file.

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEAdvertising.h>
#if UWB_ENABLED
#include "uwb_tag.h"
#endif

// ---------------------------------------------------------------------------
// Pins (ESP32-C3 mini). Adjust to the carrier board.
// ---------------------------------------------------------------------------
static const int PIN_BUTTON = 9;    // active low, internal pull-up
static const int PIN_LED = 8;       // on-board status LED
static const int PIN_VBAT = 0;      // ADC, through a 2:1 divider
static const int PIN_BEACON = 1;    // gate of the N-MOSFET that switches the beacon LEDs
                                    // (kept clear of the SPI pins the UWB module will use)
static const int PIN_UWB_CS = 7;
static const int PIN_UWB_RST = 10;
static const int PIN_UWB_IRQ = 3;

// ---------------------------------------------------------------------------
// Protocol constants shared with firmware/companion/follow/band_protocol.py
// ---------------------------------------------------------------------------
static const uint16_t MANUFACTURER_ID = 0xFFFF;  // test id; register one before shipping
static const uint8_t PROTOCOL_VERSION = 1;
enum ButtonState : uint8_t { BTN_NONE = 0, BTN_PAUSE = 1, BTN_LAND = 2 };

#ifndef BAND_ID
#define BAND_ID 1
#endif
#ifndef UWB_ENABLED
#define UWB_ENABLED 0
#endif
// Must match BEACON_BLINK_HZ in firmware/drone-esp32cam/platformio.ini.
#ifndef BLINK_HZ
#define BLINK_HZ 2.5f
#endif

static BLEAdvertising *g_adv = nullptr;
static volatile ButtonState g_button_state = BTN_NONE;
static bool g_paused = false;

// ---------------------------------------------------------------------------
// Battery
// ---------------------------------------------------------------------------
static uint8_t read_battery_percent() {
  // 12-bit ADC, 3.3 V reference, 2:1 divider.
  const int raw = analogRead(PIN_VBAT);
  const float v = raw * (3.3f / 4095.0f) * 2.0f;
  // Linear approximation between 3.3 V (0 %) and 4.2 V (100 %) for a 1S LiPo.
  float pct = (v - 3.3f) / (4.2f - 3.3f) * 100.0f;
  if (pct < 0) pct = 0;
  if (pct > 100) pct = 100;
  return static_cast<uint8_t>(pct + 0.5f);
}

// ---------------------------------------------------------------------------
// BLE advertisement payload
//   [0]    protocol version
//   [1]    band id
//   [2]    battery percent
//   [3]    button state (ButtonState)
//   [4..5] uptime seconds, little endian, low 16 bits
// ---------------------------------------------------------------------------
static void update_advertisement() {
  uint8_t payload[2 + 6];
  payload[0] = MANUFACTURER_ID & 0xFF;
  payload[1] = MANUFACTURER_ID >> 8;
  payload[2] = PROTOCOL_VERSION;
  payload[3] = BAND_ID;
  payload[4] = read_battery_percent();
  payload[5] = g_paused ? BTN_PAUSE : g_button_state;
  const uint16_t up = static_cast<uint16_t>(millis() / 1000);
  payload[6] = up & 0xFF;
  payload[7] = up >> 8;

  BLEAdvertisementData data;
  data.setManufacturerData(std::string(reinterpret_cast<char *>(payload), sizeof(payload)));
  data.setName("FOLLOW-BAND");
  g_adv->setAdvertisementData(data);
}

static void ble_setup() {
  BLEDevice::init("FOLLOW-BAND");
  BLEDevice::setPower(ESP_PWR_LVL_N0);  // 0 dBm is plenty for a few tens of metres
  g_adv = BLEDevice::getAdvertising();
  g_adv->setMinInterval(0x0640);  // 1.0 s in 0.625 ms units
  g_adv->setMaxInterval(0x0640);
  update_advertisement();
  g_adv->start();
}

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------
static void poll_button() {
  static uint32_t pressed_at = 0;
  static bool was_down = false;
  static bool long_fired = false;

  const bool down = digitalRead(PIN_BUTTON) == LOW;
  const uint32_t now = millis();

  if (down && !was_down) {
    pressed_at = now;
    long_fired = false;
  }
  if (down && !long_fired && now - pressed_at > 2000) {
    g_button_state = BTN_LAND;
    long_fired = true;
  }
  if (!down && was_down) {
    if (!long_fired && now - pressed_at > 40) {  // debounce
      g_paused = !g_paused;
    }
    if (long_fired) {
      // Keep LAND asserted for a few adverts so the drone cannot miss it.
      // It is cleared in loop() after 5 s.
    }
  }
  was_down = down;
}

// ---------------------------------------------------------------------------
// Arduino entry points
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);
  analogReadResolution(12);

  pinMode(PIN_BEACON, OUTPUT);
  digitalWrite(PIN_BEACON, LOW);

#if UWB_ENABLED
  uwb_tag_init(PIN_UWB_CS, PIN_UWB_RST, PIN_UWB_IRQ, BAND_ID);
#endif
  ble_setup();
  Serial.println("FOLLOW-BAND ready");
}

// ---------------------------------------------------------------------------
// Beacon: square wave at BLINK_HZ derived from the microsecond clock, so the rate
// stays exact no matter how long other work in loop() takes.
// ---------------------------------------------------------------------------
static void update_beacon() {
  static int last = -1;
  const uint32_t period_us = static_cast<uint32_t>(1e6f / BLINK_HZ);
  const int on = (micros() % period_us) < period_us / 2 ? 1 : 0;
  if (on != last) {
    digitalWrite(PIN_BEACON, on ? HIGH : LOW);
    last = on;
  }
}

void loop() {
  static uint32_t last_adv = 0;
  static uint32_t land_asserted_at = 0;

  update_beacon();

#if UWB_ENABLED
  // UWB: block briefly for a poll, respond if one arrived. Returns quickly otherwise.
  uwb_tag_service();
#endif

  poll_button();
  if (g_button_state == BTN_LAND && land_asserted_at == 0) {
    land_asserted_at = millis();
  }
  if (land_asserted_at && millis() - land_asserted_at > 5000) {
    g_button_state = BTN_NONE;
    land_asserted_at = 0;
  }

  if (millis() - last_adv >= 1000) {
    last_adv = millis();
    update_advertisement();
    digitalWrite(PIN_LED, g_paused ? HIGH : LOW);
  }

  // Short pause. The beacon edge is at most 2 ms late, which is about 1 % of a
  // 200 ms half-period at 2.5 Hz and invisible to the camera. Light sleep is avoided
  // because it can delay edges and upset BLE; the LEDs dominate power use anyway.
  delay(2);
}

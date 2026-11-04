// ESP32-CAM follow-me: camera blob tracking + VL53L0X height -> MSP RC to Betaflight.
//
// Loop: grab frame -> find LED blob -> read height -> follow logic -> send 16 RC channels.
// The MSP stream runs at a fixed 50 Hz even when no frame is ready; a stalled stream
// triggers the FC failsafe, which is what we want if this code hangs.

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_VL53L0X.h>

#include "camera_config.h"
#include "blob_tracker.h"
#include "blink_filter.h"
#include "follow_logic.h"
#include "msp.h"

// ---- pins (see docs/budget-build.md before changing) ------------------------
static const int PIN_FC_TX = 14;   // to flight controller RX
static const int PIN_I2C_SDA = 13;
static const int PIN_I2C_SCL = 15;
static const int PIN_BUTTON = 2;   // to GND
static const int PIN_STATUS_LED = 33;  // on-board red LED, active low

#ifndef HOVER_THROTTLE
#define HOVER_THROTTLE 1450
#endif
#ifndef TARGET_HEIGHT_M
#define TARGET_HEIGHT_M 1.2f
#endif
#ifndef FOLLOW_ENABLED
#define FOLLOW_ENABLED 1
#endif
// 0 = green LEDs on the wristband, 1 = infrared LEDs (needs a camera lens without IR-cut).
#ifndef BEACON_IR
#define BEACON_IR 0
#endif
// Must match BLINK_HZ in the wristband firmware.
#ifndef BEACON_BLINK_HZ
#define BEACON_BLINK_HZ 2.5f
#endif

static const BlobColour &beacon_colour() { return BEACON_IR ? BLOB_IR : BLOB_GREEN; }

static BlinkConfig make_blink_config() {
  BlinkConfig c;
  c.blink_hz = BEACON_BLINK_HZ;
  return c;
}
static BlinkTracker blink(make_blink_config());

static HardwareSerial fc_serial(1);
static MspSender msp(fc_serial);
static Adafruit_VL53L0X tof;
static bool tof_ok = false;

static VisualConfig make_config() {
  VisualConfig c;
  c.hover_throttle = HOVER_THROTTLE;
  c.target_height_m = TARGET_HEIGHT_M;
  return c;
}
static VisualFollower follower(make_config());

// ---- button: short press and long press (>1 s) events -----------------------
struct ButtonEvents { bool short_press; bool long_press; };

static ButtonEvents poll_button() {
  static bool was_down = false;
  static uint32_t down_at = 0;
  static bool long_fired = false;
  ButtonEvents ev = {false, false};
  const bool down = digitalRead(PIN_BUTTON) == LOW;
  const uint32_t now = millis();
  if (down && !was_down) { down_at = now; long_fired = false; }
  if (down && !long_fired && now - down_at > 1000) { ev.long_press = true; long_fired = true; }
  if (!down && was_down && !long_fired && now - down_at > 40) ev.short_press = true;
  was_down = down;
  return ev;
}

// ---- height -------------------------------------------------------------------
static bool read_height(float &h_m) {
  if (!tof_ok) return false;
  VL53L0X_RangingMeasurementData_t m;
  tof.rangingTest(&m, false);
  if (m.RangeStatus == 4) return false;  // phase failure = out of range
  if (m.RangeMilliMeter > 1800) return false;
  h_m = m.RangeMilliMeter / 1000.0f;
  return true;
}

// ---- optional bench debug stream (Wi-Fi!) -------------------------------------
#if DEBUG_STREAM
#include <WiFi.h>
#include <WebServer.h>
static WebServer web(80);
static Blob last_blob;
static bool last_found = false;
static void handle_root() {
  String s = "beacon=" + String(last_found ? 1 : 0) + " cx=" + String(last_blob.cx, 2) + " cy=" + String(last_blob.cy, 2) +
             " area=" + String(last_blob.area_frac, 5) + " px=" + String(last_blob.pixels) +
             " state=" + follow_state_name(follower.state()) +
             " h=" + String(follower.last_height(), 2) + "\n";
  web.send(200, "text/plain", s);
}
static void handle_jpg() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { web.send(500, "text/plain", "no frame"); return; }
  uint8_t *jpg = nullptr; size_t jpg_len = 0;
  if (frame2jpg(fb, 80, &jpg, &jpg_len)) {
    web.setContentLength(jpg_len);
    web.send(200, "image/jpeg", "");
    web.client().write(jpg, jpg_len);
    free(jpg);
  }
  esp_camera_fb_return(fb);
}
#endif

void setup() {
  Serial.begin(115200);
  pinMode(PIN_STATUS_LED, OUTPUT);
  digitalWrite(PIN_STATUS_LED, HIGH);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  fc_serial.begin(115200, SERIAL_8N1, -1 /*rx unused*/, PIN_FC_TX);

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  tof_ok = tof.begin(VL53L0X_I2C_ADDR, false, &Wire);
  if (tof_ok) tof.configSensor(Adafruit_VL53L0X::VL53L0X_SENSE_HIGH_SPEED);
  Serial.printf("VL53L0X: %s\n", tof_ok ? "ok" : "MISSING");

  if (!camera_init()) {
    Serial.println("camera init failed");
    while (true) { digitalWrite(PIN_STATUS_LED, !digitalRead(PIN_STATUS_LED)); delay(100); }
  }
  Serial.println("camera ok");

#if DEBUG_STREAM
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; ++i) delay(250);
  Serial.printf("debug stream at http://%s/  (/jpg for a frame)\n", WiFi.localIP().toString().c_str());
  web.on("/", handle_root);
  web.on("/jpg", handle_jpg);
  web.begin();
#else
  WiFi.mode(WIFI_OFF);
#endif
}

void loop() {
  static uint32_t last_msp_ms = 0;
  static uint32_t last_blink_ms = 0;
  static RcOut rc;

  // One cycle per camera frame (~20 Hz at QQVGA with manual exposure).
  // Every bright blob goes to the blink filter, which only reports the one blinking
  // the wristband's code (traffic lights, screens and glints are ignored).
  camera_fb_t *fb = esp_camera_fb_get();
  Blob blob = {};
  bool blob_found = false;
  int n_blobs = 0;
  if (fb) {
    Blob blobs[8];
    n_blobs = find_blobs(fb->buf, fb->width, fb->height, beacon_colour(), 4, blobs, 8);
    esp_camera_fb_return(fb);
    blob_found = blink.update(millis() / 1000.0f, blobs, n_blobs, &blob);
  }
#if DEBUG_STREAM
  last_blob = blob;
  last_found = blob_found;
  web.handleClient();
#endif

  float h = 0.0f;
  const bool h_ok = read_height(h);
  const ButtonEvents btn = poll_button();

  Observation o;
  o.t = millis() / 1000.0f;
  o.blob_found = FOLLOW_ENABLED ? blob_found : false;
  o.cx = blob.cx;
  o.cy = blob.cy;
  o.area_frac = blob.area_frac;
  o.height_valid = h_ok;
  o.height_m = h;
  o.button_long = btn.long_press;
  o.button_short = btn.short_press;
  rc = follower.update(o);

  // MSP at a steady 50 Hz regardless of frame timing.
  const uint32_t now = millis();
  if (now - last_msp_ms >= 20) {
    last_msp_ms = now;
    uint16_t ch[16];
    for (auto &c : ch) c = RC_MIN;
    ch[0] = rc.roll;      // A
    ch[1] = rc.pitch;     // E
    ch[2] = rc.throttle;  // T
    ch[3] = rc.yaw;       // R
    ch[4] = rc.arm;       // AUX1 = ARM
    ch[5] = RC_MAX;       // AUX2 = ANGLE mode always on
    msp.send_raw_rc(ch, 16);
  }

  // Status LED: solid when idle, slow blink in flight, fast blink when searching.
  const uint32_t period = rc.state == FollowState::IDLE ? 0 : rc.state == FollowState::SEARCH ? 150 : 600;
  if (period == 0) {
    digitalWrite(PIN_STATUS_LED, LOW);
  } else if (now - last_blink_ms >= period) {
    last_blink_ms = now;
    digitalWrite(PIN_STATUS_LED, !digitalRead(PIN_STATUS_LED));
  }

  static uint32_t last_log_ms = 0;
  if (now - last_log_ms >= 500) {
    last_log_ms = now;
    Serial.printf("%s h=%.2f%s blobs=%d tracks=%d beacon=%d cx=%.2f area=%.4f thr=%d yaw=%d pitch=%d\n",
                  follow_state_name(rc.state), h, h_ok ? "" : "!", n_blobs, blink.active_tracks(),
                  blob_found, blob.cx, blob.area_frac, rc.throttle, rc.yaw, rc.pitch);
  }
}

// Minimal MultiWii Serial Protocol (MSP v1) sender for Betaflight.
// We only ever send MSP_SET_RAW_RC so the flight controller sees us as a receiver.
#pragma once

#include <Arduino.h>

class MspSender {
 public:
  explicit MspSender(Stream &port) : port_(port) {}

  // channels: AETR order (roll, pitch, throttle, yaw, aux1..aux12) in 1000..2000 us.
  void send_raw_rc(const uint16_t *channels, uint8_t count);

 private:
  static const uint8_t MSP_SET_RAW_RC = 200;
  Stream &port_;
};

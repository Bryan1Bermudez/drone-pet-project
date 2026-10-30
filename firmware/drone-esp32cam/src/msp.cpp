#include "msp.h"

void MspSender::send_raw_rc(const uint16_t *channels, uint8_t count) {
  if (count > 16) count = 16;
  const uint8_t len = count * 2;
  uint8_t crc = 0;

  port_.write('$');
  port_.write('M');
  port_.write('<');
  port_.write(len);
  crc ^= len;
  port_.write(MSP_SET_RAW_RC);
  crc ^= MSP_SET_RAW_RC;
  for (uint8_t i = 0; i < count; ++i) {
    const uint8_t lo = channels[i] & 0xFF;
    const uint8_t hi = channels[i] >> 8;
    port_.write(lo);
    port_.write(hi);
    crc ^= lo;
    crc ^= hi;
  }
  port_.write(crc);
}

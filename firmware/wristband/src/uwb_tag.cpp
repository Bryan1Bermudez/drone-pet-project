#include "uwb_tag.h"

// Only built for the UWB upgrade (`pio run -e uwb`); the LED-beacon build skips it.
#if defined(UWB_ENABLED) && UWB_ENABLED

#include <Arduino.h>
#include <SPI.h>

// The DW3000 driver API differs between vendors. This file compiles against the
// Makerfabs DW3000 library named in platformio.ini. Replace the three marked blocks
// if you use a different driver; the frame layout below must stay the same because
// the anchor side (companion/uwb_anchor.py) depends on it.
#include "dw3000.h"

namespace {

constexpr uint8_t FRAME_POLL = 0xA1;
constexpr uint8_t FRAME_RESP = 0xA2;

// Frame layout (bytes):
//   [0] type, [1] source id, [2] destination id, [3] sequence,
//   [4..7] turnaround time in DW3000 ticks (RESP only, little endian)
constexpr size_t POLL_LEN = 4;
constexpr size_t RESP_LEN = 8;

// Fixed delay between POLL reception and RESP transmission. Deterministic so the
// anchor can subtract it instead of trusting the turnaround field alone.
constexpr uint32_t RESP_DELAY_UUS = 650;  // UWB microseconds

uint8_t g_band_id = 1;
uint32_t g_responses = 0;

// Radio configuration: channel 5, 6.8 Mb/s, preamble 64, which keeps airtime (and
// energy per exchange) short. Both sides must match.
dwt_config_t g_config = {
    5,                 // channel
    DWT_PLEN_128,      // preamble length
    DWT_PAC8,          // preamble acquisition chunk
    9,                 // TX preamble code
    9,                 // RX preamble code
    1,                 // SFD type
    DWT_BR_6M8,        // data rate
    DWT_PHRMODE_STD,   // PHY header mode
    DWT_PHRRATE_STD,   // PHY header rate
    (129 + 8 - 8),     // SFD timeout
    DWT_STS_MODE_OFF,  // STS disabled
    DWT_STS_LEN_64,
    DWT_PDOA_M0,
};

}  // namespace

void uwb_tag_init(int pin_cs, int pin_rst, int pin_irq, uint8_t band_id) {
  g_band_id = band_id;

  // --- driver-specific block 1: bring-up -------------------------------------
  spiBegin(pin_irq, pin_rst);
  spiSelect(pin_cs);
  delay(2);
  while (!dwt_checkidlerc()) {
    delay(1);
  }
  if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR) {
    Serial.println("DW3000 init failed");
    while (true) delay(1000);
  }
  dwt_configure(&g_config);
  dwt_setrxantennadelay(16385);
  dwt_settxantennadelay(16385);
  // Low-power listening: enable receiver, let the chip idle between frames.
  dwt_setlnapamode(DWT_LNA_ENABLE | DWT_PA_ENABLE);
  // ---------------------------------------------------------------------------

  dwt_rxenable(DWT_START_RX_IMMEDIATE);
}

void uwb_tag_service() {
  // --- driver-specific block 2: receive ---------------------------------------
  uint32_t status = dwt_read32bitreg(SYS_STATUS_ID);
  if (!(status & (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_ERR))) {
    return;  // nothing yet
  }
  if (!(status & SYS_STATUS_RXFCG_BIT_MASK)) {
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_ERR);
    dwt_rxenable(DWT_START_RX_IMMEDIATE);
    return;
  }
  dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);

  uint8_t rx[16] = {0};
  uint32_t len = dwt_read32bitreg(RX_FINFO_ID) & RXFLEN_MASK;
  if (len > sizeof(rx)) len = sizeof(rx);
  dwt_readrxdata(rx, len, 0);
  // ---------------------------------------------------------------------------

  if (len < POLL_LEN || rx[0] != FRAME_POLL || rx[2] != g_band_id) {
    dwt_rxenable(DWT_START_RX_IMMEDIATE);
    return;
  }

  // --- driver-specific block 3: delayed transmit -----------------------------
  uint64_t poll_rx_ts = get_rx_timestamp_u64();
  uint32_t resp_tx_time = (poll_rx_ts + (static_cast<uint64_t>(RESP_DELAY_UUS) * UUS_TO_DWT_TIME)) >> 8;
  dwt_setdelayedtrxtime(resp_tx_time);
  uint64_t resp_tx_ts = ((static_cast<uint64_t>(resp_tx_time & 0xFFFFFFFEUL)) << 8) + 16385;
  uint32_t turnaround = static_cast<uint32_t>(resp_tx_ts - poll_rx_ts);

  uint8_t tx[RESP_LEN];
  tx[0] = FRAME_RESP;
  tx[1] = g_band_id;
  tx[2] = rx[1];  // reply to the polling anchor
  tx[3] = rx[3];  // echo sequence
  tx[4] = turnaround & 0xFF;
  tx[5] = (turnaround >> 8) & 0xFF;
  tx[6] = (turnaround >> 16) & 0xFF;
  tx[7] = (turnaround >> 24) & 0xFF;

  dwt_writetxdata(sizeof(tx), tx, 0);
  dwt_writetxfctrl(sizeof(tx) + FCS_LEN, 0, 1);
  if (dwt_starttx(DWT_START_TX_DELAYED | DWT_RESPONSE_EXPECTED) == DWT_SUCCESS) {
    g_responses++;
  } else {
    dwt_rxenable(DWT_START_RX_IMMEDIATE);
  }
  // ---------------------------------------------------------------------------
}

uint32_t uwb_tag_responses() { return g_responses; }

#endif  // UWB_ENABLED

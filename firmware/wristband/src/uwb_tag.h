// Thin wrapper around the DW3000 driver for the tag (wristband) role.
//
// Ranging scheme: single-sided two-way ranging initiated by the drone's anchors.
//   anchor -> POLL   (anchor id, sequence)
//   tag    -> RESP   (band id, sequence, tag turnaround time)
// The anchor computes time of flight = (round trip - turnaround) / 2.
// Each of the two anchors polls on alternate 25 ms slots so they never collide.

#pragma once
#include <stdint.h>

void uwb_tag_init(int pin_cs, int pin_rst, int pin_irq, uint8_t band_id);

// Service one iteration: if a POLL addressed to this band is pending, answer it.
// Non-blocking beyond a few hundred microseconds.
void uwb_tag_service();

// Count of polls answered since boot, for diagnostics.
uint32_t uwb_tag_responses();

// Multi-blob finder for RGB565 frames.
//
// Classifies each pixel as "beacon-coloured" and returns every connected blob, largest
// first, so a traffic light and the wristband stay separate instead of being averaged
// into one centroid. The blink filter (blink_filter.h) then picks the one that blinks
// the wristband's code. At 160x120 this takes a few milliseconds on the ESP32.
#pragma once

#include <stdint.h>
#include <stddef.h>

struct BlobColour {
  uint8_t channel;   // 0 = red, 1 = green, 2 = blue, 3 = bright (all channels, for IR)
  uint8_t min_level; // 0..255, the dominant channel (or every channel for 3) must reach this
  uint8_t margin;    // 0..255, dominant minus each other channel must exceed this (unused for 3)
};

static const BlobColour BLOB_GREEN = {1, 140, 50};
static const BlobColour BLOB_RED = {0, 140, 60};
static const BlobColour BLOB_BLUE = {2, 140, 50};
// Infrared LEDs through a camera without an IR-cut filter show up near-white.
static const BlobColour BLOB_IR = {3, 200, 0};

struct Blob {
  float cx;        // -1..1, +right
  float cy;        // -1..1, +down
  float area_frac; // pixels / frame pixels
  uint32_t pixels;
};

// Largest frame supported by the static label buffer.
static const int BLOB_MAX_W = 160;
static const int BLOB_MAX_H = 120;

// `rgb565` is the frame buffer as delivered by esp_camera (big-endian 16-bit pixels).
// Writes up to `max_out` blobs into `out`, largest first, and returns how many.
int find_blobs(const uint8_t *rgb565, int w, int h, const BlobColour &colour, uint32_t min_pixels,
               Blob *out, int max_out);

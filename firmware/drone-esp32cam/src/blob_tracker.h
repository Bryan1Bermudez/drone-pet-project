// Single-colour blob tracker for RGB565 frames.
//
// Classifies each pixel as "LED" if it is bright and the chosen channel dominates the
// other two by a margin, then returns the centroid and pixel count. At 160x120 this
// takes ~2 ms on the ESP32, so the follow loop runs at camera rate.
#pragma once

#include <stdint.h>
#include <stddef.h>

struct BlobColour {
  uint8_t channel;   // 0 = red, 1 = green, 2 = blue
  uint8_t min_level; // 0..255, the dominant channel must be at least this bright
  uint8_t margin;    // 0..255, dominant channel minus each other channel must exceed this
};

static const BlobColour BLOB_GREEN = {1, 140, 50};
static const BlobColour BLOB_RED = {0, 140, 60};
static const BlobColour BLOB_BLUE = {2, 140, 50};

struct Blob {
  bool found;
  float cx;        // -1..1, +right
  float cy;        // -1..1, +down
  float area_frac; // pixels / frame pixels
  uint32_t pixels;
};

// `rgb565` is the frame buffer as delivered by esp_camera (big-endian 16-bit pixels).
Blob find_blob(const uint8_t *rgb565, int w, int h, const BlobColour &colour, uint32_t min_pixels);

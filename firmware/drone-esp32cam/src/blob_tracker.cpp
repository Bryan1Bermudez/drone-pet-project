#include "blob_tracker.h"

Blob find_blob(const uint8_t *buf, int w, int h, const BlobColour &colour, uint32_t min_pixels) {
  uint64_t sx = 0, sy = 0;
  uint32_t n = 0;
  const uint32_t total = static_cast<uint32_t>(w) * static_cast<uint32_t>(h);

  for (int y = 0; y < h; ++y) {
    const uint8_t *row = buf + static_cast<size_t>(y) * w * 2;
    for (int x = 0; x < w; ++x) {
      // esp_camera hands RGB565 with the high byte first.
      const uint16_t v = (static_cast<uint16_t>(row[2 * x]) << 8) | row[2 * x + 1];
      const uint8_t r = (v >> 8) & 0xF8;  // 5 bits -> 8 bits
      const uint8_t g = (v >> 3) & 0xFC;  // 6 bits -> 8 bits
      const uint8_t b = (v << 3) & 0xF8;  // 5 bits -> 8 bits
      uint8_t dom, o1, o2;
      switch (colour.channel) {
        case 0: dom = r; o1 = g; o2 = b; break;
        case 2: dom = b; o1 = r; o2 = g; break;
        default: dom = g; o1 = r; o2 = b; break;
      }
      if (dom >= colour.min_level && dom > o1 + colour.margin && dom > o2 + colour.margin) {
        sx += x;
        sy += y;
        ++n;
      }
    }
  }

  Blob out = {};
  out.pixels = n;
  if (n < min_pixels) {
    out.found = false;
    return out;
  }
  out.found = true;
  out.cx = (static_cast<float>(sx) / n) / (w * 0.5f) - 1.0f;
  out.cy = (static_cast<float>(sy) / n) / (h * 0.5f) - 1.0f;
  out.area_frac = static_cast<float>(n) / total;
  return out;
}

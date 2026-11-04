#include "blob_tracker.h"

namespace {

const int MAX_LABELS = 1024;  // provisional labels per frame; extra regions are ignored

uint16_t g_labels[BLOB_MAX_W * BLOB_MAX_H];
uint16_t g_parent[MAX_LABELS];
uint32_t g_n[MAX_LABELS];
uint32_t g_sx[MAX_LABELS];
uint32_t g_sy[MAX_LABELS];

inline bool pixel_matches(const uint8_t *p, const BlobColour &c) {
  // esp_camera hands RGB565 with the high byte first.
  const uint16_t v = (static_cast<uint16_t>(p[0]) << 8) | p[1];
  const uint8_t r = (v >> 8) & 0xF8;  // 5 bits -> 8 bits
  const uint8_t g = (v >> 3) & 0xFC;  // 6 bits -> 8 bits
  const uint8_t b = (v << 3) & 0xF8;  // 5 bits -> 8 bits
  if (c.channel == 3) {
    return r >= c.min_level && g >= c.min_level && b >= c.min_level;
  }
  uint8_t dom, o1, o2;
  switch (c.channel) {
    case 0: dom = r; o1 = g; o2 = b; break;
    case 2: dom = b; o1 = r; o2 = g; break;
    default: dom = g; o1 = r; o2 = b; break;
  }
  return dom >= c.min_level && dom > o1 + c.margin && dom > o2 + c.margin;
}

uint16_t find_root(uint16_t a) {
  while (g_parent[a] != a) {
    g_parent[a] = g_parent[g_parent[a]];  // path halving
    a = g_parent[a];
  }
  return a;
}

void unite(uint16_t a, uint16_t b) {
  a = find_root(a);
  b = find_root(b);
  if (a < b) g_parent[b] = a;
  else if (b < a) g_parent[a] = b;
}

}  // namespace

int find_blobs(const uint8_t *buf, int w, int h, const BlobColour &colour, uint32_t min_pixels,
               Blob *out, int max_out) {
  if (w > BLOB_MAX_W || h > BLOB_MAX_H || max_out <= 0) return 0;

  // Pass 1: provisional 4-connected labels with union-find.
  uint16_t next = 1;
  for (int y = 0; y < h; ++y) {
    const uint8_t *row = buf + static_cast<size_t>(y) * w * 2;
    for (int x = 0; x < w; ++x) {
      uint16_t &lab = g_labels[y * w + x];
      lab = 0;
      if (!pixel_matches(row + 2 * x, colour)) continue;
      const uint16_t left = x > 0 ? g_labels[y * w + x - 1] : 0;
      const uint16_t up = y > 0 ? g_labels[(y - 1) * w + x] : 0;
      if (left && up) {
        lab = left < up ? left : up;
        if (left != up) unite(left, up);
      } else if (left || up) {
        lab = left ? left : up;
      } else if (next < MAX_LABELS) {
        lab = next;
        g_parent[next] = next;
        g_n[next] = g_sx[next] = g_sy[next] = 0;
        ++next;
      }
    }
  }

  // Pass 2: accumulate statistics on each root.
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const uint16_t lab = g_labels[y * w + x];
      if (!lab) continue;
      const uint16_t r = find_root(lab);
      g_n[r] += 1;
      g_sx[r] += x;
      g_sy[r] += y;
    }
  }

  // Collect roots above the size threshold, keeping the largest `max_out`.
  int count = 0;
  const float total = static_cast<float>(w) * h;
  for (uint16_t lab = 1; lab < next; ++lab) {
    if (g_parent[lab] != lab || g_n[lab] < min_pixels) continue;
    Blob b;
    b.pixels = g_n[lab];
    b.cx = (static_cast<float>(g_sx[lab]) / b.pixels) / (w * 0.5f) - 1.0f;
    b.cy = (static_cast<float>(g_sy[lab]) / b.pixels) / (h * 0.5f) - 1.0f;
    b.area_frac = b.pixels / total;
    // Insertion into a list sorted by size, largest first.
    int pos = count < max_out ? count : max_out;
    while (pos > 0 && out[pos - 1].pixels < b.pixels) {
      if (pos < max_out) out[pos] = out[pos - 1];
      --pos;
    }
    if (pos < max_out) {
      out[pos] = b;
      if (count < max_out) ++count;
    }
  }
  return count;
}

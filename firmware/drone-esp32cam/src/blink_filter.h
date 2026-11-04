// Coded-beacon filter: follow only the blob that blinks the wristband's pattern.
// Port of firmware/companion/follow/blink.py, which has the tests and the reasoning.
#pragma once

#include <stdint.h>

#include "blob_tracker.h"

struct BlinkConfig {
  float blink_hz = 2.5f;
  float window_s = 2.0f;
  float lock_confirm = 0.45f;
  float lock_keep = 0.33f;
  float confirm_hold_s = 0.4f;
  float duty_min = 0.25f;
  float duty_max = 0.75f;
  float transitions_min_ratio = 0.5f;
  float transitions_max_ratio = 1.8f;
  float match_radius = 0.25f;
  float track_timeout_s = 1.0f;
  float fresh_s = 0.5f;
};

class BlinkTracker {
 public:
  static const int MAX_TRACKS = 8;
  static const int MAX_SAMPLES = 96;  // 2 s at up to 48 fps

  explicit BlinkTracker(const BlinkConfig &cfg) : cfg_(cfg) {}

  // Feed one frame's blobs. Returns true and fills `out` with the latest sighting of
  // the confirmed beacon, or returns false if no blob is currently confirmed.
  bool update(float t, const Blob *blobs, int n, Blob *out);

  int active_tracks() const;

 private:
  struct Track {
    bool used = false;
    int id = 0;
    float cx = 0, cy = 0;
    Blob last = {};
    float t_last_seen = 0, t_created = 0;
    float st[MAX_SAMPLES];
    bool sv[MAX_SAMPLES];
    int head = 0, count = 0;  // ring buffer of (time, seen)
    bool confirmed = false;
    bool lock_started = false;
    float t_lock_start = 0;

    void push(float t, bool seen);
    float time_at(int i) const { return st[(head + i) % MAX_SAMPLES]; }
    bool seen_at(int i) const { return sv[(head + i) % MAX_SAMPLES]; }
  };

  void update_confirmation(Track &tr, float t);
  float phase_lock(const Track &tr) const;
  bool duty_ok(const Track &tr, bool loose) const;
  bool transitions_ok(const Track &tr) const;

  BlinkConfig cfg_;
  Track tracks_[MAX_TRACKS];
  int next_id_ = 1;
};

#include "blink_filter.h"

#include <math.h>

void BlinkTracker::Track::push(float t, bool seen) {
  if (count == MAX_SAMPLES) {  // full: overwrite the oldest
    head = (head + 1) % MAX_SAMPLES;
    --count;
  }
  const int idx = (head + count) % MAX_SAMPLES;
  st[idx] = t;
  sv[idx] = seen;
  ++count;
}

int BlinkTracker::active_tracks() const {
  int n = 0;
  for (const Track &tr : tracks_) n += tr.used;
  return n;
}

bool BlinkTracker::update(float t, const Blob *blobs, int n, Blob *out) {
  bool taken[16] = {false};
  if (n > 16) n = 16;

  // Visit existing tracks oldest first and match each to its nearest free blob.
  int order[MAX_TRACKS];
  int m = 0;
  for (int i = 0; i < MAX_TRACKS; ++i)
    if (tracks_[i].used) order[m++] = i;
  for (int a = 1; a < m; ++a) {  // insertion sort by creation time
    const int v = order[a];
    int b = a - 1;
    while (b >= 0 && tracks_[order[b]].t_created > tracks_[v].t_created) {
      order[b + 1] = order[b];
      --b;
    }
    order[b + 1] = v;
  }

  for (int k = 0; k < m; ++k) {
    Track &tr = tracks_[order[k]];
    int best = -1;
    float best_d = cfg_.match_radius;
    for (int j = 0; j < n; ++j) {
      if (taken[j]) continue;
      const float d = hypotf(blobs[j].cx - tr.cx, blobs[j].cy - tr.cy);
      if (d < best_d) {
        best = j;
        best_d = d;
      }
    }
    if (best >= 0) {
      taken[best] = true;
      tr.cx = blobs[best].cx;
      tr.cy = blobs[best].cy;
      tr.last = blobs[best];
      tr.t_last_seen = t;
      tr.push(t, true);
    } else {
      tr.push(t, false);
    }
    while (tr.count > 0 && t - tr.time_at(0) > cfg_.window_s) {
      tr.head = (tr.head + 1) % MAX_SAMPLES;
      --tr.count;
    }
  }

  // Expire tracks not seen for a while.
  for (Track &tr : tracks_)
    if (tr.used && t - tr.t_last_seen > cfg_.track_timeout_s) tr.used = false;

  // New tracks for unmatched blobs.
  for (int j = 0; j < n; ++j) {
    if (taken[j]) continue;
    for (Track &tr : tracks_) {
      if (tr.used) continue;
      tr = Track();
      tr.used = true;
      tr.id = next_id_++;
      tr.cx = blobs[j].cx;
      tr.cy = blobs[j].cy;
      tr.last = blobs[j];
      tr.t_last_seen = tr.t_created = t;
      tr.push(t, true);
      break;
    }
  }

  for (Track &tr : tracks_)
    if (tr.used) update_confirmation(tr, t);

  // Oldest confirmed, recently seen track wins; ties go to the larger blob.
  const Track *pick = nullptr;
  for (const Track &tr : tracks_) {
    if (!tr.used || !tr.confirmed || t - tr.t_last_seen > cfg_.fresh_s) continue;
    if (!pick || tr.t_created < pick->t_created ||
        (tr.t_created == pick->t_created && tr.last.pixels > pick->last.pixels))
      pick = &tr;
  }
  if (!pick) return false;
  *out = pick->last;
  return true;
}

void BlinkTracker::update_confirmation(Track &tr, float t) {
  if (t - tr.t_created < cfg_.window_s * 0.95f) return;
  const float lock = phase_lock(tr);
  if (tr.confirmed) {
    tr.confirmed = lock >= cfg_.lock_keep && duty_ok(tr, true);
    return;
  }
  if (lock >= cfg_.lock_confirm && duty_ok(tr, false) && transitions_ok(tr)) {
    if (!tr.lock_started) {
      tr.lock_started = true;
      tr.t_lock_start = t;
    }
    if (t - tr.t_lock_start >= cfg_.confirm_hold_s) tr.confirmed = true;
  } else {
    tr.lock_started = false;
  }
}

float BlinkTracker::phase_lock(const Track &tr) const {
  if (tr.count == 0) return 0.0f;
  // Phase is measured from the track's creation time to keep float arguments small.
  const float w = 2.0f * static_cast<float>(M_PI) * cfg_.blink_hz;
  float re = 0, im = 0;
  for (int i = 0; i < tr.count; ++i) {
    const float s = tr.seen_at(i) ? 1.0f : -1.0f;
    const float ph = w * (tr.time_at(i) - tr.t_created);
    re += s * cosf(ph);
    im += s * sinf(ph);
  }
  return hypotf(re, im) / tr.count;
}

bool BlinkTracker::duty_ok(const Track &tr, bool loose) const {
  if (tr.count < 6) return false;
  const float span = tr.time_at(tr.count - 1) - tr.time_at(0);
  if (span <= 0) return false;
  float on = 0;
  for (int i = 0; i + 1 < tr.count; ++i)
    if (tr.seen_at(i)) on += tr.time_at(i + 1) - tr.time_at(i);
  const float duty = on / span;
  float lo = cfg_.duty_min, hi = cfg_.duty_max;
  if (loose) {
    lo -= 0.1f;
    hi += 0.1f;
  }
  return duty >= lo && duty <= hi;
}

bool BlinkTracker::transitions_ok(const Track &tr) const {
  const float span = tr.time_at(tr.count - 1) - tr.time_at(0);
  int edges = 0;
  for (int i = 1; i < tr.count; ++i) edges += tr.seen_at(i) != tr.seen_at(i - 1);
  const float expected = 2.0f * cfg_.blink_hz * span;
  return edges >= cfg_.transitions_min_ratio * expected && edges <= cfg_.transitions_max_ratio * expected;
}

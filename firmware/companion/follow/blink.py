"""Coded-beacon filter: follow only the light that blinks the wristband's pattern.

Why: a colour threshold alone also matches traffic lights, brake lights, screens and
reflections. The wristband instead blinks at a fixed rate (default 2.5 Hz, 50 % duty).
Steady lights never change state, mains-powered lights flicker far too fast for the
camera to resolve cleanly, and random glints change state irregularly. So we:

1. Find every bright blob in each frame (`find_blobs`), not one merged centroid.
2. Keep a short track per blob, recording each frame whether it was seen ("on") or not.
3. Confirm a track only if, over the last `window_s` seconds, its on/off sequence is
   phase-locked to a square wave at the beacon's rate (see `phase_lock`), it was on
   25 to 75 % of the time, and it switched state roughly as often as the beacon does.
   A confirmed track is kept on a looser threshold, so a few missed frames (motion
   blur, a hand passing in front) do not drop it.

The blink rate is chosen from the camera rate: at 15 to 30 fps a 2.5 Hz blink spans
6 to 12 frames per cycle, comfortably resolvable, while staying slow enough that a
dropped frame or two does not break the pattern.

`firmware/drone-esp32cam/src/blink_filter.cpp` is a port of this file.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Sequence


@dataclass(frozen=True)
class Blob:
    cx: float         # -1..1, +right
    cy: float         # -1..1, +down
    area_frac: float  # blob pixels / frame pixels
    pixels: int


def find_blobs(mask: Sequence[Sequence[bool]], min_pixels: int = 4, max_blobs: int = 8) -> list[Blob]:
    """4-connected components of a boolean mask, largest first."""
    h = len(mask)
    w = len(mask[0]) if h else 0
    labels = [[0] * w for _ in range(h)]
    blobs: list[Blob] = []
    next_label = 1
    for y0 in range(h):
        for x0 in range(w):
            if not mask[y0][x0] or labels[y0][x0]:
                continue
            stack = [(x0, y0)]
            labels[y0][x0] = next_label
            n = sx = sy = 0
            while stack:
                x, y = stack.pop()
                n += 1
                sx += x
                sy += y
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and not labels[ny][nx]:
                        labels[ny][nx] = next_label
                        stack.append((nx, ny))
            next_label += 1
            if n >= min_pixels:
                blobs.append(Blob(sx / n / (w * 0.5) - 1.0, sy / n / (h * 0.5) - 1.0, n / (w * h), n))
    blobs.sort(key=lambda b: b.pixels, reverse=True)
    return blobs[:max_blobs]


@dataclass
class BlinkConfig:
    blink_hz: float = 2.5
    window_s: float = 2.0
    lock_confirm: float = 0.45           # phase-lock needed to start following a track
    lock_keep: float = 0.33              # ...and to keep following it (hysteresis)
    confirm_hold_s: float = 0.4          # lock must stay above lock_confirm this long first
    duty_min: float = 0.25
    duty_max: float = 0.75
    transitions_min_ratio: float = 0.5   # of expected on/off transitions in the window
    transitions_max_ratio: float = 1.8   # missed frames add transitions, so allow extra
    match_radius: float = 0.25           # in normalised image units (-1..1 spans the frame)
    track_timeout_s: float = 1.0         # drop a track unseen for this long
    fresh_s: float = 0.5                 # only report the beacon if seen this recently
    max_tracks: int = 8


@dataclass
class _Track:
    id: int
    cx: float
    cy: float
    last_seen: Blob
    t_last_seen: float
    t_created: float
    samples: Deque[tuple[float, bool]] = field(default_factory=deque)
    confirmed: bool = False
    t_lock_start: Optional[float] = None


class BlinkTracker:
    def __init__(self, cfg: Optional[BlinkConfig] = None):
        self.cfg = cfg or BlinkConfig()
        self._tracks: list[_Track] = []
        self._next_id = 1

    @property
    def tracks(self) -> list[_Track]:
        return self._tracks

    def update(self, t: float, blobs: Sequence[Blob]) -> Optional[Blob]:
        """Feed one frame. Returns the latest sighting of the confirmed beacon, or None."""
        cfg = self.cfg
        unmatched = list(blobs)

        # Greedy nearest-neighbour matching, existing tracks first (oldest first).
        for tr in sorted(self._tracks, key=lambda x: x.t_created):
            best, best_d = None, cfg.match_radius
            for b in unmatched:
                d = math.hypot(b.cx - tr.cx, b.cy - tr.cy)
                if d < best_d:
                    best, best_d = b, d
            if best is not None:
                unmatched.remove(best)
                tr.cx, tr.cy = best.cx, best.cy
                tr.last_seen, tr.t_last_seen = best, t
                tr.samples.append((t, True))
            else:
                tr.samples.append((t, False))
            while tr.samples and t - tr.samples[0][0] > cfg.window_s:
                tr.samples.popleft()

        self._tracks = [tr for tr in self._tracks if t - tr.t_last_seen <= cfg.track_timeout_s]

        for b in unmatched:
            if len(self._tracks) >= cfg.max_tracks:
                break
            tr = _Track(self._next_id, b.cx, b.cy, b, t, t)
            tr.samples.append((t, True))
            self._tracks.append(tr)
            self._next_id += 1

        for tr in self._tracks:
            self._update_confirmation(tr, t)

        confirmed = [tr for tr in self._tracks if tr.confirmed and t - tr.t_last_seen <= cfg.fresh_s]
        if not confirmed:
            return None
        # Prefer the oldest confirmed track (stable), then the biggest.
        best = min(confirmed, key=lambda x: (x.t_created, -x.last_seen.pixels))
        return best.last_seen

    # ------------------------------------------------------------------ #
    def _update_confirmation(self, tr: _Track, t: float) -> None:
        cfg = self.cfg
        if t - tr.t_created < cfg.window_s * 0.95:
            return
        samples = list(tr.samples)
        lock = self.phase_lock(samples)
        if tr.confirmed:
            tr.confirmed = lock >= cfg.lock_keep and self._duty_ok(samples, loose=True)
            return
        if lock >= cfg.lock_confirm and self._duty_ok(samples) and self._transitions_ok(samples):
            if tr.t_lock_start is None:
                tr.t_lock_start = t
            if t - tr.t_lock_start >= cfg.confirm_hold_s:
                tr.confirmed = True
        else:
            tr.t_lock_start = None

    def matches_pattern(self, samples: Sequence[tuple[float, bool]]) -> bool:
        """Instantaneous check (no hysteresis), useful for tests and tuning."""
        samples = list(samples)
        return (
            self.phase_lock(samples) >= self.cfg.lock_confirm
            and self._duty_ok(samples)
            and self._transitions_ok(samples)
        )

    def _duty_ok(self, samples: list[tuple[float, bool]], loose: bool = False) -> bool:
        if len(samples) < 6:
            return False
        span = samples[-1][0] - samples[0][0]
        if span <= 0:
            return False
        on_time = sum(t1 - t0 for (t0, s0), (t1, _) in zip(samples, samples[1:]) if s0)
        duty = on_time / span
        lo, hi = self.cfg.duty_min, self.cfg.duty_max
        if loose:
            lo, hi = lo - 0.1, hi + 0.1
        return lo <= duty <= hi

    def _transitions_ok(self, samples: list[tuple[float, bool]]) -> bool:
        span = samples[-1][0] - samples[0][0]
        edges = sum(1 for a, b in zip(samples, samples[1:]) if a[1] != b[1])
        expected = 2.0 * self.cfg.blink_hz * span
        return self.cfg.transitions_min_ratio * expected <= edges <= self.cfg.transitions_max_ratio * expected

    def phase_lock(self, samples: Sequence[tuple[float, bool]]) -> float:
        """Correlation of the on/off sequence with a square wave at blink_hz, any phase.

        |mean(s_k * exp(2*pi*i*f*t_k))| with s = +1 on, -1 off. A 50 % duty square wave at
        exactly f gives 2/pi (about 0.64); random flicker gives about 1/sqrt(N); a light
        blinking at another rate averages towards 0 over the window.
        """
        w = 2.0 * math.pi * self.cfg.blink_hz
        re = im = 0.0
        for t, on in samples:
            s = 1.0 if on else -1.0
            re += s * math.cos(w * t)
            im += s * math.sin(w * t)
        return math.hypot(re, im) / len(samples)

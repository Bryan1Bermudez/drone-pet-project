"""Coded-beacon filter: the wristband must win against steady and flickering lights."""

import math
import random

import pytest

from follow.blink import Blob, BlinkConfig, BlinkTracker, find_blobs


def beacon_on(t: float, hz: float = 2.5, phase: float = 0.0) -> bool:
    return ((t * hz + phase) % 1.0) < 0.5


def run(frames, fps=20.0, duration=6.0, jitter=0.0, seed=0):
    """frames(t, rng) -> list[Blob]. Returns (times, outputs)."""
    rng = random.Random(seed)
    tr = BlinkTracker()
    t, out = 0.0, []
    while t < duration:
        out.append((t, tr.update(t, frames(t, rng))))
        t += 1.0 / fps + (rng.uniform(-jitter, jitter) if jitter else 0.0)
    return out


BAND = (0.3, -0.1)
TRAFFIC = (-0.6, -0.7)
GLINT = (0.7, 0.6)


def scene(t, rng, band=True, traffic=True, glint=True, band_hz=2.5):
    blobs = []
    if band and beacon_on(t, band_hz):
        blobs.append(Blob(BAND[0] + rng.gauss(0, 0.01), BAND[1] + rng.gauss(0, 0.01), 0.004, 77))
    if traffic:  # steady and bigger than the band
        blobs.append(Blob(*TRAFFIC, 0.01, 192))
    if glint and rng.random() < 0.5:  # random flicker, e.g. a reflection or aliased mains light
        blobs.append(Blob(*GLINT, 0.006, 115))
    return blobs


def near_band(b):
    return b is not None and math.hypot(b.cx - BAND[0], b.cy - BAND[1]) < 0.1


@pytest.mark.parametrize("fps", [15.0, 20.0, 30.0])
def test_band_confirmed_and_distractors_rejected(fps):
    out = run(lambda t, r: scene(t, r), fps=fps, duration=6.0, jitter=0.004)
    late = [b for t, b in out if t > 2.5]
    assert sum(near_band(b) for b in late) / len(late) > 0.95
    assert all(b is None or near_band(b) for b in late), "never lock onto the traffic light or glint"


def test_confirms_within_about_two_and_a_half_seconds():
    out = run(lambda t, r: scene(t, r))
    first = next(t for t, b in out if near_band(b))
    assert first < 2.6


def test_steady_light_alone_is_never_followed():
    out = run(lambda t, r: scene(t, r, band=False, glint=False))
    assert all(b is None for _, b in out)


def test_random_flicker_alone_is_never_followed():
    for seed in range(5):
        out = run(lambda t, r: scene(t, r, band=False, traffic=False), seed=seed)
        assert all(b is None for _, b in out), f"seed {seed}"


def test_wrong_blink_rate_is_rejected():
    for hz in (1.0, 6.0):
        out = run(lambda t, r: scene(t, r, traffic=False, glint=False, band_hz=hz), fps=20.0)
        assert all(b is None for _, b in out), f"{hz} Hz should not match 2.5 Hz"


def test_moving_band_is_tracked():
    def frames(t, rng):
        x = -0.6 + 0.2 * t  # crosses the frame over 6 s
        return [Blob(x, 0.0, 0.004, 77)] if beacon_on(t) else []

    out = run(frames)
    late = [(t, b) for t, b in out if t > 2.5]
    assert all(b is not None for _, b in late)
    assert all(abs(b.cx - (-0.6 + 0.2 * t)) < 0.15 for t, b in late)


def test_band_lost_then_reacquired():
    def frames(t, rng):
        return scene(t, rng, band=not (3.0 <= t < 4.0))

    out = run(frames, duration=8.0)
    assert all(b is None for t, b in out if 3.8 <= t < 4.0)
    assert any(near_band(b) for t, b in out if t > 6.5)


def test_find_blobs_separates_two_lights():
    w, h = 40, 30
    mask = [[False] * w for _ in range(h)]
    for y in range(5, 9):
        for x in range(5, 9):
            mask[y][x] = True          # 16 px, top-left
    for y in range(20, 26):
        for x in range(30, 36):
            mask[y][x] = True          # 36 px, bottom-right
    mask[0][39] = True                 # single noisy pixel, below min_pixels
    blobs = find_blobs(mask, min_pixels=4)
    assert len(blobs) == 2
    big, small = blobs
    assert big.pixels == 36 and small.pixels == 16
    assert big.cx > 0.5 and big.cy > 0.4
    assert small.cx < -0.5 and small.cy < -0.4


def test_custom_rate_config():
    cfg = BlinkConfig(blink_hz=2.0)
    tr = BlinkTracker(cfg)
    t, hits = 0.0, 0
    while t < 5.0:
        b = tr.update(t, [Blob(0, 0, 0.004, 77)] if beacon_on(t, 2.0) else [])
        hits += b is not None and t > 2.5
        t += 0.05
    assert hits > 40


def test_tolerates_missed_frames():
    """Motion blur or a hand in the way: 15 % of the band's on-frames are missed."""
    rates = []
    for seed in range(10):
        def frames(t, rng):
            return [Blob(*BAND, 0.004, 77)] if beacon_on(t) and rng.random() > 0.15 else []
        out = run(frames, fps=20.0, duration=20.0, seed=seed)
        late = [b for t, b in out if t > 4.0]
        rates.append(sum(b is not None for b in late) / len(late))
    assert sum(rates) / len(rates) > 0.9
    assert min(rates) > 0.75


def test_random_flicker_many_seeds_and_rates():
    for p in (0.3, 0.5, 0.7):
        for seed in range(20):
            def frames(t, rng):
                return [Blob(*GLINT, 0.006, 115)] if rng.random() < p else []
            out = run(frames, fps=15.0, duration=20.0, seed=seed)
            assert all(b is None for _, b in out), f"p={p} seed={seed}"


def test_phase_lock_values():
    tr = BlinkTracker()
    square = [(k / 20.0, beacon_on(k / 20.0)) for k in range(40)]
    steady = [(k / 20.0, True) for k in range(40)]
    assert tr.phase_lock(square) == pytest.approx(2 / math.pi, abs=0.08)
    assert tr.phase_lock(steady) < 0.1

"""Headless checks of the webcam test tool's pipeline (needs numpy + opencv)."""

import sys
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webcam_follow import FakeBeacon, Pipeline, VirtualDrone, describe, stick_pct  # noqa: E402

FPS = 30.0
W, H = 640, 480


def world(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(40 + rng.normal(0, 8, (H, W, 3)), 0, 255).astype(np.uint8)


def run(seconds, beacon, sim=None, steady=False):
    pipe = Pipeline()
    out = hit = None
    for i in range(int(seconds * FPS)):
        t = i / FPS
        frame = world(i)
        if steady:
            cv2.circle(frame, (int(beacon.x * W), int(beacon.y * H)), int(beacon.radius_frac * W), (0, 255, 0), -1)
        else:
            beacon.draw(frame, t)
        view = sim.view(frame, (W, H)) if sim else frame
        _, hit, out = pipe.update(view, t)
        if sim:
            sim.step(out, 1 / FPS)
    return hit, out


def test_blinking_beacon_right_of_centre_turns_right():
    b = FakeBeacon(x=0.8, y=0.5, radius_frac=0.02, enabled=True)
    hit, out = run(4, b)
    assert hit is not None and hit.cx > 0.4
    assert stick_pct(out.yaw) > 0 and "RIGHT" in describe(out)


def test_steady_green_light_is_ignored():
    b = FakeBeacon(x=0.3, y=0.5, radius_frac=0.02, enabled=True)
    hit, _ = run(4, b, steady=True)
    assert hit is None


def test_virtual_drone_centres_the_beacon():
    b = FakeBeacon(x=0.72, y=0.5, radius_frac=0.012, enabled=True)
    sim = VirtualDrone()
    hit, _ = run(12, b, sim=sim)
    assert hit is not None and abs(hit.cx) < 0.25, hit
    assert sim.view_x > 0.6


def test_small_far_beacon_moves_forward():
    b = FakeBeacon(x=0.5, y=0.5, radius_frac=0.009, enabled=True)
    sim = VirtualDrone()
    run(8, b, sim=sim)
    assert sim.zoom > 1.1

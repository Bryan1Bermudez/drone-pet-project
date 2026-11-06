"""Headless checks of the follow core's safety layer (needs numpy + opencv)."""

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from follow_core import BeaconFollower, GovernorConfig, LoomingDetector, Mode, SafetyGovernor  # noqa: E402
from webcam_follow import FakeBeacon  # noqa: E402

FPS = 15.0


@dataclass
class Hit:
    cx: float = 0.0
    cy: float = 0.0
    area_frac: float = 0.002


def texture(seed=1, w=640, h=360):
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (h // 8, w // 8), dtype=np.uint8)
    img = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(cv2.GaussianBlur(img, (5, 5), 0), cv2.COLOR_GRAY2BGR)


def zoomed(img, scale):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 0, scale)
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)


def shifted(img, dx):
    h, w = img.shape[:2]
    M = np.float32([[1, 0, dx], [0, 1, 0]])
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)


# ------------------------------------------------------------------ looming

def test_fast_approach_is_looming():
    base, det, scale, seen = texture(), LoomingDetector(), 1.0, False
    for i in range(10):
        scale *= 1.08                         # 8 % bigger each frame at 15 fps: tau ~0.8 s
        seen |= det.update(zoomed(base, scale), i / FPS)
    assert seen and det.last_tau is not None and det.last_tau < 1.2


def test_turning_is_not_looming():
    base, det = texture(), LoomingDetector()
    hits = [det.update(shifted(base, 6 * i), i / FPS) for i in range(10)]
    assert not any(hits)


def test_slow_approach_and_still_view_are_not_looming():
    base, det, scale = texture(), LoomingDetector(), 1.0
    hits = []
    for i in range(10):
        scale *= 1.01                         # tau ~6.7 s: normal following
        hits.append(det.update(zoomed(base, scale), i / FPS))
    det2 = LoomingDetector()
    hits += [det2.update(base, i / FPS) for i in range(5)]
    assert not any(hits)


# ------------------------------------------------------------------ governor

def run(gov, seconds, hit=Hit(), yaw=0.0, pitch=0.0, looming=False, t0=0.0):
    cmds, t = [], t0
    for i in range(int(seconds * FPS)):
        t = t0 + i / FPS
        cmds.append(gov.step(t, hit, yaw, pitch, looming))
    return cmds, t


def test_speed_cap_and_smoothing():
    gov = SafetyGovernor(GovernorConfig(rest_after_s=0))
    cmds, _ = run(gov, 0.2, yaw=1.0, pitch=1.0)
    assert cmds[-1].yaw <= 0.3 + 1e-9           # slewed, not jumped
    cmds, _ = run(gov, 3.0, yaw=1.0, pitch=1.0, t0=0.2)
    assert abs(cmds[-1].yaw - 0.35) < 1e-9 and abs(cmds[-1].pitch - 0.30) < 1e-9


def test_lost_beacon_hovers_then_lands_once():
    gov = SafetyGovernor(GovernorConfig(rest_after_s=0))
    run(gov, 1.0, yaw=0.3)
    cmds, t = run(gov, 8.0, hit=None, t0=1.0)
    actions = [c.action for c in cmds if c.action]
    assert actions == ["land"]
    assert all(c.yaw == 0 and c.pitch == 0 for c in cmds)
    first_land = next(i for i, c in enumerate(cmds) if c.action == "land") / FPS
    assert 5.5 <= first_land <= 6.5
    assert gov.mode == Mode.LANDED


def test_startup_waits_for_first_confirmation():
    gov = SafetyGovernor(GovernorConfig(rest_after_s=0, land_after_lost_s=2.0))
    cmds, t = run(gov, 10.0, hit=None)              # beacon not confirmed yet
    assert not any(c.action for c in cmds)
    cmds, _ = run(gov, 6.0, hit=None, t0=t + 1 / FPS)
    assert [c.action for c in cmds if c.action] == ["land"]   # gives up after the 15 s grace


def test_no_relaunch_unless_enabled():
    gov = SafetyGovernor(GovernorConfig(rest_after_s=0, relaunch=False))
    run(gov, 0.5)
    run(gov, 7.0, hit=None, t0=0.5)
    cmds, _ = run(gov, 3.0, t0=7.5)
    assert not any(c.action == "takeoff" for c in cmds)
    gov2 = SafetyGovernor(GovernorConfig(rest_after_s=0, relaunch=True))
    run(gov2, 0.5)
    run(gov2, 7.0, hit=None, t0=0.5)
    cmds, _ = run(gov2, 3.0, t0=7.5)
    assert [c.action for c in cmds if c.action] == ["takeoff"]
    assert gov2.mode == Mode.SETTLING


def test_looming_backs_off_then_resumes():
    gov = SafetyGovernor(GovernorConfig(rest_after_s=0))
    run(gov, 1.0, pitch=0.3)
    cmds, t = run(gov, 0.5, pitch=0.3, looming=True, t0=1.0)
    assert cmds[0].mode == Mode.BACKOFF and all(c.pitch < 0 for c in cmds)
    cmds, _ = run(gov, 1.0, pitch=0.3, t0=t + 1 / FPS)
    assert cmds[-1].mode == Mode.FOLLOW and cmds[-1].pitch > 0


def test_land_and_wait_then_relaunch_on_move():
    gov = SafetyGovernor(GovernorConfig(rest_after_s=5.0, relaunch=True))
    cmds, t = run(gov, 6.0, hit=Hit(cx=0.0))
    assert [c.action for c in cmds if c.action] == ["land"] and gov.mode == Mode.RESTING
    cmds, t = run(gov, 2.0, hit=Hit(cx=0.05), t0=t + 1 / FPS)       # small sway: stay down
    assert not any(c.action for c in cmds)
    cmds, _ = run(gov, 2.0, hit=Hit(cx=0.5), t0=t + 1 / FPS)        # walked off: relaunch
    assert [c.action for c in cmds if c.action] == ["takeoff"]


# ------------------------------------------------------------------ end to end

def test_beacon_right_of_centre_turns_right_within_cap():
    f = BeaconFollower(looming=False, gov_cfg=GovernorConfig(rest_after_s=0))
    b = FakeBeacon(x=0.85, y=0.5, radius_frac=0.02, enabled=True)
    rng = np.random.default_rng(0)
    cmd = None
    for i in range(int(4 * 30)):
        t = i / 30.0
        frame = np.clip(40 + rng.normal(0, 8, (360, 640, 3)), 0, 255).astype(np.uint8)
        b.draw(frame, t)
        cmd = f.update(frame, t)
    assert cmd.mode == Mode.FOLLOW and 0 < cmd.yaw <= 0.35


# ------------------------------------------------------------------ plain walls

def test_wall_filling_the_view_is_caught():
    base, det = texture(), LoomingDetector()
    for i in range(10):
        det.update(base, i / FPS)                     # normal, detailed view
    assert not det.blind and not det.blanked
    wall = np.full_like(base, 150)
    hits = [det.update(wall, (10 + i) / FPS) or det.blanked for i in range(3)]
    assert det.blind and any(hits)


def test_blind_view_forbids_forward_but_allows_turn_and_back():
    gov = SafetyGovernor(GovernorConfig(rest_after_s=0))
    cmds, t = run(gov, 2.0, yaw=0.3, pitch=0.3)
    assert cmds[-1].pitch > 0
    cmds = []
    for i in range(30):
        t += 1 / FPS
        cmds.append(gov.step(t, Hit(), 0.3, 0.3, False, blind=True))
    assert cmds[-1].pitch == 0 and cmds[-1].yaw > 0
    back = gov.step(t + 1 / FPS, Hit(), 0.0, -0.3, False, blind=True)
    for i in range(30):
        back = gov.step(t + (i + 2) / FPS, Hit(), 0.0, -0.3, False, blind=True)
    assert back.pitch < 0

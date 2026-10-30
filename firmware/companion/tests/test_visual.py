"""Tests for the budget camera-follow logic, including a toy vertical dynamics model."""

import math

from follow.visual import RC_MAX, RC_MID, RC_MIN, Observation, State, VisualConfig, VisualFollower


def obs(t, found=True, cx=0.0, area=None, h=1.2, **kw):
    cfg = VisualConfig()
    return Observation(t, found, cx=cx, area_frac=cfg.target_area_frac if area is None else area, height_m=h, **kw)


def test_idle_until_long_press_and_needs_height_sensor():
    f = VisualFollower()
    out = f.update(obs(0.0))
    assert out.state == State.IDLE and out.arm == RC_MIN and out.throttle == RC_MIN
    # No height reading: refuse to arm.
    f2 = VisualFollower()
    out = f2.update(Observation(0.0, True, height_m=None, button_long=True))
    assert out.state == State.IDLE
    # With a reading: arm and start taking off.
    out = f.update(obs(0.05, h=0.0, button_long=True))
    assert out.state == State.TAKEOFF and out.arm == RC_MAX


def test_yaw_centres_blob_with_deadband():
    f = VisualFollower()
    f.update(obs(0.0, button_long=True))
    f.state = State.FOLLOW
    assert f.update(obs(0.1, cx=0.05)).yaw == RC_MID            # inside deadband
    right = f.update(obs(0.2, cx=0.6)).yaw
    left = f.update(obs(0.3, cx=-0.6)).yaw
    assert right > RC_MID and left < RC_MID
    assert right - RC_MID == RC_MID - left
    assert f.update(obs(0.4, cx=1.0)).yaw == RC_MID + VisualConfig().yaw_max  # saturates


def test_pitch_from_apparent_size():
    cfg = VisualConfig()
    f = VisualFollower(cfg)
    f.update(obs(0.0, button_long=True))
    f.state = State.FOLLOW
    assert f.update(obs(0.1, area=cfg.target_area_frac)).pitch == RC_MID
    far = f.update(obs(0.2, area=cfg.target_area_frac / 3)).pitch
    near = f.update(obs(0.3, area=cfg.target_area_frac * 3)).pitch
    assert far > RC_MID > near, "too far -> pitch forward, too close -> pitch back"
    assert far - RC_MID == RC_MID - near
    assert f.update(obs(0.4, area=cfg.target_area_frac * 1.1)).pitch == RC_MID  # deadband


def test_lost_target_search_then_land():
    cfg = VisualConfig()
    f = VisualFollower(cfg)
    f.update(obs(0.0, button_long=True))
    f.state = State.FOLLOW
    f.update(obs(0.1))
    t = 0.1
    seen_states = []
    while t < 12.0:
        t += 0.05
        seen_states.append(f.update(obs(t, found=False)).state)
    assert State.SEARCH in seen_states
    assert seen_states[-1] in (State.LAND, State.IDLE)
    first_search = next(i for i, s in enumerate(seen_states) if s == State.SEARCH)
    assert first_search * 0.05 <= cfg.lost_search_after_s + 0.1
    # While searching it turns gently and keeps sticks otherwise centred.
    f2 = VisualFollower(cfg)
    f2.update(obs(0.0, button_long=True))
    f2.state = State.SEARCH
    out = f2.update(obs(0.1, found=False))
    assert out.yaw == RC_MID + cfg.search_yaw and out.pitch == RC_MID and out.roll == RC_MID


def test_short_press_lands_and_flight_timer_lands():
    cfg = VisualConfig(flight_time_limit_s=5.0)
    f = VisualFollower(cfg)
    f.update(obs(0.0, button_long=True))
    f.state = State.FOLLOW
    assert f.update(obs(1.0, button_short=True)).state == State.LAND

    f = VisualFollower(cfg)
    f.update(obs(0.0, button_long=True))
    f.state = State.FOLLOW
    assert f.update(obs(4.9)).state == State.FOLLOW
    assert f.update(obs(5.1)).state == State.LAND


def test_height_sensor_dropout_forces_blind_landing_and_disarm():
    cfg = VisualConfig()
    f = VisualFollower(cfg)
    f.update(obs(0.0, button_long=True))
    f.state = State.FOLLOW
    f.update(obs(0.1))
    t, states, throttles = 0.1, [], []
    while t < 8.0:
        t += 0.05
        out = f.update(Observation(t, True, height_m=None))
        states.append(out.state)
        throttles.append(out.throttle)
    assert State.LAND in states
    assert states[-1] == State.IDLE
    # Throttle ramps down monotonically during the blind landing.
    land_thr = [th for s, th in zip(states, throttles) if s == State.LAND]
    assert all(b <= a for a, b in zip(land_thr, land_thr[1:]))


def simulate_vertical(cfg: VisualConfig, duration=20.0, dt=0.02, press_land_at=None):
    """Toy 1-D model: thrust proportional to (throttle - hover), gravity balanced at hover."""
    f = VisualFollower(cfg)
    h, v, t = 0.0, 0.0, 0.0
    log = []
    f.update(Observation(t, True, area_frac=cfg.target_area_frac, height_m=h, button_long=True))
    while t < duration:
        t += dt
        short = press_land_at is not None and abs(t - press_land_at) < dt / 2
        out = f.update(Observation(t, True, area_frac=cfg.target_area_frac, height_m=max(h, 0.03), button_short=short))
        if out.arm == RC_MAX:
            accel = (out.throttle - cfg.hover_throttle) * 0.02  # m/s^2 per us
        else:
            accel = -9.81 if h > 0 else 0.0
        v = v + accel * dt - 0.5 * v * dt  # a little drag
        h = max(0.0, h + v * dt)
        if h <= 0.0:
            v = 0.0
        log.append((t, h, out.throttle, out.state))
    return log


def test_takeoff_reaches_and_holds_target_height():
    cfg = VisualConfig()
    log = simulate_vertical(cfg, duration=20.0)
    heights = [h for _, h, _, _ in log]
    settled = heights[len(heights) // 2 :]
    assert abs(sum(settled) / len(settled) - cfg.target_height_m) < 0.15
    assert max(settled) - min(settled) < 0.4
    assert max(heights) < cfg.target_height_m + 0.6, "no big overshoot"
    assert all(th <= cfg.throttle_max for _, _, th, _ in log)
    assert log[-1][3] == State.FOLLOW


def test_landing_descends_and_disarms():
    cfg = VisualConfig()
    log = simulate_vertical(cfg, duration=30.0, press_land_at=12.0)
    states = [s for _, _, _, s in log]
    assert State.LAND in states
    assert states[-1] == State.IDLE
    # Descent rate during LAND stays gentle.
    land = [(t, h) for t, h, _, s in log if s == State.LAND]
    rates = [(h0 - h1) / (t1 - t0) for (t0, h0), (t1, h1) in zip(land, land[1:])]
    assert max(rates) < 1.0

"""Closed-loop checks: tracking quality, quietness proxy (setpoint churn), and failsafes."""

from follow.config import FollowConfig
from follow.safety import Mode
from follow.sim import simulate, stand_then_walk, walk_loop, walk_straight


def settled(xs, frac=1 / 3):
    return xs[int(len(xs) * frac):]


def test_straight_walk_tracks_offset():
    cfg = FollowConfig()
    r = simulate(walk_straight(1.4), 60, cfg)
    he = settled(r.horizontal_errors(cfg.controller.follow_distance_m))
    ve = settled(r.height_errors(cfg.controller.follow_height_m))
    assert sum(he) / len(he) < 1.5
    assert max(he) < 3.5
    assert sum(ve) / len(ve) < 0.6
    assert all(m == Mode.FOLLOW for m in r.modes)


def test_loop_walk_tracks_offset():
    cfg = FollowConfig()
    r = simulate(walk_loop(15.0, 1.4), 90, cfg)
    he = settled(r.horizontal_errors(cfg.controller.follow_distance_m))
    assert sum(he) / len(he) < 2.0
    assert max(he) < 4.0


def test_stationary_wearer_produces_almost_no_setpoint_churn():
    """Quietness proxy: a standing wearer with noisy ranges should not make the drone fidget."""
    cfg = FollowConfig()
    r = simulate(stand_then_walk(wait_s=60), 60, cfg, range_noise_m=0.10)
    # Mostly small yaw trims; well under the 20 Hz loop rate.
    assert r.setpoint_change_rate_hz() < 5.0
    # And the drone itself barely moves.
    drift = max((d - r.drone[0]).norm() for d in r.drone)
    assert drift < 1.5


def test_drone_motion_is_smooth_while_walking():
    """Quietness proxy: the drone's own speed never spikes while following a walker."""
    cfg = FollowConfig()
    r = simulate(walk_straight(1.4), 60, cfg)
    dt = 1.0 / cfg.loop_hz
    speeds = [(b - a).norm() / dt for a, b in zip(r.drone, r.drone[1:])]
    assert max(speeds) < cfg.controller.max_horizontal_speed_mps * 1.2
    accels = [abs(b - a) / dt for a, b in zip(speeds, speeds[1:])]
    assert max(accels[40:]) < 4.0  # m/s^2, after the initial pick-up


def test_link_dropout_holds_then_rtls_then_recovers():
    cfg = FollowConfig()
    r = simulate(walk_straight(1.4), 60, cfg, band_dropout=(20.0, 32.0))
    modes_by_t = dict(zip([round(t, 2) for t in r.times], r.modes))
    assert modes_by_t[19.0] == Mode.FOLLOW
    assert modes_by_t[24.0] == Mode.HOLD
    assert modes_by_t[31.0] == Mode.RTL
    # After the band returns, the estimator's stale position may be far away; the
    # runner should go back to FOLLOW within a few seconds.
    assert Mode.FOLLOW in [modes_by_t[t] for t in (35.0, 36.0, 37.0, 38.0)]


def test_low_battery_triggers_rtl_then_land():
    cfg = FollowConfig()
    r = simulate(walk_straight(1.4), 60, cfg, battery_fn=lambda t: 100 - t * 2)  # 2 %/s
    modes_by_t = dict(zip([round(t, 2) for t in r.times], r.modes))
    assert modes_by_t[30.0] == Mode.FOLLOW
    assert modes_by_t[40.0] == Mode.RTL
    assert modes_by_t[45.0] == Mode.LAND

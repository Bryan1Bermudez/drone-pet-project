import math

import pytest

from follow.config import ControllerConfig
from follow.controller import FollowController
from follow.estimator import DroneState, WearerEstimate
from follow.geometry import Vec3


def wearer_at(p: Vec3, t: float) -> WearerEstimate:
    return WearerEstimate(p, 0.0, 5.0, t, 1.0)


def test_deadband_suppresses_small_errors():
    cfg = ControllerConfig(position_deadband_m=0.75)
    c = FollowController(cfg)
    # Drone already at the ideal spot: 3 m behind (west, since wearer heading defaults to
    # pointing away from the drone) and 2.5 m up.
    drone = DroneState(Vec3(-3.0, 0.0, -2.5), 0.0, 2.5)
    c.update(wearer_at(Vec3(0, 0, 0), 0.0), drone, 0.05)
    changes_before = c.setpoint_changes
    # Wearer shuffles 0.4 m: well inside the deadband.
    for i in range(1, 40):
        c.update(wearer_at(Vec3(0.4, 0, 0), i * 0.05), drone, 0.05)
    assert c.setpoint_changes == changes_before


def test_large_error_moves_setpoint_toward_desired_with_speed_limit():
    cfg = ControllerConfig(max_horizontal_speed_mps=2.0, max_accel_mps2=100.0)
    c = FollowController(cfg)
    drone = DroneState(Vec3(-3.0, 0.0, -2.5), 0.0, 2.5)
    dt = 0.05
    # Wearer has moved 10 m east; the desired setpoint is 10 m away.
    sp0 = c.update(wearer_at(Vec3(0, 0, 0), 0.0), drone, dt)
    sp1 = c.update(wearer_at(Vec3(10, 0, 0), 0.3), drone, dt)
    assert sp1.changed
    step = (sp1.position - sp0.position).horizontal_norm()
    assert step <= cfg.max_horizontal_speed_mps * dt + 1e-6
    assert sp1.position.x > sp0.position.x


def test_acceleration_limit_ramps_setpoint_velocity():
    cfg = ControllerConfig(max_horizontal_speed_mps=5.0, max_accel_mps2=1.0)
    c = FollowController(cfg)
    drone = DroneState(Vec3(-3.0, 0.0, -2.5), 0.0, 2.5)
    dt = 0.1
    prev = c.update(wearer_at(Vec3(0, 0, 0), 0.0), drone, dt).position
    steps = []
    for i in range(1, 6):
        sp = c.update(wearer_at(Vec3(50, 0, 0), i * dt), drone, dt).position
        steps.append((sp - prev).horizontal_norm())
        prev = sp
    # Each step grows by at most accel*dt*dt and is monotonic non-decreasing.
    for a, b in zip(steps, steps[1:]):
        assert b >= a - 1e-9
        assert b - a <= cfg.max_accel_mps2 * dt * dt + 1e-9


def test_follow_offset_is_behind_direction_of_travel_with_lead():
    cfg = ControllerConfig(follow_distance_m=3.0, follow_height_m=2.5, lead_time_s=1.0)
    c = FollowController(cfg)
    # Drone starts east of the wearer; after the wearer walks north the offset must
    # swing round to be south (behind) of them, regardless of where the drone began.
    drone = DroneState(Vec3(0.0, 3.0, -2.5), 0.0, 2.5)
    # Wearer walking north (+x) at 1.4 m/s for 4 s at 20 Hz.
    for i in range(80):
        t = i * 0.05
        c.update(wearer_at(Vec3(1.4 * t, 0, 0), t), drone, 0.05)
    wearer_now = Vec3(1.4 * 4.0, 0, 0)
    desired = c.desired_position(wearer_at(wearer_now, 4.0), drone)
    # lead (~1.4 m ahead) minus 3 m behind = ~1.6 m behind the wearer along x
    assert desired.x == pytest.approx(wearer_now.x + 1.4 - 3.0, abs=0.5)
    assert abs(desired.y) < 0.3
    assert desired.z == -2.5
    assert c.wearer_velocity.x == pytest.approx(1.4, abs=0.2)


def test_heading_ignores_jitter_from_a_stationary_wearer():
    cfg = ControllerConfig()
    c = FollowController(cfg)
    drone = DroneState(Vec3(-3.0, 0.0, -2.5), 0.0, 2.5)
    import random

    rng = random.Random(3)
    for i in range(100):
        t = i * 0.05
        jitter = Vec3(rng.gauss(0, 0.3), rng.gauss(0, 0.3), 0)
        c.update(wearer_at(jitter, t), drone, 0.05)
    # Heading stays at the default (pointing from drone through wearer: north) and
    # the velocity estimate stays near zero, so the drone does not start circling.
    assert c.wearer_velocity.horizontal_norm() < 0.2
    assert abs(math.degrees(c._heading_or_default(wearer_at(Vec3(), 5.0), drone))) < 15


def test_yaw_points_at_wearer_with_deadband():
    cfg = ControllerConfig(yaw_deadband_deg=10, max_yaw_rate_dps=1000)
    c = FollowController(cfg)
    drone = DroneState(Vec3(0, 0, -2.5), 0.0, 2.5)
    sp = c.update(wearer_at(Vec3(5, 5, 0), 0.0), drone, 0.1)  # wearer at 45 deg
    assert math.degrees(sp.yaw_rad) > 40
    # Small wiggle inside the deadband does not change yaw.
    yaw_before = sp.yaw_rad
    sp2 = c.update(wearer_at(Vec3(5, 5.4, 0), 0.5), drone, 0.1)
    assert sp2.yaw_rad == yaw_before

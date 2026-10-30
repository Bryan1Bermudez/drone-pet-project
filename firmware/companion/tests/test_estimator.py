import math

import pytest

from follow.config import EstimatorConfig
from follow.estimator import DroneState, RangeSample, WearerEstimator
from follow.geometry import Vec3


def make(follow_height=2.5, **kw):
    return WearerEstimator(EstimatorConfig(**kw), follow_height)


def ranges_for(drone: DroneState, wearer: Vec3, baseline: float) -> RangeSample:
    out = []
    for side in (-1.0, 1.0):
        c, s = math.cos(drone.yaw_rad), math.sin(drone.yaw_rad)
        off_body_right = side * baseline / 2
        an = Vec3(drone.position.x - off_body_right * s, drone.position.y + off_body_right * c, drone.position.z)
        out.append((wearer - an).norm())
    return RangeSample(0.0, out[0], out[1])


def test_bearing_sign_and_magnitude():
    est = make()
    drone = DroneState(Vec3(0, 0, -2.5), 0.0, 2.5)
    # Band 45 deg to the right of a north-facing drone: right anchor is closer.
    wearer_right = Vec3(5.0, 5.0, 0.0)
    s = ranges_for(drone, wearer_right, 0.30)
    assert s.range_right_m < s.range_left_m
    r, horiz, theta = est.bearing_from_ranges(s.range_left_m, s.range_right_m, 2.5)
    assert r == pytest.approx(math.sqrt(50 + 2.5**2), abs=0.05)
    assert horiz == pytest.approx(math.sqrt(50), abs=0.05)
    assert theta > 0  # positive = right
    assert math.degrees(theta) == pytest.approx(45.0, abs=1.0)


@pytest.mark.parametrize("yaw_deg", [0, 45, 90, 180, -120])
@pytest.mark.parametrize("wearer", [Vec3(6, 0, 0), Vec3(4, 3, 0), Vec3(2, -5, 0)])
def test_end_to_end_recovers_wearer_position_in_front(yaw_deg, wearer):
    """Wearer within the front hemisphere of the drone is recovered within ~0.5 m."""
    yaw = math.radians(yaw_deg)
    drone = DroneState(Vec3(0, 0, -2.5), yaw, 2.5)
    # Place the wearer at the given body-frame offset rotated into NED so it stays in front.
    c, s = math.cos(yaw), math.sin(yaw)
    w_ned = Vec3(wearer.x * c - wearer.y * s, wearer.x * s + wearer.y * c, 0.0)
    est = make(lowpass_alpha=1.0, range_lowpass_alpha=1.0)
    e = est.update(ranges_for(drone, w_ned, 0.30), drone)
    assert e is not None
    assert (e.position - w_ned).horizontal_norm() < 0.5


def test_invalid_ranges_are_ignored_and_confidence_decays():
    est = make()
    drone = DroneState(Vec3(0, 0, -2.5), 0.0, 2.5)
    e0 = est.update(ranges_for(drone, Vec3(5, 0, 0), 0.30), drone)
    c0 = e0.confidence
    e1 = est.update(RangeSample(1.0, float("nan"), 5.0), drone)
    assert e1.position == e0.position
    assert e1.confidence < c0
    e2 = est.update(RangeSample(2.0, 0.0, 5.0), drone)
    assert e2.position == e0.position
    e3 = est.update(RangeSample(3.0, 99.0, 99.0), drone)
    assert e3.position == e0.position


def test_single_outlier_rejected_but_persistent_jump_accepted():
    est = make(lowpass_alpha=1.0, range_lowpass_alpha=1.0, outlier_jump_m=3.0, outlier_confirm_count=3)
    drone = DroneState(Vec3(0, 0, -2.5), 0.0, 2.5)
    est.update(ranges_for(drone, Vec3(5, 0, 0), 0.30), drone)

    far = ranges_for(drone, Vec3(15, 0, 0), 0.30)
    e = est.update(far, drone)
    assert e.position.x == pytest.approx(5.0, abs=0.3)  # first jump sample rejected
    est.update(far, drone)
    e = est.update(far, drone)
    assert e.position.x == pytest.approx(15.0, abs=0.3)  # third agreeing sample accepted


def test_lowpass_filter_smooths():
    est = make(lowpass_alpha=0.5, range_lowpass_alpha=1.0)
    drone = DroneState(Vec3(0, 0, -2.5), 0.0, 2.5)
    est.update(ranges_for(drone, Vec3(5, 0, 0), 0.30), drone)
    e = est.update(ranges_for(drone, Vec3(6, 0, 0), 0.30), drone)
    assert 5.3 < e.position.x < 5.7

"""Wearer position estimator from two UWB ranges.

Geometry (body frame, x forward, y right):
    anchor L at (0, -d/2), anchor R at (0, +d/2), band at range r and bearing theta
    measured from the drone's nose, positive to the right.

    rL^2 - rR^2 = 2 * d * r * sin(theta)       (far-field approximation, r >> d)

(A band on the right is closer to the right anchor, so rR < rL and sin(theta) > 0.)

Two anchors on one axis cannot distinguish a band in front from one behind. We
resolve the ambiguity by continuity with the previous estimate; a stale estimator
defaults to "in front", which is where the controller tries to keep the wearer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .config import EstimatorConfig
from .geometry import Vec3, body_to_ned, clamp


@dataclass
class DroneState:
    position: Vec3  # NED, metres
    yaw_rad: float  # 0 = north, positive clockwise viewed from above
    altitude_agl_m: float  # height above ground, metres (positive up)


@dataclass
class RangeSample:
    t: float
    range_left_m: float
    range_right_m: float


@dataclass
class WearerEstimate:
    position: Vec3  # NED
    bearing_body_rad: float  # bearing from drone nose, +right
    range_m: float
    t: float
    confidence: float  # 0..1, drops as outliers are rejected or data ages


class WearerEstimator:
    def __init__(self, cfg: EstimatorConfig, follow_height_m: float):
        self.cfg = cfg
        self.follow_height_m = follow_height_m
        self._estimate: Optional[WearerEstimate] = None
        self._pending_jump: list[Vec3] = []
        self._range_filt: Optional[float] = None
        self._diff_filt: Optional[float] = None

    @property
    def estimate(self) -> Optional[WearerEstimate]:
        return self._estimate

    def reset(self) -> None:
        self._estimate = None
        self._pending_jump.clear()
        self._range_filt = None
        self._diff_filt = None

    def _filter_ranges(self, r_left: float, r_right: float) -> tuple[float, float]:
        """Low-pass the mean range and the L-R difference; return (left, right) smoothed."""
        mean = 0.5 * (r_left + r_right)
        diff = r_left - r_right
        a = self.cfg.range_lowpass_alpha
        if self._range_filt is None or self._diff_filt is None:
            self._range_filt, self._diff_filt = mean, diff
        else:
            self._range_filt += a * (mean - self._range_filt)
            self._diff_filt += a * (diff - self._diff_filt)
        return self._range_filt + 0.5 * self._diff_filt, self._range_filt - 0.5 * self._diff_filt

    # ------------------------------------------------------------------ #
    def bearing_from_ranges(
        self, r_left: float, r_right: float, height_diff_m: float = 0.0
    ) -> tuple[float, float, float]:
        """Return (mean slant range, horizontal distance, bearing) from the two anchor ranges.

        The range difference is produced by the *horizontal* offset of the anchors, so the
        bearing must be normalised by the horizontal distance, not the slant range.
        """
        r = 0.5 * (r_left + r_right)
        d = self.cfg.anchor_baseline_m
        horiz = math.sqrt(max(r * r - height_diff_m * height_diff_m, 0.0))
        if horiz <= d:
            return r, horiz, 0.0
        s = (r_left**2 - r_right**2) / (2.0 * d * horiz)
        return r, horiz, math.asin(clamp(s, -1.0, 1.0))

    def update(self, sample: RangeSample, drone: DroneState) -> Optional[WearerEstimate]:
        if not self._valid(sample):
            self._decay(sample.t)
            return self._estimate

        # The band is roughly follow_height below the drone (no altitude sensor on the band).
        dz = min(self.follow_height_m, drone.altitude_agl_m)
        r_left, r_right = self._filter_ranges(sample.range_left_m, sample.range_right_m)
        r, horiz, theta = self.bearing_from_ranges(r_left, r_right, dz)

        # Front/back ambiguity: theta and (pi - theta) give the same range difference.
        candidates = [theta, math.pi - theta]
        if self._estimate is None:
            chosen = theta  # assume in front
        else:
            chosen = min(candidates, key=lambda th: self._distance_to_previous(horiz, th, drone))

        fwd, right = horiz * math.cos(chosen), horiz * math.sin(chosen)
        n, e = body_to_ned(fwd, right, drone.yaw_rad)
        raw = Vec3(drone.position.x + n, drone.position.y + e, drone.position.z + dz)

        if self._estimate is None:
            self._estimate = WearerEstimate(raw, chosen, r, sample.t, 0.5)
            return self._estimate

        jump = (raw - self._estimate.position).norm()
        if jump > self.cfg.outlier_jump_m:
            self._pending_jump.append(raw)
            if len(self._pending_jump) < self.cfg.outlier_confirm_count:
                self._decay(sample.t)
                return self._estimate
            # Several samples agree: accept the new location outright.
            raw = self._pending_jump[-1]
            self._pending_jump.clear()
            filtered = raw
        else:
            self._pending_jump.clear()
            a = self.cfg.lowpass_alpha
            p = self._estimate.position
            filtered = Vec3(
                p.x + a * (raw.x - p.x),
                p.y + a * (raw.y - p.y),
                p.z + a * (raw.z - p.z),
            )

        conf = min(1.0, self._estimate.confidence + 0.1)
        self._estimate = WearerEstimate(filtered, chosen, r, sample.t, conf)
        return self._estimate

    # ------------------------------------------------------------------ #
    def _valid(self, s: RangeSample) -> bool:
        for r in (s.range_left_m, s.range_right_m):
            if not math.isfinite(r) or r <= 0.0 or r > self.cfg.max_range_m:
                return False
        return abs(s.range_left_m - s.range_right_m) <= self.cfg.anchor_baseline_m * 1.5

    def _decay(self, t: float) -> None:
        if self._estimate is not None:
            self._estimate = WearerEstimate(
                self._estimate.position,
                self._estimate.bearing_body_rad,
                self._estimate.range_m,
                self._estimate.t,
                max(0.0, self._estimate.confidence - 0.1),
            )

    def _distance_to_previous(self, horiz: float, theta: float, drone: DroneState) -> float:
        assert self._estimate is not None
        n, e = body_to_ned(horiz * math.cos(theta), horiz * math.sin(theta), drone.yaw_rad)
        cand = Vec3(drone.position.x + n, drone.position.y + e, self._estimate.position.z)
        return (cand - self._estimate.position).horizontal_norm()

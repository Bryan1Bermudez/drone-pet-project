"""Lazy follow controller.

Turns a wearer estimate into a drone position + yaw setpoint, moving the setpoint only
when the error is large enough to matter and never faster than the configured limits.
Fewer, gentler setpoint changes mean fewer throttle transients: quieter and cheaper.

Pieces:
- Wearer velocity from a sliding window of estimates (smooth, ignores jitter).
- Desired position = wearer + lead * velocity + offset behind the direction of travel.
- Deadband with hysteresis: start moving above `position_deadband_m`, stop below
  `position_settle_m`.
- Speed and acceleration limits on how fast the setpoint itself moves.
- Yaw toward the wearer with its own deadband.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from .config import ControllerConfig
from .estimator import DroneState, WearerEstimate
from .geometry import Vec3, clamp, wrap_angle


@dataclass
class Setpoint:
    position: Vec3  # NED
    yaw_rad: float
    changed: bool  # True if this cycle moved the setpoint (useful for metrics)


class FollowController:
    def __init__(self, cfg: ControllerConfig):
        self.cfg = cfg
        self._setpoint: Optional[Vec3] = None
        self._setpoint_yaw: float = 0.0
        self._setpoint_vel = Vec3()
        self._pursuing = False
        self._wearer_heading: Optional[float] = None
        self._wearer_vel = Vec3()
        self._history: Deque[tuple[float, Vec3]] = deque()
        self._moving_since: Optional[float] = None
        self.setpoint_changes = 0

    def reset(self) -> None:
        self._setpoint = None
        self._setpoint_vel = Vec3()
        self._pursuing = False
        self._wearer_heading = None
        self._wearer_vel = Vec3()
        self._history.clear()
        self._moving_since = None
        self.setpoint_changes = 0

    @property
    def wearer_velocity(self) -> Vec3:
        return self._wearer_vel

    @property
    def wearer_moving(self) -> bool:
        return self._wearer_vel.horizontal_norm() >= 0.5 * self.cfg.wearer_speed_for_heading_mps

    # ------------------------------------------------------------------ #
    def desired_position(self, wearer: WearerEstimate, drone: DroneState) -> Vec3:
        """Where the drone should be: behind the wearer (relative to their travel) and above."""
        self._update_wearer_motion(wearer)
        heading = self._heading_or_default(wearer, drone)
        lead = self._wearer_vel * self.cfg.lead_time_s
        back_n = -math.cos(heading) * self.cfg.follow_distance_m
        back_e = -math.sin(heading) * self.cfg.follow_distance_m
        return Vec3(
            wearer.position.x + lead.x + back_n,
            wearer.position.y + lead.y + back_e,
            wearer.position.z - self.cfg.follow_height_m,  # up is negative z
        )

    def update(self, wearer: WearerEstimate, drone: DroneState, dt: float) -> Setpoint:
        desired = self.desired_position(wearer, drone)

        if self._setpoint is None:
            # First cycle: hold where we are, then glide toward the desired point.
            self._setpoint = drone.position
            self._setpoint_yaw = drone.yaw_rad

        err = desired - self._setpoint
        horiz_err = err.horizontal_norm()
        vert_err = abs(err.z)
        moved = False

        if self.wearer_moving:
            # A walking wearer gets continuous, rate-limited tracking. Steady cruising is
            # quieter than the stop-and-go a deadband would produce here.
            self._pursuing = True
        elif not self._pursuing:
            if horiz_err > self.cfg.position_deadband_m or vert_err > self.cfg.height_deadband_m:
                self._pursuing = True
        else:
            if horiz_err < self.cfg.position_settle_m and vert_err < self.cfg.position_settle_m:
                self._pursuing = False
                self._setpoint_vel = Vec3()

        if self._pursuing:
            new_sp = self._rate_limited_step(self._setpoint, desired, dt)
            if (new_sp - self._setpoint).norm() > 1e-6:
                self._setpoint = new_sp
                moved = True

        # Yaw: point the nose at the wearer, with a deadband.
        to_wearer = wearer.position - drone.position
        if to_wearer.horizontal_norm() > 0.5:
            desired_yaw = math.atan2(to_wearer.y, to_wearer.x)
            dyaw = wrap_angle(desired_yaw - self._setpoint_yaw)
            if abs(dyaw) > math.radians(self.cfg.yaw_deadband_deg):
                max_step = math.radians(self.cfg.max_yaw_rate_dps) * dt
                self._setpoint_yaw = wrap_angle(self._setpoint_yaw + clamp(dyaw, -max_step, max_step))
                moved = True

        if moved:
            self.setpoint_changes += 1
        return Setpoint(self._setpoint, self._setpoint_yaw, moved)

    # ------------------------------------------------------------------ #
    def _update_wearer_motion(self, wearer: WearerEstimate) -> None:
        """Sliding-window velocity and a low-passed heading."""
        self._history.append((wearer.t, wearer.position))
        while self._history and wearer.t - self._history[0][0] > self.cfg.velocity_window_s:
            self._history.popleft()
        if len(self._history) < 2:
            return
        t0, p0 = self._history[0]
        span = wearer.t - t0
        if span < 0.5 * self.cfg.velocity_window_s:
            return
        d = wearer.position - p0
        vel = Vec3(d.x / span, d.y / span, 0.0)
        a = self.cfg.heading_lowpass_alpha

        looks_moving = d.horizontal_norm() >= self.cfg.heading_min_displacement_m and (
            vel.horizontal_norm() >= self.cfg.wearer_speed_for_heading_mps
        )
        if looks_moving:
            if self._moving_since is None:
                self._moving_since = wearer.t
        else:
            self._moving_since = None
        moving = self._moving_since is not None and (
            wearer.t - self._moving_since >= self.cfg.moving_confirm_s
        )
        if moving:
            self._wearer_vel = self._wearer_vel + (vel - self._wearer_vel) * a
            new_heading = math.atan2(d.y, d.x)
            if self._wearer_heading is None:
                self._wearer_heading = new_heading
            else:
                dh = wrap_angle(new_heading - self._wearer_heading)
                self._wearer_heading = wrap_angle(self._wearer_heading + a * dh)
        else:
            # Not confirmed moving: no feed-forward lead, keep the last heading. Estimate
            # jitter from a standing wearer must not turn into drone motion.
            self._wearer_vel = self._wearer_vel * (1.0 - a)
            if self._wearer_vel.horizontal_norm() < 0.05:
                self._wearer_vel = Vec3()

    def _heading_or_default(self, wearer: WearerEstimate, drone: DroneState) -> float:
        if self._wearer_heading is not None:
            return self._wearer_heading
        # No travel history yet: stay on the side we are already on.
        rel = drone.position - wearer.position
        if rel.horizontal_norm() > 0.5:
            self._wearer_heading = math.atan2(-rel.y, -rel.x)
        else:
            self._wearer_heading = drone.yaw_rad
        return self._wearer_heading

    def _rate_limited_step(self, current: Vec3, target: Vec3, dt: float) -> Vec3:
        cfg = self.cfg
        err = target - current
        h = err.horizontal_norm()
        if h > 1e-6:
            vh = min(cfg.max_horizontal_speed_mps, h / max(dt, 1e-3))
            vx, vy = err.x / h * vh, err.y / h * vh
        else:
            vx = vy = 0.0
        vz = clamp(err.z / max(dt, 1e-3), -cfg.max_vertical_speed_mps, cfg.max_vertical_speed_mps)
        desired_vel = Vec3(vx, vy, vz)

        # Acceleration limit on the setpoint velocity.
        dv = desired_vel - self._setpoint_vel
        max_dv = cfg.max_accel_mps2 * dt
        dvn = dv.norm()
        if dvn > max_dv:
            dv = dv * (max_dv / dvn)
        self._setpoint_vel = self._setpoint_vel + dv

        step = self._setpoint_vel * dt
        # Do not overshoot the target.
        if step.horizontal_norm() > h:
            step = Vec3(err.x, err.y, step.z)
        if abs(step.z) > abs(err.z):
            step = step.with_z(err.z)
        return current + step

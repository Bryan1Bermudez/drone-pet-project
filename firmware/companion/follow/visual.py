"""Follow logic for the budget camera build.

Pure math, no hardware: blob position/size + height -> RC stick values + state.
`firmware/drone-esp32cam/src/follow_logic.cpp` is a line-for-line port of this file;
when you change one, change the other and run the tests here.

Stick values are Betaflight RC microseconds: 1000..2000, centre 1500.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

RC_MIN, RC_MID, RC_MAX = 1000, 1500, 2000


class State(str, Enum):
    IDLE = "IDLE"          # disarmed on the floor
    TAKEOFF = "TAKEOFF"    # climbing to target height
    FOLLOW = "FOLLOW"      # target in view
    SEARCH = "SEARCH"      # target lost briefly: hold, yaw slowly
    LAND = "LAND"          # throttle ramp down, then disarm


@dataclass
class VisualConfig:
    target_height_m: float = 1.2
    hover_throttle: int = 1450          # tune: stick value that just hovers
    kp_height: float = 300.0            # us per metre
    kd_height: float = 150.0            # us per (m/s)
    ki_height: float = 60.0             # us per (m*s)
    i_limit: float = 0.5
    throttle_min: int = 1100
    throttle_max: int = 1750            # soft ceiling
    takeoff_ramp_us_per_s: float = 250.0
    land_descent_mps: float = 0.35
    land_cutoff_height_m: float = 0.12
    land_ramp_us_per_s: float = 150.0   # used when height sensor is dead

    # Yaw: centre the blob horizontally. cx is -1 (left edge) .. +1 (right edge).
    kp_yaw: float = 250.0
    yaw_deadband: float = 0.10
    yaw_max: int = 180
    search_yaw: int = 60                # gentle turn while searching

    # Pitch: keep apparent size. area_frac = blob pixels / frame pixels.
    target_area_frac: float = 0.004     # ~2 m with 3 LEDs at 160x120; calibrate
    kp_pitch: float = 120.0             # us per unit of ln(target/area)
    pitch_deadband: float = 0.25        # in ln units (~ +-28 % distance)
    pitch_max: int = 110

    min_blob_pixels: int = 6
    lost_search_after_s: float = 0.5
    lost_land_after_s: float = 10.0
    height_timeout_s: float = 0.5
    flight_time_limit_s: float = 240.0


@dataclass
class Observation:
    t: float
    blob_found: bool
    cx: float = 0.0            # -1..1 horizontal, +right
    cy: float = 0.0            # -1..1 vertical, +down
    area_frac: float = 0.0
    height_m: Optional[float] = None   # None = no valid reading this cycle
    button_long: bool = False          # long press event this cycle
    button_short: bool = False         # short press event this cycle


@dataclass
class RcOut:
    roll: int = RC_MID
    pitch: int = RC_MID
    throttle: int = RC_MIN
    yaw: int = RC_MID
    arm: int = RC_MIN
    state: State = State.IDLE


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


@dataclass
class VisualFollower:
    cfg: VisualConfig = field(default_factory=VisualConfig)
    state: State = State.IDLE
    _t_state: float = 0.0
    _t_armed: float = 0.0
    _t_last_seen: float = 0.0
    _t_last_height: float = -1e9
    _last_height: Optional[float] = None
    _height_rate: float = 0.0
    _i_term: float = 0.0
    _throttle: float = RC_MIN
    _last_t: Optional[float] = None
    _land_target_h: float = 0.0

    # ------------------------------------------------------------------ #
    def update(self, o: Observation) -> RcOut:
        dt = 0.0 if self._last_t is None else max(0.0, min(o.t - self._last_t, 0.2))
        self._last_t = o.t
        cfg = self.cfg

        self._track_height(o, dt)
        if o.blob_found:
            self._t_last_seen = o.t

        # --- state transitions --------------------------------------------------
        if self.state == State.IDLE:
            if o.button_long and self._height_ok(o.t):
                self._enter(State.TAKEOFF, o.t)
                self._t_armed = o.t
                self._throttle = cfg.throttle_min
                self._i_term = 0.0
        else:
            if o.button_short or o.button_long:
                self._enter(State.LAND, o.t)
            elif o.t - self._t_armed > cfg.flight_time_limit_s:
                self._enter(State.LAND, o.t)
            elif not self._height_ok(o.t) and self.state != State.LAND:
                self._enter(State.LAND, o.t)

        if self.state == State.TAKEOFF:
            if self._last_height is not None and self._last_height > 0.8 * cfg.target_height_m:
                self._enter(State.FOLLOW if o.blob_found else State.SEARCH, o.t)
        elif self.state == State.FOLLOW:
            if o.t - self._t_last_seen > cfg.lost_search_after_s:
                self._enter(State.SEARCH, o.t)
        elif self.state == State.SEARCH:
            if o.blob_found:
                self._enter(State.FOLLOW, o.t)
            elif o.t - self._t_last_seen > cfg.lost_land_after_s:
                self._enter(State.LAND, o.t)

        # --- outputs -------------------------------------------------------------
        out = RcOut(state=self.state)
        if self.state == State.IDLE:
            return out

        out.arm = RC_MAX

        if self.state == State.TAKEOFF:
            # Ramp throttle up until the height loop takes over near target height.
            self._throttle = min(self._throttle + cfg.takeoff_ramp_us_per_s * dt, cfg.throttle_max)
            h = self._last_height or 0.0
            if h > 0.3 * cfg.target_height_m:
                self._throttle = self._height_loop(cfg.target_height_m, dt)
            out.throttle = int(self._throttle)
            return out

        if self.state == State.LAND:
            if self._height_ok(o.t) and self._last_height is not None:
                self._land_target_h = max(0.0, self._land_target_h - cfg.land_descent_mps * dt)
                self._throttle = self._height_loop(self._land_target_h, dt)
                if self._last_height < cfg.land_cutoff_height_m and self._land_target_h <= 0.0:
                    self._disarm()
                    return RcOut(state=State.IDLE)
            else:
                # Blind landing: ramp down and give up after the ramp hits the floor.
                self._throttle -= cfg.land_ramp_us_per_s * dt
                if self._throttle <= cfg.throttle_min:
                    self._disarm()
                    return RcOut(state=State.IDLE)
            out.throttle = int(self._throttle)
            return out

        # FOLLOW or SEARCH: hold height.
        self._throttle = self._height_loop(cfg.target_height_m, dt)
        out.throttle = int(self._throttle)

        if self.state == State.SEARCH:
            out.yaw = RC_MID + cfg.search_yaw
            return out

        # FOLLOW: yaw to centre, pitch to hold apparent size.
        if abs(o.cx) > cfg.yaw_deadband:
            yaw = cfg.kp_yaw * (o.cx - math.copysign(cfg.yaw_deadband, o.cx))
            out.yaw = int(round(RC_MID + clamp(yaw, -cfg.yaw_max, cfg.yaw_max)))

        if o.area_frac > 0.0:
            e = math.log(cfg.target_area_frac / o.area_frac)  # +ve = too far
            if abs(e) > cfg.pitch_deadband:
                pitch = cfg.kp_pitch * (e - math.copysign(cfg.pitch_deadband, e))
                out.pitch = int(round(RC_MID + clamp(pitch, -cfg.pitch_max, cfg.pitch_max)))
        return out

    # ------------------------------------------------------------------ #
    def _enter(self, s: State, t: float) -> None:
        if s == State.LAND and self._last_height is not None:
            self._land_target_h = self._last_height
        self.state = s
        self._t_state = t

    def _disarm(self) -> None:
        self.state = State.IDLE
        self._throttle = RC_MIN
        self._i_term = 0.0

    def _height_ok(self, t: float) -> bool:
        return t - self._t_last_height <= self.cfg.height_timeout_s

    def _track_height(self, o: Observation, dt: float) -> None:
        if o.height_m is None:
            return
        if self._last_height is not None and dt > 0:
            raw_rate = (o.height_m - self._last_height) / dt
            self._height_rate += 0.3 * (raw_rate - self._height_rate)
        self._last_height = o.height_m
        self._t_last_height = o.t

    def _height_loop(self, target: float, dt: float) -> float:
        cfg = self.cfg
        h = self._last_height if self._last_height is not None else target
        err = target - h
        self._i_term = clamp(self._i_term + err * dt, -cfg.i_limit, cfg.i_limit)
        u = cfg.hover_throttle + cfg.kp_height * err - cfg.kd_height * self._height_rate + cfg.ki_height * self._i_term
        return clamp(u, cfg.throttle_min, cfg.throttle_max)

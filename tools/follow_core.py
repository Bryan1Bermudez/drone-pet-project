"""Beacon following with a safety layer, for a drone flown through Turbodrone.

Used by the Turbodrone plugin (tools/turbodrone_plugin/beacon_follow.py) and tested
headless in tools/tests/test_follow_core.py.

Pieces:
  Pipeline (webcam_follow.py)   colour blobs -> blink filter -> follow logic (yaw/pitch)
  LoomingDetector               notices something in view growing fast (closing in),
                                a view too plain to judge distance, and a view that
                                suddenly goes flat (a wall filling the camera)
  SafetyGovernor                speed cap + smooth changes, back off on looming,
                                hover then land when the beacon is lost,
                                land-and-wait when the wearer stands still,
                                optional automatic relaunch when they move again.

All stick values are -1..1 (Turbodrone's DirectStrategy scale), before the drone's
speed tier is applied.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from webcam_follow import Pipeline, stick_pct  # noqa: E402


# --------------------------------------------------------------------------- looming

class LoomingDetector:
    """Estimates how fast the view is expanding (something getting closer).

    Dense optical flow between consecutive small grey frames, then a least-squares fit
    of an affine motion model over the middle of the image:
        u = a*x + b*y + c,   v = d*x + e*y + f
    (a + e) / 2 is the expansion per frame. Turning the drone moves the image
    sideways (c, f) without expanding it, so yawing does not trigger it.
    Time to contact tau = 1 / (expansion per second). Looming = tau below the limit
    for `confirm` frames in a row. Plain walls give no flow, so two extra rules cover
    them: `blind` (too little detail: forward is forbidden) and `blanked` (detail
    suddenly collapsed: treated like looming, back off).
    """

    def __init__(self, width: int = 96, height: int = 72, tau_limit_s: float = 1.2,
                 confirm: int = 2, min_texture: float = 6.0, centre: float = 0.6):
        self.size = (width, height)
        self.tau_limit_s = tau_limit_s
        self.confirm = confirm
        self.min_texture = min_texture
        self.centre = centre
        self._prev = None
        self._prev_t = None
        self._streak = 0
        self.last_tau: Optional[float] = None
        self.last_rate = 0.0
        self.last_texture = 0.0
        self.last_side_rate = 0.0     # picture sliding sideways, image widths per second (+ = right)
        self.blind = False            # too little detail to judge distance
        self.blanked = False          # view suddenly went flat: something filling the camera
        self._texture_baseline: Optional[float] = None
        self._blank_streak = 0

    def reset(self) -> None:
        self._prev = None
        self._prev_t = None
        self._streak = 0

    def update(self, img_bgr: np.ndarray, t: float) -> bool:
        import cv2
        grey = cv2.cvtColor(cv2.resize(img_bgr, self.size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        prev, prev_t = self._prev, self._prev_t
        self._prev, self._prev_t = grey, t
        self.last_tau = None
        self._update_texture(grey)
        if prev is None or prev_t is None or t <= prev_t or self.blind:
            self._streak = 0
            self.last_side_rate = 0.0
            self.last_rate = 0.0
            return False
        flow = cv2.calcOpticalFlowFarneback(prev, grey, None, 0.5, 2, 9, 3, 5, 1.1, 0)
        h, w = grey.shape
        mx, my = int(w * (1 - self.centre) / 2), int(h * (1 - self.centre) / 2)
        ys, xs = np.mgrid[my:h - my, mx:w - mx]
        u = flow[my:h - my, mx:w - mx, 0].ravel()
        v = flow[my:h - my, mx:w - mx, 1].ravel()
        x = (xs.ravel() - w / 2) / (w / 2)
        y = (ys.ravel() - h / 2) / (w / 2)
        A = np.stack([x, y, np.ones_like(x)], axis=1)
        (a, b, c), *_ = np.linalg.lstsq(A, u, rcond=None)
        (d, e, f), *_ = np.linalg.lstsq(A, v, rcond=None)
        # a, e are pixels of flow per unit of normalised position; divide by half-width
        # in pixels to get relative expansion per frame.
        expansion = (a + e) / 2 / (w / 2)
        rate = expansion / (t - prev_t)
        self.last_rate = float(rate)
        # c: horizontal slide of the middle of the picture, pixels per frame.
        self.last_side_rate = float(c / w / (t - prev_t))
        if rate > 1e-6:
            self.last_tau = float(1.0 / rate)
        if self.last_tau is not None and self.last_tau < self.tau_limit_s:
            self._streak += 1
        else:
            self._streak = 0
        return self._streak >= self.confirm


    def _update_texture(self, grey: np.ndarray) -> None:
        """Detail in the middle of the view (Laplacian spread, robust to brightness).

        Plain walls and doors up close have almost none, and the flow-based looming
        test cannot see them. blind: too little detail now; blanked: detail collapsed
        to under a third of its recent level for 2 frames (something filling the view).
        """
        import cv2
        h, w = grey.shape
        mx, my = int(w * (1 - self.centre) / 2), int(h * (1 - self.centre) / 2)
        mid = grey[my:h - my, mx:w - mx]
        tex = float(cv2.Laplacian(mid, cv2.CV_32F).std())
        self.last_texture = tex
        self.blind = tex < self.min_texture
        base = self._texture_baseline
        if base is None:
            self._texture_baseline = tex
        elif tex > base:
            self._texture_baseline = base + 0.2 * (tex - base)    # rise quickly
        else:
            self._texture_baseline = base + 0.02 * (tex - base)   # fall slowly
        if base is not None and base > 2 * self.min_texture and tex < base / 3:
            self._blank_streak += 1
        else:
            self._blank_streak = 0
        self.blanked = self._blank_streak >= 2


# --------------------------------------------------------------------------- drift hold

@dataclass
class DriftConfig:
    k_roll: float = 1.2          # roll per (image width per second) of sideways slide
    k_pitch: float = 0.8         # pitch per (1/s) of expansion
    max_roll: float = 0.20
    max_pitch: float = 0.15
    deadband_side: float = 0.03  # ignore slides slower than this (image widths per second)
    deadband_expand: float = 0.08
    alpha: float = 0.35          # smoothing of the measurements (0..1, higher = faster)


class DriftHold:
    """Cancels drift the drone's own position hold misses, using the front camera.

    Sliding right makes the picture slide left (side_rate < 0): roll left to stop it.
    Creeping forward makes the picture expand (rate > 0): pitch back. Only used when the
    drone is not being told to turn (turning also slides the picture) and the view has
    enough detail; otherwise it resets and returns zero. Forward correction is never
    given when the view is plain.
    """

    def __init__(self, cfg: Optional[DriftConfig] = None):
        self.cfg = cfg or DriftConfig()
        self._side = 0.0
        self._expand = 0.0

    def reset(self) -> None:
        self._side = self._expand = 0.0

    def update(self, side_rate: float, expand_rate: float, turning: bool, blind: bool) -> tuple[float, float]:
        c = self.cfg
        if turning or blind:
            self.reset()
            return 0.0, 0.0
        self._side += c.alpha * (side_rate - self._side)
        self._expand += c.alpha * (expand_rate - self._expand)
        roll = 0.0
        if abs(self._side) > c.deadband_side:
            roll = c.k_roll * (self._side - math.copysign(c.deadband_side, self._side))
        pitch = 0.0
        if abs(self._expand) > c.deadband_expand:
            pitch = -c.k_pitch * (self._expand - math.copysign(c.deadband_expand, self._expand))
        roll = max(-c.max_roll, min(c.max_roll, roll))
        pitch = max(-c.max_pitch, min(c.max_pitch, pitch))
        return roll, pitch


# --------------------------------------------------------------------------- governor

class Mode(str, Enum):
    FOLLOW = "FOLLOW"
    HOLD = "HOLD"            # beacon lost: hover in place
    BACKOFF = "BACKOFF"      # something closing in: reverse briefly
    LANDED = "LANDED"        # landed after losing the beacon
    RESTING = "RESTING"      # landed because the wearer stood still
    SETTLING = "SETTLING"    # just relaunched: hover before following


@dataclass
class GovernorConfig:
    max_yaw: float = 0.35            # stick limit, before the speed tier
    max_pitch: float = 0.30
    slew_per_s: float = 1.5          # max stick change per second (smoothness)
    land_after_lost_s: float = 6.0   # hover this long without the beacon, then land
    backoff_s: float = 0.8
    backoff_pitch: float = -0.25
    rest_after_s: float = 20.0       # wearer still this long -> land and wait (0 = off)
    still_band: float = 0.05         # |command| below this counts as "standing still"
    relaunch: bool = False           # take off again automatically when the wearer moves
    relaunch_confirm_s: float = 1.0
    relaunch_move_cx: float = 0.25   # horizontal move of the beacon that counts as moving
    relaunch_area_ratio: float = 2.0 # or apparent size change by this factor
    settle_s: float = 3.0
    startup_grace_s: float = 15.0    # before the beacon is first confirmed, wait this long to land


@dataclass
class Command:
    yaw: float = 0.0
    pitch: float = 0.0
    action: Optional[str] = None     # "land" or "takeoff", once
    mode: Mode = Mode.FOLLOW
    reason: str = ""
    roll: float = 0.0


@dataclass
class SafetyGovernor:
    cfg: GovernorConfig = field(default_factory=GovernorConfig)
    mode: Mode = Mode.FOLLOW
    _t_last_seen: Optional[float] = None
    _seen_once: bool = False
    _t_mode: float = 0.0
    _t_still_since: Optional[float] = None
    _t_moved_since: Optional[float] = None
    _rest_cx: float = 0.0
    _rest_area: float = 0.0
    _yaw: float = 0.0
    _pitch: float = 0.0
    _last_t: Optional[float] = None

    def _enter(self, mode: Mode, t: float) -> None:
        self.mode = mode
        self._t_mode = t

    def _slew(self, target: float, current: float, dt: float) -> float:
        step = self.cfg.slew_per_s * dt
        return current + max(-step, min(step, target - current))

    def step(self, t: float, hit, raw_yaw: float, raw_pitch: float, looming: bool,
             blind: bool = False) -> Command:
        c = self.cfg
        dt = 0.0 if self._last_t is None else max(0.0, min(t - self._last_t, 0.3))
        self._last_t = t
        if self._t_last_seen is None:
            self._t_last_seen = t
        if hit is not None:
            self._t_last_seen = t
            self._seen_once = True
        action = None
        reason = ""

        # ---- on the ground: wait, maybe relaunch -----------------------------------
        if self.mode in (Mode.LANDED, Mode.RESTING):
            self._yaw = self._pitch = 0.0
            moved = False
            if hit is not None:
                if self.mode == Mode.LANDED:
                    moved = True  # beacon is back
                else:
                    ratio = hit.area_frac / self._rest_area if self._rest_area > 0 else 1.0
                    moved = (abs(hit.cx - self._rest_cx) > c.relaunch_move_cx
                             or ratio > c.relaunch_area_ratio or ratio < 1.0 / c.relaunch_area_ratio)
            if moved:
                self._t_moved_since = self._t_moved_since or t
            else:
                self._t_moved_since = None
            if c.relaunch and self._t_moved_since is not None and t - self._t_moved_since >= c.relaunch_confirm_s:
                self._t_moved_since = None
                self._enter(Mode.SETTLING, t)
                return Command(action="takeoff", mode=self.mode, reason="wearer moved: relaunch")
            return Command(mode=self.mode, reason="waiting on the ground")

        if self.mode == Mode.SETTLING:
            self._yaw = self._pitch = 0.0
            if t - self._t_mode >= c.settle_s:
                self._enter(Mode.FOLLOW, t)
                self._t_still_since = None
            return Command(mode=self.mode, reason="settling after takeoff")

        # ---- something closing in: reverse briefly ----------------------------------
        if looming and self.mode != Mode.BACKOFF:
            self._enter(Mode.BACKOFF, t)
            reason = "something closing in"
        if self.mode == Mode.BACKOFF:
            if t - self._t_mode < c.backoff_s:
                self._yaw = 0.0
                self._pitch = c.backoff_pitch
                return Command(0.0, self._pitch, mode=self.mode, reason=reason or "backing off")
            self._enter(Mode.FOLLOW if hit is not None else Mode.HOLD, t)
            self._pitch = 0.0

        # ---- beacon lost: hover, then land -----------------------------------------
        if hit is None:
            if self.mode != Mode.HOLD:
                self._enter(Mode.HOLD, t)
            self._yaw = self._pitch = 0.0
            self._t_still_since = None
            # The blink filter needs ~2 s to confirm the beacon at start: do not call that "lost".
            limit = c.land_after_lost_s if self._seen_once else max(c.land_after_lost_s, c.startup_grace_s)
            if t - self._t_last_seen >= limit:
                self._enter(Mode.LANDED, t)
                return Command(action="land", mode=self.mode, reason="beacon lost: landing")
            return Command(mode=self.mode, reason="beacon lost: hovering")

        if self.mode == Mode.HOLD:
            self._enter(Mode.FOLLOW, t)

        # ---- follow, capped and smoothed -------------------------------------------
        target_yaw = max(-c.max_yaw, min(c.max_yaw, raw_yaw))
        target_pitch = max(-c.max_pitch, min(c.max_pitch, raw_pitch))
        if blind and target_pitch > 0:
            target_pitch = 0.0       # cannot judge distance: turn or back up, never forward
            reason = "view too plain to judge distance: no forward"
        self._yaw = self._slew(target_yaw, self._yaw, dt)
        self._pitch = self._slew(target_pitch, self._pitch, dt)

        # ---- land-and-wait when the wearer stands still -------------------------------
        if c.rest_after_s > 0 and abs(raw_yaw) < c.still_band and abs(raw_pitch) < c.still_band:
            self._t_still_since = self._t_still_since or t
            if t - self._t_still_since >= c.rest_after_s:
                self._rest_cx, self._rest_area = hit.cx, hit.area_frac
                self._t_still_since = None
                self._enter(Mode.RESTING, t)
                self._yaw = self._pitch = 0.0
                return Command(action="land", mode=self.mode, reason="wearer still: land and wait")
        else:
            self._t_still_since = None
        return Command(self._yaw, self._pitch, action, self.mode, reason)


# --------------------------------------------------------------------------- together

class BeaconFollower:
    """Pipeline + looming + governor. update() takes a BGR frame, returns a Command."""

    def __init__(self, gov_cfg: Optional[GovernorConfig] = None, looming: bool = True,
                 blink_hz: float = 2.5, target_area: float = 0.002, channel: int = 1,
                 kp_yaw: float = 250.0, yaw_max: int = 175, kp_pitch: float = 120.0, pitch_max: int = 150):
        self.pipe = Pipeline(blink_hz, target_area, channel,
                             kp_yaw=kp_yaw, yaw_max=yaw_max, kp_pitch=kp_pitch, pitch_max=pitch_max)
        self.loom = LoomingDetector() if looming else None
        self.gov = SafetyGovernor(gov_cfg or GovernorConfig())
        self.drift = DriftHold() if looming else None
        self.last_hit = None
        self.last_blobs: list = []

    def update(self, img_bgr: np.ndarray, t: float) -> Command:
        blobs, hit, out = self.pipe.update(img_bgr, t)
        self.last_blobs, self.last_hit = blobs, hit
        raw_yaw = stick_pct(out.yaw) / 100.0 if hit is not None else 0.0
        raw_pitch = stick_pct(out.pitch) / 100.0 if hit is not None else 0.0
        looming = blind = False
        if self.loom is not None:
            looming = self.loom.update(img_bgr, t) or self.loom.blanked
            blind = self.loom.blind
        cmd = self.gov.step(t, hit, raw_yaw, raw_pitch, looming, blind)
        if self.drift is not None and cmd.mode in (Mode.FOLLOW, Mode.HOLD) and not cmd.action:
            turning = abs(cmd.yaw) > 0.05
            roll, dpitch = self.drift.update(self.loom.last_side_rate, self.loom.last_rate, turning, blind)
            cmd.roll = roll
            # Drift correction adds to pitch only when following is not already moving it.
            if abs(cmd.pitch) < 0.05:
                cmd.pitch = max(-self.gov.cfg.max_pitch, min(self.gov.cfg.max_pitch, cmd.pitch + dpitch))
        elif self.drift is not None:
            self.drift.reset()
        return cmd


class HoverHold:
    """Hold still with the camera: drift hold + back off on looming / a wall filling the view."""

    def __init__(self, drift_cfg: Optional[DriftConfig] = None, backoff_s: float = 0.8, backoff_pitch: float = -0.25):
        self.loom = LoomingDetector()
        self.drift = DriftHold(drift_cfg)
        self.backoff_s = backoff_s
        self.backoff_pitch = backoff_pitch
        self._backoff_until = -1.0

    def update(self, img_bgr: np.ndarray, t: float) -> Command:
        looming = self.loom.update(img_bgr, t) or self.loom.blanked
        if looming:
            self._backoff_until = t + self.backoff_s
        if t < self._backoff_until:
            self.drift.reset()
            return Command(pitch=self.backoff_pitch, mode=Mode.BACKOFF, reason="something closing in")
        roll, pitch = self.drift.update(self.loom.last_side_rate, self.loom.last_rate, False, self.loom.blind)
        reason = "view too plain: holding blind" if self.loom.blind else ""
        return Command(pitch=pitch, roll=roll, mode=Mode.HOLD, reason=reason)

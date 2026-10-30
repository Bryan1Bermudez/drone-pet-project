"""Safety monitor: decides the flight mode each cycle. First matching rule wins."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .config import SafetyConfig
from .geometry import Vec3


class Mode(str, Enum):
    FOLLOW = "FOLLOW"
    HOLD = "HOLD"
    RTL = "RTL"
    LAND = "LAND"


class BandButton(int, Enum):
    NONE = 0
    PAUSE = 1
    LAND = 2


@dataclass
class SafetyInputs:
    t: float
    battery_pct: float
    last_band_update_t: Optional[float]
    wearer_position: Optional[Vec3]  # NED relative to home
    band_button: BandButton = BandButton.NONE


@dataclass
class Decision:
    mode: Mode
    reason: str


class SafetyMonitor:
    def __init__(self, cfg: SafetyConfig):
        self.cfg = cfg

    def decide(self, s: SafetyInputs) -> Decision:
        if s.battery_pct <= self.cfg.battery_critical_pct:
            return Decision(Mode.LAND, "battery critical")
        if s.battery_pct <= self.cfg.battery_low_pct:
            return Decision(Mode.RTL, "battery low")

        if s.last_band_update_t is None:
            age = float("inf")
        else:
            age = s.t - s.last_band_update_t
        if age >= self.cfg.link_rtl_after_s:
            return Decision(Mode.RTL, f"band link lost for {age:.0f}s")
        if age >= self.cfg.link_hold_after_s:
            return Decision(Mode.HOLD, f"band link stale for {age:.1f}s")

        if s.band_button == BandButton.LAND:
            return Decision(Mode.LAND, "band long-press")
        if s.band_button == BandButton.PAUSE:
            return Decision(Mode.HOLD, "band pause")

        if s.wearer_position is not None:
            if s.wearer_position.horizontal_norm() > self.cfg.fence_radius_m:
                return Decision(Mode.HOLD, "wearer outside geofence")
            if -s.wearer_position.z > self.cfg.fence_ceiling_m:
                return Decision(Mode.HOLD, "wearer above fence ceiling")

        return Decision(Mode.FOLLOW, "ok")

"""Ties estimator, controller and safety together into one control cycle.

The same `FollowRunner.step` is used by the simulator and by `main.py` on the drone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import FollowConfig
from .controller import FollowController, Setpoint
from .estimator import DroneState, RangeSample, WearerEstimator
from .mavlink_io import FlightController
from .safety import BandButton, Decision, Mode, SafetyInputs, SafetyMonitor


@dataclass
class StepResult:
    decision: Decision
    setpoint: Optional[Setpoint]


class FollowRunner:
    def __init__(self, cfg: FollowConfig, fc: FlightController):
        self.cfg = cfg
        self.fc = fc
        self.estimator = WearerEstimator(cfg.estimator, cfg.controller.follow_height_m)
        self.controller = FollowController(cfg.controller)
        self.safety = SafetyMonitor(cfg.safety)
        self._last_band_t: Optional[float] = None
        self._band_button = BandButton.NONE
        self._hold_position = None
        self._last_mode: Optional[Mode] = None

    def on_band_status(self, t: float, button: BandButton) -> None:
        self._last_band_t = t
        self._band_button = button

    def step(self, t: float, ranges: Optional[RangeSample], dt: float) -> StepResult:
        drone = self.fc.read_state()
        if drone is None:
            return StepResult(Decision(Mode.HOLD, "no flight controller state"), None)

        if ranges is not None:
            est = self.estimator.update(ranges, drone)
            if est is not None and est.t == t:
                self._last_band_t = t
        est = self.estimator.estimate

        decision = self.safety.decide(
            SafetyInputs(
                t=t,
                battery_pct=self.fc.battery_pct(),
                last_band_update_t=self._last_band_t,
                wearer_position=est.position if est else None,
                band_button=self._band_button,
            )
        )

        if decision.mode != self._last_mode:
            self.fc.set_mode(decision.mode)
            self._last_mode = decision.mode
            if decision.mode == Mode.HOLD:
                self._hold_position = drone.position
            if decision.mode == Mode.FOLLOW:
                self.controller.reset()

        setpoint = None
        if decision.mode == Mode.FOLLOW and est is not None:
            setpoint = self.controller.update(est, drone, dt)
            if setpoint.changed:
                self.fc.send_position_setpoint(setpoint.position, setpoint.yaw_rad)
        elif decision.mode == Mode.HOLD and self._hold_position is not None:
            # Re-send the hold point occasionally so GUIDED does not time out.
            self.fc.send_position_setpoint(self._hold_position, drone.yaw_rad)

        return StepResult(decision, setpoint)

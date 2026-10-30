"""Kinematic simulator: a wearer walks a path, the drone tracks setpoints with lag.

Run `python -m follow.sim` for a 60 s demo with a summary, or import `simulate` in tests.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import FollowConfig
from .estimator import DroneState, RangeSample
from .geometry import Vec3, body_to_ned
from .mavlink_io import FakeFlightController
from .runner import FollowRunner
from .safety import Mode


@dataclass
class SimResult:
    times: list[float] = field(default_factory=list)
    wearer: list[Vec3] = field(default_factory=list)
    drone: list[Vec3] = field(default_factory=list)
    modes: list[Mode] = field(default_factory=list)
    setpoint_changes: int = 0
    steps: int = 0

    def horizontal_errors(self, follow_distance: float) -> list[float]:
        """How far the drone's horizontal distance to the wearer deviates from the target."""
        out = []
        for w, d in zip(self.wearer, self.drone):
            out.append(abs((d - w).horizontal_norm() - follow_distance))
        return out

    def height_errors(self, follow_height: float) -> list[float]:
        return [abs((w.z - d.z) - follow_height) for w, d in zip(self.wearer, self.drone)]

    def setpoint_change_rate_hz(self) -> float:
        return self.setpoint_changes / self.times[-1] if self.times else 0.0


class LaggyDrone:
    """Drone that moves toward its setpoint with a first-order lag and speed cap."""

    def __init__(self, position: Vec3, yaw: float, tau_s: float = 0.8, max_speed: float = 4.0):
        self.position = position
        self.yaw = yaw
        self.tau = tau_s
        self.max_speed = max_speed
        self.setpoint: Optional[Vec3] = None
        self.setpoint_yaw: Optional[float] = None

    def advance(self, dt: float) -> None:
        if self.setpoint is None:
            return
        err = self.setpoint - self.position
        vel = err * (1.0 / self.tau)
        n = vel.norm()
        if n > self.max_speed:
            vel = vel * (self.max_speed / n)
        self.position = self.position + vel * dt
        if self.setpoint_yaw is not None:
            dy = (self.setpoint_yaw - self.yaw + math.pi) % (2 * math.pi) - math.pi
            self.yaw += max(-math.radians(60) * dt, min(math.radians(60) * dt, dy))

    def state(self) -> DroneState:
        return DroneState(self.position, self.yaw, -self.position.z)


def ranges_from_truth(
    drone: LaggyDrone, wearer: Vec3, baseline: float, noise_m: float, rng: random.Random
) -> RangeSample:
    """Exact two-anchor ranges from geometry plus Gaussian noise."""
    out = []
    for side in (-1.0, 1.0):
        n, e = body_to_ned(0.0, side * baseline / 2.0, drone.yaw)
        anchor = Vec3(drone.position.x + n, drone.position.y + e, drone.position.z)
        out.append((wearer - anchor).norm() + rng.gauss(0.0, noise_m))
    return RangeSample(0.0, out[0], out[1])


def walk_straight(speed: float = 1.4) -> Callable[[float], Vec3]:
    return lambda t: Vec3(speed * t, 0.0, 0.0)


def walk_loop(radius: float = 15.0, speed: float = 1.4) -> Callable[[float], Vec3]:
    w = speed / radius
    return lambda t: Vec3(radius * math.sin(w * t), radius * (1 - math.cos(w * t)), 0.0)


def stand_then_walk(wait_s: float = 10.0, speed: float = 1.4) -> Callable[[float], Vec3]:
    return lambda t: Vec3(0.0, 0.0, 0.0) if t < wait_s else Vec3(speed * (t - wait_s), 0.0, 0.0)


def simulate(
    path: Callable[[float], Vec3],
    duration_s: float = 60.0,
    cfg: Optional[FollowConfig] = None,
    range_noise_m: float = 0.08,  # DW3000 two-way ranging is typically 5-10 cm, 1 sigma
    seed: int = 1,
    battery_fn: Optional[Callable[[float], float]] = None,
    band_dropout: Optional[tuple[float, float]] = None,
) -> SimResult:
    cfg = cfg or FollowConfig()
    rng = random.Random(seed)
    dt = 1.0 / cfg.loop_hz

    w0 = path(0.0)
    drone = LaggyDrone(
        Vec3(w0.x - cfg.controller.follow_distance_m, w0.y, w0.z - cfg.controller.follow_height_m),
        yaw=0.0,
    )
    fc = FakeFlightController(drone.state())
    runner = FollowRunner(cfg, fc)
    result = SimResult()

    t = 0.0
    while t <= duration_s:
        wearer = path(t)
        fc.state = drone.state()
        if battery_fn is not None:
            fc._battery = battery_fn(t)

        dropped = band_dropout is not None and band_dropout[0] <= t < band_dropout[1]
        sample = None
        if not dropped:
            sample = ranges_from_truth(drone, wearer, cfg.estimator.anchor_baseline_m, range_noise_m, rng)
            sample.t = t

        step = runner.step(t, sample, dt)
        if step.setpoint is not None:
            drone.setpoint = step.setpoint.position
            drone.setpoint_yaw = step.setpoint.yaw_rad
        drone.advance(dt)

        result.times.append(t)
        result.wearer.append(wearer)
        result.drone.append(drone.position)
        result.modes.append(step.decision.mode)
        result.steps += 1
        t += dt

    result.setpoint_changes = runner.controller.setpoint_changes
    return result


def _summary(name: str, r: SimResult, cfg: FollowConfig) -> str:
    he = r.horizontal_errors(cfg.controller.follow_distance_m)
    ve = r.height_errors(cfg.controller.follow_height_m)
    settled = he[len(he) // 3 :]
    return (
        f"{name:18s} steps={r.steps:5d}  "
        f"mean|dist err|={sum(settled)/len(settled):.2f} m  "
        f"max|dist err|={max(settled):.2f} m  "
        f"mean|h err|={sum(ve)/len(ve):.2f} m  "
        f"setpoint updates={r.setpoint_change_rate_hz():.1f}/s  "
        f"modes={sorted(set(m.value for m in r.modes))}"
    )


if __name__ == "__main__":
    cfg = FollowConfig()
    print(_summary("straight walk", simulate(walk_straight(), 60, cfg), cfg))
    print(_summary("loop walk", simulate(walk_loop(), 90, cfg), cfg))
    print(_summary("stand then walk", simulate(stand_then_walk(), 60, cfg), cfg))
    print(_summary("link dropout", simulate(walk_straight(), 60, cfg, band_dropout=(20, 32)), cfg))

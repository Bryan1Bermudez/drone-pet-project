"""Small vector helpers. NED frame: x north, y east, z down (so up is negative z)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, k: float) -> "Vec3":
        return Vec3(self.x * k, self.y * k, self.z * k)

    __rmul__ = __mul__

    def norm(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def horizontal_norm(self) -> float:
        return math.hypot(self.x, self.y)

    def with_z(self, z: float) -> "Vec3":
        return Vec3(self.x, self.y, z)


def wrap_angle(a: float) -> float:
    """Wrap an angle in radians to (-pi, pi]."""
    while a <= -math.pi:
        a += 2 * math.pi
    while a > math.pi:
        a -= 2 * math.pi
    return a


def body_to_ned(forward: float, right: float, yaw: float) -> tuple[float, float]:
    """Rotate a body-frame horizontal vector into NED using the drone yaw (rad, 0 = north)."""
    c, s = math.cos(yaw), math.sin(yaw)
    return forward * c - right * s, forward * s + right * c


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v

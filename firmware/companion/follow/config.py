"""Tunable parameters.

Defaults favour quiet, smooth, low-power flight over tight tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EstimatorConfig:
    anchor_baseline_m: float = 0.30
    """Distance between the two UWB anchors on the drone (body y axis)."""

    range_lowpass_alpha: float = 0.06
    """Filter weight applied to the mean range and the range *difference* before the
    bearing is computed. The difference carries the angle: per-sample noise is roughly
    range_noise * sqrt(2) / baseline radians (10 cm, 30 cm -> ~27 deg), and the asin
    saturates, so this filter is essential. 0.06 at 20 Hz is a ~0.8 s time constant and
    brings bearing noise down to a few degrees. Set to 1.0 to disable."""

    lowpass_alpha: float = 0.3
    """Filter weight on the resulting position (inputs are already smooth)."""

    outlier_jump_m: float = 3.0
    """Reject a sample that moves the estimate more than this in one step..."""

    outlier_confirm_count: int = 3
    """...unless this many consecutive samples agree on the jump."""

    max_range_m: float = 60.0
    """Ranges beyond this are treated as invalid."""


@dataclass
class ControllerConfig:
    follow_distance_m: float = 3.0
    """Horizontal offset behind the wearer."""

    follow_height_m: float = 2.5
    """Height above the wearer."""

    position_deadband_m: float = 1.0
    """No new setpoint until the error exceeds this. Larger = quieter."""

    position_settle_m: float = 0.2
    """Once moving, keep moving until the error is below this (hysteresis)."""

    height_deadband_m: float = 0.5

    lead_time_s: float = 1.0
    """Feed-forward: aim the setpoint this far ahead along the wearer's velocity so the
    drone's own response lag does not turn into a steady-state distance error."""

    velocity_window_s: float = 2.0
    """Wearer velocity is estimated over this window (longer = smoother heading)."""

    heading_min_displacement_m: float = 1.5
    """Heading only updates when the wearer moved at least this far within the window."""

    heading_lowpass_alpha: float = 0.2

    moving_confirm_s: float = 1.0
    """The wearer must look like they are moving for this long, continuously, before
    heading and velocity feed-forward update. Rejects jitter from a standing wearer."""

    max_horizontal_speed_mps: float = 2.5
    max_vertical_speed_mps: float = 1.0
    max_accel_mps2: float = 1.0
    """Limits on how fast the *setpoint* may move. ArduPilot has its own limits too."""

    yaw_deadband_deg: float = 15.0
    max_yaw_rate_dps: float = 45.0

    wearer_speed_for_heading_mps: float = 0.6
    """Below this speed the wearer's heading is held at its last value."""


@dataclass
class SafetyConfig:
    battery_low_pct: float = 25.0
    battery_critical_pct: float = 15.0
    link_hold_after_s: float = 3.0
    link_rtl_after_s: float = 10.0
    fence_radius_m: float = 150.0
    fence_ceiling_m: float = 30.0


@dataclass
class FollowConfig:
    loop_hz: float = 20.0
    estimator: EstimatorConfig = field(default_factory=EstimatorConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)

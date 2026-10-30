"""Entry point on the drone's companion board.

    python3 main.py --fc /dev/serial0 --baud 921600

UWB anchor and BLE scanner drivers are injected here; they are the only parts that
touch hardware. Until the anchor driver is written, `--fake-ranges` runs the loop
against a stationary virtual band 5 m ahead, which is useful for SITL testing.
"""

from __future__ import annotations

import argparse
import logging
import time

from follow.config import FollowConfig
from follow.estimator import RangeSample
from follow.mavlink_io import MavlinkFlightController
from follow.runner import FollowRunner

log = logging.getLogger("follow")


class FakeRanges:
    """Stationary band 5 m ahead and 2.5 m below the nose; stands in for the UWB driver."""

    def read(self, t: float) -> RangeSample:
        r = (5.0**2 + 2.5**2) ** 0.5
        return RangeSample(t, r, r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fc", default="/dev/serial0", help="MAVLink device or udp:host:port")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--fake-ranges", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(message)s")

    cfg = FollowConfig()
    fc = MavlinkFlightController(args.fc, args.baud)
    log.info("connecting to flight controller at %s", args.fc)
    fc.connect()
    log.info("heartbeat received")

    if args.fake_ranges:
        ranges = FakeRanges()
    else:
        from uwb_anchor import UwbAnchorPair  # hardware driver, to be written during bring-up

        ranges = UwbAnchorPair(baseline_m=cfg.estimator.anchor_baseline_m)

    runner = FollowRunner(cfg, fc)
    dt = 1.0 / cfg.loop_hz
    last_mode = None
    t0 = time.monotonic()
    while True:
        t = time.monotonic() - t0
        sample = ranges.read(t)
        step = runner.step(t, sample, dt)
        if step.decision.mode != last_mode:
            log.info("mode %s (%s)", step.decision.mode.value, step.decision.reason)
            last_mode = step.decision.mode
        time.sleep(max(0.0, dt - ((time.monotonic() - t0) - t)))


if __name__ == "__main__":
    main()

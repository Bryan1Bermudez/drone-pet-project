"""Turbodrone plugin: follow the blinking wristband beacon, with a safety layer.

Installed by drone-pet-project/tools/windows/install.bat as
turbodrone/backend/plugins/beacon_follow.py. Needs PLUGINS_ENABLED=true and
DRONE_PET_PROJECT=<path to drone-pet-project> in backend/.env (install.bat writes both).

Use: take off first, then switch "BeaconFollowPlugin" ON in the page's Plugins panel.
Any key press on the page stops the plugin and gives you control back.

The logic lives in drone-pet-project/tools/follow_core.py (tested headless):
speed cap + smoothing, back off when something closes in fast, hover then land when
the beacon is lost, land-and-wait when the wearer stands still, optional relaunch.

Settings (backend/.env, all optional):
  FOLLOW_MAX_YAW=0.35  FOLLOW_MAX_PITCH=0.30   stick limits before the speed tier
  FOLLOW_LAND_AFTER_LOST_S=6                    hover this long without the beacon, then land
  FOLLOW_REST_AFTER_S=20                        land when the wearer is still this long (0 = off)
  FOLLOW_RELAUNCH=0                             1 = take off again when the wearer moves
  FOLLOW_LOOMING=1  FOLLOW_TAU_S=1.2            back off when contact is < this many seconds away
  FOLLOW_TARGET_AREA=0.002                      beacon size at the wanted distance
  FOLLOW_CHANNEL=1  FOLLOW_BLINK_HZ=2.5         beacon colour (0 red, 1 green, 2 blue) and rate
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

import numpy as np

from .base import Plugin

logger = logging.getLogger(__name__)


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _import_core():
    root = os.getenv("DRONE_PET_PROJECT", "")
    candidates = [root] if root else []
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.abspath(os.path.join(here, "..", "..", "..", "drone-pet-project")))
    for c in candidates:
        tools = os.path.join(c, "tools")
        if os.path.exists(os.path.join(tools, "follow_core.py")):
            if tools not in sys.path:
                sys.path.insert(0, tools)
            import follow_core  # noqa: WPS433
            return follow_core
    raise RuntimeError("drone-pet-project not found: set DRONE_PET_PROJECT in backend/.env")


class BeaconFollowPlugin(Plugin):
    def _on_start(self):
        core = _import_core()
        self._core = core
        gcfg = core.GovernorConfig(
            max_yaw=_env_f("FOLLOW_MAX_YAW", 0.35),
            max_pitch=_env_f("FOLLOW_MAX_PITCH", 0.30),
            land_after_lost_s=_env_f("FOLLOW_LAND_AFTER_LOST_S", 6.0),
            rest_after_s=_env_f("FOLLOW_REST_AFTER_S", 20.0),
            relaunch=os.getenv("FOLLOW_RELAUNCH", "0").strip() in ("1", "true", "yes", "on"),
        )
        self.follower = core.BeaconFollower(
            gov_cfg=gcfg,
            looming=os.getenv("FOLLOW_LOOMING", "1").strip() not in ("0", "false", "no", "off"),
            blink_hz=_env_f("FOLLOW_BLINK_HZ", 2.5),
            target_area=_env_f("FOLLOW_TARGET_AREA", 0.002),
            channel=int(_env_f("FOLLOW_CHANNEL", 1)),
        )
        if self.follower.loom is not None:
            self.follower.loom.tau_limit_s = _env_f("FOLLOW_TAU_S", 1.2)

        from control.strategies import DirectStrategy
        self._prev_strategy = getattr(self.fc.model, "strategy", None)
        try:
            self.fc.model.set_strategy(DirectStrategy())
        except Exception as e:  # pragma: no cover
            logger.warning("[BeaconFollow] could not set DirectStrategy: %s", e)
        self._last_mode = None
        logger.info("[BeaconFollow] started: max yaw %.2f pitch %.2f, land after lost %.0fs, rest after %.0fs, relaunch %s",
                    gcfg.max_yaw, gcfg.max_pitch, gcfg.land_after_lost_s, gcfg.rest_after_s, gcfg.relaunch)
        self.loop_thread = threading.Thread(target=self._loop, daemon=True, name="BeaconFollow")
        self.loop_thread.start()

    def _on_stop(self):
        try:
            self.fc.set_axes_from("beacon", throttle=0, yaw=0, pitch=0, roll=0)
        except Exception:
            pass
        try:
            if self._prev_strategy is not None:
                self.fc.model.set_strategy(self._prev_strategy)
        except Exception:
            pass
        if self.loop_thread and threading.current_thread() is not self.loop_thread:
            self.loop_thread.join(timeout=1.0)
        logger.info("[BeaconFollow] stopped")

    def _loop(self):
        import cv2
        for frame in self.frames:
            if not self.running:
                break
            if hasattr(frame, "format") and frame.format == "jpeg":
                img = cv2.imdecode(np.frombuffer(frame.data, np.uint8), cv2.IMREAD_COLOR)
            elif isinstance(frame, np.ndarray):
                img = frame
            else:
                continue
            if img is None:
                continue
            t = time.monotonic()
            try:
                cmd = self.follower.update(img, t)
            except Exception as e:
                logger.warning("[BeaconFollow] frame error: %s", e)
                self.fc.set_axes_from("beacon", throttle=0, yaw=0, pitch=0, roll=0)
                continue

            if cmd.action == "land":
                self.fc.model.land()
            elif cmd.action == "takeoff":
                self.fc.model.takeoff()
            self.fc.set_axes_from("beacon", throttle=0, yaw=cmd.yaw, pitch=cmd.pitch, roll=0)

            if cmd.mode != self._last_mode or cmd.action:
                logger.info("[BeaconFollow] %s%s%s", cmd.mode.value,
                            f" ({cmd.reason})" if cmd.reason else "",
                            f" -> {cmd.action.upper()}" if cmd.action else "")
                self._last_mode = cmd.mode
            self._draw(cmd)

    def _draw(self, cmd):
        hit = self.follower.last_hit
        shapes = []
        for b in self.follower.last_blobs:
            r = max(0.02, (b.area_frac ** 0.5) * 0.8)
            x, y = (b.cx + 1) / 2, (b.cy + 1) / 2
            shapes.append({"type": "rect", "coords": [x - r, y - r, x + r, y + r], "color": "gray"})
        if hit is not None:
            r = max(0.03, (hit.area_frac ** 0.5) * 1.2)
            x, y = (hit.cx + 1) / 2, (hit.cy + 1) / 2
            shapes.append({"type": "rect", "coords": [x - r, y - r, x + r, y + r], "color": "lime"})
        if cmd.mode.value == "BACKOFF":
            shapes.append({"type": "rect", "coords": [0.02, 0.02, 0.98, 0.98], "color": "red"})
        self.send_overlay(shapes)

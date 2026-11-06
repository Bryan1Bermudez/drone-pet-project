"""Test the follow software with the PC's webcam: no drone, no Wi-Fi switching.

Runs exactly the code the drone will use (colour blob finder from tello_follow.py,
blink filter follow/blink.py, follow logic follow/visual.py) on webcam frames, and
shows the stick commands it would send. Stay on your home Wi-Fi while you tune it.

    pip install opencv-python numpy
    python tools/webcam_follow.py                # webcam 0
    python tools/webcam_follow.py --camera 1     # another camera
    python tools/webcam_follow.py --video clip.mp4

Beacons:
  * F key: a fake green beacon that blinks at the wristband's rate follows your mouse.
    Mouse wheel or +/- changes its size (= distance).
  * A real blinking light: open tools/strobe.html full screen on any other screen
    (tablet, laptop, TV browser) and hold it in view. Or the wristband, once built.
  Steady green things (a lamp, a green shirt, a screen) should show as grey
  candidates but never turn into the green "BEACON" circle.

Virtual drone (S key, on by default): the window shows a cropped "drone camera"
that turns and moves forward/back according to the stick commands, so you can see
the follow loop actually centre the beacon and hold its distance.

Keys: F fake beacon on/off, S virtual drone on/off, +/- beacon size, R reset, Q quit.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "companion"))
from tello_follow import find_blobs  # noqa: E402
from follow.blink import BlinkConfig, BlinkTracker  # noqa: E402
from follow.visual import RC_MID, Observation, RcOut, State, VisualConfig, VisualFollower  # noqa: E402


def stick_pct(us: int) -> int:
    """Betaflight-style stick microseconds -> -100..100 %."""
    return int(max(-100, min(100, round((us - RC_MID) / 5))))


@dataclass
class FakeBeacon:
    """A green dot blinking at the wristband rate, drawn into the world frame."""
    x: float = 0.5          # 0..1 of world frame width
    y: float = 0.5
    radius_frac: float = 0.012   # of world frame width (about the target distance)
    blink_hz: float = 2.5
    enabled: bool = False

    def is_on(self, t: float) -> bool:
        return (t * self.blink_hz) % 1.0 < 0.5

    def draw(self, frame: np.ndarray, t: float) -> None:
        if not self.enabled or not self.is_on(t):
            return
        import cv2
        h, w = frame.shape[:2]
        cv2.circle(frame, (int(self.x * w), int(self.y * h)), max(2, int(self.radius_frac * w)), (0, 255, 0), -1)


@dataclass
class VirtualDrone:
    """Crop window over the world frame that yaws (pans) and pitches (zooms)."""
    view_x: float = 0.5           # crop centre, 0..1 of world width
    zoom: float = 1.0             # 1 = widest view
    base_width: float = 0.6       # crop width at zoom 1, fraction of world width
    yaw_rate: float = 0.6         # world widths per second at 100 % yaw
    zoom_rate: float = 1.0        # ln(zoom) per second at 100 % pitch
    min_zoom: float = 0.7
    max_zoom: float = 1.6

    def crop_box(self, w: int, h: int) -> tuple[int, int, int, int]:
        cw = self.base_width / self.zoom
        ch = cw  # keep the world aspect ratio
        x0 = min(max(self.view_x - cw / 2, 0.0), 1.0 - cw)
        y0 = (1.0 - ch) / 2
        return int(x0 * w), int(y0 * h), max(2, int(cw * w)), max(2, int(ch * h))

    def view(self, world: np.ndarray, out_size: tuple[int, int]) -> np.ndarray:
        import cv2
        h, w = world.shape[:2]
        x, y, cw, ch = self.crop_box(w, h)
        return cv2.resize(world[y:y + ch, x:x + cw], out_size, interpolation=cv2.INTER_LINEAR)

    def step(self, rc: RcOut, dt: float) -> None:
        cw = self.base_width / self.zoom
        self.view_x += stick_pct(rc.yaw) / 100.0 * self.yaw_rate * dt
        self.view_x = min(max(self.view_x, cw / 2), 1.0 - cw / 2)
        self.zoom *= math.exp(stick_pct(rc.pitch) / 100.0 * self.zoom_rate * dt)
        self.zoom = min(max(self.zoom, self.min_zoom), self.max_zoom)

    def to_world(self, u: float, v: float, w: int, h: int) -> tuple[float, float]:
        """View coordinates (0..1) -> world coordinates (0..1)."""
        x, y, cw, ch = self.crop_box(w, h)
        return (x + u * cw) / w, (y + v * ch) / h


class Pipeline:
    """Blob finder + blink filter + follow logic, as on the drone."""

    def __init__(self, blink_hz: float = 2.5, target_area: float = 0.002, channel: int = 1, **cfg_overrides):
        # Same lowered gains as tello_follow.py: Wi-Fi video adds latency.
        gains = dict(kp_yaw=120.0, yaw_max=60, kp_pitch=60.0, pitch_max=40)
        gains.update(cfg_overrides)
        self.cfg = VisualConfig(target_area_frac=target_area, **gains)
        self.channel = channel
        self.beacon = BlinkTracker(BlinkConfig(blink_hz=blink_hz))
        self.follower = VisualFollower(self.cfg)
        self._armed = False

    def reset(self) -> None:
        self.beacon = BlinkTracker(self.beacon.cfg)
        self.follower = VisualFollower(self.cfg)
        self._armed = False

    def update(self, frame_bgr: np.ndarray, t: float):
        blobs = find_blobs(frame_bgr, self.channel)
        hit = self.beacon.update(t, blobs)
        if not self._armed or self.follower.state in (State.IDLE, State.LAND):
            # Pretend we are airborne at target height: only yaw/pitch matter here.
            self.follower.state = State.FOLLOW if hit else State.SEARCH
            self.follower._t_armed = t
            self.follower._t_last_seen = t
            self.follower._t_last_height = t
            self._armed = True
        found = hit is not None
        obs = Observation(t, found, cx=hit.cx if hit else 0.0, cy=hit.cy if hit else 0.0,
                          area_frac=hit.area_frac if hit else 0.0, height_m=self.cfg.target_height_m)
        out = self.follower.update(obs)
        return blobs, hit, out


def describe(out: RcOut) -> str:
    yaw, pitch = stick_pct(out.yaw), stick_pct(out.pitch)
    parts = []
    if yaw:
        parts.append(f"TURN {'RIGHT' if yaw > 0 else 'LEFT'} {abs(yaw)}%")
    if pitch:
        parts.append(f"{'FORWARD' if pitch > 0 else 'BACK'} {abs(pitch)}%")
    return ", ".join(parts) or "HOLD"


def draw_overlay(img, blobs, hit, out: RcOut, info: str) -> None:
    import cv2
    h, w = img.shape[:2]
    for bl in blobs:
        cv2.circle(img, (int((bl.cx + 1) * w / 2), int((bl.cy + 1) * h / 2)), 12, (170, 170, 170), 1)
    if hit:
        p = (int((hit.cx + 1) * w / 2), int((hit.cy + 1) * h / 2))
        cv2.circle(img, p, 18, (0, 255, 0), 2)
        cv2.putText(img, "BEACON", (p[0] + 20, p[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.line(img, (w // 2, h // 2 - 10), (w // 2, h // 2 + 10), (255, 255, 255), 1)
    cv2.line(img, (w // 2 - 10, h // 2), (w // 2 + 10, h // 2), (255, 255, 255), 1)
    lines = [f"{out.state.value}: {describe(out)}",
             f"beacon area {hit.area_frac:.4f}" if hit else "no beacon (grey = candidates)",
             info]
    for i, s in enumerate(lines):
        cv2.putText(img, s, (10, 28 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4)
        cv2.putText(img, s, (10, 28 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    # stick indicator, bottom right: x = yaw, y = pitch (up = forward)
    cx, cy, r = w - 70, h - 70, 50
    cv2.rectangle(img, (cx - r, cy - r), (cx + r, cy + r), (255, 255, 255), 1)
    sx = cx + int(stick_pct(out.yaw) / 100 * r)
    sy = cy - int(stick_pct(out.pitch) / 100 * r)
    cv2.circle(img, (sx, sy), 7, (0, 200, 255), -1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--video", help="use a video file instead of the webcam")
    ap.add_argument("--channel", type=int, default=1, help="LED colour: 0 red, 1 green, 2 blue")
    ap.add_argument("--blink-hz", type=float, default=2.5)
    ap.add_argument("--target-area", type=float, default=0.002,
                    help="beacon area fraction at the desired distance")
    ap.add_argument("--no-sim", action="store_true", help="start with the virtual drone off")
    args = ap.parse_args()

    import cv2

    if args.video:
        cap = cv2.VideoCapture(args.video)
    else:
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print("Could not open the camera/video. Try --camera 1, or close other apps using the webcam.")
        return 1

    pipe = Pipeline(args.blink_hz, args.target_area, args.channel)
    fake = FakeBeacon(blink_hz=args.blink_hz)
    sim = VirtualDrone()
    sim_on = not args.no_sim
    out_size = (640, 480)
    mouse = {"u": 0.5, "v": 0.5}

    def on_mouse(event, x, y, flags, _param):
        mouse["u"], mouse["v"] = x / out_size[0], y / out_size[1]
        if event == cv2.EVENT_MOUSEWHEEL:
            fake.radius_frac = min(0.1, max(0.009, fake.radius_frac * (1.1 if flags > 0 else 0.9)))

    win = "webcam follow test"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_mouse)
    last_t = time.monotonic()
    while True:
        ok, world = cap.read()
        if not ok:
            if args.video:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            print("Camera stopped sending frames.")
            break
        t = time.monotonic()
        dt, last_t = min(t - last_t, 0.2), t
        world = cv2.flip(world, 1) if not args.video else world  # mirror, feels natural
        h, w = world.shape[:2]

        # Fake beacon follows the mouse (mouse is in view coordinates).
        if sim_on:
            fake.x, fake.y = sim.to_world(mouse["u"], mouse["v"], w, h)
        else:
            fake.x, fake.y = mouse["u"], mouse["v"]
        fake.draw(world, t)

        view = sim.view(world, out_size) if sim_on else cv2.resize(world, out_size)
        blobs, hit, out = pipe.update(view, t)
        if sim_on:
            sim.step(out, dt)

        info = f"F fake beacon: {'on' if fake.enabled else 'off'}   S virtual drone: {'on' if sim_on else 'off'}"
        draw_overlay(view, blobs, hit, out, info)
        cv2.imshow(win, view)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord("f"):
            fake.enabled = not fake.enabled
        elif key == ord("s"):
            sim_on = not sim_on
            sim = VirtualDrone()
        elif key in (ord("+"), ord("=")):
            fake.radius_frac = min(0.1, fake.radius_frac * 1.15)
        elif key in (ord("-"), ord("_")):
            fake.radius_frac = max(0.009, fake.radius_frac / 1.15)
        elif key == ord("r"):
            pipe.reset()
            sim = VirtualDrone()

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())

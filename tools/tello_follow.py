"""Follow an LED wristband with a Ryze/DJI Tello from a laptop.

No modification to the drone. The Tello streams video over Wi-Fi; this script finds
every LED-coloured blob with the same colour rule as the ESP32-CAM firmware, keeps only
the one blinking the wristband's code (follow/blink.py, so traffic lights and screens are
ignored), runs the same yaw/pitch logic (follow/visual.py), and sends `rc` commands.
The Tello holds its own height. The Tello's camera has an IR-cut filter, so use the
green-LED wristband with it, not infrared.

    pip install opencv-python numpy
    python3 tools/tello_follow.py            # connect to the Tello's Wi-Fi first
    python3 tools/tello_follow.py --dry-run  # video + tracking overlay, no takeoff

Keys in the video window: t = take off, l = land, q = land and quit.
Keep a hand near the keyboard; 'l' is your safety switch.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "companion"))
from follow.blink import Blob, BlinkConfig, BlinkTracker  # noqa: E402
from follow.visual import RC_MID, Observation, State, VisualConfig, VisualFollower  # noqa: E402

TELLO_ADDR = ("192.168.10.1", 8889)
VIDEO_URL = "udp://0.0.0.0:11111"


class Tello:
    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 9000))
        self.sock.settimeout(3.0)

    def cmd(self, s: str, wait: bool = True) -> str:
        self.sock.sendto(s.encode(), TELLO_ADDR)
        if not wait:
            return ""
        try:
            data, _ = self.sock.recvfrom(1024)
            return data.decode(errors="ignore").strip()
        except socket.timeout:
            return "timeout"

    def rc(self, roll: int, pitch: int, throttle: int, yaw: int) -> None:
        # Tello rc arguments are -100..100.
        self.cmd(f"rc {roll} {pitch} {throttle} {yaw}", wait=False)


def find_blobs(frame_bgr: np.ndarray, channel: int = 1, min_level: int = 140, margin: int = 50, min_pixels: int = 12):
    """Same colour rule as blob_tracker.cpp, then every connected blob, largest first."""
    import cv2

    small = frame_bgr[::4, ::4].astype(np.int16)  # 960x720 -> 240x180
    b, g, r = small[..., 0], small[..., 1], small[..., 2]
    chans = {0: r, 1: g, 2: b}
    dom = chans[channel]
    others = [chans[c] for c in (0, 1, 2) if c != channel]
    mask = ((dom >= min_level) & (dom > others[0] + margin) & (dom > others[1] + margin)).astype(np.uint8)
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=4)
    h, w = mask.shape
    blobs = []
    for i in range(1, n):  # 0 is the background
        px = int(stats[i, cv2.CC_STAT_AREA])
        if px >= min_pixels:
            cx, cy = cents[i]
            blobs.append(Blob(float(cx / (w * 0.5) - 1.0), float(cy / (h * 0.5) - 1.0), px / (w * h), px))
    blobs.sort(key=lambda x: x.pixels, reverse=True)
    return blobs[:8]


def to_tello(rc_us: int) -> int:
    """Betaflight stick microseconds (1000..2000) -> Tello rc (-100..100)."""
    return int(max(-100, min(100, (rc_us - RC_MID) / 5)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="track only, never take off")
    ap.add_argument("--channel", type=int, default=1, help="LED colour: 0 red, 1 green, 2 blue")
    ap.add_argument("--target-area", type=float, default=0.002, help="blob area fraction at the desired distance")
    ap.add_argument("--blink-hz", type=float, default=2.5, help="must match BLINK_HZ in the wristband firmware")
    args = ap.parse_args()

    import cv2  # imported here so --help works without OpenCV

    # Lower gains than the ESP32 build: the Wi-Fi video adds ~0.3 s of latency.
    cfg = VisualConfig(kp_yaw=120.0, yaw_max=60, kp_pitch=60.0, pitch_max=40, target_area_frac=args.target_area)
    follower = VisualFollower(cfg)
    beacon = BlinkTracker(BlinkConfig(blink_hz=args.blink_hz))
    # The Tello does its own takeoff/landing and height hold, so we drive the follower's
    # state manually and use only its yaw/pitch outputs.
    follower.state = State.IDLE

    tello = Tello()
    print("command:", tello.cmd("command"))
    print("battery:", tello.cmd("battery?"))
    print("streamon:", tello.cmd("streamon"))
    cap = cv2.VideoCapture(VIDEO_URL, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("no video; is the laptop on the Tello's Wi-Fi?")
        return

    flying = False
    last_rc = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            t = time.monotonic()
            blobs = find_blobs(frame, args.channel)
            hit = beacon.update(t, blobs)
            found = hit is not None
            cx, cy, area = (hit.cx, hit.cy, hit.area_frac) if hit else (0.0, 0.0, 0.0)
            # Feed the follower as if we were at target height so it stays in FOLLOW/SEARCH.
            if flying and follower.state == State.IDLE:
                follower.state = State.FOLLOW
                follower._t_last_seen = t
                follower._t_last_height = t
            out = follower.update(Observation(t, found, cx=cx, cy=cy, area_frac=area, height_m=cfg.target_height_m))

            if flying and t - last_rc > 0.05:
                last_rc = t
                if out.state in (State.FOLLOW, State.SEARCH):
                    tello.rc(0, to_tello(out.pitch), 0, to_tello(out.yaw))
                else:
                    tello.rc(0, 0, 0, 0)
                if out.state == State.LAND:
                    print("follower requested land (lost band too long)")
                    tello.rc(0, 0, 0, 0)
                    print("land:", tello.cmd("land"))
                    flying = False
                    follower.state = State.IDLE

            # Overlay
            h, w = frame.shape[:2]
            for bl in blobs:  # every candidate in grey, the confirmed beacon in green
                px, py = int((bl.cx + 1) * w / 2), int((bl.cy + 1) * h / 2)
                cv2.circle(frame, (px, py), 10, (160, 160, 160), 1)
            if found:
                px, py = int((cx + 1) * w / 2), int((cy + 1) * h / 2)
                cv2.circle(frame, (px, py), 14, (0, 255, 0), 2)
            cv2.putText(frame, f"{out.state.value} area={area:.4f} yaw={to_tello(out.yaw)} pitch={to_tello(out.pitch)}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow("tello follow", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("t") and not flying and not args.dry_run:
                print("takeoff:", tello.cmd("takeoff"))
                flying = True
            elif key == ord("l") and flying:
                tello.rc(0, 0, 0, 0)
                print("land:", tello.cmd("land"))
                flying = False
                follower.state = State.IDLE
            elif key == ord("q"):
                break
    finally:
        if flying:
            tello.rc(0, 0, 0, 0)
            print("land:", tello.cmd("land"))
        tello.cmd("streamoff")
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

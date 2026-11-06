"""Save a few frames from Turbodrone's video stream, to check image quality offline.

Turbodrone must be running with video (start_drone.bat). Then:

    python tools/grab_frames.py                  # 10 frames to E:\\drone follower\\frames
    python tools/grab_frames.py --count 30 --out frames

Point the drone's camera at something with colour and detail (a bookshelf, a rug) in
normal room light. Attach one or two of the saved .jpg files in the chat with Claude.
Standard library only.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000/mjpeg")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--every", type=float, default=0.5, help="seconds between saved frames")
    default_out = r"E:\drone follower\frames" if os.name == "nt" else "frames"
    ap.add_argument("--out", default=default_out)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    try:
        stream = urllib.request.urlopen(args.url, timeout=10)
    except Exception as e:
        print(f"Could not open {args.url}: {e}. Is Turbodrone running with video?")
        return 1

    buf = b""
    saved, last = 0, 0.0
    deadline = time.time() + max(30.0, args.count * args.every * 4)
    while saved < args.count and time.time() < deadline:
        chunk = stream.read(16384)
        if not chunk:
            break
        buf += chunk
        while True:
            start = buf.find(b"\xff\xd8")
            end = buf.find(b"\xff\xd9", start + 2) if start >= 0 else -1
            if start < 0 or end < 0:
                buf = buf[start:] if start > 0 else buf
                break
            jpg, buf = buf[start:end + 2], buf[end + 2:]
            now = time.time()
            if now - last >= args.every:
                last = now
                path = os.path.join(args.out, f"frame_{saved:03d}.jpg")
                with open(path, "wb") as f:
                    f.write(jpg)
                saved += 1
                print("saved", path, f"({len(jpg)} bytes)")
                if saved >= args.count:
                    break
    print(f"done: {saved} frame(s) in {args.out}")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())

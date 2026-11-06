"""Search for an undocumented drone command (e.g. obstacle avoidance) by setting extra
bits in the stick packets while the backend's status sniffer watches the drone's reply.

PROPS OFF. Drone on the floor. Turbodrone (patched) running, page open.

    python tools/oa_probe.py --scan            # try each candidate bit for 6 s
    python tools/oa_probe.py --byte7 0x10      # hold one bit until Enter
    python tools/oa_probe.py --clear           # all bits off

While it runs, watch the "Drone backend" window for lines like
    [drone-status] ... flags=0x.. changed: [4] 12->32
A byte that flips when a bit is set, and flips back when it is cleared, is the
drone acknowledging that command. Note which bit did it and tell Claude.

Candidates (from the WiFi UAV app's packet layout; these bits are unused by the app):
    byte 7: 0x08 0x10 0x20 0x40      byte 6: 0x10 0x20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

CANDIDATES = [(0x00, 0x08), (0x00, 0x10), (0x00, 0x20), (0x00, 0x40), (0x10, 0x00), (0x20, 0x00)]


async def send(ws, b6: int, b7: int) -> None:
    await ws.send(json.dumps({"type": "raw_bits", "byte6": b6, "byte7": b7}))


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="ws://localhost:8000/ws")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--byte6", type=lambda s: int(s, 0), default=0)
    ap.add_argument("--byte7", type=lambda s: int(s, 0), default=0)
    ap.add_argument("--hold", type=float, default=6.0, help="seconds per candidate in --scan")
    ap.add_argument("--clear", action="store_true")
    args = ap.parse_args()

    try:
        import websockets
    except ImportError:
        print("Run this with Turbodrone's Python: turbodrone\\backend\\venv\\Scripts\\python.exe tools\\oa_probe.py ...")
        return 2

    print("PROPS OFF. Never run this with propellers fitted.")
    async with websockets.connect(args.url) as ws:
        if args.clear:
            await send(ws, 0, 0)
            print("bits cleared")
            return 0
        if args.scan:
            for b6, b7 in CANDIDATES:
                print(f"{time.strftime('%H:%M:%S')}  SET   byte6=0x{b6:02x} byte7=0x{b7:02x}  (watch the backend log)")
                await send(ws, b6, b7)
                await asyncio.sleep(args.hold)
                print(f"{time.strftime('%H:%M:%S')}  CLEAR")
                await send(ws, 0, 0)
                await asyncio.sleep(3.0)
            print("scan done, all bits cleared")
            return 0
        await send(ws, args.byte6, args.byte7)
        print(f"holding byte6=0x{args.byte6:02x} byte7=0x{args.byte7:02x}. Press Enter to clear and exit.")
        await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        await send(ws, 0, 0)
        print("bits cleared")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

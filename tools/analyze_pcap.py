"""Summarise a packet capture of the WiFi UAV app talking to the drone.

Made for captures from PCAPdroid (Android, no root) but reads any classic .pcap
(Ethernet, raw IP or Linux SLL link types). Standard library only.

    python tools/analyze_pcap.py capture.pcap
    python tools/analyze_pcap.py capture.pcap --ip 192.168.169.1 --samples 6

Prints: the UDP/TCP conversations with the drone (ports, packet counts, sizes in
each direction), then for each phone->drone port the distinct packet "shapes"
(length + first bytes) with hex samples and when they were first sent. That is
what Turbodrone needs: which port starts the video, the exact start packets,
and the stick packet layout. Paste the output to Claude.
"""

from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter, OrderedDict, defaultdict


def read_pcap(path: str):
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 24:
        raise SystemExit("File too short to be a pcap.")
    magic = data[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        endian = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        endian = ">"
    elif magic == b"\x0a\x0d\x0d\x0a":
        raise SystemExit("This is pcapng. In PCAPdroid choose 'PCAP' format, or convert with Wireshark (Save As .pcap).")
    else:
        raise SystemExit("Not a pcap file.")
    nano = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    linktype = struct.unpack(endian + "I", data[20:24])[0]
    off = 24
    while off + 16 <= len(data):
        ts_s, ts_frac, incl, _orig = struct.unpack(endian + "IIII", data[off:off + 16])
        off += 16
        pkt = data[off:off + incl]
        off += incl
        yield ts_s + ts_frac / (1e9 if nano else 1e6), linktype, pkt


def ip_payload(linktype: int, pkt: bytes):
    """Return (src, dst, proto, sport, dport, payload) or None."""
    if linktype == 1:          # Ethernet
        if len(pkt) < 14:
            return None
        etype = struct.unpack("!H", pkt[12:14])[0]
        if etype == 0x8100 and len(pkt) >= 18:
            etype = struct.unpack("!H", pkt[16:18])[0]
            pkt = pkt[18:]
        else:
            pkt = pkt[14:]
        if etype != 0x0800:
            return None
    elif linktype == 113:      # Linux SLL
        pkt = pkt[16:]
    elif linktype in (101, 228, 12, 14):  # raw IPv4
        pass
    elif linktype == 0:        # BSD loopback / null
        pkt = pkt[4:]
    else:
        return None
    if len(pkt) < 20 or pkt[0] >> 4 != 4:
        return None
    ihl = (pkt[0] & 0x0F) * 4
    proto = pkt[9]
    src = ".".join(map(str, pkt[12:16]))
    dst = ".".join(map(str, pkt[16:20]))
    body = pkt[ihl:]
    if proto == 17 and len(body) >= 8:
        sport, dport = struct.unpack("!HH", body[:4])
        return src, dst, "UDP", sport, dport, body[8:]
    if proto == 6 and len(body) >= 20:
        sport, dport = struct.unpack("!HH", body[:4])
        doff = (body[12] >> 4) * 4
        return src, dst, "TCP", sport, dport, body[doff:]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--ip", help="drone IP (default: guess the busiest 192.168.x.1)")
    ap.add_argument("--samples", type=int, default=4, help="hex samples per packet shape")
    ap.add_argument("--bytes", type=int, default=48, help="bytes of each sample to print")
    args = ap.parse_args()

    pkts = []
    for ts, lt, raw in read_pcap(args.pcap):
        p = ip_payload(lt, raw)
        if p:
            pkts.append((ts, *p))
    if not pkts:
        print("No IPv4 TCP/UDP packets found.")
        return 1
    t0 = pkts[0][0]

    drone = args.ip
    if not drone:
        c = Counter()
        for _, src, dst, *_ in pkts:
            for a in (src, dst):
                if a.startswith("192.168.") and a.endswith(".1"):
                    c[a] += 1
        drone = c.most_common(1)[0][0] if c else None
    if not drone:
        print("Could not guess the drone IP; pass --ip.")
        return 1
    print(f"Drone IP: {drone}   packets in file: {len(pkts)}   duration: {pkts[-1][0] - t0:.1f} s\n")

    conv = defaultdict(lambda: {"n": 0, "bytes": 0, "sizes": Counter(), "first": None})
    shapes = defaultdict(OrderedDict)   # (proto, dport) -> {shape: [first_t, count, samples]}
    for ts, src, dst, proto, sport, dport, pl in pkts:
        if drone not in (src, dst):
            continue
        direction = "phone->drone" if dst == drone else "drone->phone"
        key = (proto, direction, sport, dport)
        c = conv[key]
        c["n"] += 1
        c["bytes"] += len(pl)
        c["sizes"][len(pl)] += 1
        c["first"] = c["first"] if c["first"] is not None else ts - t0
        if direction == "phone->drone" and pl:
            shape = (len(pl), pl[:2].hex())
            entry = shapes[(proto, dport)].setdefault(shape, [ts - t0, 0, []])
            entry[1] += 1
            if len(entry[2]) < args.samples:
                entry[2].append((ts - t0, pl))

    print("Conversations with the drone:")
    print(f"  {'proto':5} {'direction':13} {'ports':>13}  {'first@s':>7} {'pkts':>6} {'bytes':>9}  common sizes")
    for (proto, d, sp, dp), c in sorted(conv.items(), key=lambda kv: kv[1]["first"]):
        sizes = ", ".join(f"{s}x{n}" for s, n in c["sizes"].most_common(4))
        print(f"  {proto:5} {d:13} {sp:>5}->{dp:<6}  {c['first']:7.2f} {c['n']:6} {c['bytes']:9}  {sizes}")

    print("\nPhone->drone packet shapes (length, first bytes), in order of first use:")
    for (proto, dport), table in shapes.items():
        print(f"\n  {proto} to port {dport}:")
        for (length, head), (first, count, samples) in sorted(table.items(), key=lambda kv: kv[1][0]):
            print(f"    len {length:4}  starts {head}  first at {first:6.2f}s  x{count}")
            for t, pl in samples:
                more = "..." if len(pl) > args.bytes else ""
                print(f"      {t:6.2f}s  {pl[:args.bytes].hex(' ')}{more}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

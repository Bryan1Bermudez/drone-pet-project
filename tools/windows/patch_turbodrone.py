"""Patch a Turbodrone checkout for the Contixo F19 Arvo (WiFi UAV family).

Run with Turbodrone's own Python, from anywhere:

    <turbodrone>\\backend\\venv\\Scripts\\python.exe patch_turbodrone.py <turbodrone folder>

What it changes (each edit is marked "drone-pet-project patch"):

* backend: starting speed tier and stick profile come from backend/.env
  (the shipped .env uses Medium and "normal").
* backend: new "calibrate" command that holds the gyro-calibration flag for
  half a second.
* backend: video ports and control-packet axis order can be set from .env
  (WIFI_UAV_VIDEO_PORTS, WIFI_UAV_AXIS_ORDER), so video can be probed on
  8800 and 8801 without changing how the sticks are sent.
* backend: throttle (climb/descend) also scaled, 60% with the shipped .env, so it
  does not rev the motors to full on every climb (WIFI_UAV_THROTTLE_SPEED_INDEX;
  unset = original behaviour, the shipped .env sets 1).
* backend: before asking for video, send an empty packet to udp/1234 (where the
  drone's video comes from) so a phone's tethering NAT or Windows Firewall lets
  the video back in (WIFI_UAV_PUNCH_PORTS).
* backend: video frame requests carry the live stick command instead of a fixed
  neutral one (stock behaviour flooded out the real sticks once video streamed);
  one-shot takeoff/land/stop/calibrate/flip bits stay in the RC packets only.
* backend + frontend: trim (I/K pitch, J/L roll, U/O yaw, 0 reset), added to the
  stick bytes and saved to backend/trim.json, to cancel steady drift.
* frontend: speed selector starts on "Medium"; key C = gyro calibration (on the
  ground only), Space = emergency motor stop.

Safe to run more than once. Originals are kept as *.orig next to each file.
Tested against Turbodrone commit 2c09cf8 (June 2026).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

MARK = "drone-pet-project patch"

# (relative path, old text, new text[, expected count[, skip if this text is present]]).
# Each edit is applied
# unless its new text is already present, so re-running after an update only
# adds the new edits.
EDITS: list[tuple] = [
    (
        "backend/web_server.py",
        "        model = WifiUavRcModel()\n",
        "        model = WifiUavRcModel(profile=os.getenv(\"WIFI_UAV_PROFILE\", \"precise\"))  # drone-pet-project patch\n"
        "        model.set_speed_index(int(os.getenv(\"WIFI_UAV_SPEED_INDEX\", \"0\")))  # drone-pet-project patch\n",
    ),
    (
        "backend/web_server.py",
        "            elif msg_type == \"takeoff\":\n",
        "            elif msg_type == \"calibrate\":  # drone-pet-project patch\n"
        "                async def _hold_calibration(m=flight_controller.model):\n"
        "                    # Hold the flag for ~0.5 s so a dropped UDP packet cannot lose it.\n"
        "                    for _ in range(10):\n"
        "                        try:\n"
        "                            m.calibration_flag = True\n"
        "                        except Exception:\n"
        "                            return\n"
        "                        await asyncio.sleep(0.05)\n"
        "                asyncio.create_task(_hold_calibration())\n"
        "                logger.info(\"[drone-pet-project] gyro calibration requested\")\n"
        "            elif msg_type == \"takeoff\":\n",
    ),
    (
        "backend/protocols/wifi_uav_video_protocol.py",
        "import logging\n",
        "import logging\nimport os  # drone-pet-project patch\n",
    ),
    (
        "backend/protocols/wifi_uav_video_protocol.py",
        "        nativeStart() does. The FLD/legacy path keeps the single-port behavior.\n        \"\"\"\n",
        "        nativeStart() does. The FLD/legacy path keeps the single-port behavior.\n        \"\"\"\n"
        "        env_ports = os.getenv(\"WIFI_UAV_VIDEO_PORTS\", \"\").strip()  # drone-pet-project patch\n"
        "        if env_ports:\n"
        "            ports = tuple(int(p) for p in env_ports.split(\",\") if p.strip())\n"
        "            if ports:\n"
        "                logger.info(\"[wifi-uav] video ports from WIFI_UAV_VIDEO_PORTS: %s\", ports)\n"
        "                return ports\n",
    ),
    (
        "backend/protocols/wifi_uav_rc_protocol_adapter.py",
        "import socket\n",
        "import os  # drone-pet-project patch\nimport socket\n",
    ),
    (
        "backend/protocols/wifi_uav_rc_protocol_adapter.py",
        "        if self.capabilities.transport == \"fld_compat\":\n            axis_controls = [\n",
        "        default_order = \"fld\" if self.capabilities.transport == \"fld_compat\" else \"uav\"\n"
        "        axis_order = os.getenv(\"WIFI_UAV_AXIS_ORDER\", default_order).strip().lower()  # drone-pet-project patch\n"
        "        if axis_order == \"fld\":\n            axis_controls = [\n",
    ),
    (
        "frontend/src/hooks/useControls.ts",
        "  const [speedTier, setSpeedTierSt] = useState<SpeedTier>(2);\n",
        "  const [speedTier, setSpeedTierSt] = useState<SpeedTier>(0); // drone-pet-project patch: start slow\n",
        1,
        "drone-pet-project patch: start at Medium",  # superseded by the Medium edit below
    ),
    (
        "frontend/src/hooks/useControls.ts",
        "  /* --------------- camera tilt keyboard hold ---------------- */\n",
        "  /* --------------- drone-pet-project patch: C = calibrate, Space = stop --- */\n"
        "  useEffect(() => {\n"
        "    const down = (e: KeyboardEvent) => {\n"
        "      if (e.repeat) return;\n"
        "      let type: string | null = null;\n"
        "      if (e.key === \"c\" || e.key === \"C\") type = \"calibrate\";\n"
        "      if (e.key === \" \") type = \"estop\";\n"
        "      if (!type) return;\n"
        "      e.preventDefault();\n"
        "      if (ws.current?.readyState === WebSocket.OPEN) {\n"
        "        ws.current.send(JSON.stringify({ type }));\n"
        "      }\n"
        "    };\n"
        "    window.addEventListener(\"keydown\", down);\n"
        "    return () => window.removeEventListener(\"keydown\", down);\n"
        "  }, []);\n"
        "\n"
        "  /* --------------- camera tilt keyboard hold ---------------- */\n",
    ),
    (
        # Start the speed selector on Medium: Low was too weak on the F19.
        "frontend/src/hooks/useControls.ts",
        "  const [speedTier, setSpeedTierSt] = useState<SpeedTier>(0); // drone-pet-project patch: start slow\n",
        "  const [speedTier, setSpeedTierSt] = useState<SpeedTier>(1); // drone-pet-project patch: start at Medium\n",
    ),
    (
        # Quieter climbs: throttle normally ignores the speed tier (always 100%).
        "backend/protocols/wifi_uav_rc_protocol_adapter.py",
        "                self._apply_speed_scale(drone_model.throttle, 2),\n",
        "                self._apply_speed_scale(drone_model.throttle, int(os.getenv(\"WIFI_UAV_THROTTLE_SPEED_INDEX\", \"2\"))),  # drone-pet-project patch\n",
        2,
    ),
    (
        # Video return path: the drone sends video FROM udp/1234 to the port that sent
        # START to udp/8800. A NAT (phone USB tethering) or Windows Firewall only lets in
        # replies from ports we have sent to, so first send an empty packet to udp/1234
        # from the same socket. Ports from WIFI_UAV_PUNCH_PORTS (default 1234, empty = off).
        "backend/protocols/wifi_uav_video_protocol.py",
        "    def send_start_command(self) -> None:\n",
        "    def send_start_command(self) -> None:\n"
        "        for port in [int(p) for p in os.getenv(\"WIFI_UAV_PUNCH_PORTS\", \"1234\").split(\",\") if p.strip()]:\n"
        "            self._safe_sendto(b\"\", port, \"PUNCH\")  # drone-pet-project patch: open video return path\n",
    ),
    (
        # Live sticks in the video requests. Every frame request also carries a stick
        # command; stock Turbodrone puts a fixed "centred, no buttons" one there, which
        # floods out the real RC packets once video streams (F19: nothing responded with
        # video on). The WiFi UAV app embeds the real command, so do the same: current
        # stick bytes and headless flag, camera tilt bits, but never the one-shot
        # takeoff/land/stop/calibrate/flip bits (those only go in the RC packets).
        "backend/protocols/wifi_uav_video_protocol.py",
        "    build_native_ack_packet,\n)\n",
        "    build_native_ack_packet,\n    NEUTRAL_EXTENDED_COMMAND,  # drone-pet-project patch\n)\n",
    ),
    (
        "backend/protocols/wifi_uav_video_protocol.py",
        "            rc_adapter.set_socket(self._sock)\n",
        "            self._rc_adapter = rc_adapter  # drone-pet-project patch: live sticks in requests\n"
        "            rc_adapter.set_socket(self._sock)\n",
    ),
    (
        "backend/protocols/wifi_uav_video_protocol.py",
        "        rqst_a = build_native_ack_packet(command_seq, [])\n"
        "        rqst_b = build_native_ack_packet(command_seq, self._build_ack_slots(frame_id))\n",
        "        cmd = self._live_command()  # drone-pet-project patch\n"
        "        rqst_a = build_native_ack_packet(command_seq, [], command=cmd)\n"
        "        rqst_b = build_native_ack_packet(command_seq, self._build_ack_slots(frame_id), command=cmd)\n",
    ),
    (
        "backend/protocols/wifi_uav_video_protocol.py",
        "    def _safe_sendto(self, payload: bytes, port: int, label: str) -> bool:\n",
        "    def _live_command(self) -> bytes:  # drone-pet-project patch\n"
        "        \"\"\"Extended 66 14 command with the current sticks, no one-shot action bits.\"\"\"\n"
        "        rc = getattr(self, \"_rc_adapter\", None)\n"
        "        controls = getattr(rc, \"_last_controls\", None) if rc is not None else None\n"
        "        if not controls or len(controls) != 4:\n"
        "            return NEUTRAL_EXTENDED_COMMAND\n"
        "        tilt = int(getattr(rc, \"_last_command\", 0)) & 0xC0\n"
        "        headless = int(getattr(rc, \"_last_headless\", 0x02)) & 0xFF\n"
        "        body = bytes([0x66, 0x14] + [int(c) & 0xFF for c in controls] + [tilt, headless]) + bytes(10)\n"
        "        xor = 0\n"
        "        for b in body[2:18]:\n"
        "            xor ^= b\n"
        "        return body + bytes([xor, 0x99])\n"
        "\n"
        "    def _safe_sendto(self, payload: bytes, port: int, label: str) -> bool:\n",
    ),
    (
        # Trim: steady offsets added to roll/pitch/yaw so a drone that always drifts one
        # way can be nudged back, like the trim buttons on a toy remote. Applied to the
        # final stick bytes, so the live command in video requests includes it too.
        "backend/protocols/wifi_uav_rc_protocol_adapter.py",
        "        controls: List[int] = axis_controls + [\n",
        "        trim = {\"R\": int(getattr(self, \"trim_roll\", 0)), \"P\": int(getattr(self, \"trim_pitch\", 0)),\n"
        "                \"Y\": int(getattr(self, \"trim_yaw\", 0))}  # drone-pet-project patch: trim\n"
        "        axis_controls = [max(0, min(255, v + trim.get(lbl, 0))) for v, lbl in zip(axis_controls, axis_labels)]\n"
        "        controls: List[int] = axis_controls + [\n",
    ),
    (
        "backend/web_server.py",
        "@app.websocket(\"/ws\")\n",
        "# drone-pet-project patch: trim, saved next to this file so it survives restarts\n"
        "_TRIM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), \"trim.json\")\n"
        "\n"
        "\n"
        "def _save_trim(rc) -> None:\n"
        "    import json as _json\n"
        "    try:\n"
        "        with open(_TRIM_FILE, \"w\") as f:\n"
        "            _json.dump({a: int(getattr(rc, f\"trim_{a}\", 0)) for a in (\"roll\", \"pitch\", \"yaw\")}, f)\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "\n"
        "def _load_trim(rc) -> None:\n"
        "    import json as _json\n"
        "    try:\n"
        "        with open(_TRIM_FILE) as f:\n"
        "            for a, v in _json.load(f).items():\n"
        "                if a in (\"roll\", \"pitch\", \"yaw\"):\n"
        "                    setattr(rc, f\"trim_{a}\", max(-40, min(40, int(v))))\n"
        "        logger.info(\"[drone-pet-project] trim loaded: roll=%+d pitch=%+d yaw=%+d\",\n"
        "                    rc.trim_roll if hasattr(rc, 'trim_roll') else 0,\n"
        "                    rc.trim_pitch if hasattr(rc, 'trim_pitch') else 0,\n"
        "                    rc.trim_yaw if hasattr(rc, 'trim_yaw') else 0)\n"
        "    except FileNotFoundError:\n"
        "        pass\n"
        "    except Exception:\n"
        "        logger.warning(\"[drone-pet-project] could not read %s\", _TRIM_FILE)\n"
        "\n"
        "\n"
        "@app.websocket(\"/ws\")\n",
    ),
    (
        "backend/web_server.py",
        "        rc_proto = WifiUavRcProtocolAdapter(drone_ip, ctrl_port, variant=wifi_uav_variant)\n",
        "        rc_proto = WifiUavRcProtocolAdapter(drone_ip, ctrl_port, variant=wifi_uav_variant)\n"
        "        _load_trim(rc_proto)  # drone-pet-project patch\n",
    ),
    (
        "backend/web_server.py",
        "            elif msg_type == \"takeoff\":\n",
        "            elif msg_type == \"trim\":  # drone-pet-project patch: drift trim\n"
        "                rc = flight_controller.protocol\n"
        "                axis = str(data.get(\"axis\", \"\"))\n"
        "                if axis == \"reset\":\n"
        "                    for a in (\"roll\", \"pitch\", \"yaw\"):\n"
        "                        setattr(rc, f\"trim_{a}\", 0)\n"
        "                elif axis in (\"roll\", \"pitch\", \"yaw\"):\n"
        "                    v = int(getattr(rc, f\"trim_{axis}\", 0)) + int(data.get(\"delta\", 0))\n"
        "                    setattr(rc, f\"trim_{axis}\", max(-40, min(40, v)))\n"
        "                _save_trim(rc)\n"
        "                logger.info(\"[drone-pet-project] trim roll=%+d pitch=%+d yaw=%+d\",\n"
        "                            getattr(rc, \"trim_roll\", 0), getattr(rc, \"trim_pitch\", 0), getattr(rc, \"trim_yaw\", 0))\n"
        "            elif msg_type == \"takeoff\":\n",
    ),
    (
        # Trim keys: I/K pitch, J/L roll, U/O yaw, 0 resets. 2 stick steps per press.
        "frontend/src/hooks/useControls.ts",
        "  /* ------------- helpers / commands ------------------------- */\n",
        "  /* drone-pet-project patch: trim keys */\n"
        "  useEffect(() => {\n"
        "    const keys: Record<string, [string, number]> = {\n"
        "      i: [\"pitch\", 2], k: [\"pitch\", -2], l: [\"roll\", 2], j: [\"roll\", -2],\n"
        "      o: [\"yaw\", 2], u: [\"yaw\", -2], \"0\": [\"reset\", 0],\n"
        "    };\n"
        "    const down = (e: KeyboardEvent) => {\n"
        "      const k = keys[e.key.toLowerCase()];\n"
        "      if (!k) return;\n"
        "      e.preventDefault();\n"
        "      if (ws.current?.readyState === WebSocket.OPEN) {\n"
        "        ws.current.send(JSON.stringify({ type: \"trim\", axis: k[0], delta: k[1] }));\n"
        "      }\n"
        "    };\n"
        "    window.addEventListener(\"keydown\", down);\n"
        "    return () => window.removeEventListener(\"keydown\", down);\n"
        "  }, []);\n"
        "\n"
        "  /* ------------- helpers / commands ------------------------- */\n",
    ),
    (
        # Watchdog: the page sends sticks 30 times a second. If it stops (window
        # hidden, browser frozen, tab closed), centre the sticks instead of
        # repeating the last command.
        "backend/web_server.py",
        "            data = await websocket.receive_json()\n",
        "            try:  # drone-pet-project patch: stick watchdog\n"
        "                data = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)\n"
        "            except asyncio.TimeoutError:\n"
        "                if flight_controller and not (plugin_manager and plugin_manager.running()):\n"
        "                    flight_controller.set_axes_from(\"watchdog\", 0, 0, 0, 0)\n"
        "                continue\n",
    ),
    (
        "backend/web_server.py",
        "        logger.info(\"[WebSocket] Client disconnected\")\n",
        "        logger.info(\"[WebSocket] Client disconnected\")\n"
        "        if flight_controller:  # drone-pet-project patch: centre sticks when the page goes away\n"
        "            flight_controller.set_axes_from(\"disconnect\", 0, 0, 0, 0)\n",
    ),
    (
        # Stuck keys: switching to another window while holding a key means the
        # page never sees the key-up, so that stick stayed at full.
        "frontend/src/hooks/useControls.ts",
        "  /* ------------- helpers / commands ------------------------- */\n",
        "  /* drone-pet-project patch: release all sticks when the window loses focus */\n"
        "  useEffect(() => {\n"
        "    const release = () => {\n"
        "      axesRef.current = { throttle: 0, yaw: 0, pitch: 0, roll: 0 };\n"
        "      setAxes({ ...axesRef.current });\n"
        "    };\n"
        "    const onVisibility = () => { if (document.hidden) release(); };\n"
        "    window.addEventListener(\"blur\", release);\n"
        "    document.addEventListener(\"visibilitychange\", onVisibility);\n"
        "    return () => {\n"
        "      window.removeEventListener(\"blur\", release);\n"
        "      document.removeEventListener(\"visibilitychange\", onVisibility);\n"
        "    };\n"
        "  }, []);\n"
        "\n"
        "  /* ------------- helpers / commands ------------------------- */\n",
    ),
]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_turbodrone.py <turbodrone folder>")
        return 2
    root = Path(sys.argv[1]).resolve()
    if not (root / "backend" / "web_server.py").exists():
        print(f"ERROR: {root} does not look like a Turbodrone folder (no backend/web_server.py)")
        return 2

    by_file: dict[str, list[tuple[str, str, int, str | None]]] = {}
    for edit in EDITS:
        rel, old, new = edit[:3]
        expected = edit[3] if len(edit) > 3 else 1
        skip_if = edit[4] if len(edit) > 4 else None
        by_file.setdefault(rel, []).append((old, new, expected, skip_if))

    failed = False
    for rel, edits in by_file.items():
        path = root / rel
        # Git for Windows usually checks files out with CRLF line endings.
        # Read with newline translation, match on "\n", write back the same style.
        crlf = b"\r\n" in path.read_bytes()
        text = path.read_text(encoding="utf-8")
        applied = 0
        for old, new, expected, skip_if in edits:
            if new in text or (skip_if and skip_if in text):
                continue  # already in place, or replaced by a later edit
            count = text.count(old)
            if count != expected:
                print(f"ERROR: {rel}: expected the original text {expected} time(s), found {count}. "
                      "Turbodrone may have changed; ask Claude to update the patch.")
                failed = True
                break
            text = text.replace(old, new)
            applied += 1
        else:
            if applied == 0:
                print(f"already patched: {rel}")
                continue
            backup = path.with_name(path.name + ".orig")
            if not backup.exists():
                shutil.copy2(path, backup)
            path.write_text(text, encoding="utf-8", newline="\r\n" if crlf else "\n")
            print(f"patched: {rel}")

    if failed:
        print("Some files were NOT patched (see above). Nothing half-done was written to them.")
        return 1
    print("Turbodrone patched OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

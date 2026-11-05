"""Patch a Turbodrone checkout for the Contixo F19 Arvo (WiFi UAV family).

Run with Turbodrone's own Python, from anywhere:

    <turbodrone>\\backend\\venv\\Scripts\\python.exe patch_turbodrone.py <turbodrone folder>

What it changes (each edit is marked "drone-pet-project patch"):

* backend: start at the lowest speed tier and the gentle "precise" stick
  profile (both overridable in backend/.env).
* backend: new "calibrate" command that holds the gyro-calibration flag for
  half a second.
* backend: video ports and control-packet axis order can be set from .env
  (WIFI_UAV_VIDEO_PORTS, WIFI_UAV_AXIS_ORDER), so video can be probed on
  8800 and 8801 without changing how the sticks are sent.
* backend: throttle (climb/descend) also scaled, 60% with the shipped .env, so it
  does not rev the motors to full on every climb (WIFI_UAV_THROTTLE_SPEED_INDEX;
  unset = original behaviour, the shipped .env sets 1).
* frontend: speed selector starts on "Low"; key C = gyro calibration (on the
  ground only), Space = emergency motor stop.

Safe to run more than once. Originals are kept as *.orig next to each file.
Tested against Turbodrone commit 2c09cf8 (June 2026).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

MARK = "drone-pet-project patch"

# (relative path, old text, new text[, expected count]). Each edit is applied
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
        # Quieter climbs: throttle normally ignores the speed tier (always 100%).
        "backend/protocols/wifi_uav_rc_protocol_adapter.py",
        "                self._apply_speed_scale(drone_model.throttle, 2),\n",
        "                self._apply_speed_scale(drone_model.throttle, int(os.getenv(\"WIFI_UAV_THROTTLE_SPEED_INDEX\", \"2\"))),  # drone-pet-project patch\n",
        2,
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

    by_file: dict[str, list[tuple[str, str, int]]] = {}
    for edit in EDITS:
        rel, old, new = edit[:3]
        expected = edit[3] if len(edit) > 3 else 1
        by_file.setdefault(rel, []).append((old, new, expected))

    failed = False
    for rel, edits in by_file.items():
        path = root / rel
        # Git for Windows usually checks files out with CRLF line endings.
        # Read with newline translation, match on "\n", write back the same style.
        crlf = b"\r\n" in path.read_bytes()
        text = path.read_text(encoding="utf-8")
        applied = 0
        for old, new, expected in edits:
            if new in text:
                continue  # this edit is already in place
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

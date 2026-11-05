"""Does this PC's Wi-Fi card support Windows 11 "Dual STA" (a second Wi-Fi
connection on the same card)? And can that second connection join the drone?

Usage (any Windows Python 3, no extra packages):

    python check_dual_sta.py                 # just check, changes nothing
    python check_dual_sta.py --try "Contixo-F19-XXXX"
                                             # experiment: join the drone on the
                                             # secondary interface, keep home Wi-Fi

Background (Microsoft docs, "Dual STA connectivity" and Native WiFi
"Query and configure dual STA"): Windows 11 drivers can expose a secondary
station interface. Windows only uses it while an app keeps
wlan_intf_opcode_secondary_sta_synchronized_connections set to TRUE, and the
docs describe it following the primary connection on another band. Whether it
can join a *different* network (the drone) is not documented, hence --try.
"""

from __future__ import annotations

import argparse
import ctypes
import platform
import sys
import time
from ctypes import wintypes

if sys.platform != "win32":
    print("This tool only runs on Windows.")
    sys.exit(2)

wlanapi = ctypes.WinDLL("wlanapi.dll")

# WLAN_INTF_OPCODE values from wlanapi.h (sequential from 0).
OPCODE_CURRENT_CONNECTION = 7
OPCODE_SECONDARY_STA_INTERFACES = 17
OPCODE_SECONDARY_STA_SYNCHRONIZED_CONNECTIONS = 18

ERROR_SUCCESS = 0
ERRORS = {
    5: "access denied",
    50: "not supported by this adapter/driver",
    87: "invalid parameter (Windows or driver does not know this request)",
    1168: "not found",
    1169: "no matching device",
    2: "file not found",
}


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __str__(self) -> str:
        d4 = bytes(self.Data4)
        return "{%08x-%04x-%04x-%s-%s}" % (self.Data1, self.Data2, self.Data3, d4[:2].hex(), d4[2:].hex())


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [("InterfaceGuid", GUID),
                ("strInterfaceDescription", ctypes.c_wchar * 256),
                ("isState", ctypes.c_int)]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [("dwNumberOfItems", wintypes.DWORD),
                ("dwIndex", wintypes.DWORD),
                ("InterfaceInfo", WLAN_INTERFACE_INFO * 1)]


class WLAN_CONNECTION_PARAMETERS(ctypes.Structure):
    _fields_ = [("wlanConnectionMode", ctypes.c_int),   # 0 = use profile
                ("strProfile", ctypes.c_wchar_p),
                ("pDot11Ssid", ctypes.c_void_p),
                ("pDesiredBssidList", ctypes.c_void_p),
                ("dot11BssType", ctypes.c_int),         # 1 = infrastructure
                ("dwFlags", wintypes.DWORD)]


STATES = {0: "not ready", 1: "connected", 2: "ad hoc", 3: "disconnecting",
          4: "disconnected", 5: "associating", 6: "discovering", 7: "authenticating"}


def err(code: int) -> str:
    return f"error {code} ({ERRORS.get(code, 'see Windows system error codes')})"


def interfaces(handle, query_fn=None, guid=None):
    """List of (GUID, description, state) from WlanEnumInterfaces or a secondary query."""
    plist = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
    if query_fn is None:
        rc = wlanapi.WlanEnumInterfaces(handle, None, ctypes.byref(plist))
    else:
        size = wintypes.DWORD()
        rc = wlanapi.WlanQueryInterface(handle, ctypes.byref(guid), OPCODE_SECONDARY_STA_INTERFACES,
                                        None, ctypes.byref(size), ctypes.byref(plist), None)
    if rc != ERROR_SUCCESS:
        return rc, []
    n = plist.contents.dwNumberOfItems
    if n > 64:  # nonsense: the opcode was not what we think
        wlanapi.WlanFreeMemory(plist)
        return 87, []
    arr = (WLAN_INTERFACE_INFO * n).from_address(ctypes.addressof(plist.contents.InterfaceInfo))
    out = [(GUID.from_buffer_copy(i.InterfaceGuid), i.strInterfaceDescription, i.isState) for i in arr]
    wlanapi.WlanFreeMemory(plist)
    return ERROR_SUCCESS, out


def current_profile(handle, guid) -> str | None:
    size = wintypes.DWORD()
    data = ctypes.c_void_p()
    rc = wlanapi.WlanQueryInterface(handle, ctypes.byref(guid), OPCODE_CURRENT_CONNECTION,
                                    None, ctypes.byref(size), ctypes.byref(data), None)
    if rc != ERROR_SUCCESS or not data.value:
        return None
    # WLAN_CONNECTION_ATTRIBUTES: isState (4), wlanConnectionMode (4), strProfileName[256]
    name = ctypes.wstring_at(data.value + 8)
    wlanapi.WlanFreeMemory(data)
    return name


def open_profile_xml(ssid: str) -> str:
    from xml.sax.saxutils import escape
    s = escape(ssid)
    return ('<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">'
            f'<name>{s}</name><SSIDConfig><SSID><name>{s}</name></SSID></SSIDConfig>'
            '<connectionType>ESS</connectionType><connectionMode>manual</connectionMode>'
            '<MSM><security><authEncryption><authentication>open</authentication>'
            '<encryption>none</encryption><useOneX>false</useOneX></authEncryption></security></MSM>'
            '</WLANProfile>')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--try", dest="try_ssid", metavar="DRONE_SSID",
                    help="try to join this network on the secondary interface")
    args = ap.parse_args()

    print(f"Windows: {platform.platform()}  (Dual STA needs Windows 11)")
    handle = wintypes.HANDLE()
    version = wintypes.DWORD()
    rc = wlanapi.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle))
    if rc != ERROR_SUCCESS:
        print(f"Could not open the Wi-Fi service: {err(rc)}")
        return 1

    try:
        rc, prim = interfaces(handle)
        if rc != ERROR_SUCCESS or not prim:
            print(f"No Wi-Fi adapters found ({err(rc) if rc else 'empty list'}).")
            return 1

        found = None
        for guid, desc, state in prim:
            print(f"\nAdapter: {desc}\n  state: {STATES.get(state, state)}, network: {current_profile(handle, guid)}")
            rc, sec = interfaces(handle, query_fn=True, guid=guid)
            if rc != ERROR_SUCCESS:
                print(f"  Dual STA: NO ({err(rc)})")
            elif not sec:
                print("  Dual STA: NO (driver reports 0 secondary interfaces)")
            else:
                print(f"  Dual STA: YES, {len(sec)} secondary interface(s):")
                for sguid, sdesc, sstate in sec:
                    print(f"    {sdesc}  [{STATES.get(sstate, sstate)}]")
                found = found or (guid, sec[0][0])

        if not found:
            print("\nResult: this Wi-Fi card cannot hold a second connection. "
                  "Staying online while flying needs a second adapter.")
            return 0
        if not args.try_ssid:
            print("\nResult: the card supports Dual STA. Run again with --try \"<drone Wi-Fi name>\" "
                  "(drone switched on) to test whether the second connection can join the drone.")
            return 0

        primary, secondary = found
        enable = wintypes.BOOL(True)
        rc = wlanapi.WlanSetInterface(handle, ctypes.byref(primary), OPCODE_SECONDARY_STA_SYNCHRONIZED_CONNECTIONS,
                                      ctypes.sizeof(enable), ctypes.byref(enable), None)
        print(f"\nEnable secondary connections: {'OK' if rc == 0 else err(rc)}")

        reason = wintypes.DWORD()
        rc = wlanapi.WlanSetProfile(handle, ctypes.byref(secondary), 0, open_profile_xml(args.try_ssid),
                                    None, True, None, ctypes.byref(reason))
        print(f"Add drone profile on secondary interface: {'OK' if rc == 0 else err(rc)}")

        params = WLAN_CONNECTION_PARAMETERS(0, args.try_ssid, None, None, 1, 0)
        rc = wlanapi.WlanConnect(handle, ctypes.byref(secondary), ctypes.byref(params), None)
        print(f"Connect secondary to '{args.try_ssid}': {'request accepted' if rc == 0 else err(rc)}")

        for _ in range(15):
            time.sleep(1)
            prof = current_profile(handle, secondary)
            home = current_profile(handle, primary)
            print(f"  secondary: {prof}   primary (home): {home}")
            if prof == args.try_ssid:
                print("\nSUCCESS: the drone is on the secondary connection while home Wi-Fi stays up.")
                print("Keep this window open while flying (closing it ends the second connection).")
                input("Press Enter to disconnect the drone and exit...")
                return 0
        print("\nResult: the secondary connection did not join the drone. "
              "On this card it only follows the home network, so a second adapter is needed.")
        return 0
    finally:
        wlanapi.WlanCloseHandle(handle, None)


if __name__ == "__main__":
    sys.exit(main())

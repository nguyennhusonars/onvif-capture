#!/usr/bin/env python3
"""CLI utility to scan the local network for ONVIF IP cameras via WS-Discovery UDP multicast."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onvif_capture.discovery import ws_discovery_scan


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan local network for ONVIF cameras via WS-Discovery")
    parser.add_argument("--timeout", type=float, default=4.0, help="Discovery probe listen timeout in seconds")
    parser.add_argument("--profile-m-only", action="store_true", help="Only output cameras confirming ONVIF Profile M support")
    args = parser.parse_args()

    print(f"[*] Sending WS-Discovery probe to 239.255.255.250:3702 (timeout: {args.timeout}s)...", file=sys.stderr)
    cameras = ws_discovery_scan(timeout=args.timeout)

    if args.profile_m_only:
        cameras = [c for c in cameras if c.has_profile_m]

    output = [
        {
            "ip": cam.ip,
            "port": cam.port,
            "display_name": cam.display_name,
            "hardware": cam.hardware,
            "has_profile_m": cam.has_profile_m,
            "profiles": cam.profile_summary,
            "xaddrs": cam.xaddrs,
            "scopes": cam.scopes,
        }
        for cam in cameras
    ]

    print(json.dumps(output, indent=2))
    print(f"[*] Discovered {len(cameras)} ONVIF camera(s).", file=sys.stderr)


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""CLI utility to probe ONVIF Profile M capabilities and optionally enable MetadataConfiguration."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onvif_capture.client import ONVIFProfileMClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe ONVIF Profile M camera inventory")
    parser.add_argument("--host", default="192.168.1.100")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--rtsp-port", type=int, default=None, help="Forwarded RTSP port (e.g. 551 or 552)")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="")
    parser.add_argument("--enable-metadata", action="store_true", help="Enable Analytics=true & Events in MetadataConfiguration")
    args = parser.parse_args()

    client = ONVIFProfileMClient(args.host, args.port, args.user, args.password, rtsp_port=args.rtsp_port)
    inv = client.connect()
    if args.enable_metadata and (not inv["analytics_enabled"] or not inv["events_enabled"]):
        inv["metadata_config"] = client.set_metadata_analytics_enabled(True, True)
        inv["analytics_enabled"] = True
        inv["events_enabled"] = True

    summary = {
        "device_info": inv["device_info"],
        "is_profile_m": inv["is_profile_m"],
        "scopes": inv["scopes"],
        "analytics_enabled": inv["analytics_enabled"],
        "events_enabled": inv["events_enabled"],
        "profiles": inv["profiles"],
        "active_modules": [m["type"] for m in inv["active_modules"]],
        "rules": inv["rules"],
        "topic_count": len(inv["topics"]),
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()


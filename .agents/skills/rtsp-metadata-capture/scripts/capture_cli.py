#!/usr/bin/env python3
"""Headless CLI capture utility for RTSP vnd.onvif.metadata and ONVIF PullPoint events."""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onvif_capture.client import ONVIFProfileMClient
from onvif_capture.models import CapturedMetadataItem
from onvif_capture.workers import ONVIFPullPointWorker, RTSPMetadataStreamWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture ONVIF Profile M RTSP metadata and PullPoint events")
    parser.add_argument("--host", default="192.169.1.197")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--rtsp-uri", default="rtsp://192.169.1.197:554/stream0")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="Pavana@123")
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--include-heartbeats", action="store_true")
    args = parser.parse_args()

    try:
        client = ONVIFProfileMClient(args.host, args.port, args.user, args.password)
        client.connect()
        client.set_metadata_analytics_enabled(True, True)
    except Exception as exc:
        print(f"[WARN] Could not auto-enable MetadataConfiguration: {exc}", file=sys.stderr)

    def on_items(items: List[CapturedMetadataItem]) -> None:
        for item in items:
            if not args.include_heartbeats and item.property_operation == "Initialized":
                continue
            print(
                json.dumps(
                    {
                        "utc_time": item.utc_time,
                        "channel": item.channel,
                        "kind": item.kind,
                        "topic_or_source": item.topic_or_source,
                        "rule_or_object_id": item.rule_or_object_id,
                        "property_operation": item.property_operation,
                        "likelihood": item.likelihood,
                        "bbox": item.bbox,
                        "summary": item.summary,
                        "has_snapshot": item.image_bytes is not None,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    rtsp_worker = RTSPMetadataStreamWorker(
        rtsp_uri=args.rtsp_uri,
        username=args.user,
        password=args.password,
        on_items=on_items,
        on_status=lambda s: print(f"[RTSP] {s}", file=sys.stderr, flush=True),
    )
    pp_worker = ONVIFPullPointWorker(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        on_items=on_items,
        on_status=lambda s: print(f"[PullPoint] {s}", file=sys.stderr, flush=True),
    )

    rtsp_worker.start()
    pp_worker.start()
    time.sleep(args.duration)
    rtsp_worker.stop()
    pp_worker.stop()


if __name__ == "__main__":
    main()

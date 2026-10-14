---
name: rtsp-metadata-capture
description: >-
  Use this skill when the user asks to capture, debug, or record live RTSP vnd.onvif.metadata
  RTP XML frames or ONVIF PullPoint events from the command line or verify XML parsing.
---

# RTSP `vnd.onvif.metadata` & PullPoint Capture

Use this skill to capture real-time `<tt:MetadataStream>` XML frames from `rtsp://<ip>:554/stream0/metadata` and `<wsnt:NotificationMessage>` events from the ONVIF PullPoint service.

## Steps

1. **Run the Headless Capture Script:**
   Execute [`capture_cli.py`](./scripts/capture_cli.py) for a bounded duration (e.g., 10 seconds):
   ```bash
   python3 .agents/skills/rtsp-metadata-capture/scripts/capture_cli.py --duration 10 --include-heartbeats
   ```
2. **Verify Multi-Packet RTP Reassembly & Parsing:**
   * Check that `RTSPMetadataStreamWorker` reports `RTSP metadata active (rtsp://192.169.1.64:554/stream0/metadata)`.
   * Verify that `<tt:VideoAnalytics>` frames and `<tt:Event>` frames parse cleanly into `CapturedMetadataItem` instances.
3. **Reference Schemas:**
   Consult [rtsp_metadata_xml_schemas.md](../../knowledge/rtsp_metadata_xml_schemas.md) for the exact `<tt:VideoAnalytics>` and `<tt:Event>` XML structures and coordinate transformation math.


---
name: onvif-camera-diagnostics
description: >-
  Use this skill when the user asks to probe an ONVIF camera, verify Profile M compliance,
  inspect Media1/Media2 profiles, check or enable MetadataConfiguration (Analytics=true & Events),
  or list supported analytics modules and event TopicSet schemas.
---

# ONVIF Profile M Camera Diagnostics

Follow this procedure to inspect an IP camera's ONVIF Profile M capabilities and verify that native AI metadata streaming is enabled.

## Steps

1. **Auto-Discover Camera Endpoint (Optional):**
   If the camera's IP or port is unknown, run the discovery scanner first:
   ```bash
   python3 .agents/skills/ws-discovery/scripts/scan_cameras.py
   ```

2. **Run the Camera Probe Script:**
   Execute [`probe_camera.py`](./scripts/probe_camera.py) from the repository root:
   ```bash
   python3 .agents/skills/onvif-camera-diagnostics/scripts/probe_camera.py --host 192.168.1.100 --port 8000 --user admin --password "admin" --enable-metadata
   ```

3. **Verify Profile M Readiness:**
   Confirm in the JSON output that:
   * `"is_profile_m": true` (`onvif://www.onvif.org/Profile/M` present in `scopes`).
   * `"analytics_enabled": true` and `"events_enabled": true` in `MetadataConfiguration`.
   * Both `MainStream` (`rtsp://<ip>:554/stream0`) and `SubStream` (`rtsp://<ip>:554/stream1`) are listed.

4. **Reference Documentation:**
   * See [docs/onvif_profile_m_spec.md](../../../docs/onvif_profile_m_spec.md) for Profile M protocol rules.
   * See [reference_profile_m_camera_spec.md](../../knowledge/reference_profile_m_camera_spec.md) for standard camera profile parameters.

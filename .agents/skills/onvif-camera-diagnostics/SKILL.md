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

1. **Run the Camera Probe Script:**
   Execute [`probe_camera.py`](./scripts/probe_camera.py) from the repository root:
   ```bash
   python3 .agents/skills/onvif-camera-diagnostics/scripts/probe_camera.py --host 192.169.1.64 --port 8000 --user admin --password "Pavana@123" --enable-metadata
   ```
2. **Verify Profile M Readiness:**
   Confirm in the JSON output that:
   * `"is_profile_m": true` (`onvif://www.onvif.org/Profile/M` present in `scopes`).
   * `"analytics_enabled": true` and `"events_enabled": true` in `MetadataConfiguration`.
   * Both `MainStream` (`rtsp://<ip>:554/stream0`) and `SubStream` (`rtsp://<ip>:554/stream1`) are listed.
3. **Reference Knowledge:**
   See [pavana_v_security_profile_m_spec.md](../../knowledge/pavana_v_security_profile_m_spec.md) for the expected baseline inventory of the PAVANA V-Security camera.


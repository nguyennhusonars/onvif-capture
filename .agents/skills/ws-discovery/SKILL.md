---
name: ws-discovery
description: >-
  Use this skill when the user asks to scan the local network for ONVIF IP cameras,
  discover device service XAddrs, verify Profile M/T/S/G scopes, or test WS-Discovery probes.
---

# WS-Discovery Local Camera Scanner

Follow this procedure to broadcast a WS-Discovery probe across the local subnet and detect connected ONVIF cameras.

## Steps

1. **Run the Discovery Script:**
   Execute [`scan_cameras.py`](./scripts/scan_cameras.py) from the repository root:
   ```bash
   python3 .agents/skills/ws-discovery/scripts/scan_cameras.py --timeout 4.0
   ```

2. **Filter by Profile M:**
   To locate only AI-capable Profile M cameras:
   ```bash
   python3 .agents/skills/ws-discovery/scripts/scan_cameras.py --timeout 4.0 --profile-m-only
   ```

3. **Verify Discovered Attributes:**
   Confirm in the JSON output:
   * `"ip"` and `"port"` of the device service endpoint.
   * `"has_profile_m": true` indicating AI metadata support.
   * `"xaddrs"` list containing the target `/onvif/device_service` endpoint.

4. **Reference Protocol Spec:**
   See [docs/discovery.md](../../../docs/discovery.md) for full packet schemas and numerical sorting algorithms.


# Workspace Guidelines: ONVIF Profile M Native AI Analytics & Metadata Inspector

Welcome to the **ONVIF Profile M Native AI Analytics & Metadata Inspector** codebase. This workspace provides a verified, modular Python + PySide6 application for inspecting, configuring, and capturing real-time ONVIF Profile M AI object analytics (`<tt:VideoAnalytics>`) and rule events (`<tt:Event>` / `PullPoint`) from IP cameras—specifically verified against the **PAVANA V-Security** camera (`192.169.1.64:8000`, Firmware `PAM2310.V-Security.25K00.DT.309.216`).

---

## 1. Project Overview & Architecture

* **Target Camera Profile:** ONVIF Profile M (`onvif://www.onvif.org/Profile/M`), Profile T, Profile G, Profile Streaming.
* **Dual-Channel Native AI Capture:**
  1. **RTSP `vnd.onvif.metadata` RTP-over-TCP Stream (`rtsp://<ip>:554/stream0/metadata`):**
     * Reassembles multi-packet RTP payloads using the RTP Marker bit ($M = 1$).
     * Parses `<tt:MetadataStream>` containing `<tt:VideoAnalytics><tt:Frame>` (detected objects, bounding boxes, classes, likelihoods, and Profile M `Appearance` extensions: `HumanFace`, `HumanBody`, `VehicleInfo`, `LicensePlateInfo`, `GeoLocation`) and `<tt:Event><wsnt:NotificationMessage>` (rule triggers with embedded Base64 JPEG snapshots).
  2. **ONVIF PullPoint Event Subscription (`http://<ip>:8000/onvif/event_service`):**
     * Polls `PullMessages` and parses both `<tt:SimpleItem>` and `<tt:ElementItem>` payloads (`ObjectId`, `BoundingBox`, `LicensePlateInfo`, `Image`).
* **Modular Codebase (`onvif_capture/`):**
  * `main.py`: Application entry point (`python3 main.py`).
  * `onvif_capture/models.py`: Dataclasses (`DetectedObject`, `CapturedMetadataItem`).
  * `onvif_capture/parsers.py`: XML and coordinate normalization parsers (`normalize_bbox`, `parse_metadata_stream_xml`, `parse_notification_element`).
  * `onvif_capture/client.py`: `ONVIFProfileMClient` (Device, Media1, Media2 `ver20/media/wsdl` raw SOAP with WS-Security Digest, Analytics & RuleEngine `GetRules`/`ModifyRules`/`GetSupportedMetadata`).
  * `onvif_capture/workers.py`: Background streaming threads (`RTSPMetadataStreamWorker`, `ONVIFPullPointWorker`, `RTSPVideoPreviewWorker`).
  * `onvif_capture/gui/`: PySide6 UI (`canvas.py` for `VideoAnalyticsCanvas`, `main_window.py` for `ONVIFProfileMWindow`).

---

## 2. Core Engineering Principles for Agents

When modifying or extending this codebase, all agents MUST follow these verified engineering rules:

1. **Direct WS-Security Digest SOAP for Media2 & RuleEngine:**
   * `onvif-zeep 0.2.12` lacks `create_media2_service()` and omits `RuleEnginePort` (`GetRules`, `ModifyRules`, `GetSupportedMetadata`) on `analytics_service`. Always use `ONVIFProfileMClient.soap_call()` signed with `zeep.wsse.username.UsernameToken(..., use_digest=True)` against `/onvif/media2_service` and `/onvif/analytics_service`.
2. **MetadataConfiguration Activation (`Analytics=true` & `Events`):**
   * By default, the camera's `MetadataConfigurationToken_1` may have `Analytics=false` and `Events=null`. Ensure `set_metadata_analytics_enabled(True, True)` is applied so the camera actively emits AI XML frames on `stream0/metadata`.
3. **Dual Coordinate System Normalization:**
   * `<tt:VideoAnalytics><tt:Frame><tt:Object>` bounding boxes on PAVANA firmware are emitted in normalized top-left $[0, 1]$ coordinates (`left`, `top`, `right`, `bottom`).
   * `<tt:Event><tt:ElementItem Name="BoundingBox"><tt:Rectangle>` coordinates are emitted in signed ONVIF $[-1, 1]$ space ($x \in [-1, 1]$ left-to-right, $y \in [-1, 1]$ bottom-to-top). Always normalize via `normalize_bbox()` in `onvif_capture/parsers.py`:
     $$u = \frac{x + 1}{2}, \quad v = \frac{1 - y}{2}$$
4. **Full `<tt:ElementItem>` Parsing & Huge XML Tree Support:**
   * Never restrict event parsing to `<tt:SimpleItem>`. AI events carry `<tt:ElementItem Name="Image"><tt:base64Binary>` JPEG snapshots exceeding $400\,\text{KB}$ across $\sim 300$ RTP packets. Always parse with `etree.XMLParser(recover=True, huge_tree=True)`.
5. **Zero-Conflict Video Decoding:**
   * Do not import `cv2` alongside `PySide6` in the GUI process (avoids Qt platform plugin and NumPy 2.x ABI conflicts). Decode RTSP video via `ffmpeg` subprocess (`-pix_fmt rgb24`) in `RTSPVideoPreviewWorker` at a 4:3 aspect ratio (`640x480`) matching the $2592 \times 1944$ sensor field of view.

---

## 3. Directory Navigation

* `main.py` & `onvif_capture/`: Core Python package and PySide6 GUI.
* `.agents/knowledge/`: Verified camera specifications, ONVIF Profile M XML schemas, and rule/topic inventories.
* `.agents/rules/`: Coding and protocol rules for ONVIF SOAP, RTSP RTP metadata streaming, and PySide6 GUI.
* `.agents/skills/`: Executable runbooks and CLI scripts for camera probing, RTSP metadata capture, and rule tuning.
* `.agents/agents/`: Specialized subagent personas (`onvif-protocol-specialist`, `rtsp-media-engineer`, `pyside6-ui-specialist`).
* `.agents/hooks.json` & `.agents/hooks/`: Pre-tool safety guard and post-edit Python syntax linter.


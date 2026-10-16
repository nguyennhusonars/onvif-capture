# Workspace Guidelines: ONVIF Profile M Native AI Analytics & Metadata Inspector

Welcome to the **ONVIF Profile M Native AI Analytics & Metadata Inspector** codebase. This workspace provides a verified, modular Python + PySide6 application for inspecting, configuring, and capturing real-time ONVIF Profile M AI object analytics (`<tt:VideoAnalytics>`) and rule events (`<tt:Event>` / `PullPoint`) from any compliant ONVIF IP camera.

---

## 1. Project Overview & Architecture

* **Target Camera Profiles:** ONVIF Profile M (`onvif://www.onvif.org/Profile/M`), Profile T, Profile G, Profile Streaming.
* **Network Device Discovery:**
  * Native WS-Discovery over UDP multicast (`239.255.255.250:3702`).
  * Scopes parsing for Profile M, T, S, and G compliance.
  * Numerical IPv4/IPv6 and port sorting (`IPTableWidgetItem`, `NumericTableWidgetItem`).
* **Dual-Channel Native AI Capture:**
  1. **RTSP `vnd.onvif.metadata` RTP-over-TCP Stream (`rtsp://<ip>:554/stream0/metadata`):**
     * Reassembles multi-packet RTP payloads using the RTP Marker bit ($M = 1$).
     * Parses `<tt:MetadataStream>` containing `<tt:VideoAnalytics><tt:Frame>` (detected objects, bounding boxes, classes, likelihoods, and Profile M `Appearance` extensions: `HumanFace`, `HumanBody`, `VehicleInfo`, `LicensePlateInfo`, `GeoLocation`) and `<tt:Event><wsnt:NotificationMessage>` (rule triggers with embedded Base64 JPEG snapshots).
  2. **ONVIF PullPoint Event Subscription (`http://<ip>:8000/onvif/event_service`):**
     * Polls `PullMessages` and parses both `<tt:SimpleItem>` and `<tt:ElementItem>` payloads (`ObjectId`, `BoundingBox`, `LicensePlateInfo`, `Image`).
* **Modular Codebase (`onvif_capture/`):**
  * `main.py`: Application entry point (`python3 main.py`).
  * `onvif_capture/discovery.py`: Native WS-Discovery multicast client and camera scope parser.
  * `onvif_capture/models.py`: Dataclasses (`DetectedObject`, `CapturedMetadataItem` with `template_bytes`).
  * `onvif_capture/parsers.py`: XML and coordinate normalization parsers (`normalize_bbox`, `parse_metadata_stream_xml`, `parse_notification_element`).
  * `onvif_capture/client.py`: `ONVIFProfileMClient` (Device, Media1, Media2 `ver20/media/wsdl` raw SOAP with WS-Security Digest, Analytics & RuleEngine `GetRules`/`ModifyRules`/`GetSupportedMetadata`).
  * `onvif_capture/workers.py`: Background streaming threads (`RTSPMetadataStreamWorker`, `ONVIFPullPointWorker`, `RTSPVideoPreviewWorker`).
  * `onvif_capture/gui/`: Modernized PySide6 UI:
    * `main_window.py`: `ONVIFProfileMWindow` (disaggregated tabs, telemetry dashboard, collapsible header).
    * `canvas.py`: `VideoAnalyticsCanvas` (HUD controls, class filtering, freeze-frame mode, real-time FPS).
    * `models.py`: Virtualized `MetadataTableModel` and `MetadataFilterProxyModel` with 1-based vertical row numbering.
    * `gallery.py`: `EventSnapshotStrip`, `EventGalleryGrid`, `SnapshotCard`, and `SnapshotInspectorDialog`.
    * `scanner_dialog.py`: `DeviceScannerDialog` with natural IP sorting and Profile M detection.
* **Unit Test Suite (`tests/`):**
  * 37 verified unit and simulation tests across discovery, gallery, models, parsers, and worker threads (`pytest -v`).

---

## 2. Core Engineering Principles for Agents

When modifying or extending this codebase, all agents MUST follow these verified engineering rules:

1. **Direct WS-Security Digest SOAP for Media2 & RuleEngine:**
   * `onvif-zeep 0.2.12` lacks `create_media2_service()` and omits `RuleEnginePort` (`GetRules`, `ModifyRules`, `GetSupportedMetadata`) on `analytics_service`. Always use `ONVIFProfileMClient.soap_call()` signed with `zeep.wsse.username.UsernameToken(..., use_digest=True)` against `/onvif/media2_service` and `/onvif/analytics_service`.
2. **MetadataConfiguration Activation (`Analytics=true` & `Events`):**
   * By default, the camera's `MetadataConfigurationToken_1` may have `Analytics=false` and `Events=null`. Ensure `set_metadata_analytics_enabled(True, True)` is applied so the camera actively emits AI XML frames on `stream0/metadata`.
3. **Dual Coordinate System Normalization:**
   * `<tt:VideoAnalytics><tt:Frame><tt:Object>` bounding boxes are emitted in normalized top-left $[0, 1]$ coordinates (`left`, `top`, `right`, `bottom`).
   * `<tt:Event><tt:ElementItem Name="BoundingBox"><tt:Rectangle>` coordinates are emitted in signed ONVIF $[-1, 1]$ space ($x \in [-1, 1]$ left-to-right, $y \in [-1, 1]$ bottom-to-top). Always normalize via `normalize_bbox()` in `onvif_capture/parsers.py`:
     $$u = \frac{x + 1}{2}, \quad v = \frac{1 - y}{2}$$
4. **Full `<tt:ElementItem>` Parsing & Huge XML Tree Support:**
   * Never restrict event parsing to `<tt:SimpleItem>`. AI events carry `<tt:ElementItem Name="Image"><tt:base64Binary>` JPEG snapshots exceeding $400\,\text{KB}$ across $\sim 300$ RTP packets. Always parse with `etree.XMLParser(recover=True, huge_tree=True)`.
5. **Zero-Conflict Video Decoding & Rate Capping:**
   * Do not import `cv2` alongside `PySide6` in the GUI process (avoids Qt platform plugin and NumPy 2.x ABI conflicts). Decode RTSP video via `ffmpeg` subprocess (`-pix_fmt rgb24`) in `RTSPVideoPreviewWorker` at a 4:3 aspect ratio (`640x480`) matching the $2592 \times 1944$ sensor field of view. Always cap preview decoding to 10 FPS (`-r 10`) with `-allowed_media_types video` to prevent RTSP competition and PySide6 event loop starvation.
6. **Strict Separation of Snapshot JPEGs vs Biometric Template Embeddings:**
   * In Face Recognition (`tns1:RuleEngine/FaceRecognition/Face`), `<tt:ElementItem Name="Image">` carries the JPEG snapshot, while `<tt:ElementItem Name="Template">` carries raw binary feature vector embeddings. Both are `<tt:base64Binary>`. Parsers MUST verify magic bytes (`\xff\xd8` for JPEG, `\x89PNG` for PNG) and element name, routing templates to `template_bytes` so embeddings NEVER overwrite snapshot `image_bytes`.
7. **Disaggregated Ingestion Buffer Isolation:**
   * Continuous 25 FPS spatial tracking frames (`kind="object_frame"`, ~1,800/min) and discrete security alarms (`kind="event"`, PullPoint & RTSP events) must NEVER share the same FIFO buffer. Security events must have unlimited retention (`max_items=0`) while spatial frames maintain a rolling circular buffer (e.g. 2,000 frames) so spatial frames never purge historical alarm events.
8. **Persistent HTTP Keep-Alive for ONVIF PullPoint:**
   * `ONVIFPullPointWorker` must use a persistent `requests.Session` with HTTP Keep-Alive and a 3-second long-poll timeout (`PT3S`) to maintain connection latency <3ms and avoid dropping event notifications during TCP handshake renegotiation. Always catch `requests.exceptions.Timeout` to preserve subscriptions on normal long-poll timeouts.
9. **Multi-Target Profile M Event Unbundling & List Flattening:**
   * In simultaneous multi-target alarms (e.g. multi-person Intrusion Detection `ID_rule0` sharing the same video frame timestamp), RTSP metadata streams bundle multiple detections under a single `<wsnt:NotificationMessage>` using multiple `<tt:Message>`, multiple `<tt:Data>`, or multiple `<tt:ElementItem Name="ObjectId">` groups. `parse_notification_element()` MUST return `List[CapturedMetadataItem]` and iterate through all child messages and data blocks. Never truncate to `msg_el_list[0]` or `sec_nodes[0]`, ensuring no concurrent alarm detections are dropped.
10. **Ampersand Mnemonic Avoidance in UI Text:**
    * In PySide6 / Qt, `QPushButton`, `QTabBar`, and `QGroupBox` interpret unescaped `&` as a keyboard accelerator mnemonic prefix, rendering undesired underlines or omitting characters (e.g., `Rules & Modules` renders as `Rules _Modules`).
    * Always write out natural English conjunctions (`and`) or concise labels (e.g., `Rules and Modules`, `Select and Connect`, `Live Preview and Analytics`) rather than using raw `&` or double `&&`.
11. **Natural Numerical Sorting in Qt Tables:**
    * IP address columns must use `IPTableWidgetItem` subclassing `QTableWidgetItem` with `ipaddress.ip_address()` comparisons in `__lt__` to ensure `192.169.1.9` precedes `192.169.1.140`.
    * Port columns must use `NumericTableWidgetItem` comparing integer values.

---

## 3. Directory Navigation

* `main.py` & `onvif_capture/`: Core Python package and PySide6 GUI.
* `docs/`: Technical guides on architecture, Profile M protocol specs, and WS-Discovery.
* `tests/`: 37 automated unit and integration tests.
* `.agents/knowledge/`: Verified camera specifications, ONVIF Profile M XML schemas, and rule/topic inventories.
* `.agents/rules/`: Coding and protocol rules for ONVIF SOAP, RTSP RTP metadata streaming, and PySide6 GUI.
* `.agents/skills/`: Executable runbooks and CLI scripts for camera probing, RTSP metadata capture, rule tuning, and WS-Discovery scanning.
* `.agents/agents/`: Specialized subagent personas (`onvif-protocol-specialist`, `rtsp-media-engineer`, `pyside6-ui-specialist`).
* `.agents/hooks.json` & `.agents/hooks/`: Pre-tool safety guard and post-edit Python syntax linter.

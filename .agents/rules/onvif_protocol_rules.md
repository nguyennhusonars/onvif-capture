# ONVIF Profile M Protocol & SOAP Rules

1. **WS-Security UsernameToken Digest Authentication:**
   * All SOAP requests to `/onvif/device_service`, `/onvif/media_service`, `/onvif/media2_service`, `/onvif/analytics_service`, and `/onvif/event_service` MUST be authenticated with WS-Security `PasswordDigest` (`UsernameToken(username, password, use_digest=True)`).
2. **Bypassing `onvif-zeep` Limitations for Media2 & RuleEngine:**
   * `onvif_zeep==0.2.12` does not implement `create_media2_service()` and only binds `AnalyticsEnginePort` on `analytics.wsdl` (omitting `RuleEnginePort` operations `GetRules`, `ModifyRules`, `GetSupportedRules`, `GetRuleOptions`, and `GetSupportedMetadata`).
   * Use `ONVIFProfileMClient.soap_call()` with namespaces `tr2="http://www.onvif.org/ver20/media/wsdl"`, `tan="http://www.onvif.org/ver20/analytics/wsdl"`, and `tt="http://www.onvif.org/ver10/schema"`.
3. **Complete Event Payload Extraction (`SimpleItem` + `ElementItem`):**
   * Every `<tt:Message>` parser MUST iterate over both `<tt:SimpleItem Name="..." Value="..."/>` and `<tt:ElementItem Name="...">`.
   * Handle nested `<tt:ObjectId>`, `<tt:Rectangle>` / `<tt:BoundingBox>`, `<tt:LicensePlateInfo>`, `<tt:VehicleInfo>`, `<tt:HumanFace>`, `<tt:HumanBody>`, and `<tt:base64Binary>` JPEG snapshots inside `<tt:ElementItem>`.
4. **Coordinate Space Normalization:**
   * Always pass bounding boxes through `normalize_bbox()` in `onvif_capture/parsers.py` to convert signed ONVIF $[-1, 1]$ coordinates (`left < 0` or `top > bottom`) into top-left $[0.0, 1.0]$ screen coordinates before rendering or exporting.
5. **Differentiating Snapshots from Biometric Template Embeddings:**
   * In AI face recognition (`tns1:RuleEngine/FaceRecognition/Face`), both face snapshots and face feature vectors are emitted as `<tt:base64Binary>` nodes under `<tt:ElementItem>`.
   * Never treat all base64 elements as images. Verify magic bytes (`\xff\xd8` for JPEG, `\x89PNG` for PNG) and element names (`Image` vs `Template`/`Feature`/`Embedding`). Route embeddings to `template_bytes` so they never overwrite `image_bytes`.
6. **Multi-Target Notification Flattening & Simultaneous Event Preservation:**
   * Multiple detections sharing the exact same video frame millisecond (e.g. concurrent intrusion targets) can be grouped inside a single `<wsnt:NotificationMessage>` using multiple `<tt:Message>`, multiple `<tt:Data>`, or multiple `<tt:ElementItem Name="ObjectId">` groups.
   * Parsers MUST return `List[CapturedMetadataItem]` and traverse all child message and data branches without truncating at index 0 or dropping simultaneous detections.
7. **WS-Discovery Multicast Probing & Profile Scope Extraction:**
   * Device discovery MUST use UDP multicast to `239.255.255.250:3702` transmitting a standard SOAP 1.2 probe targeting types `dn:NetworkVideoTransmitter` and `tds:Device`.
   * Parsers must parse `d:ProbeMatches` extracting `d:XAddrs` and inspecting `d:Scopes` for Profile M (`onvif://www.onvif.org/Profile/M`), Profile T, and Profile G indicators.

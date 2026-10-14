# PAVANA V-Security Camera — Verified ONVIF Profile M Specification

## 1. Device Identity & Firmware
* **Manufacturer:** `PAVANA`
* **Model:** `V-Security`
* **Firmware Version:** `PAM2310.V-Security.25K00.DT.309.216`
* **Serial Number:** `ACVN248240000043`
* **Hardware ID:** `25`
* **Default Endpoint:** `192.169.1.64` (ONVIF HTTP Port `8000`, RTSP Port `554`)

## 2. Verified ONVIF Scopes (`tds:GetScopes`)
* `onvif://www.onvif.org/Profile/M` (Native AI Analytics & Metadata Profile)
* `onvif://www.onvif.org/Profile/T`
* `onvif://www.onvif.org/Profile/G`
* `onvif://www.onvif.org/Profile/Streaming`
* `onvif://www.onvif.org/type/video_encoder`
* `onvif://www.onvif.org/type/ptz`
* `onvif://www.onvif.org/hardware/PAVANA`
* `onvif://www.onvif.org/name/V-Security`

## 3. Service Endpoints (`tds:GetServices`)
| Namespace | XAddr Endpoint | Key Capabilities |
| :--- | :--- | :--- |
| `http://www.onvif.org/ver10/device/wsdl` | `http://192.169.1.64:8000/onvif/device_service` | UsernameToken, HttpDigest, TLS 1.0–1.2 |
| `http://www.onvif.org/ver10/media/wsdl` | `http://192.169.1.64:8000/onvif/media_service` | RTP_TCP, RTP_RTSP_TCP, MaxProfiles=10 |
| `http://www.onvif.org/ver20/media/wsdl` | `http://192.169.1.64:8000/onvif/media2_service` | Media2 `GetProfiles`, `GetStreamUri`, `Metadata` & `Analytics` configs |
| `http://www.onvif.org/ver20/analytics/wsdl` | `http://192.169.1.64:8000/onvif/analytics_service` | `RuleSupport=true`, `AnalyticsModuleSupport=true`, `SupportedMetadata=true`, `RuleOptionsSupported=true` |
| `http://www.onvif.org/ver10/events/wsdl` | `http://192.169.1.64:8000/onvif/event_service` | PullPoint (`http://192.169.1.64:8000/event_service/<id>`), ConcreteSet topics |
| `http://www.onvif.org/ver20/ptz/wsdl` | `http://192.169.1.64:8000/onvif/ptz_service` | PTZ control & presets |
| `http://www.onvif.org/ver20/imaging/wsdl` | `http://192.169.1.64:8000/onvif/image_service` | Image quality & radiometry |

## 4. Media Profiles & RTSP Streams
1. **`MainStream` (`ProfileToken_1`):**
   * Video Source: `VideoSourceConfigurationToken_1` ($2592 \times 1944$, 4:3 sensor)
   * Video Encoder: `H264` Main Profile, $2592 \times 1944$ @ $23.0\,\text{fps}$, $4000\,\text{kbps}$
   * RTSP URI: `rtsp://192.169.1.64:554/stream0`
     * Video Track: `rtsp://192.169.1.64:554/stream0/realvideo` (`RTP/AVP 96 H264/90000`)
     * Metadata Track: `rtsp://192.169.1.64:554/stream0/metadata` (`RTP/AVP 98 vnd.onvif.metadata/90000`)
2. **`SubStream` (`ProfileToken_2`):**
   * Video Encoder: `H264`, $1280 \times 720$
   * RTSP URI: `rtsp://192.169.1.64:554/stream1`

## 5. MetadataConfiguration (`MetadataConfigurationToken_1`)
* Shared across `ProfileToken_1` and `ProfileToken_2` (`UseCount=2`).
* Must have `Analytics = True` and `Events = {"Filter": None, "SubscriptionPolicy": None}` persisted via `SetMetadataConfiguration` for the RTSP metadata track (`stream0/metadata`) to stream `<tt:VideoAnalytics>` and `<tt:Event>` XML frames.


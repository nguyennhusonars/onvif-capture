# ONVIF Profile M Reference Camera Specification

## 1. Device Profile & Standards Compliance
* **Standard Profiles:** ONVIF Profile M (`onvif://www.onvif.org/Profile/M`), Profile T, Profile G, Profile Streaming
* **Default Endpoints:** Port `8000` (ONVIF HTTP SOAP 1.2), Port `554` (RTSP TCP)

## 2. Standard ONVIF Scopes (`tds:GetScopes`)
* `onvif://www.onvif.org/Profile/M` (Native AI Analytics & Metadata Profile)
* `onvif://www.onvif.org/Profile/T`
* `onvif://www.onvif.org/Profile/G`
* `onvif://www.onvif.org/Profile/Streaming`
* `onvif://www.onvif.org/type/video_encoder`
* `onvif://www.onvif.org/type/ptz`
* `onvif://www.onvif.org/hardware/NetworkCamera`
* `onvif://www.onvif.org/name/SmartCamera`

## 3. Service Endpoints (`tds:GetServices`)
| Namespace | XAddr Endpoint | Key Capabilities |
| :--- | :--- | :--- |
| `http://www.onvif.org/ver10/device/wsdl` | `http://<ip>:8000/onvif/device_service` | UsernameToken, HttpDigest, TLS 1.0–1.2 |
| `http://www.onvif.org/ver10/media/wsdl` | `http://<ip>:8000/onvif/media_service` | RTP_TCP, RTP_RTSP_TCP, MaxProfiles=10 |
| `http://www.onvif.org/ver20/media/wsdl` | `http://<ip>:8000/onvif/media2_service` | Media2 `GetProfiles`, `GetStreamUri`, `Metadata` & `Analytics` configs |
| `http://www.onvif.org/ver20/analytics/wsdl` | `http://<ip>:8000/onvif/analytics_service` | `RuleSupport=true`, `AnalyticsModuleSupport=true`, `SupportedMetadata=true`, `RuleOptionsSupported=true` |
| `http://www.onvif.org/ver10/events/wsdl` | `http://<ip>:8000/onvif/event_service` | PullPoint (`http://<ip>:8000/event_service/<id>`), ConcreteSet topics |
| `http://www.onvif.org/ver20/ptz/wsdl` | `http://<ip>:8000/onvif/ptz_service` | PTZ control & presets |
| `http://www.onvif.org/ver20/imaging/wsdl` | `http://<ip>:8000/onvif/image_service` | Image quality & radiometry |

## 4. Media Profiles & RTSP Streams
1. **`MainStream` (`ProfileToken_1`):**
   * Video Source: `VideoSourceConfigurationToken_1` (Full sensor 4:3)
   * Video Encoder: `H264` / `H265` Main Profile
   * RTSP URI: `rtsp://<ip>:554/stream0`
     * Video Track: `rtsp://<ip>:554/stream0/realvideo` (`RTP/AVP 96 H264/90000`)
     * Metadata Track: `rtsp://<ip>:554/stream0/metadata` (`RTP/AVP 98 vnd.onvif.metadata/90000`)
2. **`SubStream` (`ProfileToken_2`):**
   * Video Encoder: `H264`, $1280 \times 720$
   * RTSP URI: `rtsp://<ip>:554/stream1`

## 5. MetadataConfiguration (`MetadataConfigurationToken_1`)
* Shared across profiles (`UseCount >= 1`).
* Must have `Analytics = True` and `Events = {"Filter": None, "SubscriptionPolicy": None}` persisted via `SetMetadataConfiguration` for the RTSP metadata track (`stream0/metadata`) to stream `<tt:VideoAnalytics>` and `<tt:Event>` XML frames.


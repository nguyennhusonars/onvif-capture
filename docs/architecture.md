# Architecture and System Design

## 1. High-Level System Architecture

The **ONVIF Profile M Native AI Analytics & Metadata Inspector** is designed for high-throughput, low-latency processing of simultaneous video, spatial tracking frames, and security alarm events emitted by ONVIF Profile M and Profile T cameras.

```
                              +-------------------------+
                              |   Physical IP Camera    |
                              +-------------------------+
                                 |         |         |
           UDP 3702 (Multicast)  |         |         |  HTTP 8000 (SOAP 1.2)
         +-----------------------+         |         +-------------------------+
         |                                 |                                   |
         v                                 | TCP 554                           v
+------------------+                       v                         +--------------------+
|   WS-Discovery   |             +-------------------+               |   ONVIF SOAP &     |
|   Scanner        |             |   RTSP Server     |               |   PullPoint Engine |
+------------------+             +-------------------+               +--------------------+
         |                                 |                                   |
         | Camera Metadata                 |                                   |
         v                                 |                                   v
+------------------+      +----------------+---------------+         +--------------------+
|  DeviceScanner   |      |                                |         |  ONVIFPullPoint    |
|  Dialog          |      v                                v         |  Worker Thread     |
+------------------+ +-----------------------+ +-------------------+ +--------------------+
                     | RTSPVideoPreview      | | RTSPMetadataStream|           |
                     | Worker (ffmpeg pipe)  | | Worker (RTP M=1)  |           |
                     +-----------------------+ +-------------------+           |
                                 |                       |                     |
                      QImage(RGB)|                       v                     v
                                 |             +----------------------------------+
                                 |             | parse_metadata_stream_xml()      |
                                 |             | (Recover=True, HugeTree=True)    |
                                 |             +----------------------------------+
                                 |                               |
                                 |           +-------------------+-------------------+
                                 |           | (kind="object_frame")                 | (kind="event")
                                 v           v                                       v
                     +-------------------------+                           +-------------------+
                     |  VideoAnalyticsCanvas   |                           | EventGalleryGrid  |
                     |  HUD Bounding Boxes     |                           | EventSnapshotStrip|
                     +-------------------------+                           +-------------------+
                                 |                                                   |
                                 v                                                   v
                     +-------------------------+                           +-------------------+
                     | spatial_model (FIFO)    |                           | events_model      |
                     | (Max 2,000 items)       |                           | (Unlimited Ret.)  |
                     +-------------------------+                           +-------------------+
```

---

## 2. Ingestion Channels & Threading Model

The application isolates background I/O operations from the PySide6 UI thread using dedicated `QThread` workers communicating strictly via Qt `Signal`/`Slot` mechanics.

### Channel 1: RTSP `vnd.onvif.metadata` RTP-over-TCP Worker (`RTSPMetadataStreamWorker`)
* **Transport:** TCP interleaved framing (`$` `0x24` followed by 1-byte channel, 2-byte big-endian packet length).
* **Authentication:** RFC 2617 HTTP Digest authentication on RTSP (using the `realm` and `nonce` provided in the camera's 401 challenge).
* **RTP Payload Reassembly:**
  * RTP packets are accumulated across frames until the RTP Marker bit ($M=1$, `(pkt[1] >> 7) & 1`) is detected.
  * Payloads carrying embedded Base64 JPEG snapshots can exceed $400\,\text{KB}$ spanning over 300 individual RTP packets.
* **Keepalive:** Sends periodic `GET_PARAMETER` keepalive requests every 20 seconds to prevent camera stream teardown (`Session timeout=30`).

### Channel 2: ONVIF PullPoint Event Worker (`ONVIFPullPointWorker`)
* **Transport:** HTTP 1.1 with persistent `requests.Session` Keep-Alive to maintain $<3\,\text{ms}$ socket latency.
* **Subscription:** Creates a PullPoint subscription via `/onvif/event_service` and repeatedly polls `PullMessages` with a 3-second long-poll timeout (`PT3S`).
* **Resilience:** Catches read timeouts without tearing down subscriptions. Re-subscribes automatically on server connection reset.

### Channel 3: Low-Latency Video Preview Worker (`RTSPVideoPreviewWorker`)
* **Subprocess Execution:** Uses `/usr/bin/ffmpeg` piped directly into `stdout` (`-pix_fmt rgb24 -f rawvideo pipe:1`).
* **Zero ABI Conflicts:** Avoids importing `cv2` inside the GUI process to prevent platform plugin crashes and NumPy 2.x ABI incompatibilities.
* **Rate Capping:** Capped to 10 FPS (`-r 10`) at a $4:3$ aspect ratio ($640 \times 480$) matching the full camera sensor ($2592 \times 1944$) to prevent RTSP socket starvation.

---

## 3. Disaggregated Memory & Model Isolation

To prevent UI freezing when capturing at 25–30 FPS, incoming metadata items are strictly divided into two independent models:

| Dimension | `spatial_model` | `events_model` |
|---|---|---|
| **Content Type** | Continuous object tracking (`kind="object_frame"`) | Security alarms, rule triggers (`kind="event"`) |
| **Ingestion Rate** | ~25–30 FPS (~1,500–1,800 items/minute) | Sporadic (1–20 events/minute) |
| **Buffer Capacity** | Rolling FIFO circular buffer (capped at 2,000 items) | Unlimited retention (`max_items=0`) |
| **Pruning Strategy** | Drops oldest items from bottom when exceeding capacity | Never prunes historical alarms |
| **Sorting** | Newest item at top (Index 0) | Newest item at top (Index 0) |
| **Detail Splitter** | Dedicated `spatial_json_view` & `spatial_xml_view` | Dedicated `parsed_json_view` & `raw_xml_view` |

### Insertion Order & Pruning
When items arrive:
1. `beginInsertRows(QModelIndex(), 0, len(new_items) - 1)` is invoked.
2. Items are reversed so the newest event sits at row 0.
3. If buffer size exceeds the limit, `beginRemoveRows` prunes the oldest items from the bottom (`row_count - to_remove` to `row_count - 1`).

---

## 4. Coordinate Transformation & Normalization

The application unifies two distinct coordinate systems used by ONVIF cameras into a standardized screen coordinate space:

* **Screen Space:** Top-left origin $[0.0, 1.0]$: $u \in [0.0, 1.0]$ left-to-right, $v \in [0.0, 1.0]$ top-to-bottom.
* **`<tt:VideoAnalytics>` Coordinate Space:** Emitted directly as unsigned normalized $[0.0, 1.0]$.
* **`<tt:Event>` Rectangle Coordinate Space:** Emitted as signed ONVIF space $[-1.0, 1.0]$ where $(-1, 1)$ is top-left and $(1, -1)$ is bottom-right.

**Transformation Formula:**
$$\text{left}_{u} = \frac{x_{\text{min}} + 1}{2}, \quad \text{top}_{v} = \frac{1 - y_{\text{max}}}{2}$$
$$\text{right}_{u} = \frac{x_{\text{max}} + 1}{2}, \quad \text{bottom}_{v} = \frac{1 - y_{\text{min}}}{2}$$

All bounding boxes are clamped to $[0.0, 1.0]$ to prevent drawing out of bounds on canvas viewports.


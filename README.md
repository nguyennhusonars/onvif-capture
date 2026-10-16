# ONVIF Profile M Native AI Analytics & Metadata Inspector

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6%20(Qt6)-green.svg)](https://pypi.org/project/PySide6/)
[![ONVIF Profile M](https://img.shields.io/badge/ONVIF-Profile%20M%20%7C%20T%20%7C%20G-orange.svg)](https://www.onvif.org/profiles/profile-m/)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)
[![Tests: 37 Passed](https://img.shields.io/badge/Tests-37%20Passed-brightgreen.svg)](tests/)

A high-performance, modular desktop application and protocol suite for inspecting, capturing, visualizing, and configuring real-time **ONVIF Profile M** native AI analytics (`<tt:VideoAnalytics>`) and security alarm events (`<tt:Event>` / `PullPoint`) from IP cameras.

Engineered and verified for compliant ONVIF Profile M, Profile T, Profile S, and Profile G network video transmitters and smart IP cameras.

---

## Key Capabilities

* **Local WS-Discovery Device Scanner:**
  * Auto-discovers local ONVIF cameras via UDP multicast probe (`239.255.255.250:3702`).
  * Scans scopes for Profile M, T, S, and G compliance, highlighting AI-capable cameras.
  * Natural numerical sorting for IP addresses (`192.169.1.9` < `192.169.1.140`) and integer ports.
  * Real-time search filtering across IP, port, model, and endpoint URL.
* **Dual-Channel Native AI Ingestion:**
  * **RTSP `vnd.onvif.metadata` RTP-over-TCP:** Reassembles fragmented multi-packet XML payloads using the RTP Marker bit ($M=1$) for payloads exceeding 400 KB.
  * **ONVIF PullPoint Event Subscription:** Persistent HTTP Keep-Alive long-polling (`PT3S`) parsing both `<tt:SimpleItem>` and `<tt:ElementItem>` structures.
* **Disaggregated Ingestion Buffer Isolation:**
  * Separates high-frequency 25 FPS spatial object tracking (~1,800 frames/min) from discrete security alarm events.
  * Security alarms (`events_model`) enjoy infinite retention (`max_items=0`), while tracking frames (`spatial_model`) operate on a high-throughput rolling circular buffer (2,000 items) to guarantee zero UI latency.
* **Capture Wall & Live Snapshot Strip:**
  * Dedicated visual gallery displaying alarm cards with Base64-embedded JPEG snapshots, confidence scores, and rule metadata.
  * **Biometric Template Isolation:** Enforces magic-byte verification (`\xff\xd8` for JPEG) to separate raw image snapshots from binary facial feature vector embeddings (`template_bytes`), preventing image corruption.
  * Gracefully displays text-only alarm cards when events do not include embedded images.
  * Multi-target unbundling flattens simultaneous alarm triggers sharing a single timestamp.
* **HUD Video Analytics Canvas:**
  * Low-latency video preview decoded via isolated `ffmpeg` subprocess at native 4:3 sensor aspect ratio ($640 \times 480$), avoiding OpenCV/Qt ABI conflicts.
  * Synchronized bounding box overlays with normalized $[0, 1]$ screen coordinates converted from signed ONVIF $[-1, 1]$ space.
  * Class-based filtering (Person, Vehicle, Face, Plate), freeze-frame inspection, and live FPS telemetry.
* **Interactive Rule Editor (`tan:ModifyRules`):**
  * Live camera rule calibration (Face Detection, Face Recognition, Intrusion Detection, Line Crossing, Crowd Detection, etc.).
  * Parameter editing directly against camera configuration tokens with instant reload and verification.

---

## Architecture Overview

```
                                      +-----------------------------------------+
                                      |            IP Camera Network            |
                                      +-----------------------------------------+
                                        /                  |                  \
                   WS-Discovery (UDP 3702)     RTSP Stream (TCP 554)     ONVIF SOAP (HTTP 8000)
                                      /                    |                    \
                                     v                     v                     v
                        +-----------------+   +------------------------+   +-------------------+
                        |   WS-Discovery  |   | RTSPMetadataStream     |   | ONVIFPullPoint    |
                        |   Scanner       |   | Worker (RTP Marker M=1)|   | Worker (KeepAlive)|
                        +-----------------+   +------------------------+   +-------------------+
                                 |                         |                         |
                                 v                         \_________________________/
                        +-----------------+                             |
                        |  Device Scanner |                             v
                        |  Dialog (Qt6)   |               +----------------------------+
                        +-----------------+               |    parse_metadata_stream   |
                                                          |  (HugeTree / XML recovery) |
                                                          +----------------------------+
                                                           /                          \
                                       kind="object_frame" /                            \ kind="event"
                                                          v                              v
                                            +---------------------------+  +---------------------------+
                                            |   spatial_model (FIFO)    |  |    events_model (FIFO)    |
                                            |   Rolling 2,000 frames    |  |    Unlimited Retention    |
                                            +---------------------------+  +---------------------------+
                                                          |                              |
                                                          v                              v
                                            +---------------------------+  +---------------------------+
                                            |  Spatial Tracking Tab     |  |  AI Events / Capture Wall |
                                            |  Video HUD Overlay (4:3)  |  |  Snapshot Strip & Gallery |
                                            +---------------------------+  +---------------------------+
```

---

## Installation

### Option 1: One-Click Ubuntu / Debian Package (.deb) — Recommended

The pre-built `.deb` package bundles a standalone executable with all required ONVIF, WSDL, and PySide6 runtimes, complete with system app launcher integration and high-resolution icons.

```bash
# Install the Debian package (auto-resolves dependencies like ffmpeg)
sudo apt update
sudo apt install ./dist/onvif-capture_1.0.0_amd64.deb
```
Or with `dpkg`:
```bash
sudo dpkg -i dist/onvif-capture_1.0.0_amd64.deb
sudo apt-get install -f # if any system packages (ffmpeg, libgl1) are missing
```

Once installed, **ONVIF Inspector** appears directly in your Ubuntu Application Drawer, GNOME dash/dock, and system launcher with high-resolution app icons, and can also be launched from any terminal with:
```bash
onvif-capture
```

#### Building the .deb Package Locally
To compile the standalone binary and package the `.deb` yourself:
```bash
./package_deb.sh --rebuild
```

---

### Option 2: Python Virtual Environment

#### Prerequisites
* Python 3.10 or later
* `ffmpeg` installed and available in `PATH` (used for low-latency RTSP preview decoding)

#### Setup
```bash
# Clone the repository
git clone https://github.com/your-org/onvif-capture.git
cd onvif-capture

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

If installing dependencies individually:
```bash
pip install PySide6 onvif-zeep requests lxml pytest pytest-qt
```

---

## Quickstart

### Launching the Graphical Application
```bash
python3 main.py
```

1. Click **Scan Network** in the top-right toolbar to open the **WS-Discovery Scanner**.
2. Select any discovered ONVIF camera from the list and click **Select and Connect**.
3. Alternatively, enter the camera credentials manually in the connection bar:
   * **Host:** Camera IP (e.g., `192.169.1.64`)
   * **Port:** ONVIF HTTP port (e.g., `8000`)
   * **User / Password:** Camera ONVIF credentials
   * **RTSP URI:** `rtsp://<ip>:554/stream0`
4. Click **Connect** to initialize ONVIF services, activate metadata streaming, and launch the preview.

### Navigating the UI
* **Live Preview:** Displays the 4:3 video canvas with real-time bounding boxes, classification tags, likelihood scores, and live FPS.
* **AI Events:** Real-time log of security alarms, intrusion alerts, and face recognitions.
* **Capture Wall:** Visual gallery of captured alarm snapshots with zoom and metadata inspection dialog.
* **Spatial Tracking:** High-rate 25 FPS tracking log with separate JSON and XML inspectors.
* **Rules and Modules:** Live parameter editor for active rules and camera capabilities.
* **Device Inventory:** Complete dump of camera device info, Media2 profiles, and XML schemas.

---

## Command-Line Tools & Diagnostics

The project provides headless CLI tools in `.agents/skills/` for scripting, testing, and remote diagnostics:

### 1. Network Camera Scanner
```bash
python3 .agents/skills/ws-discovery/scripts/scan_cameras.py --timeout 4.0
```

### 2. Camera Diagnostics & Profile M Verification
```bash
python3 .agents/skills/onvif-camera-diagnostics/scripts/probe_camera.py \
  --host 192.169.1.64 --port 8000 --user admin --password "Secret@123" --enable-metadata
```

### 3. Headless RTSP Metadata & Event Capture
```bash
python3 .agents/skills/rtsp-metadata-capture/scripts/capture_cli.py \
  --host 192.169.1.64 --port 8000 --duration 10.0 --include-heartbeats
```

---

## Running Tests

The test suite covers XML parsers, coordinate normalization, models, gallery widgets, discovery, and simulated worker threads:

```bash
pytest -v
```

All 37 test cases should pass:
```text
======================= 37 passed in 0.40s =======================
```

---

## Project Structure

```
onvif-capture/
├── main.py                          # Application entry point
├── requirements.txt                 # Project dependencies
├── docs/                            # In-depth architectural & protocol documentation
│   ├── architecture.md              # System design, threading, and data isolation
│   ├── onvif_profile_m_spec.md      # XML schemas, coordinate math, and SOAP rules
│   └── discovery.md                 # WS-Discovery protocol implementation
├── onvif_capture/                   # Core Python package
│   ├── __init__.py
│   ├── client.py                    # ONVIFProfileMClient (SOAP, Media2, RuleEngine)
│   ├── discovery.py                 # WS-Discovery multicast probe & parsing
│   ├── models.py                    # Dataclasses (DetectedObject, CapturedMetadataItem)
│   ├── parsers.py                   # XML parsers (Profile M Frame, Notification, BBox)
│   ├── workers.py                   # Thread workers (RTSP metadata, PullPoint, Video)
│   └── gui/                         # PySide6 desktop interface
│       ├── __init__.py
│       ├── canvas.py                # VideoAnalyticsCanvas (HUD overlays, FPS, BBox)
│       ├── gallery.py               # EventGalleryGrid, EventSnapshotStrip, Cards
│       ├── main_window.py           # ONVIFProfileMWindow (Main window, tabs, telemetry)
│       ├── models.py                # Virtualized MetadataTableModel & FilterProxy
│       └── scanner_dialog.py        # DeviceScannerDialog (WS-Discovery camera table)
├── tests/                           # Unit and integration test suite
│   ├── test_discovery.py            # WS-Discovery and scanner UI tests
│   ├── test_gallery.py              # Snapshot card, strip, and gallery tests
│   ├── test_models.py               # Ingestion order and pruning tests
│   ├── test_parsers.py              # Profile M XML parsing and coordinate tests
│   └── test_workers_simulation.py   # Multi-packet RTP and PullPoint simulation
└── .agents/                         # Autonomous engineering agent knowledge & skills
    ├── AGENTS.md                    # Core engineering rules & architecture guide
    ├── knowledge/                   # Camera specs, topics, schemas
    ├── rules/                       # Coding and protocol rules
    ├── skills/                      # Headless CLI tools & runbooks
    └── agents/                      # Specialized agent personas
```

---

## License

This project is licensed under the [MIT License](LICENSE).


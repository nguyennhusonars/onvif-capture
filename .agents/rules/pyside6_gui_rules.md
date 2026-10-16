# PySide6 GUI & Threading Rules

1. **Strict Thread Isolation via `QObject` Signals:**
   * Never mutate `QWidget`, `QTableWidget`, or `QLabel` instances directly from `RTSPMetadataStreamWorker`, `ONVIFPullPointWorker`, or `RTSPVideoPreviewWorker`.
   * Emit data via `WorkerSignals` (`Signal(object)`, `Signal(str)`, `Signal(QImage)`) connected to main-thread slots on `ONVIFProfileMWindow`.
2. **No `cv2` Import in the GUI Process:**
   * Keep video decoding in `RTSPVideoPreviewWorker` via `/usr/bin/ffmpeg` subprocess (`-pix_fmt rgb24 -f rawvideo pipe:1`) and construct `QImage(..., QImage.Format.Format_RGB888).copy()`. This prevents OpenCV's bundled Qt5 plugins and NumPy 1.x/2.x ABI warnings from interfering with `PySide6` (Qt 6.6).
3. **Sensor Aspect Ratio Alignment (4:3):**
   * The camera's full sensor (`MainStream`, $2592 \times 1944$) has a $4:3$ aspect ratio, and AI bounding boxes are normalized to that full sensor frame. Scale preview frames to $640 \times 480$ ($4:3$) so normalized $[0, 1]$ bounding boxes align 1:1 with the video preview.
4. **Direct `setStyleSheet` over `style().unpolish()`:**
   * When dynamically changing button colors (e.g., Connect vs. Disconnect), call `widget.setStyleSheet(...)` directly rather than `style().unpolish()`/`polish()` to avoid `QPainter` saved-state warnings on offscreen/Wayland platforms.
5. **Virtualized Model/View Architecture:**
   * Always use `QTableView` with virtualized `MetadataTableModel(QAbstractTableModel)` rather than `QTableWidget.insertRow()`. This avoids allocating thousands of `QTableWidgetItem` objects and eliminates UI thread stutter at 25–30 FPS metadata ingest.
6. **Disaggregated Stream Buffer Isolation:**
   * Never route continuous 25 FPS spatial tracking frames and security alarm events to the same FIFO model. Maintain separate models: `events_model` with `max_items=0` (never pruned) and `spatial_model` with `max_items=2000` (rolling telemetry window).
7. **Vertical Row Numbering in Filter Proxies:**
   * Implement `headerData(section, Qt.Orientation.Vertical)` on both `MetadataTableModel` and `MetadataFilterProxyModel` to return `str(section + 1)` so filtered views number consecutive displayed rows $1 \dots N$.
8. **Independent Detail Splitter Drawers:**
   * AI Rule & Alarm Events (`Tab 1`) and Spatial Object Tracking (`Tab 3`) maintain independent, identical detail splitters (`spatial_json_view`, `spatial_xml_view` vs. `parsed_json_view`, `raw_xml_view`). Rapid row updates or selections in `spatial_table` must never mutate or spam the Events tab's detail views.
9. **Capture Wall RTSP Ingestion Exclusivity:**
   * `EventGalleryGrid` (Capture Wall) and `EventSnapshotStrip` only ingest active alarm events from the primary RTSP metadata stream (`"RTSP" in item.channel`), preventing redundant text-only duplicates from background ONVIF PullPoint polling. PullPoint notifications remain fully tracked and searchable in `events_model` (Tab 0).
10. **Ampersand Mnemonic Avoidance in UI Text:**
    * In PySide6 / Qt, `QPushButton`, `QTabBar`, and `QGroupBox` interpret unescaped `&` as a keyboard accelerator mnemonic prefix, rendering undesired underlines or omitting characters (e.g., `Rules & Modules` renders as `Rules _Modules`).
    * Always write out natural English conjunctions (`and`) or concise labels (e.g., `Rules and Modules`, `Select and Connect`, `Live Preview and Analytics`) rather than using raw `&` or double `&&`.
11. **Natural Numerical Sorting in Qt Tables:**
    * IP address columns must use `IPTableWidgetItem` subclassing `QTableWidgetItem` with `ipaddress.ip_address()` comparisons in `__lt__` to ensure `192.169.1.9` precedes `192.169.1.140`.
    * Port columns must use `NumericTableWidgetItem` comparing integer values.
    * Temporarily disable table sorting (`setSortingEnabled(False)`) when inserting rows in batch, and restore sorting afterwards to eliminate UI flicker.

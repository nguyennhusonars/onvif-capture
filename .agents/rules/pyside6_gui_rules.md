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


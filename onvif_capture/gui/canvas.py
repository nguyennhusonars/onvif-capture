import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..models import CapturedMetadataItem, DetectedObject


class VideoAnalyticsCanvas(QWidget):
    """Renders live RTSP video frames with synchronized ONVIF Profile M bounding boxes,
    interactive HUD telemetry, class filtering, and alert pulsing."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(480, 340)

        self._current_image: Optional[QImage] = None
        self._tracked_objects: Dict[str, Tuple[float, DetectedObject]] = {}
        self._active_alerts: Deque[Tuple[float, str]] = deque(maxlen=10)
        self.overlay_ttl: float = 0.5

        # HUD and filtering states
        self.is_frozen: bool = False
        self.show_faces: bool = True
        self.show_humans: bool = True
        self.show_vehicles: bool = True
        self.show_other: bool = True
        self.show_labels: bool = True
        self.show_alerts: bool = True

        # Telemetry & Alert Glow
        self._frame_timestamps: Deque[float] = deque(maxlen=20)
        self.current_fps: float = 0.0
        self._last_alert_time: float = 0.0

    def set_frame(self, image: QImage) -> None:
        if self.is_frozen:
            return  # Paused for inspection

        now = time.time()
        self._frame_timestamps.append(now)
        if len(self._frame_timestamps) >= 3:
            elapsed = self._frame_timestamps[-1] - self._frame_timestamps[0]
            if elapsed > 0.001:
                self.current_fps = (len(self._frame_timestamps) - 1) / elapsed

        self._current_image = image
        self.update()

    def set_frozen(self, frozen: bool) -> None:
        self.is_frozen = frozen
        self.update()

    def clear_frame(self) -> None:
        self._current_image = None
        self._tracked_objects.clear()
        self._frame_timestamps.clear()
        self.current_fps = 0.0
        self.update()

    def grab_frame_jpeg(
        self, bbox: Optional[Tuple[float, float, float, float]] = None
    ) -> Optional[bytes]:
        """Capture the current live video frame as JPEG bytes, optionally cropping around bbox."""
        if self._current_image is None or self._current_image.isNull():
            return None
        img = self._current_image
        if bbox is not None:
            x1, y1, x2, y2 = bbox
            w, h = img.width(), img.height()
            rx, ry = int(max(0, x1 * w)), int(max(0, y1 * h))
            rw, rh = int(min(w - rx, (x2 - x1) * w)), int(min(h - ry, (y2 - y1) * h))
            if rw >= 16 and rh >= 16:
                img = img.copy(rx, ry, rw, rh)

        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "JPEG", 85)
        return bytes(ba.data())

    def add_metadata_item(self, item: CapturedMetadataItem, trigger_update: bool = True) -> None:
        now = time.time()
        for idx, obj in enumerate(item.objects):
            if obj.bbox is not None:
                # Key strictly by object_id so same object always updates in-place with zero duplicate boxes
                key = str(obj.object_id) if (obj.object_id and obj.object_id != "-") else f"{obj.class_type}_{idx}"
                self._tracked_objects[key] = (now, obj)

        if item.kind == "event" and item.property_operation != "Initialized":
            short_topic = item.topic_or_source.split("/")[-1]
            lk = f" ({item.likelihood:.0%})" if item.likelihood is not None else ""
            self._active_alerts.append((now, f"{short_topic}: {item.rule_or_object_id}{lk} — {item.summary}"))
            self._last_alert_time = now

        if trigger_update:
            self.update()

    def add_metadata_items(self, items: List[CapturedMetadataItem]) -> None:
        if not items:
            return
        for item in items:
            self.add_metadata_item(item, trigger_update=False)
        self.update()

    def _prune_expired(self) -> None:
        cutoff = time.time() - self.overlay_ttl
        expired_keys = [k for k, (ts, _) in self._tracked_objects.items() if ts < cutoff]
        for k in expired_keys:
            del self._tracked_objects[k]
        alert_cutoff = time.time() - max(3.5, self.overlay_ttl * 5)
        while self._active_alerts and self._active_alerts[0][0] < alert_cutoff:
            self._active_alerts.popleft()

    def _should_display_class(self, class_type: str) -> bool:
        c = class_type.lower()
        if "face" in c:
            return self.show_faces
        if "human" in c or "person" in c or "body" in c:
            return self.show_humans
        if "vehicle" in c or "car" in c or "plate" in c or "license" in c:
            return self.show_vehicles
        return self.show_other

    def _color_for_class(self, class_type: str) -> QColor:
        c = class_type.lower()
        if "face" in c:
            return QColor("#EA80FC")  # Bright lilac/purple
        if "human" in c or "person" in c or "body" in c:
            return QColor("#00E676")  # Vibrant green
        if "vehicle" in c or "car" in c:
            return QColor("#29B6F6")  # Light blue
        if "plate" in c or "license" in c:
            return QColor("#FFD54F")  # Amber gold
        return QColor("#FF5252")  # Bright coral

    def paintEvent(self, _event: Any) -> None:
        self._prune_expired()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, QColor("#0d1117"))

        # Calculate 4:3 video rectangle centered inside canvas
        if self._current_image and not self._current_image.isNull():
            img_w = self._current_image.width()
            img_h = self._current_image.height()
            scale = min(rect.width() / img_w, rect.height() / img_h)
            draw_w = img_w * scale
            draw_h = img_h * scale
            offset_x = (rect.width() - draw_w) / 2.0
            offset_y = (rect.height() - draw_h) / 2.0
            video_rect = QRectF(offset_x, offset_y, draw_w, draw_h)
            painter.drawImage(video_rect, self._current_image)
        else:
            video_rect = QRectF(12, 12, rect.width() - 24, rect.height() - 24)
            painter.setPen(QPen(QColor("#21262d"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(video_rect)
            painter.setPen(QColor("#8b949e"))
            painter.setFont(QFont("Sans Serif", 10))
            painter.drawText(
                video_rect,
                Qt.AlignmentFlag.AlignCenter,
                "Video Preview (Idle)\n(AI overlays render live)",
            )

        # Visual Alert Glow when an alarm event recently arrived (< 1.5s)
        time_since_alert = time.time() - self._last_alert_time
        if time_since_alert < 1.5:
            alpha = int(220 * (1.0 - (time_since_alert / 1.5)))
            alert_pen = QPen(QColor(248, 81, 73, alpha), 4.0)
            painter.setPen(alert_pen)
            painter.drawRect(video_rect)

        # Draw Freeze-frame indicator if active
        if self.is_frozen:
            pause_badge = QRectF(video_rect.left() + 8, video_rect.top() + 8, 90, 24)
            painter.fillRect(pause_badge, QColor(218, 54, 51, 230))
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(pause_badge, Qt.AlignmentFlag.AlignCenter, "FROZEN")

        # Telemetry HUD in top-right corner
        fps_txt = f"{self.current_fps:.1f} FPS" if self.current_fps > 0 else "Idle"
        res_txt = (
            f"{self._current_image.width()}x{self._current_image.height()} | {fps_txt}"
            if self._current_image
            else "No Video"
        )
        fm_hud = painter.fontMetrics()
        hud_w = fm_hud.horizontalAdvance(res_txt) + 16
        hud_rect = QRectF(video_rect.right() - hud_w - 6, video_rect.top() + 6, hud_w, 20)
        painter.fillRect(hud_rect, QColor(13, 17, 23, 200))
        painter.setPen(QColor("#58a6ff"))
        painter.setFont(QFont("Monospace", 8, QFont.Weight.Bold))
        painter.drawText(hud_rect, Qt.AlignmentFlag.AlignCenter, res_txt)

        # Render Bounding Boxes & AI Labels
        font_label = QFont("Monospace", 9, QFont.Weight.Bold)
        painter.setFont(font_label)

        for _, obj in list(self._tracked_objects.values()):
            if not obj.bbox:
                continue
            if not self._should_display_class(obj.class_type):
                continue

            x1, y1, x2, y2 = obj.bbox
            bx = video_rect.left() + x1 * video_rect.width()
            by = video_rect.top() + y1 * video_rect.height()
            bw = max(6.0, (x2 - x1) * video_rect.width())
            bh = max(6.0, (y2 - y1) * video_rect.height())

            color = self._color_for_class(obj.class_type)
            pen = QPen(color, 2.5)
            painter.setPen(pen)
            painter.drawRect(QRectF(bx, by, bw, bh))

            if not self.show_labels:
                continue

            lk_txt = f" {obj.likelihood:.0%}" if obj.likelihood is not None else ""
            header = f"#{obj.object_id} {obj.class_type}{lk_txt}"
            attr_lines = [header]
            for k, v in obj.attributes.items():
                if k in ("Image", "BoundingBox"):
                    continue
                if isinstance(v, dict):
                    compact = ", ".join(f"{sk}:{sv}" for sk, sv in v.items())
                    attr_lines.append(f"{k}: {compact}")
                else:
                    attr_lines.append(f"{k}: {v}")

            label_text = " | ".join(attr_lines)[:90]
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(label_text) + 12
            th = fm.height() + 6
            ly = max(video_rect.top(), by - th)
            bg_rect = QRectF(bx, ly, min(tw, video_rect.width()), th)
            painter.fillRect(bg_rect, QColor(13, 17, 23, 220))
            painter.setPen(color)
            painter.drawText(bg_rect.adjusted(5, 2, -5, -2), Qt.AlignmentFlag.AlignVCenter, label_text)

        # Render Active Event Alert Banners
        if self.show_alerts and self._active_alerts:
            y_cursor = video_rect.top() + (36 if self.is_frozen else 8)
            for _, alert_txt in list(self._active_alerts)[-3:]:
                fm = painter.fontMetrics()
                tw = min(video_rect.width() - 16, fm.horizontalAdvance(alert_txt) + 16)
                th = fm.height() + 8
                alert_rect = QRectF(video_rect.left() + 8, y_cursor, tw, th)
                painter.fillRect(alert_rect, QColor(183, 28, 28, 230))
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(alert_rect.adjusted(6, 2, -6, -2), Qt.AlignmentFlag.AlignVCenter, alert_txt)
                y_cursor += th + 4

    def grab_annotated_frame(self) -> QImage:
        """Renders the current canvas into a high-quality QImage for export/saving."""
        img = QImage(self.size(), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        self.render(img)
        return img

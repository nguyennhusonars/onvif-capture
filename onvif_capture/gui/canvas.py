import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..models import CapturedMetadataItem, DetectedObject


class VideoAnalyticsCanvas(QWidget):
    """Renders live RTSP video frames with synchronized ONVIF Profile M bounding boxes and AI attributes."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(480, 340)
        self._current_image: Optional[QImage] = None
        self._tracked_objects: Dict[str, Tuple[float, DetectedObject]] = {}
        self._active_alerts: Deque[Tuple[float, str]] = deque(maxlen=10)
        self.overlay_ttl: float = 0.5

    def set_frame(self, image: QImage) -> None:
        self._current_image = image
        self.update()

    def clear_frame(self) -> None:
        self._current_image = None
        self._tracked_objects.clear()
        self.update()

    def add_metadata_item(self, item: CapturedMetadataItem) -> None:
        now = time.time()
        for idx, obj in enumerate(item.objects):
            if obj.bbox is not None:
                # Key strictly by object_id so same object always updates in-place with zero duplicate boxes
                key = str(obj.object_id) if (obj.object_id and obj.object_id != "-") else f"{obj.class_type}_{idx}"
                self._tracked_objects[key] = (now, obj)
        if item.kind == "event" and item.property_operation != "Initialized":
            short_topic = item.topic_or_source.split("/")[-1]
            lk = f" ({item.likelihood:.0%})" if item.likelihood is not None else ""
            self._active_alerts.append((now, f"⚡ {short_topic}: {item.rule_or_object_id}{lk} — {item.summary}"))
        self.update()

    def _prune_expired(self) -> None:
        cutoff = time.time() - self.overlay_ttl
        expired_keys = [k for k, (ts, _) in self._tracked_objects.items() if ts < cutoff]
        for k in expired_keys:
            del self._tracked_objects[k]
        alert_cutoff = time.time() - max(3.5, self.overlay_ttl * 5)
        while self._active_alerts and self._active_alerts[0][0] < alert_cutoff:
            self._active_alerts.popleft()

    def _color_for_class(self, class_type: str) -> QColor:
        c = class_type.lower()
        if "human" in c or "person" in c or "body" in c:
            return QColor("#00E676")
        if "face" in c:
            return QColor("#EA80FC")
        if "vehicle" in c or "car" in c:
            return QColor("#29B6F6")
        if "plate" in c or "license" in c:
            return QColor("#FFD54F")
        return QColor("#FF5252")

    def paintEvent(self, _event: Any) -> None:
        self._prune_expired()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, QColor("#11161d"))

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
            painter.setPen(QPen(QColor("#2c3849"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(video_rect)
            painter.setPen(QColor("#7f8fa6"))
            painter.setFont(QFont("Sans Serif", 10))
            painter.drawText(
                video_rect,
                Qt.AlignmentFlag.AlignCenter,
                "RTSP Video Canvas\n(AI Bounding Boxes & Attributes render in normalized [0..1] space)",
            )

        font_label = QFont("Monospace", 9, QFont.Weight.Bold)
        painter.setFont(font_label)

        for _, obj in list(self._tracked_objects.values()):
            if not obj.bbox:
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
            painter.fillRect(bg_rect, QColor(15, 20, 28, 215))
            painter.setPen(color)
            painter.drawText(bg_rect.adjusted(5, 2, -5, -2), Qt.AlignmentFlag.AlignVCenter, label_text)

        if self._active_alerts:
            y_cursor = video_rect.top() + 8
            for _, alert_txt in list(self._active_alerts)[-4:]:
                fm = painter.fontMetrics()
                tw = min(video_rect.width() - 16, fm.horizontalAdvance(alert_txt) + 16)
                th = fm.height() + 8
                alert_rect = QRectF(video_rect.left() + 8, y_cursor, tw, th)
                painter.fillRect(alert_rect, QColor(183, 28, 28, 220))
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(alert_rect.adjusted(6, 2, -6, -2), Qt.AlignmentFlag.AlignVCenter, alert_txt)
                y_cursor += th + 4


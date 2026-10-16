import time
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import QBuffer, QByteArray, Qt, Signal
from PySide6.QtGui import QCursor, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models import CapturedMetadataItem


def create_thumbnail_pixmap(image_bytes: bytes, target_w: int = 130, target_h: int = 95) -> QPixmap:
    """Fast downsampled thumbnail generation using QImageReader DCT scale factor."""
    if not image_bytes:
        return QPixmap()
    qba = QByteArray(image_bytes)
    buf = QBuffer(qba)
    buf.open(QBuffer.OpenModeFlag.ReadOnly)
    reader = QImageReader(buf)
    reader.setAutoTransform(True)
    orig_size = reader.size()
    if orig_size.isValid() and orig_size.width() > 0 and orig_size.height() > 0:
        scaled_size = orig_size.scaled(target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(scaled_size)
    img = reader.read()
    if not img.isNull():
        return QPixmap.fromImage(img)
    pix = QPixmap()
    pix.loadFromData(image_bytes)
    if not pix.isNull():
        return pix.scaled(
            target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
        )
    return QPixmap()


class SnapshotCard(QFrame):
    """Compact modern card showing a captured snapshot thumbnail with AI badge overlays."""

    clicked = Signal(object)  # CapturedMetadataItem

    def __init__(self, item: CapturedMetadataItem, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setFixedSize(140, 160)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setObjectName("SnapshotCard")

        if item.thumbnail_pixmap is not None and not item.thumbnail_pixmap.isNull():
            self._pixmap = item.thumbnail_pixmap
        elif item.image_bytes:
            self._pixmap = create_thumbnail_pixmap(item.image_bytes)
            item.thumbnail_pixmap = self._pixmap
        else:
            self._pixmap = QPixmap()

        self._build_ui()
        self._set_idle_style()

    def _set_idle_style(self) -> None:
        self.setStyleSheet(
            """
            QFrame#SnapshotCard {
                background-color: #0d1117;
                border: 1px solid #30363d;
                border-radius: 6px;
            }
            QFrame#SnapshotCard:hover {
                background-color: #161b22;
                border: 1px solid #58a6ff;
            }
            """
        )

    def _badge_color_for_rule(self, rule_text: str) -> str:
        r = rule_text.lower()
        if "face" in r:
            return "#a371f7"  # Purple for face
        if "intrusion" in r:
            return "#f85149"  # Red for intrusion
        if "line" in r:
            return "#d29922"  # Amber for line cross
        if "motion" in r or "mrd" in r:
            return "#1f6feb"  # Blue for motion
        if "crowd" in r:
            return "#db61a2"  # Pink for crowd
        if "parking" in r:
            return "#e3b341"  # Yellow for wrong parking
        if "human" in r or "person" in r:
            return "#00E676"  # Bright green for human
        if "vehicle" in r or "plate" in r or "lpr" in r:
            return "#388bfd"  # Blue for vehicle
        return "#238636"  # Green default

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        # Image thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(130, 95)
        self.thumb_label.setStyleSheet("background-color: #010409; border-radius: 6px;")

        if not self._pixmap.isNull():
            self.thumb_label.setPixmap(self._pixmap)
        else:
            self.thumb_label.setText("Text-Only\n(No Image)")
            self.thumb_label.setStyleSheet(
                "color: #e3b341; background-color: #161b22; font-size: 11px; font-weight: bold; border: 1px dashed #d29922; border-radius: 6px; padding: 4px;"
            )

        layout.addWidget(self.thumb_label)

        # Rule tag & likelihood row
        rule_name = self.item.rule_or_object_id or self.item.topic_or_source.split("/")[-1]
        badge_bg = self._badge_color_for_rule(rule_name)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(4)

        rule_badge = QLabel(rule_name[:12])
        rule_badge.setStyleSheet(
            f"background-color: {badge_bg}; color: #ffffff; border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: 600;"
        )
        badge_row.addWidget(rule_badge)

        if self.item.likelihood is not None:
            score_badge = QLabel(f"{int(self.item.likelihood * 100)}%")
            score_badge.setStyleSheet(
                "background-color: #21262d; color: #58a6ff; border: 1px solid #30363d; border-radius: 4px; padding: 2px 5px; font-size: 10px; font-weight: 600;"
            )
            badge_row.addWidget(score_badge)

        if not self.item.image_bytes:
            txt_badge = QLabel("TEXT")
            txt_badge.setToolTip("Snapshot omitted by camera. Only text event metadata received.")
            txt_badge.setStyleSheet(
                "background-color: #30363d; color: #8b949e; border-radius: 4px; padding: 2px 5px; font-size: 9px; font-weight: 600;"
            )
            badge_row.addWidget(txt_badge)

        badge_row.addStretch()
        layout.addLayout(badge_row)

        # Time & Channel row
        time_lbl = QLabel(f"{self.item.utc_time or '-'} ({self.item.channel.split(' ')[0]})")
        time_lbl.setStyleSheet("color: #8b949e; font-size: 10px;")
        layout.addWidget(time_lbl)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item)
        super().mousePressEvent(event)


class SnapshotInspectorDialog(QDialog):
    """High-resolution snapshot inspector dialog with zoom, attributes breakdown, and save functionality."""

    def __init__(self, item: CapturedMetadataItem, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setWindowTitle(f"Snapshot — {item.rule_or_object_id} ({item.utc_time})")
        self.resize(850, 580)
        self.setStyleSheet("background-color: #161b22; color: #e6edf3; font-family: 'Segoe UI', sans-serif;")

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        # Image view container
        img_widget = QWidget()
        img_layout = QVBoxLayout(img_widget)
        img_layout.setContentsMargins(0, 0, 0, 0)

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px;")

        if self.item.image_bytes:
            pix = QPixmap()
            pix.loadFromData(self.item.image_bytes)
            self.img_label.setPixmap(
                pix.scaled(520, 480, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self.img_label.setText("No Snapshot Available\n(No image in event)")

        img_layout.addWidget(self.img_label, stretch=1)
        splitter.addWidget(img_widget)

        # Details view container
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(8, 0, 0, 0)
        details_layout.setSpacing(6)

        header = QLabel(f"<b>Event Details</b>: {self.item.topic_or_source}")
        header.setStyleSheet("color: #58a6ff; font-size: 13px;")
        details_layout.addWidget(header)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet(
            "background-color: #0d1117; color: #c9d1d9; border: 1px solid #30363d; font-family: 'Monospace'; font-size: 11px;"
        )

        if self.item.image_bytes:
            img_desc = f"{len(self.item.image_bytes):,} bytes (Native Camera Snapshot)"
        else:
            img_desc = "None (No image included in event payload)"

        lines = [
            f"UTC Time: {self.item.utc_time}",
            f"Channel: {self.item.channel}",
            f"Topic: {self.item.topic_or_source}",
            f"Rule / Object ID: {self.item.rule_or_object_id}",
            f"Likelihood: {self.item.likelihood:.2f}" if self.item.likelihood is not None else "Likelihood: -",
            f"Snapshot: {img_desc}",
            f"Biometric Template: {len(self.item.template_bytes):,} bytes (Face Embedding)" if self.item.template_bytes else "",
            "",
            "--- Source Items ---",
        ]
        for k, v in self.item.source_items.items():
            lines.append(f"{k}: {v}")

        lines.append("")
        lines.append("--- Data Items ---")
        for k, v in self.item.data_items.items():
            if k != "Image":
                lines.append(f"{k}: {v}")

        self.info_text.setPlainText("\n".join(lines))
        details_layout.addWidget(self.info_text, stretch=1)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save JPEG...")
        save_btn.setEnabled(bool(self.item.image_bytes))
        if not self.item.image_bytes:
            save_btn.setToolTip("No snapshot image available to save")
            save_btn.setStyleSheet(
                "background-color: #21262d; color: #484f58; padding: 6px 12px; font-weight: bold; border-radius: 4px; border: 1px solid #30363d;"
            )
        else:
            save_btn.setStyleSheet(
                "background-color: #238636; color: #ffffff; padding: 6px 12px; font-weight: bold; border-radius: 4px;"
            )
        save_btn.clicked.connect(self._save_image)
        btn_row.addWidget(save_btn)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 12px; border-radius: 4px;"
        )
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        details_layout.addLayout(btn_row)
        splitter.addWidget(details_widget)
        splitter.setSizes([520, 310])

    def _save_image(self) -> None:
        if not self.item.image_bytes:
            return
        default_name = f"snapshot_{self.item.rule_or_object_id}_{int(time.time())}.jpg"
        path, _ = QFileDialog.getSaveFileName(self, "Save Snapshot JPEG", default_name, "JPEG (*.jpg *.jpeg)")
        if path:
            Path(path).write_bytes(self.item.image_bytes)
            QMessageBox.information(self, "Saved", f"Snapshot saved successfully to:\n{path}")


class EventSnapshotStrip(QWidget):
    """Horizontal scrolling quick-strip showing the latest N captured snapshot cards directly below the canvas."""

    snapshot_clicked = Signal(object)  # CapturedMetadataItem

    def __init__(self, max_cards: int = 30, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.max_cards = max_cards
        self.cards: List[SnapshotCard] = []
        self._seen_keys: Dict[Tuple[str, str, str], CapturedMetadataItem] = {}

        self.setFixedHeight(175)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 2, 4, 2)
        self.title_lbl = QLabel("Recent Captures (0)")
        self.title_lbl.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 11px;")
        header_row.addWidget(self.title_lbl)
        header_row.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet(
            "background-color: #21262d; border: 1px solid #30363d; color: #8b949e; padding: 2px 8px; font-size: 10px; border-radius: 3px;"
        )
        self.clear_btn.clicked.connect(self.clear)
        header_row.addWidget(self.clear_btn)
        layout.addLayout(header_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background-color: #090d13; border: 1px solid #30363d; border-radius: 4px;")

        self.container = QWidget()
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(6, 4, 6, 4)
        self.container_layout.setSpacing(8)
        self.container_layout.addStretch()

        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area)

    def add_item(self, item: CapturedMetadataItem) -> None:
        self.add_items([item])

    def add_items(self, new_items: List[CapturedMetadataItem]) -> None:
        if not new_items:
            return

        for item in new_items:
            if not item.image_bytes and item.kind != "event":
                continue

            key = (item.topic_or_source, item.rule_or_object_id, item.utc_time or "")
            if key in self._seen_keys:
                existing = self._seen_keys[key]
                if item.image_bytes and not existing.image_bytes:
                    self._seen_keys[key] = item
                    for idx, c in enumerate(self.cards):
                        if c.item is existing:
                            new_card = SnapshotCard(item)
                            new_card.clicked.connect(self._on_card_clicked)
                            self.cards[idx] = new_card
                            self.container_layout.replaceWidget(c, new_card)
                            c.deleteLater()
                            break
                continue

            self._seen_keys[key] = item
            card = SnapshotCard(item)
            card.clicked.connect(self._on_card_clicked)

            # Insert at the beginning (before the stretch)
            self.container_layout.insertWidget(0, card)
            self.cards.insert(0, card)

            # Prune older cards if exceeding max_cards
            if len(self.cards) > self.max_cards:
                old_card = self.cards.pop()
                old_key = (old_card.item.topic_or_source, old_card.item.rule_or_object_id, old_card.item.utc_time or "")
                self._seen_keys.pop(old_key, None)
                self.container_layout.removeWidget(old_card)
                old_card.deleteLater()

        self.title_lbl.setText(f"Recent Captures ({len(self.cards)})")

    def _on_card_clicked(self, item: CapturedMetadataItem) -> None:
        self.snapshot_clicked.emit(item)

    def count(self) -> int:
        return len(self.cards)

    def clear(self) -> None:
        for card in self.cards:
            self.container_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self._seen_keys.clear()
        self.title_lbl.setText("Recent Captures (0)")


class EventGalleryGrid(QWidget):
    """Full-tab multi-column capture wall showing all captured snapshots with search, rule filtering, and batch export."""

    snapshot_selected = Signal(object)  # CapturedMetadataItem

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.items: List[CapturedMetadataItem] = []
        self._cards: List[SnapshotCard] = []
        self._seen_keys: Dict[Tuple[str, str, str], CapturedMetadataItem] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Top action toolbar
        tool_row = QHBoxLayout()
        tool_row.setSpacing(8)

        tool_row.addWidget(QLabel("Filter:"))
        self.rule_filter_edit = QLineEdit()
        self.rule_filter_edit.setPlaceholderText("Filter rule...")
        self.rule_filter_edit.setFixedWidth(180)
        self.rule_filter_edit.textChanged.connect(self._refilter_cards)
        tool_row.addWidget(self.rule_filter_edit)

        self.count_label = QLabel("0 Captures")
        self.count_label.setStyleSheet(
            "background-color: #161b22; color: #58a6ff; border: 1px solid #21262d; border-radius: 12px; padding: 3px 10px; font-weight: 600; font-size: 11px;"
        )
        tool_row.addWidget(self.count_label)
        tool_row.addStretch()

        self.export_all_btn = QPushButton("Export JPEGs...")
        self.export_all_btn.setStyleSheet(
            "background-color: #238636; color: #ffffff; padding: 5px 12px; font-weight: 600; border-radius: 6px;"
        )
        self.export_all_btn.clicked.connect(self._export_all_snapshots)
        tool_row.addWidget(self.export_all_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet(
            "background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 5px 12px; font-weight: 500; border-radius: 6px;"
        )
        self.clear_btn.clicked.connect(self.clear)
        tool_row.addWidget(self.clear_btn)

        layout.addLayout(tool_row)

        # Scroll area for multi-column grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #090d13; border: 1px solid #21262d; border-radius: 8px;")

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll, stretch=1)

    def add_item(self, item: CapturedMetadataItem) -> None:
        self.add_items([item])

    def add_items(self, new_items: List[CapturedMetadataItem]) -> None:
        if not new_items:
            return

        query = self.rule_filter_edit.text().strip().lower()
        cols = max(3, self.width() // 160) if self.width() > 100 else 4
        needs_full_relayout = False

        for item in new_items:
            if not item.image_bytes and item.kind != "event":
                continue

            key = (item.topic_or_source, item.rule_or_object_id, item.utc_time or "")
            if key in self._seen_keys:
                existing = self._seen_keys[key]
                # Upgrade existing text card if incoming item has an image
                if item.image_bytes and not existing.image_bytes:
                    self._seen_keys[key] = item
                    for idx, c in enumerate(self._cards):
                        if c.item is existing:
                            self.items[idx] = item
                            new_card = SnapshotCard(item)
                            new_card.clicked.connect(self._on_card_clicked)
                            self._cards[idx] = new_card
                            c.deleteLater()
                            needs_full_relayout = True
                            break
                continue

            self._seen_keys[key] = item
            card = SnapshotCard(item)
            card.clicked.connect(self._on_card_clicked)
            self.items.insert(0, item)
            self._cards.insert(0, card)
            needs_full_relayout = True

        if needs_full_relayout:
            self._relayout_grid()

        img_count = sum(1 for it in self.items if it.image_bytes)
        text_count = len(self.items) - img_count
        if text_count > 0:
            self.count_label.setText(f"{len(self.items)} Events ({img_count} with image, {text_count} text-only)")
        else:
            self.count_label.setText(f"{len(self.items)} Captures")

    def _on_card_clicked(self, item: CapturedMetadataItem) -> None:
        self.snapshot_selected.emit(item)
        # Open inspector dialog
        dlg = SnapshotInspectorDialog(item, self)
        dlg.exec()

    def _refilter_cards(self) -> None:
        self._relayout_grid()

    def _relayout_grid(self) -> None:
        # Clear existing items from layout without unparenting widgets
        while self.grid_layout.count() > 0:
            self.grid_layout.takeAt(0)

        query = self.rule_filter_edit.text().strip().lower()
        cols = max(3, self.width() // 160) if self.width() > 100 else 4
        cur_row = 0
        cur_col = 0

        for card in self._cards:
            rule_str = (card.item.rule_or_object_id or card.item.topic_or_source).lower()
            if query and query not in rule_str:
                card.setVisible(False)
                continue

            card.setVisible(True)
            self.grid_layout.addWidget(card, cur_row, cur_col)
            cur_col += 1
            if cur_col >= cols:
                cur_col = 0
                cur_row += 1

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._relayout_grid()

    def _export_all_snapshots(self) -> None:
        if not self.items:
            QMessageBox.information(self, "Export", "No snapshots to export.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Select Directory to Save All Snapshots")
        if not out_dir:
            return

        count = 0
        for idx, item in enumerate(self.items):
            if not item.image_bytes:
                continue
            rule = (item.rule_or_object_id or "event").replace(" ", "_").replace("/", "_")
            timestamp = (item.utc_time or "").replace(":", "-").replace(" ", "_") or f"snap_{idx}"
            score = f"_score{int(item.likelihood * 100)}" if item.likelihood is not None else ""
            filename = f"{timestamp}_{rule}{score}_{idx:04d}.jpg"
            dest = Path(out_dir) / filename
            dest.write_bytes(item.image_bytes)
            count += 1

        QMessageBox.information(
            self,
            "Export Complete",
            f"Successfully exported {count} snapshot(s) to:\n{out_dir}",
        )

    def count(self) -> int:
        return len(self.items)

    def clear(self) -> None:
        self.items.clear()
        self._seen_keys.clear()
        for card in self._cards:
            self.grid_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self.count_label.setText("0 Captures")


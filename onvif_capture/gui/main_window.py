import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..client import ONVIFProfileMClient
from ..models import CapturedMetadataItem
from ..parsers import SAMPLE_VERIFIED_XML, parse_metadata_stream_xml
from ..workers import ONVIFPullPointWorker, RTSPMetadataStreamWorker, RTSPVideoPreviewWorker
from .canvas import VideoAnalyticsCanvas


class WorkerSignals(QObject):
    items_received = Signal(object)  # List[CapturedMetadataItem]
    rtsp_status = Signal(str)
    pullpoint_status = Signal(str)
    video_frame = Signal(QImage)
    video_status = Signal(str)
    inventory_ready = Signal(object)  # dict
    error_occurred = Signal(str)


class ONVIFProfileMWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ONVIF Profile M — Native AI Analytics & Metadata Inspector")
        self.resize(1480, 920)

        self.client: Optional[ONVIFProfileMClient] = None
        self.inventory: Dict[str, Any] = {}
        self.rtsp_worker: Optional[RTSPMetadataStreamWorker] = None
        self.pullpoint_worker: Optional[ONVIFPullPointWorker] = None
        self.video_worker: Optional[RTSPVideoPreviewWorker] = None

        self.captured_items: List[CapturedMetadataItem] = []
        self.va_frame_count = 0
        self.rtsp_event_count = 0
        self.pullpoint_event_count = 0
        self.heartbeat_count = 0

        self.signals = WorkerSignals()
        self.signals.items_received.connect(self._on_metadata_items)
        self.signals.rtsp_status.connect(self._on_rtsp_status)
        self.signals.pullpoint_status.connect(self._on_pullpoint_status)
        self.signals.video_frame.connect(self._on_video_frame)
        self.signals.video_status.connect(self._on_video_status)
        self.signals.inventory_ready.connect(self._on_inventory_ready)
        self.signals.error_occurred.connect(self._on_error)

        self._build_ui()
        self._apply_dark_theme()

        self._overlay_timer = QTimer(self)
        self._overlay_timer.timeout.connect(lambda: self.video_canvas.update())
        self._overlay_timer.start(250)

        QTimer.singleShot(200, self.connect_camera)

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background-color: #161b22; color: #e6edf3; font-family: 'Segoe UI', 'Ubuntu', sans-serif; font-size: 12px; }
            QGroupBox { border: 1px solid #30363d; border-radius: 6px; margin-top: 8px; padding-top: 8px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #58a6ff; }
            QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit, QTableWidget {
                background-color: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 4px; padding: 4px;
            }
            QTableWidget { gridline-color: #21262d; selection-background-color: #1f6feb; }
            QHeaderView::section { background-color: #21262d; color: #c9d1d9; padding: 5px; border: 1px solid #30363d; font-weight: bold; }
            QPushButton { background-color: #238636; color: #ffffff; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #2ea043; }
            QPushButton#secondaryBtn { background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; }
            QPushButton#secondaryBtn:hover { background-color: #30363d; }
            QTabWidget::pane { border: 1px solid #30363d; border-radius: 4px; }
            QTabBar::tab { background-color: #21262d; color: #8b949e; padding: 7px 14px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background-color: #1f6feb; color: #ffffff; font-weight: bold; }
            """
        )

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        conn_group = QGroupBox("ONVIF Camera Connection & Native Profile M Metadata Control")
        conn_layout = QHBoxLayout(conn_group)

        conn_layout.addWidget(QLabel("IP:"))
        self.ip_edit = QLineEdit("192.169.1.197")
        self.ip_edit.setFixedWidth(120)
        conn_layout.addWidget(self.ip_edit)

        conn_layout.addWidget(QLabel("Port:"))
        self.port_edit = QLineEdit("8000")
        self.port_edit.setFixedWidth(60)
        conn_layout.addWidget(self.port_edit)

        conn_layout.addWidget(QLabel("User:"))
        self.user_edit = QLineEdit("admin")
        self.user_edit.setFixedWidth(80)
        conn_layout.addWidget(self.user_edit)

        conn_layout.addWidget(QLabel("Pass:"))
        self.pass_edit = QLineEdit("Pavana@123")
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setFixedWidth(100)
        conn_layout.addWidget(self.pass_edit)

        self.connect_btn = QPushButton("Connect & Start Capture")
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_btn)

        self.profile_m_badge = QLabel("Disconnected")
        self.profile_m_badge.setStyleSheet(
            "background-color: #30363d; color: #8b949e; padding: 4px 8px; border-radius: 4px; font-weight: bold;"
        )
        conn_layout.addWidget(self.profile_m_badge)

        self.enable_analytics_cb = QCheckBox("Enable Camera Metadata (Analytics=true & Events)")
        self.enable_analytics_cb.setChecked(True)
        self.enable_analytics_cb.clicked.connect(self._on_toggle_camera_metadata_config)
        conn_layout.addWidget(self.enable_analytics_cb)

        conn_layout.addWidget(QLabel("Stream:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(160)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        conn_layout.addWidget(self.profile_combo)

        self.video_preview_cb = QCheckBox("Live Video Preview")
        self.video_preview_cb.setChecked(True)
        self.video_preview_cb.toggled.connect(self._on_toggle_video_preview)
        conn_layout.addWidget(self.video_preview_cb)

        conn_layout.addStretch()
        root_layout.addWidget(conn_group)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(main_splitter, stretch=1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        video_group = QGroupBox("Live RTSP Stream + Synchronized Profile M AI Overlay")
        vg_layout = QVBoxLayout(video_group)
        self.video_canvas = VideoAnalyticsCanvas()
        vg_layout.addWidget(self.video_canvas, stretch=1)

        ttl_row = QHBoxLayout()
        ttl_row.addWidget(QLabel("Overlay Box Retention (s):"))
        self.ttl_spin = QDoubleSpinBox()
        self.ttl_spin.setRange(0.1, 5.0)
        self.ttl_spin.setSingleStep(0.1)
        self.ttl_spin.setValue(0.5)
        self.ttl_spin.valueChanged.connect(self._on_ttl_changed)
        ttl_row.addWidget(self.ttl_spin)

        self.counters_label = QLabel("VA Frames: 0 | RTSP Events: 0 | PullPoint Events: 0 | Heartbeats: 0")
        self.counters_label.setStyleSheet("color: #58a6ff; font-weight: bold;")
        ttl_row.addWidget(self.counters_label)
        ttl_row.addStretch()
        vg_layout.addLayout(ttl_row)
        left_layout.addWidget(video_group, stretch=3)

        snap_group = QGroupBox("Native ONVIF Event Embedded Snapshot (<tt:ElementItem Name='Image'>)")
        snap_layout = QVBoxLayout(snap_group)
        self.snapshot_label = QLabel("No event snapshot received yet (triggers on Intrusion / LPR / Face events)")
        self.snapshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.snapshot_label.setMinimumHeight(180)
        self.snapshot_label.setStyleSheet("background-color: #0d1117; border: 1px dashed #30363d; color: #8b949e;")
        snap_layout.addWidget(self.snapshot_label, stretch=1)

        snap_btn_row = QHBoxLayout()
        self.snap_info_label = QLabel("-")
        snap_btn_row.addWidget(self.snap_info_label, stretch=1)
        self.save_snap_btn = QPushButton("Save Snapshot JPEG...")
        self.save_snap_btn.setObjectName("secondaryBtn")
        self.save_snap_btn.setEnabled(False)
        self.save_snap_btn.clicked.connect(self._save_current_snapshot)
        snap_btn_row.addWidget(self.save_snap_btn)
        snap_layout.addLayout(snap_btn_row)
        left_layout.addWidget(snap_group, stretch=2)

        main_splitter.addWidget(left_widget)

        self.tabs = QTabWidget()
        main_splitter.addWidget(self.tabs)
        main_splitter.setSizes([540, 920])

        self._build_live_feed_tab()
        self._build_rules_editor_tab()
        self._build_inventory_tab()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.rtsp_status_lbl = QLabel("RTSP Metadata: Idle")
        self.pullpoint_status_lbl = QLabel("PullPoint: Idle")
        self.video_status_lbl = QLabel("Video: Idle")
        for lbl in (self.rtsp_status_lbl, self.pullpoint_status_lbl, self.video_status_lbl):
            lbl.setStyleSheet("padding: 0 10px; color: #8b949e;")
            self.status_bar.addPermanentWidget(lbl)

        self._current_snapshot_bytes: Optional[bytes] = None

    def _build_live_feed_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Channel:"))
        self.channel_filter_combo = QComboBox()
        self.channel_filter_combo.addItems(
            [
                "All Channels",
                "All Events (PullPoint + RTSP)",
                "ONVIF PullPoint",
                "RTSP Metadata (Event)",
                "RTSP Metadata (VideoAnalytics)",
            ]
        )
        self.channel_filter_combo.currentIndexChanged.connect(self._refresh_feed_table)
        filter_row.addWidget(self.channel_filter_combo)

        filter_row.addWidget(QLabel("Search Topic/Class/ID:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("e.g. Human, Intrusion, Face, LicensePlate, #108...")
        self.search_edit.textChanged.connect(self._refresh_feed_table)
        filter_row.addWidget(self.search_edit, stretch=1)

        self.hide_init_cb = QCheckBox("Hide 'Initialized' Heartbeats")
        self.hide_init_cb.setChecked(True)
        self.hide_init_cb.toggled.connect(self._refresh_feed_table)
        filter_row.addWidget(self.hide_init_cb)

        self.simulate_btn = QPushButton("Inject Verified Camera Sample")
        self.simulate_btn.setObjectName("secondaryBtn")
        self.simulate_btn.setToolTip(
            "Replay real captured PAVANA Profile M VideoAnalytics & Event XML frames for testing"
        )
        self.simulate_btn.clicked.connect(self._inject_verified_sample)
        filter_row.addWidget(self.simulate_btn)

        self.export_btn = QPushButton("Export JSONL...")
        self.export_btn.setObjectName("secondaryBtn")
        self.export_btn.clicked.connect(self._export_jsonl)
        filter_row.addWidget(self.export_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("secondaryBtn")
        self.clear_btn.clicked.connect(self._clear_feed)
        filter_row.addWidget(self.clear_btn)

        layout.addLayout(filter_row)

        feed_splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(feed_splitter, stretch=1)

        self.feed_table = QTableWidget(0, 7)
        self.feed_table.setHorizontalHeaderLabels(
            [
                "UTC Time",
                "Channel",
                "Topic / Source",
                "Rule / Object ID",
                "Likelihood",
                "AI Metadata Summary",
                "Snapshot",
            ]
        )
        self.feed_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.feed_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.feed_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.feed_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.feed_table.itemSelectionChanged.connect(self._on_feed_row_selected)
        feed_splitter.addWidget(self.feed_table)

        detail_splitter = QSplitter(Qt.Orientation.Horizontal)
        feed_splitter.addWidget(detail_splitter)
        feed_splitter.setSizes([450, 320])

        json_group = QGroupBox("Parsed Profile M Attributes (Source, Data & Appearance)")
        jg_layout = QVBoxLayout(json_group)
        self.parsed_json_view = QPlainTextEdit()
        self.parsed_json_view.setReadOnly(True)
        self.parsed_json_view.setFont(QFont("Monospace", 10))
        jg_layout.addWidget(self.parsed_json_view)
        detail_splitter.addWidget(json_group)

        xml_group = QGroupBox("Raw ONVIF XML Payload (<tt:Frame> / <wsnt:NotificationMessage>)")
        xg_layout = QVBoxLayout(xml_group)
        self.raw_xml_view = QPlainTextEdit()
        self.raw_xml_view.setReadOnly(True)
        self.raw_xml_view.setFont(QFont("Monospace", 10))
        xg_layout.addWidget(self.raw_xml_view)
        detail_splitter.addWidget(xml_group)

        self.tabs.addTab(tab, "📡 Live AI Metadata & Events (0)")

    def _build_rules_editor_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_bar = QHBoxLayout()
        top_bar.addWidget(
            QLabel(
                "View and modify active ONVIF Profile M Analytics Rules & Thresholds directly on the camera (`tan:ModifyRules`)."
            )
        )
        top_bar.addStretch()
        refresh_rules_btn = QPushButton("Refresh Rules from Camera")
        refresh_rules_btn.setObjectName("secondaryBtn")
        refresh_rules_btn.clicked.connect(self._refresh_rules_from_camera)
        top_bar.addWidget(refresh_rules_btn)

        apply_all_btn = QPushButton("Apply Modified Rules to Camera")
        apply_all_btn.clicked.connect(self._apply_rules_to_camera)
        top_bar.addWidget(apply_all_btn)
        layout.addLayout(top_bar)

        rules_group = QGroupBox("Active Camera Rules (Double-click 'Parameter Value' to edit)")
        rg_layout = QVBoxLayout(rules_group)
        self.rules_table = QTableWidget(0, 4)
        self.rules_table.setHorizontalHeaderLabels(
            ["Rule Name", "Rule Type (ONVIF)", "Parameter Name", "Parameter Value (Editable)"]
        )
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        rg_layout.addWidget(self.rules_table)
        layout.addWidget(rules_group, stretch=3)

        mods_group = QGroupBox("Verified Analytics Modules & Event Payload Schemas (GetSupportedAnalyticsModules)")
        mg_layout = QVBoxLayout(mods_group)
        self.modules_table = QTableWidget(0, 5)
        self.modules_table.setHorizontalHeaderLabels(
            [
                "Module Type",
                "Parent Event Topic",
                "Config Parameters",
                "Event Data (SimpleItem)",
                "Event Data (ElementItem)",
            ]
        )
        self.modules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.modules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.modules_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        mg_layout.addWidget(self.modules_table)
        layout.addWidget(mods_group, stretch=2)

        self.tabs.addTab(tab, "⚙️ AI Rules & Analytics Modules")

    def _build_inventory_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        sub_tabs = QTabWidget()
        layout.addWidget(sub_tabs)

        self_overview = QPlainTextEdit()
        self_overview.setReadOnly(True)
        self_overview.setFont(QFont("Monospace", 10))
        self.inv_overview_text = self_overview
        sub_tabs.addTab(self_overview, "Device Scopes & MetadataConfiguration")

        self.topics_table = QTableWidget(0, 4)
        self.topics_table.setHorizontalHeaderLabels(
            ["ONVIF Topic (TopicSet)", "IsProperty", "Source Items", "Data Items"]
        )
        self.topics_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.topics_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.topics_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.topics_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        sub_tabs.addTab(self.topics_table, "Event TopicSet (GetEventProperties)")

        self.media2_xml_view = QPlainTextEdit()
        self.media2_xml_view.setReadOnly(True)
        self.media2_xml_view.setFont(QFont("Monospace", 10))
        sub_tabs.addTab(self.media2_xml_view, "Media2 Profiles XML (ver20/media/wsdl)")

        self.supported_meta_xml_view = QPlainTextEdit()
        self.supported_meta_xml_view.setReadOnly(True)
        self.supported_meta_xml_view.setFont(QFont("Monospace", 10))
        sub_tabs.addTab(self.supported_meta_xml_view, "Supported Metadata Schemas (GetSupportedMetadata)")

        self.tabs.addTab(tab, "🔍 Verified Profile M Inventory")

    def toggle_connection(self) -> None:
        if self.rtsp_worker or self.pullpoint_worker:
            self.disconnect_camera()
        else:
            self.connect_camera()

    def connect_camera(self) -> None:
        host = self.ip_edit.text().strip()
        port = int(self.port_edit.text().strip() or "8000")
        user = self.user_edit.text().strip()
        pwd = self.pass_edit.text()

        self.connect_btn.setEnabled(False)
        self.profile_m_badge.setText("Connecting & Verifying...")

        def _connect_task() -> None:
            try:
                client = ONVIFProfileMClient(host, port, user, pwd)
                inv = client.connect()
                if self.enable_analytics_cb.isChecked() and (
                    not inv["analytics_enabled"] or not inv["events_enabled"]
                ):
                    updated_mc = client.set_metadata_analytics_enabled(True, True)
                    inv["metadata_config"] = updated_mc
                    inv["analytics_enabled"] = True
                    inv["events_enabled"] = True
                self.client = client
                self.signals.inventory_ready.emit(inv)
            except Exception as exc:
                self.signals.error_occurred.emit(f"Connection failed: {exc}")

        threading.Thread(target=_connect_task, daemon=True).start()

    def disconnect_camera(self) -> None:
        if self.rtsp_worker:
            self.rtsp_worker.stop()
            self.rtsp_worker = None
        if self.pullpoint_worker:
            self.pullpoint_worker.stop()
            self.pullpoint_worker = None
        if self.video_worker:
            self.video_worker.stop()
            self.video_worker = None
        self.video_canvas.clear_frame()
        self.connect_btn.setText("Connect & Start Capture")
        self.connect_btn.setStyleSheet("background-color: #238636; color: #ffffff;")
        self.profile_m_badge.setText("Disconnected")
        self.profile_m_badge.setStyleSheet(
            "background-color: #30363d; color: #8b949e; padding: 4px 8px; border-radius: 4px; font-weight: bold;"
        )
        self.rtsp_status_lbl.setText("RTSP Metadata: Stopped")
        self.pullpoint_status_lbl.setText("PullPoint: Stopped")
        self.video_status_lbl.setText("Video: Stopped")

    def _on_inventory_ready(self, inv: Dict[str, Any]) -> None:
        self.inventory = inv
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setStyleSheet("background-color: #da3633; color: #ffffff;")

        dev = inv.get("device_info", {})
        model_str = f"{dev.get('Manufacturer', '')} {dev.get('Model', '')}".strip()
        if inv.get("is_profile_m"):
            self.profile_m_badge.setText(f"✓ Profile M Verified ({model_str})")
            self.profile_m_badge.setStyleSheet(
                "background-color: #1f6feb; color: #ffffff; padding: 4px 10px; border-radius: 4px; font-weight: bold;"
            )
        else:
            self.profile_m_badge.setText(f"Connected ({model_str})")

        self.enable_analytics_cb.blockSignals(True)
        self.enable_analytics_cb.setChecked(bool(inv.get("analytics_enabled") and inv.get("events_enabled")))
        self.enable_analytics_cb.blockSignals(False)

        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        profiles = inv.get("profiles", [])
        default_idx = 0
        for idx, p in enumerate(profiles):
            label = f"{p['name']} ({p['width']}x{p['height']}) - {p['token']}"
            self.profile_combo.addItem(label, p)
            if "sub" in p["name"].lower():
                default_idx = idx
        self.profile_combo.setCurrentIndex(default_idx)
        self.profile_combo.blockSignals(False)

        self._populate_rules_and_modules_tables(inv)
        self._populate_inventory_views(inv)
        self._start_stream_workers()

    def _start_stream_workers(self) -> None:
        if not self.client or not self.inventory:
            return
        profiles = self.inventory.get("profiles", [])
        if not profiles:
            return

        main_rtsp_uri = profiles[0]["rtsp_uri"]
        if self.rtsp_worker:
            self.rtsp_worker.stop()
        self.rtsp_worker = RTSPMetadataStreamWorker(
            rtsp_uri=main_rtsp_uri,
            username=self.client.username,
            password=self.client.password,
            on_items=lambda items: self.signals.items_received.emit(items),
            on_status=lambda s: self.signals.rtsp_status.emit(s),
            before_connect=lambda: self.client.set_metadata_analytics_enabled(True, True)
            if (self.client and self.enable_analytics_cb.isChecked())
            else None,
        )
        self.rtsp_worker.start()

        if self.pullpoint_worker:
            self.pullpoint_worker.stop()
        self.pullpoint_worker = ONVIFPullPointWorker(
            host=self.client.host,
            port=self.client.port,
            username=self.client.username,
            password=self.client.password,
            on_items=lambda items: self.signals.items_received.emit(items),
            on_status=lambda s: self.signals.pullpoint_status.emit(s),
        )
        self.pullpoint_worker.start()

        self._restart_video_worker()

    def _restart_video_worker(self) -> None:
        if self.video_worker:
            self.video_worker.stop()
            self.video_worker = None
        if not self.video_preview_cb.isChecked() or not self.client:
            self.video_canvas.clear_frame()
            self.video_status_lbl.setText("Video: Disabled")
            return
        prof = self.profile_combo.currentData()
        if not prof:
            return

        def _emit_qimage(raw: bytes, w: int, h: int) -> None:
            img = QImage(raw, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            self.signals.video_frame.emit(img)

        self.video_worker = RTSPVideoPreviewWorker(
            rtsp_uri=prof["rtsp_uri"],
            username=self.client.username,
            password=self.client.password,
            out_width=640,
            out_height=480,
            on_rgb_frame=_emit_qimage,
            on_status=lambda s: self.signals.video_status.emit(s),
        )
        self.video_worker.start()

    def _on_profile_changed(self, _idx: int) -> None:
        if self.client:
            self._restart_video_worker()

    def _on_toggle_video_preview(self, _checked: bool) -> None:
        if self.client:
            self._restart_video_worker()

    def _on_ttl_changed(self, val: float) -> None:
        self.video_canvas.overlay_ttl = val

    def _on_toggle_camera_metadata_config(self, checked: bool) -> None:
        if not self.client:
            return
        try:
            updated = self.client.set_metadata_analytics_enabled(checked, checked)
            self.inventory["metadata_config"] = updated
            self.inventory["analytics_enabled"] = checked
            self.inventory["events_enabled"] = checked
            self._populate_inventory_views(self.inventory)
            self.status_bar.showMessage(
                f"Updated camera MetadataConfiguration: Analytics={checked}, Events={'Enabled' if checked else 'Disabled'}",
                5000,
            )
        except Exception as exc:
            QMessageBox.warning(self, "SetMetadataConfiguration Error", str(exc))

    def _on_metadata_items(self, items: List[CapturedMetadataItem]) -> None:
        added_visible = False
        for item in items:
            if item.property_operation == "Initialized":
                self.heartbeat_count += 1
            elif item.kind == "object_frame":
                self.va_frame_count += 1
            elif "RTSP" in item.channel:
                self.rtsp_event_count += 1
            else:
                self.pullpoint_event_count += 1

            self.captured_items.append(item)
            self.video_canvas.add_metadata_item(item)

            if item.image_bytes:
                self._display_snapshot(item)

            if self._item_matches_filter(item):
                self._append_row_to_feed_table(len(self.captured_items) - 1, item)
                added_visible = True

        self._update_counters()
        if added_visible:
            self.feed_table.scrollToBottom()

    def _display_snapshot(self, item: CapturedMetadataItem) -> None:
        if not item.image_bytes:
            return
        self._current_snapshot_bytes = item.image_bytes
        pix = QPixmap()
        if pix.loadFromData(item.image_bytes):
            scaled = pix.scaled(
                self.snapshot_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.snapshot_label.setPixmap(scaled)
            short_topic = item.topic_or_source.split("/")[-1]
            self.snap_info_label.setText(
                f"{short_topic} | {item.rule_or_object_id} | {item.utc_time} ({len(item.image_bytes):,} B)"
            )
            self.save_snap_btn.setEnabled(True)

    def _save_current_snapshot(self) -> None:
        if not self._current_snapshot_bytes:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Embedded ONVIF Event Snapshot",
            f"onvif_event_snapshot_{int(time.time())}.jpg",
            "JPEG Images (*.jpg *.jpeg)",
        )
        if path:
            Path(path).write_bytes(self._current_snapshot_bytes)
            self.status_bar.showMessage(f"Saved snapshot to {path}", 5000)

    def _update_counters(self) -> None:
        self.counters_label.setText(
            f"VA Object Frames: {self.va_frame_count} | RTSP Events: {self.rtsp_event_count} | "
            f"PullPoint Events: {self.pullpoint_event_count} | Heartbeats: {self.heartbeat_count}"
        )
        total_non_hb = self.va_frame_count + self.rtsp_event_count + self.pullpoint_event_count
        self.tabs.setTabText(0, f"📡 Live AI Metadata & Events ({total_non_hb})")

    def _item_matches_filter(self, item: CapturedMetadataItem) -> bool:
        if self.hide_init_cb.isChecked() and item.property_operation == "Initialized":
            return False
        ch_filter = self.channel_filter_combo.currentText()
        if ch_filter == "All Events (PullPoint + RTSP)":
            if item.kind != "event":
                return False
        elif ch_filter != "All Channels" and item.channel != ch_filter:
            return False
        q = self.search_edit.text().strip().lower()
        if q:
            haystack = f"{item.topic_or_source} {item.rule_or_object_id} {item.summary}".lower()
            if q not in haystack:
                return False
        return True

    def _append_row_to_feed_table(self, item_idx: int, item: CapturedMetadataItem) -> None:
        if self.feed_table.rowCount() >= 1500:
            self.feed_table.removeRow(0)

        row = self.feed_table.rowCount()
        self.feed_table.insertRow(row)

        lk_str = f"{item.likelihood:.2f}" if item.likelihood is not None else "-"
        snap_str = f"📷 {len(item.image_bytes) // 1024} KB" if item.image_bytes else "-"

        cols = [
            item.utc_time or time.strftime("%H:%M:%S"),
            item.channel,
            item.topic_or_source,
            item.rule_or_object_id,
            lk_str,
            item.summary,
            snap_str,
        ]
        for c_idx, text in enumerate(cols):
            cell = QTableWidgetItem(str(text))
            cell.setData(Qt.ItemDataRole.UserRole, item_idx)
            if item.kind == "object_frame":
                cell.setForeground(QColor("#00E676"))
            elif item.image_bytes:
                cell.setForeground(QColor("#FFA657"))
            elif item.property_operation == "Initialized":
                cell.setForeground(QColor("#8b949e"))
            self.feed_table.setItem(row, c_idx, cell)

    def _refresh_feed_table(self) -> None:
        self.feed_table.setRowCount(0)
        for idx, item in enumerate(self.captured_items):
            if self._item_matches_filter(item):
                self._append_row_to_feed_table(idx, item)

    def _on_feed_row_selected(self) -> None:
        selected = self.feed_table.selectedItems()
        if not selected:
            return
        item_idx = selected[0].data(Qt.ItemDataRole.UserRole)
        if item_idx is None or item_idx >= len(self.captured_items):
            return
        item = self.captured_items[item_idx]

        structured = {
            "channel": item.channel,
            "kind": item.kind,
            "utc_time": item.utc_time,
            "topic_or_source": item.topic_or_source,
            "rule_or_object_id": item.rule_or_object_id,
            "property_operation": item.property_operation,
            "likelihood": item.likelihood,
            "normalized_bbox_0_1": item.bbox,
            "source_items": item.source_items,
            "data_items": item.data_items,
        }
        self.parsed_json_view.setPlainText(json.dumps(structured, indent=2, ensure_ascii=False))
        self.raw_xml_view.setPlainText(item.raw_xml)
        if item.image_bytes:
            self._display_snapshot(item)

    def _inject_verified_sample(self) -> None:
        parsed = parse_metadata_stream_xml(SAMPLE_VERIFIED_XML)
        self._on_metadata_items(parsed)

    def _export_jsonl(self) -> None:
        if not self.captured_items:
            QMessageBox.information(self, "Export JSONL", "No metadata items captured yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Captured ONVIF Profile M Metadata",
            f"onvif_profile_m_capture_{int(time.time())}.jsonl",
            "JSON Lines (*.jsonl)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            for item in self.captured_items:
                rec = {
                    "utc_time": item.utc_time,
                    "channel": item.channel,
                    "kind": item.kind,
                    "topic_or_source": item.topic_or_source,
                    "rule_or_object_id": item.rule_or_object_id,
                    "property_operation": item.property_operation,
                    "likelihood": item.likelihood,
                    "bbox": item.bbox,
                    "source_items": item.source_items,
                    "data_items": item.data_items,
                    "has_snapshot": item.image_bytes is not None,
                    "raw_xml": item.raw_xml,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.status_bar.showMessage(f"Exported {len(self.captured_items)} items to {path}", 5000)

    def _clear_feed(self) -> None:
        self.captured_items.clear()
        self.va_frame_count = 0
        self.rtsp_event_count = 0
        self.pullpoint_event_count = 0
        self.heartbeat_count = 0
        self.feed_table.setRowCount(0)
        self.parsed_json_view.clear()
        self.raw_xml_view.clear()
        self._update_counters()

    def _populate_rules_and_modules_tables(self, inv: Dict[str, Any]) -> None:
        rules = inv.get("rules", [])
        self.rules_table.setRowCount(0)
        for r in rules:
            rname = r["name"]
            rtype = r["type"]
            for pname, pval in r.get("parameters", {}).items():
                row = self.rules_table.rowCount()
                self.rules_table.insertRow(row)
                c0 = QTableWidgetItem(rname)
                c0.setFlags(c0.flags() & ~Qt.ItemFlag.ItemIsEditable)
                c1 = QTableWidgetItem(rtype)
                c1.setFlags(c1.flags() & ~Qt.ItemFlag.ItemIsEditable)
                c2 = QTableWidgetItem(pname)
                c2.setFlags(c2.flags() & ~Qt.ItemFlag.ItemIsEditable)
                c3 = QTableWidgetItem(str(pval))
                c3.setForeground(QColor("#58a6ff"))
                self.rules_table.setItem(row, 0, c0)
                self.rules_table.setItem(row, 1, c1)
                self.rules_table.setItem(row, 2, c2)
                self.rules_table.setItem(row, 3, c3)

        mods = inv.get("supported_modules", [])
        self.modules_table.setRowCount(0)
        for m in mods:
            row = self.modules_table.rowCount()
            self.modules_table.insertRow(row)
            params_str = ", ".join(f"{p['name']} ({p['type']})" for p in m.get("parameters", []))
            self.modules_table.setItem(row, 0, QTableWidgetItem(m.get("type", "")))
            self.modules_table.setItem(row, 1, QTableWidgetItem(", ".join(m.get("topics", []))))
            self.modules_table.setItem(row, 2, QTableWidgetItem(params_str or "-"))
            self.modules_table.setItem(row, 3, QTableWidgetItem(", ".join(m.get("data_simple", [])) or "-"))
            self.modules_table.setItem(row, 4, QTableWidgetItem(", ".join(m.get("data_element", [])) or "-"))

    def _refresh_rules_from_camera(self) -> None:
        if not self.client:
            return
        try:
            vac_token = self.inventory.get("vac_token", "VideoAnalyticsConfigurationToken_1")
            self.inventory["rules"] = self.client.get_rules(vac_token)
            self._populate_rules_and_modules_tables(self.inventory)
            self.status_bar.showMessage("Refreshed analytics rules from camera", 4000)
        except Exception as exc:
            QMessageBox.warning(self, "Refresh Rules Error", str(exc))

    def _apply_rules_to_camera(self) -> None:
        if not self.client:
            return
        grouped: Dict[Tuple[str, str], Dict[str, str]] = {}
        for row in range(self.rules_table.rowCount()):
            rname = self.rules_table.item(row, 0).text()
            rtype = self.rules_table.item(row, 1).text()
            pname = self.rules_table.item(row, 2).text()
            pval = self.rules_table.item(row, 3).text().strip()
            grouped.setdefault((rname, rtype), {})[pname] = pval

        vac_token = self.inventory.get("vac_token", "VideoAnalyticsConfigurationToken_1")
        try:
            for (rname, rtype), params in grouped.items():
                self.client.modify_rule(rname, rtype, params, vac_token=vac_token)
            self._refresh_rules_from_camera()
            QMessageBox.information(
                self,
                "Rules Updated",
                f"Successfully applied {len(grouped)} ONVIF Analytics rules to camera ({vac_token}).",
            )
        except Exception as exc:
            QMessageBox.warning(self, "ModifyRules Error", str(exc))

    def _populate_inventory_views(self, inv: Dict[str, Any]) -> None:
        overview = {
            "DeviceInformation": inv.get("device_info"),
            "ProfileM_Verified": inv.get("is_profile_m"),
            "ONVIF_Scopes": inv.get("scopes"),
            "Service_XAddrs": inv.get("xaddrs"),
            "Stream_Profiles": inv.get("profiles"),
            "MetadataConfiguration": inv.get("metadata_config"),
            "Active_AnalyticsModules": inv.get("active_modules"),
        }
        self.inv_overview_text.setPlainText(json.dumps(overview, indent=2, default=str, ensure_ascii=False))

        topics = inv.get("topics", [])
        self.topics_table.setRowCount(0)
        for t in topics:
            row = self.topics_table.rowCount()
            self.topics_table.insertRow(row)
            t_item = QTableWidgetItem(t["topic"])
            if "RuleEngine" in t["topic"]:
                t_item.setForeground(QColor("#00E676"))
            self.topics_table.setItem(row, 0, t_item)
            self.topics_table.setItem(row, 1, QTableWidgetItem(str(t["is_property"])))
            self.topics_table.setItem(row, 2, QTableWidgetItem(", ".join(t["source"]) or "-"))
            self.topics_table.setItem(row, 3, QTableWidgetItem(", ".join(t["data"]) or "-"))

        self.media2_xml_view.setPlainText(inv.get("media2_profiles_xml", ""))
        self.supported_meta_xml_view.setPlainText(inv.get("supported_metadata_xml", ""))

    def _on_rtsp_status(self, status: str) -> None:
        self.rtsp_status_lbl.setText(f"RTSP Metadata: {status}")

    def _on_pullpoint_status(self, status: str) -> None:
        self.pullpoint_status_lbl.setText(f"PullPoint: {status}")

    def _on_video_status(self, status: str) -> None:
        self.video_status_lbl.setText(f"Video: {status}")

    def _on_video_frame(self, img: QImage) -> None:
        self.video_canvas.set_frame(img)

    def _on_error(self, err: str) -> None:
        self.connect_btn.setEnabled(True)
        self.profile_m_badge.setText("Connection Error")
        self.status_bar.showMessage(err, 8000)

    def closeEvent(self, event: Any) -> None:
        self.disconnect_camera()
        super().closeEvent(event)

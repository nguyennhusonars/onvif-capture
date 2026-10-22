import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QItemSelection, QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
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
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..client import ONVIFProfileMClient
from ..discovery import DiscoveredCamera
from ..models import CapturedMetadataItem
from ..parsers import SAMPLE_VERIFIED_XML, parse_metadata_stream_xml
from ..workers import ONVIFPullPointWorker, RTSPMetadataStreamWorker, RTSPVideoPreviewWorker
from .canvas import VideoAnalyticsCanvas
from .gallery import EventGalleryGrid, EventSnapshotStrip
from .models import MetadataFilterProxyModel, MetadataTableModel
from .scanner_dialog import DeviceScannerDialog


class WorkerSignals(QObject):
    items_received = Signal(object)  # List[CapturedMetadataItem]
    rtsp_status = Signal(str)
    pullpoint_status = Signal(str)
    video_frame = Signal(QImage)
    video_status = Signal(str)
    inventory_ready = Signal(object)  # dict
    error_occurred = Signal(str)


class ONVIFProfileMWindow(QMainWindow):
    """Main application window for the ONVIF Profile M Native AI Analytics & Metadata Inspector."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ONVIF Profile M Inspector")
        self.resize(1560, 960)

        self.client: Optional[ONVIFProfileMClient] = None
        self.inventory: Dict[str, Any] = {}
        self.rtsp_worker: Optional[RTSPMetadataStreamWorker] = None
        self.pullpoint_worker: Optional[ONVIFPullPointWorker] = None
        self.video_worker: Optional[RTSPVideoPreviewWorker] = None

        self.captured_items: List[CapturedMetadataItem] = []
        self.alarm_event_count = 0
        self.face_detection_count = 0
        self.spatial_frame_count = 0
        self.heartbeat_count = 0
        self.snapshot_count = 0

        # Dedicated models: events_model never prunes events (max_items=0),
        # while spatial_model maintains a rolling window of 2,000 frames for 25 FPS tracking.
        self.events_model = MetadataTableModel(max_items=0, parent=self)
        self.spatial_model = MetadataTableModel(max_items=2000, parent=self)

        self.signals = WorkerSignals()
        self.signals.items_received.connect(self._on_metadata_items)
        self.signals.rtsp_status.connect(self._on_rtsp_status)
        self.signals.pullpoint_status.connect(self._on_pullpoint_status)
        self.signals.video_frame.connect(self._on_video_frame)
        self.signals.video_status.connect(self._on_video_status)
        self.signals.inventory_ready.connect(self._on_inventory_ready)
        self.signals.error_occurred.connect(self._on_error)

        self._build_ui()
        self._apply_surveillance_dark_theme()

        self._overlay_timer = QTimer(self)
        self._overlay_timer.timeout.connect(lambda: self.video_canvas.update())
        self._overlay_timer.start(100)

        QTimer.singleShot(200, self.connect_camera)

    def _apply_surveillance_dark_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #0d1117;
                color: #e6edf3;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Ubuntu', 'Helvetica Neue', sans-serif;
                font-size: 12px;
            }
            QFrame#topHeaderBar {
                background-color: #161b22;
                border: 1px solid #21262d;
                border-radius: 8px;
            }
            QGroupBox {
                border: 1px solid #21262d;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 10px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #58a6ff;
                font-size: 11px;
            }
            QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {
                background-color: #090d13;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {
                border: 1px solid #58a6ff;
            }
            QTableView, QTableWidget {
                background-color: #0d1117;
                border: 1px solid #21262d;
                border-radius: 6px;
                gridline-color: #161b22;
                selection-background-color: #1f3554;
                selection-color: #ffffff;
                alternate-background-color: #090d13;
            }
            QTableView::item, QTableWidget::item {
                padding: 4px 6px;
            }
            QTableView::item:selected, QTableWidget::item:selected {
                background-color: #1f3554;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #161b22;
                color: #8b949e;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #30363d;
                font-weight: 600;
                font-size: 11px;
            }
            QHeaderView::section:vertical {
                background-color: #0d1117;
                color: #6e7681;
                padding: 2px 6px;
                border: none;
                border-right: 1px solid #21262d;
                border-bottom: 1px solid #161b22;
                font-family: 'Monospace', monospace;
                font-size: 11px;
                min-width: 32px;
            }
            QPushButton {
                background-color: #238636;
                color: #ffffff;
                border: 1px solid rgba(240, 246, 252, 0.1);
                border-radius: 6px;
                padding: 5px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2ea043;
            }
            QPushButton:pressed {
                background-color: #1a7f37;
            }
            QPushButton#secondaryBtn {
                background-color: #21262d;
                border: 1px solid #30363d;
                color: #c9d1d9;
                font-weight: 500;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #30363d;
                border-color: #8b949e;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #21262d;
                border-radius: 8px;
                background-color: #0d1117;
            }
            QTabBar {
                background: transparent;
            }
            QTabBar::tab {
                background-color: #161b22;
                color: #8b949e;
                padding: 8px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                font-weight: 600;
                font-size: 12px;
                border: 1px solid transparent;
            }
            QTabBar::tab:hover {
                color: #c9d1d9;
                background-color: #21262d;
            }
            QTabBar::tab:selected {
                background-color: #0d1117;
                color: #58a6ff;
                border: 1px solid #21262d;
                border-bottom: 1px solid #0d1117;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background-color: #21262d;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #30363d;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                height: 0;
            }
            QScrollBar:horizontal {
                background-color: transparent;
                height: 8px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background-color: #21262d;
                min-width: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #30363d;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
                width: 0;
            }
            QSplitter::handle {
                background-color: #161b22;
            }
            QSplitter::handle:hover {
                background-color: #58a6ff;
            }
            QSplitter::handle:horizontal {
                width: 3px;
            }
            QSplitter::handle:vertical {
                height: 3px;
            }
            QStatusBar {
                background-color: #090d13;
                border-top: 1px solid #21262d;
                color: #8b949e;
                font-size: 11px;
            }
            QFrame#SnapshotCard {
                background-color: #0d1117;
                border: 1px solid #21262d;
                border-radius: 8px;
            }
            QFrame#SnapshotCard:hover {
                background-color: #161b22;
                border: 1px solid #388bfd;
            }
            """
        )

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        # 1. Top Header Bar (Collapsible Connection Controls + Live Telemetry Badges)
        self._build_top_header(root_layout)

        # 2. Main Horizontal Splitter (Left: Video + HUD + Snapshots; Right: Tabs)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(main_splitter, stretch=1)

        # Left Column: Video Analytics Canvas, HUD Controls Bar, Recent Snapshots Strip
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        video_group = QGroupBox("Live Preview and Analytics (4:3)")
        vg_layout = QVBoxLayout(video_group)
        vg_layout.setContentsMargins(4, 6, 4, 4)
        vg_layout.setSpacing(4)

        self.video_canvas = VideoAnalyticsCanvas()
        vg_layout.addWidget(self.video_canvas, stretch=1)

        # Canvas HUD Controls Bar
        hud_bar = QHBoxLayout()
        hud_bar.setContentsMargins(2, 2, 2, 2)
        hud_bar.setSpacing(6)

        # Class filter checkboxes
        self.filter_faces_cb = QCheckBox("Faces")
        self.filter_faces_cb.setChecked(True)
        self.filter_faces_cb.toggled.connect(lambda v: setattr(self.video_canvas, "show_faces", v))
        hud_bar.addWidget(self.filter_faces_cb)

        self.filter_humans_cb = QCheckBox("Humans")
        self.filter_humans_cb.setChecked(True)
        self.filter_humans_cb.toggled.connect(lambda v: setattr(self.video_canvas, "show_humans", v))
        hud_bar.addWidget(self.filter_humans_cb)

        self.filter_vehicles_cb = QCheckBox("Vehicles")
        self.filter_vehicles_cb.setChecked(True)
        self.filter_vehicles_cb.toggled.connect(lambda v: setattr(self.video_canvas, "show_vehicles", v))
        hud_bar.addWidget(self.filter_vehicles_cb)

        self.filter_labels_cb = QCheckBox("Labels")
        self.filter_labels_cb.setChecked(True)
        self.filter_labels_cb.toggled.connect(lambda v: setattr(self.video_canvas, "show_labels", v))
        hud_bar.addWidget(self.filter_labels_cb)

        hud_bar.addSpacing(6)
        hud_bar.addWidget(QLabel("TTL:"))
        self.ttl_spin = QDoubleSpinBox()
        self.ttl_spin.setRange(0.1, 5.0)
        self.ttl_spin.setSingleStep(0.1)
        self.ttl_spin.setValue(0.5)
        self.ttl_spin.setFixedWidth(55)
        self.ttl_spin.valueChanged.connect(self._on_ttl_changed)
        hud_bar.addWidget(self.ttl_spin)

        hud_bar.addStretch()

        self.freeze_btn = QPushButton("Freeze")
        self.freeze_btn.setObjectName("secondaryBtn")
        self.freeze_btn.setCheckable(True)
        self.freeze_btn.toggled.connect(self._on_toggle_freeze)
        hud_bar.addWidget(self.freeze_btn)

        self.grab_frame_btn = QPushButton("Save")
        self.grab_frame_btn.setObjectName("secondaryBtn")
        self.grab_frame_btn.clicked.connect(self._save_canvas_view)
        hud_bar.addWidget(self.grab_frame_btn)

        vg_layout.addLayout(hud_bar)
        left_layout.addWidget(video_group, stretch=3)

        # Recent Event Snapshot Strip
        self.snapshot_strip = EventSnapshotStrip(max_cards=25)
        self.snapshot_strip.snapshot_clicked.connect(self._on_snapshot_clicked)
        left_layout.addWidget(self.snapshot_strip, stretch=0)

        main_splitter.addWidget(left_widget)

        # Right Column: Disaggregated Tabbed Console
        self.tabs = QTabWidget()
        main_splitter.addWidget(self.tabs)
        main_splitter.setSizes([560, 1000])

        self._build_events_tab()
        self._build_gallery_tab()
        self._build_spatial_tab()
        self._build_rules_editor_tab()
        self._build_inventory_tab()

        # 3. Bottom Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.rtsp_status_lbl = QLabel("RTSP Metadata: Idle")
        self.pullpoint_status_lbl = QLabel("PullPoint: Idle")
        self.video_status_lbl = QLabel("Video: Idle")
        for lbl in (self.rtsp_status_lbl, self.pullpoint_status_lbl, self.video_status_lbl):
            lbl.setStyleSheet("padding: 0 8px; color: #8b949e;")
            self.status_bar.addPermanentWidget(lbl)

    def _build_top_header(self, parent_layout: QVBoxLayout) -> None:
        self.conn_group = QFrame()
        self.conn_group.setObjectName("topHeaderBar")
        conn_layout = QHBoxLayout(self.conn_group)
        conn_layout.setContentsMargins(10, 6, 10, 6)
        conn_layout.setSpacing(8)

        conn_layout.addWidget(QLabel("IP:"))
        self.ip_edit = QLineEdit("192.168.1.100")
        self.ip_edit.setPlaceholderText("IP Address")
        self.ip_edit.setFixedWidth(115)
        conn_layout.addWidget(self.ip_edit)

        conn_layout.addWidget(QLabel("Port:"))
        self.port_edit = QLineEdit("8000")
        self.port_edit.setToolTip("ONVIF HTTP port (e.g. 8000, or 8001/8002)")
        self.port_edit.setFixedWidth(48)
        conn_layout.addWidget(self.port_edit)

        conn_layout.addWidget(QLabel("RTSP:"))
        self.rtsp_port_edit = QLineEdit("554")
        self.rtsp_port_edit.setToolTip("RTSP stream port (e.g. 554, or 551/552 if forwarded)")
        self.rtsp_port_edit.setFixedWidth(45)
        conn_layout.addWidget(self.rtsp_port_edit)

        conn_layout.addWidget(QLabel("User:"))
        self.user_edit = QLineEdit("admin")
        self.user_edit.setFixedWidth(70)
        conn_layout.addWidget(self.user_edit)

        conn_layout.addWidget(QLabel("Pass:"))
        self.pass_edit = QLineEdit("")
        self.pass_edit.setPlaceholderText("Password")
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setFixedWidth(90)
        conn_layout.addWidget(self.pass_edit)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_btn)

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("secondaryBtn")
        self.scan_btn.setToolTip("Scan local network for ONVIF cameras via WS-Discovery")
        self.scan_btn.clicked.connect(self._open_scanner_dialog)
        conn_layout.addWidget(self.scan_btn)

        self.profile_m_badge = QLabel("Disconnected")
        self.profile_m_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; border: 1px solid #30363d; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 11px;"
        )
        conn_layout.addWidget(self.profile_m_badge)

        self.enable_analytics_cb = QCheckBox("Analytics")
        self.enable_analytics_cb.setChecked(True)
        self.enable_analytics_cb.clicked.connect(self._on_toggle_camera_metadata_config)
        conn_layout.addWidget(self.enable_analytics_cb)

        conn_layout.addWidget(QLabel("Stream:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(140)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        conn_layout.addWidget(self.profile_combo)

        self.video_preview_cb = QCheckBox("Preview (10 FPS)")
        self.video_preview_cb.setChecked(True)
        self.video_preview_cb.toggled.connect(self._on_toggle_video_preview)
        conn_layout.addWidget(self.video_preview_cb)

        conn_layout.addStretch()

        parent_layout.addWidget(self.conn_group)

    def _build_events_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        filter_row.addWidget(QLabel("Channel:"))
        self.event_channel_combo = QComboBox()
        self.event_channel_combo.addItems(
            [
                "All Channels",
                "ONVIF PullPoint",
                "RTSP Metadata (Event)",
            ]
        )
        self.event_channel_combo.currentIndexChanged.connect(self._on_event_filter_changed)
        filter_row.addWidget(self.event_channel_combo)

        filter_row.addWidget(QLabel("Search:"))
        self.event_search_edit = QLineEdit()
        self.event_search_edit.setPlaceholderText("Filter topic, rule, object...")
        self.event_search_edit.textChanged.connect(self._on_event_filter_changed)
        filter_row.addWidget(self.event_search_edit, stretch=1)

        self.hide_hb_cb = QCheckBox("Hide Heartbeats")
        self.hide_hb_cb.setChecked(True)
        self.hide_hb_cb.toggled.connect(self._on_event_filter_changed)
        filter_row.addWidget(self.hide_hb_cb)

        self.inject_sample_btn = QPushButton("Inject Sample")
        self.inject_sample_btn.setObjectName("secondaryBtn")
        self.inject_sample_btn.clicked.connect(self._inject_verified_sample)
        filter_row.addWidget(self.inject_sample_btn)

        self.export_btn = QPushButton("Export...")
        self.export_btn.setObjectName("secondaryBtn")
        self.export_btn.clicked.connect(self._export_jsonl)
        filter_row.addWidget(self.export_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("secondaryBtn")
        self.clear_btn.clicked.connect(self._clear_feed)
        filter_row.addWidget(self.clear_btn)

        self.events_count_badge = QLabel("0 / 0 events")
        self.events_count_badge.setStyleSheet(
            "background-color: #161b22; color: #58a6ff; border: 1px solid #21262d; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 11px; font-family: 'Monospace';"
        )
        filter_row.addWidget(self.events_count_badge)

        layout.addLayout(filter_row)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, stretch=1)

        # Virtualized Table for AI Rule & Alarm Events
        self.events_proxy = MetadataFilterProxyModel(self)
        self.events_proxy.setSourceModel(self.events_model)
        self.events_proxy.set_kind_filter("event")
        self.events_proxy.set_hide_heartbeats(True)

        self.events_table = QTableView()
        self.events_table.setModel(self.events_proxy)
        self.events_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.events_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.events_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.events_table.verticalHeader().setVisible(True)
        self.events_table.verticalHeader().setDefaultSectionSize(28)
        self.events_table.verticalHeader().setMinimumSectionSize(20)
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.events_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.events_table.selectionModel().selectionChanged.connect(self._on_event_table_row_selected)
        splitter.addWidget(self.events_table)

        # Details drawer
        detail_splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(detail_splitter)
        splitter.setSizes([460, 240])

        json_group = QGroupBox("Parsed Attributes")
        jg_layout = QVBoxLayout(json_group)
        self.parsed_json_view = QPlainTextEdit()
        self.parsed_json_view.setReadOnly(True)
        self.parsed_json_view.setFont(QFont("Monospace", 10))
        jg_layout.addWidget(self.parsed_json_view)
        detail_splitter.addWidget(json_group)

        xml_group = QGroupBox("Raw XML")
        xg_layout = QVBoxLayout(xml_group)
        self.raw_xml_view = QPlainTextEdit()
        self.raw_xml_view.setReadOnly(True)
        self.raw_xml_view.setFont(QFont("Monospace", 10))
        xg_layout.addWidget(self.raw_xml_view)
        detail_splitter.addWidget(xml_group)

        self.tabs.addTab(tab, "AI Events (0)")

    def _build_gallery_tab(self) -> None:
        self.gallery_grid = EventGalleryGrid()
        self.gallery_grid.snapshot_selected.connect(self._on_snapshot_clicked)
        self.tabs.addTab(self.gallery_grid, "Capture Wall (0)")

    def _build_spatial_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Search:"))
        self.spatial_search_edit = QLineEdit()
        self.spatial_search_edit.setPlaceholderText("Filter ID, class, likelihood...")
        self.spatial_search_edit.textChanged.connect(self._on_spatial_filter_changed)
        filter_row.addWidget(self.spatial_search_edit, stretch=1)

        self.spatial_pause_cb = QCheckBox("Pause Table")
        filter_row.addWidget(self.spatial_pause_cb)

        self.spatial_clear_btn = QPushButton("Clear")
        self.spatial_clear_btn.setObjectName("secondaryBtn")
        self.spatial_clear_btn.clicked.connect(self._clear_spatial_feed)
        filter_row.addWidget(self.spatial_clear_btn)

        self.spatial_count_badge = QLabel("0 / 0 frames")
        self.spatial_count_badge.setStyleSheet(
            "background-color: #161b22; color: #00E676; border: 1px solid #21262d; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 11px; font-family: 'Monospace';"
        )
        filter_row.addWidget(self.spatial_count_badge)

        layout.addLayout(filter_row)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, stretch=1)

        self.spatial_proxy = MetadataFilterProxyModel(self)
        self.spatial_proxy.setSourceModel(self.spatial_model)
        self.spatial_proxy.set_kind_filter("object_frame")
        self.spatial_proxy.set_hide_heartbeats(False)

        self.spatial_table = QTableView()
        self.spatial_table.setModel(self.spatial_proxy)
        self.spatial_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.spatial_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.spatial_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.spatial_table.verticalHeader().setVisible(True)
        self.spatial_table.verticalHeader().setDefaultSectionSize(28)
        self.spatial_table.verticalHeader().setMinimumSectionSize(20)
        self.spatial_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.spatial_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.spatial_table.selectionModel().selectionChanged.connect(self._on_spatial_table_row_selected)
        splitter.addWidget(self.spatial_table)

        # Dedicated Details drawer for Spatial Tab
        detail_splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(detail_splitter)
        splitter.setSizes([460, 240])

        json_group = QGroupBox("Parsed Attributes")
        jg_layout = QVBoxLayout(json_group)
        self.spatial_json_view = QPlainTextEdit()
        self.spatial_json_view.setReadOnly(True)
        self.spatial_json_view.setFont(QFont("Monospace", 10))
        jg_layout.addWidget(self.spatial_json_view)
        detail_splitter.addWidget(json_group)

        xml_group = QGroupBox("Raw XML")
        xg_layout = QVBoxLayout(xml_group)
        self.spatial_xml_view = QPlainTextEdit()
        self.spatial_xml_view.setReadOnly(True)
        self.spatial_xml_view.setFont(QFont("Monospace", 10))
        xg_layout.addWidget(self.spatial_xml_view)
        detail_splitter.addWidget(xml_group)

        self.tabs.addTab(tab, "Spatial Tracking (0)")

    def _build_rules_editor_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_bar = QHBoxLayout()
        top_bar.addWidget(
            QLabel("Rules and Thresholds (`tan:ModifyRules`):")
        )
        top_bar.addStretch()
        refresh_rules_btn = QPushButton("Refresh Rules")
        refresh_rules_btn.setObjectName("secondaryBtn")
        refresh_rules_btn.clicked.connect(self._refresh_rules_from_camera)
        top_bar.addWidget(refresh_rules_btn)

        apply_all_btn = QPushButton("Apply Rules")
        apply_all_btn.clicked.connect(self._apply_rules_to_camera)
        top_bar.addWidget(apply_all_btn)
        layout.addLayout(top_bar)

        rules_group = QGroupBox("Active Rules (Double-click to edit)")
        rg_layout = QVBoxLayout(rules_group)
        self.rules_table = QTableWidget(0, 4)
        self.rules_table.setHorizontalHeaderLabels(
            ["Rule Name", "Rule Type (ONVIF)", "Parameter Name", "Parameter Value (Editable)"]
        )
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        rg_layout.addWidget(self.rules_table)
        layout.addWidget(rules_group, stretch=3)

        mods_group = QGroupBox("Supported Modules and Event Schemas")
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

        self.tabs.addTab(tab, "Rules and Modules")

    def _build_inventory_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        sub_tabs = QTabWidget()
        layout.addWidget(sub_tabs)

        self.inv_overview_text = QPlainTextEdit()
        self.inv_overview_text.setReadOnly(True)
        self.inv_overview_text.setFont(QFont("Monospace", 10))
        sub_tabs.addTab(self.inv_overview_text, "Configuration")

        self.topics_table = QTableWidget(0, 4)
        self.topics_table.setHorizontalHeaderLabels(
            ["ONVIF Topic (TopicSet)", "IsProperty", "Source Items", "Data Items"]
        )
        self.topics_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.topics_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.topics_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.topics_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        sub_tabs.addTab(self.topics_table, "Event Topics")

        self.media2_xml_view = QPlainTextEdit()
        self.media2_xml_view.setReadOnly(True)
        self.media2_xml_view.setFont(QFont("Monospace", 10))
        sub_tabs.addTab(self.media2_xml_view, "Media2 Profiles")

        self.supported_meta_xml_view = QPlainTextEdit()
        self.supported_meta_xml_view.setReadOnly(True)
        self.supported_meta_xml_view.setFont(QFont("Monospace", 10))
        sub_tabs.addTab(self.supported_meta_xml_view, "Metadata Schemas")

        self.tabs.addTab(tab, "Device Inventory")

    def _open_scanner_dialog(self) -> None:
        dlg = DeviceScannerDialog(self)
        dlg.camera_selected.connect(self._on_scanner_camera_selected)
        dlg.exec()

    def _on_scanner_camera_selected(self, cam: DiscoveredCamera) -> None:
        if self.rtsp_worker or self.pullpoint_worker:
            self.disconnect_camera()
        self.ip_edit.setText(cam.ip)
        self.port_edit.setText(str(cam.port))
        self.rtsp_port_edit.setText("554")
        self.connect_camera()

    def toggle_connection(self) -> None:
        if self.rtsp_worker or self.pullpoint_worker:
            self.disconnect_camera()
        else:
            self.connect_camera()

    def connect_camera(self) -> None:
        host = self.ip_edit.text().strip()
        port = int(self.port_edit.text().strip() or "8000")
        rtsp_port_str = self.rtsp_port_edit.text().strip()
        rtsp_port = int(rtsp_port_str) if rtsp_port_str else None
        user = self.user_edit.text().strip()
        pwd = self.pass_edit.text()

        self.connect_btn.setEnabled(False)
        self.profile_m_badge.setText("Connecting...")

        def _connect_task() -> None:
            try:
                client = ONVIFProfileMClient(host, port, user, pwd, rtsp_port=rtsp_port)
                inv = client.connect()
                if self.enable_analytics_cb.isChecked() and (
                    not inv["analytics_enabled"] or not inv["events_enabled"]
                ):
                    try:
                        updated_mc = client.set_metadata_analytics_enabled(True, True)
                        inv["metadata_config"] = updated_mc
                        inv["analytics_enabled"] = True
                        inv["events_enabled"] = True
                    except Exception as mc_err:
                        print(f"[WARN] Could not auto-enable MetadataConfiguration: {mc_err}", flush=True)
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
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Connect")
        self.connect_btn.setStyleSheet("background-color: #238636; color: #ffffff; border-radius: 6px; font-weight: 600; padding: 5px 14px;")
        self.profile_m_badge.setText("Disconnected")
        self.profile_m_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; border: 1px solid #30363d; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 11px;"
        )
        self.rtsp_status_lbl.setText("RTSP Metadata: Stopped")
        self.pullpoint_status_lbl.setText("PullPoint: Stopped")
        self.video_status_lbl.setText("Video: Stopped")

    def _on_inventory_ready(self, inv: Dict[str, Any]) -> None:
        self.inventory = inv
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setStyleSheet("background-color: #da3633; color: #ffffff; border-radius: 6px; font-weight: 600; padding: 5px 14px;")

        dev = inv.get("device_info", {})
        model_str = f"{dev.get('Manufacturer', '')} {dev.get('Model', '')}".strip()
        if inv.get("is_profile_m"):
            self.profile_m_badge.setText(f"Profile M Verified ({model_str})")
            self.profile_m_badge.setStyleSheet(
                "background-color: #1f6feb; color: #ffffff; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 11px;"
            )
        else:
            self.profile_m_badge.setText(f"Connected ({model_str})")
            self.profile_m_badge.setStyleSheet(
                "background-color: #238636; color: #ffffff; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 11px;"
            )

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

    def _on_toggle_freeze(self, checked: bool) -> None:
        self.video_canvas.set_frozen(checked)
        if checked:
            self.freeze_btn.setText("Resume")
            self.freeze_btn.setStyleSheet("background-color: #da3633; color: #ffffff;")
        else:
            self.freeze_btn.setText("Freeze")
            self.freeze_btn.setStyleSheet("")

    def _save_canvas_view(self) -> None:
        annotated = self.video_canvas.grab_annotated_frame()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Annotated Canvas Frame",
            f"onvif_view_{int(time.time())}.jpg",
            "JPEG (*.jpg *.jpeg);;PNG (*.png)",
        )
        if path:
            annotated.save(path)
            self.status_bar.showMessage(f"Saved annotated canvas view to {path}", 5000)

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
        events_to_add: List[CapturedMetadataItem] = []
        spatial_to_add: List[CapturedMetadataItem] = []
        wall_items: List[CapturedMetadataItem] = []

        for item in items:
            self.captured_items.append(item)

            is_hb = (item.property_operation or "").strip().lower() == "initialized"

            if is_hb:
                self.heartbeat_count += 1

            if item.kind == "object_frame":
                self.spatial_frame_count += 1
                spatial_to_add.append(item)
            elif item.kind == "event":
                if not is_hb:
                    self.alarm_event_count += 1
                    if "face" in item.topic_or_source.lower() or "face" in item.rule_or_object_id.lower():
                        self.face_detection_count += 1

                events_to_add.append(item)

            # Route active alarm events (only from RTSP stream, excluding PullPoint) to Capture Wall
            if not is_hb and item.kind == "event" and "RTSP" in item.channel:
                state_val = str(item.data_items.get("State", "")).strip().lower()
                # Only add active triggers or items with images/objects to the capture wall
                if state_val != "false" or item.image_bytes is not None or item.objects:
                    if item.image_bytes:
                        self.snapshot_count += 1
                    wall_items.append(item)

        # Batch update canvas telemetry and overlays
        self.video_canvas.add_metadata_items(items)

        # Batch update Capture Wall and Recent Strip
        if wall_items:
            self.snapshot_strip.add_items(wall_items)
            self.gallery_grid.add_items(wall_items)

        # Batch add to dedicated models
        if events_to_add:
            self.events_model.add_items(events_to_add)
        if spatial_to_add and not self.spatial_pause_cb.isChecked():
            self.spatial_model.add_items(spatial_to_add)

        self._update_counters()

    def _update_counters(self) -> None:
        ev_shown = self.events_proxy.rowCount()
        ev_total = self.events_model.rowCount()
        if hasattr(self, "events_count_badge"):
            self.events_count_badge.setText(f"{ev_shown} / {ev_total} events")
        self.tabs.setTabText(0, f"AI Events ({ev_shown})")
        self.tabs.setTabText(1, f"Capture Wall ({self.gallery_grid.count()})")

        sp_shown = self.spatial_proxy.rowCount()
        sp_total = self.spatial_model.rowCount()
        if hasattr(self, "spatial_count_badge"):
            self.spatial_count_badge.setText(f"{sp_shown} / {sp_total} frames")
        self.tabs.setTabText(2, f"Spatial Tracking ({sp_shown})")

    def _on_event_filter_changed(self) -> None:
        ch = self.event_channel_combo.currentText()
        self.events_proxy.set_channel_filter(ch)
        self.events_proxy.set_hide_heartbeats(self.hide_hb_cb.isChecked())
        self.events_proxy.set_search_query(self.event_search_edit.text())
        self._update_counters()

    def _on_spatial_filter_changed(self) -> None:
        self.spatial_proxy.set_search_query(self.spatial_search_edit.text())
        self._update_counters()

    def _on_snapshot_clicked(self, item: CapturedMetadataItem) -> None:
        self._display_event_details(item)

    def _on_event_table_row_selected(self, selected: QItemSelection, _deselected: QItemSelection) -> None:
        indexes = selected.indexes()
        if not indexes:
            return
        proxy_idx = indexes[0]
        source_idx = self.events_proxy.mapToSource(proxy_idx)
        item = self.events_model.get_item(source_idx.row())
        if item:
            self._display_event_details(item)

    def _on_spatial_table_row_selected(self, selected: QItemSelection, _deselected: QItemSelection) -> None:
        indexes = selected.indexes()
        if not indexes:
            return
        proxy_idx = indexes[0]
        source_idx = self.spatial_proxy.mapToSource(proxy_idx)
        item = self.spatial_model.get_item(source_idx.row())
        if item:
            self._display_spatial_details(item)

    def _format_item_json(self, item: CapturedMetadataItem) -> str:
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
            "has_embedded_image": item.image_bytes is not None,
            "has_biometric_template": item.template_bytes is not None,
        }
        return json.dumps(structured, indent=2, ensure_ascii=False)

    def _display_event_details(self, item: CapturedMetadataItem) -> None:
        self.parsed_json_view.setPlainText(self._format_item_json(item))
        self.raw_xml_view.setPlainText(item.raw_xml)

    def _display_spatial_details(self, item: CapturedMetadataItem) -> None:
        self.spatial_json_view.setPlainText(self._format_item_json(item))
        self.spatial_xml_view.setPlainText(item.raw_xml)

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
                    "has_template": item.template_bytes is not None,
                    "raw_xml": item.raw_xml,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.status_bar.showMessage(f"Exported {len(self.captured_items)} items to {path}", 5000)

    def _clear_spatial_feed(self) -> None:
        self.spatial_model.clear()
        self.spatial_frame_count = 0
        if hasattr(self, "spatial_json_view"):
            self.spatial_json_view.clear()
        if hasattr(self, "spatial_xml_view"):
            self.spatial_xml_view.clear()
        self._update_counters()

    def _clear_feed(self) -> None:
        self.captured_items.clear()
        self.events_model.clear()
        self.spatial_model.clear()
        self.snapshot_strip.clear()
        self.gallery_grid.clear()
        self.alarm_event_count = 0
        self.face_detection_count = 0
        self.spatial_frame_count = 0
        self.heartbeat_count = 0
        self.snapshot_count = 0
        self.parsed_json_view.clear()
        self.raw_xml_view.clear()
        if hasattr(self, "spatial_json_view"):
            self.spatial_json_view.clear()
        if hasattr(self, "spatial_xml_view"):
            self.spatial_xml_view.clear()
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
        self.profile_m_badge.setStyleSheet(
            "background-color: #21262d; color: #f85149; border: 1px solid #f85149; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 11px;"
        )
        self.profile_m_badge.setToolTip(err)
        self.status_bar.showMessage(err, 15000)
        print(f"[ONVIF Error] {err}", flush=True)

    def closeEvent(self, event: Any) -> None:
        self.disconnect_camera()
        super().closeEvent(event)

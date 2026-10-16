"""Device Scanner Dialog for discovering ONVIF cameras on the local network via native WS-Discovery."""

import ipaddress
from typing import Any, Dict, Optional
from PySide6.QtCore import QThread, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..discovery import DiscoveredCamera, ws_discovery_scan


class IPTableWidgetItem(QTableWidgetItem):
    """Sorts IPv4/IPv6 addresses by their numerical integer value instead of lexicographically."""

    def __lt__(self, other: Any) -> bool:
        try:
            return ipaddress.ip_address(self.text().strip()) < ipaddress.ip_address(other.text().strip())
        except Exception:
            return super().__lt__(other)


class NumericTableWidgetItem(QTableWidgetItem):
    """Sorts integer values (e.g. port numbers) numerically."""

    def __lt__(self, other: Any) -> bool:
        try:
            return int(self.text().strip()) < int(other.text().strip())
        except Exception:
            return super().__lt__(other)


class DiscoveryWorker(QThread):
    """Background worker executing WS-Discovery UDP multicast probes."""

    camera_found = Signal(object)  # DiscoveredCamera
    scan_finished = Signal(int)  # total count
    scan_error = Signal(str)

    def __init__(self, timeout: float = 4.0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.timeout = timeout
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            cameras = ws_discovery_scan(
                timeout=self.timeout,
                on_camera_found=lambda cam: self.camera_found.emit(cam),
                stop_check=lambda: self._stop_requested,
            )
            self.scan_finished.emit(len(cameras))
        except Exception as exc:
            self.scan_error.emit(str(exc))


class DeviceScannerDialog(QDialog):
    """Modern modal dialog displaying live ONVIF camera discovery results."""

    camera_selected = Signal(object)  # DiscoveredCamera

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Discover ONVIF Cameras")
        self.resize(880, 500)
        self.setMinimumSize(760, 380)

        self.discovered_cameras: Dict[str, DiscoveredCamera] = {}
        self._selected_cam: Optional[DiscoveredCamera] = None
        self._worker: Optional[DiscoveryWorker] = None
        self._scan_duration: float = 4.0
        self._elapsed_time: float = 0.0

        self._build_ui()
        self._start_scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header bar: search filter + rescan + status
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by IP, model, name...")
        self.search_edit.textChanged.connect(self._refilter_table)
        top_bar.addWidget(self.search_edit, stretch=1)

        self.rescan_btn = QPushButton("Rescan")
        self.rescan_btn.setObjectName("secondaryBtn")
        self.rescan_btn.clicked.connect(self._start_scan)
        top_bar.addWidget(self.rescan_btn)

        layout.addLayout(top_bar)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: none; background-color: #161b22; border-radius: 2px; } "
            "QProgressBar::chunk { background-color: #1f6feb; border-radius: 2px; }"
        )
        layout.addWidget(self.progress_bar)

        # Table of discovered cameras
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["IP Address", "Port", "Model / Name", "ONVIF Profiles", "Device Service Endpoint"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 55)
        self.table.setColumnWidth(3, 135)
        self.table.setColumnWidth(4, 220)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, stretch=1)

        # Bottom row: Count badge + action buttons
        bot_bar = QHBoxLayout()
        bot_bar.setSpacing(8)

        self.status_lbl = QLabel("Scanning network...")
        self.status_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        bot_bar.addWidget(self.status_lbl)

        self.count_badge = QLabel("0 cameras found")
        self.count_badge.setStyleSheet(
            "background-color: #161b22; color: #58a6ff; border: 1px solid #21262d; border-radius: 12px; padding: 3px 10px; font-weight: 600; font-size: 11px;"
        )
        bot_bar.addWidget(self.count_badge)

        bot_bar.addStretch()

        self.connect_btn = QPushButton("Select and Connect")
        self.connect_btn.setEnabled(False)
        self.connect_btn.setStyleSheet(
            "background-color: #238636; color: #ffffff; border-radius: 6px; font-weight: 600; padding: 6px 16px;"
        )
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        bot_bar.addWidget(self.connect_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("secondaryBtn")
        self.close_btn.clicked.connect(self.reject)
        bot_bar.addWidget(self.close_btn)

        layout.addLayout(bot_bar)

        # Animation timer for progress bar
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._update_progress)

    def _start_scan(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(500)

        self.discovered_cameras.clear()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.connect_btn.setEnabled(False)
        self._selected_cam = None
        self.rescan_btn.setEnabled(False)
        self.status_lbl.setText("Broadcasting WS-Discovery probe across local network...")
        self.count_badge.setText("0 cameras found")

        self._elapsed_time = 0.0
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self._timer.start()

        self._worker = DiscoveryWorker(timeout=self._scan_duration, parent=self)
        self._worker.camera_found.connect(self._on_camera_found)
        self._worker.scan_finished.connect(self._on_scan_finished)
        self._worker.scan_error.connect(self._on_scan_error)
        self._worker.start()

    def _update_progress(self) -> None:
        self._elapsed_time += 0.05
        pct = int(min(100.0, (self._elapsed_time / self._scan_duration) * 100))
        self.progress_bar.setValue(pct)
        if self._elapsed_time >= self._scan_duration:
            self._timer.stop()

    def _on_camera_found(self, cam: DiscoveredCamera) -> None:
        key = f"{cam.ip}:{cam.port}"
        if key in self.discovered_cameras:
            return
        self.discovered_cameras[key] = cam

        self._add_camera_row(cam)
        n = len(self.discovered_cameras)
        self.count_badge.setText(f"{n} camera{'s' if n != 1 else ''} found")
        self.status_lbl.setText(f"Found {cam.ip} ({cam.display_name})")

    def _add_camera_row(self, cam: DiscoveredCamera) -> None:
        sorting_was_enabled = self.table.isSortingEnabled()
        if sorting_was_enabled:
            self.table.setSortingEnabled(False)

        row = self.table.rowCount()
        self.table.insertRow(row)

        c0 = IPTableWidgetItem(cam.ip)
        c0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        c0.setData(Qt.ItemDataRole.UserRole, cam)

        c1 = NumericTableWidgetItem(str(cam.port))
        c1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        c2 = QTableWidgetItem(cam.display_name)
        c2.setToolTip(cam.display_name)
        if cam.has_profile_m:
            c2.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

        profiles_str = cam.profile_summary
        c3 = QTableWidgetItem(profiles_str)
        c3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if cam.has_profile_m:
            c3.setForeground(QColor("#00E676"))  # Green highlight for Profile M support
            c3.setToolTip(f"Camera supports ONVIF Profile M (AI Metadata and Analytics)\nProfiles: {cam.profile_summary}")
        else:
            c3.setToolTip(f"Profiles: {cam.profile_summary}")

        xaddr_str = cam.xaddrs[0] if cam.xaddrs else "-"
        c4 = QTableWidgetItem(xaddr_str)
        c4.setToolTip(xaddr_str)
        c4.setForeground(QColor("#8b949e"))
        c4.setFont(QFont("Monospace", 8))

        self.table.setItem(row, 0, c0)
        self.table.setItem(row, 1, c1)
        self.table.setItem(row, 2, c2)
        self.table.setItem(row, 3, c3)
        self.table.setItem(row, 4, c4)

        self.table.setSortingEnabled(True)

        # Auto-sort by active header indicator (default Column 0: IP Address ascending)
        sort_col = self.table.horizontalHeader().sortIndicatorSection()
        sort_order = self.table.horizontalHeader().sortIndicatorOrder()
        if sort_col < 0:
            sort_col = 0
            sort_order = Qt.SortOrder.AscendingOrder
        self.table.sortItems(sort_col, sort_order)

        # Apply search filter visibility
        if self.search_edit.text().strip():
            self._refilter_table()

    def _refilter_table(self) -> None:
        query = self.search_edit.text().strip().lower()
        for row in range(self.table.rowCount()):
            c0 = self.table.item(row, 0)
            if not c0:
                continue
            cam: DiscoveredCamera = c0.data(Qt.ItemDataRole.UserRole)
            if not query:
                self.table.setRowHidden(row, False)
            else:
                haystack = f"{cam.ip} {cam.port} {cam.display_name} {cam.profile_summary} {cam.xaddrs}".lower()
                self.table.setRowHidden(row, query not in haystack)

    def _on_selection_changed(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            c0 = self.table.item(row, 0)
            if c0:
                self._selected_cam = c0.data(Qt.ItemDataRole.UserRole)
                self.connect_btn.setEnabled(True)
                return
        self._selected_cam = None
        self.connect_btn.setEnabled(False)

    def _on_row_double_clicked(self, _item: QTableWidgetItem) -> None:
        self._on_connect_clicked()

    def _on_connect_clicked(self) -> None:
        if self._selected_cam:
            self._stop_and_cleanup()
            self.camera_selected.emit(self._selected_cam)
            self.accept()

    def _on_scan_finished(self, total: int) -> None:
        self._timer.stop()
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.rescan_btn.setEnabled(True)
        self.table.setSortingEnabled(True)
        self.status_lbl.setText(f"Scan complete. {total} camera{'s' if total != 1 else ''} discovered.")

    def _on_scan_error(self, err: str) -> None:
        self._timer.stop()
        self.progress_bar.setVisible(False)
        self.rescan_btn.setEnabled(True)
        self.table.setSortingEnabled(True)
        self.status_lbl.setText(f"Scan error: {err}")

    def _stop_and_cleanup(self) -> None:
        self._timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(500)
            self._worker = None

    def selected_camera(self) -> Optional[DiscoveredCamera]:
        return self._selected_cam

    def closeEvent(self, event: Any) -> None:
        self._stop_and_cleanup()
        super().closeEvent(event)

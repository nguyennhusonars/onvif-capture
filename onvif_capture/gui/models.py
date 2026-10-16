from typing import Any, List, Optional
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from ..models import CapturedMetadataItem

COLUMNS = [
    "UTC Time",
    "Channel",
    "Topic / Source",
    "Rule / Object ID",
    "Likelihood",
    "Summary",
    "Snapshot",
]


class MetadataTableModel(QAbstractTableModel):
    """High-performance virtualized table model for captured ONVIF Profile M metadata items."""

    def __init__(self, max_items: int = 5000, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.max_items = max_items
        self._items: List[CapturedMetadataItem] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._items):
            return None

        item = self._items[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return item.utc_time or "-"
            if col == 1:
                return item.channel
            if col == 2:
                return item.topic_or_source
            if col == 3:
                return item.rule_or_object_id
            if col == 4:
                return f"{item.likelihood:.2f}" if item.likelihood is not None else "-"
            if col == 5:
                return item.summary
            if col == 6:
                return f"{len(item.image_bytes) // 1024} KB" if item.image_bytes else "-"

        elif role == Qt.ItemDataRole.ForegroundRole:
            if item.kind == "object_frame":
                return QColor("#00E676")  # Green for continuous tracking
            if "face" in item.topic_or_source.lower() or "face" in item.rule_or_object_id.lower():
                return QColor("#a371f7")  # Purple for faces
            if item.image_bytes:
                return QColor("#FFA657")  # Amber for snapshot events
            if (item.property_operation or "").strip().lower() == "initialized":
                return QColor("#8b949e")  # Muted gray for heartbeat
            if item.kind == "event":
                return QColor("#58a6ff")  # Light blue for general events

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1, 4, 6):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        elif role == Qt.ItemDataRole.UserRole:
            # Return full item reference
            return item

        return None

    def add_items(self, new_items: List[CapturedMetadataItem]) -> None:
        if not new_items:
            return

        # If adding exceeds max_items, prune oldest from the end (only if max_items is positive)
        if self.max_items and self.max_items > 0:
            if len(new_items) > self.max_items:
                new_items = new_items[-self.max_items :]
            total = len(self._items) + len(new_items)
            if total > self.max_items:
                excess = total - self.max_items
                prune_count = min(excess, len(self._items))
                if prune_count > 0:
                    first_remove = len(self._items) - prune_count
                    last_remove = len(self._items) - 1
                    self.beginRemoveRows(QModelIndex(), first_remove, last_remove)
                    del self._items[first_remove:]
                    self.endRemoveRows()

        # Insert newest at top (row 0). Since incoming new_items are chronological
        # (earliest to latest), reverse so the latest item becomes row 0.
        items_to_insert = list(reversed(new_items))
        start_row = 0
        end_row = len(items_to_insert) - 1
        self.beginInsertRows(QModelIndex(), start_row, end_row)
        self._items[:0] = items_to_insert
        self.endInsertRows()

    def clear(self) -> None:
        if not self._items:
            return
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[CapturedMetadataItem]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def all_items(self) -> List[CapturedMetadataItem]:
        return list(self._items)


class MetadataFilterProxyModel(QSortFilterProxyModel):
    """Custom filter proxy model supporting channel, event kind, and freeform text search."""

    def __init__(self, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._channel_filter: str = "All Channels"
        self._kind_filter: Optional[str] = None  # None, "event", or "object_frame"
        self._hide_heartbeats: bool = True
        self._search_query: str = ""

    def set_channel_filter(self, channel: str) -> None:
        self._channel_filter = channel
        self.invalidateFilter()

    def set_kind_filter(self, kind: Optional[str]) -> None:
        self._kind_filter = kind
        self.invalidateFilter()

    def set_hide_heartbeats(self, hide: bool) -> None:
        self._hide_heartbeats = hide
        self.invalidateFilter()

    def set_search_query(self, query: str) -> None:
        self._search_query = query.strip().lower()
        self.invalidateFilter()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return super().headerData(section, orientation, role)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, MetadataTableModel):
            return True

        item = model.get_item(source_row)
        if not item:
            return False

        if self._hide_heartbeats and (item.property_operation or "").strip().lower() == "initialized":
            return False

        if self._kind_filter is not None and item.kind != self._kind_filter:
            return False

        if self._channel_filter == "All Events (PullPoint + RTSP)":
            if item.kind != "event":
                return False
        elif self._channel_filter != "All Channels" and item.channel != self._channel_filter:
            return False

        if self._search_query:
            haystack = f"{item.topic_or_source} {item.rule_or_object_id} {item.summary}".lower()
            if self._search_query not in haystack:
                return False

        return True


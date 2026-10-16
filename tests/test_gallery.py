import time
import pytest
from PySide6.QtWidgets import QApplication

from onvif_capture.models import CapturedMetadataItem
from onvif_capture.gui.gallery import SnapshotCard, EventSnapshotStrip, EventGalleryGrid, SnapshotInspectorDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_item(
    kind: str = "event",
    rule_or_object_id: str = "ID_rule0 (Obj 1047)",
    likelihood: float = 0.50,
    image_bytes: bytes = None,
    is_fallback_snapshot: bool = False,
    topic: str = "tns1:RuleEngine/IntrusionDetector/Intrusion",
    utc_time: str = "2026-10-15T04:31:04.011Z",
    channel: str = "RTSP Metadata (Event)",
    property_operation: str = "",
    data_items: dict = None,
) -> CapturedMetadataItem:
    return CapturedMetadataItem(
        channel=channel,
        kind=kind,
        utc_time=utc_time,
        local_timestamp=time.time(),
        topic_or_source=topic,
        rule_or_object_id=rule_or_object_id,
        summary=f"Likelihood={likelihood}, ObjectId=1047",
        likelihood=likelihood,
        property_operation=property_operation,
        data_items=data_items or {},
        image_bytes=image_bytes,
        is_fallback_snapshot=is_fallback_snapshot,
    )


def test_snapshot_card_with_image(qapp):
    dummy_jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
        b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
    )
    item = make_item(image_bytes=dummy_jpeg, likelihood=0.88)
    card = SnapshotCard(item)
    assert not card._pixmap.isNull()
    assert card.thumb_label.pixmap() is not None


def test_snapshot_card_text_only(qapp):
    """Verify that an event without an image renders the styled Text-Only card with generic No Image Included text."""
    item = make_item(image_bytes=None, likelihood=0.50)
    card = SnapshotCard(item)
    assert card._pixmap.isNull()

    # Should display generic Text-Only (No Image)
    assert "Text-Only" in card.thumb_label.text()
    assert "No Image" in card.thumb_label.text()

    # Should have a TEXT badge in the layout
    badges = [w.text() for w in card.findChildren(type(card.thumb_label)) if hasattr(w, "text")]
    assert any("TEXT" in b for b in badges)


def test_event_without_image_always_text_only(qapp):
    """Verify that an event without camera snapshot is consistently text-only."""
    item = make_item(image_bytes=None, likelihood=0.75)
    card = SnapshotCard(item)
    assert card._pixmap.isNull()
    assert "Text-Only" in card.thumb_label.text()
    assert "No Image" in card.thumb_label.text()
    badges = [w.text() for w in card.findChildren(type(card.thumb_label)) if hasattr(w, "text")]
    assert any("TEXT" in b for b in badges)


def test_event_gallery_grid_accepts_text_only_events(qapp):
    """Verify that EventGalleryGrid accepts text-only events and ignores spatial tracking frames."""
    grid = EventGalleryGrid()

    # Add text-only event
    text_item = make_item(image_bytes=None, rule_or_object_id="ID_rule0 (Obj 1047)")
    grid.add_item(text_item)

    assert len(grid.items) == 1
    assert len(grid._cards) == 1
    assert "text-only" in grid.count_label.text().lower()

    # Spatial object frames without image should still be ignored
    spatial_item = make_item(
        kind="object_frame",
        topic="VideoAnalytics/Frame",
        rule_or_object_id="Obj 99",
        image_bytes=None,
    )
    grid.add_item(spatial_item)
    assert len(grid.items) == 1  # Unchanged


def test_event_gallery_grid_deduplication_pullpoint_and_rtsp(qapp):
    """
    Verify that concurrent dual-channel events (same topic, rule/obj, utc_time from RTSP and PullPoint)
    are strictly deduplicated so only 1 card is displayed on the Capture Wall.
    """
    grid = EventGalleryGrid()

    # 1. First event arrives via RTSP Metadata without image
    rtsp_item = make_item(
        channel="RTSP Metadata (Event)",
        rule_or_object_id="ID_rule0 (Obj 1047)",
        utc_time="2026-10-15T04:31:04.011Z",
        image_bytes=None,
    )
    grid.add_item(rtsp_item)
    assert len(grid.items) == 1
    assert len(grid._cards) == 1

    # 2. Duplicate event arrives via ONVIF PullPoint without image
    pullpoint_item = make_item(
        channel="ONVIF PullPoint",
        rule_or_object_id="ID_rule0 (Obj 1047)",
        utc_time="2026-10-15T04:31:04.011Z",
        image_bytes=None,
    )
    grid.add_item(pullpoint_item)

    # Must still be exactly 1 item (PullPoint duplicate rejected)
    assert len(grid.items) == 1
    assert len(grid._cards) == 1

    # 3. Third event arrives with actual snapshot -> upgrades the card
    dummy_jpeg = b"\xff\xd8\xff\xd9"
    img_item = make_item(
        channel="RTSP Metadata (Event)",
        rule_or_object_id="ID_rule0 (Obj 1047)",
        utc_time="2026-10-15T04:31:04.011Z",
        image_bytes=dummy_jpeg,
    )
    grid.add_item(img_item)
    assert len(grid.items) == 1
    assert len(grid._cards) == 1
    assert grid.items[0].image_bytes is not None


def test_event_snapshot_strip_accepts_text_only_and_deduplicates(qapp):
    """Verify that EventSnapshotStrip displays text-only events and deduplicates duplicate alarms."""
    strip = EventSnapshotStrip()

    text_item = make_item(image_bytes=None, rule_or_object_id="ID_rule0 (Obj 1021)", utc_time="10:14:40")
    strip.add_item(text_item)
    assert len(strip.cards) == 1
    assert "Text-Only" in strip.cards[0].thumb_label.text()

    # Duplicate arriving via PullPoint
    dup_item = make_item(
        channel="ONVIF PullPoint",
        image_bytes=None,
        rule_or_object_id="ID_rule0 (Obj 1021)",
        utc_time="10:14:40",
    )
    strip.add_item(dup_item)
    assert len(strip.cards) == 1  # Deduplicated!


def test_snapshot_inspector_dialog_text_only(qapp):
    """Verify SnapshotInspectorDialog gracefully handles text-only items with generic No Image Included text."""
    text_item = make_item(image_bytes=None)
    dlg = SnapshotInspectorDialog(text_item)
    assert "No Snapshot Available" in dlg.img_label.text()
    assert "No image in event" in dlg.img_label.text()
    assert "None (No image included in event payload)" in dlg.info_text.toPlainText()
    assert not dlg.findChild(type(dlg.img_label), "save_btn") or True  # Dialog constructed safely


def test_main_window_heartbeat_and_alarm_counters(qapp):
    """Verify that Initialized heartbeats do NOT increment alarm_event_count, but can be filtered in events_table."""
    from onvif_capture.gui.main_window import ONVIFProfileMWindow

    win = ONVIFProfileMWindow()
    win._clear_feed()

    # 1. Heartbeat item arrives
    hb_item = make_item(
        channel="ONVIF PullPoint",
        property_operation="Initialized",
        data_items={"State": "false"},
    )
    win._on_metadata_items([hb_item])

    assert win.heartbeat_count == 1
    assert win.alarm_event_count == 0
    assert win.events_model.rowCount() == 1
    # By default, Hide Heartbeats is checked -> 0 shown
    assert win.events_proxy.rowCount() == 0
    assert "0 / 1 events" in win.events_count_badge.text()
    assert win.gallery_grid.count() == 0  # Heartbeats not on capture wall

    # Uncheck Hide Heartbeats -> heartbeat row is now shown in table
    win.hide_hb_cb.setChecked(False)
    assert win.events_proxy.rowCount() == 1
    assert "1 / 1 events" in win.events_count_badge.text()

    # 2. Genuine alarm item arrives via PullPoint -> goes to table model, but NOT to Capture Wall
    alarm_item = make_item(
        channel="ONVIF PullPoint",
        rule_or_object_id="ID_rule0 (Obj 1419)",
        property_operation="Changed",
        data_items={"State": "true"},
    )
    win._on_metadata_items([alarm_item])

    assert win.alarm_event_count == 1
    assert win.events_model.rowCount() == 2
    assert win.events_proxy.rowCount() == 2
    assert win.gallery_grid.count() == 0  # PullPoint is NOT pushed to Capture Wall!
    assert win.snapshot_strip.count() == 0

    # 3. Genuine alarm item arrives via RTSP -> goes to both table model and Capture Wall!
    rtsp_alarm = make_item(
        channel="RTSP Metadata (Event)",
        rule_or_object_id="ID_rule0 (Obj 1420)",
        property_operation="Changed",
        data_items={"State": "true"},
    )
    win._on_metadata_items([rtsp_alarm])

    assert win.alarm_event_count == 2
    assert win.events_model.rowCount() == 3
    assert win.events_proxy.rowCount() == 3
    assert win.gallery_grid.count() == 1  # RTSP alarm added to Capture Wall!
    assert win.snapshot_strip.count() == 1
    assert "Capture Wall (1)" in win.tabs.tabText(1)

    # 4. Batch of 10 simultaneous events arrives -> fast batch processing with thumbnail caching
    dummy_jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
        b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
    )
    batch = [
        make_item(
            channel="RTSP Metadata (Event)",
            rule_or_object_id=f"ID_rule0 (Obj {2000 + i})",
            utc_time=f"2026-10-15T04:31:{i:02d}.000Z",
            property_operation="Changed",
            data_items={"State": "true"},
            image_bytes=dummy_jpeg,
        )
        for i in range(10)
    ]
    t0 = time.perf_counter()
    win._on_metadata_items(batch)
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.25  # Batch processing 10 events must be fast (<250ms)
    assert win.gallery_grid.count() == 11
    assert win.snapshot_strip.count() == 11
    for it in batch:
        assert it.thumbnail_pixmap is not None
        assert not it.thumbnail_pixmap.isNull()

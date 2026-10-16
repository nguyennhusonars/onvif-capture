from onvif_capture.models import CapturedMetadataItem, DetectedObject


def test_detected_object_defaults():
    obj = DetectedObject(
        object_id="101",
        utc_time="2026-10-14T10:14:33.000Z",
        source="AI_Classifier",
        class_type="Human",
        likelihood=0.85,
        bbox=(0.1, 0.2, 0.3, 0.4),
    )
    assert obj.object_id == "101"
    assert obj.class_type == "Human"
    assert obj.likelihood == 0.85
    assert obj.bbox == (0.1, 0.2, 0.3, 0.4)
    assert obj.attributes == {}


def test_captured_metadata_item_properties():
    item = CapturedMetadataItem(
        channel="RTSP Metadata (Event)",
        kind="event",
        utc_time="2026-10-14T10:14:33.000Z",
        local_timestamp=1728900000.0,
        topic_or_source="tns1:RuleEngine/Detection/Intrusion",
        rule_or_object_id="ID_rule0 (Obj #2503)",
        summary="State=true",
        likelihood=0.67,
        image_bytes=b"\xff\xd8\xff\xd9",
        template_bytes=b"\x01\x02\x03\x04",
    )
    assert item.has_embedded_image is True
    assert item.has_template is True
    assert item.image_bytes == b"\xff\xd8\xff\xd9"
    assert item.template_bytes == b"\x01\x02\x03\x04"


def make_test_item(
    rule_or_object_id: str = "Rule_1",
    utc_time: str = "2026-10-16T08:00:00.000Z",
    kind: str = "event",
    channel: str = "ONVIF PullPoint",
) -> CapturedMetadataItem:
    return CapturedMetadataItem(
        channel=channel,
        kind=kind,
        utc_time=utc_time,
        local_timestamp=1728900000.0,
        topic_or_source="tns1:RuleEngine/Detection/Intrusion",
        rule_or_object_id=rule_or_object_id,
        summary="State=true",
    )


def test_metadata_table_model_latest_at_top(qapp):
    """Verify that latest event or message is placed at row 0 (top row)."""
    from onvif_capture.gui.models import MetadataTableModel

    model = MetadataTableModel(max_items=10)

    item1 = make_test_item(rule_or_object_id="Rule_1", utc_time="2026-10-16T08:00:01.000Z")
    item2 = make_test_item(rule_or_object_id="Rule_2", utc_time="2026-10-16T08:00:02.000Z")

    # Add item 1
    model.add_items([item1])
    assert model.rowCount() == 1
    assert model.get_item(0).rule_or_object_id == "Rule_1"

    # Add item 2 (later event)
    model.add_items([item2])
    assert model.rowCount() == 2
    # Row 0 must be item2 (latest event on top)
    assert model.get_item(0).rule_or_object_id == "Rule_2"
    # Row 1 must be item1 (older event below)
    assert model.get_item(1).rule_or_object_id == "Rule_1"


def test_metadata_table_model_batch_insertion_order(qapp):
    """Verify that a batch of chronological items preserves order with newest at row 0."""
    from onvif_capture.gui.models import MetadataTableModel

    model = MetadataTableModel(max_items=10)
    batch = [
        make_test_item(
            rule_or_object_id=f"Obj_{i}",
            utc_time=f"2026-10-16T08:00:{i:02d}.000Z",
            kind="object_frame",
            channel="RTSP Metadata (Frame)",
        )
        for i in range(5)  # Obj_0 (earliest) to Obj_4 (latest)
    ]

    model.add_items(batch)
    assert model.rowCount() == 5
    # Row 0 must be the newest item in the batch (Obj_4)
    assert model.get_item(0).rule_or_object_id == "Obj_4"
    assert model.get_item(1).rule_or_object_id == "Obj_3"
    assert model.get_item(2).rule_or_object_id == "Obj_2"
    assert model.get_item(3).rule_or_object_id == "Obj_1"
    assert model.get_item(4).rule_or_object_id == "Obj_0"


def test_metadata_table_model_prunes_oldest_from_bottom(qapp):
    """Verify that when capacity is reached, oldest items at the bottom are pruned."""
    from onvif_capture.gui.models import MetadataTableModel

    # Max 3 items
    model = MetadataTableModel(max_items=3)

    batch1 = [
        make_test_item(rule_or_object_id=f"Ev_{i}")
        for i in range(1, 4)  # Ev_1, Ev_2, Ev_3
    ]
    model.add_items(batch1)
    assert model.rowCount() == 3
    assert model.get_item(0).rule_or_object_id == "Ev_3"
    assert model.get_item(1).rule_or_object_id == "Ev_2"
    assert model.get_item(2).rule_or_object_id == "Ev_1"

    # Add newer event Ev_4 -> Ev_1 (oldest, at bottom) must be pruned
    ev_4 = make_test_item(rule_or_object_id="Ev_4")
    model.add_items([ev_4])

    assert model.rowCount() == 3
    assert model.get_item(0).rule_or_object_id == "Ev_4"
    assert model.get_item(1).rule_or_object_id == "Ev_3"
    assert model.get_item(2).rule_or_object_id == "Ev_2"


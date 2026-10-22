import base64
import pytest
from lxml import etree

from onvif_capture.parsers import (
    clean_xml_string,
    local_name,
    normalize_bbox,
    parse_appearance_element,
    parse_metadata_stream_xml,
    parse_notification_element,
    SAMPLE_VERIFIED_XML,
)


# ============================================================================
# 1. Coordinate Normalization Math Tests
# ============================================================================

def test_normalize_bbox_unsigned_standard():
    """Unsigned [0, 1] coordinates standard top-left space."""
    bb = normalize_bbox(0.1, 0.2, 0.5, 0.8, is_signed_onvif=False)
    assert bb == (0.1, 0.2, 0.5, 0.8)


def test_normalize_bbox_unsigned_inverted():
    """Ensure coordinates are swapped if min/max are inverted."""
    bb = normalize_bbox(0.6, 0.9, 0.2, 0.3, is_signed_onvif=False)
    assert bb == (0.2, 0.3, 0.6, 0.9)


def test_normalize_bbox_signed_onvif_corners():
    """
    Signed ONVIF [-1, 1] coordinates:
    (-1, 1) top-left -> (0.0, 0.0)
    (1, -1) bottom-right -> (1.0, 1.0)
    """
    bb = normalize_bbox(-1.0, 1.0, 1.0, -1.0, is_signed_onvif=True)
    assert bb == (0.0, 0.0, 1.0, 1.0)


def test_normalize_bbox_signed_onvif_auto_detection():
    """Negative values should automatically trigger signed ONVIF normalization."""
    bb = normalize_bbox(-0.84, 0.76, -0.12, -0.84)
    # Expected:
    # left = (-0.84 + 1) / 2 = 0.08
    # top = (1 - 0.76) / 2 = 0.12
    # right = (-0.12 + 1) / 2 = 0.44
    # bottom = (1 - (-0.84)) / 2 = 0.92
    assert pytest.approx(bb[0], 0.01) == 0.08
    assert pytest.approx(bb[1], 0.01) == 0.12
    assert pytest.approx(bb[2], 0.01) == 0.44
    assert pytest.approx(bb[3], 0.01) == 0.92


def test_normalize_bbox_out_of_bounds_clamping():
    """Values exceeding [-1, 1] or [0, 1] must be safely clamped."""
    bb = normalize_bbox(-1.5, 1.5, 1.5, -1.5, is_signed_onvif=True)
    assert bb == (0.0, 0.0, 1.0, 1.0)


# ============================================================================
# 2. Appearance & Extension Parsing Tests
# ============================================================================

def test_parse_appearance_human_rich():
    xml = b"""<tt:Appearance xmlns:tt="http://www.onvif.org/ver10/schema">
      <tt:Shape><tt:BoundingBox left="0.1" top="0.2" right="0.4" bottom="0.9"/></tt:Shape>
      <tt:Class><tt:Type Likelihood="0.88">Human</tt:Type></tt:Class>
      <tt:HumanFace>
        <tt:Gender Likelihood="0.95">Female</tt:Gender>
        <tt:Temperature>36.6</tt:Temperature>
        <tt:Hair Likelihood="0.72">Long</tt:Hair>
      </tt:HumanFace>
      <tt:HumanBody>
        <tt:BodyMetric><tt:Height>165</tt:Height><tt:BodyShape>Normal</tt:BodyShape></tt:BodyMetric>
      </tt:HumanBody>
      <tt:GeoLocation><tt:lat>21.0285</tt:lat><tt:lon>105.8542</tt:lon></tt:GeoLocation>
    </tt:Appearance>"""
    elem = etree.fromstring(xml)
    ctype, lk, raw_bb, attrs = parse_appearance_element(elem)

    assert ctype == "Human"
    assert lk == 0.88
    assert raw_bb == {"left": 0.1, "top": 0.2, "right": 0.4, "bottom": 0.9}
    assert attrs["HumanFace"]["Gender"] == "Female (0.95)"
    assert attrs["HumanBody"]["Height"] == "165"
    assert attrs["GeoLocation"]["lat"] == "21.0285"


def test_parse_appearance_vehicle_rich():
    xml = b"""<tt:Appearance xmlns:tt="http://www.onvif.org/ver10/schema">
      <tt:VehicleInfo>
        <tt:Type Likelihood="0.92">SUV</tt:Type>
        <tt:Brand Likelihood="0.85">Toyota</tt:Brand>
        <tt:Color Likelihood="0.78">White</tt:Color>
      </tt:VehicleInfo>
      <tt:LicensePlateInfo>
        <tt:PlateNumber Likelihood="0.97">30H-12345</tt:PlateNumber>
        <tt:CountryCode Likelihood="0.99">VN</tt:CountryCode>
      </tt:LicensePlateInfo>
    </tt:Appearance>"""
    elem = etree.fromstring(xml)
    ctype, lk, raw_bb, attrs = parse_appearance_element(elem)

    assert ctype == "Vehicle"
    assert attrs["VehicleInfo"]["Brand"] == "Toyota (0.85)"
    assert attrs["LicensePlateInfo"]["PlateNumber"] == "30H-12345 (0.97)"


# ============================================================================
# 3. Notification & Multi-Target Alarm Event Tests
# ============================================================================

def test_parse_notification_case1_multi_message():
    """
    Case 1: Multiple <tt:Message> inside <wsnt:Message> sharing the exact same timestamp
    (e.g., Object #2503 and #2509 in simultaneous intrusion detection).
    """
    xml = b"""<wsnt:NotificationMessage xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
                                        xmlns:tt="http://www.onvif.org/ver10/schema"
                                        xmlns:tns1="http://www.onvif.org/ver10/topics">
      <wsnt:Topic>tns1:RuleEngine/Detection/Intrusion</wsnt:Topic>
      <wsnt:Message>
        <tt:Message UtcTime="2026-10-14T10:14:33.038Z">
          <tt:Source><tt:SimpleItem Name="Rule" Value="ID_rule0"/></tt:Source>
          <tt:Data>
            <tt:ElementItem Name="ObjectId"><tt:ObjectId>2503</tt:ObjectId></tt:ElementItem>
            <tt:ElementItem Name="BoundingBox">
              <tt:Rectangle left="-0.5" top="0.5" right="0.0" bottom="-0.5"/>
            </tt:ElementItem>
            <tt:SimpleItem Name="Likelihood" Value="0.67"/>
          </tt:Data>
        </tt:Message>
        <tt:Message UtcTime="2026-10-14T10:14:33.038Z">
          <tt:Source><tt:SimpleItem Name="Rule" Value="ID_rule0"/></tt:Source>
          <tt:Data>
            <tt:ElementItem Name="ObjectId"><tt:ObjectId>2509</tt:ObjectId></tt:ElementItem>
            <tt:ElementItem Name="BoundingBox">
              <tt:Rectangle left="0.0" top="0.5" right="0.5" bottom="-0.5"/>
            </tt:ElementItem>
            <tt:SimpleItem Name="Likelihood" Value="0.71"/>
          </tt:Data>
        </tt:Message>
      </wsnt:Message>
    </wsnt:NotificationMessage>"""

    items = parse_notification_element(etree.fromstring(xml), channel="RTSP Metadata (Event)")
    assert len(items) == 2
    assert "2503" in items[0].rule_or_object_id
    assert items[0].likelihood == 0.67
    assert items[0].bbox is not None
    assert "2509" in items[1].rule_or_object_id
    assert items[1].likelihood == 0.71


def test_parse_notification_case2_multi_data():
    """
    Case 2: Multiple <tt:Data> elements within a single <tt:Message>.
    """
    xml = b"""<wsnt:NotificationMessage xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
                                        xmlns:tt="http://www.onvif.org/ver10/schema"
                                        xmlns:tns1="http://www.onvif.org/ver10/topics">
      <wsnt:Topic>tns1:RuleEngine/Detection/Intrusion</wsnt:Topic>
      <wsnt:Message>
        <tt:Message UtcTime="2026-10-14T10:14:33.038Z">
          <tt:Source><tt:SimpleItem Name="Rule" Value="ID_rule0"/></tt:Source>
          <tt:Data>
            <tt:ElementItem Name="ObjectId"><tt:ObjectId>2503</tt:ObjectId></tt:ElementItem>
            <tt:SimpleItem Name="Likelihood" Value="0.67"/>
          </tt:Data>
          <tt:Data>
            <tt:ElementItem Name="ObjectId"><tt:ObjectId>2509</tt:ObjectId></tt:ElementItem>
            <tt:SimpleItem Name="Likelihood" Value="0.71"/>
          </tt:Data>
        </tt:Message>
      </wsnt:Message>
    </wsnt:NotificationMessage>"""

    items = parse_notification_element(etree.fromstring(xml), channel="RTSP Metadata (Event)")
    assert len(items) == 2
    assert "2503" in items[0].rule_or_object_id
    assert "2509" in items[1].rule_or_object_id


def test_parse_notification_case3_multi_object_in_single_data():
    """
    Case 3: Multiple <tt:ElementItem Name="ObjectId"> inside a single <tt:Data> block,
    along with dummy empty SimpleItem tags.
    """
    xml = b"""<wsnt:NotificationMessage xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
                                        xmlns:tt="http://www.onvif.org/ver10/schema"
                                        xmlns:tns1="http://www.onvif.org/ver10/topics">
      <wsnt:Topic>tns1:RuleEngine/Detection/Intrusion</wsnt:Topic>
      <wsnt:Message>
        <tt:Message UtcTime="2026-10-14T10:14:33.038Z">
          <tt:Source><tt:SimpleItem Name="Rule" Value="ID_rule0"/></tt:Source>
          <tt:Data>
            <tt:SimpleItem Name="State" Value="true"/>
            <tt:ElementItem Name="ObjectId"><tt:ObjectId>2503</tt:ObjectId></tt:ElementItem>
            <tt:SimpleItem Name="Likelihood" Value="0.67"/>
            <tt:ElementItem Name="ObjectId"><tt:ObjectId>2509</tt:ObjectId></tt:ElementItem>
            <tt:SimpleItem Name="Likelihood" Value="0.71"/>
            <tt:SimpleItem Name="" Value=""/>
          </tt:Data>
        </tt:Message>
      </wsnt:Message>
    </wsnt:NotificationMessage>"""

    items = parse_notification_element(etree.fromstring(xml), channel="RTSP Metadata (Event)")
    assert len(items) == 2
    assert "2503" in items[0].rule_or_object_id
    assert items[0].data_items["State"] == "true"
    assert "2509" in items[1].rule_or_object_id
    assert items[1].data_items["State"] == "true"
    # Ensure empty name tag is skipped
    assert "" not in items[0].data_items


def test_parse_notification_face_recognition_snapshot_and_biometric_template():
    """
    Principle 6: Strict separation of Snapshot JPEG vs Biometric Template Feature Vector.
    Ensure template embedding does not overwrite image_bytes.
    """
    # 1x1 dummy JPEG
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb"
    b64_jpeg = base64.b64encode(jpeg_bytes).decode("ascii")

    # Binary feature vector embedding (128-byte float vector)
    template_raw = bytes(range(128))
    b64_template = base64.b64encode(template_raw).decode("ascii")

    xml = f"""<wsnt:NotificationMessage xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
                                        xmlns:tt="http://www.onvif.org/ver10/schema"
                                        xmlns:tns1="http://www.onvif.org/ver10/topics">
      <wsnt:Topic>tns1:RuleEngine/Recognition/Face</wsnt:Topic>
      <wsnt:Message>
        <tt:Message UtcTime="2026-10-14T10:14:33.038Z">
          <tt:Source><tt:SimpleItem Name="Rule" Value="FR_rule0"/></tt:Source>
          <tt:Data>
            <tt:SimpleItem Name="EnrollmentID" Value="EMP_0042"/>
            <tt:SimpleItem Name="Likelihood" Value="0.94"/>
            <tt:ElementItem Name="Image"><tt:base64Binary>{b64_jpeg}</tt:base64Binary></tt:ElementItem>
            <tt:ElementItem Name="Template"><tt:base64Binary>{b64_template}</tt:base64Binary></tt:ElementItem>
          </tt:Data>
        </tt:Message>
      </wsnt:Message>
    </wsnt:NotificationMessage>""".encode("utf-8")

    items = parse_notification_element(etree.fromstring(xml), channel="ONVIF PullPoint")
    assert len(items) == 1
    ev = items[0]
    assert ev.image_bytes == jpeg_bytes
    assert ev.template_bytes == template_raw
    assert "Snapshot" in ev.summary
    assert "Embedding" in ev.summary
    assert ev.data_items["EnrollmentID"] == "EMP_0042"


def test_parse_notification_dirty_prefix_in_jpeg():
    """Ensure decoder trims dirty prefix header bytes before FF D8 JPEG SOI magic."""
    dirty_jpeg = b"JUNK_METADATA_HEADER\xff\xd8\xff\xe0\x00\x10JFIF\xff\xd9"
    b64_dirty = base64.b64encode(dirty_jpeg).decode("ascii")

    xml = f"""<wsnt:NotificationMessage xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
                                        xmlns:tt="http://www.onvif.org/ver10/schema">
      <wsnt:Topic>tns1:RuleEngine/FaceDetector/Detected</wsnt:Topic>
      <wsnt:Message>
        <tt:Data>
          <tt:ElementItem Name="Image"><tt:base64Binary>{b64_dirty}</tt:base64Binary></tt:ElementItem>
        </tt:Data>
      </wsnt:Message>
    </wsnt:NotificationMessage>""".encode("utf-8")

    items = parse_notification_element(etree.fromstring(xml))
    assert len(items) == 1
    assert items[0].image_bytes.startswith(b"\xff\xd8")


def test_parse_notification_robust_fallbacks():
    """Handle missing topic, non-numeric likelihood, missing BBox, empty fields."""
    xml = b"""<wsnt:NotificationMessage xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
                                        xmlns:tt="http://www.onvif.org/ver10/schema">
      <wsnt:Message PropertyOperation="Changed">
        <tt:Data>
          <tt:SimpleItem Name="Likelihood" Value="INVALID_FLOAT"/>
          <tt:SimpleItem Name="State" Value="false"/>
        </tt:Data>
      </wsnt:Message>
    </wsnt:NotificationMessage>"""

    items = parse_notification_element(etree.fromstring(xml))
    assert len(items) == 1
    ev = items[0]
    assert ev.topic_or_source == "UnknownTopic"
    assert ev.likelihood is None
    assert ev.data_items["State"] == "false"
    assert ev.property_operation == "Changed"


# ============================================================================
# 4. RTSP MetadataStream XML Track Reassembly Tests
# ============================================================================

def test_parse_metadata_stream_xml_sample_verified():
    """Verify parsing of SAMPLE_VERIFIED_XML emits both frame and event."""
    items = parse_metadata_stream_xml(SAMPLE_VERIFIED_XML)
    assert len(items) == 2
    assert items[0].kind == "object_frame"
    assert len(items[0].objects) == 2
    assert items[0].objects[0].object_id == "108"
    assert items[0].objects[1].object_id == "204"

    assert items[1].kind == "event"
    assert items[1].topic_or_source == "tns1:RuleEngine/Detection/Intrusion"
    assert "108" in items[1].rule_or_object_id


def test_parse_metadata_stream_concatenated_chunks():
    """RTSP multi-frame packet reassembly: multiple <MetadataStream> elements concatenated."""
    frame_xml = b"""<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema">
      <tt:VideoAnalytics>
        <tt:Frame UtcTime="2026-10-14T10:14:33.000Z">
          <tt:Object ObjectId="1"><tt:Appearance><tt:Class><tt:Type>Human</tt:Type></tt:Class></tt:Appearance></tt:Object>
        </tt:Frame>
      </tt:VideoAnalytics>
    </tt:MetadataStream>"""

    event_xml = b"""<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
      <tt:Event>
        <wsnt:NotificationMessage>
          <wsnt:Topic>tns1:RuleEngine/LineCross/LC_rule0</wsnt:Topic>
          <wsnt:Message>
            <tt:Source><tt:SimpleItem Name="Rule" Value="LC_rule0"/></tt:Source>
            <tt:Data><tt:SimpleItem Name="State" Value="true"/></tt:Data>
          </wsnt:Message>
        </wsnt:NotificationMessage>
      </tt:Event>
    </tt:MetadataStream>"""

    concatenated = b"<?xml version='1.0'?>" + frame_xml + b"<?xml version='1.0'?>" + event_xml
    items = parse_metadata_stream_xml(concatenated)
    assert len(items) == 2
    assert items[0].kind == "object_frame"
    assert items[1].kind == "event"
    assert "LC_rule0" in items[1].rule_or_object_id


def test_parse_metadata_stream_huge_tree():
    """
    Principle 4: High-resolution camera snapshot payload test.
    Simulate a 500 KB base64 snapshot to verify huge_tree parser support.
    """
    huge_jpeg = b"\xff\xd8" + (b"A" * 500_000) + b"\xff\xd9"
    b64_huge = base64.b64encode(huge_jpeg).decode("ascii")

    xml = f"""<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
      <tt:Event>
        <wsnt:NotificationMessage>
          <wsnt:Topic>tns1:RuleEngine/Detection/Intrusion</wsnt:Topic>
          <wsnt:Message>
            <tt:Data>
              <tt:ElementItem Name="Image"><tt:base64Binary>{b64_huge}</tt:base64Binary></tt:ElementItem>
            </tt:Data>
          </wsnt:Message>
        </wsnt:NotificationMessage>
      </tt:Event>
    </tt:MetadataStream>""".encode("utf-8")

    items = parse_metadata_stream_xml(xml)
    assert len(items) == 1
    assert items[0].image_bytes is not None
    assert len(items[0].image_bytes) == len(huge_jpeg)


def test_parse_metadata_stream_corrupted_xml_graceful():
    """Corrupted / unclosed stream chunks must not raise unhandled exceptions."""
    corrupted_data = b"<tt:MetadataStream><tt:VideoAnalytics><tt:Frame UtcTime='unclosed"
    items = parse_metadata_stream_xml(corrupted_data)
    assert isinstance(items, list)

    items_empty = parse_metadata_stream_xml(b"")
    assert items_empty == []


def test_nat_and_port_forwarding_rewriting():
    """Verify NAT XAddr and custom RTSP port rewrites for cameras behind port forwarding."""
    from onvif_capture.client import _rewrite_rtsp_uri, _rewrite_url

    # SOAP Service XAddr rewrite
    internal_xaddr = "http://193.169.0.2:8000/onvif/media2_service"
    rewritten_xaddr = _rewrite_url(internal_xaddr, "14.224.145.111", 8001)
    assert rewritten_xaddr == "http://14.224.145.111:8001/onvif/media2_service"

    # RTSP URI rewrite with custom forwarded RTSP port (551, 552)
    internal_rtsp = "rtsp://193.169.0.2:554/stream0"
    rewritten_rtsp = _rewrite_rtsp_uri(internal_rtsp, "14.224.145.111", 551)
    assert rewritten_rtsp == "rtsp://14.224.145.111:551/stream0"

    # Without port override, keep internal port or default
    rewritten_rtsp_default = _rewrite_rtsp_uri(internal_rtsp, "14.224.145.111", None)
    assert rewritten_rtsp_default == "rtsp://14.224.145.111:554/stream0"

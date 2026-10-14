from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DetectedObject:
    """Represents a single AI-detected object inside an ONVIF <tt:VideoAnalytics><tt:Frame> or <tt:Event>."""

    object_id: str
    utc_time: str
    source: str
    class_type: str = "Object"
    likelihood: Optional[float] = None
    bbox: Optional[Tuple[float, float, float, float]] = None  # Normalized [0.0, 1.0] (x1, y1, x2, y2)
    raw_bbox: Optional[Dict[str, float]] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapturedMetadataItem:
    """Represents a parsed ONVIF Profile M metadata frame or event notification."""

    channel: str  # "RTSP Metadata (VideoAnalytics)", "RTSP Metadata (Event)", "ONVIF PullPoint"
    kind: str  # "object_frame" or "event"
    utc_time: str
    local_timestamp: float
    topic_or_source: str
    rule_or_object_id: str
    summary: str
    likelihood: Optional[float] = None
    property_operation: str = ""
    bbox: Optional[Tuple[float, float, float, float]] = None
    objects: List[DetectedObject] = field(default_factory=list)
    source_items: Dict[str, Any] = field(default_factory=dict)
    data_items: Dict[str, Any] = field(default_factory=dict)
    image_bytes: Optional[bytes] = None
    raw_xml: str = ""


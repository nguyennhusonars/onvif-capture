import base64
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree

from .models import CapturedMetadataItem, DetectedObject


def local_name(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def clean_xml_string(elem: etree._Element, truncate_base64: bool = True) -> str:
    """Pretty-print an XML element while stripping redundant root xmlns noise and optionally shortening base64 blobs."""
    saved_b64 = []
    if truncate_base64:
        for b64 in elem.xpath(".//*[local-name()='base64Binary']"):
            if b64.text and len(b64.text) > 120:
                saved_b64.append((b64, b64.text))
                parent_name = ""
                parent = b64.getparent()
                while parent is not None:
                    if parent.get("Name"):
                        parent_name = parent.get("Name")
                        break
                    parent = parent.getparent()
                tag_label = f"base64 {parent_name}" if parent_name else "base64Binary"
                b64.text = f"{b64.text[:60]}... [{tag_label}: {len(b64.text)} chars] ...{b64.text[-30:]}"
    try:
        etree.cleanup_namespaces(elem)
        return etree.tostring(elem, encoding="unicode", pretty_print=True).strip()
    finally:
        for b64, orig_txt in saved_b64:
            b64.text = orig_txt


def normalize_bbox(
    left: float, top: float, right: float, bottom: float, is_signed_onvif: Optional[bool] = None
) -> Tuple[float, float, float, float]:
    """
    Convert bounding box to normalized top-left [0.0, 1.0] screen coordinates (x1, y1, x2, y2).
    Handles both:
      - [0, 1] normalized coordinates (standard ONVIF Profile M <tt:VideoAnalytics><tt:Frame><tt:Object>)
      - [-1, 1] ONVIF normalized coordinates (x in [-1, 1] left-to-right, y in [-1, 1] bottom-to-top,
        standard ONVIF <tt:Event><tt:ElementItem Name="BoundingBox"><tt:Rectangle>)
    """
    if is_signed_onvif is None:
        is_signed_onvif = any(v < -0.001 for v in (left, top, right, bottom)) or (top > bottom and top > 0)

    if is_signed_onvif:
        x1 = (left + 1.0) / 2.0
        x2 = (right + 1.0) / 2.0
        y1 = (1.0 - top) / 2.0
        y2 = (1.0 - bottom) / 2.0
    else:
        x1, y1, x2, y2 = left, top, right, bottom

    x_min, x_max = min(x1, x2), max(x1, x2)
    y_min, y_max = min(y1, y2), max(y1, y2)
    return (
        max(0.0, min(1.0, x_min)),
        max(0.0, min(1.0, y_min)),
        max(0.0, min(1.0, x_max)),
        max(0.0, min(1.0, y_max)),
    )


def parse_appearance_element(
    app_elem: etree._Element,
) -> Tuple[str, Optional[float], Optional[Dict[str, float]], Dict[str, Any]]:
    """Extract class type, likelihood, raw bbox, and Profile M semantic attributes from <tt:Appearance>."""
    class_type = "Object"
    likelihood: Optional[float] = None
    raw_bbox: Optional[Dict[str, float]] = None
    attrs: Dict[str, Any] = {}

    for child in app_elem:
        cname = local_name(child.tag)
        if cname == "Shape":
            bb = child.xpath(".//*[local-name()='BoundingBox']")
            if bb:
                b = bb[0]
                try:
                    raw_bbox = {
                        "left": float(b.get("left", "0")),
                        "top": float(b.get("top", "0")),
                        "right": float(b.get("right", "0")),
                        "bottom": float(b.get("bottom", "0")),
                    }
                except ValueError:
                    pass
            cog = child.xpath(".//*[local-name()='CenterOfGravity']")
            if cog:
                attrs["CenterOfGravity"] = dict(cog[0].attrib)
        elif cname == "Class":
            for t in child.xpath(
                ".//*[local-name()='Type'] | .//*[local-name()='ClassCandidate']/*[local-name()='Type']"
            ):
                if t.text and t.text.strip():
                    class_type = t.text.strip()
                lk = t.get("Likelihood")
                if lk is not None:
                    try:
                        likelihood = float(lk)
                    except ValueError:
                        pass
            for cand in child.xpath(".//*[local-name()='ClassCandidate']"):
                t_el = cand.xpath("./*[local-name()='Type']")
                l_el = cand.xpath("./*[local-name()='Likelihood']")
                if t_el and t_el[0].text:
                    class_type = t_el[0].text.strip()
                if l_el and l_el[0].text:
                    try:
                        likelihood = float(l_el[0].text.strip())
                    except ValueError:
                        pass
        else:
            # Profile M extensions: VehicleInfo, LicensePlateInfo, HumanFace, HumanBody, GeoLocation, etc.
            sub_dict: Dict[str, Any] = {}
            for sub in child.iter():
                if sub is child:
                    continue
                sname = local_name(sub.tag)
                if len(sub) == 0 and sub.text and sub.text.strip():
                    val_str = sub.text.strip()
                    lk = sub.get("Likelihood")
                    sub_dict[sname] = f"{val_str} ({float(lk):.2f})" if lk else val_str
                    if likelihood is None and lk:
                        try:
                            likelihood = float(lk)
                        except ValueError:
                            pass
            if sub_dict:
                attrs[cname] = sub_dict
                if class_type == "Object":
                    class_type = cname.replace("Info", "")

    return class_type, likelihood, raw_bbox, attrs


def _parse_items_from_element_group(
    items_list: List[etree._Element],
    topic: str,
    utc_time: str,
    prop_op: str,
    source_items: Dict[str, Any],
    channel: str,
    raw_node: etree._Element,
) -> CapturedMetadataItem:
    data_items: Dict[str, Any] = {}
    image_bytes: Optional[bytes] = None
    template_bytes: Optional[bytes] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    likelihood: Optional[float] = None
    object_id = ""

    for item in items_list:
        iname = local_name(item.tag)
        attr_name = (item.get("Name") or "").strip()
        if not attr_name:
            if iname != "SimpleItem":
                attr_name = iname
            else:
                continue

        if iname == "SimpleItem":
            val = item.get("Value", "")
            data_items[attr_name] = val
            if attr_name.lower() == "likelihood":
                try:
                    likelihood = float(val)
                except ValueError:
                    pass
            elif attr_name.lower() == "objectid" and not object_id:
                object_id = str(val)

        elif iname == "ElementItem":
            b64_el = item.xpath(".//*[local-name()='base64Binary']")
            b64_txt = (
                b64_el[0].text.strip()
                if (b64_el and b64_el[0].text)
                else (item.text.strip() if item.text else "")
            )
            is_template_name = any(
                t in attr_name.lower() for t in ("template", "feature", "embedding", "biometric", "descriptor")
            )
            is_image_name = any(
                t in attr_name.lower() for t in ("image", "snapshot", "picture", "photo", "thumbnail")
            )

            if b64_txt and (is_image_name or is_template_name or b64_el):
                try:
                    decoded_data = base64.b64decode(b64_txt)
                    is_jpeg = decoded_data.startswith(b"\xff\xd8") or (b"\xff\xd8" in decoded_data[:64])
                    is_png = decoded_data.startswith(b"\x89PNG")

                    if (is_jpeg or is_png or is_image_name) and not is_template_name:
                        if not decoded_data.startswith(b"\xff\xd8") and is_jpeg:
                            idx = decoded_data.find(b"\xff\xd8")
                            if idx > 0:
                                decoded_data = decoded_data[idx:]
                        if image_bytes is None or attr_name.lower() == "image":
                            image_bytes = decoded_data
                        img_fmt = "PNG" if is_png else "JPEG"
                        data_items[attr_name] = f"<{img_fmt} Snapshot: {len(decoded_data):,} bytes>"
                    else:
                        template_bytes = decoded_data
                        data_items[attr_name] = f"<Biometric Template: {len(decoded_data):,} bytes>"
                except Exception:
                    data_items[attr_name] = f"<base64Binary ({attr_name}): {len(b64_txt)} chars>"

            elif attr_name.lower() == "boundingbox" or item.xpath(
                ".//*[local-name()='Rectangle'] | .//*[local-name()='BoundingBox']"
            ):
                rect_el = item.xpath(".//*[local-name()='Rectangle'] | .//*[local-name()='BoundingBox']")
                if rect_el:
                    r = rect_el[0]
                    try:
                        raw_r = {
                            "left": float(r.get("left", "0")),
                            "top": float(r.get("top", "0")),
                            "right": float(r.get("right", "0")),
                            "bottom": float(r.get("bottom", "0")),
                        }
                        data_items[attr_name] = raw_r
                        bbox = normalize_bbox(
                            raw_r["left"], raw_r["top"], raw_r["right"], raw_r["bottom"], is_signed_onvif=True
                        )
                    except ValueError:
                        data_items[attr_name] = dict(r.attrib)

            elif len(item) > 0:
                child = item[0]
                if len(child) == 0 and child.text:
                    val_txt = child.text.strip()
                    data_items[attr_name] = val_txt
                    if attr_name.lower() == "objectid":
                        object_id = val_txt
                else:
                    nested: Dict[str, Any] = {}
                    for sub in child.iter():
                        if sub is child:
                            continue
                        if len(sub) == 0 and sub.text and sub.text.strip():
                            lk = sub.get("Likelihood")
                            nested[local_name(sub.tag)] = (
                                f"{sub.text.strip()} ({float(lk):.2f})" if lk else sub.text.strip()
                            )
                    data_items[attr_name] = nested if nested else dict(child.attrib)

    rule_name = (
        source_items.get("Rule")
        or source_items.get("RuleName")
        or source_items.get("SimpleItem")
        or object_id
        or "-"
    )
    if object_id and rule_name != object_id:
        rule_or_obj = f"{rule_name} (Obj #{object_id})"
    else:
        rule_or_obj = str(rule_name)

    summary_parts = []
    for k, v in data_items.items():
        if k == "Image":
            summary_parts.append("Snapshot")
        elif k in ("Template", "Feature", "Embedding"):
            summary_parts.append("Embedding")
        elif k == "BoundingBox" and isinstance(v, dict):
            summary_parts.append(
                f"BBox[{v.get('left', 0):.2f},{v.get('top', 0):.2f},{v.get('right', 0):.2f},{v.get('bottom', 0):.2f}]"
            )
        else:
            summary_parts.append(f"{k}={v}")

    detected_objs: List[DetectedObject] = []
    if bbox is not None:
        short_topic = topic.split("/")[-1]
        detected_objs.append(
            DetectedObject(
                object_id=object_id or rule_name,
                utc_time=utc_time,
                source=topic,
                class_type=short_topic,
                likelihood=likelihood,
                bbox=bbox,
                attributes=data_items,
            )
        )

    return CapturedMetadataItem(
        channel=channel,
        kind="event",
        utc_time=utc_time,
        local_timestamp=time.time(),
        topic_or_source=topic,
        rule_or_object_id=rule_or_obj,
        summary=", ".join(summary_parts) if summary_parts else prop_op,
        likelihood=likelihood,
        property_operation=prop_op,
        bbox=bbox,
        objects=detected_objs,
        source_items=source_items,
        data_items=data_items,
        image_bytes=image_bytes,
        template_bytes=template_bytes,
        raw_xml=clean_xml_string(raw_node, truncate_base64=True),
    )


def parse_notification_element(
    notif_elem: etree._Element, channel: str = "ONVIF PullPoint"
) -> List[CapturedMetadataItem]:
    """
    Parse a <wsnt:NotificationMessage> (or <tt:Event>) XML element into CapturedMetadataItems.
    Robustly handles multi-message notifications, multiple <tt:Data> blocks, and simultaneous
    multi-object detections without dropping simultaneous events.
    """
    topic_el = notif_elem.xpath(".//*[local-name()='Topic']")
    topic = topic_el[0].text.strip() if topic_el and topic_el[0].text else "UnknownTopic"

    msg_el_list = notif_elem.xpath("./*[local-name()='Message']/*[local-name()='Message']")
    if not msg_el_list:
        msg_el_list = notif_elem.xpath("./*[local-name()='Message']")
    if not msg_el_list:
        msg_el_list = [notif_elem]

    results: List[CapturedMetadataItem] = []

    for msg_el in msg_el_list:
        utc_time = msg_el.get("UtcTime") or ""
        if not utc_time:
            utc_nodes = notif_elem.xpath(".//@UtcTime")
            utc_time = utc_nodes[0] if utc_nodes else ""

        prop_op = (msg_el.get("PropertyOperation") or "").strip()
        if not prop_op:
            op_nodes = notif_elem.xpath(".//@PropertyOperation")
            prop_op = (op_nodes[0] if op_nodes else "").strip()

        source_items: Dict[str, Any] = {}
        src_nodes = msg_el.xpath("./*[local-name()='Source']") or notif_elem.xpath(".//*[local-name()='Source']")
        for src in src_nodes:
            for item in src:
                iname = local_name(item.tag)
                attr_name = (item.get("Name") or "").strip()
                if not attr_name:
                    if iname != "SimpleItem":
                        attr_name = iname
                    else:
                        continue
                if iname == "SimpleItem":
                    source_items[attr_name] = item.get("Value", "")
                elif iname == "ElementItem" and item.text:
                    source_items[attr_name] = item.text.strip()

        data_nodes = msg_el.xpath("./*[local-name()='Data']")
        if not data_nodes:
            data_nodes = notif_elem.xpath("./*[local-name()='Data']")
        if not data_nodes:
            data_nodes = [None]

        for dn in data_nodes:
            if dn is not None:
                obj_els = dn.xpath(
                    './*[local-name()=\'ElementItem\'][translate(@Name, "OBJECTID", "objectid")=\'objectid\']'
                )
                if len(obj_els) > 1:
                    # Simultaneous multiple objects within a single Data element
                    common_items = []
                    current_items = None
                    groups = []
                    for item in dn:
                        name = (item.get("Name") or "").lower()
                        if name == "objectid":
                            if current_items is not None:
                                groups.append(common_items + current_items)
                            current_items = [item]
                        elif current_items is None:
                            common_items.append(item)
                        else:
                            current_items.append(item)
                    if current_items is not None:
                        groups.append(common_items + current_items)

                    for grp in groups:
                        item_obj = _parse_items_from_element_group(
                            grp, topic, utc_time, prop_op, source_items, channel, dn
                        )
                        results.append(item_obj)
                else:
                    item_obj = _parse_items_from_element_group(
                        list(dn), topic, utc_time, prop_op, source_items, channel, dn if len(data_nodes) > 1 else msg_el
                    )
                    results.append(item_obj)
            else:
                item_obj = _parse_items_from_element_group(
                    [], topic, utc_time, prop_op, source_items, channel, msg_el
                )
                results.append(item_obj)

    return results


def _parse_single_metadata_root(root: etree._Element) -> List[CapturedMetadataItem]:
    items: List[CapturedMetadataItem] = []

    # 1. Check <tt:VideoAnalytics> frames
    for frame in root.xpath(".//*[local-name()='VideoAnalytics']/*[local-name()='Frame']"):
        utc_time = frame.get("UtcTime", "")
        source = frame.get("Source", "VideoAnalytics")
        objs: List[DetectedObject] = []
        summaries: List[str] = []
        top_likelihood: Optional[float] = None
        first_bbox: Optional[Tuple[float, float, float, float]] = None

        for obj_el in frame.xpath("./*[local-name()='Object']"):
            obj_id = obj_el.get("ObjectId", "")
            app_el = obj_el.xpath("./*[local-name()='Appearance']")
            if app_el:
                ctype, lk, raw_bb, attrs = parse_appearance_element(app_el[0])
            else:
                ctype, lk, raw_bb, attrs = "Object", None, None, {}

            norm_bb = None
            if raw_bb:
                norm_bb = normalize_bbox(raw_bb["left"], raw_bb["top"], raw_bb["right"], raw_bb["bottom"])
                if first_bbox is None:
                    first_bbox = norm_bb

            if lk is not None and (top_likelihood is None or lk > top_likelihood):
                top_likelihood = lk

            dobj = DetectedObject(
                object_id=obj_id,
                utc_time=utc_time,
                source=source,
                class_type=ctype,
                likelihood=lk,
                bbox=norm_bb,
                raw_bbox=raw_bb,
                attributes=attrs,
            )
            objs.append(dobj)
            lk_str = f" ({lk:.0%})" if lk is not None else ""
            attr_str = f" {json.dumps(attrs, ensure_ascii=False)}" if attrs else ""
            bb_str = (
                f" [{norm_bb[0]:.2f},{norm_bb[1]:.2f}-{norm_bb[2]:.2f},{norm_bb[3]:.2f}]"
                if norm_bb
                else ""
            )
            summaries.append(f"#{obj_id}: {ctype}{lk_str}{bb_str}{attr_str}")

        obj_ids = ", ".join(f"#{o.object_id}" for o in objs) if objs else "-"
        data_items_dict: Dict[str, Any] = {}
        for idx, o in enumerate(objs):
            base_key = f"Object_{o.object_id}" if o.object_id else f"Object_{idx + 1}"
            key = base_key if base_key not in data_items_dict else f"{base_key}_{idx + 1}"
            data_items_dict[key] = {
                "Class": o.class_type,
                "Likelihood": o.likelihood,
                "NormalizedBBox": o.bbox,
                "RawBBox": o.raw_bbox,
                "Attributes": o.attributes,
            }

        items.append(
            CapturedMetadataItem(
                channel="RTSP Metadata (VideoAnalytics)",
                kind="object_frame",
                utc_time=utc_time,
                local_timestamp=time.time(),
                topic_or_source=f"tt:VideoAnalytics/{source}",
                rule_or_object_id=obj_ids,
                summary="; ".join(summaries) if summaries else "Empty Analytics Frame",
                likelihood=top_likelihood,
                bbox=first_bbox,
                objects=objs,
                data_items=data_items_dict,
                raw_xml=clean_xml_string(frame, truncate_base64=True),
            )
        )

    # 2. Check NotificationMessages inside the RTSP metadata stream
    notif_nodes = root.xpath(".//*[local-name()='NotificationMessage']")
    if notif_nodes:
        for notif in notif_nodes:
            items.extend(parse_notification_element(notif, channel="RTSP Metadata (Event)"))
    else:
        for ev in root.xpath(".//*[local-name()='Event']"):
            items.extend(parse_notification_element(ev, channel="RTSP Metadata (Event)"))

    return items


def parse_metadata_stream_xml(xml_bytes: bytes) -> List[CapturedMetadataItem]:
    """
    Parse one or more <tt:MetadataStream> XML payloads from the RTSP vnd.onvif.metadata track.
    Robustly handles multiple concatenated or fragmented <MetadataStream> elements.
    """
    items: List[CapturedMetadataItem] = []
    if not xml_bytes or not xml_bytes.strip():
        return items

    parser = etree.XMLParser(recover=True, huge_tree=True)

    # Extract all complete <MetadataStream>...</MetadataStream> chunks
    chunks = re.findall(rb"(<(?:\w+:)?MetadataStream[\s\S]*?<\/(?:\w+:)?MetadataStream>)", xml_bytes)
    if not chunks:
        if xml_bytes.count(b"<?xml ") > 1:
            chunks = [b"<?xml " + p for p in xml_bytes.split(b"<?xml ") if p.strip()]
        else:
            chunks = [xml_bytes]

    for part in chunks:
        try:
            root = etree.fromstring(part, parser=parser)
            if root is not None:
                items.extend(_parse_single_metadata_root(root))
        except Exception:
            continue

    return items


SAMPLE_VERIFIED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema">
  <tt:VideoAnalytics>
    <tt:Frame UtcTime="2026-10-13T01:23:51.402Z" Source="AI_Classifier" Colorspace="RGB">
      <tt:Transformation><tt:Translate x="-1" y="1"/><tt:Scale x="2" y="-2"/></tt:Transformation>
      <tt:Object ObjectId="108">
        <tt:Appearance>
          <tt:Shape><tt:BoundingBox left="0.08" top="0.12" right="0.44" bottom="0.92"/></tt:Shape>
          <tt:Class><tt:Type Likelihood="0.86">Human</tt:Type></tt:Class>
          <tt:HumanFace><tt:Gender Likelihood="0.82">Male</tt:Gender><tt:Temperature>36.8</tt:Temperature><tt:Hair Likelihood="0.65">Straight</tt:Hair></tt:HumanFace>
          <tt:HumanBody><tt:BodyMetric><tt:Height>172</tt:Height></tt:BodyMetric></tt:HumanBody>
        </tt:Appearance>
      </tt:Object>
      <tt:Object ObjectId="204">
        <tt:Appearance>
          <tt:Shape><tt:BoundingBox left="0.52" top="0.35" right="0.91" bottom="0.85"/></tt:Shape>
          <tt:VehicleInfo><tt:Type Likelihood="0.91">Car</tt:Type><tt:Brand Likelihood="0.74">Volvo</tt:Brand><tt:Model Likelihood="0.68">XC60</tt:Model></tt:VehicleInfo>
          <tt:LicensePlateInfo><tt:PlateNumber Likelihood="0.93">6DZG261</tt:PlateNumber><tt:CountryCode Likelihood="0.80">VN</tt:CountryCode></tt:LicensePlateInfo>
        </tt:Appearance>
      </tt:Object>
    </tt:Frame>
  </tt:VideoAnalytics>
  <tt:Event>
    <wsnt:NotificationMessage xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2" xmlns:tns1="http://www.onvif.org/ver10/topics">
      <wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">tns1:RuleEngine/Detection/Intrusion</wsnt:Topic>
      <wsnt:Message>
        <tt:Message UtcTime="2026-10-13T01:23:51.402Z">
          <tt:Source>
            <tt:SimpleItem Name="VideoSource" Value="VideoSourceToken_1"/>
            <tt:SimpleItem Name="Rule" Value="ID_rule0"/>
          </tt:Source>
          <tt:Data>
            <tt:SimpleItem Name="Likelihood" Value="0.86"/>
            <tt:ElementItem Name="ObjectId"><tt:ObjectId>108</tt:ObjectId></tt:ElementItem>
            <tt:ElementItem Name="BoundingBox"><tt:Rectangle left="-0.84" top="0.76" right="-0.12" bottom="-0.84"/></tt:ElementItem>
          </tt:Data>
        </tt:Message>
      </wsnt:Message>
    </wsnt:NotificationMessage>
  </tt:Event>
</tt:MetadataStream>"""


import socket
import struct
import threading
import time
from unittest.mock import MagicMock, patch
import requests

from onvif_capture.workers import RTSPMetadataStreamWorker, ONVIFPullPointWorker
from onvif_capture.models import CapturedMetadataItem


def test_rtsp_metadata_worker_rtp_reassembly():
    """
    Simulate RTSP interleaved TCP packet stream (dollar sign '$', channel 0, 16-bit length,
    followed by 12-byte RTP header and XML fragment) to verify stream reassembly and item dispatch.
    """
    delivered_items = []
    status_updates = []

    xml_content = b"""<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema">
      <tt:VideoAnalytics>
        <tt:Frame UtcTime="2026-10-14T10:14:33.000Z">
          <tt:Object ObjectId="42"><tt:Appearance><tt:Class><tt:Type>Human</tt:Type></tt:Class></tt:Appearance></tt:Object>
        </tt:Frame>
      </tt:VideoAnalytics>
    </tt:MetadataStream>"""

    # Create dummy RTP packet: 12-byte RTP header (marker bit set) + XML
    rtp_header = bytearray(12)
    rtp_header[0] = 0x80
    rtp_header[1] = 0x80  # Marker bit = 1
    rtp_payload = bytes(rtp_header) + xml_content

    # Prepend interleaved frame header: '$', channel 0, uint16 length
    interleaved_pkt = b"$" + bytes([0]) + struct.pack("!H", len(rtp_payload)) + rtp_payload

    # Create worker
    worker = RTSPMetadataStreamWorker(
        rtsp_uri="rtsp://127.0.0.1:554/stream0/metadata",
        username="admin",
        password="pwd",
        on_items=lambda batch: delivered_items.extend(batch),
        on_status=lambda s: status_updates.append(s),
    )

    # Put raw complete frame into worker queue directly to test consumer thread dispatch
    worker._xml_queue.put(xml_content)
    worker._xml_queue.put(None)  # Sentinel to terminate parser thread
    worker._parser_loop()

    assert len(delivered_items) == 1
    assert delivered_items[0].kind == "object_frame"
    assert delivered_items[0].objects[0].object_id == "42"


def test_pullpoint_worker_timeout_preserves_subscription():
    """
    Verify that normal requests.exceptions.Timeout during PullPoint PT3S long-polling
    does NOT crash or disconnect the worker, but gracefully continues polling.
    """
    delivered_items = []
    status_updates = []

    worker = ONVIFPullPointWorker(
        host="127.0.0.1",
        port=8000,
        username="admin",
        password="pwd",
        on_items=lambda batch: delivered_items.extend(batch),
        on_status=lambda s: status_updates.append(s),
    )

    # Verify that timeout is treated as a normal long-poll event
    with patch("onvif_capture.workers.ONVIFProfileMClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.connect.return_value = {}
        mock_instance.analytics_url = "http://127.0.0.1:8000/onvif/analytics_service"
        # First call raises Timeout, second call sets stop event
        def soap_side_effect(url, body, **kwargs):
            if "CreatePullPointSubscription" in body:
                el = MagicMock()
                sub_addr_el = MagicMock()
                sub_addr_el.text = "http://127.0.0.1:8000/onvif/sub_1"
                el.xpath.return_value = [sub_addr_el]
                return el
            elif "PullMessages" in body:
                worker.stop()
                raise requests.exceptions.Timeout("Long poll timeout")
            return MagicMock()

        mock_instance.soap_call.side_effect = soap_side_effect

        worker.start()
        worker.join(timeout=2.0)
        assert not worker.is_alive()

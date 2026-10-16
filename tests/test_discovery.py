"""Unit tests for native ONVIF WS-Discovery engine and scanner dialog."""

import xml.etree.ElementTree as ET
from PySide6.QtWidgets import QApplication

from onvif_capture.discovery import (
    DiscoveredCamera,
    build_probe_envelope,
    parse_probe_matches,
    _parse_probe_matches_regex,
)
from onvif_capture.gui.scanner_dialog import DeviceScannerDialog


SAMPLE_PROBE_MATCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <s:Header>
    <wsa:MessageID>uuid:00000000-0000-1000-4122-000000000000</wsa:MessageID>
    <wsa:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>
  </s:Header>
  <s:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <wsa:EndpointReference>
          <wsa:Address>urn:uuid:00000000-0000-1000-4122-000000000000</wsa:Address>
        </wsa:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter tds:Device</d:Types>
        <d:Scopes>
          onvif://www.onvif.org/location/country/Local
          onvif://www.onvif.org/name/NetworkCamera
          onvif://www.onvif.org/hardware/SmartCamera
          onvif://www.onvif.org/Profile/Streaming
          onvif://www.onvif.org/Profile/T
          onvif://www.onvif.org/Profile/G
          onvif://www.onvif.org/Profile/M
        </d:Scopes>
        <d:XAddrs>http://192.169.1.222:8000/onvif/device_service</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </s:Body>
</s:Envelope>
"""

SAMPLE_NON_ONVIF_XML = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
               xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery"
               xmlns:wsdp="http://schemas.xmlsoap.org/ws/2006/02/devprof">
  <soap:Header>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>
  </soap:Header>
  <soap:Body>
    <wsd:ProbeMatches>
      <wsd:ProbeMatch>
        <wsa:EndpointReference>
          <wsa:Address>urn:uuid:a1da569f-5627-43a9-96f6-a05986be4573</wsa:Address>
        </wsa:EndpointReference>
        <wsd:Types>wsdp:Device pub:Computer</wsd:Types>
        <wsd:XAddrs>http://pvn_nas:5357/a1da569f-5627-43a9-96f6-a05986be4573</wsd:XAddrs>
      </wsd:ProbeMatch>
    </wsd:ProbeMatches>
  </soap:Body>
</soap:Envelope>
"""


def test_build_probe_envelope():
    xml_str = build_probe_envelope()
    assert "NetworkVideoTransmitter" in xml_str
    assert "http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe" in xml_str
    # Must be valid XML
    root = ET.fromstring(xml_str)
    assert root is not None


def test_parse_probe_matches_onvif_camera():
    cams = parse_probe_matches(SAMPLE_PROBE_MATCH_XML, fallback_ip="192.169.1.222")
    assert len(cams) == 1
    cam = cams[0]
    assert cam.ip == "192.169.1.222"
    assert cam.port == 8000
    assert cam.name == "NetworkCamera"
    assert cam.hardware == "SmartCamera"
    assert cam.display_name == "SmartCamera - NetworkCamera"
    assert cam.has_profile_m is True
    assert "Profile M" in cam.profiles
    assert "Profile T" in cam.profiles
    assert "http://192.169.1.222:8000/onvif/device_service" in cam.xaddrs


def test_parse_probe_matches_ignores_non_onvif():
    cams = parse_probe_matches(SAMPLE_NON_ONVIF_XML, fallback_ip="192.169.3.3")
    assert len(cams) == 0  # Computer / NAS WSD device ignored!


def test_parse_probe_matches_regex_fallback():
    # Strip some closing tags to test robust regex fallback
    corrupted_xml = SAMPLE_PROBE_MATCH_XML.replace("</s:Envelope>", "")
    cams = _parse_probe_matches_regex(corrupted_xml, fallback_ip="192.169.1.222")
    assert len(cams) == 1
    assert cams[0].ip == "192.169.1.222"
    assert cams[0].port == 8000
    assert cams[0].hardware == "SmartCamera"


def test_scanner_dialog_ui_and_selection(qapp):
    dlg = DeviceScannerDialog()
    # Stop background thread in unit test
    dlg._stop_and_cleanup()

    # Verify table columns
    assert dlg.table.columnCount() == 5
    assert dlg.table.horizontalHeaderItem(0).text() == "IP Address"

    # Simulate camera discovered live
    cam1 = DiscoveredCamera(
        ip="192.169.1.64",
        port=8000,
        xaddrs=["http://192.169.1.64:8000/onvif/device_service"],
        name="NetworkCamera",
        hardware="SmartCamera",
        profiles=["Profile M", "Profile T"],
    )
    dlg._on_camera_found(cam1)

    assert dlg.table.rowCount() == 1
    assert dlg.table.item(0, 0).text() == "192.169.1.64"
    assert dlg.table.item(0, 1).text() == "8000"
    assert "SmartCamera" in dlg.table.item(0, 2).text()
    assert "Profile M" in dlg.table.item(0, 3).text()

    # Test search filtering
    dlg.search_edit.setText("NonExistent")
    assert dlg.table.isRowHidden(0) is True
    dlg.search_edit.setText("192.169")
    assert dlg.table.isRowHidden(0) is False

    # Test selection
    dlg.table.selectRow(0)
    assert dlg.connect_btn.isEnabled() is True
    assert dlg.connect_btn.text() == "Select and Connect"
    assert dlg.selected_camera() == cam1

    # Test numerical IP address sorting
    cam2 = DiscoveredCamera(
        ip="192.169.1.9",
        port=80,
        xaddrs=["http://192.169.1.9:80/onvif/device_service"],
        name="Cam 9",
        hardware="GenericVendor",
    )
    cam3 = DiscoveredCamera(
        ip="192.169.1.140",
        port=8000,
        xaddrs=["http://192.169.1.140:8000/onvif/device_service"],
        name="Cam 140",
        hardware="GenericVendor",
    )
    dlg._on_camera_found(cam2)
    dlg._on_camera_found(cam3)
    assert dlg.table.rowCount() == 3

    # Table is auto-sorted on each discovery append: 192.169.1.9 < 192.169.1.64 < 192.169.1.140
    auto_sorted_ips = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
    assert auto_sorted_ips == ["192.169.1.9", "192.169.1.64", "192.169.1.140"]

    # Test camera_selected signal
    selected_event = []
    dlg.camera_selected.connect(lambda c: selected_event.append(c))
    dlg._on_connect_clicked()
    assert len(selected_event) == 1
    assert selected_event[0].ip == "192.169.1.64"


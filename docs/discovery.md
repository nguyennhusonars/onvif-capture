# WS-Discovery Device Discovery Protocol

## 1. Overview

The application incorporates a native, zero-dependency Python implementation of the **OASIS WS-Discovery (Web Services Dynamic Discovery)** standard to automatically discover ONVIF IP cameras on the local network without requiring manual IP entry.

---

## 2. Multicast Probe Transmission

### Network Transport
* **Protocol:** UDP Multicast
* **Multicast IP:** `239.255.255.250`
* **Port:** `3702`
* **Socket Options:** `SO_BROADCAST`, `IP_MULTICAST_TTL = 4`

### Probe SOAP Envelope
The scanner transmits a SOAP 1.2 probe targeting standard ONVIF device contract types:

```xml
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
               xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
               xmlns:dn="http://www.onvif.org/ver10/network/wsdl"
               xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
  <soap:Header>
    <wsa:MessageID>urn:uuid:7a9c84e1-23d9-4820-a612-4f6c8d769123</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
  </soap:Header>
  <soap:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter tds:Device</d:Types>
    </d:Probe>
  </soap:Body>
</soap:Envelope>
```

---

## 3. Response Parsing & Profile Extraction

### 3.1 Endpoint and Scopes Extraction
When an ONVIF camera receives the probe, it responds with a unicast UDP packet containing `d:ProbeMatches`:
* **`d:XAddrs`:** Space-delimited URLs pointing to the device service endpoint (e.g. `http://192.169.1.64:8000/onvif/device_service`).
* **`d:Scopes`:** Space-delimited list of ONVIF scopes describing profiles, hardware, and location.

### 3.2 ONVIF Profile Detection
The parser checks `d:Scopes` for standardized profile identifiers:
* `onvif://www.onvif.org/Profile/M` &rarr; Profile M (Native AI Metadata & Analytics)
* `onvif://www.onvif.org/Profile/T` &rarr; Profile T (Advanced Video Streaming / H.265)
* `onvif://www.onvif.org/Profile/S` &rarr; Profile S (Basic Video Streaming)
* `onvif://www.onvif.org/Profile/G` &rarr; Profile G (Edge Storage & Retrieval)

Cameras supporting Profile M are highlighted with green badge indicators and bold styling in the scanner table.

---

## 4. Natural Numerical Sorting Algorithm

In standard Qt tables, sorting strings compares ASCII character codes lexicographically. This incorrectly orders IP addresses:
```text
192.169.1.140  <-- Incorrectly placed before .9
192.169.1.9
```

### Numerical IP Table Widget Item
To guarantee natural numerical ordering, `IPTableWidgetItem` subclasses `QTableWidgetItem` and overrides `__lt__` using Python's standard `ipaddress` module:

```python
class IPTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other: Any) -> bool:
        try:
            return ipaddress.ip_address(self.text().strip()) < ipaddress.ip_address(other.text().strip())
        except Exception:
            return super().__lt__(other)
```

Similarly, `NumericTableWidgetItem` parses integers to sort port numbers numerically.

---

## 5. UI Integration & Selection Flow

1. Clicking **Scan Network** in the top bar launches `DeviceScannerDialog`.
2. A background `DiscoveryWorker(QThread)` sends the multicast probe and emits `camera_found` signals.
3. During item insertion, row widgets are populated with `IPTableWidgetItem` and the table immediately and automatically sorts by the active header indicator (defaulting to Column 0: IP Address ascending) without requiring manual column clicks.
4. If a search filter query is active, visibility is dynamically recalculated post-sort.
5. Selecting a row enables **Select and Connect**, which populates the host, port, and service endpoints in the main window and initiates connection.


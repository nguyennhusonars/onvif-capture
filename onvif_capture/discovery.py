"""Native zero-dependency ONVIF WS-Discovery engine for camera network discovery."""

import re
import socket
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
import xml.etree.ElementTree as ET


@dataclass
class DiscoveredCamera:
    """Represents an ONVIF camera discovered via WS-Discovery Probe."""

    ip: str
    port: int
    xaddrs: List[str]
    name: str = ""
    hardware: str = ""
    location: str = ""
    profiles: List[str] = field(default_factory=list)
    types: List[str] = field(default_factory=list)
    endpoint_reference: str = ""

    @property
    def display_name(self) -> str:
        parts = []
        if self.hardware:
            parts.append(self.hardware)
        if self.name and self.name != self.hardware:
            parts.append(self.name)
        return " - ".join(parts) if parts else "ONVIF Camera"

    @property
    def profile_summary(self) -> str:
        if not self.profiles:
            return "-"
        letters = []
        for p in self.profiles:
            raw = p.replace("Profile", "").strip()
            if raw.lower() == "streaming":
                raw = "S"
            if raw and raw not in letters:
                letters.append(raw)
        if not letters:
            return "-"
        order_map = {"M": 0, "T": 1, "G": 2, "S": 3, "C": 4, "A": 5, "D": 6, "Q": 7}
        letters.sort(key=lambda x: order_map.get(x.upper(), 99))
        return f"Profile {', '.join(letters)}"

    @property
    def has_profile_m(self) -> bool:
        return any("m" in p.lower() for p in self.profiles)


def build_probe_envelope() -> str:
    """Build a standard ONVIF WS-Discovery Probe XML envelope."""
    msg_id = f"urn:uuid:{uuid.uuid4()}"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Envelope xmlns="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
        'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
        'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">\n'
        "  <Header>\n"
        f"    <wsa:MessageID>{msg_id}</wsa:MessageID>\n"
        "    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>\n"
        "    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>\n"
        "  </Header>\n"
        "  <Body>\n"
        "    <d:Probe>\n"
        "      <d:Types>dn:NetworkVideoTransmitter</d:Types>\n"
        "    </d:Probe>\n"
        "  </Body>\n"
        "</Envelope>"
    )


def parse_probe_matches(raw_xml: str, fallback_ip: str = "") -> List[DiscoveredCamera]:
    """Parse WS-Discovery ProbeMatches SOAP XML and return discovered cameras."""
    cameras: List[DiscoveredCamera] = []
    if not raw_xml or "ProbeMatch" not in raw_xml:
        return cameras

    try:
        root = ET.fromstring(raw_xml)
    except Exception:
        # Fallback to regex extraction if XML has minor encoding or namespace issues
        return _parse_probe_matches_regex(raw_xml, fallback_ip)

    # Search for all ProbeMatch elements across namespace variations
    for el in root.iter():
        if el.tag.endswith("ProbeMatch") and not el.tag.endswith("ProbeMatches"):
            cam = _extract_camera_from_element(el, fallback_ip)
            if cam:
                cameras.append(cam)

    return cameras


def _extract_camera_from_element(match_el: ET.Element, fallback_ip: str) -> Optional[DiscoveredCamera]:
    xaddrs_text = ""
    types_text = ""
    scopes_text = ""
    endpoint_ref = ""

    for child in match_el.iter():
        tag = child.tag.split("}")[-1]
        text = (child.text or "").strip()
        if tag == "XAddrs":
            xaddrs_text = text
        elif tag == "Types":
            types_text = text
        elif tag == "Scopes":
            scopes_text = text
        elif tag == "Address" and not endpoint_ref:
            endpoint_ref = text

    # Filter out non-ONVIF devices (e.g. Windows/NAS WSD computers on port 5357)
    is_onvif = (
        "networkvideotransmitter" in types_text.lower()
        or "onvif" in scopes_text.lower()
        or "/onvif/" in xaddrs_text.lower()
    )
    if not is_onvif:
        return None

    xaddrs = [x.strip() for x in xaddrs_text.split() if x.strip()]
    ip = fallback_ip
    port = 80

    for x in xaddrs:
        try:
            parsed = urllib.parse.urlparse(x)
            if parsed.hostname:
                ip = parsed.hostname
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                break
        except Exception:
            continue

    if not ip:
        return None

    # Parse Scopes
    name = ""
    hardware = ""
    location = ""
    profiles = []

    for scope in scopes_text.split():
        s = scope.strip()
        if "onvif://www.onvif.org/name/" in s:
            name = urllib.parse.unquote(s.split("onvif://www.onvif.org/name/")[-1])
        elif "onvif://www.onvif.org/hardware/" in s:
            hardware = urllib.parse.unquote(s.split("onvif://www.onvif.org/hardware/")[-1])
        elif "onvif://www.onvif.org/location/" in s:
            location = urllib.parse.unquote(s.split("onvif://www.onvif.org/location/")[-1])
        elif "onvif://www.onvif.org/Profile/" in s:
            p_name = urllib.parse.unquote(s.split("onvif://www.onvif.org/Profile/")[-1]).strip()
            if "/" in p_name:
                continue
            if f"Profile {p_name}" not in profiles:
                profiles.append(f"Profile {p_name}")

    types_list = [t.strip() for t in types_text.split() if t.strip()]

    return DiscoveredCamera(
        ip=ip,
        port=port,
        xaddrs=xaddrs,
        name=name,
        hardware=hardware,
        location=location,
        profiles=profiles,
        types=types_list,
        endpoint_reference=endpoint_ref,
    )


def _parse_probe_matches_regex(raw_xml: str, fallback_ip: str) -> List[DiscoveredCamera]:
    """Resilient regex-based parser when XML parser encounters malformed elements."""
    cameras: List[DiscoveredCamera] = []
    matches = re.findall(r"<[^:]*:?ProbeMatch\b[^>]*>(.*?)</[^:]*:?ProbeMatch>", raw_xml, re.DOTALL | re.IGNORECASE)
    if not matches:
        return cameras

    for block in matches:
        xaddrs_m = re.search(r"<[^:]*:?XAddrs[^>]*>(.*?)</[^:]*:?XAddrs>", block, re.DOTALL | re.IGNORECASE)
        xaddrs_text = xaddrs_m.group(1).strip() if xaddrs_m else ""

        scopes_m = re.search(r"<[^:]*:?Scopes[^>]*>(.*?)</[^:]*:?Scopes>", block, re.DOTALL | re.IGNORECASE)
        scopes_text = scopes_m.group(1).strip() if scopes_m else ""

        types_m = re.search(r"<[^:]*:?Types[^>]*>(.*?)</[^:]*:?Types>", block, re.DOTALL | re.IGNORECASE)
        types_text = types_m.group(1).strip() if types_m else ""

        ep_m = re.search(r"<[^:]*:?Address[^>]*>(.*?)</[^:]*:?Address>", block, re.DOTALL | re.IGNORECASE)
        endpoint_ref = ep_m.group(1).strip() if ep_m else ""

        xaddrs = [x.strip() for x in xaddrs_text.split() if x.strip()]
        ip = fallback_ip
        port = 80
        for x in xaddrs:
            try:
                parsed = urllib.parse.urlparse(x)
                if parsed.hostname:
                    ip = parsed.hostname
                    port = parsed.port or (443 if parsed.scheme == "https" else 80)
                    break
            except Exception:
                continue

        if not ip:
            continue

        name = ""
        hardware = ""
        location = ""
        profiles = []

        for scope in scopes_text.split():
            s = scope.strip()
            if "onvif://www.onvif.org/name/" in s:
                name = urllib.parse.unquote(s.split("onvif://www.onvif.org/name/")[-1])
            elif "onvif://www.onvif.org/hardware/" in s:
                hardware = urllib.parse.unquote(s.split("onvif://www.onvif.org/hardware/")[-1])
            elif "onvif://www.onvif.org/location/" in s:
                location = urllib.parse.unquote(s.split("onvif://www.onvif.org/location/")[-1])
            elif "onvif://www.onvif.org/Profile/" in s:
                p_name = urllib.parse.unquote(s.split("onvif://www.onvif.org/Profile/")[-1]).strip()
                if "/" in p_name:
                    continue
                if f"Profile {p_name}" not in profiles:
                    profiles.append(f"Profile {p_name}")

        cameras.append(
            DiscoveredCamera(
                ip=ip,
                port=port,
                xaddrs=xaddrs,
                name=name,
                hardware=hardware,
                location=location,
                profiles=profiles,
                types=[t.strip() for t in types_text.split() if t.strip()],
                endpoint_reference=endpoint_ref,
            )
        )

    return cameras


def ws_discovery_scan(
    timeout: float = 4.0,
    on_camera_found: Optional[Callable[[DiscoveredCamera], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
) -> List[DiscoveredCamera]:
    """Execute a native WS-Discovery UDP multicast scan and stream results live.

    Args:
        timeout: Total time in seconds to listen for camera responses (default 4.0s).
        on_camera_found: Optional callback invoked immediately whenever a new camera is found.
        stop_check: Optional callback returning True if scan should abort early.

    Returns:
        List of unique DiscoveredCamera objects found.
    """
    discovered: Dict[str, DiscoveredCamera] = {}
    probe_msg = build_probe_envelope().encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.5)

    try:
        # Multicast to standard WS-Discovery group
        sock.sendto(probe_msg, ("239.255.255.250", 3702))

        start_time = time.time()
        while time.time() - start_time < timeout:
            if stop_check and stop_check():
                break

            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except Exception:
                break

            raw_text = data.decode("utf-8", errors="ignore")
            if "ProbeMatch" not in raw_text:
                continue

            cams = parse_probe_matches(raw_text, fallback_ip=addr[0])
            for cam in cams:
                key = f"{cam.ip}:{cam.port}"
                if key not in discovered:
                    discovered[key] = cam
                    if on_camera_found:
                        on_camera_found(cam)

    finally:
        sock.close()

    return list(discovered.values())

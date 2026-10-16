import hashlib
import queue
import re
import socket
import struct
import subprocess
import threading
import time
from typing import Callable, List, Optional, Tuple
from urllib.parse import quote, urlparse

import requests

from .client import ONVIFProfileMClient
from .models import CapturedMetadataItem
from .parsers import parse_metadata_stream_xml, parse_notification_element


class RTSPMetadataStreamWorker(threading.Thread):
    """
    Background worker that connects to an RTSP stream's `vnd.onvif.metadata` track
    over interleaved TCP (RFC 2326), reassembles RTP payloads via the RTP Marker bit
    and XML end-tag detection, and parses XML on a decoupled consumer thread so the
    socket reader never drops or stalls during large Base64 snapshot frames.
    """

    def __init__(
        self,
        rtsp_uri: str,
        username: str,
        password: str,
        on_items: Callable[[List[CapturedMetadataItem]], None],
        on_status: Callable[[str], None],
        before_connect: Optional[Callable[[], None]] = None,
    ):
        super().__init__(daemon=True)
        self.rtsp_uri = rtsp_uri
        self.username = username
        self.password = password
        self.on_items = on_items
        self.on_status = on_status
        self.before_connect = before_connect
        self._stop_event = threading.Event()
        self._xml_queue: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=512)
        self._parser_thread = threading.Thread(target=self._parser_loop, daemon=True)

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._xml_queue.put_nowait(None)
        except queue.Full:
            pass

    def _parser_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                raw_xml_bytes = self._xml_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if raw_xml_bytes is None:
                break
            try:
                parsed_items = parse_metadata_stream_xml(raw_xml_bytes)
                if parsed_items:
                    self.on_items(parsed_items)
            except Exception:
                pass

    def _make_digest_header(self, method: str, uri: str, realm: str, nonce: str) -> str:
        ha1 = hashlib.md5(f"{self.username}:{realm}:{self.password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        resp = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
        return (
            f'Authorization: Digest username="{self.username}", realm="{realm}", '
            f'nonce="{nonce}", uri="{uri}", response="{resp}"\r\n'
        )

    def run(self) -> None:
        self._parser_thread.start()
        parsed = urlparse(self.rtsp_uri)
        host = parsed.hostname or "192.169.1.197"
        port = parsed.port or 554
        base_uri = f"rtsp://{host}:{port}{parsed.path or '/stream0'}"

        while not self._stop_event.is_set():
            sock: Optional[socket.socket] = None
            try:
                if self.before_connect:
                    try:
                        self.before_connect()
                    except Exception:
                        pass
                self.on_status(f"Connecting RTSP metadata: {base_uri} ...")
                sock = socket.create_connection((host, port), timeout=5.0)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
                except Exception:
                    pass
                cseq = 0
                realm = ""
                nonce = ""

                def send_rtsp(method: str, uri: str, extra_headers: str = "") -> Tuple[str, bytes]:
                    nonlocal cseq, realm, nonce
                    cseq += 1
                    auth = self._make_digest_header(method, uri, realm, nonce) if (realm and nonce) else ""
                    req = f"{method} {uri} RTSP/1.0\r\nCSeq: {cseq}\r\nUser-Agent: ONVIFProfileMInspector/1.0\r\n{auth}{extra_headers}\r\n"
                    sock.sendall(req.encode())
                    data = b""
                    while b"\r\n\r\n" not in data:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    header_part, remainder = data.split(b"\r\n\r\n", 1) if b"\r\n\r\n" in data else (data, b"")
                    header_txt = header_part.decode(errors="replace")

                    m_cl = re.search(r"Content-Length:\s*(\d+)", header_txt, re.IGNORECASE)
                    if m_cl:
                        cl = int(m_cl.group(1))
                        while len(remainder) < cl:
                            chunk = sock.recv(4096)
                            if not chunk:
                                break
                            remainder += chunk
                        body_txt = remainder[:cl].decode(errors="replace")
                        header_txt = header_txt + "\r\n\r\n" + body_txt
                        remainder = remainder[cl:]

                    if "401 Unauthorized" in header_txt:
                        m_r = re.search(r'realm="([^"]+)"', header_txt)
                        m_n = re.search(r'nonce="([^"]+)"', header_txt)
                        if m_r and m_n:
                            realm, nonce = m_r.group(1), m_n.group(1)
                            return send_rtsp(method, uri, extra_headers)
                    return header_txt, remainder

                desc_txt, _ = send_rtsp("DESCRIBE", base_uri, "Accept: application/sdp\r\n")
                if "200 OK" not in desc_txt:
                    raise RuntimeError(f"RTSP DESCRIBE failed: {desc_txt.splitlines()[0] if desc_txt else 'empty'}")

                metadata_control = f"{base_uri}/metadata"
                in_meta = False
                for line in desc_txt.splitlines():
                    line = line.strip()
                    if line.startswith("m=application"):
                        in_meta = True
                    elif line.startswith("m="):
                        in_meta = False
                    elif in_meta and line.startswith("a=control:"):
                        ctrl = line.split("a=control:", 1)[1].strip()
                        metadata_control = (
                            ctrl if ctrl.startswith("rtsp://") else f"{base_uri.rstrip('/')}/{ctrl.lstrip('/')}"
                        )
                        break

                setup_txt, _ = send_rtsp(
                    "SETUP",
                    metadata_control,
                    "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n",
                )
                if "200 OK" not in setup_txt:
                    raise RuntimeError(f"RTSP SETUP failed: {setup_txt.splitlines()[0] if setup_txt else 'empty'}")

                sess_id = ""
                for line in setup_txt.splitlines():
                    if line.lower().startswith("session:"):
                        sess_id = line.split(":", 1)[1].split(";")[0].strip()
                        break

                play_txt, buf = send_rtsp(
                    "PLAY",
                    base_uri,
                    f"Session: {sess_id}\r\nRange: npt=0.000-\r\n",
                )
                if "200 OK" not in play_txt:
                    raise RuntimeError(f"RTSP PLAY failed: {play_txt.splitlines()[0] if play_txt else 'empty'}")

                self.on_status(f"RTSP metadata active ({metadata_control})")
                sock.settimeout(2.0)
                xml_accumulator = bytearray()
                last_keepalive = time.time()

                while not self._stop_event.is_set():
                    if time.time() - last_keepalive > 20.0:
                        cseq += 1
                        auth = (
                            self._make_digest_header("GET_PARAMETER", base_uri, realm, nonce)
                            if (realm and nonce)
                            else ""
                        )
                        ka_req = (
                            f"GET_PARAMETER {base_uri} RTSP/1.0\r\nCSeq: {cseq}\r\nSession: {sess_id}\r\n{auth}\r\n"
                        )
                        sock.sendall(ka_req.encode())
                        last_keepalive = time.time()

                    try:
                        chunk = sock.recv(65536)
                        if not chunk:
                            raise ConnectionError("RTSP metadata socket closed by camera")
                        buf += chunk
                    except socket.timeout:
                        continue

                    while len(buf) >= 4:
                        if buf[0:1] != b"$":
                            # Wait if a partial "RTSP/1.0" header is arriving at the buffer boundary
                            if b"RTSP/1.0".startswith(buf[:8]) and len(buf) < 8:
                                break
                            if buf.startswith(b"RTSP/1.0"):
                                end_idx = buf.find(b"\r\n\r\n")
                                if end_idx == -1:
                                    break
                                hdr_bytes = buf[:end_idx].decode(errors="replace")
                                body_len = 0
                                m_cl = re.search(r"Content-Length:\s*(\d+)", hdr_bytes, re.IGNORECASE)
                                if m_cl:
                                    body_len = int(m_cl.group(1))
                                total_rtsp_len = end_idx + 4 + body_len
                                if len(buf) < total_rtsp_len:
                                    break
                                buf = buf[total_rtsp_len:]
                                continue
                            dollar_idx = buf.find(b"$")
                            if dollar_idx == -1:
                                buf = b""
                                break
                            buf = buf[dollar_idx:]
                            if len(buf) < 4:
                                break

                        channel = buf[1]
                        pkt_len = struct.unpack("!H", buf[2:4])[0]
                        if len(buf) < 4 + pkt_len:
                            break
                        pkt = buf[4 : 4 + pkt_len]
                        buf = buf[4 + pkt_len :]

                        if channel == 0 and len(pkt) > 12:
                            cc = pkt[0] & 0x0F
                            extension = (pkt[0] >> 4) & 0x01
                            marker = (pkt[1] >> 7) & 0x01
                            header_len = 12 + cc * 4
                            if extension and len(pkt) >= header_len + 4:
                                ext_len = struct.unpack("!H", pkt[header_len + 2 : header_len + 4])[0] * 4
                                header_len += 4 + ext_len

                            if len(pkt) > header_len:
                                xml_accumulator.extend(pkt[header_len:])

                            while True:
                                end_match = re.search(rb"</(?:\w+:)?MetadataStream>", xml_accumulator)
                                if not end_match:
                                    break
                                end_pos = end_match.end()
                                complete_frame = bytes(xml_accumulator[:end_pos])
                                del xml_accumulator[:end_pos]
                                try:
                                    self._xml_queue.put_nowait(complete_frame)
                                except queue.Full:
                                    pass

            except Exception as exc:
                if not self._stop_event.is_set():
                    self.on_status(f"RTSP metadata reconnecting ({exc})...")
                    time.sleep(1.5)
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass


class ONVIFPullPointWorker(threading.Thread):
    """
    Background worker that subscribes to the ONVIF PullPoint event service via direct
    WS-Security Digest SOAP, automatically renews the subscription (`wsnt:Renew`) before
    the camera's 3-minute `TerminationTime` expires, and parses full `<wsnt:NotificationMessage>`
    XML (avoiding zeep's `TopicExpressionType` `_value_1 = None` bug).
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        on_items: Callable[[List[CapturedMetadataItem]], None],
        on_status: Callable[[str], None],
    ):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.on_items = on_items
        self.on_status = on_status
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        client = ONVIFProfileMClient(self.host, self.port, self.username, self.password)
        event_service_url = f"http://{self.host}:{self.port}/onvif/event_service"

        while not self._stop_event.is_set():
            sub_addr: Optional[str] = None
            try:
                self.on_status(f"Subscribing ONVIF PullPoint ({self.host}:{self.port})...")
                sub_resp = client.soap_call(
                    event_service_url,
                    "<tev:CreatePullPointSubscription><tev:InitialTerminationTime>PT600S</tev:InitialTerminationTime></tev:CreatePullPointSubscription>",
                    timeout=5.0,
                )
                addr_els = sub_resp.xpath(".//*[local-name()='Address']")
                if not addr_els or not addr_els[0].text:
                    raise RuntimeError("No SubscriptionReference Address returned by camera")
                sub_addr = addr_els[0].text.strip()
                self.on_status(f"ONVIF PullPoint active ({sub_addr.split('/')[-1]})")
                last_renew = time.time()

                consecutive_errors = 0
                while not self._stop_event.is_set():
                    # Renew every 60s so the camera's 180s subscription lease never expires
                    if time.time() - last_renew > 60.0:
                        try:
                            client.soap_call(
                                sub_addr,
                                "<wsnt:Renew><wsnt:TerminationTime>PT600S</wsnt:TerminationTime></wsnt:Renew>",
                                timeout=5.0,
                            )
                            last_renew = time.time()
                        except Exception as renew_exc:
                            err_msg = str(renew_exc).lower()
                            if "404" in err_msg or "not found" in err_msg or "fault" in err_msg:
                                raise

                    try:
                        pull_resp = client.soap_call(
                            sub_addr,
                            "<tev:PullMessages><tev:Timeout>PT3S</tev:Timeout><tev:MessageLimit>100</tev:MessageLimit></tev:PullMessages>",
                            timeout=8.0,
                        )
                        consecutive_errors = 0
                        notifs = pull_resp.xpath(".//*[local-name()='NotificationMessage']")
                        if notifs:
                            batch: List[CapturedMetadataItem] = []
                            for notif_el in notifs:
                                batch.extend(parse_notification_element(notif_el, channel="ONVIF PullPoint"))
                            if batch:
                                self.on_items(batch)
                    except (requests.exceptions.Timeout, socket.timeout):
                        # Normal long-polling timeout when camera has no messages to return; keep subscription alive
                        continue
                    except Exception as poll_exc:
                        err_str = str(poll_exc).lower()
                        if "404" in err_str or "not found" in err_str or "fault" in err_str or "invalid" in err_str:
                            raise
                        consecutive_errors += 1
                        if consecutive_errors >= 3:
                            raise
                        time.sleep(0.5)

            except Exception as exc:
                if not self._stop_event.is_set():
                    self.on_status(f"PullPoint reconnecting ({exc})...")
                    time.sleep(1.0)
            finally:
                if sub_addr:
                    try:
                        client.soap_call(sub_addr, "<wsnt:Unsubscribe/>", timeout=2.0)
                    except Exception:
                        pass


class RTSPVideoPreviewWorker(threading.Thread):
    """Decodes RTSP video stream via ffmpeg subprocess into RGB24 frames for zero-conflict Qt rendering."""

    def __init__(
        self,
        rtsp_uri: str,
        username: str,
        password: str,
        out_width: int,
        out_height: int,
        on_rgb_frame: Callable[[bytes, int, int], None],
        on_status: Callable[[str], None],
    ):
        super().__init__(daemon=True)
        self.rtsp_uri = rtsp_uri
        self.username = username
        self.password = password
        self.out_width = out_width
        self.out_height = out_height
        self.on_rgb_frame = on_rgb_frame
        self.on_status = on_status
        self._stop_event = threading.Event()
        self._proc: Optional[subprocess.Popen] = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _build_auth_rtsp_url(self) -> str:
        parsed = urlparse(self.rtsp_uri)
        user_enc = quote(self.username, safe="")
        pwd_enc = quote(self.password, safe="")
        host = parsed.hostname or "192.169.1.197"
        port = parsed.port or 554
        path = parsed.path or "/stream0"
        return f"rtsp://{user_enc}:{pwd_enc}@{host}:{port}{path}"

    def run(self) -> None:
        auth_url = self._build_auth_rtsp_url()
        frame_bytes = self.out_width * self.out_height * 3

        while not self._stop_event.is_set():
            try:
                self.on_status(f"Starting RTSP video ({self.out_width}x{self.out_height})...")
                cmd = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-allowed_media_types",
                    "video",
                    "-rtsp_transport",
                    "tcp",
                    "-fflags",
                    "nobuffer",
                    "-flags",
                    "low_delay",
                    "-i",
                    auth_url,
                    "-an",
                    "-sn",
                    "-r",
                    "10",
                    "-vf",
                    f"scale={self.out_width}:{self.out_height}",
                    "-pix_fmt",
                    "rgb24",
                    "-f",
                    "rawvideo",
                    "pipe:1",
                ]
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=frame_bytes * 2,
                )
                self.on_status("RTSP video active")

                while not self._stop_event.is_set() and self._proc.stdout:
                    raw = self._proc.stdout.read(frame_bytes)
                    if len(raw) < frame_bytes:
                        break
                    self.on_rgb_frame(raw, self.out_width, self.out_height)

            except Exception as exc:
                if not self._stop_event.is_set():
                    self.on_status(f"Video error: {exc}")
            finally:
                if self._proc:
                    try:
                        self._proc.terminate()
                        self._proc.wait(timeout=1.0)
                    except Exception:
                        pass
                    self._proc = None

            if not self._stop_event.is_set():
                time.sleep(2.0)

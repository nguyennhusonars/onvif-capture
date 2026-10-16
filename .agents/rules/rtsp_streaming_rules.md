# RTSP Metadata & Video Streaming Rules

1. **RTSP HTTP Digest Authentication:**
   * The camera's RTSP server requires RFC 2617 Digest Authentication (`MD5(MD5(user:realm:pass):nonce:MD5(method:uri))`).
   * Always handle `401 Unauthorized` on `DESCRIBE` by extracting `realm` and `nonce` from `WWW-Authenticate` and signing subsequent `DESCRIBE`, `SETUP`, `PLAY`, and `GET_PARAMETER` requests.
2. **Interleaved TCP Transport (`RTP/AVP/TCP;unicast;interleaved=0-1`):**
   * Always use TCP interleaved mode for `rtsp://<ip>:554/stream0/metadata` (`a=rtpmap:98 vnd.onvif.metadata/90000`) to avoid UDP firewall/NAT drops and packet reordering.
   * Parse `$` (`0x24`) 4-byte framing headers (`$`, `channel_id`, `uint16_be length`) and strip the 12-byte RTP header (plus any CSRC or RTP header extension bytes) on channel `0`.
3. **RTP Marker Bit ($M = 1$) Multi-Packet XML Reassembly:**
   * A single `<tt:MetadataStream>` XML document—especially an event carrying `<tt:ElementItem Name="Image"><tt:base64Binary>` ($> 400\,\text{KB}$)—is fragmented across hundreds of RTP packets.
   * Accumulate RTP payload bytes in a buffer and only invoke `parse_metadata_stream_xml()` when the RTP Marker bit (`(pkt[1] >> 7) & 1`) equals `1`.
4. **Session Keepalive (`GET_PARAMETER`):**
   * The camera returns `Session: <id>;timeout=30` on `SETUP`. Send an authenticated `GET_PARAMETER` RTSP request every $20\,\text{s}$ and discard `RTSP/1.0 200 OK` headers in the TCP stream reader so the metadata stream never times out.


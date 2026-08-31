# core/addon.py
from . import *
from .utils import host_matches_any

class TextualMitmAddon:
    """
    Addon mitmproxy hỗ trợ 2 chế độ:
    - basic: response / error / websocket_message / tcp_message / tcp_error
    - full: toàn bộ lifecycle events
    """

    def __init__(self, app_instance):
        self.app = app_instance

    def _is_full_capture(self) -> bool:
        return getattr(self.app, "opt_capture_mode", "basic") == "full"

    def _send_to_app(self, data: dict) -> None:
        try:
            self.app.call_from_thread(self.app.add_proxy_record, data)
        except RuntimeError:
            pass

    def _row_key(self, flow, suffix: str | None = None) -> str:
        # mitmproxy.flow.Flow.id: unique UUID for this flow
        fid = getattr(flow, "id", "") or ""
        if suffix:
            return f"{fid}:{suffix}"
        return fid

    def _send_flow_record(self, flow, data: dict, suffix: str | None = None) -> None:
        data["flow_id"] = getattr(flow, "id", "") or ""
        data["row_key"] = self._row_key(flow, suffix)
        self._send_to_app(data)

    def _should_process(self, host: str) -> bool:
        # Cùng thứ tự NextLayer._ignore_connection:
        # allow_hosts trước (whitelist), ignore_hosts sau (blacklist).
        # List rỗng = không áp tầng đó.
        if not host:
            return True
        allowed = self.app.allowed_hosts
        ignored = self.app.ignored_hosts
        if allowed and not host_matches_any(host, allowed):
            return False
        if ignored and host_matches_any(host, ignored):
            return False
        return True

    def _get_client_ip(self, flow) -> str:
        try:
            if flow.client_conn and flow.client_conn.peername:
                return flow.client_conn.peername[0]
        except Exception:
            pass
        return "N/A"

    def _get_server_ip(self, flow) -> str:
        try:
            if flow.server_conn and flow.server_conn.peername:
                return flow.server_conn.peername[0]
            if flow.server_conn and flow.server_conn.address:
                return str(flow.server_conn.address[0])
        except Exception:
            pass
        return "N/A"

    def _detect_http_version(self, flow: http.HTTPFlow) -> str:
        raw = (flow.request.http_version or "").upper()
        if "HTTP/1" in raw:
            return "HTTP1"
        if "HTTP/2" in raw:
            return "HTTP2"
        if "HTTP/3" in raw:
            return "HTTP3"
        return "UNKNOWN"

    def _detect_mime(self, content_type: str) -> str:
        ct = (content_type or "").lower()
        if "json" in ct:
            return "JSON"
        if "xml" in ct:
            return "XML"
        if "html" in ct:
            return "HTML"
        if "javascript" in ct or "ecmascript" in ct:
            return "JS"
        if "text/" in ct:
            return "TEXT"
        if "image/" in ct:
            return "IMAGE"
        if "audio/" in ct or "video/" in ct:
            return "MEDIA"
        if "octet-stream" in ct:
            return "BINARY"
        return "UNKNOWN"

    def _format_size(self, num_bytes: int) -> str:
        if num_bytes is None or num_bytes <= 0:
            return "0 KB"
        kb = num_bytes / 1024
        if kb < 0.1:
            return f"{num_bytes} B"
        return f"{kb:.1f} KB"

    def _cookies_str(self, req) -> str:
        if not req or not req.cookies:
            return ""
        return "; ".join(f"{k}={v}" for k, v in req.cookies.items())

    # ------------------------------------------------------------------
    # HTTP – Full only
    # ------------------------------------------------------------------
    def requestheaders(self, flow: http.HTTPFlow) -> None:
        if not self._is_full_capture():
            return
        host = flow.request.pretty_host if flow.request else ""
        if not self._should_process(host):
            return
        try:
            req = flow.request
            data = {
                "host": host,
                "method": req.method,
                "url": req.pretty_url,
                "path": req.path,
                "status": "REQ",
                "length": "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": self._cookies_str(req),
                "req_headers": "\n".join(f"{k}: {v}" for k, v in req.headers.items()) if req.headers else "",
                "req_body": "",
                "res_headers": "",
                "res_body": "[Request Headers Only]",
                "protocol": req.scheme.upper() if req.scheme else "HTTP",
                "http_version": self._detect_http_version(flow),
                "mime_category": "UNKNOWN",
                "status_category": "REQ",
            }
            self._send_flow_record(flow, data)
        except Exception:
            pass

    def request(self, flow: http.HTTPFlow) -> None:
        if not self._is_full_capture():
            return
        host = flow.request.pretty_host if flow.request else ""
        if not self._should_process(host):
            return
        try:
            req = flow.request
            body = req.get_text(strict=False) or ""
            data = {
                "host": host,
                "method": req.method,
                "url": req.pretty_url,
                "path": req.path,
                "status": "REQ",
                "length": self._format_size(len(req.content)) if req.content else "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": self._cookies_str(req),
                "req_headers": "\n".join(f"{k}: {v}" for k, v in req.headers.items()) if req.headers else "",
                "req_body": body,
                "res_headers": "",
                "res_body": "[Full Request Captured]",
                "protocol": req.scheme.upper() if req.scheme else "HTTP",
                "http_version": self._detect_http_version(flow),
                "mime_category": "UNKNOWN",
                "status_category": "REQ",
            }
            self._send_flow_record(flow, data)
        except Exception:
            pass

    def responseheaders(self, flow: http.HTTPFlow) -> None:
        if not self._is_full_capture():
            return
        host = flow.request.pretty_host if flow.request else ""
        if not self._should_process(host):
            return
        try:
            req = flow.request
            res = flow.response
            content_type = res.headers.get("Content-Type", "") if res else ""
            data = {
                "host": host,
                "method": req.method,
                "url": req.pretty_url,
                "path": req.path,
                "status": str(res.status_code) if res else "N/A",
                "length": "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": self._cookies_str(req),
                "req_headers": "\n".join(f"{k}: {v}" for k, v in req.headers.items()) if req.headers else "",
                "req_body": "",
                "res_headers": "\n".join(f"{k}: {v}" for k, v in res.headers.items()) if res and res.headers else "",
                "res_body": "[Response Headers Only]",
                "protocol": req.scheme.upper() if req.scheme else "HTTP",
                "http_version": self._detect_http_version(flow),
                "mime_category": self._detect_mime(content_type),
                "status_category": f"{str(res.status_code)[0]}xx" if res else "ERR",
            }
            self._send_flow_record(flow, data)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # HTTP – Basic + Full
    # ------------------------------------------------------------------
    def response(self, flow: http.HTTPFlow) -> None:
        host = flow.request.pretty_host if flow.request else ""
        if not self._should_process(host):
            return
        try:
            req = flow.request
            res = flow.response
            content_type = res.headers.get("Content-Type", "").lower() if res else ""
            mime_category = self._detect_mime(content_type)
            status_category = f"{str(res.status_code)[0]}xx" if res else "ERR"

            req_body = req.get_text(strict=False) or ""
            res_body = ""
            if res:
                text_formats = ["text", "json", "xml", "javascript", "x-www-form-urlencoded", "html"]
                if any(fmt in content_type for fmt in text_formats) or not content_type:
                    res_body = res.get_text(strict=False) or ""
                else:
                    res_body = (
                        f"[[ DỮ LIỆU NHỊ PHÂN / MEDIA ]]\n"
                        f"Định dạng: {content_type}\n"
                        f"Dung lượng: {len(res.content) if res.content else 0} Bytes"
                    )

            data = {
                "host": host,
                "method": req.method,
                "url": req.pretty_url,
                "path": req.path,
                "status": str(res.status_code) if res else "N/A",
                "length": self._format_size(len(res.content)) if res and res.content else "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": self._cookies_str(req),
                "req_headers": "\n".join(f"{k}: {v}" for k, v in req.headers.items()) if req.headers else "",
                "req_body": req_body,
                "res_headers": "\n".join(f"{k}: {v}" for k, v in res.headers.items()) if res and res.headers else "",
                "res_body": res_body,
                "protocol": req.scheme.upper() if req.scheme else "HTTP",
                "http_version": self._detect_http_version(flow),
                "mime_category": mime_category,
                "status_category": status_category,
            }
            self._send_flow_record(flow, data)
        except Exception:
            pass

    def error(self, flow: http.HTTPFlow) -> None:
        host = flow.request.pretty_host if flow.request else ""
        if not self._should_process(host):
            return
        try:
            req = flow.request
            data = {
                "host": host or "Unknown",
                "method": req.method if req else "N/A",
                "url": req.pretty_url if req else "N/A",
                "path": req.path if req else "N/A",
                "status": "ERR",
                "length": "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": self._cookies_str(req) if req else "",
                "req_headers": "",
                "req_body": "",
                "res_headers": "",
                "res_body": f"HTTP Error: {flow.error}",
                "protocol": req.scheme.upper() if req and req.scheme else "HTTP",
                "http_version": "UNKNOWN",
                "mime_category": "UNKNOWN",
                "status_category": "ERR",
            }
            self._send_flow_record(flow, data)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------
    def websocket_start(self, flow: http.HTTPFlow) -> None:
        if not self._is_full_capture():
            return
        host = flow.request.pretty_host if flow.request else ""
        if not self._should_process(host):
            return
        try:
            data = {
                "host": host,
                "method": "WS",
                "url": flow.request.pretty_url,
                "path": flow.request.path,
                "status": "WS-START",
                "length": "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": "",
                "req_headers": "WebSocket Handshake Start",
                "req_body": "",
                "res_headers": "",
                "res_body": "[WebSocket Connection Started]",
                "protocol": "WEBSOCKET",
                "http_version": "UNKNOWN",
                "mime_category": "UNKNOWN",
                "status_category": "UNKNOWN",
            }
            # Cùng HTTPFlow.id với handshake HTTP — tách hàng, không đè request/response
            self._send_flow_record(flow, data, suffix="ws:start")
        except Exception:
            pass

    def websocket_message(self, flow: http.HTTPFlow) -> None:
        host = flow.request.pretty_host if flow.request else ""
        if not self._should_process(host):
            return
        if not flow.websocket or not flow.websocket.messages:
            return
        try:
            message = flow.websocket.messages[-1]
            direction = "C->S" if message.from_client else "S->C"
            data = {
                "host": host,
                "method": "WS",
                "url": flow.request.pretty_url,
                "path": f"[{direction}] {flow.request.path}",
                "status": "WS",
                "length": self._format_size(len(message.content)),
                "ip": self._get_server_ip(flow),
                "cookies": "",
                "req_headers": "WebSocket Message",
                "req_body": "",
                "res_headers": f"Hướng: {'Client → Server' if message.from_client else 'Server → Client'}",
                "res_body": message.content.decode("utf-8", errors="replace"),
                "protocol": "WEBSOCKET",
                "http_version": "UNKNOWN",
                "mime_category": "UNKNOWN",
                "status_category": "UNKNOWN",
            }
            self._send_flow_record(flow, data, suffix=f"ws:{len(flow.websocket.messages)}")
        except Exception:
            pass

    def websocket_end(self, flow: http.HTTPFlow) -> None:
        if not self._is_full_capture():
            return
        host = flow.request.pretty_host if flow.request else ""
        if not self._should_process(host):
            return
        try:
            close_code = getattr(flow.websocket, "close_code", None)
            data = {
                "host": host,
                "method": "WS",
                "url": flow.request.pretty_url if flow.request else "N/A",
                "path": flow.request.path if flow.request else "N/A",
                "status": "WS-END",
                "length": "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": "",
                "req_headers": "WebSocket Connection End",
                "req_body": "",
                "res_headers": "",
                "res_body": f"[WebSocket Ended] close_code={close_code}",
                "protocol": "WEBSOCKET",
                "http_version": "UNKNOWN",
                "mime_category": "UNKNOWN",
                "status_category": "UNKNOWN",
            }
            self._send_flow_record(flow, data, suffix="ws:end")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # TCP
    # ------------------------------------------------------------------
    def tcp_start(self, flow: tcp.TCPFlow) -> None:
        if not self._is_full_capture():
            return
        server_addr = flow.server_conn.address[0] if flow.server_conn and flow.server_conn.address else "Unknown"
        if not self._should_process(server_addr):
            return
        try:
            port = flow.server_conn.address[1] if flow.server_conn and flow.server_conn.address else 0
            data = {
                "host": server_addr,
                "method": "TCP",
                "url": f"tcp://{server_addr}:{port}",
                "path": "[TCP Start]",
                "status": "TCP-START",
                "length": "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": "",
                "req_headers": "TCP Connection Start",
                "req_body": "",
                "res_headers": "",
                "res_body": "[TCP Connection Started]",
                "protocol": "TCP",
                "http_version": "UNKNOWN",
                "mime_category": "BINARY",
                "status_category": "UNKNOWN",
            }
            self._send_flow_record(flow, data)
        except Exception:
            pass

    def tcp_message(self, flow: tcp.TCPFlow) -> None:
        server_addr = flow.server_conn.address[0] if flow.server_conn and flow.server_conn.address else "Unknown"
        if not self._should_process(server_addr):
            return
        if not flow.messages:
            return
        try:
            message = flow.messages[-1]
            direction = "C->S" if message.from_client else "S->C"
            port = flow.server_conn.address[1] if flow.server_conn and flow.server_conn.address else 0
            data = {
                "host": server_addr,
                "method": "TCP",
                "url": f"tcp://{server_addr}:{port}",
                "path": f"[{direction}] TCP Data",
                "status": "TCP",
                "length": self._format_size(len(message.content)),
                "ip": self._get_server_ip(flow),
                "cookies": "",
                "req_headers": "Raw TCP",
                "req_body": "",
                "res_headers": f"Hướng: {'Client → Server' if message.from_client else 'Server → Client'}",
                "res_body": message.content.decode("utf-8", errors="replace"),
                "protocol": "TCP",
                "http_version": "UNKNOWN",
                "mime_category": "BINARY",
                "status_category": "UNKNOWN",
            }
            self._send_flow_record(flow, data, suffix=f"tcp:{len(flow.messages)}")
        except Exception:
            pass

    def tcp_end(self, flow: tcp.TCPFlow) -> None:
        if not self._is_full_capture():
            return
        server_addr = flow.server_conn.address[0] if flow.server_conn and flow.server_conn.address else "Unknown"
        if not self._should_process(server_addr):
            return
        try:
            data = {
                "host": server_addr,
                "method": "TCP",
                "url": f"tcp://{server_addr}",
                "path": "[TCP End]",
                "status": "TCP-END",
                "length": "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": "",
                "req_headers": "TCP Connection End",
                "req_body": "",
                "res_headers": "",
                "res_body": "[TCP Connection Ended]",
                "protocol": "TCP",
                "http_version": "UNKNOWN",
                "mime_category": "BINARY",
                "status_category": "UNKNOWN",
            }
            self._send_flow_record(flow, data)
        except Exception:
            pass

    def tcp_error(self, flow: tcp.TCPFlow) -> None:
        server_addr = flow.server_conn.address[0] if flow.server_conn and flow.server_conn.address else "Unknown"
        if not self._should_process(server_addr):
            return
        try:
            data = {
                "host": server_addr,
                "method": "TCP",
                "url": f"tcp://{server_addr}",
                "path": "[TCP Error]",
                "status": "ERR",
                "length": "0 KB",
                "ip": self._get_server_ip(flow),
                "cookies": "",
                "req_headers": "",
                "req_body": "",
                "res_headers": "",
                "res_body": f"TCP Error: {flow.error}",
                "protocol": "TCP",
                "http_version": "UNKNOWN",
                "mime_category": "UNKNOWN",
                "status_category": "ERR",
            }
            self._send_flow_record(flow, data)
        except Exception:
            pass

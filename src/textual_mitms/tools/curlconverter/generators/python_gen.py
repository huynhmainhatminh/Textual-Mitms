# core/generators/python_gen.py
"""Sinh code Python từ IR curl: url, method, headers, auth, files_form, data_body."""

from urllib.parse import urlparse

from . import register_generator
from .utils import escape_string


def _get_headers(data: dict) -> dict:
    headers = data.get("headers") or {}
    return headers if isinstance(headers, dict) else {}


def _content_type(headers: dict) -> str:
    for key, value in headers.items():
        if str(key).lower() == "content-type":
            return "" if value is None else str(value).lower()
    return ""


def _py_str(value) -> str:
    """Literal chuỗi Python hợp lệ.

    Vẫn gọi escape_string theo convention dự án, rồi repr() để bảo vệ
    dấu nháy, newline và backslash — không bọc thủ công bằng "...".
    """
    if value is None:
        value = ""
    return repr(escape_string(str(value)))


def _py_dict(mapping: dict) -> str:
    """Dict Python. Không dùng json.dumps (null/true/false không phải Python)."""
    if not mapping:
        return "{}"
    inner = ",\n".join(f"    {_py_str(k)}: {_py_str(v)}" for k, v in mapping.items())
    return "{\n" + inner + ",\n}"


def _auth_pair(auth) -> tuple:
    if not auth:
        return "", ""
    user = auth[0] if len(auth) > 0 else ""
    password = auth[1] if len(auth) > 1 else ""
    return user, password


def _is_file_handle_expr(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith("open(") and stripped.endswith(")")


def _unwrap_quoted(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _emit_files_dict(files_form: dict) -> list:
    lines = ["files = {"]
    for key, raw in files_form.items():
        value = "" if raw is None else str(raw)
        if _is_file_handle_expr(value):
            lines.append(f"    {_py_str(key)}: {value},")
        else:
            lines.append(
                f"    {_py_str(key)}: (None, {_py_str(_unwrap_quoted(value))}),"
            )
    lines.append("}")
    return lines


def _common_request_setup(data: dict, lines: list) -> list:
    """URL, method, headers, Basic Auth, files/form, body.

    Khi có files_form thì không gắn data=payload: requests/httpx sẽ nhét
    data vào multipart và phá JSON/raw body.
    Body JSON giữ nguyên chuỗi + Content-Type; không dùng json= vì
    json= sẽ dumps thêm một lần nếu payload đã là document JSON.
    """
    url = data.get("url") or ""
    method = str(data.get("method") or "GET").upper()
    headers = _get_headers(data)
    auth = data.get("auth")
    files_form = data.get("files_form") or {}
    body = data.get("data_body") or ""

    lines.extend(["", f"url = {_py_str(url)}"])
    req_args = [_py_str(method), "url"]

    if headers:
        lines.append(f"headers = {_py_dict(headers)}")
        req_args.append("headers=headers")

    if auth:
        user, password = _auth_pair(auth)
        lines.append(f"auth = ({_py_str(user)}, {_py_str(password)})")
        req_args.append("auth=auth")

    if files_form:
        lines.extend(_emit_files_dict(files_form))
        req_args.append("files=files")
    elif body:
        lines.append(f"payload = {_py_str(body)}")
        req_args.append("data=payload")

    return req_args


@register_generator("requests")
def generate_requests(data: dict) -> str:
    lines = ["import requests"]
    req_args = _common_request_setup(data, lines)
    lines.extend(
        [
            "",
            f"response = requests.request({', '.join(req_args)})",
            "print(response.text)",
        ]
    )
    return "\n".join(lines)


@register_generator("httpx")
def generate_httpx(data: dict) -> str:
    lines = ["import httpx"]
    req_args = _common_request_setup(data, lines)
    lines.extend(
        [
            "",
            "with httpx.Client() as client:",
            f"    response = client.request({', '.join(req_args)})",
            "    print(response.text)",
        ]
    )
    return "\n".join(lines)


@register_generator("curl_cffi")
def generate_curl_cffi(data: dict) -> str:
    lines = ["from curl_cffi import requests"]
    req_args = _common_request_setup(data, lines)
    # Tiện ích thư viện, không phải flag curl.
    req_args.append("impersonate='chrome110'")
    lines.extend(
        [
            "",
            f"response = requests.request({', '.join(req_args)})",
            "print(response.text)",
        ]
    )
    return "\n".join(lines)


@register_generator("http_client")
def generate_http_client(data: dict) -> str:
    lines = ["import http.client"]
    auth = data.get("auth")
    if auth:
        lines.append("import base64")

    parsed = urlparse(data.get("url") or "")
    scheme = (parsed.scheme or "https").lower()
    host = parsed.hostname or ""
    host_arg = f"{host}:{parsed.port}" if parsed.port else host
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    conn_cls = (
        "http.client.HTTPConnection"
        if scheme == "http"
        else "http.client.HTTPSConnection"
    )
    lines.extend(["", f"conn = {conn_cls}({_py_str(host_arg)})"])

    files_form = data.get("files_form") or {}
    if files_form:
        lines.append(
            "# http.client không sinh multipart từ files_form; chỉ gửi raw body nếu có"
        )
    lines.append(f"payload = {_py_str(data.get('data_body') or '')}")

    headers = dict(_get_headers(data))
    if auth:
        user, password = _auth_pair(auth)
        for key in list(headers):
            if str(key).lower() == "authorization":
                headers.pop(key, None)
        lines.append(
            "auth_token = base64.b64encode("
            f"({_py_str(user)} + ':' + {_py_str(password)})"
            ".encode('utf-8')).decode('utf-8')"
        )
        lines.append(f"headers = {_py_dict(headers)}")
        lines.append('headers["Authorization"] = "Basic " + auth_token')
    else:
        lines.append(f"headers = {_py_dict(headers)}")

    method = str(data.get("method") or "GET").upper()
    lines.extend(
        [
            "",
            f"conn.request({_py_str(method)}, {_py_str(path)}, payload, headers)",
            "res = conn.getresponse()",
            "data = res.read()",
            "print(data.decode('utf-8'))",
        ]
    )
    return "\n".join(lines)

# core/generators/lua_gen.py
import json
from urllib.parse import urlencode

from . import register_generator
from .utils import escape_string


def _headers_items(headers):
    if not headers:
        return []
    if isinstance(headers, dict):
        return list(headers.items())
    return list(headers)


def _header_value(headers, name):
    target = name.lower()
    for key, value in _headers_items(headers):
        if str(key).lower() == target:
            return value
    return None


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _serialize_body(data_body, content_type):
    """Giu nguyen chuoi da serialize. Chi doi kieu khi data_body khong phai str.

    Khong them khoa moi vao `data`. Chi doc data_body + Content-Type da co.
    """
    if data_body is None or data_body is False:
        return "", content_type, False

    if isinstance(data_body, bytes):
        return data_body.decode("utf-8"), content_type, True

    if isinstance(data_body, str):
        return data_body, content_type, bool(data_body)

    if isinstance(data_body, (dict, list)):
        ct = (content_type or "").lower()
        if "json" in ct or isinstance(data_body, list):
            body = json.dumps(data_body, ensure_ascii=False, separators=(",", ":"))
            if not content_type:
                content_type = "application/json"
            return body, content_type, True
        if isinstance(data_body, dict):
            body = urlencode(
                {str(k): "" if v is None else str(v) for k, v in data_body.items()},
                doseq=True,
            )
            if not content_type:
                content_type = "application/x-www-form-urlencoded"
            return body, content_type, True

    return _as_text(data_body), content_type, True


def _multipart_from_files_form(files_form, extra_body=""):
    """Dung multipart trong Python.

    Chi nhan cac dang khong bia schema:
    - dict: field -> gia tri chuoi (noi dung field, khong doc file tu dia)
    - list/tuple cac cap (name, value)
    Tra None neu khong nhan dien duoc.
    """
    fields = []
    if isinstance(files_form, dict):
        fields = list(files_form.items())
    elif isinstance(files_form, (list, tuple)):
        for item in files_form:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                fields.append((item[0], item[1]))
            else:
                return None
    elif files_form:
        return None
    else:
        return None

    boundary = "LuaSocketFormBoundary7MA4YWxkTrZu0gW"
    parts = []
    for name, value in fields:
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{_as_text(name)}"\r\n'
            f"\r\n"
            f"{_as_text(value)}\r\n"
        )
    if extra_body:
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="data"\r\n'
            f"\r\n"
            f"{extra_body}\r\n"
        )
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts), f"multipart/form-data; boundary={boundary}"


@register_generator("lua_socket")
def generate_lua_socket(data: dict) -> str:
    """Sinh ma Lua dung socket.http (HTTP) hoac ssl.https (HTTPS)."""
    url = _as_text(data["url"])
    method = _as_text(data["method"]).upper() or "GET"
    headers = data["headers"] or {}
    data_body = data["data_body"]
    files_form = data["files_form"]
    auth = data["auth"]

    content_type = _header_value(headers, "Content-Type")
    body, content_type, has_explicit_body = _serialize_body(data_body, content_type)

    multipart_warning = False
    if files_form:
        built = _multipart_from_files_form(files_form, extra_body=body)
        if built:
            body, content_type = built
            has_explicit_body = True
        else:
            multipart_warning = True

    has_body = bool(body) or has_explicit_body
    use_https = url.lower().startswith("https://")

    lines = []
    if use_https:
        lines.append('local https = require("ssl.https")')
    else:
        lines.append('local http = require("socket.http")')
    lines.append('local ltn12 = require("ltn12")')
    if auth:
        lines.append('local mime = require("mime")')

    lines.extend(["", "local response_body = {}", ""])

    if multipart_warning:
        lines.append("-- CANH BAO: files_form khong o dang dict hoac list cap (name, value).")
        lines.append("-- socket.http khong ghep multipart tu file path. Bo qua body multipart.")

    if has_body:
        lines.append(f'local req_body = "{escape_string(body)}"')
        lines.append("")

    request_lib = "https" if use_https else "http"
    lines.append(f"local res, code, response_headers, status = {request_lib}.request{{")
    lines.append(f'    url = "{escape_string(url)}",')
    lines.append(f'    method = "{escape_string(method)}",')
    lines.append("    headers = {")

    header_lines = []
    seen_keys = set()
    for key, value in _headers_items(headers):
        key_s = _as_text(key)
        key_l = key_s.lower()
        seen_keys.add(key_l)
        if key_l == "content-length":
            continue
        if key_l == "content-type" and content_type:
            header_lines.append(
                f'        ["{escape_string(key_s)}"] = "{escape_string(content_type)}"'
            )
            continue
        header_lines.append(
            f'        ["{escape_string(key_s)}"] = "{escape_string(_as_text(value))}"'
        )

    if content_type and "content-type" not in seen_keys:
        header_lines.append(
            f'        ["Content-Type"] = "{escape_string(content_type)}"'
        )

    if auth and "authorization" not in seen_keys:
        user = _as_text(auth[0])
        password = _as_text(auth[1])
        header_lines.append(
            '        ["Authorization"] = "Basic " .. mime.b64("'
            + escape_string(user)
            + ":"
            + escape_string(password)
            + '")'
        )

    if has_body:
        header_lines.append('        ["Content-Length"] = tostring(#req_body)')

    if header_lines:
        lines.append(",\n".join(header_lines))

    lines.append("    },")

    if has_body:
        lines.append("    source = ltn12.source.string(req_body),")

    lines.append("    sink = ltn12.sink.table(response_body)")
    lines.append("}")
    lines.extend(
        [
            "",
            "print(table.concat(response_body))",
        ]
    )
    return "\n".join(lines)

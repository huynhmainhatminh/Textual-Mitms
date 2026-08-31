# core/generators/http_gen.py
import base64
import json
import os
import re
from urllib.parse import urlencode, urlsplit

from . import register_generator


_OPEN_FILE_RE = re.compile(r"""^open\(\s*(['"])(.*)\1\s*\)$""")
_MULTIPART_BOUNDARY = "----WebKitFormBoundary7MA4YWxkTrZu0gW"


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _parse_open_path(value):
    text = _as_text(value).strip()
    match = _OPEN_FILE_RE.match(text)
    if match:
        return match.group(2)
    if text.startswith("open(") and "'" in text:
        parts = text.split("'")
        if len(parts) >= 2:
            return parts[1]
    if text.startswith("open(") and '"' in text:
        parts = text.split('"')
        if len(parts) >= 2:
            return parts[1]
    return None


def _files_form_items(files_form):
    if not files_form:
        return []
    if isinstance(files_form, dict):
        return list(files_form.items())
    if isinstance(files_form, (list, tuple)):
        items = []
        for item in files_form:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                items.append((item[0], item[1]))
            else:
                return None
        return items
    return None


def _serialize_body(data_body, content_type, is_json):
    if data_body is None or data_body is False:
        return "", content_type
    if isinstance(data_body, bytes):
        return data_body.decode("utf-8"), content_type
    if isinstance(data_body, str):
        if is_json and (not content_type or "json" not in content_type.lower()):
            content_type = "application/json"
        return data_body, content_type
    if isinstance(data_body, (dict, list)):
        want_json = bool(is_json) or (
            content_type and "json" in content_type.lower()
        ) or isinstance(data_body, list)
        if want_json:
            body = json.dumps(data_body, ensure_ascii=False, separators=(",", ":"))
            if not content_type or "json" not in content_type.lower():
                content_type = "application/json"
            return body, content_type
        if isinstance(data_body, dict):
            body = urlencode(
                {str(k): "" if v is None else str(v) for k, v in data_body.items()},
                doseq=True,
            )
            if not content_type:
                content_type = "application/x-www-form-urlencoded"
            return body, content_type
    return _as_text(data_body), content_type


class _HeaderMap:
    """Giu thu tu chen; ghi de theo ten header khong phan biet hoa thuong."""

    def __init__(self):
        self._items = []

    def set(self, name, value):
        target = name.lower()
        for i, (k, _) in enumerate(self._items):
            if k.lower() == target:
                self._items[i] = (name, value)
                return
        self._items.append((name, value))

    def get(self, name):
        target = name.lower()
        for k, v in self._items:
            if k.lower() == target:
                return v
        return None

    def items(self):
        return list(self._items)


@register_generator("http_raw")
def generate_http_raw(data: dict) -> str:
    """Sinh goi tin HTTP/1.1 tho (CRLF theo RFC 9112)."""
    url_parts = urlsplit(_as_text(data["url"]))
    path = url_parts.path if url_parts.path else "/"
    if url_parts.query:
        path += "?" + url_parts.query

    host = url_parts.netloc
    method = _as_text(data["method"]).upper() or "GET"
    is_json = data["is_json"] if "is_json" in data else False

    headers = _HeaderMap()
    headers.set("Host", host)

    form_items = _files_form_items(data["files_form"])
    use_multipart = bool(form_items)
    if form_items is None:
        form_items = []

    incoming_ct = None
    if data["headers"]:
        if isinstance(data["headers"], dict):
            header_pairs = data["headers"].items()
        else:
            header_pairs = data["headers"]
        for key, value in header_pairs:
            key_l = str(key).lower()
            if use_multipart and key_l == "content-type":
                continue
            if key_l == "host":
                continue
            if key_l == "content-length":
                continue
            if key_l == "authorization" and data["auth"]:
                continue
            if key_l == "content-type":
                incoming_ct = _as_text(value)
            headers.set(str(key), _as_text(value))

    if data["auth"]:
        raw = _as_text(data["auth"][0]) + ":" + _as_text(data["auth"][1])
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        headers.set("Authorization", "Basic " + encoded)

    text_body, content_type = _serialize_body(
        data["data_body"], incoming_ct or headers.get("Content-Type"), is_json
    )

    body_content = ""
    if use_multipart:
        headers.set(
            "Content-Type",
            "multipart/form-data; boundary=" + _MULTIPART_BOUNDARY,
        )
        parts = []
        for key, raw in form_items:
            parts.append("--" + _MULTIPART_BOUNDARY)
            path = _parse_open_path(raw)
            if path is not None:
                filename = os.path.basename(path) or path
                parts.append(
                    'Content-Disposition: form-data; name="%s"; filename="%s"'
                    % (key, filename)
                )
                parts.append("Content-Type: application/octet-stream")
                parts.append("")
                parts.append("[file content not embedded: %s]" % path)
            else:
                parts.append('Content-Disposition: form-data; name="%s"' % key)
                parts.append("")
                parts.append(_as_text(raw))
        if text_body:
            parts.append("--" + _MULTIPART_BOUNDARY)
            parts.append('Content-Disposition: form-data; name="data"')
            parts.append("")
            parts.append(text_body)
        parts.append("--" + _MULTIPART_BOUNDARY + "--")
        parts.append("")
        body_content = "\r\n".join(parts)
    elif text_body:
        body_content = text_body
        if content_type and headers.get("Content-Type") is None:
            headers.set("Content-Type", content_type)

    if body_content:
        headers.set("Content-Length", str(len(body_content.encode("utf-8"))))

    out = ["%s %s HTTP/1.1" % (method, path)]
    for key, value in headers.items():
        out.append("%s: %s" % (key, value))
    out.append("")
    if body_content:
        out.append(body_content)
        return "\r\n".join(out)
    return "\r\n".join(out) + "\r\n"

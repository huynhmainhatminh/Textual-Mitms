# core/generators/har_gen.py
import base64
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse

from . import register_generator


_OPEN_FILE_RE = re.compile(r"""^open\(\s*(['"])(.*)\1\s*\)$""")


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _parse_open_path(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
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


def _header_value(headers, name):
    target = name.lower()
    for item in headers:
        if str(item["name"]).lower() == target:
            return item["value"]
    return None


def _cookies_from_headers(headers):
    raw = _header_value(headers, "Cookie")
    if not raw:
        return []
    cookies = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, value = part.split("=", 1)
            cookies.append({"name": name.strip(), "value": value})
        else:
            cookies.append({"name": part, "value": ""})
    return cookies


def _serialize_text(data_body, mime_type, is_json):
    if data_body is None or data_body is False:
        return None, mime_type
    if isinstance(data_body, bytes):
        data_body = data_body.decode("utf-8")
    if isinstance(data_body, str):
        if is_json and "json" not in (mime_type or "").lower():
            mime_type = "application/json"
        return data_body, mime_type
    if isinstance(data_body, (dict, list)):
        want_json = bool(is_json) or "json" in (mime_type or "").lower() or isinstance(
            data_body, list
        )
        if want_json:
            if "json" not in (mime_type or "").lower():
                mime_type = "application/json"
            return json.dumps(data_body, ensure_ascii=False, separators=(",", ":")), mime_type
        if isinstance(data_body, dict):
            text = urlencode(
                {str(k): "" if v is None else str(v) for k, v in data_body.items()},
                doseq=True,
            )
            if not mime_type or mime_type == "text/plain":
                mime_type = "application/x-www-form-urlencoded"
            return text, mime_type
    return _as_text(data_body), mime_type


@register_generator("har_format")
def generate_har(data: dict) -> str:
    """Sinh HAR 1.2 JSON tu lenh cURL da boc tach."""
    url = _as_text(data["url"])
    parsed_url = urlparse(url)
    query_string = [
        {"name": k, "value": v}
        for k, v in parse_qsl(parsed_url.query, keep_blank_values=True)
    ]

    headers = []
    seen_auth = False
    if data["headers"]:
        pairs = (
            data["headers"].items()
            if isinstance(data["headers"], dict)
            else data["headers"]
        )
        for key, value in pairs:
            if str(key).lower() == "authorization":
                seen_auth = True
            headers.append({"name": str(key), "value": _as_text(value)})

    if data["auth"]:
        raw = _as_text(data["auth"][0]) + ":" + _as_text(data["auth"][1])
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        if seen_auth:
            headers = [
                h
                for h in headers
                if str(h["name"]).lower() != "authorization"
            ]
        headers.append({"name": "Authorization", "value": "Basic " + encoded})

    mime_type = _header_value(headers, "Content-Type") or "text/plain"
    is_json = data["is_json"] if "is_json" in data else False
    text_body, mime_type = _serialize_text(data["data_body"], mime_type, is_json)

    form_items = _files_form_items(data["files_form"])
    if form_items is None:
        form_items = []

    post_data = None
    if form_items:
        params = []
        for key, raw in form_items:
            path = _parse_open_path(raw)
            if path is not None:
                params.append(
                    {
                        "name": _as_text(key),
                        "fileName": os.path.basename(path) or path,
                        "contentType": "application/octet-stream",
                    }
                )
            else:
                params.append({"name": _as_text(key), "value": _as_text(raw)})
        if text_body:
            params.append({"name": "data", "value": text_body})
        post_data = {"mimeType": "multipart/form-data", "params": params}
    elif text_body is not None and text_body != "":
        post_data = {"mimeType": mime_type, "text": text_body}
        if "application/x-www-form-urlencoded" in mime_type.lower():
            pairs = parse_qsl(text_body, keep_blank_values=True)
            if pairs:
                post_data["params"] = [
                    {"name": k, "value": v} for k, v in pairs
                ]

    body_size = -1
    if post_data and "text" in post_data:
        body_size = len(post_data["text"].encode("utf-8"))

    request = {
        "method": _as_text(data["method"]).upper() or "GET",
        "url": url,
        "httpVersion": "HTTP/1.1",
        "cookies": _cookies_from_headers(headers),
        "headers": headers,
        "queryString": query_string,
        "headersSize": -1,
        "bodySize": body_size,
    }
    if post_data:
        request["postData"] = post_data

    har_dict = {
        "log": {
            "version": "1.2",
            "creator": {
                "name": "cURL Converter UI",
                "version": "1.0",
            },
            "entries": [
                {
                    "startedDateTime": datetime.now(timezone.utc).isoformat(),
                    "time": 0,
                    "request": request,
                    "response": {
                        "status": 0,
                        "statusText": "",
                        "httpVersion": "HTTP/1.1",
                        "cookies": [],
                        "headers": [],
                        "content": {"size": 0, "mimeType": "x-unknown"},
                        "redirectURL": "",
                        "headersSize": -1,
                        "bodySize": -1,
                    },
                    "cache": {},
                    "timings": {"send": 0, "wait": 0, "receive": 0},
                }
            ],
        }
    }
    return json.dumps(har_dict, indent=4, ensure_ascii=False)

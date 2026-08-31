# core/generators/json_gen.py
import json
import re
from urllib.parse import parse_qsl

from . import register_generator


_OPEN_FILE_RE = re.compile(r"""^open\(\s*(['"])(.*)\1\s*\)$""")


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _headers_map(headers):
    if not headers:
        return {}
    if isinstance(headers, dict):
        return dict(headers)
    return dict(headers)


def _header_value(headers, name):
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return value
    return None


def _parse_open_path(value):
    """Quy uoc open(...) da xuat hien o kotlin_gen/julia_gen cua cung project."""
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


def _normalize_files_form(files_form):
    if not files_form:
        return None
    if isinstance(files_form, dict):
        items = list(files_form.items())
    elif isinstance(files_form, (list, tuple)):
        items = []
        for item in files_form:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                items.append((item[0], item[1]))
            else:
                return files_form
    else:
        return files_form

    out = {}
    for key, raw in items:
        path = _parse_open_path(raw)
        out[_as_text(key)] = path if path is not None else raw
    return out


def _normalize_data_body(data_body, is_json, content_type):
    if data_body is None or data_body is False:
        return None

    if isinstance(data_body, bytes):
        data_body = data_body.decode("utf-8")

    if isinstance(data_body, (dict, list)):
        return data_body

    if not isinstance(data_body, str):
        return data_body

    if not data_body:
        return None

    ct = (content_type or "").lower()
    if is_json or "json" in ct:
        try:
            return json.loads(data_body)
        except json.JSONDecodeError:
            return data_body

    if "application/x-www-form-urlencoded" in ct:
        pairs = parse_qsl(data_body, keep_blank_values=True)
        if not pairs:
            return data_body
        keys = [k for k, _ in pairs]
        if len(keys) == len(set(keys)):
            return dict(pairs)
        return [{"name": k, "value": v} for k, v in pairs]

    return data_body


@register_generator("json_format")
def generate_json(data: dict) -> str:
    """Sinh chuoi JSON mo ta cau truc lenh cURL da boc tach."""
    headers = _headers_map(data["headers"])
    method = _as_text(data["method"]).lower() or "get"
    url = data["url"]

    result = {
        "url": url,
        "raw_url": url,
        "method": method,
        "headers": headers,
    }

    headers_lower = {str(k).lower(): v for k, v in headers.items()}
    result["compressed"] = "accept-encoding" in headers_lower

    if data["auth"]:
        result["auth"] = {
            "user": data["auth"][0],
            "password": data["auth"][1],
        }

    if data["files_form"]:
        result["files_form"] = _normalize_files_form(data["files_form"])

    content_type = _header_value(headers, "Content-Type")
    payload = _normalize_data_body(data["data_body"], data["is_json"], content_type)
    if payload is not None:
        result["data"] = payload

    return json.dumps(result, indent=4, ensure_ascii=False)

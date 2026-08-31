# core/generators/wget_gen.py
import json
import re
from urllib.parse import urlencode

from . import register_generator
from .utils import escape_string


_OPEN_FILE_RE = re.compile(r"""^open\(\s*(['"])(.*)\1\s*\)$""")


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _sh_escape(value):
    return escape_string(_as_text(value)).replace("$", "\\$").replace("`", "\\`")


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


def _header_pairs(headers):
    if not headers:
        return []
    if isinstance(headers, dict):
        return list(headers.items())
    return list(headers)


def _header_value(headers, name):
    target = name.lower()
    for key, value in _header_pairs(headers):
        if str(key).lower() == target:
            return value
    return None


def _serialize_body(data_body, content_type, is_json):
    if data_body is None or data_body is False:
        return "", content_type, False
    if isinstance(data_body, bytes):
        return data_body.decode("utf-8"), content_type, True
    if isinstance(data_body, str):
        if is_json and (not content_type or "json" not in content_type.lower()):
            content_type = "application/json"
        return data_body, content_type, bool(data_body)
    if isinstance(data_body, (dict, list)):
        want_json = bool(is_json) or (
            content_type and "json" not in content_type.lower()
        ) or isinstance(data_body, list)
        if want_json:
            body = json.dumps(data_body, ensure_ascii=False, separators=(",", ":"))
            if not content_type or "json" not in content_type.lower():
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


@register_generator("wget")
def generate_wget(data: dict) -> str:
    """Sinh lenh wget tu cau truc cURL da boc tach."""
    method = _as_text(data["method"]).upper() or "GET"
    headers = data["headers"] or {}
    auth = data["auth"]
    is_json = data["is_json"] if "is_json" in data else False
    content_type = _header_value(headers, "Content-Type")
    text_body, content_type, has_text = _serialize_body(
        data["data_body"], content_type, is_json
    )
    form_items = _files_form_items(data["files_form"])
    if form_items is None:
        form_items = []
    use_multipart = bool(form_items)

    notes = []
    if use_multipart:
        notes.append(
            "# wget khong ho tro multipart/form-data / upload file nhu curl -F."
        )
        notes.append("# Khuyen nghi dung curl cho files_form.")
        for key, raw in form_items:
            path = _parse_open_path(raw)
            if path is not None:
                notes.append("# file field %s -> %s" % (key, path))
            else:
                notes.append("# form field %s" % key)

    flags = ["wget \\"]
    if method != "GET" or (has_text and not use_multipart):
        flags.append("  --method=%s \\" % _sh_escape(method))

    if auth:
        flags.append('  --user="%s" \\' % _sh_escape(auth[0]))
        flags.append('  --password="%s" \\' % _sh_escape(auth[1]))

    seen_ct = False
    for key, value in _header_pairs(headers):
        key_l = str(key).lower()
        if use_multipart and key_l == "content-type":
            continue
        if auth and key_l == "authorization":
            continue
        if key_l == "content-type":
            seen_ct = True
            value = content_type or value
        flags.append(
            '  --header="%s: %s" \\' % (_sh_escape(key), _sh_escape(value))
        )
    if content_type and has_text and not use_multipart and not seen_ct:
        flags.append(
            '  --header="Content-Type: %s" \\' % _sh_escape(content_type)
        )

    if has_text and not use_multipart:
        flags.append('  --body-data="%s" \\' % _sh_escape(text_body))

    flags.append('  "%s"' % _sh_escape(data["url"]))

    if notes:
        return "\n".join(notes + [""] + flags)
    return "\n".join(flags)

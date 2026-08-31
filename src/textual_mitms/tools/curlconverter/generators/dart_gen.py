# core/generators/dart_gen.py
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


def _dart_escape(value):
    # Dart noi suy $ trong ca '...' lan "...".
    return escape_string(_as_text(value)).replace("$", "\\$")


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
            content_type and "json" in content_type.lower()
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


@register_generator("dart_http")
def generate_dart_http(data: dict) -> str:
    """Sinh ma Dart dung package:http."""
    url = _dart_escape(data["url"])
    method = _as_text(data["method"]).upper() or "GET"
    headers_in = data["headers"] or {}
    auth = data["auth"]
    is_json = data["is_json"] if "is_json" in data else False
    content_type = _header_value(headers_in, "Content-Type")
    text_body, content_type, has_text = _serialize_body(
        data["data_body"], content_type, is_json
    )
    form_items = _files_form_items(data["files_form"])
    if form_items is None:
        form_items = []
    use_multipart = bool(form_items)

    lines = ["import 'package:http/http.dart' as http;"]
    if auth:
        lines.append("import 'dart:convert';")
    lines.extend(["", "void main() async {", f"  var url = Uri.parse('{url}');", ""])

    header_lines = []
    seen = set()
    for key, value in _header_pairs(headers_in):
        key_l = str(key).lower()
        seen.add(key_l)
        if use_multipart and key_l == "content-type":
            continue
        if auth and key_l == "authorization":
            continue
        if key_l == "content-type" and content_type and not use_multipart:
            header_lines.append(
                f"    '{_dart_escape(key)}': '{_dart_escape(content_type)}',"
            )
            continue
        header_lines.append(
            f"    '{_dart_escape(key)}': '{_dart_escape(value)}',"
        )
    if (
        content_type
        and not use_multipart
        and "content-type" not in seen
        and has_text
    ):
        header_lines.append(
            f"    'Content-Type': '{_dart_escape(content_type)}',"
        )
    if auth:
        user = _dart_escape(auth[0])
        password = _dart_escape(auth[1])
        header_lines.append(
            "    'Authorization': 'Basic ' + base64Encode(utf8.encode('"
            + user
            + ":"
            + password
            + "')),"
        )

    if header_lines:
        lines.append("  var headers = {")
        lines.extend(header_lines)
        lines.append("  };")
        lines.append("")

    if use_multipart:
        lines.append(f"  var request = http.MultipartRequest('{_dart_escape(method)}', url);")
        if header_lines:
            lines.append("  request.headers.addAll(headers);")
        for key, raw in form_items:
            path = _parse_open_path(raw)
            if path is not None:
                lines.append(
                    "  request.files.add(await http.MultipartFile.fromPath('"
                    + _dart_escape(key)
                    + "', '"
                    + _dart_escape(path)
                    + "'));"
                )
            else:
                lines.append(
                    "  request.fields['"
                    + _dart_escape(key)
                    + "'] = '"
                    + _dart_escape(raw)
                    + "';"
                )
        if has_text:
            lines.append(
                "  request.fields['data'] = '" + _dart_escape(text_body) + "';"
            )
    else:
        lines.append(f"  var request = http.Request('{_dart_escape(method)}', url);")
        if header_lines:
            lines.append("  request.headers.addAll(headers);")
        if has_text:
            lines.append("  request.body = '" + _dart_escape(text_body) + "';")

    lines.extend(
        [
            "",
            "  var streamedResponse = await request.send();",
            "  var response = await http.Response.fromStream(streamedResponse);",
            "",
            "  if (response.statusCode >= 200 && response.statusCode < 300) {",
            "    print(response.body);",
            "  } else {",
            "    print('Request failed with status: ${response.statusCode}.');",
            "  }",
            "}",
        ]
    )
    return "\n".join(lines)

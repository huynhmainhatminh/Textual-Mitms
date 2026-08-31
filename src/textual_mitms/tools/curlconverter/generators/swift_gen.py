# core/generators/swift_gen.py
import base64
import json
import os
import re
from urllib.parse import urlencode

from . import register_generator
from .utils import escape_string


_OPEN_FILE_RE = re.compile(r"""^open\(\s*(['"])(.*)\1\s*\)$""")
_SWIFT_BOUNDARY = "Boundary-011000010111000001101001"


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _sw_escape(value):
    # Swift noi suy \(...) trong chuoi ".
    return escape_string(_as_text(value)).replace("\\(", "\\\\(")


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


@register_generator("swift_urlsession")
def generate_swift_urlsession(data: dict) -> str:
    """Sinh ma Swift dung URLSession."""
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

    lines = [
        "import Foundation",
        "",
        'let url = URL(string: "%s")!' % _sw_escape(data["url"]),
        "var request = URLRequest(url: url)",
        'request.httpMethod = "%s"' % _sw_escape(method),
        "",
    ]

    header_pairs = []
    for key, value in _header_pairs(headers):
        key_l = str(key).lower()
        if use_multipart and key_l == "content-type":
            continue
        if auth and key_l == "authorization":
            continue
        if key_l == "content-type" and content_type and not use_multipart:
            header_pairs.append((key, content_type))
            continue
        header_pairs.append((key, value))
    if use_multipart:
        header_pairs.append(
            (
                "Content-Type",
                "multipart/form-data; boundary=%s" % _SWIFT_BOUNDARY,
            )
        )
    elif (
        content_type
        and has_text
        and _header_value(headers, "Content-Type") is None
    ):
        header_pairs.append(("Content-Type", content_type))
    if auth:
        user = _as_text(auth[0])
        password = _as_text(auth[1])
        header_pairs.append(
            (
                "Authorization",
                "Basic "
                + base64.b64encode((user + ":" + password).encode("utf-8")).decode(
                    "ascii"
                ),
            )
        )

    for key, value in header_pairs:
        lines.append(
            'request.setValue("%s", forHTTPHeaderField: "%s")'
            % (_sw_escape(value), _sw_escape(key))
        )

    if use_multipart:
        lines.extend(
            [
                "",
                'let boundary = "%s"' % _SWIFT_BOUNDARY,
                "var body = Data()",
                'let boundaryPrefix = "--\\(boundary)\\r\\n"',
            ]
        )
        for key, raw in form_items:
            lines.append("body.append(boundaryPrefix.data(using: .utf8)!)")
            path = _parse_open_path(raw)
            if path is not None:
                filename = os.path.basename(path) or path
                lines.append(
                    'body.append("Content-Disposition: form-data; name=\\"%s\\"; filename=\\"%s\\"\\r\\n".data(using: .utf8)!)'
                    % (_sw_escape(key), _sw_escape(filename))
                )
                lines.append(
                    'body.append("Content-Type: application/octet-stream\\r\\n\\r\\n".data(using: .utf8)!)'
                )
                lines.append(
                    'if let fileData = try? Data(contentsOf: URL(fileURLWithPath: "%s")) {'
                    % _sw_escape(path)
                )
                lines.append("    body.append(fileData)")
                lines.append("}")
                lines.append('body.append("\\r\\n".data(using: .utf8)!)')
            else:
                lines.append(
                    'body.append("Content-Disposition: form-data; name=\\"%s\\"\\r\\n\\r\\n".data(using: .utf8)!)'
                    % _sw_escape(key)
                )
                lines.append(
                    'body.append("%s\\r\\n".data(using: .utf8)!)' % _sw_escape(raw)
                )
        if has_text:
            lines.append("body.append(boundaryPrefix.data(using: .utf8)!)")
            lines.append(
                'body.append("Content-Disposition: form-data; name=\\"data\\"\\r\\n\\r\\n".data(using: .utf8)!)'
            )
            lines.append(
                'body.append("%s\\r\\n".data(using: .utf8)!)' % _sw_escape(text_body)
            )
        lines.append('body.append("--\\(boundary)--\\r\\n".data(using: .utf8)!)')
        lines.append("request.httpBody = body")
    elif has_text:
        lines.append("")
        lines.append('let bodyString = "%s"' % _sw_escape(text_body))
        lines.append("request.httpBody = bodyString.data(using: .utf8)")

    lines.extend(
        [
            "",
            "let semaphore = DispatchSemaphore(value: 0)",
            "let task = URLSession.shared.dataTask(with: request) { data, response, error in",
            "    if let error = error {",
            '        print("Error: \\(error)")',
            "    } else if let data = data, let str = String(data: data, encoding: .utf8) {",
            "        print(str)",
            "    }",
            "    semaphore.signal()",
            "}",
            "",
            "task.resume()",
            "semaphore.wait()",
        ]
    )
    return "\n".join(lines)

# core/generators/rust_gen.py
import json
import re
from urllib.parse import urlencode

from . import register_generator
from .utils import escape_string


_OPEN_FILE_RE = re.compile(r"""^open\(\s*(['"])(.*)\1\s*\)$""")
_REQWEST_METHODS = {
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "PATCH",
    "HEAD",
    "OPTIONS",
    "CONNECT",
    "TRACE",
}


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _rs_escape(value):
    return escape_string(_as_text(value))


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


@register_generator("rust_reqwest")
def generate_rust(data: dict) -> str:
    """Sinh ma Rust dung reqwest blocking."""
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
        "use reqwest::header;",
        "",
        "fn main() -> Result<(), Box<dyn std::error::Error>> {",
        "    let client = reqwest::blocking::Client::new();",
    ]
    if method in _REQWEST_METHODS:
        lines.append(
            '    let mut request = client.request(reqwest::Method::%s, "%s");'
            % (method, _rs_escape(data["url"]))
        )
    else:
        lines.append(
            '    let method = reqwest::Method::from_bytes(b"%s")?;'
            % _rs_escape(method)
        )
        lines.append(
            '    let mut request = client.request(method, "%s");'
            % _rs_escape(data["url"])
        )

    header_stmts = []
    for key, value in _header_pairs(headers):
        key_l = str(key).lower()
        if use_multipart and key_l == "content-type":
            continue
        if auth and key_l == "authorization":
            continue
        val = content_type if key_l == "content-type" and content_type else value
        header_stmts.append(
            '    headers.insert("%s".parse::<header::HeaderName>()?, "%s".parse()?);'
            % (_rs_escape(key), _rs_escape(val))
        )
    if (
        content_type
        and not use_multipart
        and has_text
        and _header_value(headers, "Content-Type") is None
    ):
        header_stmts.append(
            '    headers.insert(header::CONTENT_TYPE, "%s".parse()?);'
            % _rs_escape(content_type)
        )

    if header_stmts:
        lines.append("")
        lines.append("    let mut headers = header::HeaderMap::new();")
        lines.extend(header_stmts)
        lines.append("    request = request.headers(headers);")

    if auth:
        lines.append("")
        lines.append(
            '    request = request.basic_auth("%s", Some("%s"));'
            % (_rs_escape(auth[0]), _rs_escape(auth[1]))
        )

    if use_multipart:
        lines.append("")
        lines.append("    let mut form = reqwest::blocking::multipart::Form::new();")
        for key, raw in form_items:
            path = _parse_open_path(raw)
            if path is not None:
                lines.append(
                    '    form = form.file("%s", "%s")?;'
                    % (_rs_escape(key), _rs_escape(path))
                )
            else:
                lines.append(
                    '    form = form.text("%s", "%s");'
                    % (_rs_escape(key), _rs_escape(raw))
                )
        if has_text:
            lines.append(
                '    form = form.text("data", "%s");' % _rs_escape(text_body)
            )
        lines.append("    request = request.multipart(form);")
    elif has_text:
        lines.append("")
        lines.append('    request = request.body("%s");' % _rs_escape(text_body))

    lines.extend(
        [
            "",
            "    let response = request.send()?;",
            '    println!("Status: {}", response.status());',
            '    println!("Body: {}\\n", response.text()?);',
            "",
            "    Ok(())",
            "}",
        ]
    )
    return "\n".join(lines)

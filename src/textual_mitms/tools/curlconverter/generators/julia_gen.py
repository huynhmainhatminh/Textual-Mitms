# core/generators/julia_gen.py
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


def _jl_escape(value):
    """escape_string cua project + '$' (Julia string interpolation)."""
    return escape_string(_as_text(value)).replace("$", "\\$")


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


def _parse_open_path(value):
    """Quy uoc da co trong file goc: v.startswith('open(') roi split quote."""
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


def _serialize_text_body(data_body, content_type):
    """Giu chuoi. dict/list chi serialize theo Content-Type da co trong headers."""
    if data_body is None or data_body is False:
        return "", content_type, False

    if isinstance(data_body, bytes):
        data_body = data_body.decode("utf-8")

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


@register_generator("julia_http")
def generate_julia_http(data: dict) -> str:
    """Sinh ma Julia su dung package HTTP.jl."""
    url = _as_text(data["url"])
    method = _as_text(data["method"]).upper() or "GET"
    headers = data["headers"] or {}
    data_body = data["data_body"]
    files_form = data["files_form"]
    auth = data["auth"]

    form_items = _files_form_items(files_form)
    form_unparsed = bool(files_form) and form_items is None
    if form_items is None:
        form_items = []

    content_type = _header_value(headers, "Content-Type")
    text_body, content_type, has_text_body = _serialize_text_body(
        data_body, content_type
    )
    use_multipart = bool(form_items)

    lines = ["using HTTP"]
    if auth:
        lines.append("using Base64")
    lines.append("")

    header_lines = []
    seen = set()
    for key, value in _headers_items(headers):
        key_l = str(key).lower()
        seen.add(key_l)
        if use_multipart and key_l == "content-type":
            continue
        if auth and key_l == "authorization":
            continue
        if (not use_multipart) and key_l == "content-type" and content_type:
            header_lines.append(
                f'    "{_jl_escape(key)}" => "{_jl_escape(content_type)}"'
            )
            continue
        header_lines.append(f'    "{_jl_escape(key)}" => "{_jl_escape(value)}"')

    if content_type and (not use_multipart) and "content-type" not in seen:
        header_lines.append(f'    "Content-Type" => "{_jl_escape(content_type)}"')

    if auth:
        user = _jl_escape(auth[0])
        password = _jl_escape(auth[1])
        header_lines.append(
            f'    "Authorization" => "Basic " * base64encode("{user}:{password}")'
        )

    if header_lines:
        lines.append("headers = Dict(")
        lines.append(",\n".join(header_lines))
        lines.append(")")
    else:
        lines.append("headers = Dict{String,String}()")

    lines.append("")

    if form_unparsed:
        lines.append("# CANH BAO: files_form khong phai dict hoac list cap (name, value).")

    if use_multipart:
        lines.append("body = HTTP.Form(Dict(")
        form_lines = []
        for key, raw in form_items:
            file_path = _parse_open_path(raw)
            if file_path is not None:
                form_lines.append(
                    f'    "{_jl_escape(key)}" => open("{_jl_escape(file_path)}")'
                )
            else:
                form_lines.append(
                    f'    "{_jl_escape(key)}" => "{_jl_escape(raw)}"'
                )
        if has_text_body:
            form_lines.append(f'    "data" => "{_jl_escape(text_body)}"')
        lines.append(",\n".join(form_lines))
        lines.append("))")
    elif has_text_body:
        lines.append(f'body = "{_jl_escape(text_body)}"')
    else:
        lines.append("body = UInt8[]")

    lines.append("")
    lines.append(
        f'response = HTTP.request("{_jl_escape(method)}", "{_jl_escape(url)}", headers, body)'
    )
    lines.append("println(String(response.body))")
    return "\n".join(lines)

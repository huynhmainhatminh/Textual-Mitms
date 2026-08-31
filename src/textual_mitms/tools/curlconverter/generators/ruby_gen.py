# core/generators/ruby_gen.py
import json
import re
from urllib.parse import urlencode

from . import register_generator
from .utils import escape_string


_OPEN_FILE_RE = re.compile(r"""^open\(\s*(['"])(.*)\1\s*\)$""")
_NETHTTP_CLASSES = ("Get", "Post", "Put", "Delete", "Patch", "Head", "Options")
_HTTPARTY_METHODS = ("get", "post", "put", "delete", "patch", "head", "options")


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _rb_escape(value):
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


def _collect(data):
    headers = data["headers"] or {}
    is_json = data["is_json"] if "is_json" in data else False
    content_type = _header_value(headers, "Content-Type")
    text_body, content_type, has_text = _serialize_body(
        data["data_body"], content_type, is_json
    )
    form_items = _files_form_items(data["files_form"])
    if form_items is None:
        form_items = []
    return {
        "url": _as_text(data["url"]),
        "method": _as_text(data["method"]).upper() or "GET",
        "headers": headers,
        "auth": data["auth"],
        "form_items": form_items,
        "use_multipart": bool(form_items),
        "text_body": text_body,
        "has_text": has_text,
        "content_type": content_type,
    }


def _emit_headers(lines, info, assign):
    for key, value in _header_pairs(info["headers"]):
        key_l = str(key).lower()
        if info["use_multipart"] and key_l == "content-type":
            continue
        if info["auth"] and key_l == "authorization":
            continue
        if key_l == "content-type" and info["content_type"] and not info["use_multipart"]:
            lines.append(assign % (_rb_escape(key), _rb_escape(info["content_type"])))
            continue
        lines.append(assign % (_rb_escape(key), _rb_escape(value)))
    if (
        info["content_type"]
        and not info["use_multipart"]
        and info["has_text"]
        and _header_value(info["headers"], "Content-Type") is None
    ):
        lines.append(assign % ("Content-Type", _rb_escape(info["content_type"])))


@register_generator("ruby_nethttp")
def generate_ruby_nethttp(data: dict) -> str:
    """Sinh ma Ruby dung net/http."""
    info = _collect(data)
    klass = info["method"].capitalize()
    lines = [
        "require 'net/http'",
        "require 'uri'",
        "",
        "uri = URI('%s')" % _rb_escape(info["url"]),
    ]
    if klass in _NETHTTP_CLASSES:
        lines.append("request = Net::HTTP::%s.new(uri)" % klass)
    else:
        has_body = "true" if (info["use_multipart"] or info["has_text"]) else "false"
        lines.append(
            "request = Net::HTTPGenericRequest.new('%s', %s, true, uri)"
            % (_rb_escape(info["method"]), has_body)
        )

    _emit_headers(lines, info, "request['%s'] = '%s'")

    if info["auth"]:
        lines.append(
            "request.basic_auth('%s', '%s')"
            % (_rb_escape(info["auth"][0]), _rb_escape(info["auth"][1]))
        )

    if info["use_multipart"]:
        lines.append("form_data = [")
        for key, raw in info["form_items"]:
            path = _parse_open_path(raw)
            if path is not None:
                lines.append(
                    "  ['%s', File.open('%s')],"
                    % (_rb_escape(key), _rb_escape(path))
                )
            else:
                lines.append(
                    "  ['%s', '%s']," % (_rb_escape(key), _rb_escape(raw))
                )
        if info["has_text"]:
            lines.append("  ['data', '%s']," % _rb_escape(info["text_body"]))
        lines.append("]")
        lines.append("request.set_form(form_data, 'multipart/form-data')")
    elif info["has_text"]:
        lines.append("request.body = '%s'" % _rb_escape(info["text_body"]))

    lines.extend(
        [
            "",
            "req_options = {",
            "  use_ssl: uri.scheme == 'https',",
            "}",
            "",
            "response = Net::HTTP.start(uri.hostname, uri.port, req_options) do |http|",
            "  http.request(request)",
            "end",
            "",
            "puts response.body",
        ]
    )
    return "\n".join(lines)


@register_generator("ruby_httparty")
def generate_ruby_httparty(data: dict) -> str:
    """Sinh ma Ruby dung HTTParty."""
    info = _collect(data)
    lines = ["require 'httparty'", "", "url = '%s'" % _rb_escape(info["url"]), "options = {}", ""]

    header_lines = []
    _emit_headers(header_lines, info, "  '%s' => '%s',")
    if header_lines:
        lines.append("options[:headers] = {")
        lines.extend(header_lines)
        lines.append("}")

    if info["auth"]:
        lines.append("options[:basic_auth] = {")
        lines.append("  username: '%s'," % _rb_escape(info["auth"][0]))
        lines.append("  password: '%s'" % _rb_escape(info["auth"][1]))
        lines.append("}")

    if info["use_multipart"]:
        lines.append("options[:multipart] = true")
        lines.append("options[:body] = {")
        for key, raw in info["form_items"]:
            path = _parse_open_path(raw)
            if path is not None:
                lines.append(
                    "  '%s' => File.open('%s'),"
                    % (_rb_escape(key), _rb_escape(path))
                )
            else:
                lines.append(
                    "  '%s' => '%s'," % (_rb_escape(key), _rb_escape(raw))
                )
        if info["has_text"]:
            lines.append("  'data' => '%s'," % _rb_escape(info["text_body"]))
        lines.append("}")
    elif info["has_text"]:
        lines.append("options[:body] = '%s'" % _rb_escape(info["text_body"]))

    lines.append("")
    method = info["method"].lower()
    if method in _HTTPARTY_METHODS:
        lines.append("response = HTTParty.%s(url, options)" % method)
    else:
        lines.append("response = HTTParty.send('%s', url, options)" % _rb_escape(method))
    lines.extend(["", "puts response.body"])
    return "\n".join(lines)

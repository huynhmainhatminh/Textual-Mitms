# core/generators/r_gen.py
import json
import re
from urllib.parse import urlencode

from . import register_generator
from .utils import escape_string


_OPEN_FILE_RE = re.compile(r"""^open\(\s*(['"])(.*)\1\s*\)$""")
_HTTR_VERBS = ("get", "post", "put", "delete", "patch", "head")


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _r_escape(value):
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


@register_generator("r_httr")
def generate_r_httr(data: dict) -> str:
    """Sinh ma R dung httr."""
    info = _collect(data)
    lines = ["library(httr)", ""]

    header_items = []
    for key, value in _header_pairs(info["headers"]):
        key_l = str(key).lower()
        if info["use_multipart"] and key_l == "content-type":
            continue
        if info["auth"] and key_l == "authorization":
            continue
        if key_l == "content-type" and info["content_type"] and not info["use_multipart"]:
            header_items.append(
                "    `%s` = '%s'" % (_r_escape(key), _r_escape(info["content_type"]))
            )
            continue
        header_items.append(
            "    `%s` = '%s'" % (_r_escape(key), _r_escape(value))
        )
    if (
        info["content_type"]
        and not info["use_multipart"]
        and info["has_text"]
        and _header_value(info["headers"], "Content-Type") is None
    ):
        header_items.append(
            "    `Content-Type` = '%s'" % _r_escape(info["content_type"])
        )

    if header_items:
        lines.append("headers = c(")
        lines.append(",\n".join(header_items))
        lines.append(")")
        lines.append("")

    extra = []
    if info["use_multipart"]:
        form_items = []
        for key, raw in info["form_items"]:
            path = _parse_open_path(raw)
            if path is not None:
                form_items.append(
                    "    '%s' = upload_file('%s')"
                    % (_r_escape(key), _r_escape(path))
                )
            else:
                form_items.append(
                    "    '%s' = '%s'" % (_r_escape(key), _r_escape(raw))
                )
        if info["has_text"]:
            form_items.append(
                "    'data' = '%s'" % _r_escape(info["text_body"])
            )
        lines.append("body = list(")
        lines.append(",\n".join(form_items))
        lines.append(")")
        extra.append("body = body")
        extra.append('encode = "multipart"')
    elif info["has_text"]:
        lines.append("body = '%s'" % _r_escape(info["text_body"]))
        extra.append("body = body")
        extra.append('encode = "raw"')

    req_args = ["url = '%s'" % _r_escape(info["url"])]
    if header_items:
        req_args.append("add_headers(.headers = headers)")
    req_args.extend(extra)
    if info["auth"]:
        req_args.append(
            "authenticate('%s', '%s')"
            % (_r_escape(info["auth"][0]), _r_escape(info["auth"][1]))
        )

    method = info["method"].lower()
    joined = ",\n    ".join(req_args)
    if method in _HTTR_VERBS:
        lines.append("response <- %s(\n    %s\n)" % (method, joined))
    else:
        lines.append(
            "response <- VERB(\n    '%s',\n    %s\n)" % (_r_escape(info["method"]), joined)
        )
    lines.append("")
    lines.append("# Xem noi dung phan hoi")
    lines.append("content(response, 'text', encoding = 'UTF-8')")
    return "\n".join(lines)


@register_generator("r_httr2")
def generate_r_httr2(data: dict) -> str:
    """Sinh ma R dung httr2 voi pipe |>."""
    info = _collect(data)
    lines = ["library(httr2)", ""]
    lines.append('req <- request("%s") |>' % _r_escape(info["url"]))
    if info["method"] != "GET":
        lines.append('  req_method("%s") |>' % _r_escape(info["method"]))

    header_args = []
    for key, value in _header_pairs(info["headers"]):
        key_l = str(key).lower()
        if info["use_multipart"] and key_l == "content-type":
            continue
        if info["auth"] and key_l == "authorization":
            continue
        if key_l == "content-type" and info["content_type"] and not info["use_multipart"]:
            header_args.append(
                '`%s` = "%s"' % (_r_escape(key), _r_escape(info["content_type"]))
            )
            continue
        header_args.append(
            '`%s` = "%s"' % (_r_escape(key), _r_escape(value))
        )
    if (
        info["content_type"]
        and not info["use_multipart"]
        and info["has_text"]
        and _header_value(info["headers"], "Content-Type") is None
    ):
        header_args.append('`Content-Type` = "%s"' % _r_escape(info["content_type"]))

    if header_args:
        lines.append("  req_headers(")
        for i, arg in enumerate(header_args):
            comma = "," if i < len(header_args) - 1 else ""
            lines.append("    %s%s" % (arg, comma))
        lines.append("  ) |>")

    if info["auth"]:
        lines.append(
            '  req_auth_basic("%s", "%s") |>'
            % (_r_escape(info["auth"][0]), _r_escape(info["auth"][1]))
        )

    if info["use_multipart"]:
        lines.append("  req_body_multipart(")
        form_args = []
        for key, raw in info["form_items"]:
            path = _parse_open_path(raw)
            if path is not None:
                form_args.append(
                    '`%s` = curl::form_file("%s")'
                    % (_r_escape(key), _r_escape(path))
                )
            else:
                form_args.append(
                    '`%s` = "%s"' % (_r_escape(key), _r_escape(raw))
                )
        if info["has_text"]:
            form_args.append('`data` = "%s"' % _r_escape(info["text_body"]))
        for i, arg in enumerate(form_args):
            comma = "," if i < len(form_args) - 1 else ""
            lines.append("    %s%s" % (arg, comma))
        lines.append("  ) |>")
    elif info["has_text"]:
        lines.append(
            '  req_body_raw("%s") |>' % _r_escape(info["text_body"])
        )

    if lines[-1].endswith(" |>"):
        lines[-1] = lines[-1][:-3]

    lines.extend(["", "resp <- req_perform(req)", "cat(resp_body_string(resp))"])
    return "\n".join(lines)

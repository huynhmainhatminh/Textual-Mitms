# core/generators/javascript_gen.py
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


def _js_escape(value):
    return escape_string(_as_text(value))


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


def _json_literal(value, indent_spaces):
    dumped = json.dumps(value, indent=4, ensure_ascii=False)
    pad = " " * indent_spaces
    return dumped.replace("\n", "\n" + pad)


def _text_body(data_body, is_json, content_type):
    if data_body is None or data_body is False:
        return None, content_type, False

    if isinstance(data_body, bytes):
        data_body = data_body.decode("utf-8")

    if isinstance(data_body, (dict, list)):
        want_json = bool(is_json) or (
            content_type and "json" in content_type.lower()
        ) or isinstance(data_body, list)
        if want_json:
            if not content_type or "json" not in content_type.lower():
                content_type = "application/json"
            return data_body, content_type, True
        if isinstance(data_body, dict):
            body = urlencode(
                {str(k): "" if v is None else str(v) for k, v in data_body.items()},
                doseq=True,
            )
            if not content_type:
                content_type = "application/x-www-form-urlencoded"
            return body, content_type, False
        return json.dumps(data_body, ensure_ascii=False), content_type, False

    if isinstance(data_body, str):
        if not data_body:
            return None, content_type, False
        if is_json or (content_type and "json" in content_type.lower()):
            try:
                parsed = json.loads(data_body)
                if not content_type or "json" not in content_type.lower():
                    content_type = "application/json"
                return parsed, content_type, True
            except json.JSONDecodeError:
                if is_json and (not content_type or "json" not in content_type.lower()):
                    content_type = "application/json"
                return data_body, content_type, False
        return data_body, content_type, False

    return _as_text(data_body), content_type, False


def _auth_js(auth):
    user = _js_escape(auth[0])
    password = _js_escape(auth[1])
    # btoa chi an toan Latin-1; encodeURIComponent giu dung user/pass Unicode.
    return (
        '"Basic " + btoa(unescape(encodeURIComponent("'
        + user
        + ":"
        + password
        + '")))'
    )


def _form_append_lines(var_name, form_items, extra_text, file_note):
    lines = []
    for key, raw in form_items:
        path = _parse_open_path(raw)
        if path is not None:
            lines.append(f"// {file_note}")
            lines.append(
                f'{var_name}.append("{_js_escape(key)}", "{_js_escape(path)}");'
            )
        else:
            lines.append(
                f'{var_name}.append("{_js_escape(key)}", "{_js_escape(raw)}");'
            )
    if extra_text is not None:
        if isinstance(extra_text, (dict, list)):
            extra = json.dumps(extra_text, ensure_ascii=False)
        else:
            extra = extra_text
        lines.append(f'{var_name}.append("data", "{_js_escape(extra)}");')
    return lines


def _collect(data):
    url = _as_text(data["url"])
    method = _as_text(data["method"]).upper() or "GET"
    headers = data["headers"] or {}
    form_items = _files_form_items(data["files_form"])
    form_unparsed = bool(data["files_form"]) and form_items is None
    if form_items is None:
        form_items = []
    content_type = _header_value(headers, "Content-Type")
    body, content_type, is_json_obj = _text_body(
        data["data_body"], data["is_json"], content_type
    )
    return {
        "url": url,
        "method": method,
        "headers": headers,
        "auth": data["auth"],
        "form_items": form_items,
        "form_unparsed": form_unparsed,
        "body": body,
        "content_type": content_type,
        "is_json_obj": is_json_obj,
        "use_multipart": bool(form_items),
        "forbid_body": method in ("GET", "HEAD") and (
            bool(form_items) or body is not None
        ),
    }


def _header_js_lines(info, indent, skip_content_type):
    out = []
    seen = set()
    for key, value in _headers_items(info["headers"]):
        key_l = str(key).lower()
        seen.add(key_l)
        if skip_content_type and key_l == "content-type":
            continue
        if info["auth"] and key_l == "authorization":
            continue
        if key_l == "content-type" and info["content_type"] and not info["use_multipart"]:
            out.append(
                f'{indent}"{_js_escape(key)}": "{_js_escape(info["content_type"])}"'
            )
            continue
        out.append(f'{indent}"{_js_escape(key)}": "{_js_escape(value)}"')
    if (
        info["content_type"]
        and not info["use_multipart"]
        and "content-type" not in seen
        and info["body"] is not None
        and not info["forbid_body"]
    ):
        out.append(f'{indent}"Content-Type": "{_js_escape(info["content_type"])}"')
    if info["auth"]:
        out.append(f'{indent}"Authorization": {_auth_js(info["auth"])}')
    return out


@register_generator("javascript_fetch")
def generate_javascript_fetch(data: dict) -> str:
    info = _collect(data)
    lines = []
    if info["form_unparsed"]:
        lines.append("// CANH BAO: files_form khong phai dict hoac list cap (name, value).")

    emit_body = not info["forbid_body"]
    if info["use_multipart"] and emit_body:
        lines.append("const formData = new FormData();")
        lines.extend(
            _form_append_lines(
                "formData",
                info["form_items"],
                info["body"],
                "Trinh duyet: thay path bang File (vd. fileInput.files[0]). Node: fs.createReadStream.",
            )
        )
        lines.append("")
    elif info["forbid_body"]:
        lines.append(f"// CANH BAO: Fetch spec cam body tren {info['method']}.")
        lines.append("")

    lines.append("const options = {")
    lines.append(f'    method: "{_js_escape(info["method"])}",')

    header_lines = _header_js_lines(
        info, "        ", skip_content_type=(info["use_multipart"] and emit_body)
    )
    if header_lines:
        lines.append("    headers: {")
        lines.append(",\n".join(header_lines))
        lines.append("    },")

    if emit_body and info["use_multipart"]:
        lines.append("    body: formData")
    elif emit_body and info["body"] is not None:
        if info["is_json_obj"]:
            lines.append(
                "    body: JSON.stringify("
                + _json_literal(info["body"], 8)
                + ")"
            )
        else:
            lines.append(f'    body: "{_js_escape(info["body"])}"')

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]

    lines.append("};")
    lines.append("")
    lines.append(f'fetch("{_js_escape(info["url"])}", options)')
    lines.append("    .then(response => response.text())")
    lines.append("    .then(result => console.log(result))")
    lines.append("    .catch(error => console.error('Error:', error));")
    return "\n".join(lines)


@register_generator("javascript_jquery")
def generate_javascript_jquery(data: dict) -> str:
    info = _collect(data)
    lines = []
    if info["form_unparsed"]:
        lines.append("// CANH BAO: files_form khong phai dict hoac list cap (name, value).")

    emit_body = not info["forbid_body"]
    if info["use_multipart"] and emit_body:
        lines.append("var form = new FormData();")
        lines.extend(
            _form_append_lines(
                "form",
                info["form_items"],
                info["body"],
                "Thay path bang File tu input type=file.",
            )
        )
        lines.append("")
    elif info["forbid_body"]:
        lines.append(f"// CANH BAO: {info['method']} kem body khong khop jQuery/XHR thong thuong.")
        lines.append("")

    lines.append("var settings = {")
    lines.append(f'    "url": "{_js_escape(info["url"])}",')
    lines.append(f'    "method": "{_js_escape(info["method"])}",')

    header_lines = _header_js_lines(
        info, "        ", skip_content_type=(info["use_multipart"] and emit_body)
    )
    if header_lines:
        lines.append('    "headers": {')
        lines.append(",\n".join(header_lines))
        lines.append("    },")

    if emit_body and info["use_multipart"]:
        # contentType/processData = false de browser tu gan boundary.
        # Khong set mimeType=multipart/form-data (thieu boundary).
        lines.append('    "processData": false,')
        lines.append('    "contentType": false,')
        lines.append('    "data": form')
    elif emit_body and info["body"] is not None:
        if info["is_json_obj"]:
            lines.append(
                '    "data": JSON.stringify('
                + _json_literal(info["body"], 8)
                + ")"
            )
        else:
            lines.append(f'    "data": "{_js_escape(info["body"])}"')

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]

    lines.append("};")
    lines.append("")
    lines.append("$.ajax(settings).done(function (response) {")
    lines.append("    console.log(response);")
    lines.append("}).fail(function (jqXHR, textStatus, errorThrown) {")
    lines.append("    console.error('Error:', textStatus, errorThrown);")
    lines.append("});")
    return "\n".join(lines)


@register_generator("javascript_xhr")
def generate_javascript_xhr(data: dict) -> str:
    info = _collect(data)
    lines = []
    if info["form_unparsed"]:
        lines.append("// CANH BAO: files_form khong phai dict hoac list cap (name, value).")

    emit_body = not info["forbid_body"]
    if info["use_multipart"] and emit_body:
        lines.append("let data = new FormData();")
        lines.extend(
            _form_append_lines(
                "data",
                info["form_items"],
                info["body"],
                "Thay path bang File tu input.",
            )
        )
        lines.append("")
    elif emit_body and info["body"] is not None:
        if info["is_json_obj"]:
            lines.append(
                "let data = JSON.stringify(" + _json_literal(info["body"], 4) + ");"
            )
        else:
            lines.append(f'let data = "{_js_escape(info["body"])}";')
        lines.append("")
    else:
        if info["forbid_body"]:
            lines.append(f"// CANH BAO: XHR khong gui body tren {info['method']}.")
        lines.append("let data = null;")
        lines.append("")

    lines.append("let xhr = new XMLHttpRequest();")
    lines.append("")
    lines.append('xhr.addEventListener("readystatechange", function() {')
    lines.append("    if (this.readyState === 4) {")
    lines.append("        console.log(this.responseText);")
    lines.append("    }")
    lines.append("});")
    lines.append("")
    lines.append(
        f'xhr.open("{_js_escape(info["method"])}", "{_js_escape(info["url"])}");'
    )

    for line in _header_js_lines(
        info, "", skip_content_type=(info["use_multipart"] and emit_body)
    ):
        # line dang "Key": "Val" hoac "Authorization": expr
        key, val = line.split(": ", 1)
        key = key.strip().strip('"')
        lines.append(f"xhr.setRequestHeader(\"{key}\", {val.rstrip()});")

    lines.append("")
    lines.append("xhr.send(data);")
    return "\n".join(lines)

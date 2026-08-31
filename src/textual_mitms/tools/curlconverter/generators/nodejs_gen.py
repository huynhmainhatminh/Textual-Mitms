# core/generators/nodejs_gen.py
"""Sinh JS trình duyệt / Node từ IR:
url, method, headers, auth, files_form, data_body, is_json.
"""

import json
import re

from . import register_generator
from .utils import escape_string


def _get_headers(data: dict) -> dict:
    headers = data.get("headers") or {}
    return headers if isinstance(headers, dict) else {}


def _get_files(data: dict) -> dict:
    files = data.get("files_form") or {}
    return files if isinstance(files, dict) else {}


def _auth_pair(auth) -> tuple:
    if not auth:
        return "", ""
    user = auth[0] if len(auth) > 0 else ""
    password = auth[1] if len(auth) > 1 else ""
    return ("" if user is None else str(user), "" if password is None else str(password))


def _is_json(data: dict) -> bool:
    return bool(data.get("is_json"))


def _js_str(value) -> str:
    """Literal JS double-quoted. json.dumps(str) ra chuỗi JS hợp lệ."""
    if value is None:
        value = ""
    return json.dumps(escape_string(str(value)), ensure_ascii=False)


def _js_squote(value) -> str:
    """Literal JS single-quoted (template Node gốc dùng '...')."""
    if value is None:
        value = ""
    dumped = json.dumps(escape_string(str(value)), ensure_ascii=False)
    inner = dumped[1:-1].replace("\\'", "'").replace("'", "\\'")
    return "'" + inner + "'"


def _is_file_handle_expr(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith("open(") and stripped.endswith(")")


def _path_from_open(expr: str):
    match = re.match(r"""^open\(\s*(['"])((?:\\.|(?!\1).)*)\1""", expr.strip())
    if not match:
        match = re.match(r"""^open\(\s*(['"])(.*?)\1""", expr.strip())
    if not match:
        return None
    return match.group(2).replace("\\'", "'").replace('\\"', '"')


def _unwrap_quoted(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _header_pairs(data: dict):
    files_form = _get_files(data)
    for key, value in _get_headers(data).items():
        if files_form and str(key).lower() == "content-type":
            continue
        yield key, "" if value is None else value


def _json_object_literal(body: str, indent: int) -> str:
    parsed = json.loads(body)
    dumped = json.dumps(parsed, indent=4, ensure_ascii=False)
    pad = " " * indent
    return dumped.replace("\n", "\n" + pad)


def _emit_node_form(lines: list, data: dict, var_name: str = "form", squote=True) -> None:
    q = _js_squote if squote else _js_str
    lines.append(f"const {var_name} = new FormData();")
    for key, raw in _get_files(data).items():
        value = "" if raw is None else str(raw)
        if _is_file_handle_expr(value):
            path = _path_from_open(value) or value
            lines.append(f"{var_name}.append({q(key)}, fs.createReadStream({q(path)}));")
        else:
            lines.append(f"{var_name}.append({q(key)}, {q(_unwrap_quoted(value))});")
    lines.append("")


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------


@register_generator("javascript_fetch")
def generate_javascript_fetch(data: dict) -> str:
    lines = []
    files_form = _get_files(data)
    if files_form:
        lines.append("const formData = new FormData();")
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                lines.append(
                    f"// Browser: thay {_js_str(path)} bằng File (input.files[0])."
                )
                lines.append(f"formData.append({_js_str(key)}, {_js_str(path)});")
            else:
                lines.append(
                    f"formData.append({_js_str(key)}, {_js_str(_unwrap_quoted(value))});"
                )
        lines.append("")

    lines.append("const options = {")
    lines.append(f"    method: {_js_str(str(data.get('method') or 'GET').upper())},")

    header_lines = []
    for key, value in _header_pairs(data):
        header_lines.append(f"        {_js_str(key)}: {_js_str(value)}")
    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        header_lines.append(
            f"        {_js_str('Authorization')}: {_js_str('Basic ')} + btoa({_js_str(user + ':' + password)})"
        )
    if header_lines:
        lines.append("    headers: {")
        lines.append(",\n".join(header_lines))
        lines.append("    },")

    if files_form:
        lines.append("    body: formData")
    elif data.get("data_body"):
        if _is_json(data):
            try:
                lit = _json_object_literal(data.get("data_body") or "", 8)
                lines.append(f"    body: JSON.stringify({lit})")
            except json.JSONDecodeError:
                lines.append(f"    body: {_js_str(data.get('data_body'))}")
        else:
            lines.append(f"    body: {_js_str(data.get('data_body'))}")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.extend(
        [
            "};",
            "",
            f"fetch({_js_str(data.get('url') or '')}, options)",
            "    .then(response => response.text())",
            "    .then(result => console.log(result))",
            "    .catch(error => console.error('Error:', error));",
        ]
    )
    return "\n".join(lines)


@register_generator("javascript_jquery")
def generate_javascript_jquery(data: dict) -> str:
    lines = []
    files_form = _get_files(data)
    if files_form:
        lines.append("var form = new FormData();")
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                lines.append(f"// Thay {_js_str(path)} bằng File từ <input type=\"file\">.")
                lines.append(f"form.append({_js_str(key)}, {_js_str(path)});")
            else:
                lines.append(
                    f"form.append({_js_str(key)}, {_js_str(_unwrap_quoted(value))});"
                )
        lines.append("")

    lines.append("var settings = {")
    lines.append(f"    {_js_str('url')}: {_js_str(data.get('url') or '')},")
    lines.append(f"    {_js_str('method')}: {_js_str(str(data.get('method') or 'GET').upper())},")
    lines.append(f"    {_js_str('crossDomain')}: true,")

    header_lines = []
    for key, value in _header_pairs(data):
        header_lines.append(f"        {_js_str(key)}: {_js_str(value)}")
    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        header_lines.append(
            f"        {_js_str('Authorization')}: {_js_str('Basic ')} + btoa({_js_str(user + ':' + password)})"
        )
    if header_lines:
        lines.append(f"    {_js_str('headers')}: {{")
        lines.append(",\n".join(header_lines))
        lines.append("    },")

    if files_form:
        # processData+contentType false: jQuery không đè FormData / boundary.
        # Không gắn mimeType: "multipart/form-data" (thiếu boundary).
        lines.append(f"    {_js_str('processData')}: false,")
        lines.append(f"    {_js_str('contentType')}: false,")
        lines.append(f"    {_js_str('data')}: form")
    elif data.get("data_body"):
        if _is_json(data):
            try:
                lit = _json_object_literal(data.get("data_body") or "", 8)
                lines.append(f"    {_js_str('data')}: JSON.stringify({lit})")
            except json.JSONDecodeError:
                lines.append(f"    {_js_str('data')}: {_js_str(data.get('data_body'))}")
        else:
            lines.append(f"    {_js_str('data')}: {_js_str(data.get('data_body'))}")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.extend(
        [
            "};",
            "",
            "$.ajax(settings).done(function (response) {",
            "    console.log(response);",
            "}).fail(function (jqXHR, textStatus, errorThrown) {",
            "    console.error('Lỗi:', textStatus, errorThrown);",
            "});",
        ]
    )
    return "\n".join(lines)


@register_generator("javascript_xhr")
def generate_javascript_xhr(data: dict) -> str:
    lines = []
    files_form = _get_files(data)
    if files_form:
        lines.append("let data = new FormData();")
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                lines.append(f"// Thay {_js_str(path)} bằng File từ input.")
                lines.append(f"data.append({_js_str(key)}, {_js_str(path)});")
            else:
                lines.append(
                    f"data.append({_js_str(key)}, {_js_str(_unwrap_quoted(value))});"
                )
        lines.append("")
    elif data.get("data_body"):
        if _is_json(data):
            try:
                lit = _json_object_literal(data.get("data_body") or "", 0)
                lines.append(f"let data = JSON.stringify({lit});")
            except json.JSONDecodeError:
                lines.append(f"let data = {_js_str(data.get('data_body'))};")
        else:
            lines.append(f"let data = {_js_str(data.get('data_body'))};")
        lines.append("")
    else:
        lines.append("let data = null;")
        lines.append("")

    lines.extend(
        [
            "let xhr = new XMLHttpRequest();",
            "xhr.withCredentials = true;",
            "",
            'xhr.addEventListener("readystatechange", function() {',
            "    if(this.readyState === 4) {",
            "        console.log(this.responseText);",
            "    }",
            "});",
            "",
            f"xhr.open({_js_str(str(data.get('method') or 'GET').upper())}, {_js_str(data.get('url') or '')});",
        ]
    )
    for key, value in _header_pairs(data):
        lines.append(f"xhr.setRequestHeader({_js_str(key)}, {_js_str(value)});")
    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        lines.append(
            f"xhr.setRequestHeader({_js_str('Authorization')}, {_js_str('Basic ')} + btoa({_js_str(user + ':' + password)}));"
        )
    lines.extend(["", "xhr.send(data);"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node.js
# ---------------------------------------------------------------------------


@register_generator("nodejs_axios")
def generate_nodejs_axios(data: dict) -> str:
    files_form = _get_files(data)
    lines = ["import axios from 'axios';"]
    if files_form:
        lines.append("import FormData from 'form-data';")
        lines.append("import fs from 'fs';")
    lines.append("")
    if files_form:
        _emit_node_form(lines, data)

    lines.append("const config = {")
    lines.append(f"    method: {_js_squote(str(data.get('method') or 'GET').lower())},")
    lines.append(f"    url: {_js_squote(data.get('url') or '')},")

    header_needed = bool(list(_header_pairs(data))) or bool(files_form)
    if header_needed:
        lines.append("    headers: {")
        for key, value in _header_pairs(data):
            lines.append(f"        {_js_squote(key)}: {_js_squote(value)},")
        if files_form:
            lines.append("        ...form.getHeaders()")
        elif lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("    },")

    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        lines.append("    auth: {")
        lines.append(f"        username: {_js_squote(user)},")
        lines.append(f"        password: {_js_squote(password)}")
        lines.append("    },")

    if files_form:
        lines.append("    data: form")
    elif data.get("data_body"):
        if _is_json(data):
            try:
                lines.append(
                    f"    data: {_json_object_literal(data.get('data_body') or '', 4)}"
                )
            except json.JSONDecodeError:
                lines.append(f"    data: {_js_squote(data.get('data_body'))}")
        else:
            lines.append(f"    data: {_js_squote(data.get('data_body'))}")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.extend(
        [
            "};",
            "",
            "axios.request(config)",
            "    .then((response) => {",
            "        console.log(response.data);",
            "    })",
            "    .catch((error) => {",
            "        console.error(error);",
            "    });",
        ]
    )
    return "\n".join(lines)


@register_generator("nodejs_got")
def generate_nodejs_got(data: dict) -> str:
    files_form = _get_files(data)
    lines = ["import got from 'got';"]
    if files_form:
        lines.append("import FormData from 'form-data';")
        lines.append("import fs from 'fs';")
    lines.append("")
    if files_form:
        _emit_node_form(lines, data)

    lines.append("const options = {")
    lines.append(f"    method: {_js_squote(str(data.get('method') or 'GET').upper())},")

    extra_headers = list(_header_pairs(data))
    if extra_headers or files_form:
        lines.append("    headers: {")
        for key, value in extra_headers:
            lines.append(f"        {_js_squote(key)}: {_js_squote(value)},")
        if files_form:
            lines.append("        ...form.getHeaders()")
        elif lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("    },")

    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        lines.append(f"    username: {_js_squote(user)},")
        lines.append(f"    password: {_js_squote(password)},")

    if files_form:
        lines.append("    body: form")
    elif data.get("data_body"):
        if _is_json(data):
            try:
                lines.append(
                    f"    json: {_json_object_literal(data.get('data_body') or '', 4)}"
                )
            except json.JSONDecodeError:
                lines.append(f"    body: {_js_squote(data.get('data_body'))}")
        else:
            lines.append(f"    body: {_js_squote(data.get('data_body'))}")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.extend(
        [
            "};",
            "",
            "try {",
            f"    const response = await got({_js_squote(data.get('url') or '')}, options);",
            "    console.log(response.body);",
            "} catch (error) {",
            "    console.error(error.response ? error.response.body : error.message);",
            "}",
        ]
    )
    return "\n".join(lines)


@register_generator("nodejs_ky")
def generate_nodejs_ky(data: dict) -> str:
    files_form = _get_files(data)
    lines = ["import ky from 'ky';"]
    if files_form:
        lines.append("import FormData from 'form-data';")
        lines.append("import fs from 'fs';")
    lines.append("")
    if files_form:
        _emit_node_form(lines, data)

    lines.append("const options = {")
    lines.append(f"    method: {_js_squote(str(data.get('method') or 'GET').upper())},")

    header_lines = []
    for key, value in _header_pairs(data):
        header_lines.append(f"        {_js_squote(key)}: {_js_squote(value)}")
    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        header_lines.append(
            "        'Authorization': 'Basic ' + Buffer.from("
            f"{_js_squote(user + ':' + password)}"
            ").toString('base64')"
        )
    if header_lines:
        lines.append("    headers: {")
        lines.append(",\n".join(header_lines))
        lines.append("    },")

    if files_form:
        lines.append("    body: form")
    elif data.get("data_body"):
        if _is_json(data):
            try:
                lines.append(
                    f"    json: {_json_object_literal(data.get('data_body') or '', 4)}"
                )
            except json.JSONDecodeError:
                lines.append(f"    body: {_js_squote(data.get('data_body'))}")
        else:
            lines.append(f"    body: {_js_squote(data.get('data_body'))}")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.extend(
        [
            "};",
            "",
            "try {",
            f"    const response = await ky({_js_squote(data.get('url') or '')}, options);",
            "    const responseData = await response.text();",
            "    console.log(responseData);",
            "} catch (error) {",
            "    console.error('Error:', error.message);",
            "}",
        ]
    )
    return "\n".join(lines)


@register_generator("nodejs_node_fetch")
def generate_nodejs_node_fetch(data: dict) -> str:
    files_form = _get_files(data)
    lines = ["import fetch from 'node-fetch';"]
    if files_form:
        lines.append("import FormData from 'form-data';")
        lines.append("import fs from 'fs';")
    lines.append("")
    if files_form:
        _emit_node_form(lines, data)

    lines.append("const options = {")
    lines.append(f"    method: {_js_squote(str(data.get('method') or 'GET').upper())},")

    header_lines = []
    for key, value in _header_pairs(data):
        header_lines.append(f"        {_js_squote(key)}: {_js_squote(value)}")
    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        header_lines.append(
            "        'Authorization': 'Basic ' + Buffer.from("
            f"{_js_squote(user + ':' + password)}"
            ").toString('base64')"
        )
    if files_form:
        header_lines.append("        ...form.getHeaders()")
    if header_lines:
        lines.append("    headers: {")
        lines.append(",\n".join(header_lines))
        lines.append("    },")

    if files_form:
        lines.append("    body: form")
    elif data.get("data_body"):
        if _is_json(data):
            try:
                lit = _json_object_literal(data.get("data_body") or "", 4)
                lines.append(f"    body: JSON.stringify({lit})")
            except json.JSONDecodeError:
                lines.append(f"    body: {_js_squote(data.get('data_body'))}")
        else:
            lines.append(f"    body: {_js_squote(data.get('data_body'))}")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.extend(
        [
            "};",
            "",
            "try {",
            f"    const response = await fetch({_js_squote(data.get('url') or '')}, options);",
            "    const responseData = await response.text();",
            "    console.log(responseData);",
            "} catch (error) {",
            "    console.error('Error:', error);",
            "}",
        ]
    )
    return "\n".join(lines)


@register_generator("nodejs_request")
def generate_nodejs_request(data: dict) -> str:
    files_form = _get_files(data)
    lines = ["var request = require('request');"]
    if files_form:
        lines.append("var fs = require('fs');")
    lines.append("")
    lines.append("var options = {")
    lines.append(f"  'method': {_js_squote(str(data.get('method') or 'GET').upper())},")
    lines.append(f"  'url': {_js_squote(data.get('url') or '')},")

    header_lines = [f"    {_js_squote(k)}: {_js_squote(v)}" for k, v in _header_pairs(data)]
    if header_lines:
        lines.append("  'headers': {")
        lines.append(",\n".join(header_lines))
        lines.append("  },")

    if files_form:
        form_lines = []
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                form_lines.append(
                    f"    {_js_squote(key)}: fs.createReadStream({_js_squote(path)})"
                )
            else:
                form_lines.append(
                    f"    {_js_squote(key)}: {_js_squote(_unwrap_quoted(value))}"
                )
        lines.append("  formData: {")
        lines.append(",\n".join(form_lines))
        lines.append("  },")
    elif data.get("data_body"):
        lines.append(f"  body: {_js_squote(data.get('data_body'))},")

    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        lines.append("  auth: {")
        lines.append(f"    user: {_js_squote(user)},")
        lines.append(f"    pass: {_js_squote(password)}")
        lines.append("  }")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.extend(
        [
            "};",
            "",
            "request(options, function (error, response) {",
            "  if (error) throw new Error(error);",
            "  console.log(response.body);",
            "});",
        ]
    )
    return "\n".join(lines)


@register_generator("nodejs_superagent")
def generate_nodejs_superagent(data: dict) -> str:
    files_form = _get_files(data)
    lines = [
        "import request from 'superagent';",
        "",
        f"let req = request({_js_squote(str(data.get('method') or 'GET').upper())}, {_js_squote(data.get('url') or '')});",
    ]
    for key, value in _header_pairs(data):
        lines.append(f"req.set({_js_squote(key)}, {_js_squote(value)});")
    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        lines.append(f"req.auth({_js_squote(user)}, {_js_squote(password)});")
    if files_form:
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                lines.append(f"req.attach({_js_squote(key)}, {_js_squote(path)});")
            else:
                lines.append(
                    f"req.field({_js_squote(key)}, {_js_squote(_unwrap_quoted(value))});"
                )
    elif data.get("data_body"):
        if _is_json(data):
            try:
                lit = _json_object_literal(data.get("data_body") or "", 4)
                lines.append(f"req.send({lit});")
            except json.JSONDecodeError:
                lines.append(f"req.send({_js_squote(data.get('data_body'))});")
        else:
            lines.append(f"req.send({_js_squote(data.get('data_body'))});")
    lines.extend(
        [
            "",
            "try {",
            "    const response = await req;",
            "    console.log(response.text);",
            "} catch (error) {",
            "    console.error(error.response ? error.response.text : error.message);",
            "}",
        ]
    )
    return "\n".join(lines)


@register_generator("nodejs_https")
def generate_nodejs_https(data: dict) -> str:
    files_form = _get_files(data)
    lines = [
        "import https from 'https';",
        "import http from 'http';",
        "import { URL } from 'url';",
    ]
    if files_form:
        lines.append("import FormData from 'form-data';")
        lines.append("import fs from 'fs';")
    lines.append("")
    if files_form:
        _emit_node_form(lines, data)

    lines.append(f"const parsedUrl = new URL({_js_squote(data.get('url') or '')});")
    lines.append("const options = {")
    lines.append("    hostname: parsedUrl.hostname,")
    lines.append("    port: parsedUrl.port || (parsedUrl.protocol === 'https:' ? 443 : 80),")
    lines.append("    path: parsedUrl.pathname + parsedUrl.search,")
    lines.append(f"    method: {_js_squote(str(data.get('method') or 'GET').upper())},")

    header_lines = [f"        {_js_squote(k)}: {_js_squote(v)}" for k, v in _header_pairs(data)]
    if data.get("auth"):
        user, password = _auth_pair(data.get("auth"))
        header_lines.append(
            "        'Authorization': 'Basic ' + Buffer.from("
            f"{_js_squote(user + ':' + password)}"
            ").toString('base64')"
        )
    if files_form:
        header_lines.append("        ...form.getHeaders()")
    if header_lines:
        lines.append("    headers: {")
        lines.append(",\n".join(header_lines))
        lines.append("    }")
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.extend(
        [
            "};",
            "",
            "const reqLib = parsedUrl.protocol === 'https:' ? https : http;",
            "const req = reqLib.request(options, (res) => {",
            "    const chunks = [];",
            "    res.on('data', (chunk) => {",
            "        chunks.push(chunk);",
            "    });",
            "    res.on('end', () => {",
            "        const body = Buffer.concat(chunks);",
            "        console.log(body.toString());",
            "    });",
            "});",
            "",
            "req.on('error', (error) => {",
            "    console.error(error);",
            "});",
            "",
        ]
    )
    if files_form:
        lines.append("form.pipe(req);")
    elif data.get("data_body"):
        if _is_json(data):
            try:
                lit = _json_object_literal(data.get("data_body") or "", 0)
                lines.append(f"req.write(JSON.stringify({lit}));")
            except json.JSONDecodeError:
                lines.append(f"req.write({_js_squote(data.get('data_body'))});")
        else:
            lines.append(f"req.write({_js_squote(data.get('data_body'))});")
        lines.append("req.end();")
    else:
        lines.append("req.end();")
    return "\n".join(lines)

# core/generators/php_gen.py
"""Sinh code PHP từ IR curl: url, method, headers, auth, files_form, data_body.

- php_curl   → ext-curl: CURLOPT_URL, CUSTOMREQUEST, HTTPHEADER,
               USERPWD, POSTFIELDS, CURLFile
- php_guzzle → Guzzle: headers, auth, body, multipart
"""

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


def _php_single(value) -> str:
    """Literal PHP single-quoted.

    Trong '...', chỉ \\ và ' cần escape. Không bọc kiểu Python \"...\".
    """
    if value is None:
        value = ""
    text = escape_string(str(value))
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


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


def _skip_content_type(data: dict, key) -> bool:
    return bool(_get_files(data)) and str(key).lower() == "content-type"


@register_generator("php_curl")
def generate_php_curl(data: dict) -> str:
    lines = ["<?php", "$ch = curl_init();"]

    url = data.get("url") or ""
    method = str(data.get("method") or "GET").upper()
    lines.append(f"curl_setopt($ch, CURLOPT_URL, {_php_single(url)});")
    lines.append("curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);")
    lines.append(f"curl_setopt($ch, CURLOPT_CUSTOMREQUEST, {_php_single(method)});")

    files_form = _get_files(data)
    headers = _get_headers(data)
    header_lines = []
    for key, value in headers.items():
        if _skip_content_type(data, key):
            continue
        rendered = f"{key}: {'' if value is None else value}"
        header_lines.append(f"    {_php_single(rendered)},")
    if header_lines:
        lines.append("")
        lines.append("$headers = array(")
        lines.extend(header_lines)
        lines.append(");")
        lines.append("curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);")

    auth = data.get("auth")
    if auth:
        user, password = _auth_pair(auth)
        lines.append("")
        lines.append(
            "curl_setopt($ch, CURLOPT_USERPWD, "
            f"{_php_single(user + ':' + password)});"
        )

    if files_form:
        lines.append("")
        lines.append("$post_fields = array(")
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                lines.append(
                    f"    {_php_single(key)} => new CURLFile({_php_single(path)}),"
                )
            else:
                lines.append(
                    f"    {_php_single(key)} => {_php_single(_unwrap_quoted(value))},"
                )
        lines.append(");")
        lines.append("curl_setopt($ch, CURLOPT_POSTFIELDS, $post_fields);")
    elif data.get("data_body"):
        lines.append("")
        lines.append(
            "curl_setopt($ch, CURLOPT_POSTFIELDS, "
            f"{_php_single(data.get('data_body'))});"
        )

    lines.extend(
        [
            "",
            "$response = curl_exec($ch);",
            "if (curl_errno($ch)) {",
            "    echo 'Error:' . curl_error($ch);",
            "}",
            "curl_close($ch);",
            "",
            "echo $response;",
            "?>",
        ]
    )
    return "\n".join(lines)


@register_generator("php_guzzle")
def generate_php_guzzle(data: dict) -> str:
    lines = [
        "<?php",
        "require 'vendor/autoload.php';",
        "use GuzzleHttp\\Client;",
        "",
        "$client = new Client();",
        "$options = [];",
    ]

    files_form = _get_files(data)
    headers = _get_headers(data)
    header_entries = []
    for key, value in headers.items():
        if _skip_content_type(data, key):
            continue
        header_entries.append(
            f"    {_php_single(key)} => {_php_single('' if value is None else value)},"
        )
    if header_entries:
        lines.append("$options['headers'] = [")
        lines.extend(header_entries)
        lines.append("];")

    auth = data.get("auth")
    if auth:
        user, password = _auth_pair(auth)
        lines.append(
            f"$options['auth'] = [{_php_single(user)}, {_php_single(password)}];"
        )

    if files_form:
        lines.append("$options['multipart'] = [")
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                contents = f"fopen({_php_single(path)}, 'r')"
            else:
                contents = _php_single(_unwrap_quoted(value))
            lines.extend(
                [
                    "    [",
                    f"        'name' => {_php_single(key)},",
                    f"        'contents' => {contents}",
                    "    ],",
                ]
            )
        lines.append("];")
    elif data.get("data_body"):
        lines.append(f"$options['body'] = {_php_single(data.get('data_body'))};")

    url = data.get("url") or ""
    method = str(data.get("method") or "GET").upper()
    lines.extend(
        [
            "",
            f"$response = $client->request({_php_single(method)}, {_php_single(url)}, $options);",
            "echo $response->getBody();",
            "?>",
        ]
    )
    return "\n".join(lines)

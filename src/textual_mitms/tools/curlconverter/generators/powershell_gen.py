# core/generators/powershell_gen.py
"""Sinh code PowerShell từ IR curl: url, method, headers, auth, files_form, data_body.

- powershell_restmethod → Invoke-RestMethod
- powershell_webrequest → Invoke-WebRequest

-Form cần PowerShell 6.1+ (tham số chính thức của hai cmdlet này).
"""

import base64
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


def _ps_single(value) -> str:
    """Literal chuỗi single-quoted của PowerShell.

    Trong '...', ký tự ' được escape bằng cách nhân đôi ('').
    escape_string vẫn được gọi theo convention dự án, nhưng không dùng
    kiểu bọc Python "..." vì backslash không escape trong PS single-quote.
    """
    if value is None:
        value = ""
    text = escape_string(str(value))
    return "'" + text.replace("'", "''") + "'"


def _is_file_handle_expr(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith("open(") and stripped.endswith(")")


def _path_from_open(expr: str):
    """Lấy path từ IR open('file', 'rb') hoặc open(\"file\", \"rb\")."""
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


def _emit_headers(lines: list, data: dict) -> bool:
    files_form = _get_files(data)
    headers_dict = {}
    for key, value in _get_headers(data).items():
        if files_form and str(key).lower() == "content-type":
            continue
        headers_dict[key] = value

    auth = data.get("auth")
    if auth:
        user, password = _auth_pair(auth)
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        for key in list(headers_dict):
            if str(key).lower() == "authorization":
                headers_dict.pop(key, None)
        headers_dict["Authorization"] = f"Basic {token}"

    if not headers_dict:
        return False

    lines.append("$headers = @{")
    for key, value in headers_dict.items():
        lines.append(f"    {_ps_single(key)} = {_ps_single('' if value is None else value)}")
    lines.append("}")
    lines.append("")
    return True


def _emit_payload(lines: list, data: dict) -> str:
    files_form = _get_files(data)
    if files_form:
        lines.append("$form = @{")
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value)
                if path is None:
                    path = value
                lines.append(
                    f"    {_ps_single(key)} = Get-Item -Path {_ps_single(path)}"
                )
            else:
                lines.append(
                    f"    {_ps_single(key)} = {_ps_single(_unwrap_quoted(value))}"
                )
        lines.append("}")
        lines.append("")
        return "form"

    body = data.get("data_body") or ""
    if body:
        lines.append(f"$body = {_ps_single(body)}")
        lines.append("")
        return "body"
    return ""


def _build_invoke(cmdlet: str, data: dict, has_headers: bool, payload_kind: str) -> str:
    url = data.get("url") or ""
    method = str(data.get("method") or "GET").upper()
    parts = [
        cmdlet,
        f"-Uri {_ps_single(url)}",
        f"-Method {_ps_single(method)}",
    ]
    if has_headers:
        parts.append("-Headers $headers")
    if payload_kind == "form":
        parts.append("-Form $form")
    elif payload_kind == "body":
        parts.append("-Body $body")
    return " ".join(parts)


@register_generator("powershell_restmethod")
def generate_powershell_restmethod(data: dict) -> str:
    lines = []
    has_headers = _emit_headers(lines, data)
    payload_kind = _emit_payload(lines, data)
    lines.append(
        "$response = " + _build_invoke("Invoke-RestMethod", data, has_headers, payload_kind)
    )
    lines.append("$response | ConvertTo-Json -Depth 10")
    return "\n".join(lines)


@register_generator("powershell_webrequest")
def generate_powershell_webrequest(data: dict) -> str:
    lines = []
    has_headers = _emit_headers(lines, data)
    payload_kind = _emit_payload(lines, data)
    lines.append(
        "$response = " + _build_invoke("Invoke-WebRequest", data, has_headers, payload_kind)
    )
    lines.append("$response.Content")
    return "\n".join(lines)

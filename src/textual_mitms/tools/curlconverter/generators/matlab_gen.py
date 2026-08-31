# core/generators/matlab_gen.py
"""Sinh MATLAB từ IR: url, method, headers, auth, files_form, data_body, is_json.

matlab_http → matlab.net.http + matlab.net.http.io
  HeaderField / RequestMessage / RequestMethod
  StringProvider / MultipartFormProvider / FileProvider
"""

import base64
import re

from . import register_generator
from .utils import escape_string

_REQUEST_METHODS = {
    "GET",
    "PUT",
    "POST",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS",
    "CONNECT",
    "TRACE",
}


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


def _ml_str(value) -> str:
    """Literal MATLAB '...'. Nháy đơn được nhân đôi."""
    if value is None:
        value = ""
    text = escape_string(str(value)).replace("'", "''")
    return "'" + text + "'"


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


@register_generator("matlab_http")
def generate_matlab(data: dict) -> str:
    files_form = _get_files(data)
    lines = [
        "%% HTTP Interface Request",
        "import matlab.net.*",
        "import matlab.net.http.*",
        "import matlab.net.http.io.*",
        "",
        "headers = [",
    ]

    header_fields = []
    for key, value in _get_headers(data).items():
        if files_form and str(key).lower() == "content-type":
            continue
        header_fields.append(
            f"    HeaderField({_ml_str(key)}, {_ml_str('' if value is None else value)})"
        )

    auth = data.get("auth")
    if auth:
        user, password = _auth_pair(auth)
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        header_fields.append(
            f"    HeaderField('Authorization', {_ml_str('Basic ' + token)})"
        )

    if header_fields:
        lines.extend(header_fields)
    else:
        lines.append("    % Không có header")
    lines.extend(["]';", ""])

    if files_form:
        parts = []
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                parts.append(f"    {_ml_str(key)}, FileProvider({_ml_str(path)})")
            else:
                parts.append(f"    {_ml_str(key)}, {_ml_str(_unwrap_quoted(value))}")
        lines.append("provider = MultipartFormProvider(...")
        for i, part in enumerate(parts):
            suffix = ", ..." if i < len(parts) - 1 else ""
            lines.append(part + suffix)
        lines.append(");")
        has_body = True
    elif data.get("data_body"):
        lines.append(f"bodyData = {_ml_str(data.get('data_body'))};")
        if data.get("is_json"):
            lines.append("provider = StringProvider(bodyData, 'application/json');")
        else:
            lines.append("provider = StringProvider(bodyData);")
        has_body = True
    else:
        lines.append("provider = [];")
        has_body = False

    method = str(data.get("method") or "GET").upper()
    url = data.get("url") or ""
    lines.append("")
    lines.append(f"uri = URI({_ml_str(url)});")

    # RequestMethod là enumeration chính thức; method lạ dùng chuỗi (RequestMessage chấp nhận).
    if method in _REQUEST_METHODS:
        method_arg = f"RequestMethod.{method}"
    else:
        method_arg = _ml_str(method)

    if has_body:
        lines.append(f"request = RequestMessage({method_arg}, headers, provider);")
    else:
        lines.append(f"request = RequestMessage({method_arg}, headers);")

    lines.extend(
        [
            "response = request.send(uri.EncodedURI);",
            "",
            "% Hiển thị kết quả",
            "disp(response.Body.Data);",
        ]
    )
    return "\n".join(lines)

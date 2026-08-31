# core/generators/perl_gen.py
"""Sinh code Perl từ IR curl: url, method, headers, auth, files_form, data_body.

perl_lwp → LWP::UserAgent + HTTP::Request
         hoặc HTTP::Request::Common POST(..., Content_Type => 'form-data')
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


def _perl_single(value) -> str:
    """Literal Perl single-quoted. Trong '...', chỉ \\ và ' được escape."""
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


@register_generator("perl_lwp")
def generate_perl_lwp(data: dict) -> str:
    files_form = _get_files(data)
    auth = data.get("auth")

    lines = [
        "use strict;",
        "use warnings;",
        "use LWP::UserAgent;",
    ]
    if auth:
        lines.append("use MIME::Base64;")
    if files_form:
        lines.append("use HTTP::Request::Common;")
    else:
        lines.append("use HTTP::Request;")

    lines.extend(["", "my $ua = LWP::UserAgent->new();"])

    url = data.get("url") or ""
    method = str(data.get("method") or "GET").upper()

    if files_form:
        # HTTP::Request::Common: Content_Type => 'form-data' + Content array.
        # File field: name => [ $path ]
        lines.extend(
            [
                f"my $req = POST {_perl_single(url)},",
                "    Content_Type => 'form-data',",
                "    Content      => [",
            ]
        )
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                lines.append(
                    f"        {_perl_single(key)} => [{_perl_single(path)}],"
                )
            else:
                lines.append(
                    f"        {_perl_single(key)} => {_perl_single(_unwrap_quoted(value))},"
                )
        lines.append("    ];")
        if method != "POST":
            lines.append(f"$req->method({_perl_single(method)});")
    else:
        lines.append(
            f"my $req = HTTP::Request->new({_perl_single(method)} => {_perl_single(url)});"
        )
        body = data.get("data_body") or ""
        if body:
            lines.append(f"$req->content({_perl_single(body)});")

    for key, value in _get_headers(data).items():
        if files_form and str(key).lower() == "content-type":
            continue
        lines.append(
            f"$req->header({_perl_single(key)} => {_perl_single('' if value is None else value)});"
        )

    if auth:
        user, password = _auth_pair(auth)
        # encode_base64($str, '') — tham số 2 rỗng bỏ newline (MIME::Base64).
        lines.append(
            "$req->header('Authorization' => 'Basic ' . encode_base64("
            f"{_perl_single(user + ':' + password)}, ''));"
        )

    lines.extend(
        [
            "",
            "my $res = $ua->request($req);",
            "if ($res->is_success) {",
            "    print $res->decoded_content;",
            "} else {",
            "    die $res->status_line;",
            "}",
        ]
    )
    return "\n".join(lines)

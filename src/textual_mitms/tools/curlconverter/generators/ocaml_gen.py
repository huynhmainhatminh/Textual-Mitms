# core/generators/ocaml_gen.py
"""Sinh code OCaml từ IR curl: url, method, headers, auth, files_form, data_body.

ocaml_cohttp → Cohttp_lwt_unix.Client.call
  Header.init / of_list / add / add_authorization (`Basic (user, pass))
  Cohttp_lwt.Body.of_string | empty
  Cohttp.Code.method_of_string  (cohttp 5.3+: string -> meth)
"""

import re

from . import register_generator
from .utils import escape_string

# Cohttp.Code.meth constructors (cohttp 5.3 Code.meth).
_METH_VARIANTS = {
    "GET": "`GET",
    "POST": "`POST",
    "HEAD": "`HEAD",
    "DELETE": "`DELETE",
    "PATCH": "`PATCH",
    "PUT": "`PUT",
    "OPTIONS": "`OPTIONS",
    "TRACE": "`TRACE",
    "CONNECT": "`CONNECT",
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
    """Literal chuỗi OCaml "...". Escape \\ " và ký tự điều khiển."""
    if value is None:
        value = ""
    text = escape_string(str(value))
    out = []
    for char in text:
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


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


def _meth_expr(method: str) -> str:
    variant = _METH_VARIANTS.get(method)
    if variant:
        return variant
    return f"(Cohttp.Code.method_of_string {_ml_str(method)})"


@register_generator("ocaml_cohttp")
def generate_ocaml(data: dict) -> str:
    files_form = _get_files(data)
    url = data.get("url") or ""
    method = str(data.get("method") or "GET").upper()

    lines = [
        "open Lwt",
        "open Cohttp",
        "open Cohttp_lwt_unix",
        "",
        "let () =",
        f"  let uri = Uri.of_string {_ml_str(url)} in",
    ]

    headers = _get_headers(data)
    header_pairs = []
    for key, value in headers.items():
        if files_form and str(key).lower() == "content-type":
            continue
        header_pairs.append(
            f"    ({_ml_str(key)}, {_ml_str('' if value is None else value)});"
        )
    if header_pairs:
        lines.append("  let headers = Header.of_list [")
        lines.extend(header_pairs)
        lines.append("  ] in")
    else:
        lines.append("  let headers = Header.init () in")

    auth = data.get("auth")
    if auth:
        user, password = _auth_pair(auth)
        lines.append(
            "  let headers = Header.add_authorization headers "
            f"(`Basic ({_ml_str(user)}, {_ml_str(password)})) in"
        )

    if files_form:
        # Multipart tự ghép — Cohttp không có helper multipart trong API gốc file này dùng.
        boundary = "---011000010111000001101001"
        lines.append(f"  let boundary = {_ml_str(boundary)} in")
        lines.append(
            '  let headers = Header.add headers "content-type" '
            '("multipart/form-data; boundary=" ^ boundary) in'
        )
        lines.append("  let body_str = Buffer.create 1024 in")
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            lines.append(
                "  Buffer.add_string body_str (Printf.sprintf \"--%s\\r\\n\" boundary);"
            )
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                lines.append(
                    "  Buffer.add_string body_str "
                    f'("Content-Disposition: form-data; name=\\"" ^ {_ml_str(key)} ^ '
                    f'"\\"; filename=\\"" ^ {_ml_str(path)} ^ "\\"\\r\\n");'
                )
                lines.append(
                    '  Buffer.add_string body_str "Content-Type: application/octet-stream\\r\\n\\r\\n";'
                )
                lines.append(f"  let ic = open_in_bin {_ml_str(path)} in")
                lines.append("  let file_len = in_channel_length ic in")
                lines.append("  let file_data = really_input_string ic file_len in")
                lines.append("  close_in ic;")
                lines.append("  Buffer.add_string body_str file_data;")
                lines.append('  Buffer.add_string body_str "\\r\\n";')
            else:
                text = _unwrap_quoted(value)
                lines.append(
                    "  Buffer.add_string body_str "
                    f'("Content-Disposition: form-data; name=\\"" ^ {_ml_str(key)} ^ "\\"\\r\\n\\r\\n");'
                )
                lines.append(f"  Buffer.add_string body_str {_ml_str(text)};")
                lines.append('  Buffer.add_string body_str "\\r\\n";')
        lines.append(
            '  Buffer.add_string body_str (Printf.sprintf "--%s--\\r\\n" boundary);'
        )
        lines.append(
            "  let body = Cohttp_lwt.Body.of_string (Buffer.contents body_str) in"
        )
    elif data.get("data_body"):
        lines.append(
            "  let body = Cohttp_lwt.Body.of_string "
            f"{_ml_str(data.get('data_body'))} in"
        )
    else:
        lines.append("  let body = Cohttp_lwt.Body.empty in")

    lines.extend(
        [
            "",
            "  let request =",
            f"    Client.call ~headers ~body {_meth_expr(method)} uri >>= fun (resp, body) ->",
            "    let code = resp |> Response.status |> Code.code_of_status in",
            '    Printf.printf "Status: %d\\n" code;',
            "    Cohttp_lwt.Body.to_string body >>= fun body_str ->",
            '    Printf.printf "Body: %s\\n" body_str;',
            "    Lwt.return_unit",
            "  in",
            "  Lwt_main.run request",
        ]
    )
    return "\n".join(lines)

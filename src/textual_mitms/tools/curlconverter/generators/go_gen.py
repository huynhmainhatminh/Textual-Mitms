# core/generators/go_gen.py
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


def _go_escape(value):
    return escape_string(_as_text(value))


def _go_ident(name, prefix):
    ident = re.sub(r"[^0-9A-Za-z_]", "_", _as_text(name))
    if not ident:
        ident = "field"
    if ident[0].isdigit():
        ident = "f_" + ident
    return prefix + ident


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


def _header_value(headers, name):
    if not headers:
        return None
    pairs = headers.items() if isinstance(headers, dict) else headers
    target = name.lower()
    for key, value in pairs:
        if str(key).lower() == target:
            return value
    return None


def _header_pairs(headers):
    if not headers:
        return []
    if isinstance(headers, dict):
        return list(headers.items())
    return list(headers)


@register_generator("go_http")
def generate_go(data: dict) -> str:
    url = _go_escape(data["url"])
    method = _as_text(data["method"]).upper() or "GET"
    headers = data["headers"] or {}
    auth = data["auth"]
    is_json = data["is_json"] if "is_json" in data else False
    content_type = _header_value(headers, "Content-Type")
    text_body, content_type, has_text = _serialize_body(
        data["data_body"], content_type, is_json
    )
    form_items = _files_form_items(data["files_form"])
    if form_items is None:
        form_items = []
    use_multipart = bool(form_items)
    has_file = any(_parse_open_path(raw) is not None for _, raw in form_items)

    imports = ['\t"fmt"', '\t"io"', '\t"log"', '\t"net/http"']
    if has_text and not use_multipart:
        imports.append('\t"strings"')
    if use_multipart:
        imports.extend(['\t"bytes"', '\t"mime/multipart"'])
        if has_file:
            imports.extend(['\t"os"', '\t"path/filepath"'])

    lines = ["package main", "", "import ("]
    lines.extend(imports)
    lines.append(")")
    lines.append("")
    lines.append("func main() {")

    declared_err = False
    if use_multipart:
        lines.append("\tpayload := &bytes.Buffer{}")
        lines.append("\twriter := multipart.NewWriter(payload)")
        used_idents = set()
        for key, raw in form_items:
            path = _parse_open_path(raw)
            if path is not None:
                ident = _go_ident(key, "")
                n = 1
                base = ident
                while ident in used_idents:
                    n += 1
                    ident = "%s_%d" % (base, n)
                used_idents.add(ident)
                file_var = "file_" + ident
                part_var = "part_" + ident
                safe_path = _go_escape(path)
                lines.append(f'\t{file_var}, err := os.Open("{safe_path}")')
                declared_err = True
                lines.extend(
                    [
                        "\tif err != nil {",
                        "\t\tlog.Fatal(err)",
                        "\t}",
                        f"\tdefer {file_var}.Close()",
                        f'\t{part_var}, err := writer.CreateFormFile("{_go_escape(key)}", filepath.Base("{safe_path}"))',
                        "\tif err != nil {",
                        "\t\tlog.Fatal(err)",
                        "\t}",
                        f"\t_, err = io.Copy({part_var}, {file_var})",
                        "\tif err != nil {",
                        "\t\tlog.Fatal(err)",
                        "\t}",
                    ]
                )
            else:
                lines.append(
                    f'\twriter.WriteField("{_go_escape(key)}", "{_go_escape(raw)}")'
                )
        if has_text:
            lines.append(
                f'\twriter.WriteField("data", "{_go_escape(text_body)}")'
            )
        if declared_err:
            lines.append("\terr = writer.Close()")
        else:
            lines.append("\terr := writer.Close()")
            declared_err = True
        lines.extend(
            [
                "\tif err != nil {",
                "\t\tlog.Fatal(err)",
                "\t}",
                "",
                f'\treq, err := http.NewRequest("{_go_escape(method)}", "{url}", payload)',
            ]
        )
    elif has_text:
        lines.append(f'\tpayload := strings.NewReader("{_go_escape(text_body)}")')
        lines.append(
            f'\treq, err := http.NewRequest("{_go_escape(method)}", "{url}", payload)'
        )
    else:
        lines.append(
            f'\treq, err := http.NewRequest("{_go_escape(method)}", "{url}", nil)'
        )

    lines.extend(["\tif err != nil {", "\t\tlog.Fatal(err)", "\t}"])

    if use_multipart:
        lines.append('\treq.Header.Set("Content-Type", writer.FormDataContentType())')
    elif has_text and content_type and _header_value(headers, "Content-Type") is None:
        lines.append(
            f'\treq.Header.Set("Content-Type", "{_go_escape(content_type)}")'
        )

    for key, value in _header_pairs(headers):
        key_l = str(key).lower()
        if use_multipart and key_l == "content-type":
            continue
        if auth and key_l == "authorization":
            continue
        if (
            not use_multipart
            and key_l == "content-type"
            and content_type
        ):
            lines.append(
                f'\treq.Header.Set("{_go_escape(key)}", "{_go_escape(content_type)}")'
            )
            continue
        lines.append(
            f'\treq.Header.Set("{_go_escape(key)}", "{_go_escape(value)}")'
        )

    if auth:
        lines.append(
            f'\treq.SetBasicAuth("{_go_escape(auth[0])}", "{_go_escape(auth[1])}")'
        )

    lines.extend(
        [
            "",
            "\tres, err := http.DefaultClient.Do(req)",
            "\tif err != nil {",
            "\t\tlog.Fatal(err)",
            "\t}",
            "\tdefer res.Body.Close()",
            "",
            "\tbody, err := io.ReadAll(res.Body)",
            "\tif err != nil {",
            "\t\tlog.Fatal(err)",
            "\t}",
            "\tfmt.Println(string(body))",
            "}",
        ]
    )
    return "\n".join(lines)

# core/generators/kotlin_gen.py
import json
import os
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


def _kt_escape(value):
    """escape_string cua project + '$' (Kotlin string template)."""
    return escape_string(_as_text(value)).replace("$", "\\$")


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
    """Chi dung dang ma file goc da dung: dict. Them list cap (k, v) neu parser tra list."""
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
    """Nhan dien dung quy uoc da co trong file goc: v.startswith('open(') + split quotes."""
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


def _serialize_text_body(data_body, content_type, is_json):
    """Giu chuoi. Neu data_body la dict/list thi serialize theo is_json hoac Content-Type."""
    if data_body is None or data_body is False:
        return "", content_type, False

    if isinstance(data_body, bytes):
        data_body = data_body.decode("utf-8")

    if isinstance(data_body, str):
        if is_json and (not content_type or "json" not in content_type.lower()):
            content_type = "application/json"
        elif not content_type:
            content_type = "text/plain"
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

    return _as_text(data_body), content_type or "text/plain", True


@register_generator("kotlin_okhttp")
def generate_kotlin_okhttp(data: dict) -> str:
    """Sinh ma Kotlin su dung okhttp3."""
    url = _as_text(data["url"])
    method = _as_text(data["method"]).upper() or "GET"
    headers = data["headers"] or {}
    data_body = data["data_body"]
    files_form = data["files_form"]
    auth = data["auth"]
    is_json = data["is_json"]

    form_items = _files_form_items(files_form)
    form_unparsed = bool(files_form) and form_items is None
    if form_items is None:
        form_items = []

    content_type = _header_value(headers, "Content-Type")
    text_body, content_type, has_text_body = _serialize_text_body(
        data_body, content_type, is_json
    )

    use_multipart = bool(form_items)
    has_body = use_multipart or has_text_body
    use_file_api = False
    if use_multipart:
        for _, raw in form_items:
            if _parse_open_path(raw) is not None:
                use_file_api = True
                break

    # GET/HEAD + body: OkHttp nem IllegalArgumentException neu method co body.
    okhttp_forbids_body = method in ("GET", "HEAD") and has_body

    imports = [
        "import java.io.IOException",
        "import okhttp3.OkHttpClient",
        "import okhttp3.Request",
    ]
    if auth:
        imports.append("import okhttp3.Credentials")
    if has_body and not okhttp_forbids_body:
        imports.append("import okhttp3.MediaType.Companion.toMediaType")
        imports.append("import okhttp3.RequestBody.Companion.toRequestBody")
        if use_multipart:
            imports.append("import okhttp3.MultipartBody")
            if use_file_api:
                imports.append("import java.io.File")
                imports.append("import okhttp3.RequestBody.Companion.asRequestBody")

    lines = imports + ["", "fun main() {", "    val client = OkHttpClient()", ""]

    if form_unparsed:
        lines.append("    // CANH BAO: files_form khong phai dict hoac list cap (name, value).")
        lines.append("")

    if has_body and not okhttp_forbids_body:
        if use_multipart:
            lines.append(
                "    val body = MultipartBody.Builder().setType(MultipartBody.FORM)"
            )
            for key, raw in form_items:
                safe_key = _kt_escape(key)
                file_path = _parse_open_path(raw)
                if file_path is not None:
                    safe_path = _kt_escape(file_path)
                    filename = _kt_escape(os.path.basename(file_path) or file_path)
                    lines.append(
                        f'        .addFormDataPart("{safe_key}", "{filename}", '
                        f'File("{safe_path}").asRequestBody("application/octet-stream".toMediaType()))'
                    )
                else:
                    lines.append(
                        f'        .addFormDataPart("{safe_key}", "{_kt_escape(raw)}")'
                    )
            if has_text_body:
                lines.append(
                    f'        .addFormDataPart("data", "{_kt_escape(text_body)}")'
                )
            lines.append("        .build()")
        else:
            lines.append(f'    val mediaType = "{_kt_escape(content_type)}".toMediaType()')
            lines.append(
                f'    val body = "{_kt_escape(text_body)}".toRequestBody(mediaType)'
            )
        lines.append("")
    elif okhttp_forbids_body:
        lines.append(
            f"    // CANH BAO: curl co body nhung OkHttp cam body tren {method}."
        )
        lines.append("")

    lines.append("    val request = Request.Builder()")
    lines.append(f'        .url("{_kt_escape(url)}")')

    for key, value in _headers_items(headers):
        key_l = str(key).lower()
        if key_l == "content-type" and has_body and not okhttp_forbids_body:
            continue
        if key_l == "authorization" and auth:
            continue
        lines.append(f'        .header("{_kt_escape(key)}", "{_kt_escape(value)}")')

    if auth:
        user = _kt_escape(auth[0])
        password = _kt_escape(auth[1])
        lines.append(
            f'        .header("Authorization", Credentials.basic("{user}", "{password}"))'
        )

    if has_body and not okhttp_forbids_body:
        lines.append(f'        .method("{_kt_escape(method)}", body)')
    elif method == "GET":
        lines.append("        .get()")
    elif method == "HEAD":
        lines.append("        .head()")
    else:
        lines.append(f'        .method("{_kt_escape(method)}", null)')

    lines.extend(
        [
            "        .build()",
            "",
            "    client.newCall(request).execute().use { response ->",
            '        if (!response.isSuccessful) throw IOException("Unexpected code $response")',
            "        println(response.body?.string())",
            "    }",
            "}",
        ]
    )
    return "\n".join(lines)

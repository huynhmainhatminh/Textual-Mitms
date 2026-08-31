# core/generators/c_cpp_csharp_gen.py
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


def _esc(value):
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


@register_generator("csharp_httpclient")
def generate_csharp(data: dict) -> str:
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

    usings = [
        "using System;",
        "using System.Net.Http;",
        "using System.Net.Http.Headers;",
        "using System.Text;",
        "using System.Threading.Tasks;",
    ]
    if has_file:
        usings.append("using System.IO;")

    lines = usings + [
        "",
        "class Program {",
        "    static async Task Main(string[] args) {",
        "        using (var client = new HttpClient()) {",
    ]

    if auth:
        lines.append(
            f'            var authByteArray = Encoding.UTF8.GetBytes("{_esc(auth[0])}:{_esc(auth[1])}");'
        )
        lines.append(
            '            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Basic", Convert.ToBase64String(authByteArray));'
        )

    lines.append(
        f'            using (var request = new HttpRequestMessage(new HttpMethod("{_esc(method)}"), "{_esc(data["url"])}")) {{'
    )

    for key, value in _header_pairs(headers):
        key_l = str(key).lower()
        if key_l == "content-type":
            continue
        if auth and key_l == "authorization":
            continue
        lines.append(
            f'                request.Headers.TryAddWithoutValidation("{_esc(key)}", "{_esc(value)}");'
        )

    if use_multipart:
        lines.append("                var content = new MultipartFormDataContent();")
        for key, raw in form_items:
            path = _parse_open_path(raw)
            if path is not None:
                filename = os.path.basename(path) or path
                lines.append(
                    f'                content.Add(new StreamContent(File.OpenRead("{_esc(path)}")), "{_esc(key)}", "{_esc(filename)}");'
                )
            else:
                lines.append(
                    f'                content.Add(new StringContent("{_esc(raw)}"), "{_esc(key)}");'
                )
        if has_text:
            lines.append(
                f'                content.Add(new StringContent("{_esc(text_body)}"), "data");'
            )
        lines.append("                request.Content = content;")
    elif has_text:
        lines.append(f'                request.Content = new StringContent("{_esc(text_body)}");')
        if content_type:
            lines.append(
                f'                request.Content.Headers.ContentType = MediaTypeHeaderValue.Parse("{_esc(content_type)}");'
            )

    lines.extend(
        [
            "                var response = await client.SendAsync(request);",
            "                var responseBody = await response.Content.ReadAsStringAsync();",
            "                Console.WriteLine(responseBody);",
            "            }",
            "        }",
            "    }",
            "}",
        ]
    )
    return "\n".join(lines)


@register_generator("c_libcurl")
def generate_c(data: dict) -> str:
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

    lines = [
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "#include <string.h>",
        "#include <curl/curl.h>",
        "",
        "int main(void)",
        "{",
        "    CURL *curl;",
        "    CURLcode res;",
        "    struct curl_slist *headers = NULL;",
        "    curl_mime *form = NULL;",
        "",
        "    curl_global_init(CURL_GLOBAL_DEFAULT);",
        "    curl = curl_easy_init();",
        "    if(curl) {",
        f'        curl_easy_setopt(curl, CURLOPT_URL, "{_esc(data["url"])}");',
    ]

    if method == "POST" and (has_text or use_multipart):
        lines.append("        curl_easy_setopt(curl, CURLOPT_POST, 1L);")
    elif method != "GET":
        lines.append(
            f'        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "{_esc(method)}");'
        )

    header_pairs = []
    for key, value in _header_pairs(headers):
        key_l = str(key).lower()
        if use_multipart and key_l == "content-type":
            continue
        if auth and key_l == "authorization":
            continue
        if key_l == "content-type" and content_type and not use_multipart:
            header_pairs.append((key, content_type))
            continue
        header_pairs.append((key, value))
    if content_type and not use_multipart and _header_value(headers, "Content-Type") is None and has_text:
        header_pairs.append(("Content-Type", content_type))

    if header_pairs:
        lines.append("")
        for key, value in header_pairs:
            lines.append(
                f'        headers = curl_slist_append(headers, "{_esc(key)}: {_esc(value)}");'
            )
        lines.append("        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);")

    if auth:
        lines.append("")
        lines.append(
            f'        curl_easy_setopt(curl, CURLOPT_USERPWD, "{_esc(auth[0])}:{_esc(auth[1])}");'
        )

    if use_multipart:
        lines.extend(
            [
                "",
                "        form = curl_mime_init(curl);",
            ]
        )
        for key, raw in form_items:
            lines.append("        {")
            lines.append("            curl_mimepart *field = curl_mime_addpart(form);")
            lines.append(f'            curl_mime_name(field, "{_esc(key)}");')
            path = _parse_open_path(raw)
            if path is not None:
                lines.append(f'            curl_mime_filedata(field, "{_esc(path)}");')
            else:
                lines.append(
                    f'            curl_mime_data(field, "{_esc(raw)}", CURL_ZERO_TERMINATED);'
                )
            lines.append("        }")
        if has_text:
            lines.append("        {")
            lines.append("            curl_mimepart *field = curl_mime_addpart(form);")
            lines.append('            curl_mime_name(field, "data");')
            lines.append(
                f'            curl_mime_data(field, "{_esc(text_body)}", CURL_ZERO_TERMINATED);'
            )
            lines.append("        }")
        lines.append("        curl_easy_setopt(curl, CURLOPT_MIMEPOST, form);")
    elif has_text:
        lines.append("")
        lines.append(
            f'        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, "{_esc(text_body)}");'
        )
        if method == "GET":
            lines.append('        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "GET");')

    lines.extend(
        [
            "",
            "        res = curl_easy_perform(curl);",
            "        if(res != CURLE_OK) {",
            '            fprintf(stderr, "curl_easy_perform() failed: %s\\n", curl_easy_strerror(res));',
            "        }",
            "",
            "        curl_easy_cleanup(curl);",
            "        if(form) {",
            "            curl_mime_free(form);",
            "        }",
            "        if(headers) {",
            "            curl_slist_free_all(headers);",
            "        }",
            "    }",
            "    curl_global_cleanup();",
            "    return 0;",
            "}",
        ]
    )
    return "\n".join(lines)

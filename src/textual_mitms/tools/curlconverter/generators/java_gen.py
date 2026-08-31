# core/generators/java_gen.py
import json
import os
import re
from urllib.parse import urlencode

from . import register_generator
from .utils import escape_string


_OPEN_FILE_RE = re.compile(r"""^open\(\s*(['"])(.*)\1\s*\)$""")
_JSOUP_METHODS = {
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "PATCH",
    "HEAD",
    "OPTIONS",
    "TRACE",
}
_MULTIPART_BOUNDARY = "JavaFormBoundary7MA4YWxkTrZu0gW"


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _j_escape(value):
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


def _serialize_text_body(data_body, content_type, is_json):
    if data_body is None or data_body is False:
        return "", content_type, False
    if isinstance(data_body, bytes):
        data_body = data_body.decode("utf-8")
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


def _collect(data):
    headers = data["headers"] or {}
    content_type = _header_value(headers, "Content-Type")
    is_json = data["is_json"] if "is_json" in data else False
    text_body, content_type, has_text = _serialize_text_body(
        data["data_body"], content_type, is_json
    )
    form_items = _files_form_items(data["files_form"])
    form_unparsed = bool(data["files_form"]) and form_items is None
    if form_items is None:
        form_items = []
    method = _as_text(data["method"]).upper() or "GET"
    return {
        "url": _as_text(data["url"]),
        "method": method,
        "headers": headers,
        "auth": data["auth"],
        "form_items": form_items,
        "form_unparsed": form_unparsed,
        "text_body": text_body,
        "has_text": has_text,
        "content_type": content_type,
        "use_multipart": bool(form_items),
        "has_body": bool(form_items) or has_text,
        "forbid_body": method in ("GET", "HEAD") and (bool(form_items) or has_text),
    }


def _auth_java_lines(indent, auth, header_call):
    user_pass = _j_escape(auth[0]) + ":" + _j_escape(auth[1])
    return [
        f'{indent}String auth = "{user_pass}";',
        f"{indent}String encodedAuth = Base64.getEncoder().encodeToString(auth.getBytes(java.nio.charset.StandardCharsets.UTF_8));",
        f'{indent}{header_call}("Authorization", "Basic " + encodedAuth);',
    ]


def _emit_headers(lines, info, indent, setter, skip_ct, skip_auth):
    for key, value in _headers_items(info["headers"]):
        key_l = str(key).lower()
        if skip_ct and key_l == "content-type":
            continue
        if skip_auth and key_l == "authorization":
            continue
        if key_l == "content-type" and info["content_type"] and not info["use_multipart"]:
            lines.append(
                f'{indent}{setter}("{_j_escape(key)}", "{_j_escape(info["content_type"])}");'
            )
            continue
        lines.append(
            f'{indent}{setter}("{_j_escape(key)}", "{_j_escape(value)}");'
        )
    if (
        info["content_type"]
        and not info["use_multipart"]
        and not skip_ct
        and _header_value(info["headers"], "Content-Type") is None
        and info["has_text"]
        and not info["forbid_body"]
    ):
        lines.append(
            f'{indent}{setter}("Content-Type", "{_j_escape(info["content_type"])}");'
        )


def _multipart_java_string_builder(info):
    """Sinh code Java ghep multipart (HttpClient / HttpURLConnection khong co helper)."""
    lines = [
        f'            String boundary = "{_MULTIPART_BOUNDARY}";',
        "            StringBuilder bodyBuilder = new StringBuilder();",
    ]
    for key, raw in info["form_items"]:
        path = _parse_open_path(raw)
        lines.append('            bodyBuilder.append("--").append(boundary).append("\\r\\n");')
        if path is not None:
            filename = os.path.basename(path) or path
            lines.append(
                f'            bodyBuilder.append("Content-Disposition: form-data; name=\\"{_j_escape(key)}\\"; filename=\\"{_j_escape(filename)}\\"\\r\\n");'
            )
            lines.append(
                '            bodyBuilder.append("Content-Type: application/octet-stream\\r\\n\\r\\n");'
            )
            lines.append(
                f'            bodyBuilder.append(java.nio.file.Files.readString(java.nio.file.Path.of("{_j_escape(path)}")));'
            )
            lines.append('            bodyBuilder.append("\\r\\n");')
        else:
            lines.append(
                f'            bodyBuilder.append("Content-Disposition: form-data; name=\\"{_j_escape(key)}\\"\\r\\n\\r\\n");'
            )
            lines.append(f'            bodyBuilder.append("{_j_escape(raw)}");')
            lines.append('            bodyBuilder.append("\\r\\n");')
    if info["has_text"]:
        lines.append('            bodyBuilder.append("--").append(boundary).append("\\r\\n");')
        lines.append(
            '            bodyBuilder.append("Content-Disposition: form-data; name=\\"data\\"\\r\\n\\r\\n");'
        )
        lines.append(f'            bodyBuilder.append("{_j_escape(info["text_body"])}");')
        lines.append('            bodyBuilder.append("\\r\\n");')
    lines.append('            bodyBuilder.append("--").append(boundary).append("--\\r\\n");')
    lines.append("            String body = bodyBuilder.toString();")
    return lines


@register_generator("java_httpclient")
def generate_java_httpclient(data: dict) -> str:
    info = _collect(data)
    imports = [
        "import java.io.IOException;",
        "import java.net.URI;",
        "import java.net.http.HttpClient;",
        "import java.net.http.HttpRequest;",
        "import java.net.http.HttpResponse;",
    ]
    if info["auth"]:
        imports.append("import java.util.Base64;")
    lines = imports + [
        "",
        "public class Main {",
        "    public static void main(String[] args) {",
        "        try {",
        "            HttpClient client = HttpClient.newHttpClient();",
        "            HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()",
        f'                .uri(URI.create("{_j_escape(info["url"])}"));',
    ]
    if info["form_unparsed"]:
        lines.append("            // CANH BAO: files_form khong phai dict hoac list cap (name, value).")

    skip_ct = info["use_multipart"] and not info["forbid_body"]
    _emit_headers(
        lines,
        info,
        "            ",
        "requestBuilder.header",
        skip_ct,
        bool(info["auth"]),
    )
    if info["use_multipart"] and not info["forbid_body"]:
        lines.append(
            f'            requestBuilder.header("Content-Type", "multipart/form-data; boundary={_MULTIPART_BOUNDARY}");'
        )
    if info["auth"]:
        lines.extend(
            _auth_java_lines("            ", info["auth"], "requestBuilder.header")
        )

    if info["forbid_body"]:
        lines.append(f"            // CANH BAO: HttpClient cam body tren {info['method']}.")
        if info["method"] == "GET":
            lines.append("            requestBuilder.GET();")
        else:
            lines.append("            requestBuilder.HEAD();")
    elif info["use_multipart"]:
        lines.extend(_multipart_java_string_builder(info))
        lines.append(
            f'            requestBuilder.method("{_j_escape(info["method"])}", HttpRequest.BodyPublishers.ofString(body));'
        )
    elif info["has_text"]:
        lines.append(
            f'            requestBuilder.method("{_j_escape(info["method"])}", HttpRequest.BodyPublishers.ofString("{_j_escape(info["text_body"])}"));'
        )
    elif info["method"] == "GET":
        lines.append("            requestBuilder.GET();")
    else:
        lines.append(
            f'            requestBuilder.method("{_j_escape(info["method"])}", HttpRequest.BodyPublishers.noBody());'
        )

    lines.extend(
        [
            "            HttpRequest request = requestBuilder.build();",
            "            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());",
            "            System.out.println(response.body());",
            "        } catch (IOException | InterruptedException e) {",
            "            e.printStackTrace();",
            "        }",
            "    }",
            "}",
        ]
    )
    return "\n".join(lines)


@register_generator("java_httpurlconnection")
def generate_java_httpurlconnection(data: dict) -> str:
    info = _collect(data)
    imports = [
        "import java.io.IOException;",
        "import java.io.InputStream;",
        "import java.net.HttpURLConnection;",
        "import java.net.URL;",
        "import java.nio.charset.StandardCharsets;",
        "import java.util.Scanner;",
    ]
    if info["auth"]:
        imports.append("import java.util.Base64;")
    if info["has_body"] and not info["forbid_body"]:
        imports.append("import java.io.OutputStream;")
    lines = imports + [
        "",
        "class Main {",
        "    public static void main(String[] args) throws IOException {",
        f'        URL url = new URL("{_j_escape(info["url"])}");',
        "        HttpURLConnection httpConn = (HttpURLConnection) url.openConnection();",
        f'        httpConn.setRequestMethod("{_j_escape(info["method"])}");',
    ]
    if info["form_unparsed"]:
        lines.append("        // CANH BAO: files_form khong phai dict hoac list cap (name, value).")

    skip_ct = info["use_multipart"] and not info["forbid_body"]
    _emit_headers(
        lines,
        info,
        "        ",
        "httpConn.setRequestProperty",
        skip_ct,
        bool(info["auth"]),
    )
    if info["use_multipart"] and not info["forbid_body"]:
        lines.append(
            f'        httpConn.setRequestProperty("Content-Type", "multipart/form-data; boundary={_MULTIPART_BOUNDARY}");'
        )
    if info["auth"]:
        lines.extend(
            _auth_java_lines("        ", info["auth"], "httpConn.setRequestProperty")
        )

    if info["has_body"] and not info["forbid_body"]:
        if info["use_multipart"]:
            # Tai su dung builder nhung indent 8 spaces -> thay the block rieng ngan.
            lines.append(f'        String boundary = "{_MULTIPART_BOUNDARY}";')
            lines.append("        StringBuilder bodyBuilder = new StringBuilder();")
            for key, raw in info["form_items"]:
                path = _parse_open_path(raw)
                lines.append(
                    '        bodyBuilder.append("--").append(boundary).append("\\r\\n");'
                )
                if path is not None:
                    filename = os.path.basename(path) or path
                    lines.append(
                        f'        bodyBuilder.append("Content-Disposition: form-data; name=\\"{_j_escape(key)}\\"; filename=\\"{_j_escape(filename)}\\"\\r\\n");'
                    )
                    lines.append(
                        '        bodyBuilder.append("Content-Type: application/octet-stream\\r\\n\\r\\n");'
                    )
                    lines.append(
                        f'        bodyBuilder.append(java.nio.file.Files.readString(java.nio.file.Path.of("{_j_escape(path)}")));'
                    )
                    lines.append('        bodyBuilder.append("\\r\\n");')
                else:
                    lines.append(
                        f'        bodyBuilder.append("Content-Disposition: form-data; name=\\"{_j_escape(key)}\\"\\r\\n\\r\\n");'
                    )
                    lines.append(f'        bodyBuilder.append("{_j_escape(raw)}");')
                    lines.append('        bodyBuilder.append("\\r\\n");')
            if info["has_text"]:
                lines.append(
                    '        bodyBuilder.append("--").append(boundary).append("\\r\\n");'
                )
                lines.append(
                    '        bodyBuilder.append("Content-Disposition: form-data; name=\\"data\\"\\r\\n\\r\\n");'
                )
                lines.append(
                    f'        bodyBuilder.append("{_j_escape(info["text_body"])}");'
                )
                lines.append('        bodyBuilder.append("\\r\\n");')
            lines.append(
                '        bodyBuilder.append("--").append(boundary).append("--\\r\\n");'
            )
            lines.append("        byte[] out = bodyBuilder.toString().getBytes(StandardCharsets.UTF_8);")
        else:
            lines.append(
                f'        byte[] out = "{_j_escape(info["text_body"])}".getBytes(StandardCharsets.UTF_8);'
            )
        lines.extend(
            [
                "        httpConn.setDoOutput(true);",
                "        try (OutputStream os = httpConn.getOutputStream()) {",
                "            os.write(out);",
                "        }",
            ]
        )
    elif info["forbid_body"]:
        lines.append(f"        // CANH BAO: {info['method']} kem body; HttpURLConnection van mo method goc, khong ghi output.")

    lines.extend(
        [
            "",
            "        InputStream responseStream = httpConn.getResponseCode() / 100 == 2",
            "                ? httpConn.getInputStream()",
            "                : httpConn.getErrorStream();",
            "        String response = \"\";",
            "        if (responseStream != null) {",
            "            try (Scanner s = new Scanner(responseStream, StandardCharsets.UTF_8.name()).useDelimiter(\"\\\\A\")) {",
            "                response = s.hasNext() ? s.next() : \"\";",
            "            }",
            "        }",
            "        System.out.println(response);",
            "    }",
            "}",
        ]
    )
    return "\n".join(lines)


@register_generator("java_jsoup")
def generate_java_jsoup(data: dict) -> str:
    info = _collect(data)
    imports = [
        "import java.io.IOException;",
        "import org.jsoup.Connection;",
        "import org.jsoup.Jsoup;",
    ]
    if info["auth"]:
        imports.append("import java.util.Base64;")
    need_file = any(_parse_open_path(raw) for _, raw in info["form_items"])
    if need_file:
        imports.extend(
            [
                "import java.io.File;",
                "import java.io.FileInputStream;",
            ]
        )
    lines = imports + [
        "",
        "class Main {",
        "    public static void main(String[] args) throws IOException {",
        f'        Connection connection = Jsoup.connect("{_j_escape(info["url"])}")',
        "                .ignoreContentType(true);",
    ]
    if info["form_unparsed"]:
        lines.append("        // CANH BAO: files_form khong phai dict hoac list cap (name, value).")

    if info["method"] != "GET":
        if info["method"] in _JSOUP_METHODS:
            lines.append(
                f"        connection.method(Connection.Method.{info['method']});"
            )
        else:
            lines.append(
                f"        // CANH BAO: Jsoup Connection.Method khong co {info['method']}."
            )

    skip_ct = info["use_multipart"]
    _emit_headers(
        lines,
        info,
        "        ",
        "connection.header",
        skip_ct,
        bool(info["auth"]),
    )
    if info["auth"]:
        lines.extend(_auth_java_lines("        ", info["auth"], "connection.header"))

    if info["use_multipart"]:
        for key, raw in info["form_items"]:
            path = _parse_open_path(raw)
            if path is not None:
                filename = os.path.basename(path) or path
                lines.append(
                    f'        connection.data("{_j_escape(key)}", "{_j_escape(filename)}", new FileInputStream(new File("{_j_escape(path)}")));'
                )
            else:
                lines.append(
                    f'        connection.data("{_j_escape(key)}", "{_j_escape(raw)}");'
                )
        if info["has_text"]:
            lines.append(
                f'        connection.data("data", "{_j_escape(info["text_body"])}");'
            )
    elif info["has_text"]:
        lines.append(
            f'        connection.requestBody("{_j_escape(info["text_body"])}");'
        )

    lines.extend(
        [
            "",
            "        Connection.Response response = connection.execute();",
            "        System.out.println(response.body());",
            "    }",
            "}",
        ]
    )
    return "\n".join(lines)


@register_generator("java_okhttp")
def generate_java_okhttp(data: dict) -> str:
    info = _collect(data)
    imports = [
        "import java.io.IOException;",
        "import okhttp3.OkHttpClient;",
        "import okhttp3.Request;",
        "import okhttp3.Response;",
    ]
    if info["auth"]:
        imports.append("import okhttp3.Credentials;")
    emit_body = info["has_body"] and not info["forbid_body"]
    if emit_body:
        imports.append("import okhttp3.MediaType;")
        imports.append("import okhttp3.RequestBody;")
        if info["use_multipart"]:
            imports.append("import okhttp3.MultipartBody;")
            if any(_parse_open_path(raw) for _, raw in info["form_items"]):
                imports.append("import java.io.File;")
    lines = imports + [
        "",
        "public class Main {",
        "    public static void main(String[] args) {",
        "        OkHttpClient client = new OkHttpClient();",
        "",
    ]
    if info["form_unparsed"]:
        lines.append("        // CANH BAO: files_form khong phai dict hoac list cap (name, value).")

    if emit_body and info["use_multipart"]:
        lines.append(
            "        MultipartBody.Builder bodyBuilder = new MultipartBody.Builder().setType(MultipartBody.FORM);"
        )
        for key, raw in info["form_items"]:
            path = _parse_open_path(raw)
            if path is not None:
                filename = os.path.basename(path) or path
                lines.append(
                    f'        bodyBuilder.addFormDataPart("{_j_escape(key)}", "{_j_escape(filename)}",'
                )
                lines.append(
                    f'            RequestBody.create(new File("{_j_escape(path)}"), MediaType.parse("application/octet-stream")));'
                )
            else:
                lines.append(
                    f'        bodyBuilder.addFormDataPart("{_j_escape(key)}", "{_j_escape(raw)}");'
                )
        if info["has_text"]:
            lines.append(
                f'        bodyBuilder.addFormDataPart("data", "{_j_escape(info["text_body"])}");'
            )
        lines.append("        RequestBody body = bodyBuilder.build();")
    elif emit_body:
        ct = info["content_type"] or "text/plain"
        lines.append(f'        MediaType mediaType = MediaType.parse("{_j_escape(ct)}");')
        lines.append(
            f'        RequestBody body = RequestBody.create("{_j_escape(info["text_body"])}", mediaType);'
        )
    elif info["forbid_body"]:
        lines.append(f"        // CANH BAO: OkHttp cam body tren {info['method']}.")

    lines.append("")
    lines.append("        Request.Builder requestBuilder = new Request.Builder()")
    lines.append(f'            .url("{_j_escape(info["url"])}");')

    _emit_headers(
        lines,
        info,
        "        ",
        "requestBuilder.addHeader",
        emit_body,
        bool(info["auth"]),
    )
    if info["auth"]:
        lines.append(
            f'        String credential = Credentials.basic("{_j_escape(info["auth"][0])}", "{_j_escape(info["auth"][1])}");'
        )
        lines.append('        requestBuilder.addHeader("Authorization", credential);')

    if emit_body:
        lines.append(
            f'        requestBuilder.method("{_j_escape(info["method"])}", body);'
        )
    elif info["method"] == "GET":
        lines.append("        requestBuilder.get();")
    elif info["method"] == "HEAD":
        lines.append("        requestBuilder.head();")
    else:
        lines.append(
            f'        requestBuilder.method("{_j_escape(info["method"])}", null);'
        )

    lines.extend(
        [
            "",
            "        Request request = requestBuilder.build();",
            "",
            "        try (Response response = client.newCall(request).execute()) {",
            '            if (!response.isSuccessful()) throw new IOException("Unexpected code " + response);',
            "            System.out.println(response.body().string());",
            "        } catch (IOException e) {",
            "            e.printStackTrace();",
            "        }",
            "    }",
            "}",
        ]
    )
    return "\n".join(lines)

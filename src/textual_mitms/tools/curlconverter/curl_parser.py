# curlconverter/curl_parser.py
import shlex


def parse_curl_command(curl_cmd: str) -> dict:
    """Đọc lệnh cURL và trả về một dictionary chứa các thông tin đã bóc tách."""
    curl_cmd = curl_cmd.replace("\\\n", " ").replace("\\\r\n", " ")

    try:
        tokens = shlex.split(curl_cmd)
    except Exception as e:
        return {"error": f"// Lỗi phân tích cú pháp cURL: {e}"}

    if not tokens or not tokens[0].lower().endswith("curl"):
        return {"error": "// Lệnh không hợp lệ. Vui lòng bắt đầu bằng chữ 'curl'."}

    method = "GET"
    url = ""
    headers = {}
    data_body = None
    is_json = False
    auth = None
    files_form = {}

    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in ("-X", "--request") and i + 1 < len(tokens):
            method = tokens[i + 1].upper()
            i += 2
        elif token in ("-H", "--header") and i + 1 < len(tokens):
            header_str = tokens[i + 1]
            if ":" in header_str:
                key, value = header_str.split(":", 1)
                headers[key.strip()] = value.strip()
                if key.strip().lower() == "content-type" and "application/json" in value.lower():
                    is_json = True
            i += 2
        elif token in ("-d", "--data", "--data-raw", "--data-binary") and i + 1 < len(tokens):
            data_body = tokens[i + 1]
            if method == "GET": method = "POST"
            i += 2
        elif token in ("-u", "--user") and i + 1 < len(tokens):
            auth_str = tokens[i + 1]
            if ":" in auth_str:
                u, p = auth_str.split(":", 1)
                auth = (u, p)
            else:
                auth = (auth_str, "")
            i += 2
        elif token in ("-F", "--form") and i + 1 < len(tokens):
            form_str = tokens[i + 1]
            if "=" in form_str:
                key, value = form_str.split("=", 1)
                if value.startswith("@"):
                    files_form[key] = f"open('{value[1:]}', 'rb')"
                else:
                    files_form[key] = f"'{value}'"
            if method == "GET": method = "POST"
            i += 2
        elif not token.startswith("-") and not url:
            url = token
            i += 1
        else:
            i += 1

    return {
        "error": None,
        "method": method,
        "url": url,
        "headers": headers,
        "data_body": data_body,
        "is_json": is_json,
        "auth": auth,
        "files_form": files_form
    }

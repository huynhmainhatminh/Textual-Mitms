# core/utils.py
import json


def parse_headers_to_list(headers_str: str) -> list[tuple[str, str]]:
    """Tách chuỗi Header thành các cặp Key - Value."""
    headers_list = []
    if not headers_str: return headers_list
    for line in headers_str.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            headers_list.append((k.strip(), v.strip()))
        elif line.strip():
            headers_list.append((line.strip(), ""))
    return headers_list


def format_secure_json(text: str) -> str:
    """Định dạng JSON và loại bỏ tiền tố Anti-Hijacking an toàn."""
    if not text: return ""
    clean_text = text.strip()
    prefix = ""
    if clean_text.startswith(")]}'"):
        prefix = ")]}'\n"
        clean_text = clean_text[4:].strip()
    elif clean_text.startswith("for (;;);"):
        prefix = "for (;;);\n"
        clean_text = clean_text[9:].strip()

    try:
        parsed = json.loads(clean_text)
        return prefix + json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return text


def build_curl_command(method: str, url: str, headers_str: str, body_str: str) -> str:
    """Tái tạo câu lệnh cURL từ request gốc."""
    curl_cmd = f"curl -X {method} '{url}'"
    for key, val in parse_headers_to_list(headers_str):
        if not key.startswith(":"):
            safe_val = val.replace("'", "'\\''")
            curl_cmd += f" \\\n  -H '{key}: {safe_val}'"

    if body_str and method in ["POST", "PUT", "PATCH", "DELETE"]:
        safe_body = body_str.replace("'", "'\\''")
        curl_cmd += f" \\\n  --data-raw '{safe_body}'"

    return curl_cmd


def build_row_string(record: dict) -> str:
    """Ghép các dữ liệu thành dòng phân cách bằng Tab cho Excel."""
    row_values = [
        str(record.get("id", "")),
        str(record.get("host", "")),
        str(record.get("method", "")),
        str(record.get("url", "")),
        str(record.get("status", "")),
        str(record.get("length", "")),
        str(record.get("ip", "")),
        str(record.get("cookies", ""))
    ]
    return "\t".join(row_values)
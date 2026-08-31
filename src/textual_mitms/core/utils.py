# core/utils.py
from . import *


def normalize_host_rule(rule: str) -> str:
    """Chuẩn hóa rule người dùng nhập thành hostname literal.

    PromptModal lưu domain kiểu example.com.
    Bỏ tiền tố '*.' hoặc '.' nếu có, không diễn giải như regex.
    """
    host = (rule or "").strip().lower()
    if host.startswith("*."):
        host = host[2:]
    elif host.startswith("."):
        host = host[1:]
    return host.rstrip(".")


def host_rule_to_mitm_regex(rule: str) -> str | None:
    """Sinh regex cho options allow_hosts / ignore_hosts của mitmproxy.

    Docs options: giá trị là regular expression, matched on the ip or the hostname.
    Source NextLayer._ignore_connection (mitmproxy/addons/next_layer.py):
        re.search(rex, host, re.IGNORECASE)
    và `host` thường có dạng hostname:port
        hostnames.append(f"{host}:{port}")

    Pattern neo domain + subdomain, không dùng .*host.* (over-match
    myexample.com và example.com.evil.com).
    """
    host = normalize_host_rule(rule)
    if not host:
        return None
    escaped = re.escape(host)
    return rf"(^|\.){escaped}(:\d+)?$"


def hosts_to_mitm_regex_list(hosts_set: set) -> list[str]:
    patterns: list[str] = []
    for item in hosts_set:
        pattern = host_rule_to_mitm_regex(item)
        if pattern:
            patterns.append(pattern)
    return patterns


def unique_normalized_hosts(hosts) -> set[str]:
    """Gom list về hostname đã normalize; bỏ chuỗi rỗng, gộp *.x / .x / x."""
    out: set[str] = set()
    for item in hosts or ():
        key = normalize_host_rule(item)
        if key:
            out.add(key)
    return out


def subtract_same_host_rules(keep: set, drop_from: set) -> tuple[set[str], list[str]]:
    """Gỡ khỏi drop_from những rule trùng normalize với keep.

    Không đụng subdomain khác độ cụ thể:
    keep={google.com} không gỡ ads.google.com.
    """
    keep_keys = unique_normalized_hosts(keep)
    kept: set[str] = set()
    removed: list[str] = []
    for item in drop_from:
        key = normalize_host_rule(item)
        if key and key in keep_keys:
            removed.append(item)
        elif key:
            kept.add(key)
        elif item:
            kept.add(item)
    return kept, removed


def host_matches_rule(target_host: str, rule: str) -> bool:
    """So host (pretty_host / IP, không bắt buộc có port) với một rule.

    Cùng ngữ nghĩa với regex mitmproxy ở trên:
    khớp đúng host hoặc subdomain, không khớp chuỗi chứa một phần.
    """
    host = (target_host or "").strip().lower()
    if not host:
        return False
    if host.count(":") == 1:
        maybe_host, maybe_port = host.rsplit(":", 1)
        if maybe_port.isdigit():
            host = maybe_host
    rule_n = normalize_host_rule(rule)
    if not rule_n:
        return False
    return host == rule_n or host.endswith("." + rule_n)


def host_matches_any(target_host: str, rules: set) -> bool:
    return any(host_matches_rule(target_host, rule) for rule in rules)


def parse_headers_to_list(headers_str: str) -> list[tuple[str, str]]:
    """Tách chuỗi Header thành các cặp Key - Value."""
    headers_list = []
    if not headers_str:
        return headers_list
    for line in headers_str.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            headers_list.append((k.strip(), v.strip()))
        elif line.strip():
            headers_list.append((line.strip(), ""))
    return headers_list


def format_secure_json(text: str) -> str:
    """Định dạng JSON và loại bỏ tiền tố Anti-Hijacking an toàn."""
    if not text:
        return ""
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

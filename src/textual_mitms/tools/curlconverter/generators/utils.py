# core/generators/utils.py

def escape_string(text: str) -> str:
    """Escape an toàn cho các chuỗi code (để tránh lỗi cú pháp dấu nháy)."""
    if not text:
        return ""
    return str(text).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

# core/system_proxy.py
"""
Bật/tắt proxy hệ thống khi Start/Stop DumpMaster.

Nguồn lệnh / khóa — không bịa:

macOS  man networksetup(8):
  networksetup -listallnetworkservices
      Dòng đầu là chú thích; service bị tắt có tiền tố "* ".
  networksetup -getwebproxy <service>
  networksetup -getsecurewebproxy <service>
      Output:
        Enabled: Yes|No
        Server: ...
        Port: ...
        Authenticated Proxy Enabled: 0|1
  networksetup -setwebproxy <service> <domain> <portnumber>
      "Turns proxy on."
  networksetup -setsecurewebproxy <service> <domain> <portnumber>
  networksetup -setwebproxystate <service> on|off
  networksetup -setsecurewebproxystate <service> on|off
  Binary: /usr/sbin/networksetup

Windows
  HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings
      ProxyEnable  REG_DWORD  (Microsoft: 0 = direct, khác 0 = dùng ProxyServer)
      ProxyServer  REG_SZ     host:port
      ProxyOverride REG_SZ    danh sách tách bởi ';' ; token <local>
  wininet.h / Microsoft Learn Option Flags:
      INTERNET_OPTION_REFRESH           = 37
      INTERNET_OPTION_SETTINGS_CHANGED  = 39
  InternetSetOption(NULL, option, NULL, 0) sau khi ghi registry
  để Chrome/Edge/WinINet đọc lại.

GNOME  org.gnome.system.proxy.gschema.xml:
      org.gnome.system.proxy          mode          enum none|manual|auto
      org.gnome.system.proxy          ignore-hosts  as
      org.gnome.system.proxy.http     host s  port i
      org.gnome.system.proxy.https    host s  port i
  gsettings get|set <schema> <key> <value>

KDE  kioslaverc [Proxy Settings] (KIO / Chromium parser):
      ProxyType  0=none 1=manual 2=PAC 3=WPAD 4=env
      httpProxy / httpsProxy   "http://host:port"
  kwriteconfig5|kwriteconfig6 --file kioslaverc --group "Proxy Settings" --key ...
  dbus-send --type=signal /KIO/Scheduler \\
      org.kde.KIO.Scheduler.reparseSlaveConfiguration string:''

Không sửa /etc/environment hay apt.conf (đòi root, ảnh hưởng cả máy).
0.0.0.0 / :: / *  → client proxy host = 127.0.0.1
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from mitmproxy.options import CONF_DIR


SNAPSHOT_NAME = "textual-mitms-os-proxy-snapshot.json"


@dataclass
class ProxyOpResult:
    ok: bool
    message: str
    applied: bool = False
    restored: bool = False
    details: list[str] = field(default_factory=list)


def snapshot_path() -> Path:
    return Path(os.path.expanduser(CONF_DIR)) / SNAPSHOT_NAME


def client_proxy_host(listen_host: str) -> str:
    h = (listen_host or "").strip()
    if h in {"", "0.0.0.0", "::", "*", "[::]"}:
        return "127.0.0.1"
    if h.startswith("[") and h.endswith("]"):
        return h[1:-1]
    return h


def _run(argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, "", f"not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _load_snapshot() -> dict | None:
    path = snapshot_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_snapshot(data: dict) -> None:
    path = snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _clear_snapshot() -> None:
    path = snapshot_path()
    if path.is_file():
        path.unlink()


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

_NETWORKSETUP = "/usr/sbin/networksetup"


def _macos_services() -> list[str]:
    code, out, _err = _run([_NETWORKSETUP, "-listallnetworkservices"])
    if code != 0:
        return []
    names: list[str] = []
    for i, raw in enumerate(out.splitlines()):
        line = raw.strip()
        if not line:
            continue
        if i == 0 and line.startswith("An asterisk"):
            continue
        if line.startswith("*"):
            continue
        names.append(line)
    return names


def _macos_parse_get(text: str) -> dict:
    enabled = False
    server = ""
    port = 0
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "enabled":
            enabled = value.lower() == "yes"
        elif key == "server":
            server = value
        elif key == "port":
            try:
                port = int(value)
            except ValueError:
                port = 0
    return {"enabled": enabled, "server": server, "port": port}


def _macos_get(flag: str, service: str) -> dict:
    _code, out, _err = _run([_NETWORKSETUP, flag, service])
    return _macos_parse_get(out)


def _macos_snapshot() -> dict:
    services = []
    for name in _macos_services():
        services.append({
            "name": name,
            "http": _macos_get("-getwebproxy", name),
            "https": _macos_get("-getsecurewebproxy", name),
        })
    return {"os": "darwin", "services": services}


def _macos_apply(host: str, port: int) -> ProxyOpResult:
    services = _macos_services()
    if not services:
        return ProxyOpResult(ok=False, message="networksetup -listallnetworkservices không trả về service.")
    details = []
    ok_all = True
    for name in services:
        for set_flag in ("-setwebproxy", "-setsecurewebproxy"):
            code, _out, err = _run([_NETWORKSETUP, set_flag, name, host, str(port)])
            if code != 0:
                ok_all = False
                details.append(f"{set_flag} {name}: {err.strip() or code}")
            else:
                details.append(f"{set_flag} {name} -> {host}:{port}")
    return ProxyOpResult(
        ok=ok_all,
        message="Đã set Web + Secure Web proxy trên mọi service đang bật." if ok_all
        else "Một số service set thất bại (thường cần quyền admin).",
        applied=ok_all,
        details=details,
    )


def _macos_restore_one(service: str, kind: str, data: dict) -> list[str]:
    set_flag = "-setwebproxy" if kind == "http" else "-setsecurewebproxy"
    state_flag = "-setwebproxystate" if kind == "http" else "-setsecurewebproxystate"
    notes = []
    server = data.get("server") or ""
    port = int(data.get("port") or 0)
    if server and port:
        code, _out, err = _run([_NETWORKSETUP, set_flag, service, server, str(port)])
        if code != 0:
            notes.append(f"{set_flag} {service}: {err.strip() or code}")
    state = "on" if data.get("enabled") else "off"
    code, _out, err = _run([_NETWORKSETUP, state_flag, service, state])
    if code != 0:
        notes.append(f"{state_flag} {service} {state}: {err.strip() or code}")
    else:
        notes.append(f"{service} {kind} -> {state}")
    return notes


def _macos_restore(snap: dict) -> ProxyOpResult:
    details: list[str] = []
    ok_all = True
    for svc in snap.get("services") or []:
        name = svc.get("name")
        if not name:
            continue
        details.extend(_macos_restore_one(name, "http", svc.get("http") or {}))
        details.extend(_macos_restore_one(name, "https", svc.get("https") or {}))
    if any(":" in line and not line.endswith("on") and not line.endswith("off") and "->" not in line for line in details):
        ok_all = False
    fail = [d for d in details if d.split(":")[-1].strip().isdigit() or "Error" in d]
    if fail:
        ok_all = False
    return ProxyOpResult(
        ok=ok_all,
        message="Đã restore proxy macOS." if ok_all else "Restore macOS chưa đủ (xem details).",
        restored=True,
        details=details,
    )


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

_WIN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
_INTERNET_OPTION_REFRESH = 37
_INTERNET_OPTION_SETTINGS_CHANGED = 39


def _win_notify() -> None:
    import ctypes
    inet = ctypes.windll.wininet
    inet.InternetSetOptionW(None, _INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
    inet.InternetSetOptionW(None, _INTERNET_OPTION_REFRESH, None, 0)


def _win_read() -> dict:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_KEY) as key:
        def _get(name, default=""):
            try:
                value, _typ = winreg.QueryValueEx(key, name)
                return value
            except FileNotFoundError:
                return default
        enable = int(_get("ProxyEnable", 0) or 0)
        return {
            "os": "win32",
            "ProxyEnable": enable,
            "ProxyServer": str(_get("ProxyServer", "") or ""),
            "ProxyOverride": str(_get("ProxyOverride", "") or ""),
        }


def _win_write(enable: int, server: str, override: str | None = None) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, int(enable))
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, server)
        if override is not None:
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, override)
    _win_notify()


def _win_apply(host: str, port: int) -> ProxyOpResult:
    server = f"{host}:{port}"
    current = _win_read()
    override = current.get("ProxyOverride") or "<local>"
    _win_write(1, server, override)
    return ProxyOpResult(
        ok=True,
        applied=True,
        message=f"HKCU ProxyEnable=1 ProxyServer={server}",
        details=[f"ProxyOverride giữ: {override}"],
    )


def _win_restore(snap: dict) -> ProxyOpResult:
    _win_write(
        int(snap.get("ProxyEnable") or 0),
        str(snap.get("ProxyServer") or ""),
        str(snap.get("ProxyOverride") or ""),
    )
    return ProxyOpResult(ok=True, restored=True, message="Đã restore HKCU Internet Settings.")


# ---------------------------------------------------------------------------
# GNOME
# ---------------------------------------------------------------------------

def _gsettings_available() -> bool:
    return shutil.which("gsettings") is not None


def _gs_get(schema: str, key: str) -> str:
    _code, out, _err = _run(["gsettings", "get", schema, key])
    return out.strip()


def _gs_set(schema: str, key: str, value: str) -> tuple[int, str]:
    code, _out, err = _run(["gsettings", "set", schema, key, value])
    return code, err.strip()


def _gnome_snapshot() -> dict:
    return {
        "os": "gnome",
        "mode": _gs_get("org.gnome.system.proxy", "mode"),
        "ignore-hosts": _gs_get("org.gnome.system.proxy", "ignore-hosts"),
        "http_host": _gs_get("org.gnome.system.proxy.http", "host"),
        "http_port": _gs_get("org.gnome.system.proxy.http", "port"),
        "https_host": _gs_get("org.gnome.system.proxy.https", "host"),
        "https_port": _gs_get("org.gnome.system.proxy.https", "port"),
    }


def _gnome_apply(host: str, port: int) -> ProxyOpResult:
    ops = [
        ("org.gnome.system.proxy.http", "host", f"'{host}'"),
        ("org.gnome.system.proxy.http", "port", str(port)),
        ("org.gnome.system.proxy.https", "host", f"'{host}'"),
        ("org.gnome.system.proxy.https", "port", str(port)),
        ("org.gnome.system.proxy", "mode", "'manual'"),
    ]
    details = []
    ok_all = True
    for schema, key, value in ops:
        code, err = _gs_set(schema, key, value)
        if code != 0:
            ok_all = False
            details.append(f"{schema} {key}: {err or code}")
        else:
            details.append(f"{schema} {key}={value}")
    return ProxyOpResult(
        ok=ok_all,
        applied=ok_all,
        message="Đã gsettings mode=manual http/https." if ok_all else "gsettings set thất bại.",
        details=details,
    )


def _gnome_restore(snap: dict) -> ProxyOpResult:
    details = []
    ok_all = True
    mapping = [
        ("org.gnome.system.proxy.http", "host", snap.get("http_host") or "''"),
        ("org.gnome.system.proxy.http", "port", str(snap.get("http_port") or "0")),
        ("org.gnome.system.proxy.https", "host", snap.get("https_host") or "''"),
        ("org.gnome.system.proxy.https", "port", str(snap.get("https_port") or "0")),
        ("org.gnome.system.proxy", "ignore-hosts", snap.get("ignore-hosts") or "['localhost', '127.0.0.0/8', '::1']"),
        ("org.gnome.system.proxy", "mode", snap.get("mode") or "'none'"),
    ]
    for schema, key, value in mapping:
        code, err = _gs_set(schema, key, value)
        if code != 0:
            ok_all = False
            details.append(f"{schema} {key}: {err or code}")
    return ProxyOpResult(
        ok=ok_all,
        restored=True,
        message="Đã restore gsettings proxy." if ok_all else "Restore gsettings lỗi.",
        details=details,
    )


# ---------------------------------------------------------------------------
# KDE
# ---------------------------------------------------------------------------

def _kde_tool() -> str | None:
    return shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")


def _kde_read_tool() -> str | None:
    return shutil.which("kreadconfig6") or shutil.which("kreadconfig5")


def _kde_rw(tool: str, key: str, value: str | None = None) -> str:
    base = [
        tool,
        "--file", "kioslaverc",
        "--group", "Proxy Settings",
        "--key", key,
    ]
    if value is None:
        _code, out, _err = _run(base)
        return out.strip()
    _run([*base, value])
    return ""


def _kde_reparse() -> None:
    _run([
        "dbus-send",
        "--type=signal",
        "/KIO/Scheduler",
        "org.kde.KIO.Scheduler.reparseSlaveConfiguration",
        "string:",
    ])


def _kde_snapshot() -> dict:
    reader = _kde_read_tool()
    if not reader:
        return {"os": "kde", "available": False}
    return {
        "os": "kde",
        "available": True,
        "ProxyType": _kde_rw(reader, "ProxyType"),
        "httpProxy": _kde_rw(reader, "httpProxy"),
        "httpsProxy": _kde_rw(reader, "httpsProxy"),
    }


def _kde_apply(host: str, port: int) -> ProxyOpResult:
    writer = _kde_tool()
    if not writer:
        return ProxyOpResult(ok=False, message="Không có kwriteconfig5/6.")
    url = f"http://{host}:{port}"
    _kde_rw(writer, "ProxyType", "1")
    _kde_rw(writer, "httpProxy", url)
    _kde_rw(writer, "httpsProxy", url)
    _kde_reparse()
    return ProxyOpResult(
        ok=True,
        applied=True,
        message=f"kioslaverc ProxyType=1 http(s)Proxy={url}",
    )


def _kde_restore(snap: dict) -> ProxyOpResult:
    writer = _kde_tool()
    if not writer:
        return ProxyOpResult(ok=False, message="Không có kwriteconfig5/6.")
    _kde_rw(writer, "ProxyType", snap.get("ProxyType") or "0")
    _kde_rw(writer, "httpProxy", snap.get("httpProxy") or "")
    _kde_rw(writer, "httpsProxy", snap.get("httpsProxy") or "")
    _kde_reparse()
    return ProxyOpResult(ok=True, restored=True, message="Đã restore kioslaverc.")


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def detect_backend() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform == "win32":
        return "win32"
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    if "kde" in desktop or "plasma" in desktop:
        if _kde_tool():
            return "kde"
    if _gsettings_available():
        return "gnome"
    if _kde_tool():
        return "kde"
    return "none"


def take_snapshot() -> dict:
    backend = detect_backend()
    if backend == "darwin":
        snap = _macos_snapshot()
    elif backend == "win32":
        snap = _win_read()
    elif backend == "gnome":
        snap = _gnome_snapshot()
    elif backend == "kde":
        snap = _kde_snapshot()
    else:
        snap = {"os": "none"}
    snap["backend"] = backend
    return snap


def apply_system_proxy(listen_host: str, listen_port: int) -> ProxyOpResult:
    backend = detect_backend()
    if backend == "none":
        return ProxyOpResult(
            ok=False,
            message="Không có backend OS (cần networksetup / HKCU WinINet / gsettings / kwriteconfig).",
        )
    host = client_proxy_host(listen_host)
    port = int(listen_port)
    if _load_snapshot() is None:
        _save_snapshot(take_snapshot())
    if backend == "darwin":
        return _macos_apply(host, port)
    if backend == "win32":
        return _win_apply(host, port)
    if backend == "gnome":
        return _gnome_apply(host, port)
    if backend == "kde":
        return _kde_apply(host, port)
    return ProxyOpResult(ok=False, message=f"backend lạ: {backend}")


def restore_system_proxy() -> ProxyOpResult:
    snap = _load_snapshot()
    if snap is None:
        return ProxyOpResult(ok=True, restored=False, message="Không có snapshot — không đụng proxy OS.")
    backend = snap.get("backend") or snap.get("os") or detect_backend()
    try:
        if backend == "darwin":
            result = _macos_restore(snap)
        elif backend == "win32":
            result = _win_restore(snap)
        elif backend == "gnome":
            result = _gnome_restore(snap)
        elif backend == "kde":
            result = _kde_restore(snap)
        else:
            result = ProxyOpResult(ok=False, message=f"Snapshot backend không hỗ trợ: {backend}")
    except Exception as exc:
        return ProxyOpResult(ok=False, message=f"Restore lỗi: {exc}")
    if result.ok:
        _clear_snapshot()
    return result


def system_proxy_status() -> str:
    backend = detect_backend()
    snap = "yes" if _load_snapshot() else "no"
    return f"backend={backend} snapshot={snap}"

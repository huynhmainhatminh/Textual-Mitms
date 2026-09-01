# core/ca.py
"""
Sinh và cài/gỡ CA cert của mitmproxy vào trust store hệ thống.

Nguồn tham số (mitmproxy==11.0.2, không bịa):
- mitmproxy.options.CONF_DIR = "~/.mitmproxy"
- mitmproxy.options.CONF_BASENAME = "mitmproxy"
- mitmproxy.options.KEY_SIZE = 2048
- CertStore.from_store(path, basename, key_size, passphrase=None)
  nếu {basename}-ca.pem chưa có thì gọi CertStore.create_store(...)
- create_store ghi đúng các file:
    {basename}-ca.pem          (cert + private key)
    {basename}-ca.p12          (cert + private key, PKCS#12)
    {basename}-ca-cert.pem     (cert only, PEM)  ← file dùng để trust
    {basename}-ca-cert.cer     (cùng nội dung PEM, tên Android/Windows)
    {basename}-ca-cert.p12     (cert only, PKCS#12)
    {basename}-dhparam.pem

Lệnh trust (docs mitmproxy / OS):
- macOS:
    sudo security add-trusted-cert -d -p ssl -p basic \\
      -k /Library/Keychains/System.keychain <mitmproxy-ca-cert.pem>
    gỡ: security delete-certificate -Z <SHA-1> /Library/Keychains/System.keychain
- Windows:
    certutil -addstore root <mitmproxy-ca-cert.cer>
    gỡ: certutil -delstore root <CertId>   (CertId = SHA-1 thumbprint)
- Debian/Ubuntu:
    copy vào /usr/local/share/ca-certificates/*.crt rồi update-ca-certificates
    (đuôi .crt bắt buộc — Ubuntu Server docs)
- Fedora/RHEL:
    copy vào /etc/pki/ca-trust/source/anchors/ rồi update-ca-trust
- Arch (p11-kit):
    trust anchor <file>
    trust anchor --remove <file>
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from mitmproxy.certs import CertStore
from mitmproxy.options import CONF_BASENAME, CONF_DIR, KEY_SIZE


# File do chính tool này thả vào trust store — chỉ gỡ file này, không đụng CA khác.
_LINUX_TRUST_BASENAME = "textual-mitms.crt"
_NSS_NICKNAME = "mitmproxy"


@dataclass
class CaPaths:
    confdir: Path
    basename: str
    ca_pem: Path          # cert + key  — KHÔNG install
    ca_p12: Path          # cert + key
    ca_cert_pem: Path     # cert only
    ca_cert_cer: Path     # cert only (cùng bytes PEM)
    ca_cert_p12: Path     # cert only PKCS#12
    dhparam: Path


@dataclass
class CaInfo:
    paths: CaPaths
    exists: bool
    subject: str = ""
    issuer: str = ""
    not_valid_before: str = ""
    not_valid_after: str = ""
    fingerprint_sha256: str = ""
    fingerprint_sha1: str = ""
    serial_hex: str = ""


@dataclass
class CaCommandResult:
    ok: bool
    message: str
    command: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None


def _cert_time(cert: x509.Certificate, name: str) -> str:
    # cryptography >=42: not_valid_before_utc; bản cũ: not_valid_before (naive datetime)
    utc_attr = getattr(cert, f"{name}_utc", None)
    value = utc_attr if utc_attr is not None else getattr(cert, name)
    return value.isoformat()


def default_confdir() -> Path:
    """~/.mitmproxy — đúng CONF_DIR của mitmproxy 11.0.2, expanduser."""
    return Path(os.path.expanduser(CONF_DIR))


def ca_paths(confdir: Path | None = None) -> CaPaths:
    base = confdir or default_confdir()
    name = CONF_BASENAME
    return CaPaths(
        confdir=base,
        basename=name,
        ca_pem=base / f"{name}-ca.pem",
        ca_p12=base / f"{name}-ca.p12",
        ca_cert_pem=base / f"{name}-ca-cert.pem",
        ca_cert_cer=base / f"{name}-ca-cert.cer",
        ca_cert_p12=base / f"{name}-ca-cert.p12",
        dhparam=base / f"{name}-dhparam.pem",
    )


def ensure_ca(confdir: Path | None = None) -> CaPaths:
    """
    Tạo CA nếu chưa có. Không listen port.

    Gọi đúng API mitmproxy 11.0.2:
        CertStore.from_store(path, basename, key_size, passphrase=None)
    key_size = KEY_SIZE = 2048.
    """
    paths = ca_paths(confdir)
    paths.confdir.mkdir(parents=True, exist_ok=True)
    CertStore.from_store(
        path=paths.confdir,
        basename=CONF_BASENAME,
        key_size=KEY_SIZE,
        passphrase=None,
    )
    return paths


def inspect_ca(confdir: Path | None = None) -> CaInfo:
    paths = ca_paths(confdir)
    if not paths.ca_cert_pem.is_file():
        return CaInfo(paths=paths, exists=False)
    data = paths.ca_cert_pem.read_bytes()
    cert = x509.load_pem_x509_certificate(data)
    sha256 = cert.fingerprint(hashes.SHA256()).hex().upper()
    sha1 = cert.fingerprint(hashes.SHA1()).hex().upper()
    serial = format(cert.serial_number, "X")
    return CaInfo(
        paths=paths,
        exists=True,
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        not_valid_before=_cert_time(cert, "not_valid_before"),
        not_valid_after=_cert_time(cert, "not_valid_after"),
        fingerprint_sha256=":".join(sha256[i:i + 2] for i in range(0, len(sha256), 2)),
        fingerprint_sha1=":".join(sha1[i:i + 2] for i in range(0, len(sha1), 2)),
        serial_hex=serial,
    )


def env_snippet(listen_host: str = "127.0.0.1", listen_port: int = 8080) -> str:
    """
    Cách trust theo process, không đụng system store.
    docs mitmproxy: curl --proxy ... --cacert ~/.mitmproxy/mitmproxy-ca-cert.pem
    """
    paths = ca_paths()
    pem = str(paths.ca_cert_pem)
    proxy = f"http://{listen_host}:{listen_port}"
    if os.name == "nt":
        return (
            f'set HTTPS_PROXY={proxy}\n'
            f'set HTTP_PROXY={proxy}\n'
            f'set SSL_CERT_FILE={pem}\n'
            f'set REQUESTS_CA_BUNDLE={pem}\n'
            f'set NODE_EXTRA_CA_CERTS={pem}\n'
            f'set CURL_CA_BUNDLE={pem}\n'
        )
    return (
        f"export HTTPS_PROXY={proxy}\n"
        f"export HTTP_PROXY={proxy}\n"
        f"export SSL_CERT_FILE={pem}\n"
        f"export REQUESTS_CA_BUNDLE={pem}\n"
        f"export NODE_EXTRA_CA_CERTS={pem}\n"
        f"export CURL_CA_BUNDLE={pem}\n"
    )


def _run(argv: list[str], *, timeout: int = 120) -> CaCommandResult:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return CaCommandResult(
            ok=False,
            message=f"Không tìm thấy lệnh: {argv[0]}",
            command=argv,
        )
    except subprocess.TimeoutExpired:
        return CaCommandResult(
            ok=False,
            message="Lệnh hết thời gian chờ (password sudo/UAC?).",
            command=argv,
        )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    ok = proc.returncode == 0
    detail = stdout or stderr or f"returncode={proc.returncode}"
    return CaCommandResult(
        ok=ok,
        message=detail if ok else (stderr or stdout or f"returncode={proc.returncode}"),
        command=argv,
        stdout=stdout,
        stderr=stderr,
        returncode=proc.returncode,
    )


def _posix_elevate(inner: list[str]) -> list[str]:
    """
    Bọc lệnh bằng pkexec (GUI) hoặc sudo (TTY).
    Không nhúng mật khẩu. User phải xác nhận trên dialog/TTY.
    """
    if shutil.which("pkexec"):
        return ["pkexec", *inner]
    if shutil.which("sudo"):
        return ["sudo", *inner]
    return inner


def _macos_admin_shell(shell_command: str) -> list[str]:
    """
    Hộp thoại admin macOS. Lệnh bên trong là đúng `security` / `cp` của hệ thống.
    osascript 'do shell script ... with administrator privileges'
    """
    escaped = (
        shell_command
        .replace("\\", "\\\\")
        .replace('"', '\\"')
    )
    return [
        "osascript",
        "-e",
        f'do shell script "{escaped}" with administrator privileges',
    ]


def _linux_flavor() -> str:
    if shutil.which("update-ca-certificates"):
        return "debian"
    if shutil.which("update-ca-trust"):
        return "rhel"
    if shutil.which("trust"):
        return "arch"
    return "unknown"


def _linux_dest(flavor: str) -> Path | None:
    if flavor == "debian":
        return Path("/usr/local/share/ca-certificates") / _LINUX_TRUST_BASENAME
    if flavor == "rhel":
        return Path("/etc/pki/ca-trust/source/anchors") / _LINUX_TRUST_BASENAME
    return None


def install_ca(confdir: Path | None = None) -> CaCommandResult:
    paths = ensure_ca(confdir)
    cert_pem = paths.ca_cert_pem
    cert_cer = paths.ca_cert_cer
    if not cert_pem.is_file():
        return CaCommandResult(ok=False, message="Chưa có file CA cert (mitmproxy-ca-cert.pem).")

    system = sys.platform

    if system == "darwin":
        # docs mitmproxy: security add-trusted-cert -d -p ssl -p basic -k System.keychain
        inner = (
            "security add-trusted-cert -d -p ssl -p basic "
            f"-k /Library/Keychains/System.keychain {cert_pem}"
        )
        return _run(_macos_admin_shell(inner))

    if system == "win32":
        # docs mitmproxy: certutil -addstore root mitmproxy-ca-cert.cer
        # store name "root" = Trusted Root Certification Authorities (Local Machine)
        return _run(["certutil", "-addstore", "root", str(cert_cer)])

    flavor = _linux_flavor()
    if flavor == "debian":
        dest = _linux_dest(flavor)
        assert dest is not None
        script = f"cp {cert_pem} {dest} && update-ca-certificates"
        return _run(_posix_elevate(["bash", "-lc", script]))

    if flavor == "rhel":
        dest = _linux_dest(flavor)
        assert dest is not None
        script = f"cp {cert_pem} {dest} && update-ca-trust"
        return _run(_posix_elevate(["bash", "-lc", script]))

    if flavor == "arch":
        # man trust: trust anchor /path/to/certificate.crt
        return _run(_posix_elevate(["trust", "anchor", str(cert_pem)]))

    return CaCommandResult(
        ok=False,
        message=(
            "Không nhận ra trust store Linux "
            "(cần update-ca-certificates, update-ca-trust hoặc trust)."
        ),
    )


def uninstall_ca(confdir: Path | None = None) -> CaCommandResult:
    info = inspect_ca(confdir)
    system = sys.platform

    if system == "darwin":
        if not info.exists:
            return CaCommandResult(ok=False, message="Chưa có file CA để đối chiếu fingerprint.")
        # man security: delete-certificate [-c name] [-Z hash] [keychain...]
        # Dùng SHA-1 (-Z) để khỏi xóa nhầm cert khác cùng CN.
        sha1_plain = info.fingerprint_sha1.replace(":", "")
        inner = (
            f"security delete-certificate -Z {sha1_plain} "
            "/Library/Keychains/System.keychain"
        )
        return _run(_macos_admin_shell(inner))

    if system == "win32":
        if not info.exists:
            return CaCommandResult(ok=False, message="Chưa có file CA để lấy thumbprint.")
        # certutil -delstore CertificateStoreName CertId
        # CertId = SHA-1 thumbprint (Microsoft docs).
        thumb = info.fingerprint_sha1.replace(":", "")
        return _run(["certutil", "-delstore", "root", thumb])

    flavor = _linux_flavor()
    if flavor == "debian":
        dest = _linux_dest(flavor)
        script = f"rm -f {dest} && update-ca-certificates"
        return _run(_posix_elevate(["bash", "-lc", script]))

    if flavor == "rhel":
        dest = _linux_dest(flavor)
        script = f"rm -f {dest} && update-ca-trust"
        return _run(_posix_elevate(["bash", "-lc", script]))

    if flavor == "arch":
        paths = ca_paths(confdir)
        return _run(_posix_elevate(["trust", "anchor", "--remove", str(paths.ca_cert_pem)]))

    return CaCommandResult(
        ok=False,
        message="Không nhận ra trust store Linux để gỡ CA.",
    )


def trust_status(confdir: Path | None = None) -> tuple[str, str]:
    """
    Trả về (state, detail).
    state: missing | generated | trusted | untrusted | unknown
    Chỉ dùng lệnh có thật của từng OS, không đoán.
    """
    info = inspect_ca(confdir)
    if not info.exists:
        return "missing", "Chưa generate CA (chưa có ~/.mitmproxy/mitmproxy-ca-cert.pem)."

    system = sys.platform
    pem = info.paths.ca_cert_pem

    if system == "darwin":
        result = _run(["security", "verify-cert", "-c", str(pem)])
        if result.ok:
            return "trusted", "security verify-cert: hệ thống tin CA này."
        return "untrusted", result.message or "Chưa có trong System.keychain."

    if system == "win32":
        thumb = info.fingerprint_sha1.replace(":", "")
        result = _run(["certutil", "-verifystore", "root", thumb])
        if result.ok:
            return "trusted", "certutil -verifystore root: có trong Trusted Root."
        return "untrusted", result.message or "Chưa có trong store Root."

    flavor = _linux_flavor()
    dest = _linux_dest(flavor)
    if dest is not None and dest.is_file():
        return "trusted", f"Đã thấy file trust: {dest}"
    if flavor == "arch":
        listed = _run(["trust", "list"])
        needle = info.fingerprint_sha256.replace(":", "").lower()
        blob = (listed.stdout + listed.stderr).lower().replace(":", "")
        if listed.ok and needle and needle in blob:
            return "trusted", "trust list có fingerprint SHA-256 của CA."
        return "untrusted", "Chưa thấy CA trong `trust list`."
    if dest is not None:
        return "untrusted", f"Chưa có {dest}."
    return "generated", "Đã có file CA; chưa kiểm tra được trust store."


def install_nss_user_db(confdir: Path | None = None) -> CaCommandResult:
    """
    Chrome/Chromium trên Linux đọc NSS db ~/.pki/nssdb, không đọc /etc/ssl/certs.
    Dùng nss `certutil` (libnss3-tools) — khác hoàn toàn certutil của Windows.
    """
    if sys.platform == "win32":
        return CaCommandResult(ok=False, message="NSS db không áp dụng trên Windows.")
    nss = shutil.which("certutil")
    if not nss:
        return CaCommandResult(
            ok=False,
            message="Không có nss certutil (Debian/Ubuntu: apt install libnss3-tools).",
        )
    nssdb = Path.home() / ".pki" / "nssdb"
    if not nssdb.is_dir():
        return CaCommandResult(ok=False, message=f"Không có NSS db: {nssdb}")
    paths = ensure_ca(confdir)
    return _run([
        nss,
        "-d", f"sql:{nssdb}",
        "-A",
        "-t", "C,,",
        "-n", _NSS_NICKNAME,
        "-i", str(paths.ca_cert_pem),
    ])


def uninstall_nss_user_db() -> CaCommandResult:
    if sys.platform == "win32":
        return CaCommandResult(ok=False, message="NSS db không áp dụng trên Windows.")
    nss = shutil.which("certutil")
    if not nss:
        return CaCommandResult(ok=False, message="Không có nss certutil.")
    nssdb = Path.home() / ".pki" / "nssdb"
    if not nssdb.is_dir():
        return CaCommandResult(ok=False, message=f"Không có NSS db: {nssdb}")
    return _run([nss, "-d", f"sql:{nssdb}", "-D", "-n", _NSS_NICKNAME])

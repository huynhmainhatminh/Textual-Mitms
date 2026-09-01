import argparse

from .app import TextualMitms
from .core.system_proxy import apply_system_proxy, restore_system_proxy, system_proxy_status
from .core.ca import (
    ensure_ca,
    env_snippet,
    inspect_ca,
    install_ca,
    install_nss_user_db,
    trust_status,
    uninstall_ca,
    uninstall_nss_user_db,
)


def _print_info() -> int:
    info = inspect_ca()
    state, detail = trust_status()
    print(f"confdir     : {info.paths.confdir}")
    print(f"cert (only) : {info.paths.ca_cert_pem}")
    print(f"cert+key    : {info.paths.ca_pem}   # KHÔNG install file này")
    print(f"state       : {state}")
    print(f"detail      : {detail}")
    if info.exists:
        print(f"subject     : {info.subject}")
        print(f"valid       : {info.not_valid_before} -> {info.not_valid_after}")
        print(f"sha256      : {info.fingerprint_sha256}")
        print(f"sha1        : {info.fingerprint_sha1}")
    return 0


def _print_result(result, ok_exit: str) -> int:
    if result.ok:
        print(ok_exit)
        if result.stdout:
            print(result.stdout)
        return 0
    print(result.message)
    if result.command:
        print("command:", " ".join(result.command))
    if result.stderr:
        print(result.stderr)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Textual-Mitms — Terminal MITM proxy UI"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Proxy listen host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Proxy listen port (default: 8080)",
    )

    sub = parser.add_subparsers(dest="command")

    cert = sub.add_parser("cert", help="Generate / install / uninstall mitmproxy CA")
    cert_sub = cert.add_subparsers(dest="cert_command", required=True)
    cert_sub.add_parser("generate", help="Tạo CA vào ~/.mitmproxy nếu chưa có")
    cert_sub.add_parser("status", help="In path, fingerprint, trạng thái trust")
    cert_sub.add_parser("path", help="In đường dẫn mitmproxy-ca-cert.pem")
    cert_sub.add_parser("install", help="Cài CA vào system trust store (cần admin)")
    cert_sub.add_parser("uninstall", help="Gỡ CA khỏi system trust store (cần admin)")
    env_p = cert_sub.add_parser("env", help="In snippet HTTPS_PROXY + SSL_CERT_FILE")
    env_p.add_argument("--host", dest="env_host", default=None)
    env_p.add_argument("--port", dest="env_port", type=int, default=None)
    nss = cert_sub.add_parser("nss", help="Cài/gỡ CA trong ~/.pki/nssdb (Chrome Linux)")
    nss.add_argument("nss_action", choices=["install", "uninstall"])

    os_proxy = sub.add_parser("os-proxy", help="Bật/tắt / restore proxy hệ thống")
    os_sub = os_proxy.add_subparsers(dest="os_command", required=True)
    os_sub.add_parser("status", help="Backend hiện tại + snapshot")
    os_sub.add_parser("apply", help="Set HTTP/HTTPS system proxy = listen host:port")
    os_sub.add_parser("restore", help="Trả proxy OS về snapshot trước apply")

    args = parser.parse_args()

    if args.command == "cert":
        raise SystemExit(_handle_cert(args))
    if args.command == "os-proxy":
        raise SystemExit(_handle_os_proxy(args))

    app = TextualMitms(listen_host=args.host, listen_port=args.port)
    app.run()


def _handle_cert(args) -> int:
    cmd = args.cert_command
    if cmd == "generate":
        paths = ensure_ca()
        print(paths.ca_cert_pem)
        return 0
    if cmd == "status":
        ensure_ca()
        return _print_info()
    if cmd == "path":
        print(ensure_ca().ca_cert_pem)
        return 0
    if cmd == "install":
        ensure_ca()
        return _print_result(install_ca(), "Installed CA into system trust store.")
    if cmd == "uninstall":
        return _print_result(uninstall_ca(), "Removed CA from system trust store.")
    if cmd == "env":
        host = args.env_host or args.host
        port = args.env_port or args.port
        ensure_ca()
        print(env_snippet(host, port), end="")
        return 0
    if cmd == "nss":
        if args.nss_action == "install":
            ensure_ca()
            return _print_result(install_nss_user_db(), "Installed CA into NSS db.")
        return _print_result(uninstall_nss_user_db(), "Removed CA from NSS db.")
    return 1


def _handle_os_proxy(args) -> int:
    cmd = args.os_command
    if cmd == "status":
        print(system_proxy_status())
        return 0
    if cmd == "apply":
        result = apply_system_proxy(args.host, args.port)
        print(result.message)
        for line in result.details:
            print(" ", line)
        return 0 if result.ok else 1
    if cmd == "restore":
        result = restore_system_proxy()
        print(result.message)
        for line in result.details:
            print(" ", line)
        return 0 if result.ok else 1
    return 1


if __name__ == "__main__":
    main()

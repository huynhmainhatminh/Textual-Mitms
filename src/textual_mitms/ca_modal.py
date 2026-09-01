# ui/ca_modal.py
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static
from textual.screen import ModalScreen
from textual import events, on, work

from .core.ca import (
    CaCommandResult,
    ensure_ca,
    env_snippet,
    inspect_ca,
    install_ca,
    install_nss_user_db,
    trust_status,
    uninstall_ca,
    uninstall_nss_user_db,
)


class CaCertModal(ModalScreen[None]):
    """Popup generate / install / uninstall CA cert (system trust store)."""

    BINDINGS = [("escape", "close_modal", "Đóng")]

    def __init__(self, listen_host: str, listen_port: int) -> None:
        super().__init__()
        self.listen_host = listen_host
        self.listen_port = listen_port
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical(id="ca-dialog") as dialog:
            dialog.border_title = "CA CERTIFICATE"
            dialog.styles.border_title_align = "center"

            yield Label("── Status ──", classes="section-title")
            yield Static("Đang đọc CA…", id="ca-status")
            yield Static("", id="ca-detail")
            yield Static("", id="ca-meta")

            yield Label("── Cảnh báo ──", classes="section-title")
            yield Static(
                "Install CA = máy này tin mọi chứng chỉ do proxy ký.\n"
                "Chỉ làm trên máy bạn quản lý. Private key (mitmproxy-ca.pem) không được cài.",
                id="ca-warn",
            )

            with Horizontal(id="ca-buttons"):
                yield Button("Generate", id="btn-ca-generate", variant="primary")
                yield Button("Install", id="btn-ca-install", variant="success")
                yield Button("Uninstall", id="btn-ca-uninstall", variant="error")
            with Horizontal(id="ca-buttons-2"):
                yield Button("Copy path", id="btn-ca-copy-path")
                yield Button("Copy env", id="btn-ca-copy-env")
                yield Button("NSS (Linux Chrome)", id="btn-ca-nss")
            with Horizontal(id="ca-buttons-3"):
                yield Button("Gỡ NSS", id="btn-ca-nss-remove")
                yield Button("Refresh", id="btn-ca-refresh")
                yield Button("Close", id="btn-ca-close", variant="error")

    def on_mount(self) -> None:
        self._refresh_status()

    def _refresh_status(self) -> None:
        info = inspect_ca()
        state, detail = trust_status()
        status = self.query_one("#ca-status", Static)
        meta = self.query_one("#ca-meta", Static)
        extra = self.query_one("#ca-detail", Static)

        color = {
            "missing": "red",
            "generated": "yellow",
            "untrusted": "yellow",
            "trusted": "green",
            "unknown": "yellow",
        }.get(state, "yellow")
        status.update(f"[{color}]● {state.upper()}[/]  {info.paths.ca_cert_pem}")
        extra.update(detail)

        if info.exists:
            meta.update(
                f"Subject: {info.subject}\n"
                f"Valid:   {info.not_valid_before} → {info.not_valid_after}\n"
                f"SHA-256: {info.fingerprint_sha256}\n"
                f"SHA-1:   {info.fingerprint_sha1}"
            )
        else:
            meta.update("Chưa có file CA. Bấm Generate (hoặc Start Proxy lần đầu).")

    def action_close_modal(self) -> None:
        self.dismiss(None)

    def _notify_result(self, result: CaCommandResult, ok_msg: str) -> None:
        if result.ok:
            self.app.notify(ok_msg, severity="information")
        else:
            self.app.notify(result.message, severity="error")
        self._refresh_status()
        self._busy = False

    @on(Button.Pressed, "#btn-ca-generate")
    def on_generate(self) -> None:
        paths = ensure_ca()
        self.app.notify(f"CA sẵn sàng: {paths.ca_cert_pem}", severity="information")
        self._refresh_status()

    @on(Button.Pressed, "#btn-ca-install")
    def on_install(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.app.notify("Đang cài CA — hệ thống sẽ hỏi quyền admin.", severity="warning")
        self._run_install()

    @on(Button.Pressed, "#btn-ca-uninstall")
    def on_uninstall(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.app.notify("Đang gỡ CA — hệ thống sẽ hỏi quyền admin.", severity="warning")
        self._run_uninstall()

    @work(thread=True)
    def _run_install(self) -> None:
        result = install_ca()
        self.app.call_from_thread(self._notify_result, result, "Đã gửi lệnh install CA.")

    @work(thread=True)
    def _run_uninstall(self) -> None:
        result = uninstall_ca()
        self.app.call_from_thread(self._notify_result, result, "Đã gửi lệnh uninstall CA.")

    @on(Button.Pressed, "#btn-ca-nss")
    def on_nss_install(self) -> None:
        result = install_nss_user_db()
        self._notify_result(result, "Đã thêm CA vào ~/.pki/nssdb (Chrome Linux).")

    @on(Button.Pressed, "#btn-ca-nss-remove")
    def on_nss_remove(self) -> None:
        result = uninstall_nss_user_db()
        self._notify_result(result, "Đã gỡ CA khỏi ~/.pki/nssdb.")

    @on(Button.Pressed, "#btn-ca-copy-path")
    def on_copy_path(self) -> None:
        paths = ensure_ca()
        self.app.copy_to_clipboard(str(paths.ca_cert_pem))
        self.app.notify("Đã copy đường dẫn mitmproxy-ca-cert.pem", severity="information")

    @on(Button.Pressed, "#btn-ca-copy-env")
    def on_copy_env(self) -> None:
        snippet = env_snippet(self.listen_host, self.listen_port)
        self.app.copy_to_clipboard(snippet)
        self.app.notify("Đã copy biến môi trường HTTPS_PROXY + SSL_CERT_FILE", severity="information")

    @on(Button.Pressed, "#btn-ca-refresh")
    def on_refresh(self) -> None:
        self._refresh_status()

    @on(Button.Pressed, "#btn-ca-close")
    def on_close(self) -> None:
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)

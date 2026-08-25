# ui/options_modal.py
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Switch
from textual.screen import ModalScreen
from textual import events, on


class OptionsModal(ModalScreen[dict | None]):
    """Popup tùy chọn bật/tắt các tính năng mitmproxy (boolean only)."""

    def __init__(self, current: dict) -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="options-dialog") as options_dialog:
            options_dialog.border_title = "OPTIONS"
            options_dialog.styles.border_title_align = "center"

            # ----- Capture Mode (chỉ chọn 1) -----
            yield Label("── Capture Mode ──", classes="section-title")
            with Horizontal(classes="option-row"):
                yield Label("Basic Capture", classes="option-label")
                yield Switch(
                    value=self.current.get("capture_mode", "basic") == "basic",
                    id="switch-capture-basic",
                )
            with Horizontal(classes="option-row"):
                yield Label("Full Capture", classes="option-label")
                yield Switch(
                    value=self.current.get("capture_mode", "basic") == "full",
                    id="switch-capture-full",
                )

            # ----- Protocol -----
            yield Label("── Protocol ──", classes="section-title")
            with Horizontal(classes="option-row"):
                yield Label("HTTP/2", classes="option-label")
                yield Switch(value=self.current["http2"], id="switch-http2")
            with Horizontal(classes="option-row"):
                yield Label("HTTP/3", classes="option-label")
                yield Switch(value=self.current["http3"], id="switch-http3")
            with Horizontal(classes="option-row"):
                yield Label("WebSocket", classes="option-label")
                yield Switch(value=self.current["websocket"], id="switch-websocket")

            # ----- Capture Helpers -----
            yield Label("── Capture Helpers ──", classes="section-title")
            with Horizontal(classes="option-row"):
                yield Label("Anti-Cache", classes="option-label")
                yield Switch(value=self.current["anticache"], id="switch-anticache")
            with Horizontal(classes="option-row"):
                yield Label("Anti-Comp", classes="option-label")
                yield Switch(value=self.current["anticomp"], id="switch-anticomp")

            # ----- Security -----
            yield Label("── Security ──", classes="section-title")
            with Horizontal(classes="option-row"):
                yield Label("SSL Insecure", classes="option-label")
                yield Switch(value=self.current["ssl_insecure"], id="switch-ssl-insecure")

            with Horizontal(id="options-buttons"):
                yield Button("Save", id="btn-apply", variant="success")
                yield Button("Cancel", id="btn-cancel", variant="error")

    def on_mount(self) -> None:
        self.query_one("#switch-capture-basic", Switch).focus()

    # --- Mutual exclusion: chỉ 1 trong 2 chế độ được bật ---
    @on(Switch.Changed, "#switch-capture-basic")
    def on_basic_changed(self, event: Switch.Changed) -> None:
        if event.value:
            self.query_one("#switch-capture-full", Switch).value = False
        elif not self.query_one("#switch-capture-full", Switch).value:
            # Không cho tắt cả hai → giữ Basic
            event.switch.value = True

    @on(Switch.Changed, "#switch-capture-full")
    def on_full_changed(self, event: Switch.Changed) -> None:
        if event.value:
            self.query_one("#switch-capture-basic", Switch).value = False
        elif not self.query_one("#switch-capture-basic", Switch).value:
            event.switch.value = True

    @on(Button.Pressed, "#btn-apply")
    def apply_options(self) -> None:
        is_full = self.query_one("#switch-capture-full", Switch).value
        result = {
            "capture_mode": "full" if is_full else "basic",
            "http2": self.query_one("#switch-http2", Switch).value,
            "http3": self.query_one("#switch-http3", Switch).value,
            "websocket": self.query_one("#switch-websocket", Switch).value,
            "anticache": self.query_one("#switch-anticache", Switch).value,
            "anticomp": self.query_one("#switch-anticomp", Switch).value,
            "ssl_insecure": self.query_one("#switch-ssl-insecure", Switch).value,
        }
        self.dismiss(result)

    @on(Button.Pressed, "#btn-cancel")
    def cancel_options(self) -> None:
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)

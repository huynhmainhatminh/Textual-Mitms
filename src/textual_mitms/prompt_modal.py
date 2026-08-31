# ui/prompt_modal.py
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Input
from textual.screen import ModalScreen
from textual import on

from .core.utils import normalize_host_rule, unique_normalized_hosts


class PromptModal(ModalScreen[set]):
    """Cửa sổ nhỏ gọn để người dùng nhập Domain và quản lý danh sách đã thêm dưới dạng Thẻ (Tags)."""

    # escape → action_cancel_prompt (ModalScreen không document binding escape mặc định)
    BINDINGS = [
        Binding("escape", "cancel_prompt", "Cancel", show=False),
    ]

    CSS = """
    PromptModal { align: center middle; background: rgba(0, 0, 0, 0.7); }
    #prompt-dialog { width: 50; height: auto; max-height: 80%; background: $surface; padding: 1 2; border: heavy $accent; }
    #prompt-title { text-style: bold; margin-bottom: 1; text-align: center; width: 100%; color: $text; }

    #host-list-box { 
        height: auto; 
        max-height: 12; 
        margin-bottom: 1; 
        border: round $panel-lighten-2; 
        background: $panel-darken-2; 
        padding: 1; 
    }

    .host-row { 
        height: 3; 
        margin-bottom: 1; 
        align-vertical: middle; 
        border: solid $panel-lighten-2; 
        background: $panel; 
        padding: 0 1; 
    }
    .host-name { width: 1fr; text-style: bold; align-vertical: middle; color: $success; }

    .btn-remove-host { min-width: 3; height: 1; border: none; background: transparent; color: $error; text-style: bold; }
    .btn-remove-host:hover { background: $error; color: white; }

    #prompt-input-row { height: auto; margin-bottom: 1; }
    #prompt-input { width: 1fr; }
    #prompt-buttons { height: auto; align: center middle; }
    #prompt-buttons Button { margin: 0 1; min-width: 10; }
    .-hidden { display: none !important; }
    """

    def __init__(
        self,
        title: str,
        placeholder: str,
        current_hosts: set,
        other_hosts: set | None = None,
        other_list_name: str = "list còn lại",
    ):
        super().__init__()
        self.title = title
        self.placeholder = placeholder
        self.working_hosts = unique_normalized_hosts(current_hosts)
        self.other_keys = unique_normalized_hosts(other_hosts or set())
        self.other_list_name = other_list_name
        self.sorted_hosts = []

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-dialog") as prompt_dialog:
            prompt_dialog.border_title = f"{self.title}"
            prompt_dialog.styles.border_title_align = "center"
            yield VerticalScroll(id="host-list-box", classes="-hidden")
            with Horizontal(id="prompt-input-row"):
                yield Input(placeholder=self.placeholder, id="prompt-input")

            with Horizontal(id="prompt-buttons"):
                yield Button("Save", id="btn-save", variant="success")
                yield Button("Add", id="btn-add-host", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="error")

    def on_mount(self) -> None:
        self._refresh_host_list()
        self.query_one("#prompt-input", Input).focus()

    def _refresh_host_list(self) -> None:
        list_box = self.query_one("#host-list-box", VerticalScroll)
        list_box.remove_children()

        if self.working_hosts:
            list_box.remove_class("-hidden")
            self.sorted_hosts = sorted(list(self.working_hosts))

            for idx, host in enumerate(self.sorted_hosts):
                row = Horizontal(
                    Label(f"• {host}", classes="host-name"),
                    Button("-", id=f"del__{idx}", classes="btn-remove-host"),
                    classes="host-row"
                )
                list_box.mount(row)
        else:
            list_box.add_class("-hidden")
            self.sorted_hosts = []

    def _commit_input_host(self, raw_value: str, host_input: Input) -> bool:
        """Thêm host từ ô nhập vào working_hosts, xóa ô, refresh list. Không dismiss."""
        key = normalize_host_rule(raw_value)
        if not key:
            return False
        already = key in self.working_hosts
        self.working_hosts.add(key)
        host_input.value = ""
        self._refresh_host_list()
        if key in self.other_keys:
            self.notify(
                f"'{key}' đang có trong {self.other_list_name}. "
                f"Save sẽ gỡ khỏi {self.other_list_name}.",
                severity="warning",
            )
        elif already:
            self.notify(f"'{key}' đã có trong danh sách.", severity="information")
        return True

    @on(Button.Pressed)
    def handle_buttons(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id and button_id.startswith("del__"):
            try:
                idx = int(button_id.replace("del__", ""))
                host_to_remove = self.sorted_hosts[idx]
                if host_to_remove in self.working_hosts:
                    self.working_hosts.remove(host_to_remove)
                    self._refresh_host_list()
            except (ValueError, IndexError):
                pass

    @on(Button.Pressed, "#btn-add-host")
    def add_host_action(self) -> None:
        host_input = self.query_one("#prompt-input", Input)
        self._commit_input_host(host_input.value, host_input)
        host_input.focus()

    @on(Button.Pressed, "#btn-save")
    def save_action(self) -> None:
        host_input = self.query_one("#prompt-input", Input)
        self._commit_input_host(host_input.value, host_input)
        self.dismiss(self.working_hosts)

    @on(Button.Pressed, "#btn-cancel")
    def cancel_action(self) -> None:
        self.dismiss(None)

    def action_cancel_prompt(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#prompt-input")
    def submit_action(self, event: Input.Submitted) -> None:
        # Input.Submitted: posted khi nhấn Enter trong Input
        # attributes chính thức: event.value, event.input, event.validation_result
        # Enter chỉ commit host, không đóng modal.
        self._commit_input_host(event.value, event.input)

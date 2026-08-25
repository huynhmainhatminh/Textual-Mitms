# ui/modal.py
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static, Tabs, Tab, TextArea, Input, DataTable
from textual.screen import ModalScreen
from textual import events, on
from rich.text import Text
from textual.widgets.text_area import Selection as TASelection
from pathlib import Path
# Import bộ công cụ xử lý logic
from .core.utils import parse_headers_to_list, format_secure_json, build_curl_command, build_row_string


class PromptModal(ModalScreen[set]):
    """Cửa sổ nhỏ gọn để người dùng nhập Domain và quản lý danh sách đã thêm dưới dạng Thẻ (Tags)."""

    CSS = """
    PromptModal { align: center middle; background: rgba(0, 0, 0, 0.7); }
    #prompt-dialog { width: 50; height: auto; max-height: 80%; background: $surface; padding: 1 2; border: heavy $accent; }
    #prompt-title { text-style: bold; margin-bottom: 1; text-align: center; width: 100%; color: $text; }

    /* Box hiển thị danh sách đã thêm */
    #host-list-box { 
        height: auto; 
        max-height: 12; 
        margin-bottom: 1; 
        border: round $panel-lighten-2; 
        background: $panel-darken-2; 
        padding: 1; 
    }

    /* Giao diện từng dòng Host: Đóng khung như một Thẻ (Tag) */
    .host-row { 
        height: 3; 
        margin-bottom: 1; 
        align-vertical: middle; 
        border: solid $panel-lighten-2; 
        background: $panel; 
        padding: 0 1; 
    }
    .host-name { width: 1fr; text-style: bold; align-vertical: middle; color: $success; }

    /* Nút xóa dấu trừ: Nền trong suốt, nổi đỏ khi hover */
    .btn-remove-host { min-width: 3; height: 1; border: none; background: transparent; color: $error; text-style: bold; }
    .btn-remove-host:hover { background: $error; color: white; }

    #prompt-input { margin-bottom: 1; }
    #prompt-buttons { height: auto; align: center middle; }
    #prompt-buttons Button { margin: 0 1; min-width: 10; }
    .-hidden { display: none !important; }
    """

    def __init__(self, title: str, placeholder: str, current_hosts: set):
        super().__init__()
        self.title = title
        self.placeholder = placeholder
        self.working_hosts = set(current_hosts)
        self.sorted_hosts = []

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-dialog") as prompt_dialog:
            prompt_dialog.border_title = f"{self.title}"
            prompt_dialog.styles.border_title_align = "center"
            yield VerticalScroll(id="host-list-box", classes="-hidden")
            yield Input(placeholder=self.placeholder, id="prompt-input")

            with Horizontal(id="prompt-buttons"):
                yield Button("Save", id="btn-save", variant="success")
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

    @on(Button.Pressed)
    def handle_buttons(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id and button_id.startswith("del__"):
            try:
                idx_str = button_id.replace("del__", "")
                idx = int(idx_str)

                host_to_remove = self.sorted_hosts[idx]

                if host_to_remove in self.working_hosts:
                    self.working_hosts.remove(host_to_remove)
                    self._refresh_host_list()
            except (ValueError, IndexError):
                pass

    @on(Button.Pressed, "#btn-save")
    def save_action(self) -> None:
        val = self.query_one("#prompt-input", Input).value.strip()
        if val:
            self.working_hosts.add(val)
        self.dismiss(self.working_hosts)

    @on(Button.Pressed, "#btn-cancel")
    def cancel_action(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#prompt-input")
    def submit_action(self) -> None:
        self.save_action()


class ClickableVertical(Vertical):
    class Clicked(events.Message):
        def __init__(self, container: "ClickableVertical") -> None:
            self.container = container
            super().__init__()

    def on_click(self) -> None:
        self.post_message(self.Clicked(self))


class HttpDetailModal(ModalScreen):
    """Màn hình Modal chi tiết HTTP (Đã được tái cấu trúc sạch sẽ)."""

    # Nạp CSS từ file ngoài
    CSS_PATH = str(Path(__file__).parent / "styles.tcss")

    BINDINGS = [
        ("escape", "app.pop_screen", "Đóng"),
        ("ctrl+f", "focus_search", "Search")
    ]

    def __init__(self, record_data: dict):
        super().__init__()
        self.record_data = record_data
        self.method = record_data.get("method", "GET")
        self.path = record_data.get("path", "/")
        self.url = record_data.get("url", "")
        self.status = record_data.get("status", "200")

        http_ver_raw = record_data.get("http_version", "HTTP1")
        self.http_version_str = "HTTP/2" if http_ver_raw == "HTTP2" else "HTTP/3" if http_ver_raw == "HTTP3" else "HTTP/1.1"

        self.req_headers_raw = record_data.get("req_headers", "")
        self.req_body = record_data.get("req_body", "")
        self.res_headers_raw = record_data.get("res_headers", "")
        self.res_body = record_data.get("res_body", "")

        self.active_panel = "left"
        self.search_state = {
            "req": {"matches": [], "index": -1, "term": ""},
            "res": {"matches": [], "index": -1, "term": ""}
        }

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-box"):
            with Vertical(id="action-menu"):
                yield Button("Copy cURL", id="btn-copy-curl")
                yield Button("Copy URL", id="btn-copy-url")
                yield Button("Copy Row", id="btn-copy-row")

            with Horizontal(id="dialog-header"):
                yield Button("☰", id="btn-menu")
                yield Static("", classes="spacer")
                yield Button("X", id="btn-close")

            with Horizontal(id="split-container"):
                # REQUEST
                with ClickableVertical(id="left-wrapper", classes="column-wrapper selected-panel") as p_req:
                    p_req.border_title = "REQUEST"
                    p_req.styles.border_title_align = "center"
                    with Vertical(id="panel-request"):
                        yield Static(f"[{self.method}] {self.url}", classes="info-line")
                        yield Tabs(
                            Tab("Pretty", id="view_pretty_request"), Tab("Raw", id="view_raw_request"),
                            Tab("Headers", id="view_headers_request"), id="view-request"
                            )
                        yield Label("Nội dung Request", classes="text-bold")
                        with Vertical(classes="content-box"):
                            yield TextArea(id="req-content-area", read_only=True)
                            yield DataTable(id="req-headers-table", zebra_stripes=True, classes="-hidden")
                        with Horizontal(classes="search-bar-container", id="req-search-bar"):
                            yield Input(
                                placeholder="Search Request", classes="search-input",
                                id="input-req-search"
                                )
                            yield Label("0/0", id="lbl-req-count", classes="search-count")
                            yield Button("▲", id="btn-req-prev", classes="search-nav-btn")
                            yield Button("▼", id="btn-req-next", classes="search-nav-btn")

                # RESPONSE
                with ClickableVertical(id="right-wrapper", classes="column-wrapper") as p_res:
                    p_res.border_title = "RESPONSE"
                    p_res.styles.border_title_align = "center"
                    with Vertical(id="panel-response"):
                        yield Static(f"Status: {self.status}", classes="info-line")
                        yield Tabs(
                            Tab("Pretty", id="view_pretty_response"), Tab("Raw", id="view_raw_response"),
                            Tab("Headers", id="view_headers_response"), id="view-response"
                            )
                        yield Label("Nội dung Response", classes="text-bold")
                        with Vertical(classes="content-box"):
                            yield TextArea(id="res-content-area", read_only=True)
                            yield DataTable(id="res-headers-table", zebra_stripes=True, classes="-hidden")
                        with Horizontal(classes="search-bar-container", id="res-search-bar"):
                            yield Input(
                                placeholder="Search Response", classes="search-input",
                                id="input-res-search"
                                )
                            yield Label("0/0", id="lbl-res-count", classes="search-count")
                            yield Button("▲", id="btn-res-prev", classes="search-nav-btn")
                            yield Button("▼", id="btn-res-next", classes="search-nav-btn")

    def on_mount(self) -> None:
        self._setup_headers_tables()
        self._update_request_view("view_pretty_request")
        self._update_response_view("view_pretty_response")

    def _setup_headers_tables(self) -> None:
        req_table = self.query_one("#req-headers-table", DataTable)
        req_table.add_columns("Key", "Value")
        for k, v in parse_headers_to_list(self.req_headers_raw):
            req_table.add_row(k, v)

        res_table = self.query_one("#res-headers-table", DataTable)
        res_table.add_columns("Key", "Value")
        for k, v in parse_headers_to_list(self.res_headers_raw):
            res_table.add_row(k, v)

    def _find_all_matches(self, text: str, term: str) -> list:
        if not term: return []
        term_lower, text_lower, matches, start = term.lower(), text.lower(), [], 0
        while True:
            idx = text_lower.find(term_lower, start)
            if idx == -1: break
            row = text.count('\n', 0, idx)
            last_nl = text.rfind('\n', 0, idx)
            col = idx if last_nl == -1 else idx - last_nl - 1
            matches.append(((row, col), (row, col + len(term))))
            start = idx + len(term)
        return matches

    def _apply_search(self, is_req: bool) -> None:
        panel_key = "req" if is_req else "res"
        search_term = self.query_one(f"#input-{panel_key}-search", Input).value
        active_tab = self.query_one(f"#view-request" if is_req else "#view-response", Tabs).active
        if not active_tab: return
        lbl_count = self.query_one(f"#lbl-{panel_key}-count", Label)

        if "headers" in active_tab:
            table = self.query_one(f"#{panel_key}-headers-table", DataTable)
            table.clear()
            raw_headers = self.req_headers_raw if is_req else self.res_headers_raw
            match_count = 0
            for key, val in parse_headers_to_list(raw_headers):
                if not search_term or search_term.lower() in key.lower() or search_term.lower() in val.lower():
                    k_text, v_text = Text(key), Text(val)
                    if search_term:
                        k_text.highlight_words([search_term], "bold black on #ffd700", case_sensitive=False)
                        v_text.highlight_words([search_term], "bold black on #ffd700", case_sensitive=False)
                    table.add_row(k_text, v_text)
                    match_count += 1
            total = len(parse_headers_to_list(raw_headers))
            lbl_count.update(f"{match_count}/{total}")
            self.search_state[panel_key] = {"matches": [], "index": -1, "term": search_term}
        else:
            area = self.query_one(f"#{panel_key}-content-area", TextArea)
            matches = self._find_all_matches(area.text, search_term)
            self.search_state[panel_key].update(
                {"term": search_term, "matches": matches, "index": 0 if matches else -1}
                )
            if matches:
                self._highlight_current_match(is_req)
            else:
                area.selection = TASelection((0, 0), (0, 0))
                lbl_count.update("0/0")

    def _highlight_current_match(self, is_req: bool) -> None:
        panel_key = "req" if is_req else "res"
        state = self.search_state[panel_key]
        if state["index"] == -1 or not state["matches"]: return
        area = self.query_one(f"#{panel_key}-content-area", TextArea)
        start_pos, end_pos = state["matches"][state["index"]]
        area.selection = TASelection(start_pos, end_pos)
        area.scroll_cursor_visible()
        self.query_one(f"#lbl-{panel_key}-count", Label).update(f"{state['index'] + 1}/{len(state['matches'])}")

    def _navigate_search(self, is_req: bool, forward: bool = True) -> None:
        state = self.search_state["req" if is_req else "res"]
        if not state["matches"]: return
        state["index"] = (state["index"] + (1 if forward else -1)) % len(state["matches"])
        self._highlight_current_match(is_req)

    @on(Input.Changed, ".search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        self._apply_search(event.input.id == "input-req-search")

    @on(Input.Submitted, ".search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        self._navigate_search(event.input.id == "input-req-search", True)

    @on(Button.Pressed, "#btn-req-next")
    def req_search_next(self) -> None:
        self._navigate_search(True, True)

    @on(Button.Pressed, "#btn-req-prev")
    def req_search_prev(self) -> None:
        self._navigate_search(True, False)

    @on(Button.Pressed, "#btn-res-next")
    def res_search_next(self) -> None:
        self._navigate_search(False, True)

    @on(Button.Pressed, "#btn-res-prev")
    def res_search_prev(self) -> None:
        self._navigate_search(False, False)

    def _update_request_view(self, tab_id: str) -> None:
        req_area = self.query_one("#req-content-area", TextArea)
        req_table = self.query_one("#req-headers-table", DataTable)
        if tab_id == "view_headers_request":
            req_area.add_class("-hidden")
            req_table.remove_class("-hidden")
        else:
            req_table.add_class("-hidden")
            req_area.remove_class("-hidden")
            req_line = f"{self.method} {self.path} {self.http_version_str}"
            if tab_id == "view_pretty_request":
                body_part = format_secure_json(self.req_body)
                req_area.text = f"{req_line}\n{self.req_headers_raw}\n\n{body_part}".strip()
            elif tab_id == "view_raw_request":
                req_area.text = f"{req_line}\n{self.req_headers_raw}\n\n{self.req_body}".strip()
        self._apply_search(True)

    def _update_response_view(self, tab_id: str) -> None:
        res_area = self.query_one("#res-content-area", TextArea)
        res_table = self.query_one("#res-headers-table", DataTable)
        if tab_id == "view_headers_response":
            res_area.add_class("-hidden")
            res_table.remove_class("-hidden")
        else:
            res_table.add_class("-hidden")
            res_area.remove_class("-hidden")
            status_line = f"{self.http_version_str} {self.status}"
            if tab_id == "view_pretty_response":
                body_part = format_secure_json(self.res_body)
                res_area.text = f"{status_line}\n{self.res_headers_raw}\n\n{body_part}".strip()
            elif tab_id == "view_raw_response":
                res_area.text = f"{status_line}\n{self.res_headers_raw}\n\n{self.res_body}".strip()
        self._apply_search(False)

    @on(Tabs.TabActivated)
    def on_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tabs.id == "view-request":
            self._update_request_view(event.tab.id)
        elif event.tabs.id == "view-response":
            self._update_response_view(event.tab.id)

    def on_clickable_vertical_clicked(self, event: ClickableVertical.Clicked) -> None:
        self.query_one("#left-wrapper").remove_class("selected-panel")
        self.query_one("#right-wrapper").remove_class("selected-panel")
        event.container.add_class("selected-panel")
        self.active_panel = "left" if event.container.id == "left-wrapper" else "right"

    def action_focus_search(self) -> None:
        bar_id, input_id = ("#req-search-bar", "#input-req-search") if self.active_panel == "left" else (
        "#res-search-bar", "#input-res-search")
        search_bar, input_widget = self.query_one(bar_id, Horizontal), self.query_one(input_id, Input)
        search_bar.toggle_class("-show")
        if search_bar.has_class("-show"):
            input_widget.focus()
        else:
            input_widget.value = ""

    @on(Button.Pressed, "#btn-menu")
    def toggle_action_menu(self) -> None:
        self.query_one("#action-menu").toggle_class("-show")

    @on(Button.Pressed, "#btn-copy-url")
    def action_copy_url(self) -> None:
        if self.url:
            self.app.copy_to_clipboard(self.url)
            self.app.notify("Đã copy URL vào bộ nhớ tạm!", severity="information")
        self.query_one("#action-menu").remove_class("-show")

    @on(Button.Pressed, "#btn-copy-row")
    def action_copy_row(self) -> None:
        self.app.copy_to_clipboard(build_row_string(self.record_data))
        self.app.notify("Đã copy thông tin Row!", severity="information")
        self.query_one("#action-menu").remove_class("-show")

    @on(Button.Pressed, "#btn-copy-curl")
    def action_copy_curl(self) -> None:
        cmd = build_curl_command(self.method, self.url, self.req_headers_raw, self.req_body)
        self.app.copy_to_clipboard(cmd)
        self.app.notify("Đã copy lệnh cURL!", severity="information")
        self.query_one("#action-menu").remove_class("-show")

    @on(Button.Pressed, "#btn-close")
    def close_modal(self) -> None:
        self.app.pop_screen()

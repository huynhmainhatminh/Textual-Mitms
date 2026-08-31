# ui/app.py
import asyncio
import re
import fnmatch
from pathlib import Path
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, Footer, Header, Label, DataTable, Input, Tabs, Tab,
    SelectionList, Select
)
from textual.widgets.selection_list import Selection
from textual.widgets.data_table import RowDoesNotExist
from textual.timer import Timer
from textual import events, on, work

from .core.proxy import ProxyManager
from .core.utils import hosts_to_mitm_regex_list, unique_normalized_hosts, subtract_same_host_rules
from .http_detail_modal import HttpDetailModal
from .prompt_modal import PromptModal
from .options_modal import OptionsModal
from .tools.regexlite.screen import RegexLiteScreen


class TextualMitms(App):
    CSS_PATH = Path(__file__).with_name("styles.tcss")

    # priority=True: kiểm tra trước binding của widget đang focus (Input/DataTable)
    # cú pháp key "ctrl+s" / "ctrl+r" theo textual.binding.KeyString
    BINDINGS = [
        Binding("ctrl+s", "toggle_proxy", "Start/Stop Proxy", show=True, priority=True),
        Binding("ctrl+r", "open_regexlite", "RegexLite", show=True, priority=True),
    ]

    # MessagePump.set_timer(delay: float, ...) — delay tính bằng giây
    SEARCH_DEBOUNCE_SECONDS = 2

    ALL_COLUMNS = ["ID", "HOST", "METHOD", "URL", "STATUS CODE", "LENGTH", "IP", "COOKIES"]

    SEARCH_FIELDS = [
        ("Host", "host"),
        ("Method", "method"),
        ("URL / Path", "path"),
        ("Status Code", "status"),
        ("IP", "ip"),
        ("Cookies", "cookies"),
        ("Request Headers", "req_headers"),
        ("Request Body", "req_body"),
        ("Response Headers", "res_headers"),
        ("Response Body", "res_body"),
        ("Protocol", "protocol"),
        ("HTTP Version", "http_version"),
        ("MIME Type", "mime_category"),
    ]

    SEARCH_MODES = [
        ("Contains", "contains"),
        ("NOT Contains", "not_contains"),
        ("Equals", "equals"),
        ("NOT Equals", "not_equals"),
        ("Starts With", "starts_with"),
        ("Ends With", "ends_with"),
        ("Match Wildcard", "wildcard"),
        ("NOT Match Wildcard", "not_wildcard"),
        ("Match Regex", "regex"),
        ("NOT Match Regex", "not_regex"),
    ]

    def __init__(self, listen_host: str = "127.0.0.1", listen_port: int = 8080):
        super().__init__()
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.active_columns = self.ALL_COLUMNS.copy()
        self.HTTP_HISTORY = []
        self._records_by_key: dict[str, dict] = {}
        self.proxy = ProxyManager(self)

        self.active_filters = {
            "application-protocols": "ALL",
            "http-version": "ALL",
            "mime-types": "ALL",
            "status-codes": "ALL",
        }

        self.allowed_hosts = set()
        self.ignored_hosts = set()

        # ===== OPTIONS =====
        self.opt_capture_mode = "basic"  # "basic" | "full"
        self.opt_http2 = True
        self.opt_http3 = False
        self.opt_websocket = True
        self.opt_anticache = False
        self.opt_anticomp = False
        self.opt_ssl_insecure = False

        # stopped | starting | running | stopping
        self.proxy_phase = "stopped"

        # Timer trả về bởi MessagePump.set_timer
        self._search_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="config_1", classes="config-panel"):
            yield Label("●", id="lbl-status-icon")
            yield Label("Proxying on", id="lbl-proxy")
            yield Input(
                value=f"{self.listen_host}:{self.listen_port}",
                id="input-proxy",
            )
            yield Button("▶", id="btn-toggle-run", variant="success")
            yield Button("X", id="btn-clear-data", variant="error")
            yield Button("▼", id="btn-toggle-filter", variant="primary")
            yield Button("Allow Hosts +", id="btn-allow-hosts", variant="primary")
            yield Button("Ignore Hosts +", id="btn-ignore-hosts", variant="warning")
            yield Button("Options", id="btn-options", variant="primary")

            yield Select(self.SEARCH_FIELDS, value="path", id="search-field", allow_blank=False, compact=True)
            yield Select(self.SEARCH_MODES, value="contains", id="search-mode", allow_blank=False, compact=True)
            yield Input(placeholder="Search", id="search-input")

        with Horizontal(id="config_2"):
            yield Label("※ TRAFFIC(0)", id="nav-traffic")
            yield Tabs(Tab("ALL"), Tab("HTTP"), Tab("HTTPS"), Tab("WEBSOCKET"), id="application-protocols")
            yield Tabs(Tab("ALL"), Tab("HTTP1"), Tab("HTTP2"), Tab("HTTP3"), id="http-version")
            yield Tabs(
                Tab("ALL"), Tab("JSON"), Tab("XML"), Tab("TEXT"), Tab("HTML"), Tab("JS"),
                Tab("IMAGE"), Tab("MEDIA"), Tab("BINARY"), id="mime-types"
            )
            yield Tabs(Tab("ALL"), Tab("1xx"), Tab("2xx"), Tab("3xx"), Tab("4xx"), Tab("5xx"), id="status-codes")
            yield Button("TABLE LAYOUT", id="btn-col-config")

        with Vertical(id="config_3", classes="config-panel") as config_panel:
            config_panel.border_title = "HTTP History"
            config_panel.styles.border_title_color = "#ffd700"
            with Vertical(id="col-menu"):
                yield SelectionList[str](id="col-selector")
            yield DataTable(id="history-table", cursor_type="row", zebra_stripes=True)

        yield Footer()

    def on_mount(self) -> None:
        selector = self.query_one("#col-selector", SelectionList)
        for col in self.ALL_COLUMNS:
            selector.add_option(Selection(col, col, True))
        self.rebuild_table(self.active_columns)
        self.query_one("#history-table", DataTable).focus()

    def _get_regex_hosts(self, hosts_set: set) -> list[str]:
        return hosts_to_mitm_regex_list(hosts_set)

    # ==========================================
    # SEARCH
    # ==========================================
    def match_condition(self, text: str, query: str, mode: str) -> bool:
        if not query:
            return True
        t = str(text).lower()
        q = str(query).lower()
        try:
            if mode == "contains":
                return q in t
            if mode == "not_contains":
                return q not in t
            if mode == "equals":
                return q == t
            if mode == "not_equals":
                return q != t
            if mode == "starts_with":
                return t.startswith(q)
            if mode == "ends_with":
                return t.endswith(q)
            if mode == "wildcard":
                return fnmatch.fnmatch(t, q)
            if mode == "not_wildcard":
                return not fnmatch.fnmatch(t, q)
            if mode == "regex":
                return re.search(query, text, re.IGNORECASE) is not None
            if mode == "not_regex":
                return re.search(query, text, re.IGNORECASE) is None
        except re.error:
            return False
        return False

    def _matches_search(self, data: dict) -> bool:
        try:
            field = self.query_one("#search-field", Select).value
            mode = self.query_one("#search-mode", Select).value
            query = self.query_one("#search-input", Input).value
        except Exception:
            return True
        if not query:
            return True
        return self.match_condition(data.get(field, ""), query, mode)

    def _cancel_search_timer(self) -> None:
        if self._search_timer is not None:
            self._search_timer.stop()
            self._search_timer = None

    def _apply_search(self) -> None:
        self._search_timer = None
        self.rebuild_table(self.active_columns)

    def _schedule_search(self) -> None:
        if self._search_timer is not None:
            # Timer.reset(): "Reset the timer, so it starts from the beginning."
            self._search_timer.reset()
            return
        self._search_timer = self.set_timer(
            self.SEARCH_DEBOUNCE_SECONDS,
            self._apply_search,
            name="search-debounce",
        )

    @on(Input.Changed, "#search-input")
    def on_search_input_changed(self) -> None:
        self._schedule_search()

    @on(Input.Submitted, "#search-input")
    def on_search_input_submitted(self) -> None:
        # Enter trong Input → Input.Submitted: search ngay, không chờ debounce
        self._cancel_search_timer()
        self._apply_search()

    @on(Select.Changed, "#search-mode")
    @on(Select.Changed, "#search-field")
    def on_search_select_changed(self) -> None:
        self._cancel_search_timer()
        self._apply_search()

    # ==========================================
    # OPTIONS
    # ==========================================
    @on(Button.Pressed, "#btn-options")
    def open_options(self) -> None:
        current = {
            "capture_mode": self.opt_capture_mode,
            "http2": self.opt_http2,
            "http3": self.opt_http3,
            "websocket": self.opt_websocket,
            "anticache": self.opt_anticache,
            "anticomp": self.opt_anticomp,
            "ssl_insecure": self.opt_ssl_insecure,
        }

        def on_closed(result: dict | None) -> None:
            if result is None:
                return
            self.opt_capture_mode = result["capture_mode"]
            self.opt_http2 = result["http2"]
            self.opt_http3 = result["http3"]
            self.opt_websocket = result["websocket"]
            self.opt_anticache = result["anticache"]
            self.opt_anticomp = result["anticomp"]
            self.opt_ssl_insecure = result["ssl_insecure"]

            self.proxy.update_options(
                http2=self.opt_http2,
                http3=self.opt_http3,
                websocket=self.opt_websocket,
                ssl_insecure=self.opt_ssl_insecure,
                anticache=self.opt_anticache,
                anticomp=self.opt_anticomp,
            )

        self.push_screen(OptionsModal(current), on_closed)

    # ==========================================
    # HOST LISTS
    # ==========================================
    def _apply_host_lists_to_proxy(self) -> None:
        if not self.proxy.is_running:
            return
        self.proxy.update_options(
            allow_hosts=self._get_regex_hosts(self.allowed_hosts),
            ignore_hosts=self._get_regex_hosts(self.ignored_hosts),
        )

    @on(Button.Pressed, "#btn-allow-hosts")
    def prompt_allow_host(self) -> None:
        def update_allow_hosts(new_set: set | None) -> None:
            if new_set is None:
                return
            self.allowed_hosts = unique_normalized_hosts(new_set)
            self.ignored_hosts, removed = subtract_same_host_rules(
                self.allowed_hosts, self.ignored_hosts
            )
            msg = f"Allow List đã cập nhật. Hiện có: {len(self.allowed_hosts)} mục."
            if removed:
                msg += f" Đã gỡ khỏi Ignore: {', '.join(removed)}."
            self.notify(msg, severity="information")
            self._apply_host_lists_to_proxy()

        self.push_screen(
            PromptModal(
                "Manage Allowed Hosts",
                "example.com",
                self.allowed_hosts,
                other_hosts=self.ignored_hosts,
                other_list_name="Ignore List",
            ),
            update_allow_hosts,
        )

    @on(Button.Pressed, "#btn-ignore-hosts")
    def prompt_ignore_host(self) -> None:
        def update_ignore_hosts(new_set: set | None) -> None:
            if new_set is None:
                return
            self.ignored_hosts = unique_normalized_hosts(new_set)
            self.allowed_hosts, removed = subtract_same_host_rules(
                self.ignored_hosts, self.allowed_hosts
            )
            msg = f"Ignore List đã cập nhật. Hiện có: {len(self.ignored_hosts)} mục."
            if removed:
                msg += f" Đã gỡ khỏi Allow: {', '.join(removed)}."
            self.notify(msg, severity="warning")
            self._apply_host_lists_to_proxy()

        self.push_screen(
            PromptModal(
                "Manage Ignore Hosts",
                "example.com",
                self.ignored_hosts,
                other_hosts=self.allowed_hosts,
                other_list_name="Allow List",
            ),
            update_ignore_hosts,
        )

    # ==========================================
    # FILTERS
    # ==========================================
    @on(Tabs.TabActivated)
    def update_filters_on_tab_click(self, event: Tabs.TabActivated) -> None:
        tabs_group_id = event.tabs.id
        selected_tab_label = str(event.tab.label)
        if tabs_group_id in self.active_filters:
            self.active_filters[tabs_group_id] = selected_tab_label
        self.rebuild_table(self.active_columns)

    def _matches_filters(self, data: dict) -> bool:
        p_filter = self.active_filters.get("application-protocols", "ALL")
        v_filter = self.active_filters.get("http-version", "ALL")
        m_filter = self.active_filters.get("mime-types", "ALL")
        s_filter = self.active_filters.get("status-codes", "ALL")

        if p_filter != "ALL" and data.get("protocol") != p_filter:
            return False
        if v_filter != "ALL" and data.get("http_version") != v_filter:
            return False
        if m_filter != "ALL" and data.get("mime_category") != m_filter:
            return False
        if s_filter != "ALL" and data.get("status_category") != s_filter:
            return False
        if not self._matches_search(data):
            return False
        return True

    # ==========================================
    # PROXY CONTROL
    # ==========================================
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Textual: True chạy + hiện footer; None hiện mờ + không chạy; False ẩn + không chạy
        if action == "toggle_proxy" and self.proxy_phase == "stopping":
            return None
        return True

    def action_toggle_proxy(self) -> None:
        """Hotkey Ctrl+S: luân phiên start/stop."""
        self._toggle_proxy()

    def action_open_regexlite(self) -> None:
        """Hotkey Ctrl+R: ModalScreen RegexLite. App.push_screen."""
        self.push_screen(RegexLiteScreen())

    def _set_proxy_phase(self, phase: str) -> None:
        self.proxy_phase = phase
        self.refresh_bindings()

        button = self.query_one("#btn-toggle-run", Button)
        status_icon = self.query_one("#lbl-status-icon", Label)
        address_input = self.query_one("#input-proxy", Input)

        if phase == "stopped":
            button.remove_class("-running")
            button.label = "▶"
            button.variant = "success"
            button.disabled = False
            status_icon.remove_class("-running")
            address_input.disabled = False
        elif phase == "starting":
            button.remove_class("-running")
            button.label = "…"
            button.variant = "warning"
            button.disabled = False
            status_icon.remove_class("-running")
            address_input.disabled = True
        elif phase == "running":
            button.add_class("-running")
            button.label = "■"
            button.variant = "error"
            button.disabled = False
            status_icon.add_class("-running")
            address_input.disabled = True
        elif phase == "stopping":
            button.add_class("-running")
            button.label = "…"
            button.variant = "warning"
            button.disabled = True
            status_icon.add_class("-running")
            address_input.disabled = True

    def _toggle_proxy(self) -> None:
        if self.proxy_phase == "stopping":
            return
        if self.proxy_phase in ("running", "starting"):
            self._begin_stop_proxy()
            return
        self._begin_start_proxy()

    def _begin_start_proxy(self) -> None:
        proxy_address = self.query_one("#input-proxy", Input).value
        try:
            host, port_str = proxy_address.split(":")
            port = int(port_str)
        except ValueError:
            self.notify("Invalid proxy format (Required: HOST:PORT)", severity="error")
            return

        self._set_proxy_phase("starting")
        self.run_proxy_worker(host, port)

    def _begin_stop_proxy(self) -> None:
        self._set_proxy_phase("stopping")
        self.proxy.stop()

    def _on_proxy_started(self) -> None:
        if self.proxy_phase == "stopping":
            return
        self._set_proxy_phase("running")

    def _on_proxy_stopped(self) -> None:
        self._set_proxy_phase("stopped")

    def _on_proxy_failed(self, error: BaseException) -> None:
        self._set_proxy_phase("stopped")
        self.notify(f"Proxy startup error: {error}", severity="error")

    @work(thread=True)
    def run_proxy_worker(self, host: str, port: int) -> None:
        try:
            asyncio.run(self._run_proxy_session(host, port))
        except Exception as e:
            self.call_from_thread(self._on_proxy_failed, e)
        else:
            self.call_from_thread(self._on_proxy_stopped)

    async def _run_proxy_session(self, host: str, port: int) -> None:
        await self.proxy.start(host, port)

    def stop_proxy(self) -> None:
        self.proxy.stop()

    async def on_unmount(self) -> None:
        self.stop_proxy()

    # ==========================================
    # HISTORY
    # ==========================================
    def _traffic_label_update(self) -> None:
        self.query_one("#nav-traffic", Label).update(f"※ TRAFFIC({len(self.HTTP_HISTORY)})")

    def _formatted_row_cells(self, data: dict) -> dict[str, str]:
        method_color = "green" if data["method"] == "GET" else "yellow" if data["method"] == "POST" else "blue"
        status_color = (
            "green" if str(data["status"]).startswith("2")
            else "red" if str(data["status"]).startswith("5") or data["status"] == "ERR"
            else "orange3"
        )
        display_url = data.get("path", "")
        if len(display_url) > 60:
            display_url = display_url[:60] + "..."
        cookies_display = data.get("cookies", "")
        if len(cookies_display) > 60:
            cookies_display = cookies_display[:60] + "..."
        return {
            "ID": f"{data['id']}\n ",
            "HOST": f"[dim]{data['host']}[/]\n ",
            "METHOD": f"[bold {method_color}]{data['method']:<5}[/]\n ",
            "URL": f"{display_url}\n ",
            "STATUS CODE": f"[bold {status_color}]{data['status']}[/]\n ",
            "LENGTH": f"{data['length']}\n ",
            "IP": f"{data['ip']}\n ",
            "COOKIES": f"{cookies_display}\n ",
        }

    def _table_has_row(self, table: DataTable, row_key: str) -> bool:
        try:
            table.get_row(row_key)
            return True
        except RowDoesNotExist:
            return False

    def _sync_table_row(self, data: dict) -> None:
        table = self.query_one("#history-table", DataTable)
        row_key = data["row_key"]
        visible = self._matches_filters(data)
        in_table = self._table_has_row(table, row_key)
        if visible and in_table:
            cells = self._formatted_row_cells(data)
            for col in self.active_columns:
                table.update_cell(row_key, col, cells[col])
            return
        if visible and not in_table:
            cells = self._formatted_row_cells(data)
            table.add_row(*[cells[col] for col in self.active_columns], key=row_key)
            table.scroll_end(animate=False)
            return
        if not visible and in_table:
            table.remove_row(row_key)

    def add_proxy_record(self, data: dict) -> None:
        try:
            row_key = data.get("row_key") or data.get("flow_id")
            if not row_key:
                row_key = f"anon:{len(self.HTTP_HISTORY) + 1}"
            data["row_key"] = row_key

            existing = self._records_by_key.get(row_key)
            if existing is None:
                data["id"] = str(len(self.HTTP_HISTORY) + 1).zfill(4)
                self.HTTP_HISTORY.append(data)
                self._records_by_key[row_key] = data
                self._traffic_label_update()
                if self._matches_filters(data):
                    self._sync_table_row(data)
                return

            display_id = existing["id"]
            existing.update(data)
            existing["id"] = display_id
            existing["row_key"] = row_key
            self._sync_table_row(existing)
        except Exception as e:
            self.notify(f"Data display error: {e}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key.value
        target_record = self._records_by_key.get(row_key)
        if target_record is None:
            target_record = next((item for item in self.HTTP_HISTORY if item.get("id") == row_key), None)
        if target_record:
            self.push_screen(HttpDetailModal(target_record))

    # ==========================================
    # BUTTONS
    # ==========================================
    @on(Button.Pressed, "#btn-toggle-run")
    def toggle_run_state(self) -> None:
        self._toggle_proxy()

    @on(Button.Pressed, "#btn-toggle-filter")
    def toggle_filter_bar(self, event: Button.Pressed) -> None:
        config_2 = self.query_one("#config_2")
        config_2.toggle_class("-hidden")
        event.button.label = "▲" if config_2.has_class("-hidden") else "▼"

    @on(Button.Pressed, "#btn-clear-data")
    def clear_table_data(self) -> None:
        self.HTTP_HISTORY = []
        self._records_by_key = {}
        self.rebuild_table(self.active_columns)
        self._traffic_label_update()

    @on(Button.Pressed, "#btn-col-config")
    def toggle_column_menu(self) -> None:
        self.query_one("#col-menu").toggle_class("-show")

    @on(events.MouseDown)
    def hide_menu_on_outside_click(self, event: events.MouseDown) -> None:
        try:
            menu = self.query_one("#col-menu")
        except Exception:
            return
        if menu.has_class("-show"):
            clicked, _ = self.screen.get_widget_at(event.screen_x, event.screen_y)
            is_inside = False
            node = clicked
            while node:
                if node.id in ["col-menu", "btn-col-config"]:
                    is_inside = True
                    break
                node = node.parent
            if not is_inside:
                menu.remove_class("-show")

    @on(SelectionList.SelectedChanged, "#col-selector")
    def on_column_selection_changed(self, event: SelectionList.SelectedChanged) -> None:
        self.active_columns = [col for col in self.ALL_COLUMNS if col in event.selection_list.selected]
        self.rebuild_table(self.active_columns)

    def rebuild_table(self, active_columns: list[str]) -> None:
        table = self.query_one("#history-table", DataTable)
        table.clear(columns=True)
        if not active_columns:
            return
        for col in active_columns:
            table.add_column(col, key=col)

        for data in self.HTTP_HISTORY:
            if not self._matches_filters(data):
                continue
            cells = self._formatted_row_cells(data)
            table.add_row(
                *[cells[col] for col in active_columns],
                key=data.get("row_key") or data["id"],
            )

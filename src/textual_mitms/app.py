# ui/app.py
import asyncio
import re
import fnmatch
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, Footer, Header, Label, DataTable, Input, Tabs, Tab,
    SelectionList, Select
)
from textual.widgets.selection_list import Selection
from textual import events, on, work
from pathlib import Path

from .core.proxy import ProxyManager
from .modal import HttpDetailModal, PromptModal
from .options_modal import OptionsModal



class TextualMitms(App):
    CSS_PATH = str(Path(__file__).parent / "styles.tcss")

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

    def __init__(self):
        super().__init__()
        self.active_columns = self.ALL_COLUMNS.copy()
        self.HTTP_HISTORY = []
        self.proxy = ProxyManager(self)

        self.active_filters = {
            "application-protocols": "ALL",
            "http-version": "ALL",
            "mime-types": "ALL",
            "status-codes": "ALL"
        }

        self.allowed_hosts = set()
        self.ignored_hosts = set()

        # ===== OPTIONS =====
        self.opt_capture_mode = "basic"   # "basic" | "full"
        self.opt_http2 = True
        self.opt_http3 = False
        self.opt_websocket = True
        self.opt_anticache = False
        self.opt_anticomp = False
        self.opt_ssl_insecure = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="config_1", classes="config-panel"):
            yield Label("●", id="lbl-status-icon")
            yield Label("Proxying on", id="lbl-proxy")
            yield Input(value="127.0.0.1:8080", id="input-proxy")
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
        return [f".*{re.escape(h)}.*" for h in hosts_set]

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

    @on(Input.Changed, "#search-input")
    @on(Select.Changed, "#search-mode")
    @on(Select.Changed, "#search-field")
    def on_search_update(self) -> None:
        self.rebuild_table(self.active_columns)

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
    @on(Button.Pressed, "#btn-allow-hosts")
    def prompt_allow_host(self) -> None:
        def update_allow_hosts(new_set: set | None) -> None:
            if new_set is not None:
                self.allowed_hosts = new_set
                self.notify(f"Allow List đã cập nhật. Hiện có: {len(self.allowed_hosts)} mục.", severity="information")
                if self.proxy.is_running:
                    self.proxy.update_options(allow_hosts=self._get_regex_hosts(self.allowed_hosts))

        self.push_screen(PromptModal("Manage Allowed Hosts", "example.com", self.allowed_hosts), update_allow_hosts)

    @on(Button.Pressed, "#btn-ignore-hosts")
    def prompt_ignore_host(self) -> None:
        def update_ignore_hosts(new_set: set | None) -> None:
            if new_set is not None:
                self.ignored_hosts = new_set
                self.notify(f"Ignore List đã cập nhật. Hiện có: {len(self.ignored_hosts)} mục.", severity="warning")
                if self.proxy.is_running:
                    self.proxy.update_options(ignore_hosts=self._get_regex_hosts(self.ignored_hosts))

        self.push_screen(PromptModal("Manage Ignore Hosts", "example.com", self.ignored_hosts), update_ignore_hosts)

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
    @work(thread=True)
    def run_proxy_worker(self, host: str, port: int) -> None:
        try:
            asyncio.run(self.proxy.start(host, port))
        except Exception as e:
            self.call_from_thread(self.notify, f"Proxy startup error: {e}", severity="error")

    def stop_proxy(self) -> None:
        self.proxy.stop()

    async def on_unmount(self) -> None:
        self.stop_proxy()

    # ==========================================
    # HISTORY
    # ==========================================
    def add_proxy_record(self, data: dict) -> None:
        try:
            unique_id = str(len(self.HTTP_HISTORY) + 1).zfill(4)
            data["id"] = unique_id

            self.HTTP_HISTORY.append(data)
            self.query_one("#nav-traffic", Label).update(f"※ TRAFFIC({len(self.HTTP_HISTORY)})")

            if not self._matches_filters(data):
                return

            table = self.query_one("#history-table", DataTable)
            key_map = {
                "ID": "id", "HOST": "host", "METHOD": "method", "URL": "url",
                "STATUS CODE": "status", "LENGTH": "length", "IP": "ip", "COOKIES": "cookies"
            }

            method_color = "green" if data["method"] == "GET" else "yellow" if data["method"] == "POST" else "blue"
            status_color = (
                "green" if data["status"].startswith("2")
                else "red" if data["status"].startswith("5") or data["status"] == "ERR"
                else "orange3"
            )

            display_url = data["path"]
            if len(display_url) > 60:
                display_url = display_url[:60] + "..."

            cookies_display = data.get("cookies", "")
            if len(cookies_display) > 60:
                cookies_display = cookies_display[:60] + "..."

            formatted_data = {
                "id": f"{data['id']}\n ",
                "host": f"[dim]{data['host']}[/]\n ",
                "method": f"[bold {method_color}]{data['method']:<5}[/]\n ",
                "url": f"{display_url}\n ",
                "status": f"[bold {status_color}]{data['status']}[/]\n ",
                "length": f"{data['length']}\n ",
                "ip": f"{data['ip']}\n ",
                "cookies": f"{cookies_display}\n "
            }

            filtered_row = [formatted_data[key_map[col]] for col in self.active_columns]
            table.add_row(*filtered_row, key=data["id"])
            table.scroll_end(animate=False)
        except Exception as e:
            self.notify(f"Data display error: {e}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        target_record = next((item for item in self.HTTP_HISTORY if item["id"] == event.row_key.value), None)
        if target_record:
            self.push_screen(HttpDetailModal(target_record))

    # ==========================================
    # BUTTONS
    # ==========================================
    @on(Button.Pressed, "#btn-toggle-run")
    def toggle_run_state(self, event: Button.Pressed) -> None:
        button = event.button
        proxy_address = self.query_one("#input-proxy", Input).value
        status_icon = self.query_one("#lbl-status-icon", Label)

        if button.has_class("-running"):
            self.stop_proxy()
            button.remove_class("-running")
            button.label = "▶"
            button.variant = "success"
            status_icon.remove_class("-running")
            self.query_one("#input-proxy", Input).disabled = False
        else:
            try:
                host, port = proxy_address.split(":")
                self.query_one("#input-proxy", Input).disabled = True
                self.run_proxy_worker(host, int(port))
                button.add_class("-running")
                button.label = "■"
                button.variant = "error"
                status_icon.add_class("-running")
            except ValueError:
                self.notify("Invalid proxy format (Required: HOST:PORT)", severity="error")

    @on(Button.Pressed, "#btn-toggle-filter")
    def toggle_filter_bar(self, event: Button.Pressed) -> None:
        config_2 = self.query_one("#config_2")
        config_2.toggle_class("-hidden")
        event.button.label = "▲" if config_2.has_class("-hidden") else "▼"

    @on(Button.Pressed, "#btn-clear-data")
    def clear_table_data(self) -> None:
        self.HTTP_HISTORY = []
        self.rebuild_table(self.active_columns)
        self.query_one("#nav-traffic", Label).update("※ TRAFFIC(0)")

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
        table.add_columns(*active_columns)

        key_map = {
            "ID": "id", "HOST": "host", "METHOD": "method", "URL": "url",
            "STATUS CODE": "status", "LENGTH": "length", "IP": "ip", "COOKIES": "cookies"
        }

        for data in self.HTTP_HISTORY:
            if not self._matches_filters(data):
                continue

            method_color = "green" if data["method"] == "GET" else "yellow" if data["method"] == "POST" else "blue"
            status_color = (
                "green" if data["status"].startswith("2")
                else "red" if data["status"].startswith("5") or data["status"] == "ERR"
                else "orange3"
            )
            display_url = data["path"][:60] + "..." if len(data["path"]) > 60 else data["path"]
            cookies_display = data.get("cookies", "")
            if len(cookies_display) > 60:
                cookies_display = cookies_display[:60] + "..."

            formatted_data = {
                "id": f"{data['id']}\n ",
                "host": f"[dim]{data['host']}[/]\n ",
                "method": f"[bold {method_color}]{data['method']:<5}[/]\n ",
                "url": f"{display_url}\n ",
                "status": f"[bold {status_color}]{data['status']}[/]\n ",
                "length": f"{data['length']}\n ",
                "ip": f"{data['ip']}\n ",
                "cookies": f"{cookies_display}\n "
            }
            table.add_row(*[formatted_data[key_map[col]] for col in active_columns], key=data["id"])

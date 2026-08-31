"""RegexLite TUI — ModalScreen (nhúng vào App proxy qua Ctrl+R)."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Markdown,
    OptionList,
    RichLog,
    Select,
    Static,
    ContentSwitcher,
    Tab,
    Tabs,
    TextArea,
)
from textual.widgets.option_list import Option

try:
    from textual.widgets.text_area import Selection
except ImportError:
    from textual.document import Selection

from ..regexlite.engine import generate, test_matches
from ..regexlite.library import PRESETS
from ..regexlite.models import DEFAULT_OPTIONS, PATTERN_LABELS, Field, Formula
from ..regexlite.snippets import render_snippet

CSS_PATH = Path(__file__).with_name("regexlite.tcss")

TEN_APP = "RegexLite"
PHU_DE = "Sample text → regular expression"

PATTERN_KEYS = (
    "field_pattern",
    "field_text",
    "anything",
    "unicode",
    "charset",
    "mask",
    "list",
    "literal",
    "bytes",
    "control",
    "number",
    "integer",
    "date",
    "datetime",
    "email",
    "url",
    "country",
    "state",
    "currency",
    "creditcard",
    "national_id",
    "vat",
    "ipv4",
    "guid",
    "regex",
)

NHAN_PATTERN = {
    "field_pattern": "Pattern used by another field",
    "field_text": "Text matched by another field",
    "anything": "Match anything",
    "unicode": "Unicode characters",
    "charset": "Basic characters",
    "mask": "Character masks",
    "list": "List of literal text",
    "literal": "Literal text",
    "bytes": "Literal bytes",
    "control": "Control characters",
    "number": "Number",
    "integer": "Integer",
    "date": "Date",
    "datetime": "Date and time",
    "email": "Email address",
    "url": "URL",
    "country": "Country",
    "state": "State or province",
    "currency": "Currency",
    "creditcard": "Credit card number",
    "national_id": "National ID",
    "vat": "VAT number",
    "ipv4": "IPv4 address",
    "guid": "GUID",
    "regex": "Regular expression",
}

PATTERN_OPTS = [(NHAN_PATTERN[k], k) for k in PATTERN_KEYS]

BEGIN_OPTS = [
    ("Anywhere", "anywhere"),
    ("Start of text", "string"),
    ("Start of line", "line"),
    ("Start of word", "word"),
    ("Start of attempt", "attempt"),
]
END_OPTS = [
    ("Anywhere", "anywhere"),
    ("End of text", "string"),
    ("End of line", "line"),
    ("End of word", "word"),
    ("End of attempt", "attempt"),
]
STRICT_OPTS = [
    ("Loose — short, may match extra", "loose"),
    ("Normal — balanced", "average"),
    ("Strict — only exact values", "strict"),
]
ACTION_OPTS = [
    ("Find / extract", "find"),
    ("Replace", "replace"),
    ("Split text", "split"),
]
FLAVOR_OPTS = [
    ("Python re", "python"),
    ("JavaScript", "javascript"),
    ("PCRE / PHP / Perl", "pcre"),
    (".NET / C#", "dotnet"),
    ("Java", "java"),
]
LANG_OPTS = [
    ("Python", "python"),
    ("JavaScript", "javascript"),
    ("Java", "java"),
    ("C# / .NET", "csharp"),
]
GROUP_OPTS = [
    ("Numbered groups  ( )", "numbered"),
    ("Named groups  (?P<name>)", "named"),
]
DATE_OPTS = [
    ("YYYY-MM-DD", "ymd-dash"),
    ("YYYY/MM/DD", "ymd-slash"),
    ("DD/MM/YYYY", "dmy-slash"),
    ("MM/DD/YYYY", "mdy-slash"),
    ("DD.MM.YYYY", "dmy-dot"),
    ("YYYYMMDD", "yyyymmdd"),
]
BASE_OPTS = [
    ("Decimal", "dec"),
    ("Hex", "hex"),
    ("Octal", "oct"),
    ("Binary", "bin"),
]
CHARSET_OPTS = [
    ("Digits 0-9", "digits"),
    ("Letters A-Z a-z", "letters"),
    ("Uppercase A-Z", "upper"),
    ("Lowercase a-z", "lower"),
    ("Word (letter, digit, _)", "word"),
    ("Whitespace", "whitespace"),
    ("Hex 0-9 A-F", "hex"),
    ("Custom", "custom"),
]
CONTROL_OPTS = [
    ("Tab \\t", "tab"),
    ("Line feed \\n", "lf"),
    ("Carriage return \\r", "cr"),
    ("CRLF \\r\\n", "crlf"),
    ("Any control \\x00-\\x1F", "any"),
]
UNICODE_OPTS = [
    ("Letter", "letter"),
    ("Digit", "digit"),
    ("Word character", "word"),
    ("Non-ASCII", "any"),
]
TIME_OPTS = [
    ("Date only", "none"),
    ("Date + HH:MM", "hm"),
    ("Date + HH:MM:SS", "hms"),
]
UNTIL_OPTS = [
    ("Until whitespace", "whitespace"),
    ("Until these characters", "delimiter"),
    ("Until this phrase", "stop_string"),
    ("Until end of line", "newline"),
    ("Until end of text", "end"),
    ("Until punctuation  . , ; : ! ?", "punct"),
    ("Until a digit 0-9", "digit"),
    ("Until a letter", "letter"),
    ("Until a bracket  ) ] } >", "bracket"),
    ("Until a quote  ' \"", "quote"),
    ("Anything except a new line", "not_newline"),
]

STAT_CHUA_SINH = "No regex yet."
MSG_CHON_PRESET = "Pick a sample first."
MSG_THEM_FIELD = "Added field #{fid}"
MSG_CHUA_CHON_FIELD = "No field is selected."
MSG_CHUA_BOI = "Select some text in Samples first."
MSG_MARK = "Marked #{fid} {kind}"
MSG_CHUA_REGEX = "There is no regex to copy yet."
MSG_DA_COPY = "Regex copied."
MSG_DA_LUU = "Saved {path}"
MSG_KHONG_THAY_FILE = "No formula.json in this folder."
MSG_LOI_DOC = "Could not read file: {exc}"
MSG_DA_NAP = "Loaded {path}"
MSG_PRESET = "Sample: {name}"
MSG_KHONG_TEST = "Cannot run a test yet."
MSG_PASTE_OK = "Pasted into Samples."
MSG_PASTE_EMPTY = "Clipboard is empty. Copy text first, or focus Samples and press Ctrl+V."
MSG_SAMPLES_CLEARED = "Samples cleared."

HELP_MD = """
# RegexLite

Build a regular expression by stacking **fields**. You do not write regex by hand.

## Steps

1. Paste text in **Samples**.
2. Select a piece → **F2 Mark** (detects email, date, number…).
3. Or **Ctrl+N** to add a field and pick a type on **Match**.
4. **F5 Build** shows the regex. **F7 Try** runs it on your sample.

## Keys

- `F2` Mark · `Ctrl+N` New field · `Ctrl+D` Delete
- `F5` Build · `F6` Copy · `F7` Try
- `Ctrl+Shift+S` Save · `Ctrl+O` Open
- `Esc` / `Ctrl+Q` Close (không tắt proxy app)
"""

PANEL_BY_PATTERN = {
    "literal": "opts-literal",
    "list": "opts-list",
    "integer": "opts-integer",
    "number": "opts-number",
    "date": "opts-date",
    "email": "opts-email",
    "url": "opts-url",
    "ipv4": "opts-ipv4",
    "guid": "opts-guid",
    "charset": "opts-charset",
    "anything": "opts-anything",
    "bytes": "opts-bytes",
    "control": "opts-control",
    "mask": "opts-mask",
    "unicode": "opts-unicode",
    "datetime": "opts-datetime",
    "regex": "opts-regex",
    "creditcard": "opts-creditcard",
    "field_pattern": "opts-field-pattern",
    "field_text": "opts-field-text",
    "country": "opts-country",
    "state": "opts-state",
    "currency": "opts-currency",
    "national_id": "opts-nid",
    "vat": "opts-vat",
}


class RegexLiteScreen(ModalScreen[None]):
    """RegexLite nhúng. Đóng bằng dismiss() — không gọi App.exit()."""

    CSS_PATH = CSS_PATH

    BINDINGS = [
        Binding("escape", "close_regexlite", "Close", show=True),
    ]

    def __init__(self, initial_samples: str = "") -> None:
        super().__init__()
        self.formula = Formula(fields=[])
        if initial_samples:
            self.formula.samples = initial_samples
        self._syncing = False
        self._selected_fid: int | None = None
        self._last_result_regex = ""
        self._search_hits: list[tuple[tuple[int, int], tuple[int, int]]] = []
        self._search_idx = -1

    def action_close_regexlite(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-close-modal")
    def close_modal(self) -> None:
        # Cùng handler CurlConverterModal.close_modal
        self.app.pop_screen()

    def compose(self) -> ComposeResult:
        with Vertical(id="regexlite-dialog") as dialog:
            dialog.border_title = "REGEXLITE"
            dialog.styles.border_title_align = "center"
            with Horizontal(classes="modal-header"):
                yield Static("", classes="spacer")
                yield Button("X", id="btn-close-modal")
            with Horizontal(id="regexlite-body"):
                with Vertical(id="layout_1"):
                    with Vertical(id="fields-box") as fields:
                        fields.border_title = "FIELDS"
                        with Horizontal(id="sidebar-actions"):
                            yield Button("NEW", id="btn-add", variant="success")
                            yield Button("MARK", id="btn-mark", variant="primary")
                            yield Button("DELETE", id="btn-del", variant="error")
                            yield Button("CLEAR", id="btn-clear", variant="warning")
                        yield VerticalScroll(id="field-list")
                    with Vertical(id="test-box"):
                        with Horizontal():
                            yield Select(GROUP_OPTS, id="sel-group", allow_blank=False, value="numbered", compact=True)
                            yield Select(FLAVOR_OPTS, id="sel-flavor", allow_blank=False, value="python", compact=True)
                            yield Button("COPY", id="btn-copy", variant="primary")
                        yield Static(STAT_CHUA_SINH, id="test-stats")
                        with Horizontal():
                            yield Static("", id="regex-out")
                        yield RichLog(id="test-view", highlight=True, markup=True)

                with Vertical(id="layout_2"):
                    yield Tabs(
                        Tab("SAMPLES", id="samples"),
                        Tab("MATCH", id="match"),
                        Tab("ACTION", id="action"),
                        Tab("CODE", id="code"),
                        Tab("LIBRARY", id="library"),
                        Tab("HELP", id="help"),
                        id="layout_tabs",
                    )
                    with ContentSwitcher(initial="samples", id="switcher"):
                        with Vertical(id="samples"):
                            with Horizontal(id="samples-actions"):
                                yield Button("PASTE", id="btn-paste", variant="primary")
                                yield Button("BUILD", id="btn-samples-build", variant="success")
                                yield Button("CLEAR", id="btn-samples-clear", variant="warning")
                                yield Input(placeholder="Search", id="search-input")
                                yield Static("0/0", id="search-count")
                                yield Button("↑", id="btn-search-prev")
                                yield Button("↓", id="btn-search-next")
                            yield TextArea(
                                self.formula.samples,
                                id="samples-text",
                                show_line_numbers=True,
                            )
                        with VerticalScroll(id="match"):
                            with Horizontal(id="match-selects"):
                                yield Select(
                                    PATTERN_OPTS, id="sel-pattern", prompt="Field Type", value="literal", compact=True
                                )
                                yield Select(
                                    BEGIN_OPTS, id="sel-begin", prompt="Begin regex match at", value="anywhere",
                                    compact=True,
                                )
                                yield Select(
                                    END_OPTS, id="sel-end", prompt="End regex match at", value="anywhere", compact=True
                                )
                                yield Select(
                                    STRICT_OPTS, id="sel-strict", prompt="Field validation mode", value="average",
                                    compact=True,
                                )
                            with Horizontal(id="match-repeats"):
                                yield Label("Group name : ", classes="match-lab")
                                yield Input(placeholder="order_id", id="inp-name")
                                yield Label("Repeat min : ", classes="match-lab")
                                yield Input(value="1", id="inp-rmin", placeholder="Repeat min")
                                yield Label("Repeat max : ", classes="match-lab")
                                yield Input(value="1", id="inp-rmax", placeholder="Repeat max")
                                yield Button("Save as a group", id="chk-capture", classes="flag-box -on")
                                yield Button("Optional", id="chk-optional", classes="flag-box")
                            with Vertical(id="options-box") as type_options:
                                type_options.border_subtitle = "TYPE OPTIONS"
                                with Vertical(id="opts-literal", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Fixed text")
                                        yield Input(id="opt-text")
                                with Vertical(id="opts-list", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("One value per line")
                                    yield TextArea("", id="opt-items")
                                with Vertical(id="opts-integer", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Minimum")
                                        yield Input("0", id="opt-min")
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Maximum")
                                        yield Input("99", id="opt-max")
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Number base")
                                        yield Select(BASE_OPTS, id="opt-base", value="dec", compact=True)
                                with Vertical(id="opts-number", classes="opt-panel"):
                                    yield Checkbox("Allow + or -", value=True, id="opt-sign")
                                    yield Checkbox("Allow a decimal point", value=True, id="opt-dec")
                                    yield Checkbox("Allow thousands comma", value=False, id="opt-grp")
                                    yield Checkbox("Allow exponent e/E", value=False, id="opt-exp")
                                with Vertical(id="opts-date", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Date format")
                                        yield Select(DATE_OPTS, id="opt-date", value="ymd-dash", compact=True)
                                with Vertical(id="opts-email", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Domains")
                                        yield Input(placeholder="shop.vn;example.com", id="opt-domains")
                                with Vertical(id="opts-url", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Schemes")
                                        yield Input("http;https", id="opt-schemes")
                                with Vertical(id="opts-ipv4", classes="opt-panel"):
                                    yield Static("No extra boxes. Use Strict to reject fake IPs.", classes="muted")
                                with Vertical(id="opts-guid", classes="opt-panel"):
                                    yield Checkbox("Use hyphens", value=True, id="opt-hyphens")
                                    yield Checkbox("Use { } braces", value=False, id="opt-braces")
                                with Vertical(id="opts-charset", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Preset")
                                        yield Select(CHARSET_OPTS, id="opt-preset", value="digits", compact=True)
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Custom")
                                        yield Input(id="opt-custom")
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Min length")
                                        yield Input("1", id="opt-cmin")
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Max length")
                                        yield Input("64", id="opt-cmax")
                                with Vertical(id="opts-anything", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Stop when")
                                        yield Select(UNTIL_OPTS, id="opt-until", value="whitespace", compact=True)
                                    with Horizontal(id="row-delim", classes="opt-row"):
                                        yield Label("Stop characters")
                                        yield Input(id="opt-delim")
                                    with Horizontal(id="row-stop", classes="opt-row"):
                                        yield Label("Stop phrase")
                                        yield Input(id="opt-stop")
                                with Vertical(id="opts-bytes", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Hex bytes")
                                        yield Input(placeholder="DE AD BE EF", id="opt-hex")
                                with Vertical(id="opts-control", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Control")
                                        yield Select(CONTROL_OPTS, id="opt-control", value="tab", compact=True)
                                with Vertical(id="opts-mask", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Mask")
                                        yield Input(placeholder="###-AA-??", id="opt-mask")
                                with Vertical(id="opts-unicode", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Set")
                                        yield Select(UNICODE_OPTS, id="opt-unicode", value="letter", compact=True)
                                with Vertical(id="opts-datetime", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Date format")
                                        yield Select(DATE_OPTS, id="opt-dt-date", value="ymd-dash", compact=True)
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Time")
                                        yield Select(TIME_OPTS, id="opt-dt-time", value="hms", compact=True)
                                with Vertical(id="opts-regex", classes="opt-panel"):
                                    yield TextArea("", id="opt-regex")
                                with Vertical(id="opts-creditcard", classes="opt-panel"):
                                    yield Checkbox("Allow spaces / dashes", value=True, id="opt-cc-spaces")
                                with Vertical(id="opts-field-pattern", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Source field")
                                        yield Select([("(none)", "")], id="opt-src-pattern", compact=True)
                                with Vertical(id="opts-field-text", classes="opt-panel"):
                                    with Horizontal(classes="opt-row"):
                                        yield Label("Source field")
                                        yield Select([("(none)", "")], id="opt-src-text", compact=True)
                                with Vertical(id="opts-country", classes="opt-panel"):
                                    yield TextArea("", id="opt-country")
                                with Vertical(id="opts-state", classes="opt-panel"):
                                    yield TextArea("", id="opt-state")
                                with Vertical(id="opts-currency", classes="opt-panel"):
                                    yield TextArea("", id="opt-currency")
                                with Vertical(id="opts-nid", classes="opt-panel"):
                                    yield TextArea("", id="opt-nid")
                                with Vertical(id="opts-vat", classes="opt-panel"):
                                    yield TextArea("", id="opt-vat")
                        with VerticalScroll(id="action"):
                            with Horizontal(classes="opt-row"):
                                yield Label("What to do with the regex")
                                yield Select(ACTION_OPTS, id="sel-action", value="find", compact=True)
                            with Horizontal(classes="opt-row"):
                                yield Label("Replace with")
                                yield Input("$1", id="inp-repl")
                            yield Checkbox("Ignore uppercase / lowercase", value=False, id="chk-flag-i")
                            yield Checkbox("Multi-line (^ $ on each line)", value=False, id="chk-flag-m")
                            yield Checkbox("Dot also matches new lines", value=False, id="chk-flag-s")
                        with Vertical(id="code"):
                            with Horizontal(classes="opt-row"):
                                yield Label("Code language")
                                yield Select(LANG_OPTS, id="sel-lang", value="python", compact=True)
                            yield TextArea("", id="snippet-out", read_only=True)
                        with Vertical(id="library"):
                            yield Static("Pick a sample, then click Load.", classes="muted")
                            yield OptionList(id="lib-list")
                            yield Static("", id="lib-info")
                            yield Button("Load this sample", id="btn-load-preset", variant="primary")
                        with Vertical(id="help"):
                            yield Markdown(HELP_MD, id="help-md")

    def on_mount(self) -> None:
        ol = self.query_one("#lib-list", OptionList)
        for name in PRESETS:
            ol.add_option(Option(name, id=name))
        self._write_global_controls()
        self._rebuild_field_list()
        self._write_field_controls()
        self._show_option_panel()

    def _goto_tab(self, tab_id: str) -> None:
        self.query_one("#layout_tabs", Tabs).active = tab_id
        self.query_one("#switcher", ContentSwitcher).current = tab_id

    @on(Tabs.TabActivated, "#layout_tabs")
    def _on_layout_tab(self, event: Tabs.TabActivated) -> None:
        if event.tab and event.tab.id:
            self.query_one("#switcher", ContentSwitcher).current = event.tab.id

    def _selected_field(self) -> Field | None:
        if self._selected_fid is None:
            return None
        return self.formula.field_by_id(self._selected_fid)

    def _rebuild_field_list(self, keep: int | None = None) -> None:
        if keep is not None:
            self._selected_fid = keep
        box = self.query_one("#field-list", VerticalScroll)
        box.remove_children()
        for fld in self.formula.fields:
            btn = Button(fld.label(), classes="field-item")
            btn.fid = fld.fid  # type: ignore[attr-defined]
            if fld.fid == self._selected_fid:
                btn.add_class("-on")
            box.mount(btn)

    def _show_option_panel(self) -> None:
        fld = self._selected_field()
        want = PANEL_BY_PATTERN.get(fld.pattern) if fld else None
        for panel in self.query("#options-box .opt-panel"):
            panel.display = panel.id == want

    def _toggle_on(self, selector: str) -> bool:
        return self.query_one(selector, Button).has_class("-on")

    def _set_toggle(self, selector: str, on: bool) -> None:
        self.query_one(selector, Button).set_class(on, "-on")

    def _write_global_controls(self) -> None:
        self._syncing = True
        try:
            self.query_one("#sel-begin", Select).value = self.formula.begin
            self.query_one("#sel-end", Select).value = self.formula.end
            self.query_one("#sel-strict", Select).value = self.formula.strictness
            self.query_one("#sel-action", Select).value = self.formula.action
            self.query_one("#sel-flavor", Select).value = self.formula.flavor
            self.query_one("#sel-group", Select).value = self.formula.group_style
            self.query_one("#inp-repl", Input).value = self.formula.replacement
            self.query_one("#chk-flag-i", Checkbox).value = self.formula.flags_ignorecase
            self.query_one("#chk-flag-m", Checkbox).value = self.formula.flags_multiline
            self.query_one("#chk-flag-s", Checkbox).value = self.formula.flags_dotall
            self.query_one("#samples-text", TextArea).text = self.formula.samples
        finally:
            self._syncing = False

    def _read_global_controls(self) -> None:
        self.formula.begin = self.query_one("#sel-begin", Select).value  # type: ignore[assignment]
        self.formula.end = self.query_one("#sel-end", Select).value  # type: ignore[assignment]
        self.formula.strictness = self.query_one("#sel-strict", Select).value  # type: ignore[assignment]
        self.formula.action = self.query_one("#sel-action", Select).value  # type: ignore[assignment]
        self.formula.flavor = self.query_one("#sel-flavor", Select).value  # type: ignore[assignment]
        self.formula.group_style = self.query_one("#sel-group", Select).value  # type: ignore[assignment]
        self.formula.replacement = self.query_one("#inp-repl", Input).value
        self.formula.flags_ignorecase = self.query_one("#chk-flag-i", Checkbox).value
        self.formula.flags_multiline = self.query_one("#chk-flag-m", Checkbox).value
        self.formula.flags_dotall = self.query_one("#chk-flag-s", Checkbox).value
        self.formula.samples = self.query_one("#samples-text", TextArea).text

    def _write_field_controls(self) -> None:
        fld = self._selected_field()
        self._syncing = True
        try:
            if fld is None:
                return
            self.query_one("#sel-pattern", Select).value = fld.pattern
            self.query_one("#inp-name", Input).value = fld.name
            self.query_one("#inp-rmin", Input).value = str(fld.repeat_min)
            self.query_one("#inp-rmax", Input).value = str(fld.repeat_max)
            self._set_toggle("#chk-capture", fld.capture)
            self._set_toggle("#chk-optional", fld.optional)
            self._show_option_panel()
            self._write_options_from(fld)
        finally:
            self._syncing = False

    def _read_field_controls(self) -> None:
        fld = self._selected_field()
        if fld is None:
            return
        try:
            fld.name = self.query_one("#inp-name", Input).value or fld.name
            fld.repeat_min = int(self.query_one("#inp-rmin", Input).value or 1)
            fld.repeat_max = int(self.query_one("#inp-rmax", Input).value or 1)
        except ValueError:
            pass
        fld.capture = self._toggle_on("#chk-capture")
        fld.optional = self._toggle_on("#chk-optional")
        self._read_options_into(fld)

    def _write_options_from(self, fld: Field) -> None:
        opts = fld.options
        p = fld.pattern
        self._syncing = True
        try:
            if p == "literal":
                self.query_one("#opt-text", Input).value = str(opts.get("text", ""))
            elif p == "list":
                self.query_one("#opt-items", TextArea).text = str(opts.get("items", ""))
            elif p == "integer":
                self.query_one("#opt-min", Input).value = str(opts.get("minimum", "0"))
                self.query_one("#opt-max", Input).value = str(opts.get("maximum", "99"))
                self.query_one("#opt-base", Select).value = opts.get("base", "dec")
            elif p == "number":
                self.query_one("#opt-sign", Checkbox).value = bool(opts.get("allow_sign", True))
                self.query_one("#opt-dec", Checkbox).value = bool(opts.get("allow_decimal", True))
                self.query_one("#opt-grp", Checkbox).value = bool(opts.get("allow_grouping", False))
                self.query_one("#opt-exp", Checkbox).value = bool(opts.get("allow_exponent", False))
            elif p == "date":
                self.query_one("#opt-date", Select).value = opts.get("format", "ymd-dash")
            elif p == "email":
                self.query_one("#opt-domains", Input).value = str(opts.get("domains", ""))
            elif p == "url":
                self.query_one("#opt-schemes", Input).value = str(opts.get("schemes", "http;https"))
            elif p == "guid":
                self.query_one("#opt-hyphens", Checkbox).value = bool(opts.get("hyphens", True))
                self.query_one("#opt-braces", Checkbox).value = bool(opts.get("braces", False))
            elif p == "charset":
                self.query_one("#opt-preset", Select).value = opts.get("preset", "digits")
                self.query_one("#opt-custom", Input).value = str(opts.get("custom", ""))
                self.query_one("#opt-cmin", Input).value = str(opts.get("min_len", "1"))
                self.query_one("#opt-cmax", Input).value = str(opts.get("max_len", "64"))
            elif p == "anything":
                self.query_one("#opt-until", Select).value = opts.get("until", "whitespace")
                self.query_one("#opt-delim", Input).value = str(opts.get("delimiter", ""))
                self.query_one("#opt-stop", Input).value = str(opts.get("stop_string", ""))
                self._sync_anything_rows()
            elif p == "bytes":
                self.query_one("#opt-hex", Input).value = str(opts.get("hex", ""))
            elif p == "control":
                self.query_one("#opt-control", Select).value = opts.get("which", "tab")
            elif p == "mask":
                self.query_one("#opt-mask", Input).value = str(opts.get("mask", ""))
            elif p == "unicode":
                self.query_one("#opt-unicode", Select).value = opts.get("set", "letter")
            elif p == "datetime":
                self.query_one("#opt-dt-date", Select).value = opts.get("format", "ymd-dash")
                self.query_one("#opt-dt-time", Select).value = opts.get("time", "hms")
            elif p == "regex":
                self.query_one("#opt-regex", TextArea).text = str(opts.get("pattern", ""))
            elif p == "creditcard":
                self.query_one("#opt-cc-spaces", Checkbox).value = bool(opts.get("spaces", True))
            elif p == "field_pattern":
                self._fill_field_select("#opt-src-pattern", str(opts.get("source", "")))
            elif p == "field_text":
                self._fill_field_select("#opt-src-text", str(opts.get("source", "")))
            elif p == "country":
                self.query_one("#opt-country", TextArea).text = str(opts.get("items", ""))
            elif p == "state":
                self.query_one("#opt-state", TextArea).text = str(opts.get("items", ""))
            elif p == "currency":
                self.query_one("#opt-currency", TextArea).text = str(opts.get("items", ""))
            elif p == "national_id":
                self.query_one("#opt-nid", TextArea).text = str(opts.get("items", ""))
            elif p == "vat":
                self.query_one("#opt-vat", TextArea).text = str(opts.get("items", ""))
        finally:
            self._syncing = False

    def _read_options_into(self, fld: Field) -> None:
        def _val(wid: str, default=None):
            try:
                w = self.query_one("#" + wid)
            except Exception:
                return default
            if isinstance(w, Input):
                return w.value
            if isinstance(w, TextArea):
                return w.text
            if isinstance(w, Checkbox):
                return w.value
            if isinstance(w, Select):
                return w.value
            return default

        p = fld.pattern
        o = fld.options
        if p == "literal":
            o["text"] = _val("opt-text", o.get("text", ""))
        elif p == "list":
            o["items"] = _val("opt-items", o.get("items", ""))
        elif p == "integer":
            o["minimum"] = _val("opt-min", o.get("minimum", "0"))
            o["maximum"] = _val("opt-max", o.get("maximum", "99"))
            o["base"] = _val("opt-base", o.get("base", "dec"))
        elif p == "number":
            o["allow_sign"] = bool(_val("opt-sign", True))
            o["allow_decimal"] = bool(_val("opt-dec", True))
            o["allow_grouping"] = bool(_val("opt-grp", False))
            o["allow_exponent"] = bool(_val("opt-exp", False))
        elif p == "date":
            o["format"] = _val("opt-date", "ymd-dash")
        elif p == "email":
            o["domains"] = _val("opt-domains", "")
        elif p == "url":
            o["schemes"] = _val("opt-schemes", "http;https")
        elif p == "guid":
            o["hyphens"] = bool(_val("opt-hyphens", True))
            o["braces"] = bool(_val("opt-braces", False))
        elif p == "charset":
            o["preset"] = _val("opt-preset", "digits")
            o["custom"] = _val("opt-custom", "")
            o["min_len"] = _val("opt-cmin", "1")
            o["max_len"] = _val("opt-cmax", "64")
        elif p == "anything":
            o["until"] = _val("opt-until", "whitespace")
            o["delimiter"] = _val("opt-delim", "")
            o["stop_string"] = _val("opt-stop", "")
        elif p == "bytes":
            o["hex"] = _val("opt-hex", "")
        elif p == "control":
            o["which"] = _val("opt-control", "tab")
        elif p == "mask":
            o["mask"] = _val("opt-mask", "")
        elif p == "unicode":
            o["set"] = _val("opt-unicode", "letter")
        elif p == "datetime":
            o["format"] = _val("opt-dt-date", "ymd-dash")
            o["time"] = _val("opt-dt-time", "hms")
        elif p == "regex":
            o["pattern"] = _val("opt-regex", "")
        elif p == "creditcard":
            o["spaces"] = bool(_val("opt-cc-spaces", True))
        elif p == "field_pattern":
            o["source"] = _val("opt-src-pattern", "")
        elif p == "field_text":
            o["source"] = _val("opt-src-text", "")
        elif p in ("country", "state", "currency", "national_id", "vat"):
            ids = {
                "country": "opt-country",
                "state": "opt-state",
                "currency": "opt-currency",
                "national_id": "opt-nid",
                "vat": "opt-vat",
            }
            o["items"] = _val(ids[p], o.get("items", ""))

    def _sync_anything_rows(self) -> None:
        try:
            until = self.query_one("#opt-until", Select).value
        except Exception:
            return
        try:
            self.query_one("#row-delim").display = until == "delimiter"
            self.query_one("#row-stop").display = until == "stop_string"
        except Exception:
            pass

    def _fill_field_select(self, selector: str, current: str) -> None:
        sel = self.query_one(selector, Select)
        pairs = [("(none)", "")]
        for f in self.formula.fields:
            if self._selected_fid is not None and f.fid == self._selected_fid:
                continue
            pairs.append((f"#{f.fid} {f.name}", str(f.fid)))
        wanted = current if any(v == current for _, v in pairs) else ""
        sel.set_options(pairs)
        sel.value = wanted

    @on(Select.Changed, "#opt-until")
    def _until_changed(self, event: Select.Changed) -> None:
        if self._syncing:
            return
        fld = self._selected_field()
        if fld is None or fld.pattern != "anything":
            return
        if event.value in (None, Select.BLANK):
            return
        fld.options["until"] = event.value
        self._sync_anything_rows()

    @on(Button.Pressed, ".field-item")
    def _pick_field(self, event: Button.Pressed) -> None:
        self._read_field_controls()
        fid = getattr(event.button, "fid", None)
        if fid is None:
            return
        self._selected_fid = int(fid)
        box = self.query_one("#field-list", VerticalScroll)
        for child in box.children:
            on_ = getattr(child, "fid", None) == self._selected_fid
            child.set_class(on_, "-on")
        self._write_field_controls()
        self._goto_tab("match")

    @on(Select.Changed, "#sel-pattern")
    def _pattern_changed(self, event: Select.Changed) -> None:
        if self._syncing:
            return
        fld = self._selected_field()
        if fld is None:
            return
        new_p = event.value
        if new_p == fld.pattern:
            return
        fld.pattern = new_p  # type: ignore[assignment]
        fld.options = dict(DEFAULT_OPTIONS.get(new_p, {}))
        self._rebuild_field_list(keep=fld.fid)
        self._show_option_panel()

    @on(Button.Pressed, "#btn-add")
    def _btn_add(self) -> None:
        self.action_add_field()

    @on(Button.Pressed, "#btn-del")
    def _btn_del(self) -> None:
        self.action_delete_field()

    @on(Button.Pressed, "#btn-mark")
    def _btn_mark(self) -> None:
        self.action_mark_selection()

    @on(Button.Pressed, "#btn-samples-build")
    def _btn_samples_build(self) -> None:
        self.action_generate()

    @on(Button.Pressed, "#btn-paste")
    def _btn_paste(self) -> None:
        text = self._clipboard_text()
        if not text:
            self.notify(MSG_PASTE_EMPTY, severity="warning")
            return
        area = self.query_one("#samples-text", TextArea)
        area.text = text
        self.formula.samples = text
        self._refresh_search()
        self.notify(MSG_PASTE_OK)

    @on(Button.Pressed, "#btn-samples-clear")
    def _btn_samples_clear(self) -> None:
        area = self.query_one("#samples-text", TextArea)
        area.text = ""
        self.formula.samples = ""
        self._refresh_search()
        self.notify(MSG_SAMPLES_CLEARED)

    def _offset_to_loc(self, text: str, offset: int) -> tuple[int, int]:
        row = 0
        col = offset
        for line in text.splitlines(keepends=True):
            if col < len(line):
                return row, col
            col -= len(line)
            row += 1
        return row, max(col, 0)

    def _refresh_search(self) -> None:
        needle = self.query_one("#search-input", Input).value
        area = self.query_one("#samples-text", TextArea)
        hay = area.text
        hits: list[tuple[tuple[int, int], tuple[int, int]]] = []
        if needle:
            start = 0
            while True:
                found = hay.find(needle, start)
                if found < 0:
                    break
                hits.append(
                    (
                        self._offset_to_loc(hay, found),
                        self._offset_to_loc(hay, found + len(needle)),
                    )
                )
                start = found + 1
        self._search_hits = hits
        if not hits:
            self._search_idx = -1
        elif self._search_idx < 0 or self._search_idx >= len(hits):
            self._search_idx = 0
        self._show_search_hit()

    def _show_search_hit(self) -> None:
        count = self.query_one("#search-count", Static)
        hits = self._search_hits
        if not hits:
            count.update("0/0")
            return
        idx = self._search_idx
        count.update(f"{idx + 1}/{len(hits)}")
        start, end = hits[idx]
        area = self.query_one("#samples-text", TextArea)
        area.selection = Selection(start, end)
        try:
            area.scroll_cursor_visible(animate=False)
        except TypeError:
            area.scroll_cursor_visible()

    def _search_step(self, delta: int) -> None:
        self._refresh_search()
        if not self._search_hits:
            return
        self._search_idx = (self._search_idx + delta) % len(self._search_hits)
        self._show_search_hit()

    @on(Input.Changed, "#search-input")
    def _search_changed(self) -> None:
        if self._syncing:
            return
        self._search_idx = 0
        self._refresh_search()

    @on(Input.Submitted, "#search-input")
    def _search_submitted(self) -> None:
        self._search_step(1)

    @on(Button.Pressed, "#btn-search-prev")
    def _btn_search_prev(self) -> None:
        self._search_step(-1)

    @on(Button.Pressed, "#btn-search-next")
    def _btn_search_next(self) -> None:
        self._search_step(1)

    @on(Button.Pressed, "#btn-copy")
    def _btn_copy(self) -> None:
        self.action_copy_regex()

    @on(Button.Pressed, "#btn-clear")
    def _btn_clear(self) -> None:
        self.action_clear_fields()

    @on(Button.Pressed, "#btn-load-preset")
    def _btn_preset(self) -> None:
        ol = self.query_one("#lib-list", OptionList)
        opt = ol.get_option_at_index(ol.highlighted) if ol.highlighted is not None else None
        if opt is None or opt.id is None:
            self.notify(MSG_CHON_PRESET, severity="warning")
            return
        self._load_preset(opt.id)

    @on(OptionList.OptionSelected, "#lib-list")
    def _lib_pick(self, event: OptionList.OptionSelected) -> None:
        name = event.option.id
        if not name or name not in PRESETS:
            return
        info = self.query_one("#lib-info", Static)
        formula = PRESETS[name]
        info.update(f"{name}\n{len(formula.fields)} field(s) · strictness={formula.strictness}")

    @on(Select.Changed, "#sel-lang")
    def _lang_changed(self) -> None:
        self._refresh_snippet()

    @on(Select.Changed, "#sel-flavor")
    def _flavor_changed(self) -> None:
        if not self._syncing:
            self.action_generate()

    @on(Select.Changed, "#sel-group")
    def _group_style_changed(self) -> None:
        if not self._syncing:
            self.action_generate()

    @on(Button.Pressed, "#chk-capture")
    def _toggle_capture(self) -> None:
        if self._syncing:
            return
        self._set_toggle("#chk-capture", not self._toggle_on("#chk-capture"))

    @on(Button.Pressed, "#chk-optional")
    def _toggle_optional(self) -> None:
        if self._syncing:
            return
        self._set_toggle("#chk-optional", not self._toggle_on("#chk-optional"))

    def action_show_help(self) -> None:
        self._goto_tab("help")

    def action_clear_fields(self) -> None:
        self.formula.fields = []
        self._selected_fid = None
        self._rebuild_field_list()
        self._write_field_controls()
        self.action_generate()

    def action_add_field(self) -> None:
        fid = self.formula.next_id()
        fld = Field(fid=fid, pattern="literal", options=dict(DEFAULT_OPTIONS["literal"]))
        self.formula.fields.append(fld)
        self._selected_fid = fid
        self._rebuild_field_list(keep=fid)
        self._write_field_controls()
        self.notify(MSG_THEM_FIELD.format(fid=fid))

    def action_delete_field(self) -> None:
        if self._selected_fid is None:
            self.notify(MSG_CHUA_CHON_FIELD, severity="warning")
            return
        self.formula.fields = [f for f in self.formula.fields if f.fid != self._selected_fid]
        self._selected_fid = self.formula.fields[-1].fid if self.formula.fields else None
        self._rebuild_field_list()
        self._write_field_controls()

    def action_mark_selection(self) -> None:
        from ..regexlite.patterns import detect_pattern

        area = self.query_one("#samples-text", TextArea)
        text = area.selected_text.strip()
        if not text:
            self.notify(MSG_CHUA_BOI, severity="warning")
            return
        pattern, options = detect_pattern(text)
        fld = self._selected_field()
        if fld is None:
            fid = self.formula.next_id()
            fld = Field(fid=fid, pattern=pattern, options=options)
            self.formula.fields.append(fld)
            self._selected_fid = fid
        else:
            fld.pattern = pattern
            fld.options = options
            fid = fld.fid
        self._rebuild_field_list(keep=fid)
        self._write_field_controls()
        self._goto_tab("match")
        self.notify(MSG_MARK.format(fid=fid, kind=PATTERN_LABELS.get(pattern, pattern)))
        self.action_generate()

    def action_generate(self) -> None:
        self._read_global_controls()
        self._read_field_controls()
        self._rebuild_field_list(keep=self._selected_fid)
        result = generate(self.formula)
        out = self.query_one("#regex-out", Static)
        if result.error:
            self._last_result_regex = ""
            out.update(result.error)
            self.notify(result.error, severity="error")
            return
        self._last_result_regex = result.flavor_regex
        out.update(result.flavor_regex or "")
        self.formula.flavor = self.query_one("#sel-flavor", Select).value  # type: ignore[assignment]
        self._refresh_snippet()
        self._run_test_silent()

    def action_copy_regex(self) -> None:
        if not self._last_result_regex:
            self.notify(MSG_CHUA_REGEX, severity="warning")
            return
        self.app.copy_to_clipboard(self._last_result_regex)
        self.notify(MSG_DA_COPY)

    def _clipboard_text(self) -> str:
        local = getattr(self.app, "clipboard", "") or ""
        if str(local).strip():
            return str(local)
        try:
            import subprocess

            raw = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                timeout=5,
                stderr=subprocess.DEVNULL,
            )
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def action_run_test(self) -> None:
        self.action_generate()

    def action_save_formula(self) -> None:
        self._read_global_controls()
        self._read_field_controls()
        path = Path.cwd() / "formula.json"
        path.write_text(self.formula.to_json(), encoding="utf-8")
        self.notify(MSG_DA_LUU.format(path=path))

    def action_load_formula(self) -> None:
        path = Path.cwd() / "formula.json"
        if not path.exists():
            self.notify(MSG_KHONG_THAY_FILE, severity="error")
            return
        try:
            self.formula = Formula.from_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.notify(MSG_LOI_DOC.format(exc=exc), severity="error")
            return
        self._selected_fid = self.formula.fields[0].fid if self.formula.fields else None
        self._write_global_controls()
        self._rebuild_field_list()
        self._write_field_controls()
        self.action_generate()
        self.notify(MSG_DA_NAP.format(path=path))

    def _load_preset(self, name: str) -> None:
        src = PRESETS[name]
        self.formula = Formula.from_json(src.to_json())
        self._selected_fid = self.formula.fields[0].fid if self.formula.fields else None
        self._write_global_controls()
        self._rebuild_field_list()
        self._write_field_controls()
        self.action_generate()
        self.notify(MSG_PRESET.format(name=name))

    def _refresh_snippet(self) -> None:
        lang = self.query_one("#sel-lang", Select).value
        regex = self._last_result_regex
        code = render_snippet(
            str(lang),
            regex,
            self.formula.action,
            self.formula.replacement,
            self.formula.flags_ignorecase,
            self.formula.flags_multiline,
            self.formula.flags_dotall,
        )
        area = self.query_one("#snippet-out", TextArea)
        area.language = "python" if lang in ("python",) else ("javascript" if lang == "javascript" else None)
        area.text = code

    def _run_test_silent(self) -> None:
        samples = self.query_one("#samples-text", TextArea).text
        result = generate(self.formula)
        stats = self.query_one("#test-stats", Static)
        view = self.query_one("#test-view", RichLog)
        view.clear()
        if result.error or not result.regex:
            stats.update(MSG_KHONG_TEST)
            return
        matches = test_matches(result.regex, result.python_flags, samples)
        stats.update(f"{len(matches)} match(es)  ·  engine: Python re")
        if matches:
            view.write("\n[bold]Groups[/]")
            for m in matches[:50]:
                groups = ", ".join(f"{k}={v!r}" for k, v in m["groups"].items())
                view.write(f"#{m['n']} [{m['start']}:{m['end']}] {m['text']!r}  {groups}")

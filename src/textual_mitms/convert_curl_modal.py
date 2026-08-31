from textual.app import ComposeResult
from textual.containers import Vertical, Grid, Horizontal
from textual.widgets import TextArea, Select, Button, Static, Label
from textual.screen import ModalScreen
from textual import on

from .tools.curlconverter.curl_parser import parse_curl_command
from .tools.curlconverter.generators import GENERATORS


class CurlConverterModal(ModalScreen):
    """Màn hình Modal chuyển đổi lệnh cURL tự động, giao diện tối giản không Label."""

    CSS = """
    CurlConverterModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }

    #convert-dialog {
        width: 95%;
        height: 90%;
        background: $surface;
        border: solid $accent;
        padding: 1 1;
        layers: base menu;
    }

    /* CSS cho nút Close ghim ở góc trên bên phải */
    #btn-close-modal { min-width: 5; border: none; background: $panel; color: $text; text-style: bold; dock: right; }

    #btn-close-modal:hover {
        background: $error;
        color: white;
    }

    #lbl-examples {
        text-style: underline bold; /* Gạch chân và in đậm */
        color: $accent;
        margin-right: 1;
        content-align-vertical: middle;
    }
    
    .btn-example {
        min-width: 5;
        height: 1;
        border: none;
        background: $panel;
        color: $text-muted;
        margin-right: 1;
    }

    .btn-example:hover {
        background: $primary;
        color: white;
        text-style: bold;
    }

    #input-curl { 
        height: 2fr; 
        border: round $primary; 
        margin-bottom: 1;
    }

    #output-wrapper {
        border: round $success;
        height: 3fr;
        width: 100%;
    }

    #output-code { 
        width: 1fr;
        height: 100%; 
        border: none; 
        background: $panel-darken-1; 
    }

    #btn-copy-output {
        min-width: 3;
        height: 1;
        color: white;
        background: $success;
        border: none;
        text-style: bold;
    }

    #wrapper-copy-output {
        width: 1fr;
        height: auto;         
        margin: 0 1 1 1;     
        align-horizontal: right;
    }

    #btn-copy-output:hover {
        background: $accent;
    }

    .select-group {
        layout: grid;
        grid-size: 6; 
        grid-gutter: 1 1; 
        height: auto;
        border: round $secondary; 
        padding: 1;
        margin-bottom: 1;
    }

    .select-group Select {
        width: 100%;
    }

    .modal-header {
        height: auto;
        margin-bottom: 1;
    }

    .spacer { width: 1fr; }
    """

    BINDINGS = [
        ("escape", "app.pop_screen", "Đóng Modal")
    ]

    PYTHON_LIBS = [("requests", "requests"), ("httpx", "httpx"), ("curl_cffi", "curl_cffi"),
                   ("http.client", "http_client")]
    JAVA_LIBS = [("HttpClient", "java_httpclient"), ("HttpURLConnection", "java_httpurlconnection"),
                 ("Jsoup", "java_jsoup"), ("OkHttp", "java_okhttp")]
    C_LIBS = [("libcurl", "c_libcurl")]
    CSHARP_LIBS = [("System.Net.Http", "csharp_httpclient")]
    GO_LIBS = [("net/http", "go_http")]
    JS_LIBS = [("Fetch API", "javascript_fetch"), ("jQuery AJAX", "javascript_jquery"),
               ("XMLHttpRequest", "javascript_xhr")]
    NODEJS_LIBS = [("Axios", "nodejs_axios"), ("Got", "nodejs_got"), ("Ky", "nodejs_ky"),
                   ("node-fetch", "nodejs_node_fetch"), ("Request", "nodejs_request"),
                   ("Superagent", "nodejs_superagent"), ("Native (https/http)", "nodejs_https")]
    JULIA_LIBS = [("HTTP.jl", "julia_http")]
    KOTLIN_LIBS = [("OkHttp", "kotlin_okhttp")]
    LUA_LIBS = [("socket.http", "lua_socket")]
    MATLAB_LIBS = [("HTTP Interface", "matlab_http")]
    OBJC_LIBS = [("NSURLSession", "objective_c")]
    OCAML_LIBS = [("Cohttp (Lwt)", "ocaml_cohttp")]
    PERL_LIBS = [("LWP::UserAgent", "perl_lwp")]
    PHP_LIBS = [("cURL (curl_init)", "php_curl"), ("Guzzle (GuzzleHttp)", "php_guzzle")]
    POWERSHELL_LIBS = [("Invoke-RestMethod", "powershell_restmethod"), ("Invoke-WebRequest", "powershell_webrequest")]
    R_LIBS = [("httr", "r_httr"), ("httr2 (Pipeline)", "r_httr2")]
    RUBY_LIBS = [("net/http", "ruby_nethttp"), ("HTTParty", "ruby_httparty")]
    RUST_LIBS = [("reqwest", "rust_reqwest")]
    SWIFT_LIBS = [("URLSession", "swift_urlsession")]
    CLI_LIBS = [("Wget", "wget")]
    HTTP_LIBS = [("Raw Request", "http_raw")]
    DATA_FORMAT_LIBS = [("JSON Format", "json_format"), ("HAR 1.2", "har_format")]
    DART_LIBS = [("http", "dart_http")]

    def __init__(self, initial_curl: str = ""):
        super().__init__()
        self.initial_curl = initial_curl
        self.current_target_lib = "requests"

    def compose(self) -> ComposeResult:
        with Vertical(id="convert-dialog") as dialog:
            dialog.border_title = "CONVERT CURL COMMANDS"
            dialog.styles.border_title_align = "center"

            with Horizontal(classes="modal-header"):
                # MỚI: Thêm các nút Ví dụ ở bên trái
                yield Label("Examples:", id="lbl-examples")
                yield Button("GET", id="ex_get", classes="btn-example")
                yield Button("POST", id="ex_post", classes="btn-example")
                yield Button("JSON", id="ex_json", classes="btn-example")
                yield Button("Basic Auth", id="ex_auth", classes="btn-example")
                yield Button("Files", id="ex_file", classes="btn-example")
                yield Button("Form", id="ex_form", classes="btn-example")
                yield Static("", classes="spacer")
                yield Button("X", id="btn-close-modal")

            inp_area = TextArea(id="input-curl", language="bash")
            yield inp_area

            with Grid(classes="select-group"):
                yield Select(self.PYTHON_LIBS, id="select-python", prompt="Python", compact=True)
                yield Select(self.JAVA_LIBS, id="select-java", prompt="Java", compact=True)
                yield Select(self.NODEJS_LIBS, id="select-nodejs", prompt="Node.js", compact=True)
                yield Select(self.JS_LIBS, id="select-js", prompt="JavaScript", compact=True)
                yield Select(self.CSHARP_LIBS, id="select-csharp", prompt="C#", compact=True)
                yield Select(self.GO_LIBS, id="select-go", prompt="Go", compact=True)
                yield Select(self.C_LIBS, id="select-c", prompt="C/C++", compact=True)
                yield Select(self.KOTLIN_LIBS, id="select-kotlin", prompt="Kotlin", compact=True)
                yield Select(self.JULIA_LIBS, id="select-julia", prompt="Julia", compact=True)
                yield Select(self.LUA_LIBS, id="select-lua", prompt="Lua", compact=True)
                yield Select(self.MATLAB_LIBS, id="select-matlab", prompt="MATLAB", compact=True)
                yield Select(self.OBJC_LIBS, id="select-objc", prompt="Objective-C", compact=True)
                yield Select(self.OCAML_LIBS, id="select-ocaml", prompt="OCaml", compact=True)
                yield Select(self.PERL_LIBS, id="select-perl", prompt="Perl", compact=True)
                yield Select(self.PHP_LIBS, id="select-php", prompt="PHP", compact=True)
                yield Select(self.POWERSHELL_LIBS, id="select-powershell", prompt="PowerShell", compact=True)
                yield Select(self.R_LIBS, id="select-r", prompt="R", compact=True)
                yield Select(self.RUBY_LIBS, id="select-ruby", prompt="Ruby", compact=True)
                yield Select(self.RUST_LIBS, id="select-rust", prompt="Rust", compact=True)
                yield Select(self.SWIFT_LIBS, id="select-swift", prompt="Swift", compact=True)
                yield Select(self.CLI_LIBS, id="select-cli", prompt="CLI", compact=True)
                yield Select(self.HTTP_LIBS, id="select-http", prompt="HTTP", compact=True)
                yield Select(self.DATA_FORMAT_LIBS, id="select-data-format", prompt="Data Format", compact=True)
                yield Select(self.DART_LIBS, id="select-dart", prompt="Dart", compact=True)

            with Vertical(id="output-wrapper"):
                with Horizontal(id="wrapper-copy-output"):
                    yield Button("Copy to clipboard", id="btn-copy-output", flat=True)
                yield TextArea(id="output-code")

    def on_mount(self) -> None:
        input_widget = self.query_one("#input-curl", TextArea)

        if self.initial_curl:
            input_widget.text = self.initial_curl
            self._perform_conversion()

        input_widget.focus()

    @on(Button.Pressed, "#btn-close-modal")
    def close_modal(self) -> None:
        self.app.pop_screen()

    # MỚI: Xử lý sự kiện khi bấm vào các nút Ví dụ (Examples)
    @on(Button.Pressed, ".btn-example")
    def load_curl_example(self, event: Button.Pressed) -> None:
        """Tự động điền mã cURL mẫu vào TextArea dựa trên nút được bấm."""
        examples = {
            "ex_get": "curl -X GET 'https://api.example.com/data'",
            "ex_post": "curl -X POST 'https://api.example.com/data' -d 'Hello World'",
            "ex_json": "curl -X POST 'https://api.example.com/data' -H 'Content-Type: application/json' -d '{\"key\": \"value\"}'",
            "ex_auth": "curl -u admin:secret123 'https://api.example.com/secure'",
            "ex_file": "curl -F 'document=@/path/to/file.pdf' 'https://api.example.com/upload'",
            "ex_form": "curl -X POST 'https://api.example.com/login' -H 'Content-Type: application/x-www-form-urlencoded' -d 'username=abc&password=123'"
        }

        button_id = event.button.id
        if button_id in examples:
            # Gán text vào ô nhập liệu, TextArea.Changed sẽ tự động kích hoạt _perform_conversion
            self.query_one("#input-curl", TextArea).text = examples[button_id]

    @on(Button.Pressed, "#btn-copy-output")
    def copy_output_code(self) -> None:
        output_text = self.query_one("#output-code", TextArea).text
        if output_text and not output_text.startswith("// Vui lòng") and not output_text.startswith("// Lỗi"):
            self.app.copy_to_clipboard(output_text)
            self.app.notify("Đã sao chép mã thành công!", severity="information")
        else:
            self.app.notify("Không có mã hợp lệ để sao chép!", severity="warning")

    @on(Select.Changed)
    def select_changed(self, event: Select.Changed) -> None:
        if event.value == Select.BLANK:
            return

        self.current_target_lib = str(event.value)

        select_ids = [
            "select-python", "select-java", "select-nodejs", "select-js",
            "select-csharp", "select-go", "select-c", "select-kotlin",
            "select-julia", "select-lua", "select-matlab", "select-objc",
            "select-ocaml", "select-data-format", "select-perl", "select-php",
            "select-powershell", "select-r", "select-ruby", "select-rust",
            "select-swift", "select-cli", "select-http", "select-dart"
        ]

        for s_id in select_ids:
            if event.select.id != s_id:
                other_select = self.query_one(f"#{s_id}", Select)
                with other_select.prevent(Select.Changed):
                    other_select.allow_blank = True
                    other_select.clear()

        self._perform_conversion()

    @on(TextArea.Changed, "#input-curl")
    def on_input_curl_changed(self, event: TextArea.Changed) -> None:
        self._perform_conversion()

    def _perform_conversion(self) -> None:
        curl_text = self.query_one("#input-curl", TextArea).text.strip()
        target_lib = self.current_target_lib
        output_area = self.query_one("#output-code", TextArea)

        if not curl_text:
            output_area.text = "// Vui lòng nhập lệnh cURL."
            return

        parsed_data = parse_curl_command(curl_text)

        if parsed_data.get("error"):
            output_area.text = parsed_data["error"]
            return

        generator_func = GENERATORS.get(target_lib)
        if generator_func:
            output_area.text = generator_func(parsed_data)

            LANGUAGE_MAPPING = {
                "csharp": None,
                "c_libcurl": None,
                "go": "go",
                "java": "java",
                "javascript": "javascript",
                "nodejs": "javascript",
                "powershell": "bash",
                "wget": "bash",
                "ruby": None,
                "rust": "rust",
                "json": "json",
                "har": "json",
                "julia": None,
                "kotlin": None,
                "lua": None,
                "matlab": None,
                "ocaml": None,
                "perl": None,
                "php": None,
                "objective_c": None,
                "r_": None,
                "swift": None,
                "http_raw": None,
                "dart": None
            }

            output_area.language = "python"

            for keyword, lang in LANGUAGE_MAPPING.items():
                if keyword in target_lib:
                    output_area.language = lang
                    break
        else:
            output_area.text = ""

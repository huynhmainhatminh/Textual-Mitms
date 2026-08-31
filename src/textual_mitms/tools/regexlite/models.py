"""Formula model."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal
import json

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

PATTERN_LABELS = {
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

DEFAULT_OPTIONS = {
    "literal": {"text": ""},
    "list": {"items": "one\ntwo\nthree"},
    "integer": {"minimum": "0", "maximum": "99", "base": "dec"},
    "number": {
        "allow_sign": True,
        "allow_decimal": True,
        "allow_grouping": False,
        "allow_exponent": False,
    },
    "date": {"format": "ymd-dash"},
    "email": {"domains": ""},
    "url": {"schemes": "http;https"},
    "ipv4": {"dotted": True},
    "guid": {"braces": False, "hyphens": True},
    "charset": {"preset": "digits", "custom": "", "min_len": "1", "max_len": "64"},
    "anything": {"until": "whitespace", "delimiter": ",", "stop_string": ""},
    "bytes": {"hex": ""},
    "control": {"which": "tab"},
    "mask": {"mask": "###"},
    "unicode": {"set": "letter"},
    "datetime": {"format": "ymd-dash", "time": "hms"},
    "regex": {"pattern": ""},
    "field_pattern": {"source": ""},
    "field_text": {"source": ""},
    "creditcard": {"spaces": True},
    "country": {"items": ""},
    "state": {"items": ""},
    "currency": {"items": ""},
    "national_id": {"items": ""},
    "vat": {"items": ""},
}

Strictness = Literal["strict", "average", "loose"]
ActionKind = Literal["find", "replace", "split"]
Anchor = Literal["anywhere", "string", "line", "word", "attempt"]
Flavor = Literal["python", "javascript", "pcre", "dotnet", "java"]
GroupStyle = Literal["numbered", "named"]


@dataclass
class Field:
    fid: int
    pattern: str = "literal"
    options: dict[str, Any] = field(default_factory=dict)
    capture: bool = True
    optional: bool = False
    repeat_min: int = 1
    repeat_max: int = 1
    name: str = ""

    def __post_init__(self) -> None:
        if not self.options:
            self.options = dict(DEFAULT_OPTIONS.get(self.pattern, {}))
        if not self.name:
            self.name = f"field{self.fid}"

    def label(self) -> str:
        kind = PATTERN_LABELS.get(self.pattern, self.pattern)
        extra = ""
        if self.pattern == "literal":
            extra = f" “{self.options.get('text', '')[:18]}”"
        elif self.pattern == "integer":
            extra = f" {self.options.get('minimum')}–{self.options.get('maximum')}"
        elif self.pattern in ("date", "datetime"):
            extra = f" {self.options.get('format')}"
        elif self.pattern == "mask":
            extra = f" {self.options.get('mask', '')[:18]}"
        elif self.pattern in ("field_pattern", "field_text"):
            extra = f" ← #{self.options.get('source', '')}"
        flags = []
        if self.optional:
            flags.append("?")
        if self.repeat_max != 1 or self.repeat_min != 1:
            flags.append(f"{{{self.repeat_min},{self.repeat_max}}}")
        flag_s = " " + " ".join(flags) if flags else ""
        return f"#{self.fid} {kind}{extra}{flag_s}"


@dataclass
class Formula:
    samples: str = (
        "Order #1042 placed on 2024-03-15 by ada@example.com\n"
        "Order #88 placed on 2024-12-01 by bob.nguyen@shop.vn"
    )
    fields: list[Field] = field(default_factory=list)
    begin: Anchor = "anywhere"
    end: Anchor = "anywhere"
    strictness: Strictness = "average"
    action: ActionKind = "find"
    replacement: str = "$1"
    flavor: Flavor = "python"
    group_style: GroupStyle = "numbered"
    flags_ignorecase: bool = False
    flags_multiline: bool = False
    flags_dotall: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "Formula":
        data = json.loads(raw)
        fields = [Field(**f) for f in data.pop("fields", [])]
        return cls(fields=fields, **data)

    def next_id(self) -> int:
        return (max((f.fid for f in self.fields), default=0) + 1)

    def field_by_id(self, fid: int) -> Field | None:
        for f in self.fields:
            if f.fid == fid:
                return f
        return None

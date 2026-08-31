"""Built-in formula presets (Lite library)."""

from __future__ import annotations

from .models import DEFAULT_OPTIONS, Field, Formula


def _f(fid: int, kind: str, **opts) -> Field:
    base = dict(DEFAULT_OPTIONS.get(kind, {}))
    capture = opts.pop("capture", True)
    optional = opts.pop("optional", False)
    name = opts.pop("name", f"field{fid}")
    rmin = opts.pop("repeat_min", 1)
    rmax = opts.pop("repeat_max", 1)
    base.update(opts)
    return Field(
        fid=fid,
        pattern=kind,
        options=base,
        capture=capture,
        optional=optional,
        name=name,
        repeat_min=rmin,
        repeat_max=rmax,
    )


PRESETS: dict[str, Formula] = {
    "Order line (id + date + email)": Formula(
        samples=(
            "Order #1042 placed on 2024-03-15 by ada@example.com\n"
            "Order #88 placed on 2024-12-01 by bob.nguyen@shop.vn"
        ),
        fields=[
            _f(1, "literal", text="Order #", capture=False, name="label"),
            _f(2, "integer", minimum="1", maximum="9999", name="order_id"),
            _f(3, "literal", text=" placed on ", capture=False, name="mid1"),
            _f(4, "date", format="ymd-dash", name="date"),
            _f(5, "literal", text=" by ", capture=False, name="mid2"),
            _f(6, "email", name="email"),
        ],
        begin="line",
        end="line",
        strictness="average",
    ),
    "Email only": Formula(
        samples="ada@example.com\nbob.nguyen@shop.vn\nnot-an-email",
        fields=[_f(1, "email", name="email")],
        begin="line",
        end="line",
        strictness="average",
    ),
    "ISO date": Formula(
        samples="2024-03-15\n1999-01-01\n2024-13-40",
        fields=[_f(1, "date", format="ymd-dash", name="date")],
        begin="line",
        end="line",
        strictness="strict",
    ),
    "ISO datetime": Formula(
        samples="2024-03-15 14:30:00\n2024-03-15T08:01:59\n2024-13-40 99:99:99",
        fields=[_f(1, "datetime", format="ymd-dash", time="hms", name="when")],
        begin="line",
        end="line",
        strictness="average",
    ),
    "Integer 42-2552": Formula(
        samples="41\n42\n100\n2552\n2553\n7",
        fields=[_f(1, "integer", minimum="42", maximum="2552", name="n")],
        begin="line",
        end="line",
        strictness="strict",
    ),
    "Decimal number": Formula(
        samples="3.14\n-2.5\n100\n+0.01",
        fields=[
            _f(
                1,
                "number",
                allow_sign=True,
                allow_decimal=True,
                allow_grouping=False,
                allow_exponent=False,
                name="num",
            )
        ],
        begin="line",
        end="line",
        strictness="average",
    ),
    "IPv4 address": Formula(
        samples="127.0.0.1\n192.168.0.10\n999.1.1.1\n10.0.0.2",
        fields=[_f(1, "ipv4", name="ip")],
        begin="line",
        end="line",
        strictness="strict",
    ),
    "HTTP / HTTPS URL": Formula(
        samples="https://textual.textualize.io/guide/\nhttp://example.com/a?x=1\nftp://skip.me",
        fields=[_f(1, "url", schemes="http;https", name="url")],
        begin="line",
        end="line",
        strictness="average",
    ),
    "GUID / UUID": Formula(
        samples="550e8400-e29b-41d4-a716-446655440000\nnot-a-guid",
        fields=[_f(1, "guid", braces=False, hyphens=True, name="guid")],
        begin="line",
        end="line",
        strictness="average",
    ),
    "GUID with braces": Formula(
        samples="{550e8400-e29b-41d4-a716-446655440000}\n550e8400-e29b-41d4-a716-446655440000",
        fields=[_f(1, "guid", braces=True, hyphens=True, name="guid")],
        begin="line",
        end="line",
        strictness="average",
    ),
    "Name list": Formula(
        samples="Mary had a little lamb.\nSue and Betty waved.",
        fields=[_f(1, "list", items="Mary\nSue\nBetty", name="name")],
        begin="word",
        end="word",
        strictness="average",
    ),
    "Character mask ###-##-####": Formula(
        samples="123-45-6789\n000-00-0000\n12-345-6789",
        fields=[_f(1, "mask", mask="###-##-####", name="code")],
        begin="line",
        end="line",
        strictness="average",
    ),
    "Basic digits 1-4": Formula(
        samples="1\n42\n1042\n10425",
        fields=[_f(1, "charset", preset="digits", min_len="1", max_len="4", name="digits")],
        begin="line",
        end="line",
        strictness="average",
    ),
    "Hex bytes": Formula(
        samples="DEADBEEF\n00 FF\nXYZ",
        fields=[_f(1, "bytes", hex="DEADBEEF", name="raw")],
        begin="anywhere",
        end="anywhere",
        strictness="average",
    ),
    "Match anything until whitespace": Formula(
        samples="Order #1042 placed on 2024-03-15 by ada@example.com",
        fields=[
            _f(1, "literal", text="Order #", capture=False, name="left"),
            _f(2, "anything", until="whitespace", name="order_id"),
            _f(3, "literal", text=" placed on", capture=False, name="right"),
        ],
        begin="anywhere",
        end="anywhere",
        strictness="average",
    ),
    "Match anything until phrase": Formula(
        samples='["LSD",[],{"token":"AdRZI-GSDrN8126S3P7y_fPNPo0"},323]',
        fields=[
            _f(1, "literal", text='"token":"', capture=False, name="left"),
            _f(2, "anything", until="stop_string", stop_string='"},323]', name="token"),
            _f(3, "literal", text='"},323]', capture=False, name="right"),
        ],
        begin="anywhere",
        end="anywhere",
        strictness="average",
    ),
    "Match anything until quote": Formula(
        samples='{"token":"AdRZI-GSDrN8126S3P7y_fPNPo0"}',
        fields=[
            _f(1, "literal", text='"token":"', capture=False, name="left"),
            _f(2, "anything", until="quote", name="token"),
            _f(3, "literal", text='"', capture=False, name="right"),
        ],
        begin="anywhere",
        end="anywhere",
        strictness="average",
    ),
    "Credit card (test numbers)": Formula(
        samples="4111111111111111\n5500000000000004\n370000000000002\n1234",
        fields=[_f(1, "creditcard", spaces=True, name="pan")],
        begin="line",
        end="line",
        strictness="loose",
    ),
    "ISO currency codes": Formula(
        samples="USD 10\nEUR 5\nVND 1000\nXYZ 1",
        fields=[_f(1, "currency", items="USD\nEUR\nVND\nJPY", name="ccy")],
        begin="word",
        end="word",
        strictness="average",
    ),
    "Raw regex digits": Formula(
        samples="Order #1042\nOrder #88",
        fields=[_f(1, "regex", pattern=r"\d+", name="n")],
        begin="anywhere",
        end="anywhere",
        strictness="average",
    ),
    "Repeat text of integer": Formula(
        samples="42 = 42\n7 = 7\n42 = 7",
        fields=[
            _f(1, "integer", minimum="0", maximum="99", name="n"),
            _f(2, "literal", text=" = ", capture=False, name="eq"),
            _f(3, "field_text", source="1", capture=False, name="again"),
        ],
        begin="line",
        end="line",
        strictness="average",
    ),
    "Reuse integer pattern": Formula(
        samples="12-34\n5-9\n100-1",
        fields=[
            _f(1, "integer", minimum="1", maximum="99", name="a"),
            _f(2, "literal", text="-", capture=False, name="dash"),
            _f(3, "field_pattern", source="1", name="b"),
        ],
        begin="line",
        end="line",
        strictness="average",
    ),
    "Unicode letter": Formula(
        samples="ada\nNguyễn\n42",
        fields=[_f(1, "unicode", set="letter", name="ch")],
        begin="anywhere",
        end="anywhere",
        strictness="average",
    ),
    "Control tab": Formula(
        samples="left\tright\nleft right",
        fields=[
            _f(1, "literal", text="left", capture=False, name="l"),
            _f(2, "control", which="tab", name="tab"),
            _f(3, "literal", text="right", capture=False, name="r"),
        ],
        begin="line",
        end="line",
        strictness="average",
    ),
}

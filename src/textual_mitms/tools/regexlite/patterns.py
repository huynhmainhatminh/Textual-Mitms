"""Pattern → regex fragment generators (Lite set)."""

from __future__ import annotations

import re
from typing import Any

from .models import Strictness


def _escape(text: str) -> str:
    return re.escape(text)


def _digits_range(a: str, b: str) -> str:
    """Match digit strings from a to b inclusive. a and b have equal length."""
    if a == b:
        return _escape(a)
    n = len(a)
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    pref = _escape(a[:i])
    if i == n:
        return pref
    da, db = a[i], b[i]
    rest = n - i - 1
    if rest == 0:
        return pref + (da if da == db else f"[{da}-{db}]")
    alts: list[str] = []
    alts.append(pref + _escape(da) + _digits_range(a[i + 1 :], "9" * rest))
    if int(da) + 1 <= int(db) - 1:
        alts.append(pref + f"[{int(da)+1}-{int(db)-1}]" + rf"\d{{{rest}}}")
    if da != db:
        alts.append(pref + _escape(db) + _digits_range("0" * rest, b[i + 1 :]))
    return alts[0] if len(alts) == 1 else "(?:" + "|".join(alts) + ")"


def _alt_range(lo: int, hi: int) -> str:
    if hi < lo:
        lo, hi = hi, lo
    lo = max(int(lo), 0)
    hi = int(hi)
    if hi - lo <= 40:
        return "(?:" + "|".join(_escape(str(n)) for n in range(lo, hi + 1)) + ")"
    parts: list[str] = []
    cur = lo
    while cur <= hi:
        width = len(str(cur))
        end_this = min(hi, 10**width - 1)
        parts.append(_digits_range(str(cur), str(end_this)))
        cur = end_this + 1
    return parts[0] if len(parts) == 1 else "(?:" + "|".join(parts) + ")"


def gen_integer(opts: dict[str, Any], strictness: Strictness) -> str:
    base = opts.get("base", "dec")
    try:
        lo = int(str(opts.get("minimum", "0")), 10)
        hi = int(str(opts.get("maximum", "99")), 10)
    except ValueError:
        lo, hi = 0, 99
    if lo > hi:
        lo, hi = hi, lo

    if base == "hex":
        if strictness == "loose":
            return r"[0-9A-Fa-f]+"
        return rf"[0-9A-Fa-f]{{{len(f'{lo:x}')},{len(f'{hi:x}')}}}"
    if base == "bin":
        return r"[01]+" if strictness == "loose" else rf"[01]{{{len(bin(max(lo,0)))-2},{len(bin(hi))-2}}}"
    if base == "oct":
        return r"[0-7]+" if strictness == "loose" else rf"[0-7]{{{len(oct(max(lo,0)))-2},{len(oct(hi))-2}}}"

    dmin, dmax = len(str(max(lo, 0))), len(str(max(hi, 0)))
    if strictness == "loose":
        return rf"\d{{{dmin},{dmax}}}" if dmin != dmax else rf"\d{{{dmin}}}"
    if strictness == "average":
        if lo == 0:
            return rf"\d{{1,{dmax}}}" if dmax > 1 else r"\d"
        return rf"[1-9]\d{{{max(dmin-1, 0)},{dmax-1}}}" if dmax > 1 else r"[1-9]"
    return _alt_range(lo, hi)


def gen_number(opts: dict[str, Any], strictness: Strictness) -> str:
    sign = r"[+-]?" if opts.get("allow_sign", True) else ""
    if strictness == "loose":
        return sign + r"\d+(?:\.\d+)?"
    dec = r"(?:\.\d+)?" if opts.get("allow_decimal", True) else ""
    grp = r"\d{1,3}(?:,\d{3})+" if opts.get("allow_grouping") else r"\d+"
    body = grp + dec
    if opts.get("allow_exponent"):
        body += r"(?:[eE][+-]?\d+)?"
    return sign + body


def gen_date(opts: dict[str, Any], strictness: Strictness) -> str:
    fmt = opts.get("format", "ymd-dash")
    y, m, d = r"\d{4}", r"\d{2}", r"\d{2}"
    if strictness == "strict":
        y = r"(?:19|20)\d{2}"
        m = r"(?:0[1-9]|1[0-2])"
        d = r"(?:0[1-9]|[12]\d|3[01])"
    elif strictness == "average":
        m = r"(?:0?[1-9]|1[0-2])"
        d = r"(?:0?[1-9]|[12]\d|3[01])"
    table = {
        "ymd-dash": f"{y}-{m}-{d}",
        "ymd-slash": f"{y}/{m}/{d}",
        "dmy-slash": f"{d}/{m}/{y}",
        "mdy-slash": f"{m}/{d}/{y}",
        "dmy-dot": f"{d}\\.{m}\\.{y}",
        "yyyymmdd": f"{y}{m}{d}",
    }
    return table.get(fmt, table["ymd-dash"])


def gen_email(opts: dict[str, Any], strictness: Strictness) -> str:
    domains = [x.strip() for x in str(opts.get("domains", "")).split(";") if x.strip()]
    if domains:
        dom = "(?:" + "|".join(_escape(d) for d in domains) + ")"
        local = r"[\w.+-]+" if strictness != "loose" else r"\S+"
        return local + "@" + dom
    if strictness == "loose":
        return r"\S+@\S+"
    if strictness == "average":
        return r"[\w.+-]+@[\w.-]+\.\w+"
    return r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"


def gen_url(opts: dict[str, Any], strictness: Strictness) -> str:
    schemes = [s.strip() for s in str(opts.get("schemes", "http;https")).split(";") if s.strip()]
    sch = "(?:" + "|".join(_escape(s) for s in schemes) + ")" if schemes else r"[a-zA-Z][a-zA-Z0-9+.-]*"
    if strictness == "loose":
        return sch + r"://\S+"
    return sch + r"://[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s]*)?"


def gen_ipv4(opts: dict[str, Any], strictness: Strictness) -> str:
    if strictness == "loose":
        return r"\d{1,3}(?:\.\d{1,3}){3}"
    if strictness == "average":
        return r"(?:\d{1,3}\.){3}\d{1,3}"
    octet = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    return rf"(?:{octet}\.){{3}}{octet}"


def gen_guid(opts: dict[str, Any], strictness: Strictness) -> str:
    hex8 = r"[0-9A-Fa-f]{8}"
    hex4 = r"[0-9A-Fa-f]{4}"
    hex12 = r"[0-9A-Fa-f]{12}"
    if opts.get("hyphens", True):
        core = f"{hex8}-{hex4}-{hex4}-{hex4}-{hex12}"
    else:
        core = r"[0-9A-Fa-f]{32}"
    if opts.get("braces"):
        return r"\{" + core + r"\}"
    if strictness == "loose":
        return r"[0-9A-Fa-f{}-]{32,38}"
    return core


def _custom_class(custom: str) -> str:
    """Build a character class from the Custom box.

    Users often paste a full regex like [A-Za-z0-9_-]+ — strip brackets
    and quantifiers. Do not re.escape hyphens (they mean ranges).
    """
    s = str(custom or "").strip()
    if not s:
        return r"."
    if s.startswith("[") and "]" in s:
        inner, _, tail = s[1:].partition("]")
        s = inner
        tail = tail.strip()
        # leftover + * ? {n,m} is handled by min/max length, ignore here
        _ = tail
    s = s.replace("\\", "\\\\").replace("]", "\\]")
    if s.startswith("^"):
        s = "\\" + s
    return "[" + s + "]"


def gen_charset(opts: dict[str, Any], strictness: Strictness) -> str:
    preset = opts.get("preset", "digits")
    custom = opts.get("custom", "")
    try:
        mn = max(0, int(opts.get("min_len", "1") or 1))
        mx = max(mn, int(opts.get("max_len", "64") or 64))
    except ValueError:
        mn, mx = 1, 64
    classes = {
        "digits": r"\d",
        "letters": r"[A-Za-z]",
        "upper": r"[A-Z]",
        "lower": r"[a-z]",
        "word": r"\w",
        "whitespace": r"\s",
        "hex": r"[0-9A-Fa-f]",
        "custom": _custom_class(custom),
    }
    atom = classes.get(preset, r"\d")
    if mn == 1 and mx == 1:
        return atom
    if mx >= 999:
        return atom + ("+" if mn <= 1 else f"{{{mn},}}")
    if mn == mx:
        return atom + f"{{{mn}}}"
    return atom + f"{{{mn},{mx}}}"


def gen_anything(opts: dict[str, Any], strictness: Strictness) -> str:
    """Middle field: match until a stop rule."""
    until = opts.get("until", "whitespace")
    if until == "whitespace":
        return r"\S+"
    if until in ("newline", "not_newline"):
        return r"[^\r\n]+"
    if until == "end":
        return r".*" if strictness == "loose" else r".+?"
    if until == "punct":
        return r"[^.,;:!?…]+"
    if until == "digit":
        return r"\D+"
    if until == "letter":
        return r"[^A-Za-zÀ-ỹĂăÂâÊêÔôƠơƯưĐđ]+"
    if until == "bracket":
        return r"[^)\]}>]+"
    if until == "quote":
        return r"[^'\"]+"
    if until == "stop_string":
        stop = str(opts.get("stop_string", "") or opts.get("delimiter", ""))
        if not stop:
            return r".+?"
        return rf".+?(?={_escape(stop)})"
    raw = str(opts.get("delimiter", ","))
    chars = "".join(dict.fromkeys(raw)) or ","
    return rf"[^{_escape(chars)}\n]+"


def gen_literal(opts: dict[str, Any], _strictness: Strictness) -> str:
    return _escape(str(opts.get("text", "")))


def gen_list(opts: dict[str, Any], _strictness: Strictness) -> str:
    items = [ln.strip() for ln in str(opts.get("items", "")).splitlines() if ln.strip()]
    if not items:
        return r"(?!)"
    return "(?:" + "|".join(_escape(i) for i in items) + ")"



def gen_bytes(opts: dict[str, Any], _strictness: Strictness) -> str:
    raw = str(opts.get("hex", "") or "")
    hexdigits = "".join(ch for ch in raw if ch in "0123456789abcdefABCDEF")
    if len(hexdigits) < 2 or len(hexdigits) % 2:
        return r"(?!)"
    parts = [hexdigits[i : i + 2] for i in range(0, len(hexdigits), 2)]
    return "".join("\\x" + h.lower() for h in parts)


def gen_control(opts: dict[str, Any], _strictness: Strictness) -> str:
    which = str(opts.get("which", "tab"))
    table = {
        "tab": r"\t",
        "lf": r"\n",
        "cr": r"\r",
        "crlf": r"\r\n",
        "any": r"[\x00-\x1F]",
    }
    return table.get(which, r"\t")


def gen_mask(opts: dict[str, Any], _strictness: Strictness) -> str:
    """# = digit, A = letter, ? = any, other chars are literal."""
    mask = str(opts.get("mask", "") or "")
    if not mask:
        return r"(?!)"
    out: list[str] = []
    for ch in mask:
        if ch == "#":
            out.append(r"\d")
        elif ch in "Aa":
            out.append(r"[A-Za-z]")
        elif ch == "?":
            out.append(r".")
        else:
            out.append(_escape(ch))
    return "".join(out)


def gen_unicode(opts: dict[str, Any], _strictness: Strictness) -> str:
    kind = str(opts.get("set", "letter"))
    table = {
        "letter": r"[^\W\d_]",
        "digit": r"\d",
        "any": r"[^\x00-\x7F]",
        "word": r"\w",
    }
    return table.get(kind, r"[^\W\d_]")


def gen_datetime(opts: dict[str, Any], strictness: Strictness) -> str:
    date_part = gen_date(opts, strictness)
    time = str(opts.get("time", "hms"))
    if time == "none":
        return date_part
    hh = r"(?:[01]\d|2[0-3])" if strictness != "loose" else r"\d{2}"
    mm = r"[0-5]\d" if strictness != "loose" else r"\d{2}"
    ss = r"[0-5]\d" if strictness != "loose" else r"\d{2}"
    if time == "hm":
        return date_part + r"[ T]" + hh + ":" + mm
    return date_part + r"[ T]" + hh + ":" + mm + ":" + ss


def gen_regex(opts: dict[str, Any], _strictness: Strictness) -> str:
    body = str(opts.get("pattern", "") or "").strip()
    return body or r"(?!)"


def gen_creditcard(opts: dict[str, Any], strictness: Strictness) -> str:
    sep = r"[ -]?" if opts.get("spaces", True) else ""
    if strictness == "loose":
        return rf"(?:\d{sep}){{13,19}}"
    # Public issuer prefixes: Visa 4, Mastercard 51-55, Amex 34/37
    visa = rf"4(?:\d{sep}){{12}}(?:(?:\d{sep}){{3}})?"
    mc = rf"5[1-5](?:\d{sep}){{14}}"
    amex = rf"3[47](?:\d{sep}){{13}}"
    return "(?:" + visa + "|" + mc + "|" + amex + ")"


GENERATORS = {
    "literal": gen_literal,
    "list": gen_list,
    "integer": gen_integer,
    "number": gen_number,
    "date": gen_date,
    "datetime": gen_datetime,
    "email": gen_email,
    "url": gen_url,
    "ipv4": gen_ipv4,
    "guid": gen_guid,
    "charset": gen_charset,
    "anything": gen_anything,
    "bytes": gen_bytes,
    "control": gen_control,
    "mask": gen_mask,
    "unicode": gen_unicode,
    "regex": gen_regex,
    "creditcard": gen_creditcard,
    "country": gen_list,
    "state": gen_list,
    "currency": gen_list,
    "national_id": gen_list,
    "vat": gen_list,
}



def generate_field_body(pattern: str, options: dict[str, Any], strictness: Strictness) -> str:
    fn = GENERATORS.get(pattern, gen_literal)
    return fn(options, strictness) or "(?!)"


def detect_pattern(text: str) -> tuple[str, dict[str, Any]]:
    """Heuristic used by Mark Selection — Lite auto-detect."""
    t = text.strip()
    if re.fullmatch(
        r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}",
        t,
    ):
        return "guid", {"braces": False, "hyphens": True}
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", t):
        return "ipv4", {"dotted": True}
    if re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", t):
        return "email", {"domains": ""}
    if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+", t):
        return "url", {"schemes": t.split("://", 1)[0]}
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        return "date", {"format": "ymd-dash"}
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", t):
        return "date", {"format": "dmy-slash"}
    if re.fullmatch(r"[+-]?\d+\.\d+", t):
        return "number", {
            "allow_sign": True,
            "allow_decimal": True,
            "allow_grouping": False,
            "allow_exponent": False,
        }
    if re.fullmatch(r"\d+", t):
        return "integer", {"minimum": t, "maximum": t, "base": "dec"}
    return "literal", {"text": t}

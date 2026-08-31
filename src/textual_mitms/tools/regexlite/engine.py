"""Assemble a Formula into a complete regular expression."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .flavors import adapt, flags_comment
from .models import Anchor, Formula
from .patterns import generate_field_body


@dataclass
class GenerateResult:
    regex: str
    flavor_regex: str
    flags_comment: str
    python_flags: int
    error: str | None = None


_ANCHOR_BEGIN = {
    "anywhere": "",
    "string": r"\A",
    "line": r"^",
    "word": r"\b",
    "attempt": r"\G",
}
_ANCHOR_END = {
    "anywhere": "",
    "string": r"\Z",
    "line": r"$",
    "word": r"\b",
    "attempt": r"\G",
}


def generate(formula: Formula) -> GenerateResult:
    if not formula.fields:
        return GenerateResult(
            regex="",
            flavor_regex="",
            flags_comment="(none)",
            python_flags=0,
            error="No fields yet. Add one or Mark text in Samples.",
        )

    parts: list[str] = []
    for fld in formula.fields:
        try:
            body = _field_body(formula, fld)
        except Exception as exc:  # pragma: no cover - defensive
            return GenerateResult("", "", "(none)", 0, f"Lỗi field #{fld.fid}: {exc}")
        body = _wrap(body, fld.capture, fld.name, formula.group_style)
        body = _quantify(body, fld.repeat_min, fld.repeat_max, fld.optional)
        parts.append(body)

    core = "".join(parts)
    regex = _ANCHOR_BEGIN[formula.begin] + core + _ANCHOR_END[formula.end]
    flavored = adapt(regex, formula.flavor)

    line_anchors = formula.begin == "line" or formula.end == "line"
    flags = 0
    if formula.flags_ignorecase:
        flags |= re.IGNORECASE
    if formula.flags_multiline or line_anchors:
        flags |= re.MULTILINE
    if formula.flags_dotall:
        flags |= re.DOTALL

    return GenerateResult(
        regex=regex,
        flavor_regex=flavored,
        flags_comment=flags_comment(
            formula.flavor,
            formula.flags_ignorecase,
            formula.flags_multiline or line_anchors,
            formula.flags_dotall,
        ),
        python_flags=flags,
    )



def _as_fid(raw) -> int | None:
    try:
        n = int(str(raw or "").strip())
    except ValueError:
        return None
    return n if n > 0 else None


def _capture_index(formula: Formula, fid: int) -> int:
    n = 0
    for f in formula.fields:
        if f.capture:
            n += 1
        if f.fid == fid:
            return n if f.capture else 0
    return 0


def _field_body(formula: Formula, fld) -> str:
    if fld.pattern == "field_pattern":
        src = formula.field_by_id(_as_fid(fld.options.get("source")) or 0)
        if src is None or src.fid == fld.fid:
            return r"(?!)"
        if src.pattern in ("field_pattern", "field_text"):
            return r"(?!)"
        return generate_field_body(src.pattern, src.options, formula.strictness)
    if fld.pattern == "field_text":
        src = formula.field_by_id(_as_fid(fld.options.get("source")) or 0)
        if src is None or src.fid == fld.fid:
            return r"(?!)"
        idx = _capture_index(formula, src.fid)
        if idx:
            return rf"\{idx}"
        return r"(?!)"
    return generate_field_body(fld.pattern, fld.options, formula.strictness)


def _wrap(body: str, capture: bool, name: str, style: str = "numbered") -> str:
    if not capture:
        return f"(?:{body})"
    if style != "named":
        return f"({body})"
    safe = re.sub(r"[^A-Za-z0-9_]", "", name) or "g"
    if safe[0].isdigit():
        safe = "g" + safe
    return f"(?P<{safe}>{body})"


def _quantify(body: str, lo: int, hi: int, optional: bool) -> str:
    if optional:
        lo = 0
    lo = max(0, lo)
    if hi < 0:
        if lo == 0:
            return f"(?:{body})*"
        if lo == 1:
            return f"(?:{body})+"
        return f"(?:{body}){{{lo},}}"
    if lo == 1 and hi == 1:
        return body
    if lo == 0 and hi == 1:
        return f"(?:{body})?"
    if lo == hi:
        return f"(?:{body}){{{lo}}}"
    return f"(?:{body}){{{lo},{hi}}}"


def test_matches(regex: str, flags: int, text: str) -> list[dict]:
    """Run the generated regex against samples (always via Python re)."""
    if not regex:
        return []
    try:
        compiled = re.compile(regex, flags)
    except re.error:
        return []
    rows = []
    for i, m in enumerate(compiled.finditer(text), start=1):
        rows.append(
            {
                "n": i,
                "start": m.start(),
                "end": m.end(),
                "text": m.group(0),
                "groups": m.groupdict() or {str(i): g for i, g in enumerate(m.groups(), 1)},
            }
        )
    return rows


def highlight_samples(text: str, matches: list[dict]) -> str:
    """Rich markup with matches wrapped in bold reverse."""
    if not matches:
        return text.replace("[", "\\[")
    spans = [(m["start"], m["end"]) for m in matches]
    spans.sort()
    out: list[str] = []
    cursor = 0
    for start, end in spans:
        if start < cursor:
            continue
        out.append(_esc(text[cursor:start]))
        out.append("[bold reverse]")
        out.append(_esc(text[start:end]))
        out.append("[/]")
        cursor = end
    out.append(_esc(text[cursor:]))
    return "".join(out)


def _esc(s: str) -> str:
    return s.replace("[", "\\[")

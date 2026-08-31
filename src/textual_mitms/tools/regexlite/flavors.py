"""Flavor-specific rewrites of a generated Python-style regex."""

from __future__ import annotations

import re

from .models import Flavor

FLAVOR_LABELS: dict[Flavor, str] = {
    "python": "Python re",
    "javascript": "JavaScript",
    "pcre": "PCRE / PHP / Perl",
    "dotnet": ".NET / C#",
    "java": "Java",
}

# Flags the caller should enable when using the regex.
FLAVOR_FLAG_HINTS: dict[Flavor, dict[str, str]] = {
    "python": {"i": "re.I", "m": "re.M", "s": "re.S"},
    "javascript": {"i": "i", "m": "m", "s": "s"},
    "pcre": {"i": "i", "m": "m", "s": "s"},
    "dotnet": {"i": "RegexOptions.IgnoreCase", "m": "RegexOptions.Multiline", "s": "RegexOptions.Singleline"},
    "java": {"i": "Pattern.CASE_INSENSITIVE", "m": "Pattern.MULTILINE", "s": "Pattern.DOTALL"},
}


def adapt(regex: str, flavor: Flavor) -> str:
    """Convert Python named groups to the target flavor."""
    if flavor == "python":
        return regex
    # (?P<name>...) → (?<name>...)
    return re.sub(r"\(\?P<([A-Za-z_][A-Za-z0-9_]*)>", r"(?<\1>", regex)


def flags_comment(flavor: Flavor, ignorecase: bool, multiline: bool, dotall: bool) -> str:
    hints = FLAVOR_FLAG_HINTS[flavor]
    used = []
    if ignorecase:
        used.append(hints["i"])
    if multiline:
        used.append(hints["m"])
    if dotall:
        used.append(hints["s"])
    return ", ".join(used) if used else "(none)"

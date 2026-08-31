"""Source-code snippets for the Use panel."""

from __future__ import annotations

from .models import ActionKind, Flavor


def _py_flags(i: bool, m: bool, s: bool) -> str:
    parts = []
    if i:
        parts.append("re.I")
    if m:
        parts.append("re.M")
    if s:
        parts.append("re.S")
    return " | ".join(parts) if parts else "0"


def snippet_python(regex: str, action: ActionKind, replacement: str, i: bool, m: bool, s: bool) -> str:
    flags = _py_flags(i, m, s)
    if action == "replace":
        return (
            "import re\n\n"
            f"pattern = re.compile(r'''{regex}''', {flags})\n"
            f"result = pattern.sub({replacement!r}, text)\n"
        )
    if action == "split":
        return (
            "import re\n\n"
            f"pattern = re.compile(r'''{regex}''', {flags})\n"
            "parts = pattern.split(text)\n"
        )
    return (
        "import re\n\n"
        f"pattern = re.compile(r'''{regex}''', {flags})\n"
        "for match in pattern.finditer(text):\n"
        "    print(match.group(0), match.groups())\n"
    )


def snippet_javascript(regex: str, action: ActionKind, replacement: str, i: bool, m: bool, s: bool) -> str:
    flags = "".join(x for x, on in (("i", i), ("m", m), ("s", s)) if on)
    if action == "replace":
        return (
            f"const pattern = /{regex}/{flags}g;\n"
            f"const result = text.replace(pattern, {replacement!r});\n"
        )
    if action == "split":
        return f"const pattern = /{regex}/{flags}/;\nconst parts = text.split(pattern);\n"
    return (
        f"const pattern = /{regex}/{flags}g;\n"
        "for (const match of text.matchAll(pattern)) {\n"
        "  console.log(match[0], match.slice(1));\n"
        "}\n"
    )


def snippet_java(regex: str, action: ActionKind, replacement: str, i: bool, m: bool, s: bool) -> str:
    flags = []
    if i:
        flags.append("Pattern.CASE_INSENSITIVE")
    if m:
        flags.append("Pattern.MULTILINE")
    if s:
        flags.append("Pattern.DOTALL")
    flag_s = " | ".join(flags) if flags else "0"
    escaped = regex.replace("\\", "\\\\").replace('"', '\\"')
    if action == "replace":
        return (
            "import java.util.regex.*;\n\n"
            f"Pattern pattern = Pattern.compile(\"{escaped}\", {flag_s});\n"
            "Matcher matcher = pattern.matcher(text);\n"
            f"String result = matcher.replaceAll(\"{replacement}\");\n"
        )
    if action == "split":
        return (
            "import java.util.regex.*;\n\n"
            f"Pattern pattern = Pattern.compile(\"{escaped}\", {flag_s});\n"
            "String[] parts = pattern.split(text);\n"
        )
    return (
        "import java.util.regex.*;\n\n"
        f"Pattern pattern = Pattern.compile(\"{escaped}\", {flag_s});\n"
        "Matcher matcher = pattern.matcher(text);\n"
        "while (matcher.find()) {\n"
        "    System.out.println(matcher.group());\n"
        "}\n"
    )


def snippet_csharp(regex: str, action: ActionKind, replacement: str, i: bool, m: bool, s: bool) -> str:
    flags = []
    if i:
        flags.append("RegexOptions.IgnoreCase")
    if m:
        flags.append("RegexOptions.Multiline")
    if s:
        flags.append("RegexOptions.Singleline")
    flag_s = " | ".join(flags) if flags else "RegexOptions.None"
    escaped = regex.replace("\\", "\\\\").replace('"', '\\"')
    if action == "replace":
        return (
            "using System.Text.RegularExpressions;\n\n"
            f"var pattern = new Regex(\"{escaped}\", {flag_s});\n"
            f"var result = pattern.Replace(text, \"{replacement}\");\n"
        )
    if action == "split":
        return (
            "using System.Text.RegularExpressions;\n\n"
            f"var pattern = new Regex(\"{escaped}\", {flag_s});\n"
            "var parts = pattern.Split(text);\n"
        )
    return (
        "using System.Text.RegularExpressions;\n\n"
        f"var pattern = new Regex(\"{escaped}\", {flag_s});\n"
        "foreach (Match match in pattern.Matches(text)) {\n"
        "    Console.WriteLine(match.Value);\n"
        "}\n"
    )


def render_snippet(
    language: str,
    regex: str,
    action: ActionKind,
    replacement: str,
    i: bool,
    m: bool,
    s: bool,
) -> str:
    table = {
        "python": snippet_python,
        "javascript": snippet_javascript,
        "java": snippet_java,
        "csharp": snippet_csharp,
    }
    fn = table.get(language, snippet_python)
    return fn(regex, action, replacement, i, m, s)

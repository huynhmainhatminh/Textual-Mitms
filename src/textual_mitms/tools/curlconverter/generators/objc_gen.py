# core/generators/objc_gen.py
"""Sinh code Objective-C từ IR curl: url, method, headers, auth, files_form, data_body.

objective_c → Foundation NSURLSession
  NSMutableURLRequest requestWithURL:cachePolicy:timeoutInterval:
  setHTTPMethod: / setValue:forHTTPHeaderField: / setHTTPBody:
  dataTaskWithRequest:completionHandler:
"""

import base64
import re

from . import register_generator
from .utils import escape_string


def _get_headers(data: dict) -> dict:
    headers = data.get("headers") or {}
    return headers if isinstance(headers, dict) else {}


def _get_files(data: dict) -> dict:
    files = data.get("files_form") or {}
    return files if isinstance(files, dict) else {}


def _auth_pair(auth) -> tuple:
    if not auth:
        return "", ""
    user = auth[0] if len(auth) > 0 else ""
    password = auth[1] if len(auth) > 1 else ""
    return ("" if user is None else str(user), "" if password is None else str(password))


def _objc_str(value) -> str:
    """Literal NSString @\"...\". Escape \\ \" và ký tự điều khiển."""
    if value is None:
        value = ""
    text = escape_string(str(value))
    out = []
    for char in text:
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        else:
            out.append(char)
    return '@"' + "".join(out) + '"'


def _is_file_handle_expr(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith("open(") and stripped.endswith(")")


def _path_from_open(expr: str):
    match = re.match(r"""^open\(\s*(['"])((?:\\.|(?!\1).)*)\1""", expr.strip())
    if not match:
        match = re.match(r"""^open\(\s*(['"])(.*?)\1""", expr.strip())
    if not match:
        return None
    return match.group(2).replace("\\'", "'").replace('\\"', '"')


def _unwrap_quoted(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _utf8_data(nsstring_expr: str) -> str:
    return f"[{nsstring_expr} dataUsingEncoding:NSUTF8StringEncoding]"


@register_generator("objective_c")
def generate_objective_c(data: dict) -> str:
    files_form = _get_files(data)
    url = data.get("url") or ""
    method = str(data.get("method") or "GET").upper()

    lines = [
        "#import <Foundation/Foundation.h>",
        "",
        "int main(int argc, const char * argv[]) {",
        "    @autoreleasepool {",
        "        dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);",
        "",
        "        NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:"
        + _objc_str(url)
        + "]",
        "                                                           cachePolicy:NSURLRequestUseProtocolCachePolicy",
        "                                                       timeoutInterval:10.0];",
        f"        [request setHTTPMethod:{_objc_str(method)}];",
        "",
    ]

    for key, value in _get_headers(data).items():
        if files_form and str(key).lower() == "content-type":
            continue
        lines.append(
            "        [request setValue:"
            + _objc_str("" if value is None else value)
            + " forHTTPHeaderField:"
            + _objc_str(key)
            + "];"
        )

    auth = data.get("auth")
    if auth:
        user, password = _auth_pair(auth)
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        lines.append(
            "        [request setValue:"
            + _objc_str("Basic " + token)
            + ' forHTTPHeaderField:@"Authorization"];'
        )

    if files_form:
        boundary = "---011000010111000001101001"
        lines.extend(
            [
                "",
                f"        NSString *boundary = {_objc_str(boundary)};",
                '        NSString *contentType = [NSString stringWithFormat:@"multipart/form-data; boundary=%@", boundary];',
                '        [request setValue:contentType forHTTPHeaderField:@"Content-Type"];',
                "        NSMutableData *body = [NSMutableData data];",
            ]
        )
        for key, raw in files_form.items():
            value = "" if raw is None else str(raw)
            lines.append(
                "        [body appendData:"
                + _utf8_data('[NSString stringWithFormat:@"--%@\\r\\n", boundary]')
                + "];"
            )
            if _is_file_handle_expr(value):
                path = _path_from_open(value) or value
                lines.append(
                    "        [body appendData:"
                    + _utf8_data(
                        "[NSString stringWithFormat:"
                        + '@"Content-Disposition: form-data; name=\\"%@\\"; filename=\\"%@\\"\\r\\n", '
                        + _objc_str(key)
                        + ", "
                        + _objc_str(path)
                        + "]"
                    )
                    + "];"
                )
                lines.append(
                    "        [body appendData:"
                    + _utf8_data('@"Content-Type: application/octet-stream\\r\\n\\r\\n"')
                    + "];"
                )
                lines.append(
                    "        [body appendData:[NSData dataWithContentsOfFile:"
                    + _objc_str(path)
                    + "]];"
                )
                lines.append(
                    "        [body appendData:" + _utf8_data('@"\\r\\n"') + "];"
                )
            else:
                text = _unwrap_quoted(value)
                lines.append(
                    "        [body appendData:"
                    + _utf8_data(
                        "[NSString stringWithFormat:"
                        + '@"Content-Disposition: form-data; name=\\"%@\\"\\r\\n\\r\\n", '
                        + _objc_str(key)
                        + "]"
                    )
                    + "];"
                )
                lines.append(
                    "        [body appendData:"
                    + _utf8_data("[NSString stringWithFormat:@\"%@\\r\\n\", " + _objc_str(text) + "]")
                    + "];"
                )
        lines.append(
            "        [body appendData:"
            + _utf8_data('[NSString stringWithFormat:@"--%@--\\r\\n", boundary]')
            + "];"
        )
        lines.append("        [request setHTTPBody:body];")
    elif data.get("data_body"):
        lines.append("")
        lines.append(
            "        NSData *postData = "
            + _utf8_data(_objc_str(data.get("data_body")))
            + ";"
        )
        lines.append("        [request setHTTPBody:postData];")

    lines.extend(
        [
            "",
            "        NSURLSession *session = [NSURLSession sharedSession];",
            "        NSURLSessionDataTask *dataTask = [session dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {",
            "            if (error) {",
            '                NSLog(@"Lỗi: %@", error);',
            "            } else {",
            "                NSString *responseString = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];",
            '                printf("%s\\n", [responseString UTF8String]);',
            "            }",
            "            dispatch_semaphore_signal(semaphore);",
            "        }];",
            "        [dataTask resume];",
            "        dispatch_semaphore_wait(semaphore, DISPATCH_TIME_FOREVER);",
            "    }",
            "    return 0;",
            "}",
        ]
    )
    return "\n".join(lines)

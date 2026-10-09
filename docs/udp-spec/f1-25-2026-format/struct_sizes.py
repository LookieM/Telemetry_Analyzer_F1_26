"""Compute packed (#pragma pack 1) sizes of the structs / unions / classes in a folder of C headers.

The headers are read as text only; nothing from them is executed.
"""
import pathlib
import re
import sys

PRIM = {"uint8_t": 1, "int8_t": 1, "char": 1, "uint16_t": 2, "int16_t": 2, "uint32_t": 4, "int32_t": 4,
        "float": 4, "uint64_t": 8, "int64_t": 8, "double": 8}

src = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in pathlib.Path(sys.argv[1]).glob("*.h"))
src = re.sub(r"//[^\n]*", "", src)
src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def matching_brace(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced braces")


decls = {}  # name -> (kind, body)
for m in re.finditer(r"\b(struct|class|union)\s+(\w+)\s*(?::\s*public\s+\w+\s*)?\{", src):
    end = matching_brace(src, m.end() - 1)
    body = src[m.end():end]
    if m.group(1) == "class":
        priv = re.search(r"private:(.*)", body, flags=re.S)
        body = re.split(r"\b(?:public|protected):", priv.group(1))[0] if priv else ""
    decls[m.group(2)] = (m.group(1), body)

cache: dict[str, int] = {}


def fields_size(kind: str, body: str) -> int:
    parts = []
    # anonymous nested struct members: struct { ... } Name;
    while True:
        m = re.search(r"\bstruct\s*\{", body)
        if not m:
            break
        end = matching_brace(body, m.end() - 1)
        tail = re.match(r"\s*\w+\s*;", body[end + 1:])
        parts.append(fields_size("struct", body[m.end():end]))
        body = body[:m.start()] + body[end + 1 + (tail.end() if tail else 0):]
    for typ, _field, dims in re.findall(r"^\s*(\w+)\s+(\w+)((?:\s*\[\s*\d+\s*\])*)\s*;", body, flags=re.M):
        if typ in ("return", "using", "virtual"):
            continue
        n = 1
        for d in re.findall(r"\d+", dims):
            n *= int(d)
        parts.append(size_of(typ) * n)
    return max(parts, default=0) if kind == "union" else sum(parts)


def size_of(name: str) -> int:
    if name in PRIM:
        return PRIM[name]
    if name not in cache:
        kind, body = decls[name]
        cache[name] = fields_size(kind, body)
    return cache[name]


for name, (kind, _body) in decls.items():
    if kind == "class" and name != "PHeader":
        print(f"{name:34s} {29 + size_of(name):5d}")

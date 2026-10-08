#!/usr/bin/env python3
"""把文件首行的 version 标记刷成 SHA-256（带盐）。

版本标记的算法（引擎侧算 park 的 version 用同一套）：
    version = sha256(SALT + 首行去掉 version 值之后的全文).hexdigest()

用法：
    python scripts/stamp_version.py docs/design/format       # 写入
    python scripts/stamp_version.py docs/design/format -c    # 只校验，不符退出 1（给门禁用）
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

# 盐。改动它等于改动所有 version 值，改前先想清楚。
SALT = b"oncasket/format"

# 首行形如：encoding: utf-8 version: <64 位十六进制>
HEAD = re.compile(
    r"^(?P<lead>encoding:\s*\S+\s+version:)[ \t]*(?P<hash>[0-9a-f]*)[ \t]*$"
)


def split_head(text: str) -> tuple[re.Match[str], list[str]]:
    lines = text.splitlines(keepends=True)
    match = HEAD.match(lines[0].rstrip("\r\n")) if lines else None
    if match is None:
        raise SystemExit("首行不是 `encoding: … version: …`，无法定位版本标记")
    return match, lines


def digest(text: str) -> str:
    """首行保留 `encoding: … version:`、值抹空，其余原样，再带盐算 SHA-256。"""
    match, lines = split_head(text)
    body = "".join([match.group("lead") + "\n", *lines[1:]])
    return hashlib.sha256(SALT + body.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("-c", "--check", action="store_true", help="只校验不写入")
    args = parser.parse_args()

    text = args.path.read_bytes().decode("utf-8")
    match, lines = split_head(text)
    want = digest(text)

    if args.check:
        if match.group("hash") != want:
            print(f"{args.path}: 版本标记不符\n  文件 {match.group('hash') or '(空)'}\n  应为 {want}")
            return 1
        print(f"{args.path}: OK")
        return 0

    lines[0] = f"{match.group('lead')} {want}\n"
    args.path.write_bytes("".join(lines).encode("utf-8"))
    print(f"{args.path}: version → {want}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

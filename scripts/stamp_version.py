#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""把文件首行的 version 标记刷成 SHA-256（带盐）。

版本标记的算法（引擎侧算 park 的 version 用同一套）：
    version = sha256(SALT + 首行去掉 version 值之后的全文).hexdigest()

用法：
    python scripts/stamp_version.py config/format.txt docs/design/gate.txt   # 写入
    python scripts/stamp_version.py -c config/*.txt docs/design/*.txt   # 门禁 G04：不符退出 1
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


# 盐。改动它等于改动所有 version 值，改前先想清楚。
SALT = b"oncasket/format"

# 首行形如：encoding: utf-8 version: <64 位十六进制>，尾随标点（如 ;）原样保留
HEAD = re.compile(
    r"^(?P<lead>encoding:\s*\S+\s+version:)[ \t]*(?P<hash>[0-9a-f]*)(?P<tail>[ \t;]*)$"
)


def split_head(text: str) -> tuple[re.Match[str], list[str]]:
    """拆出首行标记与全文行列表。

    Args:
        text: 全文。

    Returns:
        (首行匹配对象, 保留行尾的行列表)。

    Raises:
        SystemExit: 首行不是 `encoding: … version: …` 形态。
    """
    lines = text.splitlines(keepends=True)
    match = HEAD.match(lines[0].rstrip("\r\n")) if lines else None
    if match is None:
        raise SystemExit("首行不是 `encoding: … version: …`，无法定位版本标记")
    return match, lines


def digest(text: str) -> str:
    """算内容指纹：首行保留 `encoding: … version:` 与尾随标点、值抹空，其余原样，再带盐算 SHA-256。

    Args:
        text: 全文。

    Returns:
        64 位十六进制摘要。
    """
    match, lines = split_head(text)
    body = "".join([match.group("lead") + match.group("tail") + "\n", *lines[1:]])
    return hashlib.sha256(SALT + body.encode("utf-8")).hexdigest()


def stamp(path: Path, *, check: bool) -> bool:
    """盖一个文件的标记，或只校验。

    Args:
        path: 结构文件路径。
        check: 为真时只比不写。

    Returns:
        check 模式下是否通过；写入模式恒为真。
    """
    text = path.read_bytes().decode("utf-8")
    match, lines = split_head(text)
    want = digest(text)

    if not check:
        lines[0] = f"{match.group('lead')} {want}{match.group('tail')}\n"
        path.write_bytes("".join(lines).encode("utf-8"))
        print(f"{path}: version → {want}")
        return True

    if match.group("hash") != want:
        print(f"{path}: 版本标记不符\n  文件 {match.group('hash') or '(空)'}\n  应为 {want}")
        return False
    print(f"{path}: OK")
    return True


def main() -> int:
    """命令行入口。

    Returns:
        进程退出码：全部通过 0，否则 1。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, nargs="+")
    parser.add_argument("-c", "--check", action="store_true", help="只校验不写入")
    args = parser.parse_args()

    ok = True
    for path in args.path:
        ok = stamp(path, check=args.check) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

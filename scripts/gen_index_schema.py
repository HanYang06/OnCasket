#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""从 config/index_db.sql 生成 src/oncasket/_index/schema_gen.py。

事实依据只有一处：[`config/index_db.sql`](../../config/index_db.sql)——引擎侧的建库 DDL
与基准指纹都由这里生成，不人肉粘贴（索引库 §011）。改结构先改 `.sql`，再跑本脚本；
门禁 G21 用 `--check` 比对，手改生成物必红。

新版指纹**增量追加**、不删旧版：库的指纹高过本引擎声明的集合，照样拒绝连接（§012）。

用法：
    uv run python scripts/gen_index_schema.py            # 生成
    uv run python scripts/gen_index_schema.py --check    # 校验，不一致退出 1
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

from oncasket._index import fingerprint


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "config" / "index_db.sql"
OUTPUT = ROOT / "src" / "oncasket" / "_index" / "schema_gen.py"

GENERATE_COMMAND = "uv run python scripts/gen_index_schema.py"
CHECK_COMMAND = "uv run python scripts/gen_index_schema.py --check"

#: 生成物里的指纹行；重生成时照它把旧指纹读回来
FINGERPRINT_LINE = re.compile(r'^\s*"([0-9a-f]{64})",$', re.MULTILINE)

HEADER = '''# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""索引库建库 DDL 与基准指纹（**自动生成，勿手改**）。

由 `scripts/gen_index_schema.py` 从 `config/index_db.sql` 生成：改结构先改 `.sql`，
再跑生成脚本；门禁 G21 用 `--check` 比对，手改这份文件必红。

- `DDL`：`config/index_db.sql` 的逐字副本，建库时整段执行；
- `SCHEMA_FINGERPRINTS`：基准指纹集合，新版**增量追加**、不删旧版（索引库 §011）。
"""
'''


def _escape(text: str) -> str:
    """把文本塞进 `\"\"\"` 字面量：转义反斜杠与连续引号。

    Args:
        text: 原始文本。

    Returns:
        可直接写进三引号字面量的文本。
    """
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def fingerprint_of(ddl: str) -> str:
    """在内存库里整段跑一遍 DDL，再算结构指纹。

    Args:
        ddl: 建库脚本全文。

    Returns:
        64 位十六进制小写摘要。
    """
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(ddl)
        return fingerprint.compute(connection)
    finally:
        connection.close()


def _known_fingerprints() -> list[str]:
    """把生成物里已有的指纹读回来。

    Returns:
        指纹列表，按文件里的顺序；生成物不存在时为空。
    """
    if not OUTPUT.is_file():
        return []
    return FINGERPRINT_LINE.findall(OUTPUT.read_text(encoding="utf-8"))


def render(ddl: str, versions: list[str]) -> str:
    """渲染生成物全文。

    Args:
        ddl: 建库脚本全文。
        versions: 基准指纹，按增量顺序。

    Returns:
        生成物文本，UTF-8、LF、末尾单换行；`DDL` 与 `.sql` 逐字相同。
    """
    body = ddl if ddl.endswith("\n") else f"{ddl}\n"
    head = f'{HEADER}\nDDL: str = """\\\n'
    entries = "".join(f'    "{version}",\n' for version in versions)
    tail = '"""\n\nSCHEMA_FINGERPRINTS: tuple[str, ...] = (\n'
    return f"{head}{_escape(body)}{tail}{entries})\n"


def collect() -> tuple[str, str]:
    """算生成物文本与它对应的指纹。

    Returns:
        (全文, 当前指纹)。
    """
    ddl = SOURCE.read_text(encoding="utf-8")
    current = fingerprint_of(ddl)
    versions = _known_fingerprints()
    if current not in versions:
        versions.append(current)
    return render(ddl, versions), current


def _check(text: str, current: str) -> int:
    """比对生成物是否与事实依据一致。

    Args:
        text: 应当写出的全文。
        current: 当前指纹，只用于提示。

    Returns:
        进程退出码：一致 0，否则 1。
    """
    if not OUTPUT.is_file():
        print(f"{OUTPUT.name} 不存在。请先运行：{GENERATE_COMMAND}", file=sys.stderr)
        return 1
    if OUTPUT.read_text(encoding="utf-8") != text:
        print(
            f"{OUTPUT.name} 与 config/index_db.sql 不一致。请运行：{GENERATE_COMMAND}",
            file=sys.stderr,
        )
        return 1
    print(f"{OUTPUT.name} 与 config/index_db.sql 一致（指纹 {current}）。")
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口：默认生成，`--check` 只校验不写。

    Args:
        argv: 命令行参数；缺省取 `sys.argv[1:]`。

    Returns:
        进程退出码。
    """
    parser = argparse.ArgumentParser(
        prog="gen_index_schema.py",
        description="从 config/index_db.sql 生成索引库的建库 DDL 与基准指纹。",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=f"只校验生成物是否与 .sql 一致，不一致时退出码 1（供 CI 使用）：{CHECK_COMMAND}",
    )
    args = parser.parse_args(argv)

    text, current = collect()
    if args.check:
        return _check(text, current)

    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"已写入 {OUTPUT.relative_to(ROOT)}（指纹 {current}）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

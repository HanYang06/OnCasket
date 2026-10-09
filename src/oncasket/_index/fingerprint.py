# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
r"""schema 指纹：提取、全序排序、拼接与 sha256（索引库 §011）。

指纹只认**结构**，一个字节的数据都不取：

- 表：`PRAGMA table_info` 的列序（name / type / notnull / dflt_value / pk）＋
  `PRAGMA foreign_key_list`；
- 索引：`PRAGMA index_list` 的 unique / origin / partial ＋ `PRAGMA index_info` 的列序；
- 视图与触发器：规范化 SQL（折叠空白）。

算法**写死在这一处**：条目按 (`type`, `name`) 的 utf-8 字节序升序、大小写敏感；
同类对象内部保持列序 / `seqno`；字段间 `\x1f`（US），条目间 `\n`；
`sha256(b"oncasket/index_db" + 载荷)` 的十六进制小写。

`sqlite_` 开头的对象一律不收：那是 sqlite 自述表，以及 `sqlite_autoindex_*`
——UNIQUE / PRIMARY KEY 的派生物，已经由列与外键表达过了。
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Sequence


#: 盐：与库文件一一对应，改了等于换掉整套指纹
SALT = b"oncasket/index_db"
#: 字段分隔（US）
FIELD_SEP = "\x1f"
#: 条目分隔
ENTRY_SEP = "\n"
#: sqlite 自述对象与自动索引的前缀
INTERNAL_PREFIX = "sqlite_"


def _ascii(value: object) -> str:
    """把可能为 NULL 的字段转成字符串——`None` 记空串，不记 `"None"`。

    Args:
        value: 库里读出来的一个字段。

    Returns:
        字符串形式。
    """
    return "" if value is None else str(value)


def _identifier(name: str) -> str:
    """把对象名包成 SQL 标识符——表名里带引号也不至于把 PRAGMA 拆坏。

    Args:
        name: 对象名。

    Returns:
        双引号形式。
    """
    return '"' + name.replace('"', '""') + '"'


def _collapse(sql: str) -> str:
    """折叠空白：视图与触发器的规范形态只留单个空格。

    Args:
        sql: `sqlite_master` 里的原始 SQL。

    Returns:
        折叠后的 SQL。
    """
    return " ".join(sql.split())


def _table_entry(conn: sqlite3.Connection, name: str) -> list[str]:
    """提一张表：列序在前，外键在后。

    Args:
        conn: 已打开的索引库连接。
        name: 表名。

    Returns:
        `["table", 表名, 列字段…, 外键字段…]`。
    """
    fields = ["table", name]
    columns = sorted(
        conn.execute(f"PRAGMA table_info({_identifier(name)})"),
        key=lambda row: row[0],
    )
    for row in columns:
        fields += [str(row[1]), _ascii(row[2]), str(row[3]), _ascii(row[4]), str(row[5])]
    keys = sorted(
        conn.execute(f"PRAGMA foreign_key_list({_identifier(name)})"),
        key=lambda row: (row[0], row[1]),
    )
    for row in keys:
        fields += [str(row[2]), str(row[3]), _ascii(row[4]), str(row[5]), str(row[6]), str(row[7])]
    return fields


def _index_entries(conn: sqlite3.Connection, table: str) -> list[list[str]]:
    """提一张表上的显式索引。

    Args:
        conn: 已打开的索引库连接。
        table: 表名。

    Returns:
        索引条目列表；自动索引已排除。
    """
    found: list[list[str]] = []
    for row in conn.execute(f"PRAGMA index_list({_identifier(table)})"):
        name = str(row[1])
        if name.startswith(INTERNAL_PREFIX):
            continue
        fields = ["index", name, str(row[2]), str(row[3]), str(row[4])]
        columns = sorted(
            conn.execute(f"PRAGMA index_info({_identifier(name)})"),
            key=lambda item: item[0],
        )
        fields += [_ascii(column[2]) for column in columns]
        found.append(fields)
    return found


def _sort_key(entry: Sequence[str]) -> tuple[bytes, bytes]:
    """条目全序：先按类型、再按名字，都取 utf-8 字节序、大小写敏感。

    Args:
        entry: 一个条目。

    Returns:
        排序键。
    """
    return (entry[0].encode("utf-8"), entry[1].encode("utf-8"))


def extract(conn: sqlite3.Connection) -> list[list[str]]:
    """把库的结构提成条目列表。

    Args:
        conn: 已打开的索引库连接。

    Returns:
        条目列表，每条形如 `[type, name, 字段…]`，已按 (`type`, `name`) 升序。
    """
    entries: list[list[str]] = []
    tables: list[str] = []
    for row in conn.execute("SELECT type, name, sql FROM sqlite_master"):
        kind, name = str(row[0]), str(row[1])
        if name.startswith(INTERNAL_PREFIX):
            continue
        if kind == "table":
            tables.append(name)
            entries.append(_table_entry(conn, name))
        elif kind in {"view", "trigger"}:
            entries.append([kind, name, _collapse(_ascii(row[2]))])
    for table in tables:
        entries += _index_entries(conn, table)
    entries.sort(key=_sort_key)
    return entries


def canonical(entries: Sequence[Sequence[str]]) -> str:
    r"""把条目列表拼成载荷。

    Args:
        entries: 条目列表。

    Returns:
        字段间 `\x1f`、条目间 `\n` 的字符串。
    """
    return ENTRY_SEP.join(FIELD_SEP.join(entry) for entry in entries)


def digest(entries: Sequence[Sequence[str]]) -> str:
    """算指纹。

    Args:
        entries: 条目列表。

    Returns:
        64 位十六进制小写摘要。
    """
    return hashlib.sha256(SALT + canonical(entries).encode("utf-8")).hexdigest()


def compute(conn: sqlite3.Connection) -> str:
    """提取 ＋ 拼接 ＋ 摘要，一步到位。

    Args:
        conn: 已打开的索引库连接。

    Returns:
        64 位十六进制小写摘要。
    """
    return digest(extract(conn))

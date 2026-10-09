# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""索引库连接：pragma 与打开时的指纹守卫（索引库 §008、§011–§012）。

- 位置：`<hub>/index/index.db`（[hub 布局 §005](../../../docs/design/hub.md)）——不是 park，
  它的 WAL 边文件（`index.db-wal` / `index.db-shm`）也一并归它；
- 版本：运行时 SQLite 低于 3.37 直接拒——`STRICT` 表与所需 pragma 的下限（§008）；
- 每次连接都算一遍结构指纹并与本引擎声明的集合比对；不在集合里就是**另一套 schema**：
  拒绝连接并抛异常，**不降级、不静默重建**（§012）。

`create` 与 `load` 刻意分开：建库与开库是两件事，合并只会让「路径写错了」变成
「悄悄建了个新库」。
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from oncasket._errors import OnCasketError, SchemaMismatchError, SqliteTooOldError
from oncasket._index import fingerprint, schema_gen


if TYPE_CHECKING:
    from pathlib import Path


#: SQLite 下限：`STRICT` 表与所需 pragma 都要它
MIN_SQLITE_VERSION = (3, 37)


def _check_runtime() -> None:
    """查运行时 SQLite 版本。

    Raises:
        SqliteTooOldError: 低于 `MIN_SQLITE_VERSION`。
    """
    if sqlite3.sqlite_version_info[:2] < MIN_SQLITE_VERSION:
        raise SqliteTooOldError(
            f"SQLite 需要 {'.'.join(map(str, MIN_SQLITE_VERSION))} 起，"
            f"当前是 {sqlite3.sqlite_version}"
        )


def _connect(path: Path) -> sqlite3.Connection:
    """开一个连接并把 pragma 立好。

    Args:
        path: 库文件路径。

    Returns:
        已开好外键与 WAL 的连接。

    Raises:
        sqlite3.Error: 文件不是库 / 打不开；连接已关，不留半开句柄。
    """
    connection = sqlite3.connect(path)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
    except sqlite3.Error:
        connection.close()
        raise
    return connection


def _guard(connection: sqlite3.Connection) -> None:
    """算结构指纹，与本引擎声明的集合比对。

    Args:
        connection: 已打开的连接。

    Raises:
        SchemaMismatchError: 指纹不在集合里。
    """
    actual = fingerprint.compute(connection)
    if actual not in schema_gen.SCHEMA_FINGERPRINTS:
        raise SchemaMismatchError(
            f"索引库 schema 指纹 {actual} 不在本引擎声明的集合里：拒绝连接，不降级、不重建"
        )


class IndexStore:
    """一个已过版本检查与指纹守卫的索引库连接。"""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        """接管一个已经开好的连接。

        Args:
            path: 库文件路径。
            connection: 已开好 pragma 的连接。
        """
        self._path = path
        self._connection = connection

    @classmethod
    def create(cls, path: Path) -> IndexStore:
        """按事实依据建库，并当场验一遍生成物与 DDL 自洽。

        Args:
            path: 库文件路径；父目录不在就建。

        Returns:
            新库的连接。

        Raises:
            SqliteTooOldError: 运行时 SQLite 低于下限。
            SchemaMismatchError: 建出来的结构与声明的基准指纹不符——生成物过期。
        """
        _check_runtime()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = _connect(path)
        try:
            connection.executescript(schema_gen.DDL)
            connection.commit()
            actual = fingerprint.compute(connection)
        except sqlite3.Error:
            connection.close()
            raise
        if actual not in schema_gen.SCHEMA_FINGERPRINTS:
            connection.close()
            raise SchemaMismatchError(
                f"建库结构的指纹 {actual} 不在声明集合里：生成物过期，重跑生成脚本"
            )
        return cls(path, connection)

    @classmethod
    def load(cls, path: Path) -> IndexStore:
        """打开一个已有的库，先过指纹守卫。

        Args:
            path: 库文件路径。

        Returns:
            过守卫的连接。

        Raises:
            FileNotFoundError: 库文件不存在——开库不建库。
            SqliteTooOldError: 运行时 SQLite 低于下限。
            SchemaMismatchError: 指纹不在声明集合里（§012）。
        """
        _check_runtime()
        if not path.is_file():
            raise FileNotFoundError(f"索引库不存在：{path}")
        connection = _connect(path)
        try:
            _guard(connection)
        except (OnCasketError, sqlite3.Error):
            connection.close()
            raise
        return cls(path, connection)

    @property
    def path(self) -> Path:
        """库文件路径。"""
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        """底层连接——域内读写用它，域外别拿它绕过守卫。"""
        return self._connection

    def close(self) -> None:
        """关掉连接。"""
        self._connection.close()

    def __enter__(self) -> IndexStore:
        """进上下文。

        Returns:
            自己。
        """
        return self

    def __exit__(self, *args: object) -> None:
        """出上下文就关连接。

        Args:
            *args: 异常三元组，忽略。
        """
        self.close()

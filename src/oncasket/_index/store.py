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

import enum
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

from oncasket._errors import NotFoundError, OnCasketError, SchemaMismatchError, SqliteTooOldError
from oncasket._index import fingerprint, schema_gen


if TYPE_CHECKING:
    from pathlib import Path


#: SQLite 下限：`STRICT` 表与所需 pragma 都要它
MIN_SQLITE_VERSION = (3, 37)

#: `block.state` 的三个取值（事实依据 [`index_db.sql`](../../../config/index_db.sql) 的 CHECK）
STATE_PENDING = "pending"
STATE_OK = "ok"
STATE_ERROR = "error"

#: 总表的一行怎么取——SQL **逐个字面写死**，既不拼字符串（SQL 拼接会招 S608），也好看
_SELECT_ROW_SQL = (
    "SELECT block_id, created_at, budget_slot, block_size, global_hash, state, park, first_slot_id "
    "FROM block WHERE block_id = ?"
)
_SELECT_ALL_SQL = (
    "SELECT block_id, created_at, budget_slot, block_size, global_hash, state, park, first_slot_id "
    "FROM block ORDER BY created_at, block_id"
)
_INSERT_ROW_SQL = (
    "INSERT INTO block (block_id, created_at, budget_slot, block_size, global_hash, state, park, "
    "first_slot_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


class Role(enum.StrEnum):
    """逻辑块的身份（索引库 §006）：身份由**表归属**表达，不在总表上立 `kind` 列。"""

    DATA = "data"
    INDEX = "index"


#: 身份 → 插入语句。表名参数化不了，所以用字面映射，不拼 SQL（少一分 SQL 拼接的味道）。
_INSERT_IDENTITY_SQL = {
    Role.DATA: "INSERT INTO data_block (block_id, kind) VALUES (?, ?)",
    Role.INDEX: "INSERT INTO index_block (block_id, kind) VALUES (?, ?)",
}


@dataclass(frozen=True, slots=True)
class BlockRow:
    """`block` 总表的一行——身份、地址、状态。"""

    block_id: bytes
    created_at: int
    budget_slot: int
    block_size: int
    global_hash: bytes
    state: str
    park: str | None
    first_slot_id: int | None

    @property
    def has_address(self) -> bool:
        """地址有没有回流（`park` 与 `first_slot_id` 同生同灭，见事实依据的两条 CHECK）。"""
        return self.park is not None and self.first_slot_id is not None


def _to_row(record: sqlite3.Row) -> BlockRow:
    """`sqlite3.Row` → `BlockRow`。

    Args:
        record: 按 `_ROW_COLUMNS` 取出来的一行。

    Returns:
        索引行；`park` / `first_slot_id` 在库里可为 NULL，取出来就是 `None`。
    """
    park = record["park"]
    first_slot_id = record["first_slot_id"]
    return BlockRow(
        block_id=bytes(record["block_id"]),
        created_at=int(record["created_at"]),
        budget_slot=int(record["budget_slot"]),
        block_size=int(record["block_size"]),
        global_hash=bytes(record["global_hash"]),
        state=str(record["state"]),
        park=None if park is None else str(park),
        first_slot_id=None if first_slot_id is None else int(first_slot_id),
    )


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

    def insert(self, row: BlockRow, *, role: Role, kind: str) -> None:
        """② 写一条索引行 ＋ 它的身份行，**一个事务**（索引库 §009）。

        身份由表归属表达（§006）：总表收全量，`data_block` / `index_block` 收身份，
        两张分表都靠外键级联跟着总表走。

        Args:
            row: 要落的总表行；地址列可以为空（`state = pending` 时不回流）。
            role: 逻辑块的身份。
            kind: 身份分表里的 `kind`（开放取值，不枚举、不加 CHECK）。

        Raises:
            sqlite3.Error: 写不进去（主键撞车 / 约束不过）——事务未提交，无残留。
        """
        with self._connection:
            self._connection.execute(
                _INSERT_ROW_SQL,
                (
                    row.block_id,
                    row.created_at,
                    row.budget_slot,
                    row.block_size,
                    row.global_hash,
                    row.state,
                    row.park,
                    row.first_slot_id,
                ),
            )
            self._connection.execute(
                _INSERT_IDENTITY_SQL[role],
                (row.block_id, kind),
            )

    def get(self, block_id: bytes) -> BlockRow | None:
        """按 `block_id` 取一行。

        Args:
            block_id: 逻辑块 ID。

        Returns:
            那一行；没这号块就是 `None`。
        """
        record = self._connection.execute(_SELECT_ROW_SQL, (block_id,)).fetchone()
        return None if record is None else _to_row(record)

    def rows(self) -> list[BlockRow]:
        """列出总表的全部行，按 `created_at` ＋ `block_id` 升序。

        Returns:
            全部索引行（重建与对账要看的就是它）。
        """
        records = self._connection.execute(_SELECT_ALL_SQL).fetchall()
        return [_to_row(record) for record in records]

    def live_slots(self, park: str) -> list[tuple[int, int]]:
        """某个 park 里所有**已提交且地址已回流**的块占的槽区间。

        段表拿它当输入（空洞分配 §014 §1）：库是权威视角，段表是内存派生视图、不落盘。
        只认 `state = ok`——`pending` 那一份地址还没回流，占没占住盘上还没定。

        Args:
            park: park 名。

        Returns:
            `(first_slot_id, budget_slot)`，按 `first_slot_id` 升序。
        """
        records = self._connection.execute(
            "SELECT first_slot_id, budget_slot FROM block "
            "WHERE park = ? AND state = ? AND first_slot_id IS NOT NULL "
            "ORDER BY first_slot_id",
            (park, STATE_OK),
        ).fetchall()
        return [(int(record[0]), int(record[1])) for record in records]

    def mark_ok(self, block_id: bytes) -> None:
        """⑥ 把 `state` 翻成 `ok`（提交点，索引库 §009）。

        Args:
            block_id: 逻辑块 ID。

        Raises:
            NotFoundError: 行不在了——基准点失效，没有可提交的东西。
        """
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE block SET state = ? WHERE block_id = ?", (STATE_OK, block_id)
            )
        if cursor.rowcount == 0:
            raise NotFoundError(f"索引行不在了：{block_id.hex()}")

    def set_address(self, block_id: bytes, *, park: str, first_slot_id: int) -> None:
        """⑦ 地址回流：写 `park` ＋ `first_slot_id`（索引库 §009）。

        两列必须同生同灭（事实依据的两条 CHECK 管着），所以一次写下去。

        Args:
            block_id: 逻辑块 ID。
            park: park 名。
            first_slot_id: 链首槽 id。

        Raises:
            NotFoundError: 行不在了。
        """
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE block SET park = ?, first_slot_id = ? WHERE block_id = ?",
                (park, first_slot_id, block_id),
            )
        if cursor.rowcount == 0:
            raise NotFoundError(f"索引行不在了：{block_id.hex()}")

    def delete(self, block_id: bytes) -> bool:
        """删一行；两张身份分表靠 `ON DELETE CASCADE` 跟着走（索引库 §006）。

        Args:
            block_id: 逻辑块 ID。

        Returns:
            真删掉了一行为真；本来就没这号块为假。
        """
        with self._connection:
            cursor = self._connection.execute("DELETE FROM block WHERE block_id = ?", (block_id,))
        return cursor.rowcount == 1

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

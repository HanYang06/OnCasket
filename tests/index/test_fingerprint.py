# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""指纹的算法面：提取、全序、拼接与摘要（索引库 §011）。"""

from __future__ import annotations

import contextlib
import hashlib
import sqlite3
from typing import TYPE_CHECKING

import pytest

from oncasket._index import fingerprint, schema_gen


if TYPE_CHECKING:
    from collections.abc import Iterator


def fingerprint_of(ddl: str) -> str:
    """在一个内存库里跑一遍 DDL 再算指纹。

    Args:
        ddl: 建库脚本。

    Returns:
        指纹。
    """
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(ddl)
        return fingerprint.compute(connection)
    finally:
        connection.close()


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    """一个照事实依据建好的内存库。"""
    connection = sqlite3.connect(":memory:")
    connection.executescript(schema_gen.DDL)
    yield connection
    connection.close()


def test_the_fact_source_matches_the_baseline(conn) -> None:
    assert fingerprint.compute(conn) == schema_gen.SCHEMA_FINGERPRINTS[-1]


def test_rows_do_not_move_the_fingerprint(conn) -> None:
    before = fingerprint.compute(conn)
    conn.execute(
        "INSERT INTO block (block_id, created_at, budget_slot, block_size, global_hash, state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (b"0" * 16, 1, 2, 8192, b"hash", "pending"),
    )
    assert fingerprint.compute(conn) == before


def test_a_new_column_moves_the_fingerprint(conn) -> None:
    before = fingerprint.compute(conn)
    conn.execute("ALTER TABLE block ADD COLUMN extra TEXT")
    assert fingerprint.compute(conn) != before


def test_a_new_index_moves_the_fingerprint(conn) -> None:
    before = fingerprint.compute(conn)
    conn.execute("CREATE INDEX block_created ON block (created_at)")
    assert fingerprint.compute(conn) != before


def test_a_view_moves_the_fingerprint(conn) -> None:
    before = fingerprint.compute(conn)
    conn.execute("CREATE VIEW live_blocks AS SELECT block_id FROM block WHERE state = 'ok'")
    assert fingerprint.compute(conn) != before


def test_a_trigger_moves_the_fingerprint(conn) -> None:
    before = fingerprint.compute(conn)
    conn.execute("CREATE TRIGGER block_touch AFTER UPDATE ON block BEGIN SELECT 1; END")
    assert fingerprint.compute(conn) != before


def test_a_foreign_key_is_part_of_the_structure() -> None:
    plain = "CREATE TABLE a (x TEXT) STRICT; CREATE TABLE b (x TEXT) STRICT"
    linked = "CREATE TABLE a (x TEXT) STRICT; CREATE TABLE b (x TEXT REFERENCES a (x)) STRICT"
    assert fingerprint_of(plain) != fingerprint_of(linked)


def test_view_sql_is_whitespace_normalized() -> None:
    one = sqlite3.connect(":memory:")
    two = sqlite3.connect(":memory:")
    with contextlib.closing(one), contextlib.closing(two):
        one.execute("CREATE VIEW v AS\n   SELECT 1\n")
        two.execute("CREATE   VIEW   v   AS SELECT 1")
        assert fingerprint.compute(one) == fingerprint.compute(two)


def test_autoindexes_are_left_out() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript("CREATE TABLE t (a TEXT PRIMARY KEY, b TEXT UNIQUE) STRICT")
        names = [entry[1] for entry in fingerprint.extract(connection)]
    finally:
        connection.close()
    assert names == ["t"]


def test_entries_are_ordered_by_type_then_name(conn) -> None:
    conn.execute("CREATE VIEW a_view AS SELECT 1")
    conn.execute("CREATE VIEW z_view AS SELECT 1")
    keys = [
        (entry[0].encode("utf-8"), entry[1].encode("utf-8")) for entry in fingerprint.extract(conn)
    ]
    assert keys == sorted(keys)


def test_foreign_keys_are_extracted(conn) -> None:
    entry = next(item for item in fingerprint.extract(conn) if item[1] == "data_block")
    assert "CASCADE" in entry
    assert "block_id" in entry


def test_expression_index_columns_are_recorded_as_empty(conn) -> None:
    conn.execute("CREATE INDEX block_lower ON block (lower(park))")
    entry = next(item for item in fingerprint.extract(conn) if item[1] == "block_lower")
    assert entry[:5] == ["index", "block_lower", "0", "c", "0"]
    assert entry[5] == ""


def test_odd_table_names_are_still_readable() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript('CREATE TABLE "we""ird" (a TEXT) STRICT')
        entries = fingerprint.extract(connection)
    finally:
        connection.close()
    assert entries[0][1] == 'we"ird'


def test_digest_pins_the_separators() -> None:
    payload = b"table\x1fa\nindex\x1fb\x1f1"
    assert fingerprint.canonical([["table", "a"]]) == "table\x1fa"
    assert fingerprint.digest([["table", "a"], ["index", "b", "1"]]) == (
        hashlib.sha256(fingerprint.SALT + payload).hexdigest()
    )

# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""索引库读写：总表 ＋ 两张身份分表，以及打开时的守卫（路线 002/006/009/011/012）。"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from oncasket._errors import NotFoundError
from oncasket._index import schema_gen
from oncasket._index.store import STATE_ERROR, STATE_OK, STATE_PENDING, BlockRow, IndexStore, Role


if TYPE_CHECKING:
    from pathlib import Path


def make_store(tmp_path: Path) -> IndexStore:
    return IndexStore.create(tmp_path / "index.db")


def row(
    block_id: bytes = b"\x01" * 16,
    *,
    state: str = STATE_PENDING,
    park: str | None = None,
    first_slot_id: int | None = None,
    created_at: int = 1,
) -> BlockRow:
    return BlockRow(
        block_id=block_id,
        created_at=created_at,
        budget_slot=3,
        block_size=3072,
        global_hash=b"\xaa" * 16,
        state=state,
        park=park,
        first_slot_id=first_slot_id,
    )


def test_insert_and_get_round_trip(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        store.insert(row(), role=Role.DATA, kind="note")
        found = store.get(b"\x01" * 16)
        assert found == row()


def test_get_of_an_unknown_id_is_none(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        assert store.get(b"\xff" * 16) is None


def test_identity_row_lands_in_the_right_split_table(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        store.insert(row(b"\x02" * 16), role=Role.INDEX, kind="title")
        kinds = store.connection.execute("SELECT block_id, kind FROM index_block").fetchall()
        assert [tuple(record) for record in kinds] == [(b"\x02" * 16, "title")]
        assert store.connection.execute("SELECT count(*) FROM data_block").fetchone()[0] == 0


def test_insert_is_one_transaction(tmp_path: Path) -> None:
    """写行与写身份是一个事务：主键撞车时身份分表不留半条（索引库 §009 异常 2）。"""
    with make_store(tmp_path) as store:
        store.insert(row(), role=Role.DATA, kind="note")
        with pytest.raises(sqlite3.IntegrityError):
            store.insert(row(b"\x01" * 16), role=Role.DATA, kind="note")
        assert store.connection.execute("SELECT count(*) FROM data_block").fetchone()[0] == 1


def test_address_columns_must_live_and_die_together(tmp_path: Path) -> None:
    """事实依据的两条 CHECK：`park` 与 `first_slot_id` 同生同灭。"""
    with make_store(tmp_path) as store, pytest.raises(sqlite3.IntegrityError):
        store.insert(row(park="0123456789abcdef"), role=Role.DATA, kind="")


def test_rows_are_ordered_by_creation_then_id(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        store.insert(row(b"\x02" * 16, created_at=5), role=Role.DATA, kind="")
        store.insert(row(b"\x01" * 16, created_at=5), role=Role.DATA, kind="")
        store.insert(row(b"\x03" * 16, created_at=1), role=Role.DATA, kind="")
        assert [item.block_id for item in store.rows()] == [
            b"\x03" * 16,
            b"\x01" * 16,
            b"\x02" * 16,
        ]


def test_live_slots_only_counts_submitted_blocks_with_an_address(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        park = "0123456789abcdef"
        store.insert(
            row(b"\x01" * 16, state=STATE_OK, park=park, first_slot_id=4), role=Role.DATA, kind=""
        )
        store.insert(
            row(b"\x02" * 16, state=STATE_OK, park=park, first_slot_id=0), role=Role.DATA, kind=""
        )
        store.insert(row(b"\x03" * 16, state=STATE_PENDING), role=Role.DATA, kind="")
        store.insert(
            row(b"\x04" * 16, state=STATE_ERROR, park=park, first_slot_id=9),
            role=Role.DATA,
            kind="",
        )
        assert store.live_slots(park) == [(0, 3), (4, 3)]
        assert store.live_slots("ffffffffffffffff") == []


def test_mark_ok_turns_a_pending_row_into_a_readable_one(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        store.insert(row(), role=Role.DATA, kind="")
        store.mark_ok(b"\x01" * 16)
        found = store.get(b"\x01" * 16)
        assert found is not None
        assert found.state == STATE_OK


def test_mark_ok_of_a_missing_row_is_not_found(tmp_path: Path) -> None:
    with make_store(tmp_path) as store, pytest.raises(NotFoundError, match="索引行不在了"):
        store.mark_ok(b"\xff" * 16)


def test_set_address_refluxes_both_columns(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        store.insert(row(), role=Role.DATA, kind="")
        store.set_address(b"\x01" * 16, park="0123456789abcdef", first_slot_id=7)
        found = store.get(b"\x01" * 16)
        assert found is not None
        assert found.park == "0123456789abcdef"
        assert found.first_slot_id == 7
        assert found.has_address


def test_set_address_of_a_missing_row_is_not_found(tmp_path: Path) -> None:
    with make_store(tmp_path) as store, pytest.raises(NotFoundError, match="索引行不在了"):
        store.set_address(b"\xff" * 16, park="0123456789abcdef", first_slot_id=0)


def test_delete_cascades_into_the_identity_table(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        store.insert(row(), role=Role.DATA, kind="note")
        assert store.delete(b"\x01" * 16) is True
        assert store.delete(b"\x01" * 16) is False
        assert store.connection.execute("SELECT count(*) FROM data_block").fetchone()[0] == 0


def test_foreign_keys_are_actually_on(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert store.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_path_property_points_at_the_file(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        assert store.path == tmp_path / "index.db"
        assert store.path.is_file()


def test_create_then_load_keeps_the_declared_fingerprint(tmp_path: Path) -> None:
    with make_store(tmp_path):
        pass
    with IndexStore.load(tmp_path / "index.db") as loaded:
        assert loaded.path.is_file()
    assert len(schema_gen.SCHEMA_FINGERPRINTS) >= 1

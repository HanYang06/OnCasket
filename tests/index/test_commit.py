# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""库侧提交动作：② 写 pending 行 / ⑥ 翻 ok / ⑦ 地址回流 / 删行（索引库 §009）。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from oncasket._index import commit
from oncasket._index.store import STATE_OK, STATE_PENDING, IndexStore, Role


if TYPE_CHECKING:
    from pathlib import Path


BLOCK_ID = b"\x11" * 16


def make_store(tmp_path: Path) -> IndexStore:
    return IndexStore.create(tmp_path / "index.db")


def test_write_pending_leaves_the_address_empty(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        created = commit.write_pending(
            store,
            block_id=BLOCK_ID,
            budget_slot=2,
            block_size=2048,
            global_hash=b"\xbb" * 16,
            kind="note",
            created_at=42,
        )
        assert created.state == STATE_PENDING
        assert created.park is None
        assert created.first_slot_id is None
        assert created.created_at == 42
        found = store.get(BLOCK_ID)
        assert found == created


def test_write_pending_stamps_the_time_when_not_given(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        before = commit.now_seconds()
        created = commit.write_pending(
            store,
            block_id=BLOCK_ID,
            budget_slot=1,
            block_size=1024,
            global_hash=b"\xcc" * 16,
            kind="",
        )
        assert before <= created.created_at <= commit.now_seconds()


def test_write_pending_can_open_an_index_block(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        commit.write_pending(
            store,
            block_id=BLOCK_ID,
            budget_slot=1,
            block_size=1024,
            global_hash=b"\xdd" * 16,
            kind="title",
            role=Role.INDEX,
        )
        kinds = store.connection.execute("SELECT kind FROM index_block").fetchall()
        assert [record["kind"] for record in kinds] == ["title"]


def test_mark_ok_then_reflux_address_completes_the_commit(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        commit.write_pending(
            store,
            block_id=BLOCK_ID,
            budget_slot=2,
            block_size=2048,
            global_hash=b"\xee" * 16,
            kind="",
        )
        commit.mark_ok(store, BLOCK_ID)
        commit.reflux_address(store, BLOCK_ID, park="0123456789abcdef", first_slot_id=3)
        found = store.get(BLOCK_ID)
        assert found is not None
        assert found.state == STATE_OK
        assert found.park == "0123456789abcdef"
        assert found.first_slot_id == 3


def test_drop_removes_the_row_once(tmp_path: Path) -> None:
    with make_store(tmp_path) as store:
        commit.write_pending(
            store,
            block_id=BLOCK_ID,
            budget_slot=1,
            block_size=1024,
            global_hash=b"\xff" * 16,
            kind="",
        )
        assert commit.drop(store, BLOCK_ID) is True
        assert commit.drop(store, BLOCK_ID) is False


def test_now_seconds_is_a_whole_utc_second() -> None:
    stamp = commit.now_seconds()
    assert isinstance(stamp, int)
    assert abs(stamp - int(time.time())) <= 5

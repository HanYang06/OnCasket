# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""改（035）：基准点 ＋ 新值——读回现役、应用新值、写前验一次（乐观并发）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from oncasket._errors import ConflictError, NotFoundError, OnCasketError
from oncasket._format.park import ParkFile
from oncasket._index.store import STATE_PENDING, BlockRow, IndexStore, Role
from oncasket._ops import read as read_module
from oncasket._ops import write as write_module
from oncasket._ops.session import HubSession


if TYPE_CHECKING:
    from pathlib import Path


def open_hub(tmp_path: Path) -> HubSession:
    return HubSession.open(tmp_path / "hub")


def test_update_replaces_the_named_attrs_and_keeps_the_rest(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(
            hub, attrs={"title": b"old", "keep": b"me"}, body=b"body"
        )
        write_module.update_block(hub, block_id, attrs={"title": b"new"})
        block = read_module.read_block(hub, block_id)
        assert block.attrs == {"title": b"new", "keep": b"me"}
        assert block.body == b"body"
        assert block.block_id == block_id


def test_update_can_replace_the_body_alone(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, attrs={"title": b"same"}, body=b"old body")
        write_module.update_block(hub, block_id, body=b"new body" * 40)
        block = read_module.read_block(hub, block_id)
        assert block.attrs == {"title": b"same"}
        assert block.body == b"new body" * 40


def test_update_moves_the_address_and_frees_the_old_segment(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"before")
        before = hub.store.get(block_id)
        assert before is not None
        assert before.park is not None
        assert before.first_slot_id == 0

        write_module.update_block(hub, block_id, body=b"after")
        after = hub.store.get(block_id)
        assert after is not None
        assert after.first_slot_id == before.budget_slot  # 新段接在水线后面
        assert after.global_hash != before.global_hash

        with ParkFile.load(hub.park_path(before.park)) as park:
            assert park.header.slot_used == after.budget_slot
            assert park.header.slot_empty == before.budget_slot


def test_update_is_a_compare_and_swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """基准点已是别人换过的：不静默覆盖，抛 `ConflictError`，并把刚占的新段放回去。"""
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"first")
        before = hub.store.get(block_id)
        assert before is not None
        assert before.park is not None

        def always_stale(*_args: object, **_kwargs: object) -> bool:
            return False

        monkeypatch.setattr(IndexStore, "replace_content", always_stale)
        with pytest.raises(ConflictError, match="已不是现役"):
            write_module.update_block(hub, block_id, body=b"second")

        with ParkFile.load(hub.park_path(before.park)) as park:
            assert park.header.slot_used == before.budget_slot
            assert park.header.slot_empty == before.budget_slot  # 新段放回去了（水线不缩）
        assert read_module.read_block(hub, block_id).body == b"first"


def test_update_of_an_unknown_id_is_not_found(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub, pytest.raises(NotFoundError, match="基准点找不到"):
        write_module.update_block(hub, b"\x42" * 16, body=b"nope")


def test_update_of_a_pending_block_is_reported(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = b"\x43" * 16
        hub.store.insert(
            BlockRow(
                block_id=block_id,
                created_at=1,
                budget_slot=1,
                block_size=8,
                global_hash=b"\x00" * 16,
                state=STATE_PENDING,
                park=None,
                first_slot_id=None,
            ),
            role=Role.DATA,
            kind="",
        )
        with pytest.raises(OnCasketError, match="pending"):
            write_module.update_block(hub, block_id, body=b"nope")


def test_update_keeps_the_slot_size_of_the_existing_park(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"small", slot_size=1024)
        before = hub.store.get(block_id)
        assert before is not None
        assert before.park is not None
        write_module.update_block(hub, block_id, body=b"again")
        after = hub.store.get(block_id)
        assert after is not None
        assert after.park == before.park
        with ParkFile.load(hub.park_path(before.park)) as park:
            assert park.header.slot_size == 1024

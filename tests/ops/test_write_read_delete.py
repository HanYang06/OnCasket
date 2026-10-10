# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""最小竖切：`Hub` 打开 → 写 → 读 → 删，一条路走通（路线 002/003/005/006/007/009/013/026/036）。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from oncasket._errors import CorruptError, LockTimeoutError, NotFoundError, OnCasketError
from oncasket._format import spec
from oncasket._format.park import ParkFile
from oncasket._hub import layout
from oncasket._index.store import STATE_ERROR, STATE_PENDING, BlockRow, Role
from oncasket._ops import delete as delete_module
from oncasket._ops import read as read_module
from oncasket._ops import write as write_module
from oncasket._ops.session import HubSession


if TYPE_CHECKING:
    from pathlib import Path


def open_hub(tmp_path: Path) -> HubSession:
    return HubSession.open(tmp_path / "hub")


def park_of(hub: HubSession, name: str) -> ParkFile:
    return ParkFile.load(hub.park_path(name))


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(
            hub, attrs={"title": b"hi", "owner": b"me"}, body=b"hello", kind="note"
        )
        assert isinstance(block_id, bytes)
        assert len(block_id) == 16

        block = read_module.read_block(hub, block_id)
        assert block.block_id == block_id
        assert block.attrs == {"title": b"hi", "owner": b"me"}
        assert block.body == b"hello"

        row = hub.store.get(block_id)
        assert row is not None
        assert row.state == "ok"
        assert row.has_address
        assert row.budget_slot == block.header_slot_num + block.data_slot_num


def test_write_is_indexed_with_identity_and_address(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"x", kind="note")
        row = hub.store.get(block_id)
        assert row is not None
        assert row.park is not None
        assert row.first_slot_id == 0
        assert hub.store.live_slots(row.park) == [(0, row.budget_slot)]
        identities = hub.store.connection.execute(
            "SELECT kind FROM data_block WHERE block_id = ?", (block_id,)
        ).fetchall()
        assert [record["kind"] for record in identities] == ["note"]


def test_index_block_role_lands_in_its_own_table(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"idx", kind="title", role=Role.INDEX)
        rows = hub.store.connection.execute(
            "SELECT block_id FROM index_block WHERE block_id = ?", (block_id,)
        ).fetchall()
        assert len(rows) == 1
        data_rows = hub.store.connection.execute(
            "SELECT block_id FROM data_block WHERE block_id = ?", (block_id,)
        ).fetchall()
        assert data_rows == []


def test_second_write_appends_in_the_same_park(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        first = write_module.write_block(hub, body=b"a" * 10)
        second = write_module.write_block(hub, body=b"b" * 10)
        first_row = hub.store.get(first)
        second_row = hub.store.get(second)
        assert first_row is not None
        assert second_row is not None
        assert first_row.park == second_row.park
        assert second_row.first_slot_id == first_row.budget_slot
        assert len(layout.find_parks(hub.path)) == 1


def test_delete_frees_the_segment_and_a_later_write_reuses_it(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        first = write_module.write_block(hub, body=b"a" * 10)
        second = write_module.write_block(hub, body=b"b" * 10)
        first_row = hub.store.get(first)
        second_row = hub.store.get(second)
        assert first_row is not None
        assert second_row is not None
        park_name = first_row.park
        assert park_name is not None

        delete_module.delete_block(hub, first)
        assert hub.store.get(first) is None
        with park_of(hub, park_name) as park:
            assert park.header.slot_used == second_row.budget_slot
            assert park.header.slot_empty == first_row.budget_slot

        third = write_module.write_block(hub, body=b"c" * 10)
        third_row = hub.store.get(third)
        assert third_row is not None
        assert third_row.first_slot_id == 0  # best_fit：贴合最紧，先回到最高那一段
        assert third_row.park == park_name


def test_read_after_delete_is_not_found(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"bye")
        delete_module.delete_block(hub, block_id)
        with pytest.raises(NotFoundError, match="基准点找不到"):
            read_module.read_block(hub, block_id)


def test_delete_is_idempotent_only_once(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"once")
        delete_module.delete_block(hub, block_id)
        with pytest.raises(NotFoundError, match="基准点找不到"):
            delete_module.delete_block(hub, block_id)


def test_delete_of_a_block_without_address_only_drops_the_row(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = b"\x07" * spec.BLOCK_ID_BYTES
        row = BlockRow(
            block_id=block_id,
            created_at=1,
            budget_slot=1,
            block_size=8,
            global_hash=b"\x00" * 16,
            state=STATE_PENDING,
            park=None,
            first_slot_id=None,
        )
        hub.store.insert(row, role=Role.DATA, kind="")
        delete_module.delete_block(hub, block_id)
        assert hub.store.get(block_id) is None


def test_read_of_a_pending_row_is_reported(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = b"\x08" * spec.BLOCK_ID_BYTES
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
            read_module.read_block(hub, block_id)


def test_read_of_an_error_row_is_corrupt(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = b"\x09" * spec.BLOCK_ID_BYTES
        hub.store.insert(
            BlockRow(
                block_id=block_id,
                created_at=1,
                budget_slot=1,
                block_size=8,
                global_hash=b"\x00" * 16,
                state=STATE_ERROR,
                park=None,
                first_slot_id=None,
            ),
            role=Role.DATA,
            kind="",
        )
        with pytest.raises(CorruptError, match="损坏点"):
            read_module.read_block(hub, block_id)


def test_an_empty_address_is_repaired_by_a_blind_scan(tmp_path: Path) -> None:
    """`state = ok` 而地址空**不是错误**：盲扫补地址，补到当场回流（索引库 §013）。"""
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"scan me")
        row = hub.store.get(block_id)
        assert row is not None
        with hub.store.connection:
            hub.store.connection.execute(
                "UPDATE block SET park = NULL, first_slot_id = NULL WHERE block_id = ?",
                (block_id,),
            )

        recovered = read_module.read_block(hub, block_id)
        assert recovered.body == b"scan me"
        after = hub.store.get(block_id)
        assert after is not None
        assert after.has_address


def test_a_block_missing_from_every_park_is_corrupt(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"ghost")
        row = hub.store.get(block_id)
        assert row is not None
        assert row.park is not None
        hub.park_path(row.park).unlink()
        with pytest.raises(CorruptError, match="载体不在"):
            read_module.read_block(hub, block_id)


def test_a_tampered_slot_is_corrupt(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"tamper")
        row = hub.store.get(block_id)
        assert row is not None
        assert row.park is not None
        assert row.first_slot_id is not None
        with park_of(hub, row.park) as park:
            raw = bytearray(park.read_slot(row.first_slot_id))
            raw[-1] ^= 0xFF
            park.write_slot(row.first_slot_id, bytes(raw))
        with pytest.raises(CorruptError, match="链首槽不认"):
            read_module.read_block(hub, block_id)


def test_a_cleared_chain_head_is_corrupt(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"cleared")
        row = hub.store.get(block_id)
        assert row is not None
        assert row.park is not None
        assert row.first_slot_id is not None
        with park_of(hub, row.park) as park:
            park.clear_state(row.first_slot_id)
        with pytest.raises(CorruptError, match="链首槽不认"):
            read_module.read_block(hub, block_id)


def test_a_missing_named_park_is_not_found(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub, pytest.raises(NotFoundError, match="点名的载体不在"):
        write_module.write_block(hub, body=b"nowhere", park="0" * 16)


def test_a_full_park_makes_the_next_write_open_a_second_one(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        # 造一个只放得下一个槽的载体：装不下任何 ≥ 2 槽的块
        unique = "tiny"
        path = layout.park_path(hub.path, unique)
        path.parent.mkdir(parents=True, exist_ok=True)
        ParkFile.create(path, slot_size=spec.SLOT_SIZE_DEFAULT, slot_num=1).close()

        block_id = write_module.write_block(hub, body=b"x" * 2000)
        row = hub.store.get(block_id)
        assert row is not None
        assert row.budget_slot >= 2
        assert len(layout.find_parks(hub.path)) == 2


def test_an_unindexed_physical_block_is_seen_by_the_blind_scan(tmp_path: Path) -> None:
    """库与载体对不上（行被抹掉、槽还在）时退回盲扫拿事实，**不覆盖**已占用的槽。"""
    with open_hub(tmp_path) as hub:
        first = write_module.write_block(hub, body=b"a" * 10)
        first_row = hub.store.get(first)
        assert first_row is not None
        with hub.store.connection:
            hub.store.connection.execute("DELETE FROM block WHERE block_id = ?", (first,))

        second = write_module.write_block(hub, body=b"b" * 10)
        second_row = hub.store.get(second)
        assert second_row is not None
        assert second_row.first_slot_id == first_row.budget_slot


def test_write_honours_the_configured_lock_timeout(tmp_path: Path) -> None:
    container = tmp_path / "hub"
    container.mkdir()
    (container.parent / "hub.conf.json").write_text(
        json.dumps({"lock_timeout": 0.05}), encoding="utf-8"
    )
    with open_hub(tmp_path) as hub, hub.write_lock(), pytest.raises(LockTimeoutError):
        write_module.write_block(hub, body=b"blocked")


def test_write_rejects_a_bad_block_id(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub, pytest.raises(ValueError, match="block_id 必须是"):
        write_module.write_block(hub, block_id=b"short")


def test_read_of_an_unknown_id_is_not_found(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub, pytest.raises(NotFoundError, match="基准点找不到"):
        read_module.read_block(hub, b"\xff" * spec.BLOCK_ID_BYTES)


def test_write_into_a_named_park(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        first = write_module.write_block(hub, body=b"a" * 10)
        row = hub.store.get(first)
        assert row is not None
        assert row.park is not None
        second = write_module.write_block(hub, body=b"b" * 10, park=row.park)
        second_row = hub.store.get(second)
        assert second_row is not None
        assert second_row.park == row.park


def test_a_park_with_another_slot_size_is_skipped(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        path = layout.park_path(hub.path, "small")
        path.parent.mkdir(parents=True, exist_ok=True)
        ParkFile.create(path, slot_size=1024, slot_num=8).close()

        block_id = write_module.write_block(hub, body=b"big slot")
        row = hub.store.get(block_id)
        assert row is not None
        assert row.park is not None
        with park_of(hub, row.park) as park:
            assert park.header.slot_size == spec.SLOT_SIZE_DEFAULT


def test_a_row_whose_global_hash_does_not_match_the_chain_is_corrupt(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"hash check")
        with hub.store.connection:
            hub.store.connection.execute(
                "UPDATE block SET global_hash = ? WHERE block_id = ?", (b"\x00" * 16, block_id)
            )
        with pytest.raises(CorruptError, match="全局哈希对不上"):
            read_module.read_block(hub, block_id)


def test_an_address_that_no_park_can_satisfy_is_corrupt(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"lost")
        row = hub.store.get(block_id)
        assert row is not None
        assert row.park is not None
        with hub.store.connection:
            hub.store.connection.execute(
                "UPDATE block SET park = NULL, first_slot_id = NULL WHERE block_id = ?", (block_id,)
            )
        hub.park_path(row.park).unlink()
        with pytest.raises(CorruptError, match="载体上找不到"):
            read_module.read_block(hub, block_id)


def test_a_truncated_park_cannot_be_read(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"x" * 2000)
        row = hub.store.get(block_id)
        assert row is not None
        assert row.park is not None
        path = hub.park_path(row.park)
        raw = path.read_bytes()
        path.write_bytes(raw[: 128 + 1024 * 2 + 4])
        with pytest.raises(CorruptError, match="载体读不满"):
            read_module.read_block(hub, block_id)


def test_the_blind_scan_walks_past_other_blocks_and_broken_parks(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        write_module.write_block(hub, body=b"a" * 10)
        target = write_module.write_block(hub, body=b"b" * 10)
        junk = layout.park_path(hub.path, "junk")
        junk.parent.mkdir(parents=True, exist_ok=True)
        junk.write_bytes(b"\x00" * 200)
        with hub.store.connection:
            hub.store.connection.execute(
                "UPDATE block SET park = NULL, first_slot_id = NULL WHERE block_id = ?", (target,)
            )
        assert read_module.read_block(hub, target).body == b"b" * 10


def test_delete_of_a_block_whose_park_is_gone_drops_the_row(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"orphan")
        row = hub.store.get(block_id)
        assert row is not None
        assert row.park is not None
        hub.park_path(row.park).unlink()
        delete_module.delete_block(hub, block_id)
        assert hub.store.get(block_id) is None


def test_delete_of_a_block_whose_head_is_already_cleared_drops_the_row(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"already")
        row = hub.store.get(block_id)
        assert row is not None
        assert row.park is not None
        assert row.first_slot_id is not None
        with park_of(hub, row.park) as park:
            park.clear_state(row.first_slot_id)
        delete_module.delete_block(hub, block_id)
        assert hub.store.get(block_id) is None

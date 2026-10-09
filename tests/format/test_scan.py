# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""盲扫：认块、跳过空槽、清孤儿，以及水线以外看得见什么。"""

from __future__ import annotations

import pytest

from oncasket._format import block, park, scan, slot, spec


BLOCK_ID = bytes(range(16))
SLOT = 592


def make_park(tmp_path, *, slot_live: int, slot_num: int = 16) -> park.ParkFile:
    """建一个水线已推好的 park。

    Args:
        tmp_path: 临时目录。
        slot_live: 水线。
        slot_num: 预算槽数。

    Returns:
        打开的句柄（调用方负责关）。
    """
    handle = park.ParkFile.create(tmp_path / "a.oncat", slot_size=SLOT, slot_num=slot_num)
    handle.grow_to(slot_live)
    return handle


def put_block(
    handle: park.ParkFile,
    at: int,
    *,
    attrs: dict[str, bytes] | None = None,
    body: bytes = b"",
) -> int:
    """在 `at` 处写一条真链，返回它占几个槽。

    Args:
        handle: park 句柄。
        at: 链首槽 id。
        attrs: 属性。
        body: 块体。

    Returns:
        链长（槽数）。
    """
    plan = block.plan_block(block_id=BLOCK_ID, attrs=attrs, body=body, slot_size=SLOT)
    for offset, raw in enumerate(block.assemble_block(plan, first_slot_id=at)):
        handle.write_slot(at + offset, raw)
    return plan.slot_num


def test_an_empty_park_has_nothing(tmp_path) -> None:
    with make_park(tmp_path, slot_live=0) as handle:
        result = scan.scan_park(handle)
    assert (result.blocks, result.orphans) == ((), ())
    assert (result.slot_used, result.scanned, result.cleared) == (0, 0, False)


def test_finds_a_chain(tmp_path) -> None:
    with make_park(tmp_path, slot_live=6) as handle:
        span = put_block(handle, 0, attrs={"title": b"hi"}, body=b"x" * 100)
        result = scan.scan_park(handle, horizon=span)
    assert result.blocks == (scan.FoundBlock(first_slot_id=0, slot_num=span),)
    assert (result.slot_used, result.orphans) == (span, ())


def test_skips_empty_slots_and_finds_the_block_behind_them(tmp_path) -> None:
    with make_park(tmp_path, slot_live=8) as handle:
        span = put_block(handle, 3)
        result = scan.scan_park(handle)
    assert result.blocks == (scan.FoundBlock(first_slot_id=3, slot_num=span),)
    assert result.orphans == ()


def test_clears_a_lone_data_slot(tmp_path) -> None:
    with make_park(tmp_path, slot_live=3) as handle:
        handle.write_slot(1, slot.encode_data(body=b"orphan", end=True, slot_size=SLOT))
        result = scan.scan_park(handle)
        assert (result.orphans, result.cleared) == ((1,), True)
        assert slot.read_state(handle.read_slot(1)) is slot.SlotState.EMPTY


def test_clears_a_head_whose_check_fails(tmp_path) -> None:
    raw = bytearray(
        slot.encode_header_start(
            header_slot_num=1,
            header_slot_end=0,
            data_slot_num=0,
            data_slot_end=0,
            block_body_size=0,
            block_id=BLOCK_ID,
            slot_size=SLOT,
        )
    )
    raw[-1] ^= 0x01
    with make_park(tmp_path, slot_live=1) as handle:
        handle.write_slot(0, bytes(raw))
        result = scan.scan_park(handle)
        assert (result.blocks, result.orphans) == ((), (0,))
        assert slot.read_state(handle.read_slot(0)) is slot.SlotState.EMPTY


def test_clears_an_unknown_magic(tmp_path) -> None:
    raw = bytearray(spec.bits_to_bytes(SLOT))
    spec.write_uint32(raw, spec.SLOT_STATE, 0x1234_5678)
    with make_park(tmp_path, slot_live=1) as handle:
        handle.write_slot(0, bytes(raw))
        assert scan.scan_park(handle).orphans == (0,)


def test_clear_false_only_reports(tmp_path) -> None:
    orphan = slot.encode_data(body=b"orphan", end=True, slot_size=SLOT)
    with make_park(tmp_path, slot_live=1) as handle:
        handle.write_slot(0, orphan)
        result = scan.scan_park(handle, clear=False)
        assert (result.orphans, result.cleared) == ((0,), False)
        assert handle.read_slot(0) == orphan


def test_horizon_can_stop_early(tmp_path) -> None:
    """水线以外不看：修复可以自己决定扫到哪儿。"""
    with make_park(tmp_path, slot_live=8) as handle:
        put_block(handle, 4)
        assert scan.scan_park(handle, horizon=4).blocks == ()
        assert len(scan.scan_park(handle, horizon=8).blocks) == 1


def test_a_chain_reaching_past_the_horizon_is_still_reported(tmp_path) -> None:
    """链自报的槽数越过水线时照报——「水线不对」正是要修的东西，别在这儿替它下结论。"""
    with make_park(tmp_path, slot_live=8) as handle:
        span = put_block(handle, 5, body=b"x" * 100)  # 1 个链首槽 ＋ 2 个 data 槽
        result = scan.scan_park(handle, horizon=6)
    assert span == 3
    assert result.blocks == (scan.FoundBlock(first_slot_id=5, slot_num=3),)
    assert 5 + span > result.scanned  # 链尾落在水线以外


def test_a_zero_span_head_is_an_orphan(tmp_path) -> None:
    raw = slot.encode_header_start(
        header_slot_num=0,
        header_slot_end=0,
        data_slot_num=0,
        data_slot_end=0,
        block_body_size=0,
        block_id=BLOCK_ID,
        slot_size=SLOT,
    )
    with make_park(tmp_path, slot_live=1) as handle:
        handle.write_slot(0, raw)
        assert scan.scan_park(handle).orphans == (0,)


def test_a_head_with_a_broken_count_is_an_orphan(tmp_path) -> None:
    """`check` 自洽但计数离谱（有人改过又重盖）：认不出来，按孤儿处理。"""
    raw = bytearray(
        slot.encode_header_start(
            header_slot_num=1,
            header_slot_end=0,
            data_slot_num=0,
            data_slot_end=0,
            block_body_size=0,
            block_id=BLOCK_ID,
            slot_size=SLOT,
        )
    )
    spec.write_int32(raw, spec.HEADER_START_ATTR_NUM, 1 << 20)
    slot.seal(raw)
    with make_park(tmp_path, slot_live=1) as handle:
        handle.write_slot(0, bytes(raw))
        assert scan.scan_park(handle).orphans == (0,)


def test_a_file_short_of_the_watermark_reaches_the_caller(tmp_path) -> None:
    """文件缺了一截不是「扫不了」，是缺数据——原样抛给策略库。"""
    with make_park(tmp_path, slot_live=4) as handle:
        handle.close()
    blob = (tmp_path / "a.oncat").read_bytes()
    (tmp_path / "a.oncat").write_bytes(blob[: park.HEADER_BYTES])
    short = tmp_path / "a.oncat"
    with park.ParkFile.load(short) as handle, pytest.raises(ValueError, match="读不满"):
        scan.scan_park(handle)

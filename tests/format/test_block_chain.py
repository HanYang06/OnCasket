# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""块链装配与解析：计数、五个状态的链、地址自洽，以及各类损坏。"""

from __future__ import annotations

import pytest

from oncasket._format import block, slot, spec


BLOCK_ID = bytes(range(16))
#: 小槽：592 位 = 74 B。链首段 14 B、溢出段 34 B、data 槽体 54 B
SLOT = 592
#: data 槽体的字节容量
ROOM = spec.data_body_capacity(SLOT) // spec.BITS_PER_BYTE


def plan(**kwargs: object) -> block.BlockPlan:
    """按小槽造一份计划，`block_id` 缺省用固定的那个。

    Args:
        **kwargs: 传给 `plan_block` 的字段。

    Returns:
        块计划。
    """
    fields: dict[str, object] = {"block_id": BLOCK_ID, "slot_size": SLOT}
    fields.update(kwargs)
    return block.plan_block(**fields)  # type: ignore[arg-type]


def test_plan_of_a_minimal_block() -> None:
    one = plan()
    assert one.segments == ((),)
    assert (one.header_slot_num, one.data_slot_num, one.slot_num) == (1, 0, 1)
    assert one.block_body_size == 0
    assert (one.block_size, one.slot_size) == (74, SLOT)


def test_plan_counts_attr_segments_and_body_chunks() -> None:
    attrs = dict.fromkeys("abcd", b"")  # 每条 9 B：链首段 1 条，溢出段 3 条
    big = plan(attrs=attrs, body=b"x" * 150)
    assert [len(segment) for segment in big.segments] == [1, 3]
    assert (big.header_slot_num, big.data_slot_num, big.slot_num) == (2, 3, 5)
    assert big.block_size == 5 * 74
    assert big.block_body_size == 150 * spec.BITS_PER_BYTE


def test_plan_rejects_a_bad_block_id() -> None:
    with pytest.raises(ValueError, match="block_id"):
        block.plan_block(block_id=b"short", slot_size=SLOT)


def test_assemble_then_parse_round_trip() -> None:
    attrs = {"title": b"hi", "kind": b"note"}
    body = b"x" * 100
    original = plan(attrs=attrs, body=body)
    slots = block.assemble_block(original, first_slot_id=7)
    assert len(slots) == original.slot_num == 4

    back = block.parse_block(slots, slot_size=SLOT, first_slot_id=7)
    assert back.block_id == BLOCK_ID
    assert back.attrs == attrs
    assert back.body == body
    assert (back.header_slot_num, back.data_slot_num) == (2, 2)


def test_chain_carries_the_five_states_in_order() -> None:
    slots = block.assemble_block(
        plan(attrs={"a": b"", "b": b"", "c": b"", "d": b""}, body=b"y" * 100), first_slot_id=0
    )
    assert [slot.read_state(raw).name for raw in slots] == [
        "HEADER_START",
        "HEADER_MID",
        "DATA_MID",
        "DATA_END",
    ]
    assert all(slot.verify(raw) for raw in slots)


def test_a_minimal_block_is_one_slot() -> None:
    slots = block.assemble_block(plan(), first_slot_id=3)
    assert len(slots) == 1
    back = block.parse_block(slots, slot_size=SLOT, first_slot_id=3)
    assert (back.attrs, back.body) == ({}, b"")
    assert (back.header_slot_num, back.data_slot_num) == (1, 0)


def test_ends_are_absolute_slot_ids() -> None:
    first = 42
    original = plan(attrs={"a": b"", "b": b"", "c": b"", "d": b""}, body=b"z" * 60)
    head = slot.decode_header_start(
        block.assemble_block(original, first_slot_id=first)[0],
        slot_size=SLOT,
    )
    assert head.header_slot_end == first + original.header_slot_num - 1
    assert head.data_slot_end == head.header_slot_end + original.data_slot_num


def test_body_is_trimmed_by_block_body_size() -> None:
    body = b"q" * 100
    slots = block.assemble_block(plan(body=body), first_slot_id=0)
    raw = slot.decode_header_start(slots[0], slot_size=SLOT)
    assert raw.block_body_size == 100 * spec.BITS_PER_BYTE
    assert len(slots) == 3  # 54 + 46
    assert block.parse_block(slots, slot_size=SLOT).body == body


def test_parse_rejects_a_corrupt_slot() -> None:
    slots = [bytearray(raw) for raw in block.assemble_block(plan(body=b"x" * 100), first_slot_id=0)]
    slots[-1][-1] ^= 0x01
    with pytest.raises(ValueError, match="check 对不上"):
        block.parse_block([bytes(raw) for raw in slots], slot_size=SLOT)


def test_parse_rejects_an_empty_chain() -> None:
    with pytest.raises(ValueError, match="至少要有一个头槽"):
        block.parse_block([], slot_size=SLOT)


def test_parse_rejects_a_short_chain() -> None:
    slots = block.assemble_block(plan(body=b"x" * 100), first_slot_id=0)
    with pytest.raises(ValueError, match="链长对不上"):
        block.parse_block(slots[:-1], slot_size=SLOT)


def test_parse_rejects_zero_header_slots() -> None:
    """`header_slot_num = 0` 的链不存在——链首槽自己就算一个。"""
    raw = slot.encode_header_start(
        header_slot_num=0,
        header_slot_end=0,
        data_slot_num=0,
        data_slot_end=0,
        block_body_size=0,
        block_id=BLOCK_ID,
        slot_size=SLOT,
    )
    with pytest.raises(ValueError, match="header_slot_num 至少是 1"):
        block.parse_block([raw], slot_size=SLOT)


def test_parse_rejects_a_foreign_block_id() -> None:
    slots = [
        bytearray(raw)
        for raw in block.assemble_block(
            plan(attrs={"a": b"", "b": b"", "c": b"", "d": b""}), first_slot_id=0
        )
    ]
    at = spec.byte_offset(spec.HEADER_MID_ATTR_BITS)
    slots[1][at : at + spec.BLOCK_ID_BYTES] = bytes(reversed(BLOCK_ID))
    slot.seal(slots[1])
    with pytest.raises(ValueError, match="block_id 与链首不一致"):
        block.parse_block([bytes(raw) for raw in slots], slot_size=SLOT)


def test_parse_rejects_duplicate_keys_across_segments() -> None:
    """同一条链的两段里各有一条同名属性——跨段重名也是损坏。"""
    one = block.encode_attr_entry("a", b"")
    head = slot.encode_header_start(
        header_slot_num=2,
        header_slot_end=1,
        data_slot_num=0,
        data_slot_end=1,
        block_body_size=0,
        block_id=BLOCK_ID,
        self_attr=[one],
        slot_size=SLOT,
    )
    mid = slot.encode_header_mid(block_id=BLOCK_ID, self_attr=[one], slot_size=SLOT)
    with pytest.raises(ValueError, match="属性重名"):
        block.parse_block([head, mid], slot_size=SLOT)


def test_parse_rejects_a_broken_data_slot_end() -> None:
    head = slot.encode_header_start(
        header_slot_num=1,
        header_slot_end=0,
        data_slot_num=1,
        data_slot_end=99,
        block_body_size=0,
        block_id=BLOCK_ID,
        slot_size=SLOT,
    )
    with pytest.raises(ValueError, match="data_slot_end"):
        block.parse_block(
            [head, slot.encode_data(body=b"", end=True, slot_size=SLOT)], slot_size=SLOT
        )


def test_parse_rejects_a_mismatched_first_slot_id() -> None:
    slots = block.assemble_block(plan(), first_slot_id=7)
    with pytest.raises(ValueError, match="与链首槽 id"):
        block.parse_block(slots, slot_size=SLOT, first_slot_id=9)


def test_parse_rejects_a_missing_data_end() -> None:
    head = slot.encode_header_start(
        header_slot_num=1,
        header_slot_end=0,
        data_slot_num=2,
        data_slot_end=2,
        block_body_size=0,
        block_id=BLOCK_ID,
        slot_size=SLOT,
    )
    slots = [
        head,
        slot.encode_data(body=b"", end=True, slot_size=SLOT),
        slot.encode_data(body=b"", end=False, slot_size=SLOT),
    ]
    with pytest.raises(ValueError, match="提前标了 data_end"):
        block.parse_block(slots, slot_size=SLOT)


def test_parse_rejects_a_chain_whose_last_data_slot_is_open() -> None:
    head = slot.encode_header_start(
        header_slot_num=1,
        header_slot_end=0,
        data_slot_num=1,
        data_slot_end=1,
        block_body_size=0,
        block_id=BLOCK_ID,
        slot_size=SLOT,
    )
    with pytest.raises(ValueError, match="没标 data_end"):
        block.parse_block(
            [head, slot.encode_data(body=b"", end=False, slot_size=SLOT)], slot_size=SLOT
        )


def test_parse_rejects_a_body_bigger_than_the_chain() -> None:
    head = slot.encode_header_start(
        header_slot_num=1,
        header_slot_end=0,
        data_slot_num=1,
        data_slot_end=1,
        block_body_size=ROOM * spec.BITS_PER_BYTE + 8,
        block_id=BLOCK_ID,
        slot_size=SLOT,
    )
    with pytest.raises(ValueError, match="链上的槽只有"):
        block.parse_block(
            [head, slot.encode_data(body=b"", end=True, slot_size=SLOT)], slot_size=SLOT
        )

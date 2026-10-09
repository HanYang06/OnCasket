# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""块级属性字典：条目编解码、按键升序、逐段切分（含与槽编解码的端到端）。"""

from __future__ import annotations

import pytest

from oncasket._format import block, slot, spec


BLOCK_ID = bytes(range(16))

#: 小槽：592 位 = 74 B。链首段 14 B（592 − 480），此后每段 34 B（592 − 320）
SMALL = 592


def entry(name: bytes, value: bytes) -> bytes:
    """直接把字节拼成条目，用来造坏数据。

    Args:
        name: 名字字节。
        value: 值字节。

    Returns:
        条目字节。
    """
    return (
        len(name).to_bytes(spec.ATTR_NAME_LEN_BYTES, "little")
        + name
        + len(value).to_bytes(spec.ATTR_VALUE_LEN_BYTES, "little")
        + value
    )


def test_entry_layout_golden() -> None:
    """一条最小条目的字节：名 1 B、值 0 B。"""
    one = block.encode_attr_entry("a", b"")
    assert one == b"\x01\x00\x00\x00a\x00\x00\x00\x00"
    assert len(one) == spec.ATTR_ENTRY_OVERHEAD + 1


def test_empty_name_rejected() -> None:
    with pytest.raises(ValueError, match="属性名不能为空"):
        block.encode_attr_entry("", b"x")


def test_binary_value_round_trips() -> None:
    value = bytes(range(256))
    attrs = block.decode_attrs(block.encode_attr_entry("blob", value), 1)
    assert attrs == {"blob": value}


def test_names_sort_by_utf8_bytes() -> None:
    """按名的 utf-8 字节序，不是按长度、也不是按调用方给的顺序。"""
    attrs = {"é": b"1", "z": b"2", "a": b"3"}
    blob = b"".join(block.encode_attrs(attrs))
    assert list(block.decode_attrs(blob, 3)) == ["a", "z", "é"]


def test_same_attrs_give_the_same_bytes() -> None:
    """同一组属性 ⇒ 同一串字节，与字典是怎么构造出来的无关。"""
    one = {"title": b"hi", "kind": b"note"}
    other = {"kind": b"note", "title": b"hi"}
    assert b"".join(block.encode_attrs(one)) == b"".join(block.encode_attrs(other))


def test_zero_entries_is_empty() -> None:
    assert block.decode_attrs(bytes(14), 0) == {}


def test_truncated_segment_rejected() -> None:
    with pytest.raises(ValueError, match="中途结束"):
        block.decode_attrs(b"\x01\x00\x00\x00a", 1)


def test_name_overrun_rejected() -> None:
    name_len = (99).to_bytes(spec.ATTR_NAME_LEN_BYTES, "little")
    with pytest.raises(ValueError, match="属性名越过"):
        block.decode_attrs(name_len + b"abcdef", 1)  # 名长报 99，实际只有 6 B


def test_value_overrun_rejected() -> None:
    overrun = entry(b"a", b"")[:5] + (99).to_bytes(spec.ATTR_VALUE_LEN_BYTES, "little") + b"xx"
    with pytest.raises(ValueError, match="属性值越过"):
        block.decode_attrs(overrun, 1)


def test_non_utf8_name_rejected() -> None:
    with pytest.raises(ValueError, match="不是 utf-8"):
        block.decode_attrs(entry(b"\xff\xfe", b""), 1)


def test_duplicate_keys_rejected() -> None:
    """字典的键必须唯一：盘上出现两条同名，就等于要么谁也说不清哪条算数。"""
    one = block.encode_attr_entry("a", b"1")
    with pytest.raises(ValueError, match="属性重名"):
        block.decode_attrs(one + one, 2)


def test_plan_of_nothing_is_one_empty_segment() -> None:
    assert block.plan_attr_segments([], slot_size=SMALL) == [[]]


def test_plan_fits_in_the_chain_head() -> None:
    one = block.encode_attr_entry("a", b"")
    assert block.plan_attr_segments([one], slot_size=SMALL) == [[one]]


def test_plan_overflows_into_extra_head_slots() -> None:
    items = [block.encode_attr_entry(name, b"") for name in "abcde"]
    segments = block.plan_attr_segments(items, slot_size=SMALL)
    assert [len(segment) for segment in segments] == [1, 3, 1]
    assert [item for segment in segments for item in segment] == items


def test_plan_skips_the_head_when_one_entry_is_too_wide() -> None:
    """一条塞不进链首段就整条挪走：第 0 段空着，链首槽照样在。"""
    wide = block.encode_attr_entry("a", b"x" * 6)  # 8 + 1 + 6 = 15 B > 14 B
    assert block.plan_attr_segments([wide], slot_size=SMALL) == [[], [wide]]


def test_plan_rejects_an_entry_over_the_mid_limit() -> None:
    huge = block.encode_attr_entry("a", b"x" * 27)  # 36 B > 34 B
    with pytest.raises(ValueError, match="单条属性"):
        block.plan_attr_segments([huge], slot_size=SMALL)


def test_end_to_end_with_slot_codec() -> None:
    """属性字典 → 条目 → 分段 → 头槽字节 → 解回来，还是那个字典。"""
    attrs = {"a": b"1", "b": b"2", "c": b"3", "d": b"4"}
    segments = block.plan_attr_segments(block.encode_attrs(attrs), slot_size=SMALL)
    assert [len(segment) for segment in segments] == [1, 3]

    head = slot.encode_header_start(
        header_slot_num=len(segments),
        header_slot_end=len(segments) - 1,
        data_slot_num=0,
        data_slot_end=0,
        block_body_size=0,
        block_id=BLOCK_ID,
        self_attr=segments[0],
        slot_size=SMALL,
    )
    decoded_head = slot.decode_header_start(head, slot_size=SMALL)
    assert decoded_head.block_id == BLOCK_ID
    recovered = block.decode_attrs(decoded_head.self_attr, decoded_head.self_attr_num)

    for segment in segments[1:]:
        mid = slot.encode_header_mid(block_id=BLOCK_ID, self_attr=segment, slot_size=SMALL)
        decoded_mid = slot.decode_header_mid(mid, slot_size=SMALL)
        assert decoded_mid.block_id == BLOCK_ID
        recovered |= block.decode_attrs(decoded_mid.self_attr, decoded_mid.self_attr_num)

    assert recovered == attrs

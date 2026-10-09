# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""`spec` 的换算与读写原语：单位、切片、端序、边界。"""

from __future__ import annotations

import pytest

from oncasket._format import spec


def test_bits_to_bytes_rounds_up() -> None:
    assert spec.bits_to_bytes(0) == 0
    assert spec.bits_to_bytes(7) == 1
    assert spec.bits_to_bytes(8) == 1
    assert spec.bits_to_bytes(9) == 2
    assert spec.bits_to_bytes(spec.SLOT_SIZE_DEFAULT) == 1024


def test_byte_offset() -> None:
    assert spec.byte_offset(352) == 44
    with pytest.raises(ValueError, match="不是整字节"):
        spec.byte_offset(7)


def test_field_slice() -> None:
    assert spec.field_slice(spec.SLOT_WRITE_CHECK) == slice(4, 20)
    assert spec.field_slice(spec.PACK_SLOT_SIZE) == slice(32, 36)


def test_uint32_round_trip() -> None:
    data = bytearray(4)
    for value in (0, 1, spec.INT32_MAX, spec.UINT32_MAX):
        spec.write_uint32(data, (0, 32), value)
        assert spec.read_uint32(data, (0, 32)) == value


def test_uint32_range() -> None:
    data = bytearray(4)
    for value in (-1, spec.UINT32_MAX + 1):
        with pytest.raises(ValueError, match="32 位无符号"):
            spec.write_uint32(data, (0, 32), value)


def test_int32_range() -> None:
    data = bytearray(4)
    for value in (-1, spec.INT32_MAX + 1):
        with pytest.raises(ValueError, match="int32 非负"):
            spec.write_int32(data, (0, 32), value)


def test_field_offsets_are_byte_aligned() -> None:
    """所有区间端点都整字节——`field_slice` 的硬前提。"""
    bounds = (
        spec.PACK_VERSION,
        spec.PACK_SLOT_SIZE,
        spec.PACK_SLOT_NUM,
        spec.PACK_SLOT_LIVE,
        spec.PACK_SLOT_USED,
        spec.PACK_SLOT_DEAD,
        spec.PACK_SLOT_EMPTY,
        spec.PACK_RESERVED,
        spec.SLOT_STATE,
        spec.SLOT_WRITE_CHECK,
        spec.HEADER_START_SLOT_NUM,
        spec.HEADER_START_SLOT_END,
        spec.HEADER_START_DATA_SLOT_NUM,
        spec.HEADER_START_DATA_SLOT_END,
        spec.HEADER_START_BODY_SIZE,
        spec.HEADER_START_ATTR_NUM,
        spec.HEADER_MID_ATTR_NUM,
        spec.BLOCK_ID,
    )
    for start, end in bounds:
        assert start % spec.BITS_PER_BYTE == 0, (start, end)
        assert end % spec.BITS_PER_BYTE == 0, (start, end)


def test_capacities() -> None:
    """三种形态的容量都用缺省槽长核对一遍。"""
    slot_size = spec.SLOT_SIZE_DEFAULT
    assert spec.header_start_attr_capacity(slot_size) == slot_size - 480
    assert spec.header_mid_attr_capacity(slot_size) == slot_size - 320
    assert spec.data_body_capacity(slot_size) == slot_size - 160


def test_slot_size_bounds() -> None:
    spec.check_slot_size(spec.SLOT_SIZE_MIN)
    spec.check_slot_size(spec.SLOT_SIZE_DEFAULT)
    with pytest.raises(ValueError, match="下界"):
        spec.check_slot_size(spec.SLOT_SIZE_MIN - 8)
    with pytest.raises(ValueError, match="整字节"):
        spec.check_slot_size(spec.SLOT_SIZE_MIN + 1)


def test_state_magics_are_pairwise_far_apart() -> None:
    """事实依据要求五个魔数两两汉明距离 ≥ 14 位——别把它们改成相邻值。"""
    magics = (
        spec.STATE_HEADER_START,
        spec.STATE_HEADER_MID,
        spec.STATE_DATA_MID,
        spec.STATE_DATA_END,
        spec.STATE_EMPTY,
    )
    assert len(set(magics)) == len(magics)
    for i, left in enumerate(magics):
        for right in magics[i + 1 :]:
            assert (left ^ right).bit_count() >= 14, (hex(left), hex(right))

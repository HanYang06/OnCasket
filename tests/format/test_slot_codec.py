# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""槽编解码：三种形态的往返、槽内 `check` 与边界。

自述区是一条**条目列表**：槽这一层只把条目当字节搬运、只数**条数**，不解释条目内容
（条目框架归 `block`）。
"""

from __future__ import annotations

import pytest
import xxhash

from oncasket._format import slot, spec


BLOCK_ID = bytes(range(16))

#: 小槽：592 位 = 74 B。链首属性容量 592 − 480 = 112 位 = 14 B，
#: 正好装得下一条最小的条目（8 B 框架 + 1 B 名）；data 槽体 54 B。
SMALL = 592


def entry(name: bytes, value: bytes) -> bytes:
    """按事实依据的框架编一条条目：`<名长:u32><名><值长:u32><值>`。

    Args:
        name: 属性名（utf-8 字节）。
        value: 属性值。

    Returns:
        条目字节。
    """
    return len(name).to_bytes(4, "little") + name + len(value).to_bytes(4, "little") + value


def test_hash_is_xxh3_128() -> None:
    """空串的 XXH3-128 是公开向量——先钉住算法，别混进 XXH64。"""
    assert xxhash.xxh3_128(b"").hexdigest() == "99aa06d3014798d86001c324468d497f"


def test_golden_data_slot() -> None:
    """黄金向量：512 位、空槽体、非链尾。

    它一次钉死三件事：覆盖范围（跳过自己那 128 位）、哈希算法、字段字节序。
    """
    raw = slot.encode_data(body=b"", end=False, slot_size=512)
    assert raw[:4].hex() == "cc659958"  # data_mid 魔数，小端
    assert raw[4:20].hex() == "9307d2f1793734aed99480e614097266"
    assert raw[20:] == bytes(44)
    assert slot.verify(raw)


def test_golden_chain_head() -> None:
    """黄金向量：592 位链首头槽，一条 `a=` 条目。"""
    one = entry(b"a", b"")
    raw = slot.encode_header_start(
        header_slot_num=1,
        header_slot_end=0,
        data_slot_num=0,
        data_slot_end=0,
        block_body_size=0,
        block_id=BLOCK_ID,
        self_attr=[one],
        slot_size=SMALL,
    )
    assert raw[:4].hex() == "b179379e"  # header_start 魔数，小端
    assert raw[4:20].hex() == "7ccdea7cc3adca54e54df6e6781c3d3d"
    assert raw[20:44].hex() == "01000000" + "00000000" * 4 + "01000000"
    assert raw[44:60] == BLOCK_ID
    assert raw[60:69] == one
    assert raw[69:] == bytes(5)


def test_chain_head_round_trip() -> None:
    entries = [entry(b"title", b"hi"), entry(b"kind", b"note")]
    block_id = bytes(reversed(range(16)))
    raw = slot.encode_header_start(
        header_slot_num=2,
        header_slot_end=4,
        data_slot_num=3,
        data_slot_end=7,
        block_body_size=12345,
        block_id=block_id,
        self_attr=entries,
    )
    assert len(raw) == spec.bits_to_bytes(spec.SLOT_SIZE_DEFAULT)
    assert slot.read_state(raw) is slot.SlotState.HEADER_START
    assert slot.verify(raw)
    head = slot.decode_header_start(raw)
    assert head.header_slot_num == 2
    assert head.header_slot_end == 4
    assert head.data_slot_num == 3
    assert head.data_slot_end == 7
    assert head.block_body_size == 12345
    assert head.block_id == block_id
    assert head.self_attr_num == 2
    assert head.self_attr[: len(b"".join(entries))] == b"".join(entries)


def test_chain_head_byte_layout() -> None:
    """按事实依据的偏移逐字段核对；条数只数**条**，不记位长。"""
    one = entry(b"a", b"")
    raw = slot.encode_header_start(
        header_slot_num=1,
        header_slot_end=0,
        data_slot_num=0,
        data_slot_end=0,
        block_body_size=0,
        block_id=BLOCK_ID,
        self_attr=[one],
        slot_size=SMALL,
    )
    assert len(raw) == 74
    assert raw[0:4] == spec.STATE_HEADER_START.to_bytes(4, "little")
    assert raw[4:20] != bytes(16)  # check 已盖，不是留给零
    assert raw[20:24] == (1).to_bytes(4, "little")
    assert raw[24:28] == (0).to_bytes(4, "little")
    assert raw[28:32] == (0).to_bytes(4, "little")
    assert raw[32:36] == (0).to_bytes(4, "little")
    assert raw[36:40] == (0).to_bytes(4, "little")
    assert raw[40:44] == (1).to_bytes(4, "little")  # block_self_attr_num = 1 条
    assert raw[44:60] == BLOCK_ID
    assert raw[60:69] == one
    assert raw[69:] == bytes(5)  # 尾巴填充


def test_chain_head_attr_capacity_boundary() -> None:
    room = spec.header_start_attr_capacity(SMALL) // spec.BITS_PER_BYTE
    assert room == 14
    assert slot.verify(
        slot.encode_header_start(
            header_slot_num=1,
            header_slot_end=0,
            data_slot_num=0,
            data_slot_end=0,
            block_body_size=0,
            block_id=BLOCK_ID,
            self_attr=[b"x" * room],
            slot_size=SMALL,
        )
    )
    with pytest.raises(ValueError, match="本段条目需要"):
        slot.encode_header_start(
            header_slot_num=1,
            header_slot_end=0,
            data_slot_num=0,
            data_slot_end=0,
            block_body_size=0,
            block_id=BLOCK_ID,
            self_attr=[b"x" * (room + 1)],
            slot_size=SMALL,
        )


def test_overflow_round_trip() -> None:
    entries = [entry(b"a", b"1"), entry(b"b", b"2"), entry(b"c", b"3")]
    raw = slot.encode_header_mid(block_id=BLOCK_ID, self_attr=entries)
    assert slot.read_state(raw) is slot.SlotState.HEADER_MID
    assert slot.verify(raw)
    mid = slot.decode_header_mid(raw)
    assert mid.block_id == BLOCK_ID
    assert mid.self_attr_num == 3
    assert mid.self_attr[: len(b"".join(entries))] == b"".join(entries)


def test_decode_returns_the_whole_segment() -> None:
    """解码给的是整段（含尾部填充）：读到哪儿由条数说了算，与 data 槽同一个口径。"""
    one = entry(b"a", b"")
    mid = slot.decode_header_mid(
        slot.encode_header_mid(block_id=BLOCK_ID, self_attr=[one], slot_size=SMALL),
        slot_size=SMALL,
    )
    assert mid.self_attr_num == 1
    assert len(mid.self_attr) == spec.header_mid_attr_capacity(SMALL) // spec.BITS_PER_BYTE
    assert mid.self_attr[len(one) :] == bytes(len(mid.self_attr) - len(one))


def test_overflow_has_more_room_than_chain_head() -> None:
    """溢出槽的存在理由就是空间：同样槽长下容量大 160 位。"""
    assert spec.header_mid_attr_capacity(SMALL) == spec.header_start_attr_capacity(SMALL) + 160
    mid = slot.decode_header_mid(
        slot.encode_header_mid(block_id=BLOCK_ID, slot_size=SMALL),
        slot_size=SMALL,
    )
    assert mid.self_attr_num == 0


def test_empty_segment_has_zero_entries() -> None:
    head = slot.decode_header_start(
        slot.encode_header_start(
            header_slot_num=1,
            header_slot_end=0,
            data_slot_num=0,
            data_slot_end=0,
            block_body_size=0,
            block_id=BLOCK_ID,
            slot_size=SMALL,
        ),
        slot_size=SMALL,
    )
    assert head.self_attr_num == 0
    assert head.self_attr == bytes(14)


def test_data_slot_round_trip_and_end_flag() -> None:
    mid = slot.encode_data(body=b"body", end=False)
    assert slot.read_state(mid) is slot.SlotState.DATA_MID
    assert slot.verify(mid)
    assert slot.decode_data(mid).body[:4] == b"body"
    end = slot.encode_data(body=b"body", end=True)
    assert slot.read_state(end) is slot.SlotState.DATA_END
    assert slot.decode_data(end).state is slot.SlotState.DATA_END


def test_data_body_capacity_boundary() -> None:
    room = spec.data_body_capacity(SMALL) // spec.BITS_PER_BYTE
    assert room == 54
    assert slot.verify(slot.encode_data(body=b"y" * room, end=True, slot_size=SMALL))
    with pytest.raises(ValueError, match="槽体"):
        slot.encode_data(body=b"y" * (room + 1), end=True, slot_size=SMALL)


@pytest.mark.parametrize("offset", [0, 4, 20, 60, 1000])
def test_check_catches_corruption(offset: int) -> None:
    raw = bytearray(
        slot.encode_header_start(
            header_slot_num=1,
            header_slot_end=0,
            data_slot_num=0,
            data_slot_end=0,
            block_body_size=0,
            block_id=BLOCK_ID,
            self_attr=[entry(b"title", b"hi")],
        )
    )
    raw[offset] ^= 0x01
    assert not slot.verify(bytes(raw))


def test_decode_rejects_wrong_form() -> None:
    head = slot.encode_header_start(
        header_slot_num=1,
        header_slot_end=0,
        data_slot_num=0,
        data_slot_end=0,
        block_body_size=0,
        block_id=BLOCK_ID,
    )
    with pytest.raises(ValueError, match="不是 data 槽"):
        slot.decode_data(head)


def test_read_state_rejects_unknown_magic() -> None:
    with pytest.raises(ValueError, match="1 is not a valid"):
        slot.read_state(b"\x01\x00\x00\x00")


def test_block_id_must_be_16_bytes() -> None:
    with pytest.raises(ValueError, match="block_id"):
        slot.encode_header_mid(block_id=b"short")


def test_slot_size_must_fit_the_layout() -> None:
    with pytest.raises(ValueError, match="下界"):
        slot.encode_data(body=b"", end=True, slot_size=256)
    with pytest.raises(ValueError, match="整字节"):
        slot.encode_data(body=b"", end=True, slot_size=1001)


def test_decode_checks_slot_length() -> None:
    raw = slot.encode_data(body=b"x", end=False)
    with pytest.raises(ValueError, match="槽长应为"):
        slot.decode_data(raw[:-1])


def test_decode_rejects_impossible_attr_num() -> None:
    """条数乘最小条长都超过区域 → 槽被写坏，当场拒绝。"""
    raw = bytearray(slot.encode_header_mid(block_id=BLOCK_ID, slot_size=SMALL))
    spec.write_int32(raw, spec.HEADER_MID_ATTR_NUM, 1 << 20)
    with pytest.raises(ValueError, match="放不进"):
        slot.decode_header_mid(bytes(raw), slot_size=SMALL)

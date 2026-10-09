# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""pack 头：往返、计数不变量与由计数推出来的长度。"""

from __future__ import annotations

from typing import Any

import pytest

from oncasket._format import park, spec


def make(**changes: Any) -> park.PackHeader:
    """造一个计数自洽的头；`changes` 里的字段覆盖缺省。

    Args:
        **changes: 要改的字段。

    Returns:
        pack 头。
    """
    fields: dict[str, Any] = {
        "version": spec.FORMAT_VERSION,
        "slot_size": spec.SLOT_SIZE_DEFAULT,
        "slot_num": 64,
        "slot_live": 3,
        "slot_used": 2,
        "slot_dead": 1,
        "slot_empty": 0,
    }
    fields.update(changes)
    return park.PackHeader(**fields)


def test_round_trip() -> None:
    header = make()
    raw = park.encode_header(header)
    assert len(raw) == 128
    assert park.decode_header(raw) == header


def test_version_is_the_format_fingerprint() -> None:
    assert park.new_header().version == spec.FORMAT_VERSION
    assert len(spec.FORMAT_VERSION) == spec.bits_to_bytes(spec.PACK_VERSION[1]) == 32


def test_reserved_area_is_zeroed() -> None:
    assert park.encode_header(make())[56:128] == bytes(72)


def test_counts_are_little_endian() -> None:
    raw = park.encode_header(make(slot_size=8192, slot_num=0x0000_2000))
    assert raw[32:36] == (8192).to_bytes(4, "little")
    assert raw[32] == 0x00
    assert raw[33] == 0x20
    assert raw[36:40] == (0x0000_2000).to_bytes(4, "little")


def test_new_header_is_empty() -> None:
    header = park.new_header()
    assert (header.slot_live, header.slot_used, header.slot_dead, header.slot_empty) == (0, 0, 0, 0)
    assert header.slot_size == spec.SLOT_SIZE_DEFAULT
    assert header.slot_num == spec.SLOT_NUM_DEFAULT


def test_watermark_and_capacity() -> None:
    header = make(slot_num=64, slot_live=3)
    assert park.watermark_bits(header) == spec.PACK_HEADER_BITS + 3 * spec.SLOT_SIZE_DEFAULT
    assert park.capacity_bits(header) == spec.PACK_HEADER_BITS + 64 * spec.SLOT_SIZE_DEFAULT


@pytest.mark.parametrize(
    "changes",
    [
        {"slot_num": 0},
        {"slot_live": 65},
        {"slot_live": -1},
        {"slot_empty": 1},
        {"version": b"short"},
        {"slot_size": 256},
        {"slot_size": 1001},
        {"slot_used": -1},
    ],
    ids=[
        "槽数不能为 0",
        "水线不能超预算",
        "水线非负",
        "计数必须自洽",
        "版本宽度",
        "槽长下界",
        "整字节",
        "计数非负",
    ],
)
def test_validate_rejects(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r".+"):
        park.validate_header(make(**changes))


def test_decode_rejects_short_input() -> None:
    with pytest.raises(ValueError, match="pack 头需要"):
        park.decode_header(bytes(64))


def test_decode_validates() -> None:
    raw = bytearray(park.encode_header(make()))
    spec.write_int32(raw, spec.PACK_SLOT_LIVE, 9)  # 水线超预算
    with pytest.raises(ValueError, match="slot_live"):
        park.decode_header(bytes(raw))

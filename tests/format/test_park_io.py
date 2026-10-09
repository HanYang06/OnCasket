# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""park 文件：建 / 开 / 懒长 / 单槽读写。"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from oncasket._format import park, slot, spec


if TYPE_CHECKING:
    from typing import BinaryIO


BLOCK_ID = bytes(range(16))
#: 小槽：592 位 = 74 B
SLOT = 592


def new_park(tmp_path, *, slot_live: int = 0, slot_num: int = 16) -> park.ParkFile:
    """建一个 park，并把水线推到 `slot_live`。

    Args:
        tmp_path: 临时目录。
        slot_live: 初始水线。
        slot_num: 预算槽数。

    Returns:
        打开的句柄（调用方负责关）。
    """
    handle = park.ParkFile.create(tmp_path / "a.oncat", slot_size=SLOT, slot_num=slot_num)
    if slot_live:
        handle.grow_to(slot_live)
    return handle


def test_create_writes_only_the_header(tmp_path) -> None:
    with park.ParkFile.create(tmp_path / "a.oncat", slot_size=SLOT, slot_num=8) as handle:
        assert handle.path.name == "a.oncat"
        assert (tmp_path / "a.oncat").stat().st_size == park.HEADER_BYTES == 128
        assert handle.header.version == spec.FORMAT_VERSION
        assert (handle.header.slot_live, handle.header.slot_empty) == (0, 0)
        assert handle.slot_bytes == 74


def test_create_refuses_to_overwrite(tmp_path) -> None:
    park.ParkFile.create(tmp_path / "a.oncat", slot_size=SLOT, slot_num=8).close()
    with pytest.raises(FileExistsError):
        park.ParkFile.create(tmp_path / "a.oncat", slot_size=SLOT, slot_num=8)


def test_create_needs_the_parent_directory(tmp_path) -> None:
    """分片目录归 `_hub` 管，这里不替它建。"""
    with pytest.raises(FileNotFoundError):
        park.ParkFile.create(tmp_path / "nope" / "a.oncat", slot_size=SLOT, slot_num=8)


def test_create_rejects_a_bad_slot_size(tmp_path) -> None:
    with pytest.raises(ValueError, match="下界"):
        park.ParkFile.create(tmp_path / "a.oncat", slot_size=256, slot_num=8)


def test_load_reads_back_what_was_written(tmp_path) -> None:
    raw = slot.encode_data(body=b"hello", end=True, slot_size=SLOT)
    with new_park(tmp_path, slot_live=1) as handle:
        handle.write_slot(0, raw)
        header = handle.header
    with park.ParkFile.load(tmp_path / "a.oncat") as handle:
        assert handle.header == header
        assert handle.read_slot(0) == raw


def test_load_rejects_a_short_file(tmp_path) -> None:
    (tmp_path / "a.oncat").write_bytes(bytes(10))
    with pytest.raises(ValueError, match="读不满"):
        park.ParkFile.load(tmp_path / "a.oncat")


def test_load_rejects_a_header_with_bad_counts(tmp_path) -> None:
    with new_park(tmp_path, slot_live=1) as handle:
        handle.close()
    blob = bytearray((tmp_path / "a.oncat").read_bytes())
    spec.write_int32(blob, spec.PACK_SLOT_LIVE, 9)  # 水线超预算
    (tmp_path / "a.oncat").write_bytes(bytes(blob))
    with pytest.raises(ValueError, match="slot_live"):
        park.ParkFile.load(tmp_path / "a.oncat")


def test_write_slot_requires_a_generated_slot(tmp_path) -> None:
    with new_park(tmp_path) as handle, pytest.raises(ValueError, match="水线"):
        handle.write_slot(0, bytes(74))


def test_write_slot_requires_a_whole_slot(tmp_path) -> None:
    with new_park(tmp_path, slot_live=1) as handle, pytest.raises(ValueError, match="槽字节应为"):
        handle.write_slot(0, bytes(10))


def test_read_looks_at_the_file_not_the_watermark(tmp_path) -> None:
    """读只看文件：修复要看得见水线以外的残留。"""
    with new_park(tmp_path) as handle:
        handle.close()
    with (tmp_path / "a.oncat").open("ab") as handle:
        handle.write(bytes(2 * 74))  # 文件长到两个槽，头里却还是 0
    with park.ParkFile.load(tmp_path / "a.oncat") as handle:
        assert handle.header.slot_live == 0
        assert handle.read_slot(1) == bytes(74)
        with pytest.raises(ValueError, match="水线"):
            handle.write_slot(1, bytes(74))


def test_read_past_the_end_raises(tmp_path) -> None:
    with new_park(tmp_path) as handle, pytest.raises(ValueError, match="读不满"):
        handle.read_slot(0)


def test_grow_to_extends_the_file_and_counts_new_slots_empty(tmp_path) -> None:
    with new_park(tmp_path) as handle:
        header = handle.grow_to(3)
        assert (header.slot_live, header.slot_empty) == (3, 3)
        assert handle.size_bits == spec.PACK_HEADER_BITS + 3 * SLOT
        assert (tmp_path / "a.oncat").stat().st_size == 128 + 3 * 74
    with park.ParkFile.load(tmp_path / "a.oncat") as handle:
        assert (handle.header.slot_live, handle.header.slot_empty) == (3, 3)


def test_grow_to_is_monotone_and_bounded(tmp_path) -> None:
    with new_park(tmp_path, slot_live=4, slot_num=8) as handle:
        with pytest.raises(ValueError, match="只增不减"):
            handle.grow_to(2)
        with pytest.raises(ValueError, match="超过预算"):
            handle.grow_to(9)


def test_set_header_writes_through(tmp_path) -> None:
    with new_park(tmp_path, slot_live=2) as handle:
        header = park.PackHeader(
            version=handle.header.version,
            slot_size=SLOT,
            slot_num=16,
            slot_live=2,
            slot_used=1,
            slot_dead=0,
            slot_empty=1,
        )
        handle.set_header(header)
        assert handle.header == header
    with park.ParkFile.load(tmp_path / "a.oncat") as handle:
        assert (handle.header.slot_used, handle.header.slot_empty) == (1, 1)


def test_clear_state_touches_only_the_state(tmp_path) -> None:
    """清槽 = 把状态清成 empty，其余字节一个不碰（格式 §8）——`check` 因此不再自洽，是有意的。"""
    raw = slot.encode_data(body=b"hello", end=True, slot_size=SLOT)
    with new_park(tmp_path, slot_live=1) as handle:
        handle.write_slot(0, raw)
        handle.clear_state(0)
        after = handle.read_slot(0)
        assert slot.read_state(after) is slot.SlotState.EMPTY
        assert after[4:] == raw[4:]
        assert not slot.verify(after)


def test_clear_state_requires_a_generated_slot(tmp_path) -> None:
    with new_park(tmp_path) as handle, pytest.raises(ValueError, match="水线"):
        handle.clear_state(0)


def test_context_manager_closes_the_handle(tmp_path) -> None:
    with new_park(tmp_path, slot_live=1) as handle:
        assert not handle._handle.closed
    assert handle._handle.closed


def test_a_negative_slot_id_is_rejected(tmp_path) -> None:
    with new_park(tmp_path, slot_live=1) as handle, pytest.raises(ValueError, match="不能是负数"):
        handle.read_slot(-1)


class _StuckHandle:
    """一个字节都写不出去的句柄，用来验「卡住了就当场报错」。"""

    def seek(self, *_args: object) -> int:
        """假装定位成功。

        Args:
            *_args: 偏移与 whence，这里不关心。

        Returns:
            恒为 0。
        """
        return 0

    def write(self, _blob: memoryview) -> int:
        """假装写成功，实际一个字节没写。

        Args:
            _blob: 要写的字节。

        Returns:
            恒为 0。
        """
        return 0


def test_a_stuck_write_fails_loudly(tmp_path) -> None:
    """写不动就报错——不能在 `while` 里转圈。"""
    with new_park(tmp_path, slot_live=1) as handle:
        header = handle.header
    stuck = park.ParkFile(tmp_path / "a.oncat", cast("BinaryIO", _StuckHandle()), header)
    with pytest.raises(OSError, match="一个字节都没写出去"):
        stuck.write_slot(0, bytes(74))

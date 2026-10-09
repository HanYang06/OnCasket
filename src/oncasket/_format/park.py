# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""park：pack 文件布局、头与计数、水线懒长、单槽读写（格式 §5–§7）。

文件布局（位）：`[0, 1024)` 是头，槽 k 落在 `1024 + k × slot_size`，文件长度**正好到水线**。

- 水线长度（位）`= 1024 + slot_live × slot_size`——文件只长到水线，容量不预支磁盘（懒长）；
- 容量（位）`= 1024 + slot_num × slot_size`；
- 不变量：`slot_num ≥ 1`、`slot_live ≤ slot_num`、`slot_live = slot_used + slot_dead + slot_empty`。

两条纪律：

- **写要过水线，读只看文件**：`write_slot` 只认已经生成出来的槽（`slot_id < slot_live`）；
  `read_slot` 只受文件长度限制——修复得看得见水线以外的东西。
- **本模块不修不猜**：头不合法就抛；怎么处置由上层按[修复设计](../../../docs/design/repair.md)决定。

没用 `os.pwrite`：Windows 上没有它；写者由 park 级写锁串行（格式 §6），「seek ＋ 写」与它等价。
提交时序（①–⑦）归 `_ops/write.py`，不在这里。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from oncasket._format import spec


if TYPE_CHECKING:
    from pathlib import Path
    from typing import BinaryIO


#: pack 头在文件里占几个字节
HEADER_BYTES = spec.bits_to_bytes(spec.PACK_HEADER_BITS)


@dataclass(frozen=True, slots=True)
class PackHeader:
    """pack 头解出来的字段；保留区写 0、读不解释。"""

    version: bytes
    slot_size: int
    slot_num: int
    slot_live: int
    slot_used: int
    slot_dead: int
    slot_empty: int


def validate_header(header: PackHeader) -> None:
    """校验 pack 头与计数不变量。

    Args:
        header: pack 头。

    Raises:
        ValueError: 版本宽度不对、槽长非法，或计数越界 / 不自洽。
    """
    version_bytes = spec.bits_to_bytes(spec.PACK_VERSION[1])
    if len(header.version) != version_bytes:
        raise ValueError(f"version 必须是 {version_bytes} B，实际 {len(header.version)} B")
    spec.check_slot_size(header.slot_size)
    if not 1 <= header.slot_num <= spec.INT32_MAX:
        raise ValueError(f"slot_num {header.slot_num} 越界（1…{spec.INT32_MAX}）")
    if not 0 <= header.slot_live <= header.slot_num:
        raise ValueError(f"slot_live {header.slot_live} 不在 0…{header.slot_num} 之间")
    for name, value in (
        ("slot_used", header.slot_used),
        ("slot_dead", header.slot_dead),
        ("slot_empty", header.slot_empty),
    ):
        if not 0 <= value <= spec.INT32_MAX:
            raise ValueError(f"{name} {value} 超出 int32 非负范围")
    total = header.slot_used + header.slot_dead + header.slot_empty
    if header.slot_live != total:
        raise ValueError(
            f"计数不自洽：slot_live {header.slot_live} ≠ used + dead + empty = {total}"
        )


def new_header(
    *,
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
    slot_num: int = spec.SLOT_NUM_DEFAULT,
) -> PackHeader:
    """造一个新建 park 的头：计数全零，`version` 取当前格式指纹。

    Args:
        slot_size: 槽长（位）。
        slot_num: 预算槽数（容量上界）。

    Returns:
        计数全零的 pack 头。

    Raises:
        ValueError: 槽长或槽数越界。
    """
    header = PackHeader(
        version=spec.FORMAT_VERSION,
        slot_size=slot_size,
        slot_num=slot_num,
        slot_live=0,
        slot_used=0,
        slot_dead=0,
        slot_empty=0,
    )
    validate_header(header)
    return header


def encode_header(header: PackHeader) -> bytes:
    """把 pack 头编成文件开头的 1024 位。

    Args:
        header: pack 头。

    Returns:
        128 B 的头字节；保留区填 0。

    Raises:
        ValueError: 头不合法（见 `validate_header`）。
    """
    validate_header(header)
    data = bytearray(spec.bits_to_bytes(spec.PACK_HEADER_BITS))
    data[spec.field_slice(spec.PACK_VERSION)] = header.version
    for bounds, value in (
        (spec.PACK_SLOT_SIZE, header.slot_size),
        (spec.PACK_SLOT_NUM, header.slot_num),
        (spec.PACK_SLOT_LIVE, header.slot_live),
        (spec.PACK_SLOT_USED, header.slot_used),
        (spec.PACK_SLOT_DEAD, header.slot_dead),
        (spec.PACK_SLOT_EMPTY, header.slot_empty),
    ):
        spec.write_int32(data, bounds, value)
    return bytes(data)


def decode_header(data: bytes | bytearray) -> PackHeader:
    """解文件开头 1024 位的 pack 头。

    Args:
        data: 至少 128 B 的字节。

    Returns:
        解出来的字段。

    Raises:
        ValueError: 字节不够长，或头不合法（含计数不自洽）。
    """
    want = spec.bits_to_bytes(spec.PACK_HEADER_BITS)
    if len(data) < want:
        raise ValueError(f"pack 头需要 {want} B，实际 {len(data)} B")
    header = PackHeader(
        version=bytes(data[spec.field_slice(spec.PACK_VERSION)]),
        slot_size=spec.read_uint32(data, spec.PACK_SLOT_SIZE),
        slot_num=spec.read_uint32(data, spec.PACK_SLOT_NUM),
        slot_live=spec.read_uint32(data, spec.PACK_SLOT_LIVE),
        slot_used=spec.read_uint32(data, spec.PACK_SLOT_USED),
        slot_dead=spec.read_uint32(data, spec.PACK_SLOT_DEAD),
        slot_empty=spec.read_uint32(data, spec.PACK_SLOT_EMPTY),
    )
    validate_header(header)
    return header


def watermark_bits(header: PackHeader) -> int:
    """水线长度（位）：文件现在该有多长。

    Args:
        header: pack 头。

    Returns:
        头 ＋ 已生成出来的槽。
    """
    return spec.PACK_HEADER_BITS + header.slot_live * header.slot_size


def capacity_bits(header: PackHeader) -> int:
    """容量长度（位）：`slot_num` 用满时文件多长。

    Args:
        header: pack 头。

    Returns:
        头 ＋ 全部槽位。
    """
    return spec.PACK_HEADER_BITS + header.slot_num * header.slot_size


class ParkFile:
    """一个已打开的 park 文件：头、水线与单槽 IO。

    不用 `os.pwrite`：Windows 上没有它；写者由 park 级写锁串行（格式 §6），
    「seek ＋ 写」与它等价。句柄一律**不带缓冲**，这样「一个槽一次写」才是真的。
    """

    def __init__(self, path: Path, handle: BinaryIO, header: PackHeader) -> None:
        """不直接调；走 `create` / `load`。

        Args:
            path: 文件路径。
            handle: 不带缓冲的读写句柄。
            header: 已经解出来的 pack 头。
        """
        self._path = path
        self._handle = handle
        self._header = header

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        slot_size: int = spec.SLOT_SIZE_DEFAULT,
        slot_num: int = spec.SLOT_NUM_DEFAULT,
    ) -> ParkFile:
        """新建一个空 park：写头，文件长度就是水线（`slot_live = 0` → 只有头）。

        Args:
            path: 文件路径；**父目录得先有**（分片目录归 `_hub`）。
            slot_size: 槽长（位）。
            slot_num: 预算槽数。

        Returns:
            打开的句柄。

        Raises:
            FileExistsError: 路径上已经有东西——新建不覆盖。
            ValueError: 槽长或槽数越界。
        """
        header = new_header(slot_size=slot_size, slot_num=slot_num)
        handle = path.open("x+b", buffering=0)
        handle.write(encode_header(header))
        return cls(path, handle, header)

    @classmethod
    def load(cls, path: Path) -> ParkFile:
        """打开一个现成 park：只读头并校验，**不修不猜**。

        Args:
            path: 文件路径。

        Returns:
            打开的句柄。

        Raises:
            ValueError: 头读不满或头不合法（槽长非法、计数不自洽）——怎么处置归策略库。
        """
        handle = path.open("r+b", buffering=0)
        try:
            header = decode_header(_read_exactly(handle, 0, HEADER_BYTES))
        except ValueError:
            handle.close()
            raise
        return cls(path, handle, header)

    @property
    def path(self) -> Path:
        """文件路径。"""
        return self._path

    @property
    def header(self) -> PackHeader:
        """当前内存里的 pack 头。"""
        return self._header

    @property
    def slot_bytes(self) -> int:
        """一个槽占几个字节。"""
        return spec.bits_to_bytes(self._header.slot_size)

    @property
    def size_bits(self) -> int:
        """文件现在有多少位——**看文件**，不看计数（修复要靠它识破水线不对）。"""
        return self._handle.seek(0, os.SEEK_END) * spec.BITS_PER_BYTE

    def set_header(self, header: PackHeader) -> None:
        """盖头：校验后写回文件开头的 1024 位。

        Args:
            header: 新的 pack 头。

        Raises:
            ValueError: 头不合法（见 `validate_header`）。
        """
        self._write_at(0, encode_header(header))
        self._header = header

    def read_slot(self, slot_id: int) -> bytes:
        """读一个槽。

        Args:
            slot_id: 槽 id。

        Returns:
            整槽字节。

        Raises:
            ValueError: 槽 id 为负，或文件到那儿就不够了——**读只看文件长度**，
                所以修复能看见水线以外的残留。
        """
        return self._read_at(self._offset(slot_id), self.slot_bytes)

    def write_slot(self, slot_id: int, blob: bytes) -> None:
        """写一个槽：整槽一次写下去（格式 §7）。

        Args:
            slot_id: 槽 id。
            blob: 整槽字节。

        Raises:
            ValueError: 字节数不等于槽长，或这个槽还没生成出来（`slot_id ≥ slot_live`）。
        """
        if len(blob) != self.slot_bytes:
            raise ValueError(f"槽字节应为 {self.slot_bytes} B，实际 {len(blob)} B")
        self._write_at(self._within_watermark(slot_id), blob)

    def clear_state(self, slot_id: int) -> None:
        """把一个槽清成 `empty`：只动状态那 32 位，其余字节不碰（格式 §8）。

        Args:
            slot_id: 槽 id。

        Raises:
            ValueError: 这个槽还没生成出来。
        """
        state_bits = spec.SLOT_STATE[1]
        empty = spec.STATE_EMPTY.to_bytes(spec.bits_to_bytes(state_bits), "little")
        self._write_at(self._within_watermark(slot_id), empty)

    def grow_to(self, slot_live: int) -> PackHeader:
        """推进水线并让文件长到该有的大小；新生成出来的槽全记 `slot_empty`。

        先长文件、后盖头：崩在中间只会让文件比水线长（多占地方，不当作坏），
        反过来则会出现「头说有槽、文件里没有」。水线只增不减。

        Args:
            slot_live: 新的水线。

        Returns:
            新的 pack 头。

        Raises:
            ValueError: 水线变小，或超过预算 `slot_num`。
        """
        if slot_live < self._header.slot_live:
            raise ValueError(f"水线只增不减：{self._header.slot_live} → {slot_live}")
        if slot_live > self._header.slot_num:
            raise ValueError(f"水线 {slot_live} 超过预算 {self._header.slot_num}")
        grown = slot_live - self._header.slot_live
        self._handle.truncate(HEADER_BYTES + slot_live * self.slot_bytes)
        empty = self._header.slot_empty + grown
        header = replace(self._header, slot_live=slot_live, slot_empty=empty)
        self.set_header(header)
        return header

    def close(self) -> None:
        """关掉句柄；重复调用无害。"""
        self._handle.close()

    def __enter__(self) -> ParkFile:
        """进来就是自己（供 `with` 用）。"""
        return self

    def __exit__(self, *args: object) -> None:
        """出去就关掉（供 `with` 用）。

        Args:
            *args: 异常三元组，这里不关心。
        """
        self.close()

    def _offset(self, slot_id: int) -> int:
        """槽 id → 字节偏移。

        Args:
            slot_id: 槽 id。

        Returns:
            字节偏移。

        Raises:
            ValueError: 槽 id 为负。
        """
        if slot_id < 0:
            raise ValueError(f"槽 id 不能是负数：{slot_id}")
        return HEADER_BYTES + slot_id * self.slot_bytes

    def _within_watermark(self, slot_id: int) -> int:
        """槽 id → 字节偏移，且要求这个槽已经生成出来。

        Args:
            slot_id: 槽 id。

        Returns:
            字节偏移。

        Raises:
            ValueError: 槽 id 不在 `[0, slot_live)` 里。
        """
        if not 0 <= slot_id < self._header.slot_live:
            water = self._header.slot_live
            raise ValueError(f"槽 id {slot_id} 不在 0…{water - 1}（水线 {water}）")
        return self._offset(slot_id)

    def _read_at(self, offset: int, size: int) -> bytes:
        """从 `offset` 读满 `size` 字节。

        Args:
            offset: 字节偏移。
            size: 要读几个字节。

        Returns:
            读到的字节。

        Raises:
            ValueError: 文件到那儿就不够了。
        """
        return _read_exactly(self._handle, offset, size)

    def _write_at(self, offset: int, blob: bytes) -> None:
        """从 `offset` 把 `blob` 写满。

        Args:
            offset: 字节偏移。
            blob: 要写的字节。

        Raises:
            OSError: 底层写失败。
        """
        self._handle.seek(offset)
        view = memoryview(blob)
        while view:
            written = self._handle.write(view)
            if not written:  # 普通文件不会；真卡住了就得当场报错，不能在 while 里转圈
                raise OSError(f"写 {self._path} 偏移 {offset} 时一个字节都没写出去")
            view = view[written:]


def _read_exactly(handle: BinaryIO, offset: int, size: int) -> bytes:
    """从 `offset` 读满 `size` 字节；原始文件对象可能短读，所以要循环。

    Args:
        handle: 打开的句柄。
        offset: 字节偏移。
        size: 要读几个字节。

    Returns:
        读到的字节。

    Raises:
        ValueError: 文件到那儿就不够了。
    """
    handle.seek(offset)
    chunks: list[bytes] = []
    got = 0
    while got < size:
        chunk = handle.read(size - got)
        if not chunk:
            break
        chunks.append(chunk)
        got += len(chunk)
    if got != size:
        raise ValueError(f"文件在偏移 {offset} 处只有 {got} B，读不满 {size} B")
    return b"".join(chunks)

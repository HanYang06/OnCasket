# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""槽：三种形态的编解码与槽内 `check`（格式 §3–§5、§10）。

- 形态由 `slot_state` 的**值**决定，不靠位置推理：`header_start` / `header_mid` 是头槽的两种形态，
  `data_mid` / `data_end` 是 data 槽（末个标 `data_end`），`empty` 既可能是空也可能是死。
- `check` 只保本槽：输入串 = 本槽从 `slot_state` 到槽尾的全部字节，跳过自己的 `slot_write_check`；
  它是**故障守卫**、不是防篡改，块级完整性另有全局哈希（索引库 §009）。
- 自述区装的是**属性字典**（KV）：每段只记条目**个数**（`block_self_attr_num`），不记位长。
  本模块只管把条目字节装进区域、把条数写进字段，不解释条目内容；条目框架与拆条归 `block`。
- 解码给出的 `self_attr` 是**整段**（含尾部填充）：读到哪儿由条数说了算，与 `decode_data`
  返回整段槽体同一个口径。编码收的是**条目序列**，条数由此推出，写不出「条数对不上」的盘。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

import xxhash

from oncasket._format import spec


if TYPE_CHECKING:
    from collections.abc import Sequence


class SlotState(enum.IntEnum):
    """`slot_state`：32 位魔数，五个取值两两汉明距离 ≥ 14 位。"""

    EMPTY = spec.STATE_EMPTY
    HEADER_START = spec.STATE_HEADER_START
    HEADER_MID = spec.STATE_HEADER_MID
    DATA_MID = spec.STATE_DATA_MID
    DATA_END = spec.STATE_DATA_END


@dataclass(frozen=True, slots=True)
class HeaderStart:
    """链首头槽（`header_start`）解出来的字段。"""

    header_slot_num: int
    header_slot_end: int
    data_slot_num: int
    data_slot_end: int
    block_body_size: int
    self_attr_num: int
    block_id: bytes
    self_attr: bytes


@dataclass(frozen=True, slots=True)
class HeaderMid:
    """溢出头槽（`header_mid`）解出来的字段：不重复六个计数，只报本段条数。"""

    self_attr_num: int
    block_id: bytes
    self_attr: bytes


@dataclass(frozen=True, slots=True)
class DataSlot:
    """data 槽（`data_mid` / `data_end`）解出来的字段。"""

    state: SlotState
    body: bytes


def _blank(slot_size: int) -> bytearray:
    """造一个全零的槽。

    Args:
        slot_size: 槽长（位）。

    Returns:
        整槽字节。
    """
    return bytearray(spec.bits_to_bytes(slot_size))


def _check_slot(slot: bytes | bytearray, slot_size: int) -> None:
    """校验槽长合法、且整槽字节数与槽长一致。

    Args:
        slot: 整槽字节。
        slot_size: 槽长（位）。

    Raises:
        ValueError: 槽长非法，或字节数对不上。
    """
    spec.check_slot_size(slot_size)
    want = spec.bits_to_bytes(slot_size)
    if len(slot) != want:
        raise ValueError(f"槽长应为 {want} B，实际 {len(slot)} B")


def _check_block_id(block_id: bytes) -> None:
    """校验逻辑块 ID 的宽度。

    Args:
        block_id: 逻辑块 ID。

    Raises:
        ValueError: 不是 16 B。
    """
    if len(block_id) != spec.BLOCK_ID_BYTES:
        raise ValueError(f"block_id 必须是 {spec.BLOCK_ID_BYTES} B，实际 {len(block_id)} B")


def _join_attr(entries: Sequence[bytes], capacity_bits: int) -> tuple[bytes, int]:
    """把本段条目拼成字节，并数出条数。

    Args:
        entries: 本段条目字节，每条已按框架编好。
        capacity_bits: 本形态的属性容量（位）。

    Returns:
        (拼接后的字节, 条目个数)。

    Raises:
        ValueError: 本段放不下。
    """
    blob = b"".join(entries)
    need = len(blob) * spec.BITS_PER_BYTE
    if need > capacity_bits:
        raise ValueError(f"本段条目需要 {need} 位，本形态只有 {capacity_bits} 位")
    return blob, len(entries)


def _check_attr_num(num: int, segment_bytes: int) -> None:
    """校验条数与区域大小不矛盾。

    Args:
        num: 本段条目个数。
        segment_bytes: 本段区域的字节数。

    Raises:
        ValueError: 条数乘最小条长都超过区域，槽被写坏。
    """
    if num * spec.ATTR_ENTRY_OVERHEAD > segment_bytes:
        raise ValueError(f"本段 {num} 条放不进 {segment_bytes} B 的自述区")


def read_state(slot: bytes | bytearray) -> SlotState:
    """读槽状态。

    Args:
        slot: 整槽字节。

    Returns:
        槽状态。

    Raises:
        ValueError: 状态值不在 `slot_state` 的五个取值里。
    """
    return SlotState(spec.read_uint32(slot, spec.SLOT_STATE))


def compute_write_check(slot: bytes) -> bytes:
    """算槽内 `check`。

    Args:
        slot: 整槽字节。

    Returns:
        16 字节的 XXH3-128（算法原始输出，不翻端序）。
    """
    check_at = spec.field_slice(spec.SLOT_WRITE_CHECK)
    covered = slot[: check_at.start] + slot[check_at.stop :]
    return xxhash.xxh3_128(covered).digest()


def seal(slot: bytearray) -> None:
    """就地盖 `check`：写该槽之前先把字据算出来（格式 §7）。

    Args:
        slot: 整槽字节，`slot_write_check` 那一段被就地改写。
    """
    slot[spec.field_slice(spec.SLOT_WRITE_CHECK)] = compute_write_check(bytes(slot))


def verify(slot: bytes) -> bool:
    """重算 `check` 与槽里那份比对。

    Args:
        slot: 整槽字节。

    Returns:
        对得上为真。
    """
    on_disk = bytes(slot[spec.field_slice(spec.SLOT_WRITE_CHECK)])
    return compute_write_check(slot) == on_disk


def encode_header_start(
    *,
    header_slot_num: int,
    header_slot_end: int,
    data_slot_num: int,
    data_slot_end: int,
    block_body_size: int,
    block_id: bytes,
    self_attr: Sequence[bytes] = (),
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
) -> bytes:
    """编一个链首头槽（`header_start`）。

    Args:
        header_slot_num: 头槽区槽数（≥ 1）。
        header_slot_end: 头槽区最后一个槽的槽 id。
        data_slot_num: data 槽数。
        data_slot_end: data 区最后一个槽的槽 id（链尾）。
        block_body_size: 块体逻辑长度（位，不含填充）。
        block_id: 逻辑块 ID，16 B。
        self_attr: **本段**的条目字节（不含 `block_id`）；条数由它推出。
        slot_size: 槽长（位）。

    Returns:
        整槽字节，`check` 已盖。

    Raises:
        ValueError: 槽长非法、`block_id` 宽度不对，或本段条目放不下。
    """
    spec.check_slot_size(slot_size)
    _check_block_id(block_id)
    blob, num = _join_attr(self_attr, spec.header_start_attr_capacity(slot_size))
    slot = _blank(slot_size)
    spec.write_uint32(slot, spec.SLOT_STATE, SlotState.HEADER_START)
    spec.write_int32(slot, spec.HEADER_START_SLOT_NUM, header_slot_num)
    spec.write_int32(slot, spec.HEADER_START_SLOT_END, header_slot_end)
    spec.write_int32(slot, spec.HEADER_START_DATA_SLOT_NUM, data_slot_num)
    spec.write_int32(slot, spec.HEADER_START_DATA_SLOT_END, data_slot_end)
    spec.write_int32(slot, spec.HEADER_START_BODY_SIZE, block_body_size)
    head = spec.byte_offset(spec.HEADER_START_ATTR_BITS)
    slot[head : head + spec.BLOCK_ID_BYTES] = block_id
    attr_at = head + spec.BLOCK_ID_BYTES
    slot[attr_at : attr_at + len(blob)] = blob
    spec.write_int32(slot, spec.HEADER_START_ATTR_NUM, num)
    seal(slot)
    return bytes(slot)


def decode_header_start(
    slot: bytes | bytearray,
    *,
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
) -> HeaderStart:
    """解一个链首头槽（`header_start`）。

    Args:
        slot: 整槽字节。
        slot_size: 槽长（位）。

    Returns:
        解出来的字段；`self_attr` 是整段自述区（含尾部填充）。

    Raises:
        ValueError: 槽长对不上，或条数与自述区大小矛盾（槽被写坏）。
    """
    _check_slot(slot, slot_size)
    head = spec.byte_offset(spec.HEADER_START_ATTR_BITS)
    num = spec.read_uint32(slot, spec.HEADER_START_ATTR_NUM)
    segment = bytes(slot[head + spec.BLOCK_ID_BYTES :])
    _check_attr_num(num, len(segment))
    return HeaderStart(
        header_slot_num=spec.read_uint32(slot, spec.HEADER_START_SLOT_NUM),
        header_slot_end=spec.read_uint32(slot, spec.HEADER_START_SLOT_END),
        data_slot_num=spec.read_uint32(slot, spec.HEADER_START_DATA_SLOT_NUM),
        data_slot_end=spec.read_uint32(slot, spec.HEADER_START_DATA_SLOT_END),
        block_body_size=spec.read_uint32(slot, spec.HEADER_START_BODY_SIZE),
        self_attr_num=num,
        block_id=bytes(slot[head : head + spec.BLOCK_ID_BYTES]),
        self_attr=segment,
    )


def encode_header_mid(
    *,
    block_id: bytes,
    self_attr: Sequence[bytes] = (),
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
) -> bytes:
    """编一个溢出头槽（`header_mid`）。

    溢出槽存在的理由就是空间：除 320 位固定字段，剩下的全归自述区，个数没有上限。

    Args:
        block_id: 逻辑块 ID，16 B（每个头槽各一份，同值）。
        self_attr: **本段**的条目字节；条数由它推出。
        slot_size: 槽长（位）。

    Returns:
        整槽字节，`check` 已盖。

    Raises:
        ValueError: 槽长非法、`block_id` 宽度不对，或本段条目放不下。
    """
    spec.check_slot_size(slot_size)
    _check_block_id(block_id)
    blob, num = _join_attr(self_attr, spec.header_mid_attr_capacity(slot_size))
    slot = _blank(slot_size)
    spec.write_uint32(slot, spec.SLOT_STATE, SlotState.HEADER_MID)
    head = spec.byte_offset(spec.HEADER_MID_ATTR_BITS)
    slot[head : head + spec.BLOCK_ID_BYTES] = block_id
    attr_at = head + spec.BLOCK_ID_BYTES
    slot[attr_at : attr_at + len(blob)] = blob
    spec.write_int32(slot, spec.HEADER_MID_ATTR_NUM, num)
    seal(slot)
    return bytes(slot)


def decode_header_mid(
    slot: bytes | bytearray,
    *,
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
) -> HeaderMid:
    """解一个溢出头槽（`header_mid`）。

    Args:
        slot: 整槽字节。
        slot_size: 槽长（位）。

    Returns:
        解出来的字段；`self_attr` 是整段自述区（含尾部填充）。

    Raises:
        ValueError: 槽长对不上，或条数与自述区大小矛盾（槽被写坏）。
    """
    _check_slot(slot, slot_size)
    head = spec.byte_offset(spec.HEADER_MID_ATTR_BITS)
    num = spec.read_uint32(slot, spec.HEADER_MID_ATTR_NUM)
    segment = bytes(slot[head + spec.BLOCK_ID_BYTES :])
    _check_attr_num(num, len(segment))
    return HeaderMid(
        self_attr_num=num,
        block_id=bytes(slot[head : head + spec.BLOCK_ID_BYTES]),
        self_attr=segment,
    )


def encode_data(
    *,
    body: bytes,
    end: bool,
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
) -> bytes:
    """编一个 data 槽；链尾那个传 `end=True`（`data_end`），其余是 `data_mid`。

    Args:
        body: 本槽槽体字节。
        end: 是不是链尾槽。
        slot_size: 槽长（位）。

    Returns:
        整槽字节，`check` 已盖。

    Raises:
        ValueError: 槽长非法，或槽体放不下。
    """
    spec.check_slot_size(slot_size)
    need = len(body) * spec.BITS_PER_BYTE
    capacity = spec.data_body_capacity(slot_size)
    if need > capacity:
        raise ValueError(f"槽体需要 {need} 位，本形态只有 {capacity} 位")
    slot = _blank(slot_size)
    spec.write_uint32(slot, spec.SLOT_STATE, SlotState.DATA_END if end else SlotState.DATA_MID)
    body_at = spec.byte_offset(spec.DATA_BODY_BITS)
    slot[body_at : body_at + len(body)] = body
    seal(slot)
    return bytes(slot)


def decode_data(
    slot: bytes | bytearray,
    *,
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
) -> DataSlot:
    """解一个 data 槽。

    槽体返回**整段**（含填充）：一条链实际用了多少由块级 `block_body_size` 决定，
    不归槽管。不是 `data_mid` / `data_end` 就当场拒绝。

    Args:
        slot: 整槽字节。
        slot_size: 槽长（位）。

    Returns:
        解出来的字段。

    Raises:
        ValueError: 槽长对不上，或这个槽不是 data 槽。
    """
    _check_slot(slot, slot_size)
    state = read_state(slot)
    if state not in (SlotState.DATA_MID, SlotState.DATA_END):
        raise ValueError(f"不是 data 槽：{state.name}")
    body_at = spec.byte_offset(spec.DATA_BODY_BITS)
    return DataSlot(state=state, body=bytes(slot[body_at:]))

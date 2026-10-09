# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""盲扫：不读索引库，从水线起逐个槽认块（格式 §9）。

三条判据，与格式 §9 状态机一一对应：

- `empty` → **跳过**（空与死在盘上长得一样，死是分配策略的余项，盲扫管不着）；
- `header_start` 且**本槽 `check` 通过** → 认出一个块，按它自报的槽数整条跳过；
- 其余（头槽 `check` 不过、溢出槽与 data 槽的孤儿、认不出的魔数）→ **孤儿**，就地清成 `empty`。

扫出来的是**事实**，不是判定：`slot_used` 由它算，`slot_dead` 不行——死是分配策略的余项
（[空洞分配 §015](../../../docs/design/alloc.md)），盲扫看不见。怎么修由上层策略库按这些事实决定。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from oncasket._format import slot


if TYPE_CHECKING:
    from oncasket._format.park import ParkFile


@dataclass(frozen=True, slots=True)
class FoundBlock:
    """扫出来的一个块：链首槽 id 与它占几个槽。"""

    first_slot_id: int
    slot_num: int


@dataclass(frozen=True, slots=True)
class ScanResult:
    """一次盲扫的结果。"""

    blocks: tuple[FoundBlock, ...]
    orphans: tuple[int, ...]
    scanned: int
    cleared: bool

    @property
    def slot_used(self) -> int:
        """被这些块占掉的槽数。"""
        return sum(found.slot_num for found in self.blocks)


def scan_park(park: ParkFile, *, horizon: int | None = None, clear: bool = True) -> ScanResult:
    """盲扫一个 park，认块；顺手把孤儿槽清成 `empty`。

    Args:
        park: 打开的 park。
        horizon: 扫到第几个槽为止，默认取水线 `slot_live`。修复可以按**文件长度**另给一个
            ——「水线不对」本身就是要修的东西之一。
        clear: 认出来的孤儿是否就地清掉；清只动状态那 32 位（格式 §8）。

    Returns:
        扫出来的块、孤儿槽、扫了几个槽，以及有没有真清过。

    Raises:
        ValueError: 文件读不满——那不是「扫不了」，是文件缺了一截，同样交给策略库。
    """
    limit = park.header.slot_live if horizon is None else horizon
    blocks: list[FoundBlock] = []
    orphans: list[int] = []
    slot_id = 0
    while slot_id < limit:
        raw = park.read_slot(slot_id)
        if is_empty(raw):
            slot_id += 1
            continue
        span = chain_span(raw, slot_size=park.header.slot_size)
        if span is None:
            orphans.append(slot_id)
            slot_id += 1
            continue
        blocks.append(FoundBlock(first_slot_id=slot_id, slot_num=span))
        slot_id += span
    if clear and orphans:
        for orphan in orphans:
            park.clear_state(orphan)
    return ScanResult(
        blocks=tuple(blocks),
        orphans=tuple(orphans),
        scanned=limit,
        cleared=clear and bool(orphans),
    )


def is_empty(raw: bytes) -> bool:
    """这个槽是不是空的。

    空槽在格式 §9 里是**跳过**，既不算块也不算孤儿——空与死在盘上长得一样，
    死是分配策略的余项，盲扫管不着。认不出的魔数不算空（那是孤儿）。

    Args:
        raw: 整槽字节。

    Returns:
        状态正好是 `empty` 为真。
    """
    try:
        return slot.read_state(raw) is slot.SlotState.EMPTY
    except ValueError:
        return False


def chain_span(raw: bytes, *, slot_size: int) -> int | None:
    """认一个槽：是完整链的链首就给出链长，不是就给 None。

    Args:
        raw: 整槽字节。
        slot_size: 槽长（位）。

    Returns:
        链长（≥ 1）；孤儿槽、坏头槽、认不出的魔数一律给 None。
    """
    try:
        state = slot.read_state(raw)
    except ValueError:
        return None
    if state is not slot.SlotState.HEADER_START or not slot.verify(raw):
        return None
    try:
        head = slot.decode_header_start(raw, slot_size=slot_size)
    except ValueError:
        return None
    span = head.header_slot_num + head.data_slot_num
    return span if span > 0 else None

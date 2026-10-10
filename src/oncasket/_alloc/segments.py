# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""段表：内存派生视图，优先由索引库重建、退回盲扫，不落盘（空洞分配 §014）。

**段** = 同一 park 内一段**槽 id 连续**、且当前可复用的槽；分配与判定的单位都是段，
不是槽——一个块要么整段塞进某段，要么不塞。段表由 `slot_live` 与活块区间现算，
所以没有第二份真相要维护。
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Sequence


#: `taken` 的一条区间就是 `(起始槽 id, 槽数)` 两个数
SPAN_FIELDS = 2


@dataclass(frozen=True, slots=True)
class Segment:
    """一段连续槽。"""

    start: int  # 起始槽 id（含）
    length: int  # 槽数

    @property
    def end(self) -> int:
        """结束槽 id（不含）。"""
        return self.start + self.length


def free_segments(*, slot_live: int, taken: Sequence[tuple[int, int]]) -> list[Segment]:
    """在 `[0, slot_live)` 内挖掉被活块占掉的区间，剩下的就是空段。

    区间先排序再判重叠，所以 `taken` 的顺序不影响结果；返回的段按 `start` 升序，
    且两两不相邻（相邻的空段必须合并成一段）。`taken` 只描述「谁占着哪一段」，
    不问来源：索引库现成的行与盲扫结果都能喂进来。

    Args:
        slot_live: 该 park 的水线，`[0, slot_live)` 是已推进水线内可复用的槽。
        taken: 活块的 `(first_slot_id, slot_num)`，顺序任意。

    Returns:
        空段列表（升序、不相邻）；`taken` 为空时是整条水线，`slot_live == 0` 时是空列表。

    Raises:
        ValueError: `slot_live` 为负；区间元组不是二元；槽数为负或不是正数；
            起始槽 id 为负；区间越出水线；或区间之间重叠。
    """
    if slot_live < 0:
        raise ValueError(f"slot_live 不能为负：{slot_live}")
    spans = _checked_spans(slot_live=slot_live, taken=taken)
    if not spans:
        return [] if slot_live == 0 else [Segment(0, slot_live)]
    free: list[Segment] = []
    cursor = 0
    for start, slot_num in spans:
        if start > cursor:
            free.append(Segment(cursor, start - cursor))
        cursor = start + slot_num
    if cursor < slot_live:
        free.append(Segment(cursor, slot_live - cursor))
    return free


def _checked_spans(*, slot_live: int, taken: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """校验 `taken` 并归一化成按 `start` 升序的区间表。

    Args:
        slot_live: 该 park 的水线，区间不许越出它。
        taken: 活块的 `(first_slot_id, slot_num)`，顺序任意。

    Returns:
        按 `start` 升序的 `(start, slot_num)` 列表。

    Raises:
        ValueError: 任一元组不是二元；槽数为负或不是正数；起始槽 id 为负；
            区间越出水线；或区间之间重叠。
    """
    spans: list[tuple[int, int]] = []
    for index, entry in enumerate(taken):
        if len(entry) != SPAN_FIELDS:
            raise ValueError(f"taken[{index}] 应是 (起始槽 id, 槽数) 二元组，实得 {len(entry)} 元")
        start, slot_num = entry[0], entry[1]
        if slot_num < 0:
            raise ValueError(f"taken[{index}] 的槽数为负：{slot_num}")
        if start < 0:
            raise ValueError(f"taken[{index}] 的起始槽 id 为负：{start}")
        if slot_num <= 0:
            raise ValueError(f"taken[{index}] 的槽数应为正数：{slot_num}")
        if start + slot_num > slot_live:
            raise ValueError(
                f"taken[{index}] 越出水线：{start} + {slot_num} > slot_live={slot_live}"
            )
        spans.append((start, slot_num))
    spans.sort()
    for previous, current in pairwise(spans):
        if current[0] < previous[0] + previous[1]:
            raise ValueError(f"taken 里的区间重叠：{previous} 与 {current}")
    return spans

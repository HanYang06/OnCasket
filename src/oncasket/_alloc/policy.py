# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""段选择策略：`pick` 取值与「段表 → 挑中的段」（空洞分配 §014 第 3–4 节）。

策略是**配置型**：引擎内置几套，调用方按 hub 选一套，不把单一路线写死；默认
`best_fit`。死槽判定与额度是另一半（§015），不在这里。
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Sequence

    from oncasket._alloc.segments import Segment


class Pick(enum.StrEnum):
    """段选择策略：贴合最紧 / 最先够用 / 留最大的。"""

    BEST_FIT = "best_fit"
    FIRST_FIT = "first_fit"
    WORST_FIT = "worst_fit"


def parse_pick(name: str) -> Pick:
    """把配置里的 `pick` 字面量解析成 `Pick`。

    Args:
        name: `hub.conf.json` 里的 `pick` 取值，如 `"best_fit"`。

    Returns:
        对应的 `Pick` 成员。

    Raises:
        ValueError: `name` 不是任何一个合法取值。
    """
    try:
        return Pick(name)
    except ValueError:
        legal = " / ".join(member.value for member in Pick)
        raise ValueError(f"pick 取值非法：{name!r}；合法取值：{legal}") from None


def choose_free(segments: Sequence[Segment], needed: int, *, pick: Pick) -> Segment | None:
    """挑一段塞得下 `needed` 个槽的；挑不中给 `None`。

    候选 = `length >= needed` 的段；一个都没有就是「这轮没挑中」。段表先按
    `(start, length)` 升序排序再挑，所以输入顺序不影响结果，也不会原地改动调用方的列表。

    Args:
        segments: 候选空段表。
        needed: 需求槽数，必须为正。
        pick: 段选择策略：`best_fit` 取最小的候选，`first_fit` 取 `start` 最小的候选，
            `worst_fit` 取最大的候选；同长都取 `start` 小的。

    Returns:
        挑中的段；没有候选时给 `None`。

    Raises:
        ValueError: `needed <= 0`，或段表本身不合法（`start < 0` / `length <= 0`）。
    """
    if needed <= 0:
        raise ValueError(f"需求槽数应为正数：{needed}")
    ordered = _ordered_segments(segments)
    candidates = [segment for segment in ordered if segment.length >= needed]
    if not candidates:
        return None
    if pick is Pick.FIRST_FIT:
        return candidates[0]
    if pick is Pick.WORST_FIT:
        return max(candidates, key=lambda segment: (segment.length, -segment.start))
    return min(candidates, key=lambda segment: (segment.length, segment.start))


def _ordered_segments(segments: Sequence[Segment]) -> list[Segment]:
    """校验段表并按 `(start, length)` 升序返回**副本**。

    Args:
        segments: 候选空段表。

    Returns:
        排序后的新列表；调用方的列表一个元素都不动。

    Raises:
        ValueError: 有段的 `start < 0` 或 `length <= 0`。
    """
    for index, segment in enumerate(segments):
        if segment.start < 0:
            raise ValueError(f"segments[{index}] 的起始槽 id 为负：{segment.start}")
        if segment.length <= 0:
            raise ValueError(f"segments[{index}] 的段长应为正数：{segment.length}")
    return sorted(segments, key=lambda segment: (segment.start, segment.length))

# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""段表：`free_segments` 的挖洞、合并、乱序不变与各校验分支。"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import pytest

from oncasket._alloc.segments import Segment, free_segments


def spans(segments: list[Segment]) -> list[tuple[int, int]]:
    """把段表摊成 `(start, length)`，方便整表比对。

    Args:
        segments: 待摊平的段表。

    Returns:
        `(start, length)` 列表。
    """
    return [(segment.start, segment.length) for segment in segments]


def test_end_is_exclusive() -> None:
    segment = Segment(3, 4)
    assert (segment.start, segment.length, segment.end) == (3, 4, 7)
    assert Segment(0, 0).end == 0


def test_no_live_block_is_one_whole_segment() -> None:
    assert spans(free_segments(slot_live=10, taken=[])) == [(0, 10)]


def test_zero_live_is_empty() -> None:
    assert free_segments(slot_live=0, taken=[]) == []


def test_fully_taken_has_no_free_segment() -> None:
    assert free_segments(slot_live=10, taken=[(0, 10)]) == []


def test_taken_inside_is_punched_out() -> None:
    assert spans(free_segments(slot_live=10, taken=[(2, 3)])) == [(0, 2), (5, 5)]


def test_taken_at_both_edges() -> None:
    assert spans(free_segments(slot_live=9, taken=[(0, 2), (7, 2)])) == [(2, 5)]


def test_adjacent_taken_merge_the_free_segments() -> None:
    """活块首尾相接时不许冒出空段：相邻空段必须合并，也不许留零长段。"""
    got = free_segments(slot_live=12, taken=[(3, 2), (5, 2), (7, 2)])
    assert spans(got) == [(0, 3), (9, 3)]
    assert all(segment.length > 0 for segment in got)
    for left, right in pairwise(got):
        assert left.end < right.start


def test_order_of_taken_does_not_matter() -> None:
    taken = [(8, 2), (1, 3), (4, 1)]
    expected = [(0, 1), (5, 3), (10, 2)]
    assert spans(free_segments(slot_live=12, taken=taken)) == expected
    assert spans(free_segments(slot_live=12, taken=list(reversed(taken)))) == expected
    assert spans(free_segments(slot_live=12, taken=sorted(taken))) == expected


def test_negative_live_is_rejected() -> None:
    with pytest.raises(ValueError, match="slot_live 不能为负"):
        free_segments(slot_live=-1, taken=[])


def test_non_pair_entry_is_rejected() -> None:
    bad: Any = [(1, 2, 3)]
    with pytest.raises(ValueError, match=r"taken\[0\] 应是 .*二元组，实得 3 元"):
        free_segments(slot_live=8, taken=bad)


def test_negative_slot_num_is_rejected() -> None:
    with pytest.raises(ValueError, match="槽数为负"):
        free_segments(slot_live=8, taken=[(1, -2)])


def test_negative_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="起始槽 id 为负"):
        free_segments(slot_live=8, taken=[(-1, 2)])


def test_zero_slot_num_is_rejected() -> None:
    with pytest.raises(ValueError, match="槽数应为正数"):
        free_segments(slot_live=8, taken=[(1, 0)])


def test_taken_beyond_live_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"越出水线：6 \+ 3 > slot_live=8"):
        free_segments(slot_live=8, taken=[(6, 3)])


def test_taken_with_zero_live_is_rejected() -> None:
    """水线为 0 却报活块 = 输入自相矛盾：先校验，再走「水线为 0」的捷径。"""
    with pytest.raises(ValueError, match="越出水线"):
        free_segments(slot_live=0, taken=[(0, 1)])


def test_overlapping_taken_is_rejected_regardless_of_order() -> None:
    for taken in ([(1, 4), (3, 2)], [(3, 2), (1, 4)], [(3, 2), (4, 2), (1, 4)]):
        with pytest.raises(ValueError, match="重叠"):
            free_segments(slot_live=10, taken=taken)

# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""段选择策略：三种 `pick` 的黄金结果、挑不中、校验与 `parse_pick`。"""

from __future__ import annotations

import pytest

from oncasket._alloc.policy import Pick, choose_free, parse_pick
from oncasket._alloc.segments import Segment


#: 黄金候选表：三种策略在同一张表上各挑一段，结果互不相同。
CANDIDATES = [Segment(0, 6), Segment(10, 4), Segment(20, 9)]


def test_pick_values_are_the_config_literals() -> None:
    assert [member.value for member in Pick] == ["best_fit", "first_fit", "worst_fit"]
    assert isinstance(Pick.BEST_FIT, str)  # StrEnum：与 hub 配置里的字面量同源


def test_three_strategies_disagree_on_the_same_table() -> None:
    """黄金用例：需求 4 槽时贴合最紧 / 最先够用 / 留最大的各挑一段。"""
    assert choose_free(CANDIDATES, 4, pick=Pick.BEST_FIT) == Segment(10, 4)
    assert choose_free(CANDIDATES, 4, pick=Pick.FIRST_FIT) == Segment(0, 6)
    assert choose_free(CANDIDATES, 4, pick=Pick.WORST_FIT) == Segment(20, 9)


def test_fit_strategies_break_ties_by_lowest_start() -> None:
    table = [Segment(30, 5), Segment(10, 5), Segment(50, 5)]
    assert choose_free(table, 5, pick=Pick.BEST_FIT) == Segment(10, 5)
    assert choose_free(table, 5, pick=Pick.WORST_FIT) == Segment(10, 5)


def test_worst_fit_takes_the_largest_then_the_lowest_start() -> None:
    table = [Segment(40, 7), Segment(60, 9), Segment(5, 9)]
    assert choose_free(table, 7, pick=Pick.WORST_FIT) == Segment(5, 9)


def test_no_candidate_gives_none() -> None:
    assert choose_free(CANDIDATES, 10, pick=Pick.BEST_FIT) is None
    assert choose_free(CANDIDATES, 10, pick=Pick.FIRST_FIT) is None
    assert choose_free(CANDIDATES, 10, pick=Pick.WORST_FIT) is None
    assert choose_free([], 1, pick=Pick.BEST_FIT) is None


def test_needed_must_be_positive() -> None:
    for needed in (0, -3):
        with pytest.raises(ValueError, match="需求槽数应为正数"):
            choose_free(CANDIDATES, needed, pick=Pick.BEST_FIT)


def test_negative_start_segment_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"segments\[1\] 的起始槽 id 为负"):
        choose_free([Segment(4, 4), Segment(-1, 4)], 1, pick=Pick.BEST_FIT)


def test_non_positive_length_segment_is_rejected() -> None:
    for bad in (Segment(0, 0), Segment(0, -2)):
        with pytest.raises(ValueError, match=r"segments\[1\] 的段长应为正数"):
            choose_free([Segment(4, 4), bad], 1, pick=Pick.BEST_FIT)


def test_input_order_does_not_change_the_pick_and_the_list_is_untouched() -> None:
    """乱序输入同一结果；调用方的列表不许被原地排序。"""
    table = [Segment(20, 9), Segment(0, 6), Segment(10, 4)]
    before = list(table)
    for pick in Pick:
        assert choose_free(table, 4, pick=pick) == choose_free(CANDIDATES, 4, pick=pick)
    assert table == before


def test_parse_pick_round_trips_every_member() -> None:
    for member in Pick:
        assert parse_pick(member.value) is member


def test_parse_pick_rejects_unknown_names() -> None:
    for bad in ("", "best", "BEST_FIT", "closest_fit"):
        with pytest.raises(ValueError, match="合法取值") as excinfo:
            parse_pick(bad)
        for member in Pick:
            assert member.value in str(excinfo.value)

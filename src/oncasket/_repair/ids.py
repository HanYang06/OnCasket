# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""修复编号：日志里只出编号，不出症状（口径见 `docs/design/repair.md`）。

编号的含义只在 `config/repair.txt` 那一处对照表里；`tests/repair/test_repair_ids.py`
拿清单和这里对一遍，两边缺一即红。
"""

from __future__ import annotations

import enum


class Repair(enum.StrEnum):
    """一条修复的编号；只增不减、号不复用、全仓连号。"""

    R001 = "R001"
    R002 = "R002"
    R003 = "R003"

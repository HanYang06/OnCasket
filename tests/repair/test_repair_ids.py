# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""修复编号：`config/repair.txt` 与 `_repair.ids` 必须逐号对得上。"""

from __future__ import annotations

import re
from pathlib import Path

from oncasket._repair import ids


ROOT = Path(__file__).resolve().parent.parent.parent
FACT = ROOT / "config" / "repair.txt"

HEAD = re.compile(r"^repair (?P<rid>R\d{3})$")
FIELD = re.compile(r"^\s+(?P<key>\w+)\s+(?P<value>.+)$")

#: 清单里 `trigger` 一栏的取值（口径见 `docs/design/repair.md` §3）
TRIGGERS = frozenset({"内部异常", "自动"})

#: 一条修复固定四样：编号之外的三栏，加上头部那行的编号
FIELDS = frozenset({"name", "trigger", "recheck", "impl"})


def entries() -> dict[str, dict[str, str]]:
    """把清单拆成 `{编号: {字段: 取值}}`。

    跳过空行、`#` 注释与头部声明（头部那两行不带缩进，落不进字段正则）。

    Returns:
        按出现顺序的编号 → 字段表。
    """
    found: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in FACT.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        head = HEAD.match(line)
        if head is not None:
            current = {}
            found[head.group("rid")] = current
            continue
        body = FIELD.match(line)
        if body is not None and current is not None:
            current[body.group("key")] = body.group("value")
    return found


def test_ids_match_the_registry() -> None:
    """两向一致，而且连号——号不复用、不倒序。"""
    listed = list(entries())
    assert listed == [member.value for member in ids.Repair]
    assert listed == [f"R{number:03d}" for number in range(1, len(listed) + 1)]


def test_every_repair_has_the_four_fields() -> None:
    for rid, fields in entries().items():
        assert set(fields) == FIELDS, rid


def test_triggers_are_known() -> None:
    for rid, fields in entries().items():
        assert fields["trigger"] in TRIGGERS, rid

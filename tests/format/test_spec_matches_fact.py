# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""事实依据一致性：`_format` 的常量必须与 `config/format.txt` 逐项对上。

`config/format.txt` 是位级布局的唯一事实源。这里把它的行式 DSL 拆开，与 `spec` 里的常量比对：
改了一边没改另一边，本文件就红——这就是「位偏移先手工写、由测试对着 `.txt` 校」的落地。
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from oncasket._format import spec


if TYPE_CHECKING:
    from types import ModuleType


ROOT = Path(__file__).resolve().parent.parent.parent
FACT = ROOT / "config" / "format.txt"

#: 头部 `key: value;` 那几行
HEAD = re.compile(r"^[A-Za-z][\w-]*:")

#: 采样槽长 / 槽数：算带 `slot_size` 的区间时代入
SLOT_SIZE = 8192
SLOT_NUM = 8


@dataclass
class Row:
    """DSL 里的一行。"""

    level: int
    name: str
    kind: str
    extent: str
    children: list[Row] = field(default_factory=list)


def parse(text: str) -> list[Row]:
    """把行式 DSL 拆成带缩进的树。

    跳过空行、`#` 注释、`|` 标尺、`>` 换形态箭头与头部声明；缩进 4 空格一级。

    Args:
        text: 事实依据全文。

    Returns:
        顶层行列表，子行挂在 `children` 上。
    """
    root: list[Row] = []
    stack: list[Row] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "|", ">")) or HEAD.match(line):
            continue
        parts = line.split(maxsplit=2)
        if len(parts) < 2:
            continue
        level = (len(line) - len(line.lstrip())) // 4
        row = Row(
            level=level,
            name=parts[0],
            kind=parts[1],
            extent=parts[2].strip() if len(parts) > 2 else "",
        )
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].children.append(row)
        else:
            root.append(row)
        stack.append(row)
    return root


def child(rows: list[Row], name: str) -> Row:
    """按名字取第一个子行。

    Args:
        rows: 同级行。
        name: 行名。

    Returns:
        命中的行。

    Raises:
        AssertionError: 事实依据里没有这一行。
    """
    for row in rows:
        if row.name == name:
            return row
    raise AssertionError(f"事实依据里没有 {name}")


def eval_node(node: ast.expr) -> int:
    """求一个只含整数与 `+ - *` 的算式。

    Args:
        node: 表达式节点。

    Returns:
        整数值。

    Raises:
        AssertionError: 出现了 DSL 里没约定的算子。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.BinOp):
        left, right = eval_node(node.left), eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
    raise AssertionError(f"DSL 里不该出现这种算式：{ast.dump(node)}")


def measure(extent: str) -> int:
    """算区间的右半边：代入采样值后求 `+ - *`。

    Args:
        extent: 形如 `352:slot_size-352` 的区间。

    Returns:
        右半边的整数值。
    """
    expr = extent.split(":", 1)[1].strip("()")
    for name, value in (("slot_size", SLOT_SIZE), ("slot_num", SLOT_NUM)):
        expr = expr.replace(name, str(value))
    return eval_node(ast.parse(expr, mode="eval").body)


def bounds(row: Row) -> tuple[int, int]:
    """行代表的位区间 (起点, 终点)，**相对其父区**。

    带 `slot_size` 的右半边按 `region=start:length` 解释，纯字面量的按 `field=start:end`
    解释——事实依据里两类混写，靠这一点区分（见 `extent:` 头注）。

    Args:
        row: DSL 行。

    Returns:
        (起点, 终点)。
    """
    start, right = (part.strip() for part in row.extent.split(":", 1))
    start_at = 0 if start == "header" else int(start)
    if "slot_size" in right:
        return start_at, start_at + measure(row.extent)
    return start_at, int(right)


def load_stamper() -> ModuleType:
    """按路径加载 `scripts/stamp_version.py`：它不是包，没有可导入的名字。

    Returns:
        已执行的模块对象。
    """
    path = ROOT / "scripts" / "stamp_version.py"
    loader_spec = importlib.util.spec_from_file_location("stamp_version", path)
    assert loader_spec is not None
    assert loader_spec.loader is not None
    module = importlib.util.module_from_spec(loader_spec)
    sys.modules["stamp_version"] = module
    loader_spec.loader.exec_module(module)
    return module


def rows() -> list[Row]:
    """读并解析事实依据。

    Returns:
        顶层行列表。
    """
    return parse(FACT.read_text(encoding="utf-8"))


def slot_forms() -> list[Row]:
    """三种槽形态的行，按文件顺序：链首 → 溢出 → data。

    两种头槽形态在 DSL 里同名同型，只靠 `>` 换形态箭头分隔——所以只有顺序能区分。

    Returns:
        三个槽形态行。
    """
    return [row for row in rows() if row.name == "slot"]


def test_head_declares_little_endian_and_bits() -> None:
    text = FACT.read_text(encoding="utf-8")
    assert re.search(r"^endian:\s*little", text, re.MULTILINE)
    assert re.search(r"^Offset-unit:\s*bit", text, re.MULTILINE)


def test_format_fingerprint_matches_fact_file() -> None:
    text = FACT.read_text(encoding="utf-8")
    stamp = re.search(r"^encoding:.*version:\s*([0-9a-f]{64})", text, re.MULTILINE)
    assert stamp is not None
    assert stamp.group(1) == spec.FORMAT_VERSION_HEX
    assert load_stamper().digest(text) == spec.FORMAT_VERSION_HEX
    assert bytes.fromhex(spec.FORMAT_VERSION_HEX) == spec.FORMAT_VERSION


def test_pack_header_fields() -> None:
    pack = child(rows(), "format_pack")
    header = child(pack.children, "header")
    assert bounds(header) == (0, spec.PACK_HEADER_BITS)
    for name, want in (
        ("version", spec.PACK_VERSION),
        ("slot_size", spec.PACK_SLOT_SIZE),
        ("slot_num", spec.PACK_SLOT_NUM),
        ("slot_live", spec.PACK_SLOT_LIVE),
        ("slot_used", spec.PACK_SLOT_USED),
        ("slot_dead", spec.PACK_SLOT_DEAD),
        ("slot_empty", spec.PACK_SLOT_EMPTY),
    ):
        assert bounds(child(header.children, name)) == want, name
    reserved = bounds(child(header.children, "none"))
    assert reserved == spec.PACK_RESERVED
    assert reserved[1] == spec.PACK_HEADER_BITS


def test_slot_area_and_three_forms() -> None:
    tree = rows()
    pack = child(tree, "format_pack")
    area = bounds(child(pack.children, "slot"))
    assert area == (spec.PACK_HEADER_BITS, spec.PACK_HEADER_BITS + SLOT_SIZE * SLOT_NUM)
    forms = slot_forms()
    assert [row.kind for row in forms] == ["header_slot", "header_slot", "data_slot"]
    # 文件顺序即：链首 → 溢出 → data；两种头槽形态只靠这个顺序区分（中间有 `>` 箭头）
    assert bounds(forms[0]) == (0, SLOT_SIZE)
    assert bounds(forms[1]) == (0, SLOT_SIZE)
    assert bounds(forms[2]) == (0, SLOT_SIZE)


def test_chain_head_layout() -> None:
    head = slot_forms()[0]
    for name, want in (
        ("header_slot_state", spec.SLOT_STATE),
        ("slot_write_check", spec.SLOT_WRITE_CHECK),
        ("header_slot_num", spec.HEADER_START_SLOT_NUM),
        ("header_slot_end", spec.HEADER_START_SLOT_END),
        ("data_slot_num", spec.HEADER_START_DATA_SLOT_NUM),
        ("data_slot_end", spec.HEADER_START_DATA_SLOT_END),
        ("block_body_size", spec.HEADER_START_BODY_SIZE),
        ("block_self_attr_num", spec.HEADER_START_ATTR_NUM),
    ):
        assert bounds(child(head.children, name)) == want, name
    attr = child(head.children, "block_self_attr")
    assert bounds(attr) == (spec.HEADER_START_ATTR_BITS, SLOT_SIZE)
    assert bounds(child(attr.children, "block_id")) == spec.BLOCK_ID
    free_start, free_end = bounds(child(attr.children, "attr_entry"))
    assert free_start == spec.BLOCK_ID[1]
    assert free_end - free_start == spec.header_start_attr_capacity(SLOT_SIZE)


def test_overflow_layout() -> None:
    mid = slot_forms()[1]
    for name, want in (
        ("header_slot_state", spec.SLOT_STATE),
        ("slot_write_check", spec.SLOT_WRITE_CHECK),
        ("block_self_attr_num", spec.HEADER_MID_ATTR_NUM),
    ):
        assert bounds(child(mid.children, name)) == want, name
    attr = child(mid.children, "block_self_attr")
    assert bounds(attr) == (spec.HEADER_MID_ATTR_BITS, SLOT_SIZE)
    assert bounds(child(attr.children, "block_id")) == spec.BLOCK_ID
    free_start, free_end = bounds(child(attr.children, "attr_entry"))
    assert free_start == spec.BLOCK_ID[1]
    assert free_end - free_start == spec.header_mid_attr_capacity(SLOT_SIZE)


def test_data_layout() -> None:
    data = slot_forms()[2]
    assert bounds(child(data.children, "data_slot_state")) == spec.SLOT_STATE
    assert bounds(child(data.children, "slot_write_check")) == spec.SLOT_WRITE_CHECK
    body = child(data.children, "data_slot_body")
    assert bounds(body) == (spec.DATA_BODY_BITS, SLOT_SIZE)
    assert bounds(body)[1] - bounds(body)[0] == spec.data_body_capacity(SLOT_SIZE)


def test_slot_state_magics() -> None:
    table = child(rows(), "slot_state")
    assert table.kind == "enumerate(magic32)"
    for name, want in (
        ("header_start", spec.STATE_HEADER_START),
        ("header_mid", spec.STATE_HEADER_MID),
        ("data_mid", spec.STATE_DATA_MID),
        ("data_end", spec.STATE_DATA_END),
        ("empty", spec.STATE_EMPTY),
    ):
        row = child(table.children, name)
        assert row.extent.lower() == f"const:0x{want:08x}", name


def test_defaults() -> None:
    assert spec.HEADER_START_ATTR_BITS + spec.BLOCK_ID[1] == spec.SLOT_SIZE_MIN
    assert spec.bits_to_bytes(spec.PACK_HEADER_BITS) == 128

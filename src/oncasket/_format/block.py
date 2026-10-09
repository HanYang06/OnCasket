# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""block：块级属性字典、自述区分段与块链装配（格式 §3、§5、§7）。

自述区装的是**属性字典（KV）**，不是一段字节流：

- 一条条目 = `<名长:int32><名:utf-8><值长:int32><值:字节>`，两个长度都按**字节**计；
- 名是键、**全局唯一**；落盘**按名的 utf-8 字节序升序**——同一组属性走一遍，写出来的字节永远
  一样，`global_hash` 因此是内容确定的；
- 条目不可分割：放不下就**整条挪到下一个头槽**；单条上限 = 溢出头槽容量（`slot_size − 320` 位）。

分成两半，因为**地址是后知道的**（索引库 §009 的①与④之间隔着「找 park / 找段」）：

| 半 | 函数 | 知道什么 |
|---|---|---|
| 内容 | `plan_block` | 属性分段、块体分槽、六个计数；`budget_slot` / `block_size` 都在上面 |
| 字节 | `assemble_block` | 拿到 `first_slot_id` 后才能填 `header_slot_end` / `data_slot_end` |

`parse_block` 是反方向：逐槽验 `check`、核链长与两个 `*_end`，再把属性与块体拼回来。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from oncasket._format import slot, spec


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def encode_attr_entry(name: str, value: bytes) -> bytes:
    """编一条属性条目。

    Args:
        name: 属性名；落盘取它的 utf-8 字节。
        value: 属性值，任意字节。

    Returns:
        `<名长:u32><名><值长:u32><值>`。

    Raises:
        ValueError: 属性名为空——没有名字的键取不回来。
    """
    raw = name.encode("utf-8")
    if not raw:
        raise ValueError("属性名不能为空")
    return (
        len(raw).to_bytes(spec.ATTR_NAME_LEN_BYTES, "little")
        + raw
        + len(value).to_bytes(spec.ATTR_VALUE_LEN_BYTES, "little")
        + value
    )


def encode_attrs(attrs: Mapping[str, bytes]) -> list[bytes]:
    """把属性字典编成**按名升序**的条目序列。

    键唯一由映射本身保证——传进来的是字典，重名根本进不来。

    Args:
        attrs: 属性字典。

    Returns:
        条目字节列表，按名的 utf-8 字节序升序。
    """
    ordered = sorted(attrs, key=lambda name: name.encode("utf-8"))
    return [encode_attr_entry(name, attrs[name]) for name in ordered]


def decode_attrs(segment: bytes, num: int) -> dict[str, bytes]:
    """按条数把一段自述区解成属性字典。

    Args:
        segment: 一段自述区（`block_id` 之后的部分，含尾部填充）。
        num: 本段条数。

    Returns:
        属性字典。

    Raises:
        ValueError: 区域在条目中途结束、长度前缀越界、名不是 utf-8，或键重名（槽被写坏）。
    """
    attrs: dict[str, bytes] = {}
    at = 0
    for _ in range(num):
        if at + spec.ATTR_ENTRY_OVERHEAD > len(segment):
            raise ValueError("自述区在条目中途结束")
        name_len = int.from_bytes(segment[at : at + spec.ATTR_NAME_LEN_BYTES], "little")
        at += spec.ATTR_NAME_LEN_BYTES
        name = segment[at : at + name_len]
        if len(name) != name_len:
            raise ValueError("属性名越过了本段自述区")
        at += name_len
        value_len = int.from_bytes(segment[at : at + spec.ATTR_VALUE_LEN_BYTES], "little")
        at += spec.ATTR_VALUE_LEN_BYTES
        value = segment[at : at + value_len]
        if len(value) != value_len:
            raise ValueError("属性值越过了本段自述区")
        at += value_len
        try:
            key = name.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"属性名不是 utf-8：{name!r}") from exc
        if key in attrs:
            raise ValueError(f"属性重名：{key}")
        attrs[key] = value
    return attrs


def plan_attr_segments(
    entries: Sequence[bytes],
    *,
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
) -> list[list[bytes]]:
    """把排好序的条目切成逐段：第 0 段归链首头槽，其余归溢出头槽。

    段是按容量贪心切的：链首段装 `slot_size − 480` 位，此后每段装 `slot_size − 320` 位。
    一条都塞不进链首段时，第 0 段就是空的——链首槽照样在，它只带 `block_id`。

    Args:
        entries: 条目字节，已按名升序。
        slot_size: 槽长（位）。

    Returns:
        逐段的条目列表；没有属性时是 `[[]]`。

    Raises:
        ValueError: 有一条超过溢出头槽容量——那就是单条属性上限。
    """
    spec.check_slot_size(slot_size)
    head_room = spec.header_start_attr_capacity(slot_size) // spec.BITS_PER_BYTE
    rest_room = spec.header_mid_attr_capacity(slot_size) // spec.BITS_PER_BYTE
    segments: list[list[bytes]] = [[]]
    room = head_room
    used = 0
    for item in entries:
        if len(item) > rest_room:
            raise ValueError(f"单条属性 {len(item)} B 超过溢出头槽的 {rest_room} B 上限")
        if used + len(item) > room:
            segments.append([])
            room, used = rest_room, 0
        segments[-1].append(item)
        used += len(item)
    return segments


@dataclass(frozen=True, slots=True)
class BlockPlan:
    """块的内容：与「落在哪个 park、哪个槽」无关的那一半。"""

    block_id: bytes
    segments: tuple[tuple[bytes, ...], ...]
    chunks: tuple[bytes, ...]
    block_body_size: int
    slot_size: int

    @property
    def header_slot_num(self) -> int:
        """头槽区槽数（≥ 1：链首那一个永远在）。"""
        return len(self.segments)

    @property
    def data_slot_num(self) -> int:
        """块体占了几个 data 槽（可为 0）。"""
        return len(self.chunks)

    @property
    def slot_num(self) -> int:
        """这条链总共占几个槽——索引库的 `budget_slot`。"""
        return self.header_slot_num + self.data_slot_num

    @property
    def block_size(self) -> int:
        """这条链占多少字节——索引库的 `block_size`。"""
        return self.slot_num * spec.bits_to_bytes(self.slot_size)


@dataclass(frozen=True, slots=True)
class Block:
    """解出来的一条完整块。"""

    block_id: bytes
    attrs: dict[str, bytes]
    body: bytes
    header_slot_num: int
    data_slot_num: int


def plan_block(
    *,
    block_id: bytes,
    attrs: Mapping[str, bytes] | None = None,
    body: bytes = b"",
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
) -> BlockPlan:
    """把块的内容定下来：属性分段、块体分槽、六个计数——**不含地址**。

    Args:
        block_id: 逻辑块 ID，16 B。
        attrs: 属性字典。
        body: 块体。
        slot_size: 槽长（位）。

    Returns:
        块计划。

    Raises:
        ValueError: `block_id` 宽度不对、槽长非法，或属性放不下（`block_body_size` 的 int32
            上限由编码那一步的 `write_int32` 兜住）。
    """
    spec.check_slot_size(slot_size)
    if len(block_id) != spec.BLOCK_ID_BYTES:
        raise ValueError(f"block_id 必须是 {spec.BLOCK_ID_BYTES} B，实际 {len(block_id)} B")
    segments = plan_attr_segments(encode_attrs(attrs or {}), slot_size=slot_size)
    room = spec.data_body_capacity(slot_size) // spec.BITS_PER_BYTE
    chunks = tuple(body[at : at + room] for at in range(0, len(body), room))
    return BlockPlan(
        block_id=block_id,
        segments=tuple(tuple(segment) for segment in segments),
        chunks=chunks,
        block_body_size=len(body) * spec.BITS_PER_BYTE,
        slot_size=slot_size,
    )


def assemble_block(plan: BlockPlan, *, first_slot_id: int) -> list[bytes]:
    """把计划落成槽字节：链首头槽 → 溢出槽若干 → data 槽若干（末个标 `data_end`）。

    Args:
        plan: 块计划。
        first_slot_id: 链首槽在 park 里的槽 id——两个 `*_end` 字段按它算，所以不给不行。

    Returns:
        整条链的槽字节，按槽 id 升序。

    Raises:
        ValueError: 槽 id 或计数越界（计数是 int32，`first_slot_id` 非负）。
    """
    header_end = first_slot_id + plan.header_slot_num - 1
    head = slot.encode_header_start(
        header_slot_num=plan.header_slot_num,
        header_slot_end=header_end,
        data_slot_num=plan.data_slot_num,
        data_slot_end=header_end + plan.data_slot_num,
        block_body_size=plan.block_body_size,
        block_id=plan.block_id,
        self_attr=plan.segments[0],
        slot_size=plan.slot_size,
    )
    overflow_slots = [
        slot.encode_header_mid(block_id=plan.block_id, self_attr=segment, slot_size=plan.slot_size)
        for segment in plan.segments[1:]
    ]
    body_slots = [
        slot.encode_data(body=chunk, end=index == plan.data_slot_num - 1, slot_size=plan.slot_size)
        for index, chunk in enumerate(plan.chunks)
    ]
    return [head, *overflow_slots, *body_slots]


def parse_block(
    slots: Sequence[bytes],
    *,
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
    first_slot_id: int | None = None,
) -> Block:
    """解一条完整的链。

    Args:
        slots: 从链首开始的整条链。
        slot_size: 槽长（位）。
        first_slot_id: 链首槽的槽 id；给了就顺便核两个 `*_end` 字段。

    Returns:
        解出来的块。

    Raises:
        ValueError: 缺槽、`check` 不过、链长或 `*_end` 对不上、`block_id` 不一致、属性重名，
            或块体长度与 data 槽装不下。
    """
    spec.check_slot_size(slot_size)
    if not slots:
        raise ValueError("链至少要有一个头槽")
    for index, raw in enumerate(slots):
        if not slot.verify(raw):
            raise ValueError(f"第 {index} 个槽的 check 对不上")
    head = slot.decode_header_start(slots[0], slot_size=slot_size)
    if head.header_slot_num < 1:
        raise ValueError(f"header_slot_num 至少是 1，盘上是 {head.header_slot_num}")
    on_chain = head.header_slot_num + head.data_slot_num
    if on_chain != len(slots):
        raise ValueError(f"链长对不上：应有 {on_chain} 个槽，实到 {len(slots)}")
    attrs = decode_attrs(head.self_attr, head.self_attr_num)
    for index in range(1, head.header_slot_num):
        mid = slot.decode_header_mid(slots[index], slot_size=slot_size)
        if mid.block_id != head.block_id:
            raise ValueError(f"第 {index} 个头槽的 block_id 与链首不一致")
        _merge_attrs(attrs, decode_attrs(mid.self_attr, mid.self_attr_num))
    if head.data_slot_end != head.header_slot_end + head.data_slot_num:
        raise ValueError("data_slot_end 与 header_slot_end ＋ data_slot_num 对不上")
    if (
        first_slot_id is not None
        and head.header_slot_end != first_slot_id + head.header_slot_num - 1
    ):
        raise ValueError(
            f"header_slot_end {head.header_slot_end} 与链首槽 id {first_slot_id} 对不上"
        )
    return Block(
        block_id=head.block_id,
        attrs=attrs,
        body=_collect_body(slots, head, slot_size=slot_size),
        header_slot_num=head.header_slot_num,
        data_slot_num=head.data_slot_num,
    )


def _merge_attrs(target: dict[str, bytes], source: Mapping[str, bytes]) -> None:
    """把一段的属性并进总表——**跨段重名同样是损坏**。

    Args:
        target: 总表，就地更新。
        source: 本段的属性。

    Raises:
        ValueError: 键已在总表里。
    """
    for key, value in source.items():
        if key in target:
            raise ValueError(f"属性重名：{key}")
        target[key] = value


def _collect_body(slots: Sequence[bytes], head: slot.HeaderStart, *, slot_size: int) -> bytes:
    """把 data 槽拼成块体，并按 `block_body_size` 裁掉填充。

    Args:
        slots: 整条链。
        head: 链首解出来的字段。
        slot_size: 槽长（位）。

    Returns:
        块体字节。

    Raises:
        ValueError: 末个 data 槽没标 `data_end`、中间的标了，或 `block_body_size` 装不下。
    """
    blob = bytearray()
    for offset in range(head.data_slot_num):
        data = slot.decode_data(slots[head.header_slot_num + offset], slot_size=slot_size)
        is_last = offset == head.data_slot_num - 1
        if is_last and data.state is not slot.SlotState.DATA_END:
            raise ValueError("末个 data 槽没标 data_end")
        if not is_last and data.state is slot.SlotState.DATA_END:
            raise ValueError(f"第 {offset} 个 data 槽提前标了 data_end")
        blob += data.body
    want = spec.bits_to_bytes(head.block_body_size)
    if want > len(blob):
        raise ValueError(f"块体要 {want} B，链上的槽只有 {len(blob)} B")
    return bytes(blob[:want])

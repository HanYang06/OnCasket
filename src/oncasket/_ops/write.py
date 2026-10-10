# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
r"""提交路径 ①–⑦：预算 → 索引行 → 选址 → 物理写 → 校验 → 翻 state → 地址回流。

| # | 动作 | 落点 | 这一步在做什么 |
|---|---|---|---|
| ① | 定内容 | 内存 | `plan_block`：属性分段、块体分槽、六个计数、`budget_slot` |
| ③ | 找载体与段 | 内存 | 段表 ＋ 策略挑一段；挑不中就扩水线，再不行就新建 park |
| — | 拼字节 | 内存 | `assemble_block` 要段起点，`global_hash` 要拼出来的字节 |
| ② | 写索引行 | 库 | `state = pending`、地址留空——崩在这儿留一行待对账的痕迹 |
| ④ | 落槽 | 载体 | 头槽 → 溢出槽\\* → data 槽\\*（末个标 `data_end`），一个槽一次写 |
| ⑤ | 复检 | 载体 | 逐个槽重新读回来：逐槽 `check` ＋ 整块 `global_hash` |
| ⑥ | 提交点 | 库 | `state → ok` |
| ⑦ | 地址回流 | 库 | `park` ＋ `first_slot_id`（**地址永远是最后一步**） |

**为什么 ③ 排在 ② 前面**：`global_hash` 要等字节拼出来才知道，而字节里的两个 `*_end`
依赖段起点（格式 §3）——先写行就没东西可写。改的只是「选段」这一步的先后：
选段不落盘，② 仍在 ④ 之前落库，**地址最后回流**这条没动。

段表是内存派生视图（空洞分配 §014）：优先由索引库的地址行重建，库与载体的计数对不上
（半截提交 / 没回流的块）就退回盲扫拿事实（格式 §9）。判死不在这一步——额度与账本归
路线 015，本层只用「挑得中 / 挑不中」。

半写态靠 ⑤ 与逐槽 `check` 判废；崩在中间留下的 `pending` 行交 GC 对账（索引库 §009 异常表）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from oncasket._alloc.policy import Pick, choose_free, parse_pick
from oncasket._alloc.segments import free_segments
from oncasket._errors import ConflictError, CorruptError, NotFoundError
from oncasket._format import scan, spec
from oncasket._format.block import assemble_block, global_hash, parse_block, plan_block
from oncasket._format.park import ParkFile
from oncasket._hub import layout
from oncasket._index import commit
from oncasket._index.store import BlockRow, Role
from oncasket._ops import read as read_module


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from oncasket._format.block import Block
    from oncasket._ops.session import HubSession


#: 角色字符串：数据块 / 索引块（与公开面的 `Ref.data` / `Ref.index` 同值——公开面住在 `api`，
#: 它在分层表里比 `_ops` 高，所以这两条常量只能各写一处，别的地方请引用这里）
ROLE_DATA = "data"
ROLE_INDEX = "index"


def role_of(ref: str) -> Role:
    """把角色字符串翻成身份分表的归属。

    取值**开放、不枚举**（公开 API §2）：认得的 `index` 进索引分表，其余一律当数据块——
    「打错字是调用方自己的事」，引擎不替 Python 定义非法取值。

    Args:
        ref: 角色字符串，空串表示没定过。

    Returns:
        身份。
    """
    return Role.INDEX if ref == ROLE_INDEX else Role.DATA


@dataclass(slots=True)
class Placement:
    """挑好的落点：一个开着的载体 ＋ 链首槽 ＋ 要占几个槽。"""

    name: str
    park: ParkFile
    first_slot_id: int
    slot_num: int

    def close(self) -> None:
        """关掉载体句柄。"""
        self.park.close()


def write_block(
    session: HubSession,
    *,
    attrs: Mapping[str, bytes] | None = None,
    body: bytes = b"",
    kind: str = "",
    role: Role = Role.DATA,
    block_id: bytes | None = None,
    slot_size: int = spec.SLOT_SIZE_DEFAULT,
    park: str | None = None,
) -> bytes:
    """①–⑦ 一口气走完，返回 `block_id`（产物只有 id；地址是引擎的账）。

    Args:
        session: 开着的 hub 会话。
        attrs: 属性字典；落盘按名的 utf-8 字节序升序。
        body: 块体。
        kind: 身份分表里的 `kind`（开放取值，不枚举）。
        role: 逻辑块身份（数据块 / 索引块）。
        block_id: 逻辑块 ID；不给就由引擎生成 uuid4（128 位）。
        slot_size: 槽长（位）；同一 park 内必须一致。
        park: 点名要的载体；不给就在现有载体里挑，挑不中新建。

    Returns:
        这条块的 `block_id`。

    Raises:
        ValueError: 参数不合法（`block_id` 宽度、槽长、属性放不下）。
        NotFoundError: 点名要的载体不在。
        CorruptError: ⑤ 复检不过——刚写下去的东西自己都验不过。
        LockTimeoutError: 等写锁超时。
    """
    plan = plan_block(
        block_id=uuid.uuid4().bytes if block_id is None else block_id,
        attrs=attrs,
        body=body,
        slot_size=slot_size,
    )
    with session.write_lock():
        placement = _allocate(session, needed=plan.slot_num, slot_size=slot_size, park=park)
        try:
            slots = assemble_block(plan, first_slot_id=placement.first_slot_id)
            digest = global_hash(slots)
            commit.write_pending(
                session.store,
                block_id=plan.block_id,
                budget_slot=plan.slot_num,
                block_size=plan.block_size,
                global_hash=digest,
                kind=kind,
                role=role,
            )
            _occupy(placement, slots)
            _verify(placement, slots, digest)
            commit.mark_ok(session.store, plan.block_id)
            commit.reflux_address(
                session.store,
                plan.block_id,
                park=placement.name,
                first_slot_id=placement.first_slot_id,
            )
        finally:
            placement.close()
    return plan.block_id


def update_block(
    session: HubSession,
    block_id: bytes,
    *,
    attrs: Mapping[str, bytes] | None = None,
    body: bytes | None = None,
) -> bytes:
    """改（035）：**基准点 ＋ 新值**。读回现役 → 应用新值 → 写前验一次。

    机制与判据（公开 API §8）：

    - 先按基准点把**现役那一份**读回来——读的过程必然带强校验（逐槽 `check` ＋ 整块哈希）；
    - 应用新值后**写前再验一次**：库里的 `global_hash` 还是不是读回来那一份？不是就说明
      中途被别处改过，**不静默覆盖**，抛 `ConflictError`（乐观并发）；
    - 改的是属性与块体，不是「块」：`attrs` 只覆盖点名的键，`body` 不给就沿用现役那份；
    - 新内容先落，库侧换成新地址，**最后**才释放旧段。崩在中间最坏是多占一段
      （旧段还记在 `used` 里），不丢数据。

    Args:
        session: 开着的 hub 会话。
        block_id: 基准点：逻辑块 ID（或索引查出来的那个 id）。
        attrs: 要改的属性；只覆盖点名的键，其余沿用。
        body: 新的块体；不给就沿用现役那份。

    Returns:
        还是那个 `block_id`（改不改都不换身份）。

    Raises:
        NotFoundError: 基准点找不到。
        OnCasketError: `state = pending`——这次提交没走完，改不动。
        CorruptError: 现役那一份读回来验不过。
        ConflictError: 基准点还在，但已经不是现役（写前验不过）。
        LockTimeoutError: 等写锁超时。
    """
    with session.write_lock():
        row = read_module.row_of(session, block_id)
        current = read_module.read_block(session, block_id)
        merged = dict(current.attrs)
        if attrs:
            merged.update(attrs)
        slot_size = _slot_size_of(session, row)
        plan = plan_block(
            block_id=block_id,
            attrs=merged,
            body=current.body if body is None else body,
            slot_size=slot_size,
        )
        placement = _allocate(session, needed=plan.slot_num, slot_size=slot_size, park=None)
        try:
            slots = assemble_block(plan, first_slot_id=placement.first_slot_id)
            digest = global_hash(slots)
            _occupy(placement, slots)
            _verify(placement, slots, digest)
            swapped = session.store.replace_content(
                block_id,
                expected_hash=row.global_hash,
                global_hash=digest,
                budget_slot=plan.slot_num,
                block_size=plan.block_size,
                park=placement.name,
                first_slot_id=placement.first_slot_id,
            )
            if not swapped:
                free_slots(placement.park, placement.first_slot_id, len(slots))
                raise ConflictError(f"基准点已不是现役：{block_id.hex()}")
        finally:
            placement.close()
        _free_old(session, row, current)
    return block_id


def _slot_size_of(session: HubSession, row: BlockRow) -> int:
    """现役那一份用的槽长——从它所在的载体头上取，同一份内容要按同样的槽长铺。

    Args:
        session: 开着的 hub 会话。
        row: 现役那一行的索引行。

    Returns:
        槽长（位）；载体已经不在就退回缺省槽长。
    """
    if row.park is None:
        return spec.SLOT_SIZE_DEFAULT
    path = session.park_path(row.park)
    if not path.is_file():
        return spec.SLOT_SIZE_DEFAULT
    with ParkFile.load(path) as park:
        return park.header.slot_size


def _free_old(session: HubSession, row: BlockRow, current: Block) -> None:
    """换成功之后释放旧段（格式 §8 的顺序：先头槽、再其余）。

    Args:
        session: 开着的 hub 会话。
        row: 换之前那一行的索引行（地址还是旧地址）。
        current: 换之前那一份内容（用来数旧链有几个槽）。
    """
    if row.park is None or row.first_slot_id is None:
        return
    path = session.park_path(row.park)
    if not path.is_file():
        return
    with ParkFile.load(path) as park:
        free_slots(park, row.first_slot_id, current.header_slot_num + current.data_slot_num)


def free_slots(park: ParkFile, first_slot_id: int, slot_num: int) -> None:
    """释放一段槽：先把头槽清成 `empty`，再清其余槽，最后把计数从 `used` 挪回 `empty`。

    顺序就是格式 §8 的顺序：崩在第一步之后，剩下的是孤儿槽、扫描时逐个清掉；
    崩在第一步之前，块还完整、幂等重做。

    Args:
        park: 打开的载体。
        first_slot_id: 这段槽的起点。
        slot_num: 占几个槽。

    Raises:
        ValueError: 槽不在水线以内，或计数被减成负的。
    """
    park.clear_state(first_slot_id)
    for offset in range(1, slot_num):
        park.clear_state(first_slot_id + offset)
    header = park.header
    park.set_header(
        replace(
            header,
            slot_used=header.slot_used - slot_num,
            slot_empty=header.slot_empty + slot_num,
        )
    )


def _allocate(session: HubSession, *, needed: int, slot_size: int, park: str | None) -> Placement:
    """③ 找载体与段：现有载体里挑一段连续空槽，挑不中就扩水线，再不行就新建一个载体。

    Args:
        session: 开着的 hub 会话。
        needed: 要几个槽。
        slot_size: 槽长（位）。
        park: 点名要的载体；不给就按现有载体顺序挑。

    Returns:
        挑好的落点，载体句柄**已经开着**，调用方负责关。

    Raises:
        NotFoundError: 点名要的载体不在。
        ValueError: 段表或策略取值不合法。
    """
    pick = parse_pick(session.manifest.alloc_pick())
    if park is not None:
        path = session.park_path(park)
        if not path.is_file():
            raise NotFoundError(f"点名的载体不在：{park}")
        return _place(
            ParkFile.load(path), park, session, needed=needed, slot_size=slot_size, pick=pick
        )
    for path in layout.find_parks(session.path):
        candidate = ParkFile.load(path)
        start = _start_in(candidate, session, needed=needed, slot_size=slot_size, pick=pick)
        if start is not None:
            return Placement(name=path.stem, park=candidate, first_slot_id=start, slot_num=needed)
        candidate.close()
    return _new_park(session, needed=needed, slot_size=slot_size)


def _place(
    candidate: ParkFile,
    name: str,
    session: HubSession,
    *,
    needed: int,
    slot_size: int,
    pick: Pick,
) -> Placement:
    """点名的载体上找一段；找不到就换一个新载体。

    Args:
        candidate: 已经打开的载体。
        name: 载体名。
        session: 开着的 hub 会话。
        needed: 要几个槽。
        slot_size: 槽长（位）。
        pick: 段选择策略。

    Returns:
        挑好的落点。
    """
    start = _start_in(candidate, session, needed=needed, slot_size=slot_size, pick=pick)
    if start is not None:
        return Placement(name=name, park=candidate, first_slot_id=start, slot_num=needed)
    candidate.close()
    return _new_park(session, needed=needed, slot_size=slot_size)


def _start_in(
    candidate: ParkFile,
    session: HubSession,
    *,
    needed: int,
    slot_size: int,
    pick: Pick,
) -> int | None:
    """在一条载体里挑一段连续空槽；挑不中给 `None`。

    Args:
        candidate: 已经打开的载体。
        session: 开着的 hub 会话。
        needed: 要几个槽。
        slot_size: 槽长（位）。
        pick: 段选择策略。

    Returns:
        可用的链首槽 id；这条载体里装不下就是 `None`。
    """
    if candidate.header.slot_size != slot_size:
        return None
    taken = _taken(candidate, session, candidate.path.stem)
    chosen = choose_free(
        free_segments(slot_live=candidate.header.slot_live, taken=taken), needed, pick=pick
    )
    if chosen is not None:
        return chosen.start
    if candidate.header.slot_live + needed <= candidate.header.slot_num:
        start = candidate.header.slot_live
        candidate.grow_to(start + needed)
        return start
    return None


def _taken(candidate: ParkFile, session: HubSession, name: str) -> list[tuple[int, int]]:
    """这条载体上「谁占了哪」：优先信索引库，对不上就退回盲扫。

    Args:
        candidate: 已经打开的载体。
        session: 开着的 hub 会话。
        name: 载体名。

    Returns:
        `(first_slot_id, slot_num)` 列表。
    """
    rows = session.store.live_slots(name)
    if sum(slot_num for _, slot_num in rows) != candidate.header.slot_used:
        found = scan.scan_park(candidate, clear=False)
        return [(block.first_slot_id, block.slot_num) for block in found.blocks]
    return rows


def _new_park(session: HubSession, *, needed: int, slot_size: int) -> Placement:
    """新建一个载体：预算至少装得下这个块，水线正好推到它用得上。

    Args:
        session: 开着的 hub 会话。
        needed: 要几个槽。
        slot_size: 槽长（位）。

    Returns:
        新载体上的落点。

    Raises:
        FileExistsError: 撞上同名载体（哈希撞车）——极不可能，但不当没看见。
    """
    unique = uuid.uuid4().hex
    path = layout.park_path(session.path, unique)
    path.parent.mkdir(parents=True, exist_ok=True)
    park = ParkFile.create(path, slot_size=slot_size, slot_num=max(spec.SLOT_NUM_DEFAULT, needed))
    park.grow_to(needed)
    return Placement(name=path.stem, park=park, first_slot_id=0, slot_num=needed)


def _occupy(placement: Placement, slots: Sequence[bytes]) -> None:
    """④ 落槽：一个槽一次写满，写完把计数从 `empty` 挪到 `used`。

    Args:
        placement: 挑好的落点（载体句柄开着）。
        slots: 整条链的槽字节。

    Raises:
        ValueError: 槽字节长度不对，或槽不在水线以内。
    """
    park = placement.park
    for offset, blob in enumerate(slots):
        park.write_slot(placement.first_slot_id + offset, blob)
    header = park.header
    park.set_header(
        replace(
            header,
            slot_used=header.slot_used + len(slots),
            slot_empty=header.slot_empty - len(slots),
        )
    )


def _verify(placement: Placement, slots: Sequence[bytes], digest: bytes) -> None:
    """⑤ 复检：把刚写的槽重新读回来，逐槽 `check` ＋ 整块 `global_hash` 都要过。

    Args:
        placement: 挑好的落点（载体句柄开着）。
        slots: 写下去的槽字节。
        digest: 写下去的整块全局哈希。

    Raises:
        CorruptError: 读回来对不上——刚写下去的东西自己都验不过。
    """
    park = placement.park
    on_disk = [park.read_slot(placement.first_slot_id + offset) for offset in range(len(slots))]
    if global_hash(on_disk) != digest:
        raise CorruptError(f"刚写完的块全局哈希对不上：{placement.name}")
    try:
        parse_block(on_disk, slot_size=park.header.slot_size, first_slot_id=placement.first_slot_id)
    except ValueError as exc:
        raise CorruptError(f"刚写完的块验不过：{placement.name}") from exc

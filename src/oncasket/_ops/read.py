# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""读路径：库 → 地址 → 载体 → 块 → 内容（公开 API §3 的第三段；索引库 §009、§013）。

读三个判据，缺一不可：

- **可读性**：`state = ok`（`pending` = 这次提交没走完，`error` = 带着损坏点）；
- **地址**：库里得知道「在哪个 park、哪个槽」；`state = ok` 而地址空**不是错误**——
  盲扫能补（§013），补完当场回流；
- **完整性**：逐槽 `check` ＋ 整块 `global_hash` 都要对得上，验不过**不给半个块**。

地址空而盘上也扫不出来 = 判坏；槽已经不是「开始」（被删 / 被覆盖）同样是判坏。
先修再判坏里的「修」归修复策略库（路线 032，落在 1.0.0b1），本层修不动就出声。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from oncasket._errors import CorruptError, NotFoundError, OnCasketError
from oncasket._format import scan, slot
from oncasket._format.block import Block, global_hash, parse_block
from oncasket._format.park import ParkFile
from oncasket._hub import layout
from oncasket._index import commit
from oncasket._index.store import STATE_ERROR, STATE_PENDING, BlockRow


if TYPE_CHECKING:
    from oncasket._ops.session import HubSession


@dataclass(frozen=True, slots=True)
class Address:
    """一条块的物理落点：载体 ＋ 链首槽（地址是 ② 的产物，不是入参）。"""

    park: str
    first_slot_id: int


@dataclass(frozen=True, slots=True)
class Chain:
    """从载体上读回来的整条链。"""

    slots: tuple[bytes, ...]
    slot_size: int


def read_block(session: HubSession, block_id: bytes) -> Block:
    """读一条块：取地址、读满整条链、验完整性，再解回来。

    Args:
        session: 开着的 hub 会话。
        block_id: 逻辑块 ID。

    Returns:
        解出来的块（属性字典 ＋ 块体 ＋ 槽计数）。

    Raises:
        NotFoundError: 基准点找不到（id 不对，或那块已经被删）。
        OnCasketError: `state = pending`——这次提交没走完。
        CorruptError: `state = error`、地址扫不出来、槽不认，或全局哈希对不上。
    """
    row = row_of(session, block_id)
    address = locate(session, block_id)
    chain = read_chain(session, address)
    digest = global_hash(chain.slots)
    if digest != row.global_hash:
        raise CorruptError(f"全局哈希对不上：{block_id.hex()} 在 {address.park}")
    try:
        return parse_block(
            chain.slots, slot_size=chain.slot_size, first_slot_id=address.first_slot_id
        )
    except ValueError as exc:
        raise CorruptError(f"整条链解不回来：{block_id.hex()} 在 {address.park}") from exc


def locate(session: HubSession, block_id: bytes) -> Address:
    """库 → 地址；地址空就盲扫补一次，补到当场回流。

    Args:
        session: 开着的 hub 会话。
        block_id: 逻辑块 ID。

    Returns:
        物理落点。

    Raises:
        NotFoundError: 基准点找不到。
        OnCasketError: `state = pending`。
        CorruptError: `state = error`，或地址空而盘上也找不到。
    """
    row = row_of(session, block_id)
    if row.park is not None and row.first_slot_id is not None:
        return Address(park=row.park, first_slot_id=row.first_slot_id)
    found = _scan_for(session, block_id)
    if found is None:
        raise CorruptError(f"state = ok 但载体上找不到这条块：{block_id.hex()}")
    commit.reflux_address(
        session.store, block_id, park=found.park, first_slot_id=found.first_slot_id
    )
    return found


def read_chain(session: HubSession, address: Address) -> Chain:
    """读整条链：先读链首，再按它自报的槽数读到链尾。

    Args:
        session: 开着的 hub 会话。
        address: 物理落点。

    Returns:
        整条链的槽字节与槽长。

    Raises:
        CorruptError: 链首槽不认（被删 / 被覆盖），或槽读不满（文件缺了一截）。
    """
    path = session.park_path(address.park)
    if not path.is_file():
        raise CorruptError(f"载体不在：{address.park}")
    try:
        with ParkFile.load(path) as park:
            slot_size = park.header.slot_size
            head = park.read_slot(address.first_slot_id)
            span = scan.chain_span(head, slot_size=slot_size)
            if span is None:
                raise CorruptError(
                    f"链首槽不认：{address.park} 第 {address.first_slot_id} 槽"
                    f"（check 不过，或已经不是「开始」——被删或覆盖）"
                )
            return Chain(
                slots=tuple(
                    park.read_slot(address.first_slot_id + offset) for offset in range(span)
                ),
                slot_size=slot_size,
            )
    except ValueError as exc:
        raise CorruptError(f"载体读不满：{address.park} 第 {address.first_slot_id} 槽") from exc


def row_of(session: HubSession, block_id: bytes) -> BlockRow:
    """取一行，并把「可读性」判完。

    Args:
        session: 开着的 hub 会话。
        block_id: 逻辑块 ID。

    Returns:
        索引行（`state = ok`）。

    Raises:
        NotFoundError: 行不在了。
        OnCasketError: `state = pending`。
        CorruptError: `state = error`。
    """
    row = session.store.get(block_id)
    if row is None:
        raise NotFoundError(f"基准点找不到：{block_id.hex()}")
    if row.state == STATE_PENDING:
        raise OnCasketError(f"这次提交没走完（state = pending）：{block_id.hex()}")
    if row.state == STATE_ERROR:
        raise CorruptError(f"这一行带着损坏点（state = error）：{block_id.hex()}")
    return row


def _scan_for(session: HubSession, block_id: bytes) -> Address | None:
    """盲扫全部载体找一个 `block_id`。

    只认完整的链：槽是 `header_start` 且 `check` 通过（`scan_park` 的判据），再比链首的
    `block_id`。扫不动的载体（头不合法、文件缺一截）跳过——怎么处置归修复策略库（032）。

    Args:
        session: 开着的 hub 会话。
        block_id: 逻辑块 ID。

    Returns:
        找到的落点；盘上没有就是 `None`。
    """
    for path in layout.find_parks(session.path):
        try:
            with ParkFile.load(path) as park:
                result = scan.scan_park(park, clear=False)
                slot_size = park.header.slot_size
                for found in result.blocks:
                    head = slot.decode_header_start(
                        park.read_slot(found.first_slot_id), slot_size=slot_size
                    )
                    if head.block_id == block_id:
                        return Address(park=path.stem, first_slot_id=found.first_slot_id)
        except ValueError:
            continue
    return None

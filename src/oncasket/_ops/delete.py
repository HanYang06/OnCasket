# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""删除镜像：先动物理（头槽清零 → 其余槽清零），物理动完再动库（格式 §8）。

删就**真删**：不留墓碑、不做软删。要软删是调用方自己的事（在属性里放个标记自己筛）。

顺序是写入的反面，理由也一样——**先让槽不再是块，再让库里没有它**：

- 崩在第一步之后：槽是孤儿，扫描时逐个清掉；
- 崩在第一步之前：块还完整，幂等重做；
- 头槽已经不是「开始」（上一次已经删过 / 被覆盖）：跳过物理，直接删库，**幂等**。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from oncasket._errors import NotFoundError
from oncasket._format import scan
from oncasket._format.park import ParkFile
from oncasket._index import commit
from oncasket._ops.read import Address
from oncasket._ops.write import free_slots


if TYPE_CHECKING:
    from oncasket._ops.session import HubSession


def delete_block(session: HubSession, block_id: bytes) -> None:
    """删一条块：清槽、释放段、删库行（身份分表跟着级联清）。

    Args:
        session: 开着的 hub 会话。
        block_id: 逻辑块 ID。

    Raises:
        NotFoundError: 基准点找不到（id 不对，或那块已经被删）。
        LockTimeoutError: 等写锁超时。
    """
    with session.write_lock():
        row = session.store.get(block_id)
        if row is None:
            raise NotFoundError(f"基准点找不到：{block_id.hex()}")
        if row.park is not None and row.first_slot_id is not None:
            _clear(session, Address(park=row.park, first_slot_id=row.first_slot_id))
        commit.drop(session.store, block_id)


def _clear(session: HubSession, address: Address) -> None:
    """把一条链的槽清成 `empty` 并释放段；载体不在或已经不是「开始」就什么都不做。

    Args:
        session: 开着的 hub 会话。
        address: 物理落点。
    """
    path = session.park_path(address.park)
    if not path.is_file():
        return
    with ParkFile.load(path) as park:
        head = park.read_slot(address.first_slot_id)
        span = scan.chain_span(head, slot_size=park.header.slot_size)
        if span is None:
            return
        free_slots(park, address.first_slot_id, span)

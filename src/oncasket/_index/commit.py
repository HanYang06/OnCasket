# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""提交路径的库侧动作：索引行、`state` 翻转与地址回流（索引库 §009）。

提交 ①–⑦ 横跨「库 / 载体 / 分配」三域，整条流程归 `_ops`（跨域编排）；这里只装**库里那三下**：
② 写 `pending` 行、⑥ 翻 `ok`、⑦ 地址回流，另有删除侧的删行。域之间不互相调用，
`_ops` 按因果顺序点它们。

两个完成标记分开写：`state`（写成功）与地址（回流成功）不是一件事——
`state = ok` 而地址空是**不是错误**，扫描可以补（§013）。
"""

from __future__ import annotations

import time

from oncasket._index.store import STATE_PENDING, BlockRow, IndexStore, Role


def now_seconds() -> int:
    """当前时刻：Unix 秒、UTC（事实依据里 `created_at` 的口径）。

    Returns:
        整秒时间戳。
    """
    return int(time.time())


def write_pending(
    store: IndexStore,
    *,
    block_id: bytes,
    budget_slot: int,
    block_size: int,
    global_hash: bytes,
    kind: str,
    role: Role = Role.DATA,
    created_at: int | None = None,
) -> BlockRow:
    """② 写索引行：身份、预算、`global_hash`，`state = pending`，**地址留空**。

    地址留空不是漏写：地址是 ④ 之后才有的事实，只能最后回流。

    Args:
        store: 索引库连接。
        block_id: 逻辑块 ID。
        budget_slot: 预算槽数（`plan_block.slot_num`）。
        block_size: 预算块尺寸（字节）。
        global_hash: 整块全局哈希。
        kind: 身份分表里的 `kind`（开放取值）。
        role: 逻辑块身份。
        created_at: 创建时刻；不给就取当下。

    Returns:
        刚落下的那一行（`state = pending`、地址为空）。
    """
    row = BlockRow(
        block_id=block_id,
        created_at=now_seconds() if created_at is None else created_at,
        budget_slot=budget_slot,
        block_size=block_size,
        global_hash=global_hash,
        state=STATE_PENDING,
        park=None,
        first_slot_id=None,
    )
    store.insert(row, role=role, kind=kind)
    return row


def mark_ok(store: IndexStore, block_id: bytes) -> None:
    """⑥ 提交点：`state → ok`。

    Args:
        store: 索引库连接。
        block_id: 逻辑块 ID。
    """
    store.mark_ok(block_id)


def reflux_address(store: IndexStore, block_id: bytes, *, park: str, first_slot_id: int) -> None:
    """⑦ 地址回流：把「在哪个 park、哪个槽」写回库。

    Args:
        store: 索引库连接。
        block_id: 逻辑块 ID。
        park: park 名。
        first_slot_id: 链首槽 id。
    """
    store.set_address(block_id, park=park, first_slot_id=first_slot_id)


def drop(store: IndexStore, block_id: bytes) -> bool:
    """删除侧的库动作：删行，两张身份分表级联跟着走。

    物理动作**已经做完**才轮到这里（格式 §8 / 索引库 §009 的镜像序）。

    Args:
        store: 索引库连接。
        block_id: 逻辑块 ID。

    Returns:
        真删掉了一行为真。
    """
    return store.delete(block_id)

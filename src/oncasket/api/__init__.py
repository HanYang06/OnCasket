# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""公开 API 面：下游唯一该 import 的那个模块（`oncasket.api`）。

它是 [`oncasket`](../__init__.py) 这个唯一公开面的**整体**拆分（packages.md §2 的逃逸口），
不是「再散出几个公开模块」：公开名字在这里定义或从 `_ops` / `_errors` 重导出、逐个列进
`__all__`；公开签名里不出现私有类型。

四个面各自的状态：

| 面 | 装什么 | 状态 |
|---|---|---|
| 声明面（§6） | `Block` / `Ref` / `Attr` / `Body`（＋句柄 `AttrEntry` / `AttrLock`） | 已冻 |
| 落地面（§8） | `Hub`：增删改查四个动作 | 已冻 |
| 异常面（§11） | 七个异常类 | 已冻 |
| 查询面（§10） | `AttrIndex` / `BodyIndex` | 跟着路线 033 / 034——索引块与条目还没落地 |

拆解版（`Park` / `Packer` / `Slot`）在 `oncasket.api.park` / `oncasket.api.slot`，
**默认不开放、引擎不担保**，跟着下一块落地。

名字一旦进 `__all__` 就只增不减，所以每冻一块都得有实现兜着：
`Hub` 的四个动作底下是 `_ops` 的 session / write（含改）/ read / delete。
"""

from __future__ import annotations

from oncasket._errors import (
    ConflictError,
    CorruptError,
    LockTimeoutError,
    NotFoundError,
    OnCasketError,
    SchemaMismatchError,
    SqliteTooOldError,
)
from oncasket.api.block import Attr, AttrEntry, AttrLock, Block, Body, Ref
from oncasket.api.hub import Hub


#: 公开名字的清单（路线 022 冻结）：只增不减。
__all__ = [
    "Attr",
    "AttrEntry",
    "AttrLock",
    "Block",
    "Body",
    "ConflictError",
    "CorruptError",
    "Hub",
    "LockTimeoutError",
    "NotFoundError",
    "OnCasketError",
    "Ref",
    "SchemaMismatchError",
    "SqliteTooOldError",
]

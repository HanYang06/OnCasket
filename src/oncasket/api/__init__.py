# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""公开 API 面：下游唯一该 import 的那个模块（`oncasket.api`）。

它是 [`oncasket`](../__init__.py) 这个唯一公开面的**整体**拆分（packages.md §2 的逃逸口），
不是「再散出几个公开模块」：公开名字在这里定义或从 `_ops` / `_errors` 重导出、逐个列进
`__all__`；公开签名里不出现私有类型。

名字一块一块冻（路线 022），**冻一块就得有实现兜着**：

| 面 | 状态 |
|---|---|
| 异常面（§11） | **已冻**——七个类在 `_errors` 里是唯一定义处，且不依赖任何数据模型 |
| 落地面（§8：`Hub` 的增删改查） | 实现已通（`_ops/`），名字待声明面一起冻 |
| 声明面（§6：`Block` / `Ref` / `Attr` / `Body`） | 待裁：草图与 §5 有三处打架，见设计篇 |
| 查询面（§10：`AttrIndex` / `BodyIndex`） | 跟着路线 033 / 034 走——索引块与条目还没落地 |

**先冻异常面**的理由只有一条：它是终稿，且不欠任何实现。名字一旦进 `__all__` 就只增不减，
所以宁可一块一块来，也不先冻一个跑不起来的名字。
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


#: 公开名字的清单（路线 022 冻结）：只增不减。
__all__ = [
    "ConflictError",
    "CorruptError",
    "LockTimeoutError",
    "NotFoundError",
    "OnCasketError",
    "SchemaMismatchError",
    "SqliteTooOldError",
]

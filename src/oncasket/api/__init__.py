# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""公开 API 面：下游唯一该 import 的那个模块（`oncasket.api`）。

它是 [`oncasket`](../__init__.py) 这个唯一公开面的**整体**拆分（packages.md §2 的逃逸口），
不是「再散出几个公开模块」：公开名字在这里定义或从 `_ops` / `_errors` 重导出、逐个列进
`__all__`；公开签名里不出现私有类型。

具体名字归路线 022——在它冻结之前，`__all__` 为空。
"""

from __future__ import annotations


__all__: list[str] = []

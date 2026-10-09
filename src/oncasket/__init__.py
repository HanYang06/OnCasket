# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""OnCasket：单机存储引擎内核。

本模块是**唯一公开面**——顶层其余条目一律 `_` 前缀，属内部实现、随时可改。
公开名字在这里定义或重导出并逐个列进 `__all__`；公开签名里不出现私有类型。
口径见 docs/design/packages.md；公开 API 的冻结归路线 022（当前 `__all__` 为空）。
"""

from __future__ import annotations

from importlib.metadata import version


__version__ = version("oncasket")

# 公开名字的清单：路线 022 冻结后只增不减；空表示公开 API 尚未落地。
__all__: list[str] = []

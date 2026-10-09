# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""异常层次。

全部异常类的唯一写处：域模块只抛不定义，公开面从 `oncasket` 重导出。
层次与公开名字归路线 022；在它冻结之前，这里只放已落地域真正用得上的那几个，
**不做预建**——没被抛过的类就是没人用的类。
"""

from __future__ import annotations


class OnCasketError(Exception):
    """引擎所有异常的基类：调用方只认这一层也能兜住。"""


class SqliteTooOldError(OnCasketError):
    """运行时 SQLite 低于结构所需的下限（索引库 §008）。"""


class SchemaMismatchError(OnCasketError):
    """索引库 schema 指纹不在本引擎声明的集合里（索引库 §012）。"""

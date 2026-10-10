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


class NotFoundError(OnCasketError):
    """基准点找不到：`block_id` 不对，或那块已经被删（公开 API §11）。"""


class ConflictError(OnCasketError):
    """基准点还在，但手上那份不是现役——乐观并发撞上了（公开 API §11）。"""


class LockTimeoutError(OnCasketError):
    """写锁等过一轮还拿不到（公开 API §11）：正常情形，过会儿再来。"""


class CorruptError(OnCasketError):
    """先修过、修不动才抛——抛它就是把块判坏了（公开 API §11、修复 §032）。"""

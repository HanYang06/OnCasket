# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""库层：`Hub`——宏观的**增删改查**（公开 API §8、§12）。

| 动作 | 一句话 |
|---|---|
| `hub.write(block)` | 增：提交 ①–⑦ 一口气走完，返回 `block_id` |
| `hub.read(block_id)` | 查：带强校验（逐槽 `check` ＋ 整块 `global_hash`），验不过就抛 |
| `hub.update(block_id, attr=…)` | 改：**基准点 ＋ 新值**，写前验一次，撞上抛 `ConflictError` |
| `hub.delete(block_id)` | 删：先动物理（清槽）再动库（删行），真删、不留墓碑 |

- **打开是幂等的**：`Hub(path)` 已存在就打开、不存在就建（目录树 ＋ 索引库 ＋ 清单 ＋ 锁），
  `path` 是 hub 目录，容器就是它的上一级。
- **产物只有 id 与地址**：写与查询的结果都是 `block_id`；地址（载体 ＋ 首槽 id）是引擎的账。
- 拆解版（`locate` / `park` / `Slot` / `Packer`）与查询面（`AttrIndex` / `BodyIndex`）不在这一层：
  前者归 `oncasket.api.park` / `oncasket.api.slot`，后者跟着路线 033 / 034。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from oncasket._ops import delete as delete_ops
from oncasket._ops import read as read_ops
from oncasket._ops import write as write_ops
from oncasket._ops.session import HubSession
from oncasket.api.block import REF_KEY, Block


if TYPE_CHECKING:
    from collections.abc import Mapping


__all__ = ["Hub"]


class Hub:
    """一个 hub 的句柄：索引库、载体、锁、清单都在它手里。"""

    def __init__(self, path: str | Path) -> None:
        """打开（必要时建）一个 hub。

        Args:
            path: hub 目录。

        Raises:
            SchemaMismatchError: 索引库指纹不在本引擎声明的集合里——拒开，不降级、不重建。
            SqliteTooOldError: 运行时 SQLite 低于结构所需下限。
        """
        self._path = Path(path)
        self._session = HubSession.open(self._path)

    @property
    def path(self) -> Path:
        """Hub 目录（已解析成绝对路径）。"""
        return self._session.path

    def write(self, block: Block) -> bytes:
        """增：把声明好的块落盘，返回它的 `block_id`（地址是引擎的账）。

        Args:
            block: 声明段的块；`block.attr` / `block.body` 上绑着的那份就是要写的内容，
                `block.ref` 定角色（没定当数据块）、`block.kind` 记身份分表的 `kind`。

        Returns:
            这条块的 `block_id`。

        Raises:
            ValueError: 内容放不下（单条属性超上限、`block_id` 宽度不对）。
            CorruptError: ⑤ 复检不过——刚写下去的东西自己都验不过。
            LockTimeoutError: 等写锁超时。
        """
        return write_ops.write_block(
            self._session,
            attrs=block.attributes(),
            body=block.body.item(),
            kind=block.kind,
            role=write_ops.role_of(block.ref.get()),
        )

    def read(self, block_id: bytes) -> Block:
        """查：读回一条块，**读的过程必然带强哈希验证**，验不过就抛、不给半个块。

        Args:
            block_id: 逻辑块 ID。

        Returns:
            声明段的块：属性区与块体上绑着读回来的那份，`ref` 归位到 `block.ref`；
            它的 `owner` 是 `None`（读回来的块没有持有者，要挂回自己的结构就自己 `set`）。

        Raises:
            NotFoundError: 基准点找不到（id 不对，或那块已经被删）。
            OnCasketError: `state = pending`——这次提交没走完。
            CorruptError: 槽不认、全局哈希对不上，或地址扫不出来。
        """
        stored = read_ops.read_block(self._session, block_id)
        block = Block(block_id=stored.block_id)
        for name, value in stored.attrs.items():
            if name == REF_KEY:
                block.ref.set(value.decode("utf-8"))
            else:
                block.attr.add(name, value)
        block.body.write(stored.body)
        return block

    def update(
        self,
        block_id: bytes,
        *,
        attr: Mapping[str, bytes | str] | None = None,
        body: bytes | str | None = None,
    ) -> bytes:
        """改：**基准点 ＋ 新值**——先读回现役（带校验），应用新值后再验一次。

        中途被别处改过就抛 `ConflictError`，不静默覆盖。属性只覆盖点名的键，其余沿用现役那份。

        Args:
            block_id: 基准点：逻辑块 ID（或索引查出来的那个 id）。
            attr: 要改的属性：键 → 新值。
            body: 新的块体；不给就沿用现役那份。

        Returns:
            还是那个 `block_id`（改不改都不换身份）。

        Raises:
            NotFoundError: 基准点找不到。
            OnCasketError: `state = pending`。
            ConflictError: 基准点还在，但已经不是现役。
            CorruptError: 现役那一份读回来验不过。
            LockTimeoutError: 等写锁超时。
        """
        attrs = None if attr is None else {name: _as_bytes(value) for name, value in attr.items()}
        return write_ops.update_block(
            self._session,
            block_id,
            attrs=attrs,
            body=None if body is None else _as_bytes(body),
        )

    def delete(self, block_id: bytes) -> None:
        """删：先动物理（头槽清零 → 其余槽清零），物理动完再动库；真删、不留墓碑。

        Args:
            block_id: 逻辑块 ID。

        Raises:
            NotFoundError: 基准点找不到（id 不对，或那块已经被删）。
            LockTimeoutError: 等写锁超时。
        """
        delete_ops.delete_block(self._session, block_id)

    def close(self) -> None:
        """关掉库连接与清单；幂等。"""
        self._session.close()

    def __enter__(self) -> Hub:
        """进上下文。

        Returns:
            自己。
        """
        return self

    def __exit__(self, *args: object) -> None:
        """出上下文就关。

        Args:
            *args: 异常三元组，这里不关心。
        """
        self.close()


def _as_bytes(value: bytes | str) -> bytes:
    """`bytes | str` → `bytes`：字符串按 utf-8 落。

    Args:
        value: 字节或字符串。

    Returns:
        字节。
    """
    return value.encode("utf-8") if isinstance(value, str) else value

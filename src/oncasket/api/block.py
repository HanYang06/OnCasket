# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""声明面：`Block` / `Ref` / `Attr` / `Body`——**纯内存**，一个动作都不碰盘（公开 API §6）。

## 约定：句柄要自己留着

`block.attr.set(...)` / `block.body.set(...)` 是**绑定**，不是「装内容」——它们绑的是**一个纯句柄**：
块只记住「这个区归哪个句柄管」，读写通道仍在句柄上。所以基于 block 建自己的数据结构时，
要把 `block` 与这两个句柄一起留成自己的属性；不留下，后面就没有落点可改：

```python
class Notebook:
    def __init__(self) -> None:
        self.block = Block(self)  # 把持有者自己传进去，block 也自己持有
        self.attr = self.block.attr.set(Attr(self, self.block.id))  # 绑定 ＋ 留句柄
        self.body = self.block.body.set(Body(self, self.block.id))

    def rename(self, title: bytes) -> None:
        self.attr.add("title", title)  # 落点就是留着的那个句柄
```

不建自己的结构时也能直接用：`Block()` 里已经给这个块建好了它自己那份句柄，
所以 `block.attr.add(...)` / `block.body.write(...)` 照常能用；`set(...)` 绑进来的会顶替它。

## 三件不在这里的事

- **`Body.type`（类型声明）**：类型装在索引条目里（§7），跟着路线 034；
- **`attr.index` / `body.index`（索引开关）**：索引块与条目跟着路线 033；
- **落盘**：怎么把内容交给引擎，见 §8 的 `Hub.write`。
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, ClassVar


if TYPE_CHECKING:
    from collections.abc import Mapping


__all__ = ["Attr", "AttrEntry", "AttrLock", "Block", "Body", "Ref"]

#: 角色在属性字典里的键名（§6：`ref` 就是一条**约定好名字**的属性）
REF_KEY = "ref"


class Ref:
    """角色插槽：数据型还是索引型；取值是**字符串**，不枚举、不校验。"""

    #: 预制取值：数据块
    data: ClassVar[str] = "data"
    #: 预制取值：索引块
    index: ClassVar[str] = "index"

    def __init__(self, role: str | Ref = "") -> None:
        """造一个角色插槽。

        Args:
            role: 初始角色；`Ref.data` 与 `Ref.index` 是预制取值。
        """
        self._role = role.get() if isinstance(role, Ref) else role

    def set(self, role: str | Ref) -> None:
        """定角色。

        Args:
            role: 角色字符串，或另一个 `Ref`。
        """
        self._role = role.get() if isinstance(role, Ref) else role

    def get(self) -> str:
        """当前角色。

        Returns:
            角色字符串；没定过就是空串。
        """
        return self._role


class AttrEntry:
    """一条属性的句柄：身份是「哪个块的第几个键」，值就写在它身上。"""

    def __init__(self, owner: object, block_id: bytes, name: str, value: bytes = b"") -> None:
        """不直接调；走 `Attr.add` / `Attr.get`。

        Args:
            owner: 持有者（建这个数据结构的那份 self）。
            block_id: 逻辑块 ID。
            name: 键名。
            value: 初值。
        """
        self.owner = owner
        self.block_id = block_id
        self.name = name
        self._value = value
        self._locked = False

    def set(self, value: bytes | str) -> AttrEntry:
        """改值（**锁之前**）。

        Args:
            value: 新值；`str` 按 utf-8 落。

        Returns:
            自己，便于链式。

        Raises:
            ValueError: 这条或整个属性区已经冻上了。
        """
        if self._locked:
            raise ValueError(f"属性 {self.name!r} 已经锁定，改不了")
        self._value = _as_bytes(value)
        return self

    def item(self) -> bytes:
        """读值。

        Returns:
            这条属性的字节值。
        """
        return self._value

    def lock(self) -> AttrEntry:
        """冻结这一条。

        Returns:
            自己，便于链式。
        """
        self._locked = True
        return self

    @property
    def locked(self) -> bool:
        """这条锁上了没有。"""
        return self._locked


class AttrLock:
    """属性区的冻结开关：**可变性开关**，不是并发锁（声明段是纯内存，没有并发写者）。"""

    def __init__(self, area: Attr) -> None:
        """不直接调；走 `Attr.lock`。

        Args:
            area: 这个属性区。
        """
        self._area = area

    def all(self) -> None:
        """冻结整个属性区：之后 `add` 与 `set` 都不许再改。"""
        self._area._locked = True
        for entry in self._area._entries.values():
            entry.lock()

    def item(self, name: str) -> None:
        """冻结一条。

        Args:
            name: 键名。

        Raises:
            KeyError: 没有这个键。
        """
        self._area.get(name).lock()


class Attr:
    """属性区句柄：身份是「挂在谁身上」＋「哪个块」。

    块自己那份句柄由 `Block(...)` 建好（`block.attr`）；`set(handle)` 绑进来的会顶替它
    ——绑定只换「归谁管」，不搬数据。
    """

    def __init__(self, owner: object, block_id: bytes) -> None:
        """造一个属性区句柄。

        Args:
            owner: 持有者（建这个数据结构的那份 self）。
            block_id: 逻辑块 ID。
        """
        self.owner = owner
        self.block_id = block_id
        self._entries: dict[str, AttrEntry] = {}
        self._bound: Attr | None = None
        self._locked = False

    def set(self, handle: Attr) -> Attr:
        """**绑定**：把这个块的这个区交给 `handle` 管，并把它交回去（留着用）。

        绑的是句柄本身，不搬数据——所以绑定之后 `block.attr.add(...)` 与
        `handle.add(...)` 动的是同一份东西。

        Args:
            handle: 要绑进来的属性区句柄。

        Returns:
            同一个 `handle`（便于 `self.attr = block.attr.set(Attr(self, block.id))`）。
        """
        self._bound = handle
        return handle

    def add(self, name: str, value: bytes | str = b"") -> AttrEntry:
        """加一条属性，并拿它的句柄。

        Args:
            name: 键名，非空；同名再 `add` 是**覆盖**（字典就一条）。
            value: 初值。

        Returns:
            这条属性的句柄。

        Raises:
            ValueError: 键名为空，或整个属性区已经冻上了。
        """
        target = self._target
        target._reject_locked()
        raw = name.encode("utf-8")
        if not raw:
            raise ValueError("属性名不能为空")
        entry = AttrEntry(target.owner, target.block_id, name, _as_bytes(value))
        target._entries[name] = entry
        return entry

    def get(self, name: str) -> AttrEntry:
        """按名取句柄。

        Args:
            name: 键名。

        Returns:
            这条属性的句柄。

        Raises:
            KeyError: 没有这个键。
        """
        return self._target._entries[name]

    def items(self) -> dict[str, bytes]:
        """整区读回：键 → 值。

        Returns:
            属性字典；落盘按名的 utf-8 字节序升序由格式层负责（§6）。
        """
        return {name: entry.item() for name, entry in self._target._entries.items()}

    @property
    def lock(self) -> AttrLock:
        """冻结开关：`lock.all()` / `lock.item(名)`。"""
        return AttrLock(self._target)

    @property
    def locked(self) -> bool:
        """整个区冻上了没有。"""
        return self._target._locked

    @property
    def _target(self) -> Attr:
        """实际管这份数据的句柄：绑过就是它，没绑就是自己。"""
        return self if self._bound is None else self._bound._target

    def _reject_locked(self) -> None:
        """冻结之后不许再加。

        Raises:
            ValueError: 整个区已经冻上。
        """
        if self._locked:
            raise ValueError("属性区已经锁定，加不进东西")


class Body:
    """块体句柄：身份是「挂在谁身上」＋「哪个块」；内容就是一段字节。"""

    def __init__(self, owner: object, block_id: bytes) -> None:
        """造一个块体句柄。

        Args:
            owner: 持有者（建这个数据结构的那份 self）。
            block_id: 逻辑块 ID。
        """
        self.owner = owner
        self.block_id = block_id
        self._data = b""
        self._bound: Body | None = None
        self._locked = False

    def set(self, handle: Body) -> Body:
        """**绑定**：把这个块的这个区交给 `handle` 管，并把它交回去（留着用）。

        Args:
            handle: 要绑进来的块体句柄。

        Returns:
            同一个 `handle`。
        """
        self._bound = handle
        return handle

    def write(self, data: bytes | str) -> None:
        """写块体（**锁之前**）。

        Args:
            data: 块体字节；`str` 按 utf-8 落。

        Raises:
            ValueError: 块体已经冻上了。
        """
        target = self._target
        if target._locked:
            raise ValueError("块体已经锁定，写不了")
        target._data = _as_bytes(data)

    def item(self) -> bytes:
        """读块体。

        Returns:
            块体字节。
        """
        return self._target._data

    def lock(self) -> Body:
        """冻结块体。

        Returns:
            自己，便于链式。
        """
        self._target._locked = True
        return self

    @property
    def locked(self) -> bool:
        """冻上了没有。"""
        return self._target._locked

    @property
    def _target(self) -> Body:
        """实际管这份数据的句柄：绑过就是它，没绑就是自己。"""
        return self if self._bound is None else self._bound._target


class Block:
    """声明段的一个块：纯内存，出来就带 `id`（uuid4，128 位，**引擎给**）。"""

    def __init__(self, owner: object = None, block_id: bytes | None = None) -> None:
        """造一个块，并把它自己那份属性区 / 块体句柄一并建好。

        Args:
            owner: 持有它的数据结构（建这个结构的那份 self）；不建自己的结构时可以不给
                （读回来的块就没有持有者）。`block.attr` / `block.body` 的身份取自它。
            block_id: 逻辑块 ID；不给就新生成一个 uuid4（128 位）。**读回来的块**把它交回去
                ——身份证在头槽自述区里，不在库里另记一份，所以读回来还是同一个 id。
        """
        self.id: bytes = uuid.uuid4().bytes if block_id is None else block_id
        self.owner = owner
        #: 身份分表里的 `kind`（开放取值，不枚举、不校验）：装了什么 / 索引了什么
        self.kind: str = ""
        self.ref = Ref()
        self.attr = Attr(owner, self.id)
        self.body = Body(owner, self.id)

    def attributes(self) -> dict[str, bytes]:
        """落盘要写的那份属性字典：`ref` 按约定键并进属性（§6）。

        Returns:
            键 → 值；`block.ref` 没定过就不带 `ref` 这一条。
        """
        attrs: Mapping[str, bytes] = self.attr.items()
        merged = dict(attrs)
        role = self.ref.get()
        if role:
            merged[REF_KEY] = role.encode("utf-8")
        return merged


def _as_bytes(value: bytes | str) -> bytes:
    """`bytes | str` → `bytes`：字符串按 utf-8 落。

    Args:
        value: 字节或字符串。

    Returns:
        字节。
    """
    return value.encode("utf-8") if isinstance(value, str) else value

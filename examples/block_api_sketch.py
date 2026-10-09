# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""下游声明一个块的草图（**API 尚未落地**：路线 022 冻结、`oncasket.api` 里有名字之后才跑得起来）。

读法：`DemoData` **持有**一个 `Block`——组合，不是继承。下游要做的只是把自己那点东西声明进
`ref` / `attr` / `body`；选址、落盘、提交全归引擎。查询侧靠**索引块**（`AttrIndex` / `BodyIndex`），
它们的产物只有 `block_id`——拿到 id，地址与内容就都走正常那条路。

这里只是**形态草案**，不是已定口径：见[公开 API 设计](../docs/design/api.md)的待定 1–3。

本文件先用 ruff 管着（许可头、注解、docstring 一样不少），但它现在**跑不起来**也不是测试对象
——等 API 落地再把它接进可跑性验证。
"""

from __future__ import annotations

from oncasket.api import Attr, Block, Body, Ref
from oncasket.api.hub import Hub
from oncasket.api.index import AttrIndex, BodyIndex
from oncasket.api.park import Pack


class DemoData:
    """把「一个名字 ＋ 一段 body」声明成块的例子。"""

    def __init__(self) -> None:
        """把块的内容声明齐：角色、属性区、块体，然后上锁。"""
        self.name = "DemoData"  # 名字可选，缺省就是类名
        self.b = Block()
        self.id = self.b.id
        self.ref = Ref.data
        self.b.ref.set(self.ref)
        self.attr = self.init_attr()
        self.body = self.init_body()
        self.b.attr.set(self.attr)
        self.b.body.set(self.body)

        self.attr.index.open()
        self.attr.index.set("title")  # 点名 title；一个 set 都不调就是全量

        self.body.index.open()  # 写入时留存一份纯正文，按正文哈希建索引

        self.attr.lock.all()
        self.attr.lock.item("title")

        # 下面这段是**拆解版**：流程自己摊开调，引擎不担保；默认那条是 `Hub("hub").write(self.b)`
        self.h = Hub("hub")
        self.p = Pack(self.b)
        if self.p.check() is True:
            if self.p.allocate(self.h) is True:
                self.p.write(self.h)
            else:
                self.p.re_allocate(self.h)
                self.p.write(self.h)
            self.p.sync(self.h.index.db)

    def init_attr(self) -> Attr:
        """声明属性区：加一条 `title`，再改它的值。

        Returns:
            属性区。
        """
        attr = self.b.attr.set(Attr(self, self.name))
        self.title = attr.add("title", "DemoData")
        self.title.set("Hello,Word")
        return attr

    def init_body(self) -> Body:
        """声明块体：只报类型，编码交给引擎。

        Returns:
            块体声明。
        """
        body = self.b.body.set(Body(self, self.name))
        body.type.set(list)
        return body


def lookup(demo: DemoData) -> list[bytes]:
    """按属性取值反查块 id：索引对象绑住 hub 与属性名，拿取值去问。

    Args:
        demo: 已经声明好的块。

    Returns:
        `block_id` 表（`only_one` 时长度 ≤ 1，签名不变）。
    """
    title = demo.attr.get("title").item()
    return AttrIndex(demo.h, "title").search(title)


def lookup_by_body(demo: DemoData) -> list[bytes]:
    """按块体内容哈希反查块 id——内容一样就是同一份，天然去重。

    Args:
        demo: 已经声明好的块。

    Returns:
        `block_id` 表。
    """
    return BodyIndex(demo.h).search(demo.body.get().hash())

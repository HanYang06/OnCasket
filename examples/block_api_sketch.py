# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""下游声明一个块的草图（**API 尚未落地**：路线 022 冻结、`oncasket.api` 里有名字之后才跑得起来）。

读法：`DemoData` **持有**一个 `Block`——组合，不是继承。下游要做的只是把自己那点东西声明进
`ref` / `attr` / `body`；选址、落盘、提交全归引擎。这里的名字与链式调用是**待定形态的草案**，
不是已定口径：`Ref` / `Attr` / `Body` 各自管什么，见 docs/design/api.md（尚未立篇）。

本文件先用 ruff 管着（许可头、注解、docstring 一样不少），但它现在**跑不起来**也不是测试对象
——等 API 落地再把它接进可跑性验证。
"""

from __future__ import annotations

from oncasket.api import Attr, Block, Body, Ref


class DemoData:
    """把「一个名字 ＋ 一段 body」声明成块的例子。"""

    def __init__(self) -> None:
        """把块的内容声明齐：引用形态、属性区、块体。"""
        self.name = "DemoData"  # 名字可选，缺省就是类名
        self.b = Block()
        self.id = self.b.id
        self.ref = Ref.data
        self.b.ref.set(self.ref)
        self.attr = self.init_attr()
        self.body = self.init_body()
        self.b.attr.set(self.attr)
        self.b.body.set(self.body)

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

<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 公开 API：下游怎么造一个块

> 域：契约 / 公开 API 冻结。对应路线图 [1.x 路线增量](../roadmap/1.x.md)。
>
> **事实依据**：本域没有机读配置——公开名单就是
> [`oncasket/api/__init__.py`](../../src/oncasket/api/__init__.py) 的 `__all__`，结构契约由
> [`tests/test_public_surface.py`](../../tests/test_public_surface.py) 钉死；形态草案见
> [`examples/block_api_sketch.py`](../../examples/block_api_sketch.py)。
> 规范见[文档规范](../README.md)。

## <a id="r022"></a>022 公开 API 冻结

- 决策状态：已定（待定项见文末）

### 1. 面在哪

- 下游只有一条 import 路径：`oncasket.api`（见[包与目录 §031](packages.md#r031)）。
- **公开类型长在公开面上**：名字在 [`api/__init__.py`](../../src/oncasket/api/__init__.py)
  里定义或重导出、逐个进 `__all__`。私有类型不许出现在公开签名里——它的 `__module__`
  会跟着 repr 漏出去（`oncasket._ops.write.Handle` 就是这么漏的）。
- 由此有一条**推论**（不只是风格）：公开对象只装内容、不碰盘；读写一律经 `_ops`。
  方向永远是 `api` → `_ops`，与[依赖分层表](packages.md#r031)同向，不成环。

### 2. 三段

下游做一件事分成三段——这是设计给的分界，不是实现细节：

| 段 | 谁做 | 手上有什么 | 出处 |
|---|---|---|---|
| ① 声明 | 下游 | 纯内存：块 id、属性、块体；可重复算 | [索引库 §009](index_db.md#r009) ①、[格式 §3](format.md#r021) |
| ② 提交 | 引擎 | 索引行、park、槽地址 | §009 ②–⑦ |
| ③ 读回 | 引擎 | 地址 → 内容（逐槽 `check` 已验过） | [格式 §9](format.md#r021) |

- **地址是结果，不是入参**：`park` / `first_slot_id` 是 ② 的产物，声明段拿不到、也不该拿。
- 内部实现已经长在这个分界上：`plan_block`（内容）→ 物理写 → `parse_block`（读回）。
- 草案只画了 ①。②③ 的入口（谁写、写到哪个 hub、怎么读回来）还没出现，见待定 6。

### 3. 草案里的名字对盘

| 草案里的名 | 盘上是哪一格 | 出处 |
|---|---|---|
| `Block` | 一条链：头槽\* ＋ data 槽\*，不跨 park | [格式 §3](format.md#r021)、§5 |
| `Block().id` | `block_id`：uuid4、128 位、头槽自述区第 0 项 | [格式 §3](format.md#r021) |
| `Block().attr` | 自述区**属性字典**：名唯一、按名 utf-8 升序、条目不可分割 | [格式 §3](format.md#r021) |
| `Block().body` | `block_body_size` 位的那段字节 | [格式 §3](format.md#r021) |
| `Block().ref`？ | 身份：`data_block` / `index_block` 的**表归属** ＋ 开放取值的 `kind` | [索引库 §006](index_db.md#r006) |
| `Body().type`？ | 盘上**没有这一格**：只有字节，没有类型标签 | [格式 §3](format.md#r021) |

- 最后两行的问号是本篇最要紧的地方：`Ref` 与 `type` 是草案新带进来的概念，**盘上找不到对应物**。
  要么它们只是调用侧的便利（那就要说清怎么落成「表归属 ＋ 字节」），要么它们要进盘
  （那就是格式变更，先动 [`config/format.txt`](../../config/format.txt)）。见待定 1 与 4。

### 4. 草案里的笔误（已就地改掉）

| 雏形里的写法 | 问题 | 现在 |
|---|---|---|
| `from oncasket.block import …` | `oncasket/block.py` 不存在、也不允许——顶层白名单只有 `py.typed` 与 `api/` | `from oncasket.api import …` |
| `def init_attr(self):` | 缺返回注解（本仓所有函数都要） | 补 `-> Attr` |
| `def init_body(self) -> None:` 却 `return body.type.set(list)` | 注解与返回不一致 | 拆成调用 ＋ `return body` |
| `self.b.attr.set(...)` 调了两次（`init_attr` 内一次、`__init__` 里又一次） | `set` 是「装进去」还是「读回来」没定 | 见待定 2 |
| `self.ref` / `self.attr` / `self.body` 同时挂在两边 | 同一份内容两处引用，谁是权威没定 | 见待定 2、3 |

### 5. 已经对的地方

- **组合，不是继承**：草案是 `self.b = Block()`，下游持有块、不继承块——块是数据，不是类型。
- **属性走 KV**：要在块上放元数据就进 `attr`，不需要子类（[格式 §3](format.md#r021)）。
- **声明与提交分开**：草案停在声明段，没有把地址塞进构造函数。
- **扩展靠开放取值**：`kind` 不枚举、不加 CHECK（[索引库 §006](index_db.md#r006)），
  下游加一种「装了什么」不用改类、不用发版。

## 待定

| # | 待定项 | 卡在哪 | 谁拍 |
|---|---|---|---|
| 1 | `Ref` 是「表归属（写哪张分表）」还是「指向另一个块」 | §006 说身份由**表归属**表达、「被索引」是**关系**；草案里一个名字像后者、用法像前者 | 待定 |
| 2 | 活句柄（`attr.add(...).set(...)`）是改草稿还是改已落盘 | 盘上属性**条目不可分割**，值变长会改分段：提交后只能整块重写，不能就地改 | 待定 |
| 3 | `Attr(owner, name)` / `Body(owner, name)` 为什么带 owner | 若只是命名空间，owner 是多余耦合；若要用它取 id / 路径，得说清取什么 | 待定 |
| 4 | `body.type` 谁把类型编成字节 | 盘上 body 只有字节；引擎内置几种、还是下游注册编解码器，直接决定公开面长多大 | 待定 |
| 5 | `block_id` 谁生成 | 草案是 `Block()` 自带 uuid4；重建（§013）从载体读回；要幂等 / 去重就得允许指定 | 待定 |
| 6 | 入口对象与读写签名 | 草案没有 handle / session：谁写、写到哪个 hub、`write` / `read` 什么签名 | 待定 |

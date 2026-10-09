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
- `api/` 往下按面分子模块，各自也有 `__all__`：

  | 模块 | 装什么 |
  |---|---|
  | `oncasket.api` | 默认面：把下面几块里**默认开放**的名字重导出 |
  | `oncasket.api.block` | 声明面：`Block` / `Ref` / `Attr` / `Body` |
  | `oncasket.api.hub` | 入口与落地：`Hub` / `Pack` |
  | `oncasket.api.park` | 文件与槽层（**默认不开放**）：`Park` |
  | `oncasket.api.index` | 查询面：`AttrIndex` / `BodyIndex` |

- **推论**（不只是风格）：公开对象只装内容、不碰盘；读写一律经 `_ops`。
  方向永远是 `api` → `_ops`，与[依赖分层表](packages.md#r031)同向，不成环。

### 2. 风格：六条

整套 API 就长在这六条上，新加动作面照这六条推：

1. **短名 ＋ 点号链式**：`h.write(b)`、`attr.add(name, value)`、`attr.lock.item(name)`、
   `index.open()` / `index.set(name, only_one=True)`、`body.type.set(list)`。
   一个点一件事，不叠长名（没有 `set_attribute_value_and_lock()` 这种）。
2. **字符串流转，不枚举、不校验**：角色（`Ref`）、`kind`、类型名都是字符串。
   没有枚举，就没有「非法取值」这个概念——打错字是调用方自己的事。
3. **默认一口气，拆解版不开放**：默认那条把固定流程走完、**引擎担保**；拆解版要显式
   `import` 子模块，按自己的流程走、**引擎不担保**。
4. **句柄读写**：拿到句柄才动得了东西（`body` / `attr` / 属性条目）。锁之后句柄只读。
5. **产物只有 id 与地址**：写与查询的结果都是 `block_id`；地址（`park` ＋ `first_slot_id`）
   是引擎自己的账，不叫你算。
6. **锁即冻结**：`lock` 是可变性开关（frozen 语义），不是并发锁。

### 3. 三段

下游做一件事分成三段——这是设计给的分界，不是实现细节：

| 段 | 谁做 | 手上有什么 | 出处 |
|---|---|---|---|
| ① 声明 | 下游 | 纯内存：块 id、角色、属性、块体；可重复算 | [索引库 §009](index_db.md#r009) ①、[格式 §3](format.md#r021) |
| ② 提交 | 引擎 | 索引行、park、槽地址 | §009 ②–⑦ |
| ③ 读回 | 引擎 | 地址 → 内容（逐槽 `check` 已验过） | [格式 §9](format.md#r021) |

- **地址是结果，不是入参**：`park` / `first_slot_id` 是 ② 的产物，声明段拿不到、也不该拿。
- 内部实现已经长在这个分界上：`plan_block`（内容）→ 物理写 → `parse_block`（读回）。
- ②③ 各有**两套入口**：默认一口气的那条（§9 / §10），以及把流程摊开的拆解版。

### 4. 层与动作面

从槽到 hub 每一层都有动作面，公开面按「默认开放 / 拆解版」切：

| 层 | 公开对象 | 动作面 | 默认面 |
|---|---|---|---|
| 容器 | 不设对象 | 清单与容器锁由引擎代管；多 hub 平铺，用路径表达 | — |
| hub | `Hub` | 开 / 关、写、读、删、列 park、定位地址、清单视图 | **只有 写 / 读 / 删 / 关** |
| park | `Park` | 打开 / 关闭、六个计数、水线懒长、槽读写、清槽、逐槽 `check`、盲扫、写锁 | 否 |
| slot | 不单设对象，是 `Park` 上的槽动作 | 读一个槽、写一个槽、清状态 | 否 |
| block | `Block` / `Ref` / `Attr` / `Body` | 声明、加条目、上锁、声明索引、句柄读写 | 是 |
| index | `AttrIndex` / `BodyIndex` | 声明在块上（`attr.index.*` / `body.index.*`），查询在索引对象上 | 查询是 |

- **默认面就这一点**：`Hub` 的四个动作 ＋ 声明面 ＋ 查询面 ＋ 异常面。
  其余全在拆解版里——不是能力没给，是**不担保**。

### 5. 名字对盘

| 公开名 | 盘上是哪一格 | 出处 |
|---|---|---|
| `Block` | 一条链：头槽\* ＋ data 槽\*，不跨 park | [格式 §3](format.md#r021)、§5 |
| `Block().id` | `block_id`：uuid4、128 位、头槽自述区第 0 项，**引擎生成** | [格式 §3](format.md#r021) |
| `Block().ref` | **角色／表归属**：数据型还是索引型；取值是字符串 | [索引库 §006](index_db.md#r006) |
| `Block().attr` | 自述区**属性字典**：名唯一、按名 utf-8 升序、条目不可分割 | [格式 §3](format.md#r021) |
| `Block().body` | `block_body_size` 位的那段字节 | [格式 §3](format.md#r021) |
| `Body().type` | **块体类型声明**：读端靠它挑解码器；不在块的字节里 | [格式 §3](format.md#r021) |
| `Hub(path)` | 入口：一个 hub 的句柄（索引库、park、锁、清单都在它手里） | [hub 布局 §005](hub.md#r005) |
| `Park(name)` | 一个 `<唯一名>.oncat` 文件（**不是** `Pack`） | [格式 §6](format.md#r021) |
| `Pack(block)` | 把块打成物理槽序的那一层：`check` / `allocate` / `write` / `sync` | [格式 §7](format.md#r021) |

### 6. 声明面（block 层）

```python
b = Block()  # 出来就带 id（uuid4，128 位）

b.ref.set(Ref.data)  # 角色：预制属性；等价于 Ref("data")
b.attr.set(Attr(self, name))  # 属性区：身份就是一条 KV（name 是键）
b.body.set(Body(self, name))  # 块体声明

item = b.attr.add("title", "…")  # 加一条属性，拿它的句柄
item.set("Hello,World")  # 改值（锁之前）
b.attr.get("title").item()  # 按名取句柄

b.body.type.set(list)  # 类型声明：读端靠它解回来
b.attr.index.open()  # 开属性索引
b.attr.index.set("title", only_one=False)
b.body.index.open()  # 开块体索引

b.attr.lock.all()  # 冻结整个属性区
b.attr.lock.item("title")  # 冻结一条
```

- **组合，不是继承**：下游持有 `Block`，不继承 `Block`——块是数据，不是类型。
- `attr` 为什么不是裸 `dict`：**「可自定义」本身就是一套行为**——按名升序落盘、单条上限、
  谁能改到哪一步，都要有地方挂。
- **锁是可变性开关**：`lock.all()` / `lock.item(名)` 之后不可改，语义同 dataclass 的 frozen；
  声明段是纯内存对象，不存在要防的并发写者。
- **句柄就是读写通道**：`body` 句柄写块体，属性句柄读写属性；没有限制说属性不能当块体用
  （索引这类特化场景天然是 KV，拿它当载体正好）。

### 7. 类型与类型登记册

- `body.type` 是**类型声明**：data 槽里的字节就是 Python 原生结构落下来的那一份，
  **不知道类型就解不回来**——声明它，读端才不必盲猜这是 list、dict 还是 string。
- 它不给自己在块的字节里占一格（盘上 body 只有 `block_body_size` 位字节），而是**登记**在
  hub 级清单 `hub.lock.json` 里：记着每个块、每个属性、每个 block 的类型。**写端负责登记，
  读端从那儿取**——这份登记本身就是**为迁移设计**的（换一套代码读老数据，靠的就是它）。
- 登记册是**不可再生资产**：它丢了，盘上的数据还在、但读端不知道该按什么解——
  能看见、解不开。所以它跟着容器走，并进迁移与修复的视野。

### 8. 提交面

**默认**：把块交给 hub，[索引库 §009](index_db.md#r009) ②–⑦ 一口气走完——引擎担保：

```python
h = Hub("hub")
block_id = h.write(b)
```

**拆解版**（`from oncasket.api.hub import Pack`；默认不开放、引擎不担保）：

```python
p = Pack(b)
p.check()  # 内容自洽
if p.allocate(h):  # 找现成 park 并分配段
    pass
else:
    p.re_allocate(h)  # 没合适的就换一个 / 扩预算
p.write(h)  # 落槽：头槽 → 溢出槽\* → data 槽\*
p.sync(h)  # 与索引库对账、回流地址
```

- 每一步都能拿到 hub 手里那几样东西（库、park、锁），所以拆得开。
- 顺序**不保证**：`check` 漏了、`sync` 忘了，出来的东西引擎不管。

### 9. 读取面：两条腿

```python
blk = h.read(block_id)  # 一口气：查库拿地址 → 组链 → 逐槽 check

addr = h.locate(block_id)  # 拆解版：库 → 地址
park = h.park(addr.park)  # → park
blk = park.block(addr.first_slot_id)  # → 块
body = blk.body.get()  # → 内容
```

- `read` 对**删掉的 / 没写完的**块抛异常（`NotFoundError` / `CorruptError`），不返回半个块。
- 拆解版同样不担保：中间隔多久、park 会不会被删，都要你自己盯着。

### 10. 删除面

```python
h.delete(block_id)
```

- 按[格式 §8](format.md#r021)：**先动物理**（头槽 `state` 清成 `empty` → 其余槽清空），
  **物理动完再动库**（删行，身份分表级联清）。
- 幂等：崩在中间再删一次不出错；槽位永不摘除（位置即身份）。

### 11. 索引面

库里只放**身份、地址、状态**（`block` 的八列与两条索引），**不给用户属性建任何库侧索引**；
要按属性或块体反查，走**索引块**——这就是「两种块」存在的理由：

| 块 | 装什么 |
|---|---|
| 数据块 | 用户的内容（属性 ＋ 块体） |
| 索引块 | 「谁在哪」：键 → `block_id` 的对照 |

**声明在块上**（§6）：`attr.index.open()` / `attr.index.set(名, only_one=)` / `body.index.open()`。

- **`open` 是手动开关**：不开，索引块压根不收你的东西——跟数据库里不建索引就不处理是一个道理。
- **属性侧**：`open` 之后**默认全量**，一旦 `set` 就**只听点名的**（12 个里点 3 个，
  其余 9 个全不进）。不做「纯排除」写法——那种需求本身不成立。
- **块体侧**：`open` 之后写入时**主动留存一份纯正文**（剔掉填充等非正文部分），
  对完整正文算哈希、按哈希留存；没有点名机制。

**查询在索引对象上**：

```python
aix = AttrIndex(h, "title")  # 绑一个 hub 与一条属性
ids = aix.search("Hello,World")  # 取值 → block_id 表

bix = BodyIndex(h)
ids = bix.search(body_hash)  # 正文哈希 → block_id 表
```

- **返回永远是 `list[bytes]`**：`only_one` 只影响长度（≤ 1），不改签名——签名不随开关跳。
- 一个键后面挂几个 `block_id`，属性与块体**共用同一个开关** `only_one`：

  | 索引 | 键是什么 | `only_one=False`（默认） | `only_one=True` |
  |---|---|---|---|
  | `AttrIndex` | 属性取值 | 一个取值挂一**串** `block_id` | 该取值全局唯一：只许一个 |
  | `BodyIndex` | 正文哈希 | 理论上一个正文对一个块，但**完全重复的正文只留存一份**，一个哈希下挂多个 `block_id`——内建去重 | 严格一一对应 |

- **索引块分两层**：门面上就 `AttrIndex` / `BodyIndex` 两个，底下一大堆**子索引块**
  （它自己又索引了一批 block）。块有上限，装满了必然增量——你不是直接锁到目标块，
  而是一层层锁下去，**但总共就两层**。
- **根入口**：根的 `block_id` 登记在 §7 那份清单里（快路径）；同时**根索引块自描述**
  （自述区带 `index.*` 属性），盲扫就能认出它——重建因此不依赖清单，与
  [§013「索引可完全由载体重建」](index_db.md#r013)同一条精神。
- **其余索引块随便造**：引擎原生只提供这两种，想索引别的东西自己造——逻辑本来就是确定的
  （拿到 `block_id` 之后按你自己的数据结构去查），引擎不拦。
- **索引的产物只有一样：`block_id`**。拿到 id 之后就没有难事了——地址在库里、内容在载体上，
  读回走 §9 的正常那条路。

### 12. 拆解版：park 与 slot 层

`from oncasket.api.park import Park`（默认不开放）：

```python
park = h.park(name)          # 打开一个已有的 park（不自建；建由 Pack.allocate 负责）
park.counts                  # slot_size / num / live / used / dead / empty（格式 §5）
park.grow(n)                 # 水线懒长到 n——文件只长到水线，容量不预支磁盘
park.read_slot(i) -> bytes
park.write_slot(i, blob)     # 一个槽一次写满 slot_size / 8 B
park.clear_slot(i)           # 状态清成 empty（删除路径）
park.verify(i) -> bool       # 本槽 check（格式 §10）
park.scan()                  # 盲扫（格式 §9）：认出来的块
park.lock() / park.unlock()  # park 级写锁（格式 §6）
park.close()
```

- slot 层**不单设对象**：一个 slot 就是 `park` 上的一个槽号，动作挂在 `park` 上。
- 这层的一切都**不担保**：写坏一个槽、水线拉错，是调用方的事。

### 13. 异常面

```
OnCasketError                 引擎所有异常的基类
├─ SchemaMismatchError        索引库指纹 / park version 不符 —— 版本类，不进修复清单
├─ SqliteTooOldError          运行时 SQLite 低于下限
├─ NotFoundError              读 / 删一个不存在的块
├─ LockBusyError              写锁没拿到
└─ CorruptError               修过仍不行 —— 抛它就是把块判坏了
```

- **异常分内外**（[修复 §032](repair.md#r032)）：**外部异常**（参数不合法、找不到、锁被占、
  版本类不符）直接呈报，没有后续动作；**内部异常**（校验不过、计数不自洽、索引与载体对不上）
  **不直接抛**——先记日志 → 走修复 → 修完复检，**修不动才升级**成 `CorruptError` 抛出去。
- 判坏要出声：`CorruptError` 是唯一表示「这条数据没救了」的出口。

### 14. 生命周期与并发

```python
h = Hub("hub")  # 打开；目录不在就建（幂等）
h.close()  # 或者：

with Hub("hub") as h:
    h.write(b)
```

- **`Hub(path)` 幂等**：已存在就打开，不存在就建（目录树 ＋ 索引库 ＋ 清单 ＋ 锁）。
  默认那条腿要能「拿来就用」，把建 / 开分成两步只会让常用路径变长。
- **读者可以很多，写者串行**：写由 park 级写锁罩着（[格式 §6](format.md#r021)）；
  拿不到锁抛 `LockBusyError`——**不排队、不等待**，要等是调用方的事。
- 库侧不引入额外事务模型（[索引库 §008](index_db.md#r008)）。

### 15. 本期不做

写下来是为了别人不再提一遍：

- **范围 / 前缀 / 模糊查询**：索引只给等值。
- **遍历**：不提供「列全部块」「扫全库」——索引块是唯一的反查入口。
- **事务 / 回滚**：[索引库 §009](index_db.md#r009) 说得直白——本引擎不做数据版本管理，写入一经
  提交即为当前值，没有历史可退。
- **多写者并发写**：park 级写锁串行。
- **顶层容器对象**：多 hub 用路径表达，不设 `Container` 类。
- **只读打开**：真有需求再加。

### 16. 草案偏差与笔误

demo 是随手写的（作者原话），下面是它和本页口径的差：

| 雏形里的写法 | 问题 | 现在 |
|---|---|---|
| `from oncasket.block import …` | `oncasket/block.py` 不存在也不允许 | `from oncasket.api import …` |
| `def init_attr(self):` | 缺返回注解（本仓所有函数都要） | 补 `-> Attr` |
| `def init_body(self) -> None:` 却 `return body.type.set(list)` | 注解与返回不一致 | 拆成调用 ＋ `return body` |
| `self.b.attr.set(...)` 调了两次 | `set` 到底是「装进去」还是「读回来」 | 装进去并返回句柄，与 §6 一致 |
| `attr.lock("item")` | 与 `lock.all()` 长短不一，且没带参数 | `attr.lock.item(名)` |
| `no_one=…, only_one=…` | 两个开关会打架（都关就悬空） | 只留 `only_one`：一个布尔没有悬空态 |
| `self.Hub("hub")` | 类名写成实例属性 | `Hub("hub")` |
| `AttrIndex()` / `BodyIndex()` 无参 | 查询必须知道**查哪个 hub、哪条属性** | `AttrIndex(h, "title")` / `BodyIndex(h)` |
| `aix.search("")` | 空键没有意义 | 传取值本身 |
| `self.p.sync(self.h.index.db)` | 把手伸进了 hub 内部 | `p.sync(h)` |

### 17. 已经对的地方

- **组合，不是继承**：`self.b = Block()`，下游持有块、不继承块。
- **角色与类型都走字符串**：不枚举、不加 CHECK，加一种「装了什么」不用改类、不用发版。
- **声明与提交分开**：草案停在声明段，地址是引擎的账。
- **id 由引擎给**：下游不参与身份生成，也就不会撞 id。
- **默认担保 / 拆解自便**：两套入口同一个分界，不是两套世界观。

## 待定

| # | 待定项 | 卡在哪 | 谁拍 |
|---|---|---|---|
| 1 | 类型登记册与「锁不做账本」冲突 | 本页按作者口径把登记放进 `hub.lock.json`：那就要改 [hub 布局 §005](hub.md#r005) 与 [`_hub/lock.py`](../../src/oncasket/_hub/lock.py) 里「锁不做账本」那句；若改主意就挪进 `hub.conf.json`（[§026](hub.md#r026) 的清单） | 待定 |
| 2 | `Pack` / `Park` 只差一个字母 | 本页保留作者命名（`Pack` 是打包一个块，`Park` 是那个文件）；要不要改成 `Packer` / `Writer` | 待定 |
| 3 | 索引根入口的落地细节 | 口径定了（清单快路径 ＋ 根索引块自描述）；根块的 `index.*` 属性具体叫什么名、写哪几个字段 | 待定 |

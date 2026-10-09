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
- `api/` 往下按**层**分子模块，各自也有 `__all__`：

  | 模块 | 装什么 | 默认面 |
  |---|---|---|
  | `oncasket.api` | 把下面几块里**默认开放**的名字重导出 | 是 |
  | `oncasket.api.block` | 声明面：`Block` / `Ref` / `Attr` / `Body` | 是 |
  | `oncasket.api.hub` | 库层：`Hub` | 是 |
  | `oncasket.api.park` | 载体层：`Park` / `Packer` | 否 |
  | `oncasket.api.slot` | 槽层：`Slot` | 否 |
  | `oncasket.api.index` | 查询面：`AttrIndex` / `BodyIndex` | 是 |

- **推论**（不只是风格）：公开对象只装内容、不碰盘；读写一律经 `_ops`。
  方向永远是 `api` → `_ops`，与[依赖分层表](packages.md#r031)同向，不成环。

### 2. 风格

整套 API 长在这八条上，新加动作面照这八条推：

1. **短名 ＋ 点号链式**：`hub.write(block)`、`attr.add(name, value)`、
   `attr.lock.item(name)`、`attr.index.set(name, only_one=True)`、`body.type.set(list)`。
2. **名字一层一层叠，不猜**：`attr.index.open()`、`body.index.open()`、`park.slot(index).verify()`
   ——层级从名字里就能读出来，不造需要猜的短名。
3. **字符串流转，不枚举、不校验**：角色（`Ref`）、`kind`、类型名都是字符串。
   没有枚举，就没有「非法取值」这个概念——打错字是调用方自己的事。
4. **默认一口气，拆解版不开放**：默认那条走固定流程、**引擎担保**；拆解版要显式
   `import` 子模块，按自己的流程走、**引擎不担保**。
5. **句柄读写**：拿到句柄才动得了东西（`body` / `attr` / 属性条目）。锁之后句柄只读。
6. **产物只有 id 与地址**：写与查询的结果都是 `block_id`；地址（载体 ＋ 首槽 id）是引擎的账。
7. **不给「先抠个对象再塞进去」的 API**：参数要么是你自己的东西（块、取值、名字、id），
   要么是上一步交回来的句柄。不逼你去别人肚子里掏零件（`sync(hub.index.db)` 这种就是反面）。
8. **锁即冻结**：`lock` 是可变性开关（frozen 语义），不是并发锁。

### 3. 三段

下游做一件事分成三段——这是设计给的分界，不是实现细节：

| 段 | 谁做 | 手上有什么 | 出处 |
|---|---|---|---|
| ① 声明 | 下游 | 纯内存：块 id、角色、属性、块体；可重复算 | [索引库 §009](index_db.md#r009) ①、[格式 §3](format.md#r021) |
| ② 提交 | 引擎 | 索引行、载体、槽地址 | §009 ②–⑦ |
| ③ 读回 | 引擎 | 地址 → 内容（逐槽 `check` 已验过） | [格式 §9](format.md#r021) |

- **地址是结果，不是入参**：载体与首槽 id 是 ② 的产物，声明段拿不到、也不该拿。
- 内部实现已经长在这个分界上：`plan_block`（内容）→ 物理写 → `parse_block`（读回）。
- **两套面就长在这个分界上**：

  | 面 | 谁 | 落盘 |
  |---|---|---|
  | **内存面** | `Block` / `Ref` / `Attr` / `Body`（① 声明） | **不落**——纯内存操作；改属性、改块体都还在草稿里 |
  | **落地面** | `Hub` / `Park` / `Slot`（②③） | **真落**——落了就是真落了 |

- **索引是例外**：索引那一套**真落**——它不认你手上这份块是草稿还是现役，所以写索引要谨慎（§10）。

### 4. 分层：优先用高层

**能用 `Hub` 就别下到 `Park`，能 `Park` 就别碰 `Slot`。**
越往下摸，权限越高、影响面越广；越往上包，包得越深、越智能，一键解决很多问题。

| 层 | 对象 | 职责 | 味道 |
|---|---|---|---|
| hub（库） | `Hub` | 宏观的**增删改查** | 包得最深；一键解决 |
| park（载体） | `Park` / `Packer` | 真正的**读写策略**：选载体、分配、链装配、校验、删除顺序、对账 | 权限更高，影响面更广 |
| slot | `Slot` | **纯读写协议**：一个定长格怎么读、怎么写、怎么清 | 最底层，最原则性 |

- **下层给不了你上层的东西**：`Slot` 不认识块，`Park` 不认识提交点——它们只有原则性的能力。
- 所以公开面按「默认开放 / 拆解版」切：默认面 = `Hub` 的四个动作 ＋ 声明面 ＋ 查询面 ＋
  异常面；其余全在拆解版里，**不是能力没给，是不担保**。
- 每层的对象都由上一层的动作交回来，一层一层往下：
  `Hub` →（`hub.park(name)`）→ `Park` →（`park.slot(index)`）→ `Slot`。

### 5. 名字对盘

| 公开名 | 盘上是哪一格 | 出处 |
|---|---|---|
| `Block` | 一条链：头槽\* ＋ data 槽\*，不跨载体 | [格式 §3](format.md#r021)、§5 |
| `Block().id` | `block_id`：uuid4、128 位、头槽自述区第 0 项，**引擎生成** | [格式 §3](format.md#r021) |
| `Block().ref` | 自述区里的一条**内置属性**（键 `ref`）：数据型还是索引型；取值是字符串 | [索引库 §006](index_db.md#r006) |
| `Block().attr` | 自述区**属性字典**：名唯一、按名 utf-8 升序、条目不可分割 | [格式 §3](format.md#r021) |
| `Block().body` | `block_body_size` 位的那段字节 | [格式 §3](format.md#r021) |
| `Body().type` | **块体类型声明**：读端靠它挑解码器；不在块的字节里 | [格式 §3](format.md#r021) |
| `Hub(path)` | 库层句柄：一个 hub（索引库、载体、锁、清单都在它手里） | [hub 布局 §005](hub.md#r005) |
| `Park(name)` | **载体**：一个 `<唯一名>.oncat` 定长文件 | [格式 §6](format.md#r021) |
| `Slot(index)` | 载体里的一个定长格（位置即身份，永不摘除） | [格式 §2](format.md#r021) |
| `Packer(block)` | 把块打成物理槽序的那一层：`check` / `allocate` / `write` / `sync` | [格式 §7](format.md#r021) |

- **`park` 取的是「载体」的意思**：承载 block 的那个定长文件。它不是"停车场"，
  改名不改义；文件怎么摊在容器里见 [hub 布局 §005](hub.md#r005)。
- **`Park` 与 `Packer` 别混**：`Park` 是载体（那个文件），`Packer` 是「把块打成槽序」的执行者。
  原来叫 `Pack`，与 `Park` 只差一个字母，改掉了——名词与执行者分开。

### 6. 声明面（block 层）

**这一层是纯内存**（§3 的「内存面」）：`Block` / `Ref` / `Attr` / `Body` 的所有动作都不碰盘。
块是**组织性的概念**——它把内容聚在一起；改属性、改块体都跟它关系不大。

```python
block = Block()  # 出来就带 id（uuid4，128 位）

block.ref.set(Ref.data)  # 角色：预制属性；等价于 Ref("data")
block.attr.set(Attr(owner, "notebook"))  # 属性区：身份就是一条 KV（name 是键，owner 是挂在谁身上）
block.body.set(Body(owner, "notebook"))  # 块体声明

title = block.attr.add("title", "未命名")  # 加一条属性，拿它的句柄
title.set("Hello,World")  # 改值（锁之前）
block.attr.get("title").item()  # 按名取句柄

block.body.type.set(list)  # 类型声明：读端靠它解回来
block.attr.index.open()  # 开属性索引
block.attr.index.set("title", only_one=False)
block.body.index.open()  # 开块体索引

block.attr.lock.all()  # 冻结整个属性区
block.attr.lock.item("title")  # 冻结一条
```

- **组合，不是继承**：下游持有 `Block`，不继承 `Block`——块是数据，不是类型。
- `attr` 为什么不是裸 `dict`：**「可自定义」本身就是一套行为**——按名升序落盘、单条上限、
  谁能改到哪一步，都要有地方挂。
- **锁是可变性开关**：`lock.all()` / `lock.item(名)` 之后不可改，语义同 dataclass 的 frozen。
  声明段是纯内存对象，不存在要防的并发写者。
- **句柄就是读写通道**：`body` 句柄写块体，属性句柄读写属性；没有限制说属性不能当块体用
  （索引这类特化场景天然是 KV，拿它当载体正好）。
- **`ref` 就是一条属性**：`block.ref.set(Ref.data)` 与 `block.attr.set("ref", Ref.data)`
  是同一件事——角色不是单独的结构，它是自述区里一条**约定好名字**的属性。所以扫块时读属性
  就分得出数据块与索引块，**重建不需要另立登记**，动作还是那个动作。

### 7. 类型：装在索引条目里，不改格式

- `body.type` 是**类型声明**：data 槽里的字节就是 Python 原生结构落下来的那一份，
  **不知道类型就解不回来**——声明它，读端才不必盲猜这是 list、dict 还是 string。
- **不去改块格式。** 往块上加保留字段不是个有效办法：格式一动，全仓的位布局与指纹跟着动。
  块的自述区本来就是**开放 KV**，内置几个约定键（`ref` 就是其中一个）已经够用；
  其余的一律**靠增量索引块**表达。
- **类型装在索引条目里**（§10）：条目是 `{block_id, value, value_type}`，查一条就同时拿到
  id、取值与类型——**自包含**，不用回头翻块，也不用另找一份登记。
- 所以「专门管类型的块」不必另发明一种结构：它就是**一个索引块**，在库里按索引块登记
  （复用现成那两张身份分表，不动 [`config/index_db.sql`](../../config/index_db.sql) 与 schema 指纹）。
- **没开索引的数据**，条目不产出、类型也就没地方记——这一条见待定 1。

### 8. 库层：增删改查

四个动作都在 `Hub` 上——这是**默认面**，引擎担保：

```python
hub = Hub("path/to/hub")

block_id = hub.write(block)  # 增
block = hub.read(block_id)  # 查
hub.update(block_id, attr={"title": "改过的值"})  # 改：基准点 ＋ 新值
hub.delete(block_id)  # 删
```

**增（write）**：`block_id = hub.write(block)`。[索引库 §009](index_db.md#r009) ②–⑦ 一口气走完。

**查（read）**：`block = hub.read(block_id)`。**读的过程必然带强哈希验证**——逐槽 `check`
＋ 整块 `global_hash`，验不过就抛，不给半个块。

**删（delete）**：`hub.delete(block_id)`。按[格式 §8](format.md#r021)：先动物理（头槽状态清成
`empty` → 其余槽清空），物理动完再动库（删行，身份分表级联清）。

- **删是真的删**——不留墓碑、不做软删。要软删是调用方自己的事（在 `attr` 里放一个
  `deleted` 之类的标记，自己筛）；引擎不管。

**改（update）**：**最少两个参数**——一个**基准点**（`block_id`，或索引查出来的那个 id）＋
一样**新值**（属性、块体，至少给一样）：

```python
hub.update(block_id, attr={"title": "改过的值"})  # 改属性
hub.update(block_id, body=b"...")  # 改块体
```

- **改的是属性与块体，不是块**：`Block` 是**组织性的概念**——它把内容聚在一起，
  改数据这件事跟它关系不大。
- **机制**：修改之前**必须先验证一遍哈希**，而这一步就落在「读」上——按基准点把现役那一份
  读回来（读的过程必然带强校验），应用新值之后再**写前验一次**：中途被别处改过就报错，
  不静默覆盖（乐观并发，撞上抛 `ConflictError`——见 §11）。
- 这也解释了基准点为什么不能省：没有它，引擎不知道你改的是哪一份，也就谈不上「改前先验」。

### 9. 拆解版：载体层与槽层

`Packer` 把流程摊开（`from oncasket.api.park import Packer`；默认不开放、引擎不担保）：

```python
packer = Packer(block)
packer.check()  # 内容自洽
if not packer.allocate(hub):  # 找准载体并分配段
    packer.re_allocate(hub)  # 没合适的就换一个 / 扩预算
packer.write(hub)  # 落槽：头槽 → 溢出槽\* → data 槽\*
packer.sync(hub)  # 与索引库对账、回流地址
```

读取也拆得开（形状对应"库 → 载体 → 块 → 内容"）：

```python
address = hub.locate(block_id)  # 库 → 地址
park = hub.park(address.park)  # → 载体
block = park.block(address.first_slot_id)  # → 块
body = block.body.get()  # → 内容
```

载体层（`from oncasket.api.park import Park`）：

```python
park = hub.park(name)  # 打开一个已有的载体（不自建；建由 Packer.allocate 负责）
park.counts  # slot_size / num / live / used / dead / empty（格式 §5）
park.grow(count)  # 水线懒长——文件只长到水线，容量不预支磁盘
park.scan()  # 盲扫（格式 §9）：认出来的块
park.lock() / park.unlock()  # 载体级写锁（格式 §6）
park.close()
```

槽层（`from oncasket.api.slot import Slot`）——**纯读写协议**，只认一个定长格：

```python
slot = park.slot(index)      # 立到某个槽上
slot.read() -> bytes         # 整槽字节
slot.write(blob)             # 一个槽一次写满 slot_size / 8 B
slot.clear()                 # 状态清成 empty（删除路径）
slot.verify() -> bool        # 本槽 check（格式 §10）
slot.state                   # 槽状态值（header_start / header_mid / data_mid / data_end / empty）
```

- 这两层的一切都**不担保**：写坏一个槽、水线拉错、顺序调反，都是调用方的事。
- `Slot` 不认识块、`Park` 不认识提交点——**下层给不了你上层的东西**。

### 10. 索引面

库里只放**身份、地址、状态**（`block` 的八列与两条索引），**不给用户属性建任何库侧索引**；
要按属性或块体反查，走**索引块**——这就是「两种块」存在的理由：

| 块 | 装什么 |
|---|---|
| 数据块 | 用户的内容（属性 ＋ 块体） |
| 索引块 | 「谁在哪」：键 → `block_id` 的对照 |

**索引块的条目结构**（属性索引与块体索引长得一样）：

```json
{"attr": [{"block_id": "", "value": "", "value_type": ""}]}
{"body": [{"block_id": "", "value": "", "value_type": ""}]}
```

- 一条条目 = **哪个块** ＋ **取值** ＋ **取值的类型**。查到一条就直接能去读块、按类型解回来
  ——这就是「自包含」：索引自己能活，不用回块里翻额外字段，也不用另找一份登记。
- 也正因为类型躺在条目里，**开过索引**的数据天生可解；**没开索引**的就没有这条——见待定 1。

**声明在块上**（§6）：`attr.index.open()` / `attr.index.set(名, only_one=)` / `body.index.open()`。

- **索引那一套是真落的**（§3 的例外）：它不认你手上这份块是草稿还是现役——所以写索引要谨慎，
  它不像 `Block` 的其它动作那样只在内存里转。

#### 索引什么时候落：抄数据库的时序

**先数据、后索引**：块先落完（[索引库 §009](index_db.md#r009) ②–⑦ 走完，`state` 翻 `ok`、
地址回流），**索引块随后更新**；不先落索引。

- 抄的就是数据库那套：**数据是本体，索引是从属**。索引晚一步，崩了也不会出现
  「索引指向一个盘上不存在的块」；反过来先落索引，读侧就得天天处理悬空条目。
- **崩在中间不是坏**：索引缺条目可以补齐——索引完全能由载体重建（[§013](index_db.md#r013)），
  对账时按载体补上，对不上的悬空条目一并清掉。
- 「写索引要谨慎」（§3 的例外）说的是它**真落、不是草稿**，不是"立刻落"。

- **`open` 是手动开关**：不开，索引块压根不收你的东西——跟数据库里不建索引就不处理是一个道理。
- **属性侧**：`open` 之后**默认全量**，一旦 `set` 就**只听点名的**（12 个里点 3 个，其余 9 个全不进）。
  不做「纯排除」写法——那种需求本身不成立。
- **块体侧**：`open` 之后写入时**主动留存一份纯正文**（剔掉填充等非正文部分），对完整正文
  算哈希、按哈希留存；没有点名机制。

**查询在索引对象上**：

```python
attr_index = AttrIndex(hub, "title")  # 绑一个库与一条属性
block_ids = attr_index.search("Hello,World")

body_index = BodyIndex(hub)
block_ids = body_index.search(body_hash)
```

- **返回永远是 `list[bytes]`**：`only_one` 只影响长度（≤ 1），**不改签名**——签名不随开关跳。
- 一个键后面挂几个 `block_id`，属性与块体**共用同一个开关** `only_one`：

  | 索引 | 键是什么 | `only_one=False`（默认） | `only_one=True` |
  |---|---|---|---|
  | `AttrIndex` | 属性取值 | 一个取值挂一**串** `block_id` | 该取值全局唯一：只许一个 |
  | `BodyIndex` | 正文哈希 | 理论上一个正文对一个块，但**完全重复的正文只留存一份**，一个哈希下挂多个 `block_id`——内建去重 | 严格一一对应 |

- **索引块分两层**：门面上就 `AttrIndex` / `BodyIndex` 两个，底下一大堆**子索引块**
  （它自己又索引了一批 block）。块有上限，装满了必然增量——你不是直接锁到目标块，
  而是一层层锁下去，**但总共就两层**。
- **根入口**：根的 `block_id` 记在库里的身份分表与地址上（拿到 id 就能定位）；「哪个块是某个
  索引的根」用一条**内置约定属性**写在根索引块自己身上——跟 `ref` 一样只是约定键，不动格式。
  这样扫载体也认得出根，重建不依赖库，与 [§013](index_db.md#r013)同一条精神。
- **其余索引块随便造**：引擎原生只提供这两种，想索引别的东西自己造——逻辑本来就是确定的
  （拿到 `block_id` 之后按你自己的数据结构去查），引擎不拦。
- **索引的产物只有一样：`block_id`**。拿到 id 之后就没有难事了——地址在库里、内容在载体上。

### 11. 异常面

```
OnCasketError                 引擎所有异常的基类
├─ SchemaMismatchError        索引库指纹 / 载体 version 不符 —— 版本类，不进修复清单
├─ SqliteTooOldError          运行时 SQLite 低于下限
├─ NotFoundError              基准点找不到（id 不对，或那块已经被删）
├─ ConflictError              基准点还在，但你手上那份不是现役（乐观并发冲突）
├─ LockTimeoutError           写锁等超时（等过一轮还拿不到）
└─ CorruptError               先修过、修不动才抛 —— 抛它就是把块判坏了
```

- **参数不合法用内建 `ValueError`**，不另立类：引擎不替 Python 定义参数错误。
- **并发要细分，程度不一样**（作者口径）：

  | 情形 | 程度 | 处置 |
  |---|---|---|
  | 载体被别的写者锁着 | 正常，可重试 | **等**，不是立刻抛；等到超时才 `LockTimeoutError`，过会儿再来 |
  | 基准点还在、内容已不是现役（别人改过） | 正常，可重试 | `ConflictError`：重新读一遍再改 |
  | 基准点找不到（id 不对） | 调用方错 | `NotFoundError` |
  | id 对得上、哈希对不上 | 可能真坏了 | **先修**（`R001`–`R004`）；修不动才 `CorruptError` |
  | 版本类不符（指纹 / `version`） | 拒开 | `SchemaMismatchError`，不进修复清单 |

- **一律先修再判坏**（[修复 §032](repair.md#r032)）：内部异常（哈希对不上、计数不自洽、索引与载体
  对不上）**不直接抛**——先记日志 → 走修复 → 修完复检，**修不动才升级**成 `CorruptError`。
  外部异常（找不到、锁超时、并发冲突、版本类不符）直接呈报，没有后续动作。
- 判坏要出声：`CorruptError` 是唯一表示「这条数据没救了」的出口。

### 12. 生命周期与并发

```python
hub = Hub("path/to/hub")  # 打开；目录不在就建（幂等）
hub.close()  # 或者：
with Hub("path/to/hub") as hub:
    hub.write(block)
```

- **`Hub(path)` 幂等**：已存在就打开，不存在就建（目录树 ＋ 索引库 ＋ 清单 ＋ 锁）。
  默认那条腿要能「拿来就用」，把建 / 开分成两步只会让常用路径变长。
- **读者可以很多，写者串行**：写由载体级写锁罩着（[格式 §6](format.md#r021)）。
  拿不到锁**就等**——等超过超时才抛 `LockTimeoutError`，让调用方过会儿再来。
- **本期不做原子写**：并发靠「锁 ＋ 等」串行，不承诺写的原子性。数据结构是槽级的、
  理论上做得到原子写，但**拿不出代码就不算数**（谁能写出来，谁再来提这条）。
- 库侧不引入额外事务模型（[索引库 §008](index_db.md#r008)）。

### 13. 本期不做

写下来是为了别人不再提一遍：

- **软删 / 墓碑**：删就是真删；要软删自己在 `attr` 里做标记。
- **范围 / 前缀 / 模糊查询**：索引只给等值。
- **遍历**：不提供「列全部块」「扫全库」——索引块是唯一的反查入口。
- **事务 / 回滚**：[索引库 §009](index_db.md#r009)——本引擎不做数据版本管理，写入一经提交
  即为当前值，没有历史可退。
- **原子写**：见 §12，靠锁等待串行；代码拿不出来就不算承诺。
- **多写者并发写**：载体级写锁串行。
- **顶层容器对象**：多 hub 用路径表达，不设 `Container` 类。
- **只读打开**：真有需求再加。

### 14. 草案偏差与笔误

demo 是随手写的（作者原话：变量名图省事用了单字母，本页一律用全名），下面是它和本页口径的差：

| 雏形里的写法 | 问题 | 现在 |
|---|---|---|
| `from oncasket.block import …` | `oncasket/block.py` 不存在也不允许 | `from oncasket.api import …` |
| `from oncasket.api.hub import Hub, Pack` | `Pack` 属载体层且与 `Park` 只差一个字母 | `Hub` 在 `api.hub`，`Packer` 在 `api.park` |
| `def init_attr(self):` | 缺返回注解（本仓所有函数都要） | 补返回注解 |
| `def init_body(self) -> None:` 却 `return body.type.set(list)` | 注解与返回不一致 | 拆成调用 ＋ `return body` |
| `block.attr.set(...)` 调了两次 | `set` 到底是「装进去」还是「读回来」 | 装进去并返回句柄 |
| `attr.lock("item")` | 与 `lock.all()` 长短不一，且没带参数 | `attr.lock.item(名)` |
| `no_one=…, only_one=…` | 两个开关会打架（都关就悬空） | 只留 `only_one`：一个布尔没有悬空态 |
| `self.Hub("hub")` | 类名写成实例属性 | `Hub(path)` |
| `AttrIndex()` / `BodyIndex()` 无参 | 查询必须知道**查哪个库、哪条属性** | `AttrIndex(hub, "title")` / `BodyIndex(hub)` |
| `search("")` | 空键没有意义 | 传取值本身 |
| `sync(hub.index.db)` | 逼调用方去 hub 肚子里抠零件 | `sync(hub)` |
| `self.p.write(self.h)` 这类单字母 | 单字母只适合手写草稿 | 本页一律 `pack` / `hub` / `park` / `slot` |

### 15. 已经对的地方

- **组合，不是继承**：下游持有 `Block`，不继承 `Block`。
- **角色与类型都走字符串**：不枚举、不加 CHECK，加一种「装了什么」不用改类、不用发版。
- **声明与提交分开**：草案停在声明段，地址是引擎的账。
- **id 由引擎给**：下游不参与身份生成，也就不会撞 id。
- **默认担保 / 拆解自便**：两套入口同一个分界，不是两套世界观。

## 待定

| # | 待定项 | 卡在哪 | 谁拍 |
|---|---|---|---|
| 1 | 没开索引的数据，类型给不给招 | **我的建议：不给。** 理由——`open` 是手动开关（不开，索引块压根不收你的东西）；若给未索引的数据也补一份类型登记，等于偷偷替所有人开了一个索引，`open` 就白设了。代价要说明白：**没开索引 = 不承诺可解**（迁移时只保证字节在，不保证解释得了）。等你拍 | 待定 |
| 2 | 锁等待超时缺省多久、能不能配 | 口径定了「等，超时才抛 `LockTimeoutError`」；缺省值（秒级？）与能不能按调用传，没定 | 待定 |

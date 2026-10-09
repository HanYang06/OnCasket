<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 格式：hub / park / slot / block

> 域：内核 / 存储引擎 / 格式。对应路线图 [1.x 路线增量](../roadmap/1.x.md)。
>
> **事实依据**：[`config/format.txt`](../../config/format.txt)——字段、位偏移、类型、取值以它为准，本文不另立、不改。
> 规范见[文档规范](../README.md)。

## <a id="r021"></a>021 格式设计：hub / park / slot / block

- 决策状态：已定

### 1. 怎么读事实依据

- **声明层**（首部 `key: value;`）：`Offset-unit` / `offset-base` / `extent` / `origin` / `divider`。
- **段类标尺** `|---|…|---|…|---|`：把文件分成三类段——文件级（`format_pack`）、slot 级（三种槽形态）、枚举型（`slot_state`）。
- **同类分隔** `>>>>>>>>`：同类段之间换形态时的分隔。
- 行 = `<名称> <类型> <偏移|取值>`；缩进 4 空格/级表归属。
- **偏移**一律相对其父区起点；起点可写 `header:`，表示该槽起点。
- **区间**：区域行 `<起点>:<长度>`，字段行 `<起点>:<终点>`。
- **单位**一律位；槽内 4 字节魔数写 `unit:4byte`。

### 2. 三层

| 层 | 形态 | 定长 |
|---|---|---|
| hub | 目录（文件库），布局见 [hub 布局 §005](hub.md#r005) | 不定长 |
| park | 一个文件 `pack/<h0:2>/<h2:4>/<唯一名>.oncat` | `slot_num × slot_size` |
| slot | park 内的定长格 | `slot_size`，默认 8192 位（1024 B） |
| block | 一段连续槽，不跨 park | 由头槽里的计数决定 |

- 端序小端（LE），全文一致。
- park 头：`version`（256 位带盐 sha256，管格式不管数据）＋ `slot_size` / `slot_num` / `slot_live` /
  `slot_used` / `slot_dead` / `slot_empty`（各 int32），其余保留。
- 槽区从 1024 位（128 B）起；槽的物理偏移 `= 1024 + id × slot_size`——**位置即身份**，槽位永不摘除。
- 容量与懒生成：`slot_num` 是容量上界（槽总数），容量 `= slot_num × slot_size`；文件只长到水线
  `slot_live`，长度 `= 1024 + slot_live × slot_size`（位），容量不预支磁盘。
- 不变量：`slot_num ≥ 1`、`slot_live ≤ slot_num`、`slot_num ≤ 2^31 − 1`（int32）。
- **提交点不在载体**：载体只负责写完整，提交与地址回流见[索引库 §009](index_db.md#r009)。

### 3. 三种槽形态

| 形态 | 头 160 位 | 其后 |
|---|---|---|
| 头槽 `header_slot` | `header_slot_state` + `slot_write_check` | 六个计数 `160…352` ＋ 自述区 `352…slot_size` |
| 溢出头槽 `header_slot` | `header_slot_state` + `slot_write_check` | `block_self_attr_num` `160…192` ＋ 自述区 `192…slot_size` |
| data 槽 `data_slot` | `data_slot_state` + `slot_write_check` | `data_slot_body` `160…slot_size` |

- 二选一：`slot` 行写的是 `header_slot|data_slot`，一个槽只能是其中一种形态。
- **自述区分段连续**：段 k 落在第 k 个头槽里。段容量 = 头槽 `slot_size − 352`、溢出槽 `slot_size − 192`
  （含同槽的 `block_id` 128 位）→ 实际可放属性 = 头槽 `slot_size − 480`、溢出槽 `slot_size − 320` 位。
- **自述区是一个属性字典**（KV），不是一段字节流：`block_id` 之后跟着一条条属性，每段只数**条数**
  （`block_self_attr_num`），不记位长——字典有多大由条数说了算。
- **一条条目 = `<名长:int32><名:utf-8><值长:int32><值:字节>`**（两个长度都按**字节**计）；
  名是键、**全局唯一**，落盘**按名的 utf-8 字节序升序**——同一组属性 ⇒ 同一串字节，
  `global_hash` 因此是内容确定的。
- 条目**不可分割**：放不进本槽剩余容量就**整条挪到下一个头槽开头**，本槽尾巴留 `none`。
- 为什么不能腰斩：头槽自述区前垫着固定字段，腰斩的值中间会夹进 `header_slot_state` 32 +
  `slot_write_check` 128 + `block_self_attr_num` 32 + `block_id` 128 = 320 位引擎字段，读端认不出后半截
  属于谁——等于损坏。
- **溢出头槽个数没有上限**（`header_slot_num` 是 int32）：属性放不下就往后开一个，直到放完；
  溢出槽除了那 320 位固定字段，剩下的空间全归自述区——这就是它存在的理由。
- **单条属性上限** = 溢出头槽可放容量 `slot_size − 320` 位；更大的属性进不了自述区
  （抛异常，见[索引库 §009](index_db.md#r009) 异常 1）。
- `block_id` 与 `block_self_attr_num` 在**每个头槽里各有一份**，各管各的那一段：
  `block_id` 是块的身份证（各头槽同值），`block_self_attr_num` 只数**本段**的条数。
- 溢出槽只重复这两样，不重复六个计数。
- **当地解决当地，不跨槽**：槽上的字段只描述本槽这一段；要跨段的总量（比如属性总条数）自己求和，不加字段。

| 头槽字段 | 语义 |
|---|---|
| `header_slot_num` | 头槽区槽数（≥ 1） |
| `header_slot_end` | 头槽区最后一个槽的槽 id |
| `data_slot_num` | data 槽数（可为 0） |
| `data_slot_end` | data 区最后一个槽的槽 id（即链尾） |
| `block_body_size` | 块体逻辑长度（位，不含填充） |
| `block_self_attr_num` | **本段**属性**条数**（不是位长）；总条数 = 各头槽求和 |
| `block_id` | 逻辑块 ID：uuid4，128 位 |

### 4. `slot_state`：两套体系

| 体系 | 常量 | 名称 | 含义 |
|---|---|---|---|
| `header_slot_state` | `0x9E3779B1` | `header_start` | 链首：块的第一个槽 |
| `header_slot_state` | `0x85EBCA77` | `header_mid` | 溢出槽 |
| `data_slot_state` | `0x589965CC` | `data_mid` | 普通 data 槽 |
| `data_slot_state` | `0xC2B2AE3D` | `data_end` | 链尾：最后一个 data 槽 |
| 两者共用 | `0x00000000` | `empty` | 没写过，或已删除 |

- **值属哪套体系，槽就是哪一类**：读值即知 header / data，不靠位置推理。
- 同一个 32 位字段，类型都是 `slot_state`；按形态分别叫 `header_slot_state` / `data_slot_state`。
- 五个取值两两汉明距离 ≥ 14 位；别改成相邻值。

### 5. 链

- 头槽（`header_start`）→ 溢出槽\*（`header_mid`）→ data 槽\*（末个标 `data_end`）。
- **最少只有一个头槽**：`header_slot_num = 1`、`data_slot_num = 0` 即完整块。
- 块不跨 park；一条链全在一个 park 内。
- 删除 = 把槽 `slot_state` 清成 `empty`；槽不摘、文件不缩。
- park 头六个计数（各 int32）：`slot_size` = 单个槽的位长（定长，每槽恰好这么多）；
  `slot_num` = 槽位总数（容量上界）；`slot_live` = 水线（已生成出来的槽数）；
  `slot_used` = 被活块占用的槽数；`slot_dead` = 判死、不可复用的槽数；`slot_empty` = 可复用的空槽数。
- 关系：`slot_live = slot_used + slot_dead + slot_empty`；`slot_num ≥ slot_live`，差额是**还没生成**的余量。
- **空 ≠ 死**：盘上只有 `slot_state`，`empty` 既可能是空也可能是死；空 / 死是**判定结果**，判据见
  [空洞分配 §015](alloc.md#r015)。
- 维护：四个计数同一时机、同一写者（存储引擎）——**写入时顺手更新**、**GC 定期校正**。

### 6. park 的创建与选择

写之前选 park：挑一个能写的现成 park；只有以下三种情况才新建——

1. 现有 park 被别的进程锁着；
2. 现有 park 预算（`slot_num`）已满；
3. 现有 park 坏了——**「坏了」怎么判、怎么处置，见[修复 §032](repair.md#r032)：先修，修不了才判坏**。

- 每个 park 在创建时按预算定下 `slot_num × slot_size`，此后自身不变；不同 park 可以不同。
- **缺省预算**：`slot_num = 2^20`（配缺省 `slot_size` 8192 位 = 容量 1 GiB）；调用方可上调，且必须
  `slot_num ≥ ⌈该 park 可能承载的最大块位长 / slot_size⌉`——块不跨 park，容量不够就装不下。
- 按最大对象尺寸与死淘**自适应**地调预算与分配，见[空洞分配 §014](alloc.md#r014)；格式域只给不变量与缺省。
- park 级写锁：一个 park 同时只有一个写者。
- park 名 = `hash(唯一名)` 的十六进制小写前 16 位，无意义、不绑语义；命名与分片同源，见 [hub 布局 §005](hub.md#r005)。

### 7. 写入顺序

1. 在目标 park 的**段表**（连续空槽段）上按 Best Fit 找段，见[空洞分配 §014](alloc.md#r014)。
2. 算 `slot_state` / `slot_write_check` / 各计数，写头槽。
3. 顺序写溢出槽与 data 槽；最后一个 data 槽标 `data_end`。

- 槽内不分步：一个槽一次 `pwrite` 写 `slot_size / 8` B（默认 1024 B）。
- `slot_write_check` 必须在写该槽之前算出来（写前立字据）。
- 安全性不依赖物理写序：半写态会让重算的 `check` 对不上 → 该槽判废。
- 索引行、校验、`state` 翻转、地址回流与段表更新在[索引库 §009](index_db.md#r009)，本篇不重复。

### 8. 删除

1. 先把第一个槽 `slot_state` 清成 `empty` —— 从这一刻起它不再是块。
2. 再把其余槽清成 `empty`。

- 崩在第 1 步之后：剩下的槽是孤儿，扫描时逐个清掉。
- 崩在第 1 步之前：块仍完整，幂等重做。
- **不整槽清零**：删除即状态变更，槽一旦复用就会被整槽覆盖，残留不会留存。
- 库侧删行在物理动完之后，见[索引库 §009](index_db.md#r009)。

### 9. 盲目扫描与重建

```text
id = 0
while id < slot_live:
    读槽(id)
    if slot_state == empty:                        id += 1; continue
    if slot_state == header_start 且 check 通过:
        产出该块;  id += header_slot_num + data_slot_num; continue
    if slot_state == header_start 但 check 不过:    清该槽; id += 1; continue
    否则（溢出槽 / data 槽的孤儿）:                  清该槽; id += 1
```

- 不读索引库；索引库坏了就按这条重建。
- 头槽被写坏时，它的其余槽成孤儿逐个清掉——**不追求精确回收**。

### 10. 校验规则

- 算法：XXH3-128（第三方 `xxhash`）。
- 范围：**只管本槽、不越界**——输入串 = 本槽从 `slot_state` 到槽尾的全部字节，跳过自己的 `slot_write_check`。
- 判据：重算 == 盘上存的那份。
- 块级完整性不靠它：整块的全局哈希在索引库里，见[索引库 §009](index_db.md#r009)。
- 定位：**故障守卫**，不是防篡改（128 位、且算法非加密）。

### 11. 未覆盖

以下**还没有设计**，别在本篇里找：

- GC / 归档：临时库、15 天归档包。

hub 目录布局与索引库 schema 已经另立篇：[hub 布局](hub.md)、[索引库](index_db.md)，本篇不重复。

## 待定

当前无待定项。

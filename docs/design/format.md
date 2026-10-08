<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 格式：hub / park / slot / block

> 域：内核 / 存储引擎 / 格式。对应路线图 [0.x 路线增量](../roadmap/0.x.md)。
>
> **事实依据**：[`docs/design/format`](format)——字段、位偏移、类型、取值以它为准，本文不另立、不改。
> 规范见[文档规范](../README.md)。

## <a id="r020"></a>020 格式设计：hub / park / slot / block

- 决策状态：已定（待定项见文末）

### 1. 磁盘格式

| 层 | 形态 | 定长 |
|---|---|---|
| hub | 目录（文件库） | 不定长 |
| park | 一个文件 `<唯一名>.oncat` | 定长：`slot_num × slot_size` |
| slot | park 内的定长格 | `slot_size`，默认 1024 B |
| block | 一段连续槽，不跨 park | 由头槽里的计数决定 |

- 端序小端（LE），全文一致。
- park 头 128 B：`version` / `slot_size` / `slot_num` / `slot_live` / `slot_used` / `slot_dead`。
- 槽区从偏移 1024 B 起；槽的物理偏移 `= 1024 + id × slot_size`——**位置即身份**，槽位永不摘除。

### 2. 槽状态与空槽

| `slot_state` | 值 | 含义 |
|---|---|---|
| 开始 | `0x9E3779B1` | 块的头槽，也是链首 |
| 中间 | `0x85EBCA77` | 链中任意槽：header 溢出槽 + 全部 data 槽 |
| 结束 | `0xC2B2AE3D` | 链尾；写完即提交 |
| 空 | `0` | 没写过，或已删除 |

- 一条链：头槽 → 中间槽 × N → 结束槽。
- 头 / 数据的分界不靠魔数，靠头槽里的 `header_slot_num` / `data_slot_num`。
- 删除 = 把该槽 `slot_state` 清成 0；槽不摘、文件不缩。
- 没写过的槽不存在（懒生成）：文件长度 `= 128 B + slot_live × 1024 B`。
- 关系：`slot_live = slot_used + slot_dead + 空闲`。

### 3. park 的创建与选择

写之前选 park：挑一个能写的现成 park；只有以下三种情况才新建——

1. 现有 park 被别的进程锁着；
2. 现有 park 预算（`slot_num`）已满；
3. 现有 park 坏了。

- 每个 park 在创建时按预算定下 `slot_num × slot_size`，此后自身不变；不同 park 可以不同。
- park 级写锁：一个 park 同时只有一个写者。

### 4. 写入顺序

1. 在目标 park 的空洞表上按预算找连续空槽（Best Fit）。
2. 算 `slot_state` / `check` / 各计数，写头槽。
3. 顺序写中间槽。
4. 写结束槽（`slot_state = 结束`）——**此刻提交**。
5. 提交索引行，更新空洞表。

- 槽内不分步：一个槽一次 `pwrite` 写 1024 B。
- `check` 的值必须在写该槽之前算出来（写前立字据）。
- 安全性不依赖物理写序：任何半写态都会让重算的 `check` 对不上 → 整块丢。

### 5. 删除

1. 先把头槽 `slot_state` 清成 0 —— 从这一刻起它不再是块。
2. 再把其余槽清成 0。

- 崩在第 1 步之后：剩下的槽是孤儿，扫描时逐个清掉。
- 崩在第 1 步之前：块仍完整，幂等重做。
- 只清 `slot_state`（4 B）；要不要整槽清零以防残留，见待定。

### 6. 盲目扫描与重建

```text
id = 0
while id < slot_live:
    读槽(id)
    if slot_state == 空:                      id += 1; continue
    if slot_state == 开始 且 check 通过:
        产出该块;  id += header_slot_num + data_slot_num; continue
    if slot_state == 开始 但 check 不过:       清该槽; id += 1; continue
    否则（中间 / 结束 的孤儿槽）:               清该槽; id += 1
```

- 不读索引库；索引库坏了就按这条重建。
- 头槽被写坏时，它的中间槽成孤儿逐个清掉——**不追求精确回收**。

### 7. 校验规则

- 算法：XXH3-128（第三方 `xxhash`）。
- 输入串：该槽从 `slot_state` 到槽尾的全部字节，**跳过所有 `check` 字段**，按盘上顺序拼起来。
  - data 槽：只算本槽。
  - 头槽：本槽，再拼上整个 data 区。
- 判据：重算 == 盘上存的那份。
- 定位：**故障守卫**，不是防篡改（128 位、且算法非加密）。

### 8. 未覆盖

以下三片**还没有设计**，别在本篇里找：

- hub 目录布局：`<hub>` 下有哪些文件、怎么摆。
- 索引库 schema：逻辑块 ID ↔ 物理位置的表。
- GC / 归档：`<hub>_gc` 临时库、15 天归档包。

## 待定

| # | 待定项 | 卡在哪 | 谁拍 |
|---|---|---|---|
| 1 | `slot_num` 默认取值 / 创建预算的算法 | 由最大对象尺寸与 GC 拷贝成本定 | 待定 |
| 2 | 头槽的 `check` 是否把各 data 槽的 `check` 也算进去 | 现按「跳过所有 check」写 | 待定 |
| 3 | `slot_used` / `slot_dead` 的维护时机 | 依赖死槽判定（路线 014） | 待定 |
| 4 | 删除时是否整槽清零（防残留） | 现在只清 `slot_state` | 待定 |
| 5 | park 名 16 还是 32 字符 | 只是命名，长度够即可 | 待定 |

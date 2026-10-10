<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# hub 布局：目录与多 hub

> 域：内核 / 存储引擎 / 物理结构。对应路线图 [1.x 路线增量](../roadmap/1.x.md)。
>
> **事实依据**：[`config/hub.txt`](../../config/hub.txt)——目录与命名以它为准，本文不另立、不改。
> 规范见[文档规范](../README.md)。

## <a id="r005"></a>005 hub 目录布局与多 hub

- 决策状态：已定

```text
.oncasket/                            根目录
  <hub>/                              一个 hub；可重复
    pack/<h0:2>/<h2:4>/<h0:16>.oncat  park 本体
    index/index.db                    索引库
    index/judge.db                    判定账本（可丢弃）
    gc/cache/                         15 天归档
    gc/report/<yyyy-mm-dd-nn>.json    每次归档一份报告
    gc/lock.json                      GC 锁：索引 / 归档 / 报告
    gc/gc_<yyyy-mm-dd-nn>_<hub>/      快照库：复制 pack/* + index/*
  hub.conf.json                       清单与配置（OnConf 管理）
  hub.lock.json                       容器级锁
  schema/hub.conf.json                OnConf 的词表（它自己的资产，整篇重写）
  audit.log                           OnConf 的审计留痕（append-only）
```

- **多 hub**：容器下平铺多个 hub；hub 之间不共享 park，也不共享索引库。
- **容器名是约定，不是判据**：hub 不要求落在 `.oncasket/` 里，放任意路径都能开；`root_dir` 只是缺省容器名。
  hub 的身份来自它自己的结构（`pack/**/*.oncat` + `index/index.db`）；容器那层只是多放
  `hub.conf.json` / `hub.lock.json`。
- **容器是 hub 的上一级**：`Hub(path)` 的 `path` 是 hub 目录，`hub.conf.json` 与 `hub.lock.json`
  落在它的上一级——一条路径同时说清「哪个容器、哪个 hub」（多 hub 因此不用另立容器对象）。
- **`schema/` 与 `audit.log` 是 OnConf 的落点**：清单走 OnConf（§026），词表与审计就是这套
  配置引擎自带的配套件；引擎不按自己的规矩重排它们的名字，也不去读写它们。
  锁文件是**随取随放**的，所以容器里通常看不到 `hub.lock.json`。
- **命名与分片同源**：park 名 = `hash(唯一名)` 的十六进制小写**前 16 位**；
  两级目录取同一条哈希的第 1-2 / 3-4 位——名字不绑语义、不带序。
  算法取 XXH3-128（与 `check` 同族，仓库已有 `xxhash` 依赖）。
- **扫描**：park 只认 `pack/**` 下的 `*.oncat`；`index/` 与 `gc/` 子树整体不是 park。
- **GC 区**：`gc/cache/` 放 15 天归档、`gc/report/<yyyy-mm-dd-nn>.json` 每次归档一份报告、
  `gc/lock.json` 是 GC 独占锁（罩住索引 / 归档 / 报告）；快照库 =
  `gc/gc_<yyyy-mm-dd-nn>_<hub>/`，内容是 `copy:sub_dir::pack/*` 与 `copy:sub_dir::index/*`
  ——只复制 park 与索引，不含 `gc/` 自身（账本 `judge.db` 随 `index/*` 一并复制）。
- **锁**：`hub.lock.json` 是容器级锁；park 级写锁见[格式 §6](format.md#r021)；GC 锁只管 GC 自己那三件事。
- 索引库自己的口径（表、提交时序、指纹）见[索引库 §008](index_db.md#r008)。
- **判定账本**：`index/judge.db` 是死槽判定的留痕（见[空洞分配 §015](alloc.md#r015)）——独立于索引库，
  丢了等于判定回到冷启动、不影响数据，所以它不设指纹。

## <a id="r026"></a>026 生态依赖：hub 清单/配置是否走 OnConf

- 决策状态：已定

- **走 OnConf**：`.oncasket/hub.conf.json` 是 hub 清单与配置的唯一落点。
- 引擎不另发明配置格式，也不绕过 OnConf 直接解析这个文件。
- **走的是「一个配置目录 = 一个引擎」那一档**，不是进程级单例：同一个进程要能开多个容器
  （多 hub 的底线）。读写口在 [`_hub/manifest.py`](../../src/oncasket/_hub/manifest.py)：
  每个键都以缺省值**声明**一次（文件里已有的尊重文件），取回来时**类型与取值都要过校验**
  ——静默退回缺省等于把人改错的地方藏起来。
- **OnConf 会在容器里落下自己的配套件**（词表 `schema/hub.conf.json`、审计 `audit.log`），
  那是 `home` 这个概念的产物：它们不是 hub 的结构，也不是引擎的资产，引擎不安排、不解释。
- 本期落进清单的键：`lock_timeout`（写锁等待上限，秒；缺省见公开 API §12 待定项 1）、
  `alloc_pick` / `alloc_dead`（空洞分配的策略，见[空洞分配 §014](alloc.md#r014)）。

## 待定

当前无待定项。

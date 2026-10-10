<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 变更日志

本项目的重要变更记录在此。格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。尚未发布的能力与进度见[路线图](../roadmap/1.x.md)。

本页是索引：未发布的变更写在 `[Unreleased]` 里，发布后切出去成为 `docs/CHANGELOG/<版本>.md`，
并在 `## 已发布` 里加一行。写法与维护口径见[变更日志设计](../design/changelog.md)。

## [Unreleased]

### Added

- **公开面落地：声明面 ＋ 落地面 ＋ 异常面**（[路线图 022](../roadmap/1.x.md)）：新增
  [`oncasket.api.block`](../../src/oncasket/api/block.py)（`Block` / `Ref` / `Attr` / `Body`，
  句柄 `AttrEntry` / `AttrLock`）与 [`oncasket.api.hub`](../../src/oncasket/api/hub.py)
  （`Hub` 的增删改查），连七个异常类一起进 `oncasket.api.__all__`。
  **声明面的绑定语义定死**：`block.attr.set(handle)` / `block.body.set(handle)` 是**绑定**，
  绑的是**一个纯句柄**（身份 = 持有者自己 ＋ `block_id`）——块只记住「这个区归谁管」，
  读写通道仍在句柄上；所以基于 block 建自己的数据结构时，要把 `block` 与句柄一起留成自己的
  属性，不留就没有落点。设计篇 §6 的样例按这条重写（原样例与 §5 的名字表打架）。
  拆解版（`Park` / `Packer` / `Slot`）与查询面（`AttrIndex` / `BodyIndex`）未建：
  前者是下一块，后者跟着路线 033 / 034。
- **公开面有了第一批名字：异常面冻进 `oncasket.api.__all__`**（[路线图 022](../roadmap/1.x.md)）：
  `oncasket.api` 此前 `__all__` 为空，现在把七个异常类逐个列进去并从
  [`_errors`](../../src/oncasket/_errors.py) 重导出（`OnCasketError` 与
  `SchemaMismatchError` / `SqliteTooOldError` / `NotFoundError` / `ConflictError` /
  `LockTimeoutError` / `CorruptError`）——下游终于有一条能用的 import 路径。
  名字一旦进 `__all__` 就只增不减；声明面与落地面等设计篇 §6 的三处待裁拍完再冻，
  查询面跟着路线 033 / 034。
- **改：基准点 ＋ 新值**（[路线图 035](../roadmap/1.x.md)）：[`_ops/write.py`](../../src/oncasket/_ops/write.py)
  的 `update_block` 按公开 API §8 走——先按基准点把现役那份读回来（带强校验），应用新值后
  **写前再验一次**库里的 `global_hash`：中途被别处改过就抛 `ConflictError` 并把刚占的新段放回去，
  不静默覆盖；换成功才释放旧段。库侧对应 `IndexStore.replace_content`（`WHERE … AND global_hash = ?`
  的比较并交换）。属性只覆盖点名的键，不给块体就沿用现役那份。
- **引擎最小竖切：`Hub` 打开 → 写 → 读 → 删走通**（[路线图 002](../roadmap/1.x.md) / 003 / 005 / 006 /
  007 / 009 / 014 / 026）：索引库的表读写落地（总表 ＋ `data_block` / `index_block` 两张身份分表，
  地址两列同生同灭），库侧提交动作落地（② 写 `pending` 行、⑥ `state → ok`、⑦ 地址回流），
  [`_ops/`](../../src/oncasket/_ops/) 的 session / write / read / delete 从占位变成实现——规划内容 →
  挑段（段表 ＋ `best_fit` / `first_fit` / `worst_fit`，挑不中就扩水线、再不行新建 park）→ 落槽 →
  复检 → 提交 → 地址回流；读路径「库 → 地址 → 载体 → 块 → 内容」逐槽 `check` ＋ 整块
  `global_hash` 双重验证，地址空时盲扫补地址；删除先物理（头槽清零 → 其余槽清零）后动库。
  hub 清单走 OnConf（`hub.conf.json`，键 `lock_timeout` / `alloc_pick` / `alloc_dead`），
  容器级文件锁 `hub.lock.json` 提供「等 ＋ 超时」，`_errors` 补齐 `NotFoundError` /
  `ConflictError` / `LockTimeoutError` / `CorruptError` 四个类。
- **容器目录多了 OnConf 自己的两样落点**（[路线图 026](../roadmap/1.x.md)）：清单走 OnConf 就带上它的
  词表 `schema/hub.conf.json` 与审计 `audit.log`；事实依据 [`config/hub.txt`](../../config/hub.txt)
  已按此扩充并重盖版本标记。**索引库 schema 未动**，指纹不变。
- **`global_hash` 的算法写定为 XXH3-128**（[路线图 009](../roadmap/1.x.md)）：口径原先只说「整块在载体上的
  全部字节」、没点算法；现在与槽内 `check` 同族（`xxhash` 是既有运行时依赖），落 16 B 原始输出、不翻端序。
- **公开面加一块：新增公开子包 `oncasket.api`**（[路线图 031](../roadmap/1.x.md)）：
  门面整体拆出去的那一项——[包与目录设计](../design/packages.md) §2 早写好的逃逸口，现在正式用掉。
  顶层白名单从「只有 `py.typed`」改成 `py.typed` ＋ `api/`；两条守卫同步跟着改——公开面自查
  `oncasket` 与 `oncasket.api` 两个 `__all__`，依赖分层表加上 `api`（与 `__init__` 同层、互不依赖）。
  **名字还没定**：`__all__` 为空，具体名字与签名归路线 022。

- **工程脚手架：门禁与许可**（门禁部分挂[路线图 027](../roadmap/1.x.md)；许可与版权部分无路线条目）：
  - 本地三层钩子（`pre-commit` / `commit-msg` / `pre-push`），工具一律走 `uv run`，
    清单见 [`docs/design/gate.txt`](../design/gate.txt)；
  - CI 四组作业（lint / typecheck / test × 三平台 / security），所有 action 固定到 commit SHA；
    另有 CodeQL、Dependency Review、Scorecard、Dependabot；
  - 许可与版权：Apache-2.0 的 [LICENSE](../../LICENSE) / [NOTICE](../../NOTICE)，由
    [`scripts/gen_third_party_notices.py`](../../scripts/gen_third_party_notices.py) 生成并在 CI 校验的
    [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)，全部 Python 文件带 SPDX 许可头；
  - 社区文件：[SECURITY.md](../../SECURITY.md) / [SUPPORT.md](../../SUPPORT.md) / [CONTRIBUTING.md](../../CONTRIBUTING.md) /
    [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md) / [`.github/CODEOWNERS`](../../.github/CODEOWNERS)。
- **变更日志改为一版一文件**（[路线图 030](../roadmap/1.x.md)）：根目录单文件 `CHANGELOG.md`
  换成 `docs/CHANGELOG/` 目录——`index.md` 是索引、每版一份 `<版本>.md`；
  写法与切段流程见[变更日志设计](../design/changelog.md)，结构由门禁 G20 校验。
- **包与目录骨架：公开面只有 `oncasket/__init__.py`**（[路线图 031](../roadmap/1.x.md)）：
  顶层除 `py.typed` 外一律 `_` 前缀；域子包按设计篇切分——`_hub` / `_format` / `_index` /
  `_alloc` / `_ops`（`_gc` 待 1.1.0a1）；域之间只许单向依赖，跨域流程一律进 `_ops`，
  域内模块名不对外承诺。口径与守卫见[包与目录设计](../design/packages.md)。
- **新增 `py.typed`**（[路线图 031](../roadmap/1.x.md)）：此前 classifier 声明了
  `Typing :: Typed`，但包里没有这个文件，类型检查器实际看不到任何类型标注。
- **`python -m oncasket` 可用**（[路线图 031](../roadmap/1.x.md)）：补上 `__main__.py`。
- **格式域落地：hub / park / slot / block 的位级格式与盲扫**（[路线图 021](../roadmap/1.x.md)）：
  [`src/oncasket/_format/`](../../src/oncasket/_format/) 的 `spec` / `slot` / `block` / `park` /
  `scan` 五个模块实现位偏移、三种槽形态的编解码、槽内 `check`、块链装配与解析，
  以及不读索引库的逐槽认块；事实依据 [`config/format.txt`](../../config/format.txt) 由
  `tests/format/` 逐项对着校。这是本引擎第一份落盘格式实现，此前只有占位模块。
- **索引库落地：建库生成物、schema 指纹与打开时守卫**（[路线图 008](../roadmap/1.x.md)）：
  [`config/index_db.sql`](../../config/index_db.sql) 是表结构的唯一写处，
  `scripts/gen_index_schema.py` 从它生成 [`schema_gen.py`](../../src/oncasket/_index/schema_gen.py)
  （建库 DDL ＋ 基准指纹，**增量追加**、不删旧版），门禁 G21 用 `--check` 比对；
  [`fingerprint.py`](../../src/oncasket/_index/fingerprint.py) 按表 / 索引 / 视图 / 触发器的结构算
  带盐 sha256，[`store.py`](../../src/oncasket/_index/store.py) 每次连接都比对——指纹不在本引擎声明的
  集合里就**拒绝连接并抛异常**，不降级、不静默重建；运行时 SQLite 低于 3.37（`STRICT` 与所需
  pragma 的下限）同样拒开。这是**索引库 schema 指纹**的首次落地。

### Changed

- **Python 支持范围放宽到 3.11–3.14，开发默认仍是 3.14**（[路线图 024](../roadmap/1.x.md)）：
  `requires-python` 从 `>=3.14,<3.15` 放宽到 `>=3.11,<3.15`，classifiers 补齐 3.11 / 3.12 / 3.13。
  放宽的不只是元数据：ruff 的 `target-version` 与 mypy 的 `python_version` 都降到**最低支持版本 3.11**
  （一句 3.12+ 语法就会红），CI 测试矩阵加 3.11 作业（三平台 × 3.11 / 3.14）。
  开发解释器仍是 3.14（`.python-version`），3.15 不支持。本项目尚未发布过任何版本，无迁移成本。

- **自述属性是属性字典（KV），逐段数「条数」而不是「位长」**（[路线图 021](../roadmap/1.x.md)）：
  `block_self_attr` 段内是 `block_id` ＋ 一条条属性，字段 `block_self_attr_len` 随之改名
  `block_self_attr_num`（**本段条数**，不再是位长）；一条条目 = `<名长:int32><名:utf-8><值长:int32><值:字节>`，
  名是键、**全局唯一**，落盘按名的 utf-8 字节序升序（同一组属性 ⇒ 同一串字节），条目不可分割、
  放不下就整条挪到下一个头槽。[`config/format.txt`](../../config/format.txt) 已按此扩充并重盖指纹。
  本项目尚未发布过任何版本，无迁移成本。

- **`oncasket.main` 不再是公开名字，控制台入口改指 `oncasket._cli:main`**（[路线图 031](../roadmap/1.x.md)）：
  命令名 `oncasket` 不变。本项目尚未发布过任何版本，无迁移成本。
- **运行时依赖换成 `xxhash`，去掉 `hatchling`**（[路线图 025](../roadmap/1.x.md)）：
  槽内 `check` 与 park 命名同族都用 XXH3-128，实现来自 `xxhash`——设计篇一直写着「仓库已有
  `xxhash` 依赖」，实际运行时依赖里从来没有它；`hatchling` 则是脚手架残留，构建后端是
  `uv_build`，它还一个人拖进来 5 个传递依赖（packaging / pathspec / pluggy / tomlkit /
  trove-classifiers）。重新解析后运行时依赖从 **12 个降到 7 个**，`onconf` 顺带从 `2.1.0a1`
  落到 `2.1.0`（约束是 `>=2.1.0a1`，取到正式版）。[THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)
  已按新的依赖闭包重生成。

## 已发布

<!-- 发一版加一行，最新的在最上面：- [<版本>](<版本>.md) -->

[Unreleased]: https://github.com/HanYang06/OnCasket/commits/HEAD

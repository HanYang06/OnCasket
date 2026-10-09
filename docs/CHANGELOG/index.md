<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 变更日志

本项目的重要变更记录在此。格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。尚未发布的能力与进度见[路线图](../roadmap/1.x.md)。

本页是索引：未发布的变更写在 `[Unreleased]` 里，发布后切出去成为 `docs/CHANGELOG/<版本>.md`，
并在 `## 已发布` 里加一行。写法与维护口径见[变更日志设计](../design/changelog.md)。

## [Unreleased]

### Added

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
  放宽的是**可安装范围**，不是开发口径：`.python-version`、CI 与 ruff / mypy 的目标都还是 3.14；
  3.15 不支持。本项目尚未发布过任何版本，无迁移成本。

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

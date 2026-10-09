<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 变更日志：目录、段位与门禁

> 域：工程 / 版本与发布。对应路线图 [1.x 路线增量](../roadmap/1.x.md)。
>
> **事实依据**：结构契约由 [`scripts/check_changelog.py`](../../scripts/check_changelog.py)（门禁 G20）钉死。
> 本域没有机读的配置型文件——记的是已发生的事实，不是要照抄的字段。
> 规范见[文档规范](../README.md)。

## <a id="r030"></a>030 变更日志：一版一文件与结构门禁

- 决策状态：已定（待定项见文末）

### 1. 位置与权威

- 唯一事实源是 [`docs/CHANGELOG/`](../CHANGELOG/) 目录：`index.md` 是索引，`<版本>.md` 一版一份。
- **一版一文件**：单文件会随版本数线性膨胀，按版本切分后每段独立成篇，正文互不冲突。
- 它**不在** `路线图 > 设计 > 代码` 三层里，是**记录层**：
  - 只记**已发生的事实**（哪个版本发布了什么）；
  - 不作任何设计的依据、不推翻任何层；要口径去设计篇，要计划去路线图。
- 根目录不再放 `CHANGELOG.md`（已删）；对外入口是 `index.md`，
  `pyproject.toml` 的 `[project.urls] Changelog` 指它。
- `.gitattributes` 给 `docs/CHANGELOG/index.md` 标 `merge=union`：并行分支各自追加一行不冲突。
  版本文件一版一份，天然不冲突。

### 2. 段 = tag = 一次发布

| 位置 | 是什么 |
|---|---|
| `docs/CHANGELOG/<版本>.md` | 一个 tag `v<版本>`，一次 PyPI 发布 |
| `index.md` 的 `## [Unreleased]` | 已合入、尚未发布的变更 |
| `index.md` 的 `## 已发布` | 版本文件清单，倒序，最新在上 |

- **预发布各自成段**：`1.0.0a1` / `1.0.0b1` / `1.0.0rc1` / `1.0.0` 是四份文件，不是一段——
  PyPI 的版本号不可撤回，发出去就得有记录。
- 每段只记**相对上一发布版本的增量**；正式版不重述预发布的内容，只链回上一段。
- 发布时按序做四件事：把 `[Unreleased]` 的正文切成 `docs/CHANGELOG/<版本>.md` →
  在 `## 已发布` 加一行 → 补该版本的链接引用并把 `[Unreleased]` 指向新版本 →
  抬 `pyproject.toml` 的版本并打 tag。
- **已发布段冻结**：只许改错别字与链接；口径错了靠**新版本段**纠正，不改旧段。
  与路线图「已发布写死」同构。

### 3. 长什么样

`index.md`：声明两句 → `## [Unreleased]`（正文按六类）→ `## 已发布`（清单）→ 末尾链接引用。

```markdown
## 已发布

- [1.0.0b1](1.0.0b1.md)
- [1.0.0a1](1.0.0a1.md)

[Unreleased]: https://github.com/HanYang06/OnCasket/compare/v1.0.0b1...HEAD
[1.0.0b1]: https://github.com/HanYang06/OnCasket/compare/v1.0.0a1...v1.0.0b1
[1.0.0a1]: https://github.com/HanYang06/OnCasket/compare/v1.0.0a1
```

`<版本>.md`：许可头 → `## [<版本>] - <ISO 日期>` → 六类段。

```markdown
## [1.0.0a1] - 2026-10-20

### Added

- **<变了什么、影响谁、怎么迁移>**（[路线图 001](../roadmap/1.x.md)）
```

- 段顺序固定：`Added` → `Changed` → `Deprecated` → `Removed` → `Fixed` → `Security`；空段不写。
- 不新开六类之外的段位（不做「兼容性」头行之类）；**兼容性变化写进 `### Changed` 正文**，
  破坏性条目在首句点明「破坏性」并给出迁移动作。
- 日期用 ISO（`YYYY-MM-DD`），即该版本发布日。

### 4. 什么进日志

- **进**：公开 API（路线 022）、落盘格式（hub / park / slot / block）、索引库 schema 指纹、
  依赖与 Python 支持范围、CLI 与入口、安装与发布方式、**缺陷修复**。
- **不进**：`docs` / `test` / `ci` / `chore` / `style` 类改动、外部行为不变的内部重构、
  以及**从未实现的废弃条目**——路线 018 / 019 那种既无代码也无设计的，不记。
- 路线图**只记开发路线、不记修复路线**（见[结构说明](../roadmap/README.md)），
  所以**修复类只有这里记**：这是记录层与路线图互补的那条缝。

### 5. 提交类型 → 段

| 段 | 来自的提交类型 | 判据 |
|---|---|---|
| `Added` | `feat` | 新增能力 |
| `Changed` | `refactor`、`perf`、`build`、`deps` | 仅当外部可见：签名、输出、行为、依赖或 Python 范围变了 |
| `Deprecated` | — | 宣布将要移除 |
| `Removed` | `feat!` / `refactor!` | 移除既有能力 |
| `Fixed` | `fix` | 缺陷修复 |
| `Security` | `fix` | 安全修复与漏洞通告，正文点明影响面 |
| 不进日志 | `docs`、`test`、`ci`、`chore`、`style`、`revert` | — |

### 6. 与路线图怎么接

- 能挂路线就挂：`（[路线图 001](../roadmap/1.x.md)）`；修复类与工程杂项写「无路线条目」。
- 只写路线ID——三位号全局唯一、号不复用，引用永远稳；**不复制**条目名与口径。
- 反向不动：发布不改路线图，除了「落点」的纯增量调整与勾选。

### 7. 门禁 G20

只校验**结构**，不校验内容：

1. `index.md` 在位，正文含 Keep a Changelog 与语义化版本两条声明；
2. 二级段只有 `## [Unreleased]`（且排在最先）与 `## 已发布`；
3. 版本文件名是本仓版本形态 `X.Y.Z[{a|b|rc}N]`，与文件内标题的版本号逐字一致；
4. 版本文件内 `###` 只用六类、不重复、顺序固定；
5. `## 已发布` 清单与目录里的版本文件一一对应、按版本降序，且日期随之不增；
6. 链接引用齐全：每个版本一条 `[<版本>]:`（指向 `/compare/`），
   `[Unreleased]:` 无已发布版本时指 `/commits/HEAD`、否则指 `/compare/v<最新版本>...HEAD`。

- **不查「这次改动写了日志没有」**：对 `docs` / `ci` 类改动是误伤。
- **不查 git tag**：PR 阶段 tag 还不存在，硬查会把「先合并、再在 main 上打 tag」的正常流程挡在门外
  （见待定）。
- 落点：[`scripts/check_changelog.py`](../../scripts/check_changelog.py)，默认即校验、没有写入模式；
  pre-commit（提交层）与 CI 的 lint 作业各跑一遍。

### 8. 何时写、谁写

- 平时：改动落地时往 `[Unreleased]` 追加一行；`merge=union` 让并行分支的追加并集合合并。
- 发布时：集中切段（单人项目，不在 PR 阶段强制）。
- PR 模板的自查清单里有这一项；**CI 不复核内容**——内容是人写的，机器只管结构。

## 待定

| # | 待定项 | 卡在哪 | 谁拍 |
|---|---|---|---|
| 1 | 版本文件与 git tag 的机械对应（每个 tag 必须有一份版本文件） | 挂[发布流程](gate.md)（gate.md 待定 #3）：要先有 tag 口径，且 CI 得取到 tag（`fetch-depth: 0`） | 待定 |

# AGENTS.md —— 给编码代理的项目须知

> 门禁参数的**单一事实来源**是 [`pyproject.toml`](pyproject.toml) 与
> [`.pre-commit-config.yaml`](.pre-commit-config.yaml)：本文只写流程与硬性约束，
> 不重复参数；文档写法见[文档规范](docs/README.md)。冲突时以配置文件与文档规范为准。

## 1. 项目是什么

**OnCasket** 是单机存储引擎内核。磁盘格式分物理三层：**hub**（目录）、**park**
（定长文件 `<唯一名>.oncat`）、**slot**（park 内的定长格）；逻辑块（block）是一段
**不跨 park** 的连续槽。槽位永不摘除 —— 位置即身份。

- Python `>=3.14`，依赖与虚拟环境一律用 `uv`，构建后端 `uv_build`。
- 权威顺序 **路线图 > 设计 > 代码**：路线图管「做什么、落在哪个版本」
  （[1.x](docs/roadmap/1.x.md)），设计管「口径、为什么」（[docs/design](docs/design/)，
  事实依据在 [config/](config/)），代码管实现。三层不一致时改下层；推翻上层只有两种动作：新增条目，或撤回条目的
  `决策状态`（`已定` → `待裁` / `已废弃`）。条目只增不减。

## 2. 命令

```bash
uv sync --all-groups                          # 装全部依赖（dev 组）
uv run pre-commit install                     # 装 pre-commit / commit-msg / pre-push 钩子
uv run pre-commit run --all-files             # 本地门禁（提交层）
uv run ruff check --fix .                     # lint 并自动修复
uv run ruff format .                          # 格式化
uv run mypy                                   # 严格类型检查（files = src + tests）
uv run pytest                                 # 单测
uv run pytest --cov --cov-report=term-missing # 带覆盖率（门槛 90%，见 pyproject.toml）
uv run codespell                              # 拼写
uv run bandit -c pyproject.toml -r src        # 安全静态扫描
uv run zizmor .github/workflows               # Actions 审计
uv run pip-audit                              # 依赖漏洞（需联网）
uv run python scripts/stamp_version.py -c config/*.txt docs/design/*.txt   # 版本标记校验
```

**不要**用 `pip install`，也不要绕过 `uv run` 去调 `.venv/Scripts/*.exe`
—— 工具版本唯一来源是 `uv.lock`。

## 3. 硬性约定

### 3.1 许可头 —— 漏了门禁就红

每个 Python 文件（含 `tests/`、`scripts/`）最顶部逐字写这两行，紧接着就是模块 docstring：

```python
# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
```

由 ruff 的 `CPY` 规则强制（`notice-rgx`）。顺序、`#` 后空格、年份都不能改。

仓库整体是 **Apache-2.0**：[LICENSE](LICENSE) / [NOTICE](NOTICE)。运行时依赖的许可证清单由
[`scripts/gen_third_party_notices.py`](scripts/gen_third_party_notices.py) 生成到
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)；**改了依赖必须重跑**，CI 的 `--check` 会因此变红。

### 3.2 类型与文档

- 所有函数（含私有函数）必须完整注解；测试的宽松豁免由 `pyproject.toml` 的
  per-module override 给出。
- mypy 是 `strict = true` + `warn_unreachable` + `extra_checks`。**不要**用
  `# type: ignore` 掩盖问题；万不得已要写带错误码的窄形式并就近说明原因。
- 公共 API 必须有中文 docstring（Google convention）。
- 中文标点是有意为之：`RUF001/002/003`、`D400/D415`、`EM101/102`、`TRY003` 是
  **有意豁免**，不要「顺手修好」。

### 3.3 行尾与格式

- 全仓 **LF**、UTF-8 无 BOM、文件末尾单换行（`.gitattributes` + `.editorconfig`）；
  即使本机 `core.autocrlf=true` 也不要提交 CRLF。
- 行宽 100，quote `double`，import 排序交给 `ruff check --fix`。

### 3.4 结构文件的版本标记 —— 漏盖即门禁红

带结构的 `.txt` 事实依据（`config/<域名>.txt`）首行固定两行：`encoding: … version: <sha256>`
与 `endian: little`。`version` 是内容指纹，改完必须重盖：

```bash
uv run python scripts/stamp_version.py config/format.txt   # 写入
uv run python scripts/stamp_version.py -c config/format.txt # 校验
```

### 3.5 文档

- 写法、目录、待定项、关联锚点一律照[文档规范](docs/README.md)与
  [路线图结构说明](docs/roadmap/README.md)。
- 路线图**禁止**写设计口径；设计篇**只解释事实依据**；同一事实只写一处。

## 4. 门禁

清单以 [`docs/design/gate.txt`](docs/design/gate.txt) 为唯一事实源，说明见
[`docs/design/gate.md`](docs/design/gate.md)。本地钩子是自愿的（装了才跑）；
**真正的闸在 CI**：`.github/workflows/ci.yml` 分 lint / typecheck / test（三平台）/ security。

| 层 | 触发 | 内容 |
|---|---|---|
| 提交 | `pre-commit` | 文件卫生、ruff check / format、mypy、codespell、bandit、zizmor、第三方许可清单、版本标记 |
| 推送 | `pre-push` | pytest |
| 手动 | `manual` | pip-audit（需联网） |
| CI | PR / push main | 上述全部 + markdownlint + actionlint + gitleaks + CodeQL + Dependency Review + Scorecard |

- 门禁红了不算「环境问题」，先修；确实要放宽时改的是配置，并在 PR 里说明原因。
- 不要 `git commit --no-verify`：CI 会重跑同一套检查，绕过去只是把问题推到 PR。

## 5. 提交

Conventional Commits，允许中文 subject，type 白名单见 `.pre-commit-config.yaml`；
scope 用英文小写（`format` / `engine` / `docs` / `ci`）。合并一律走 PR。

## 6. 结构速查

```text
LICENSE / NOTICE         # Apache-2.0 许可与项目归属
THIRD_PARTY_NOTICES.md   # 运行时依赖的许可证清单（自动生成，勿手改）
config/                  # 事实依据：机读配置（位级布局 .txt / schema .sql）
src/oncasket/            # 引擎实现（CLI 入口 main）
src/oncasket/format/     # 格式域：f_pack / f_block / f_slot（占位，未实现）
scripts/stamp_version.py # 结构文件版本标记（门禁 G04）
tests/                   # 门禁测试（没有 __init__.py）
docs/roadmap/            # 路线图（权威）
docs/design/             # 设计篇（口径 + 说明篇）
```

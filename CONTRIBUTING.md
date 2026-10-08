# 贡献指南

感谢你愿意为 OnCasket 花时间。本文说明本项目的协作方式、开发环境、检查流程与提交规范。

> 门禁参数的**单一事实来源**是 [`pyproject.toml`](pyproject.toml) 与
> [`.pre-commit-config.yaml`](.pre-commit-config.yaml)；本文不重复参数。
> 给编码代理的版本见 [AGENTS.md](AGENTS.md)。

## 1. 权威顺序

**路线图 > 设计 > 代码。**

| 层 | 位置 | 管什么 |
|---|---|---|
| 路线图 | [`docs/roadmap/`](docs/roadmap/) | 做什么、关联哪篇设计、落在哪个版本 |
| 设计 | [`docs/design/`](docs/design/) | 口径、为什么 |
| 代码 | `src/` | 实现 |

- 三层不一致时**改下层**；实测证明上层不成立时才改上层，而改上层只有两种动作：
  **新增条目**，或**撤回条目的 `决策状态`**（`已定` → `待裁` / `已废弃`）。
  条目只增不减、版本号只增不减。
- 文档写法见[文档规范](docs/README.md)与[路线图结构说明](docs/roadmap/README.md)。

## 2. 开发环境

```bash
uv sync --all-groups       # 装全部依赖（Python 3.14）
uv run pre-commit install  # 装 pre-commit / commit-msg / pre-push 三种钩子
```

不要用 `pip install`，也不要绕过 `uv run` 去调 `.venv/Scripts/*.exe`
—— 工具版本唯一来源是 `uv.lock`。

## 3. 检查

提交前在本地跑一遍：

```bash
uv run pre-commit run --all-files
uv run pre-commit run --all-files --hook-stage pre-push
uv run pytest --cov --cov-report=term-missing
```

完整清单（编号 G01–G19）见 [`docs/design/gate.txt`](docs/design/gate.txt)，
说明见 [`docs/design/gate.md`](docs/design/gate.md)。每一次改动都要过 CI 的四组作业；
**CI 是主门禁**，本地钩子只是省往返。

## 4. 提交规范

Conventional Commits，**允许中文 subject**，一个提交只做一件事：

- type 白名单：`feat` `fix` `docs` `refactor` `perf` `test` `build` `ci` `chore` `revert` `deps` `style`
- scope 用英文小写模块名（`format` / `engine` / `docs` / `ci`）
- subject 不超过 72 字符、结尾不加句号
- 破坏性变更在 type 后加 `!`，并在正文写一行 `BREAKING CHANGE: <说明>`
- 关联 Issue 在正文末行写 `Closes #123`

模板见 [`.gitmessage`](.gitmessage)：

```bash
git config commit.template .gitmessage
```

## 5. 许可与版权

- 仓库整体是 **Apache-2.0**：见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
- 每个 Python 文件顶部必须有两行 SPDX 许可头，由 ruff 的 `CPY` 规则强制；新增文件照抄现有文件。
- 运行时依赖的许可证清单由 [`scripts/gen_third_party_notices.py`](scripts/gen_third_party_notices.py)
  生成到 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)；**改了依赖就要重跑**，CI 的 `--check` 会因此变红。
- 中文标点是有意为之（`RUF001/002/003` 已豁免），不要「顺手修好」。

## 6. 合并方式

改动一律走「推分支 → 开 PR → 等 CI 绿 → 合并」，**不要直推 `main`**。
PR 描述按 [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) 的自查清单填写。

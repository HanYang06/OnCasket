<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 门禁：本地钩子 / CI

> 域：工程 / 门禁与测试。对应路线图 [1.x 路线增量](../roadmap/1.x.md)。
>
> **事实依据**：[`docs/design/gate.txt`](gate.txt)——门禁清单以它为准，本文不另立、不改。
> 规范见[文档规范](../README.md)。

## <a id="r027"></a>027 门禁设计：本地钩子 + CI

- 决策状态：已定（待定项见文末）

### 1. 分层

| 层 | 触发点 | 时长 | 谁跑 |
|---|---|---|---|
| 提交 | `pre-commit` | 秒级~分钟级 | 本地（装了钩子才跑） |
| 提交信息 | `commit-msg` | 毫秒级 | 本地（装了钩子才跑） |
| 推送 | `pre-push` | 分钟级 | 本地（装了钩子才跑） |
| 手动 | `manual` | 视需要（需联网） | 人 |
| CI | `pull_request` / `push` main | 全量 | 远端，绕不过 |

- 层与门禁项的对应关系只看 `gate.txt` 的 `layer` 字段。
- **工具一律走 `uv run`**：hook 用的 ruff / mypy 与 `uv.lock` 是同一个版本来源，不会分叉。
- **actionlint 与 gitleaks 只在 CI**：两者的官方 pre-commit 实现是 `language: golang`，本机没有 Go 工具链。
- **CI 不新增本地没有的口径**：CI 作业是本地层的复跑 + 只在 CI 可跑的补充项；配置只有一处（`.pre-commit-config.yaml`）。
- 本地钩子是自愿的；**真正的闸在 CI** —— 分支保护接上必需状态检查后，PR 不绿不合。

### 2. 跑

```bash
uv run pre-commit install        # 装 pre-commit / commit-msg / pre-push 三种钩子，只装一次
uv run pre-commit run --all-files
uv run pre-commit run --all-files --hook-stage pre-push
uv run pre-commit run --all-files --hook-stage manual    # pip-audit，需联网
```

### 3. 红了怎么办

| 门禁 | 处置 |
|---|---|
| G01 文件卫生 | 多数钩子自修，`git add` 后重跑 |
| G02 ruff check | `--fix` 已开，能自修的自修，剩下的手改 |
| G03 ruff format | `uv run ruff format .` 后重跑 |
| G04 版本标记 | `uv run python scripts/stamp_version.py <文件>` 重盖 |
| G05 mypy | 改类型，不拿 `# type: ignore` 糊 |
| G06 codespell | 改拼写，或把术语加进 `[tool.codespell]` 白名单 |
| G07 bandit | 改代码；确需豁免要写 `# nosec` 并说明理由 |
| G08 zizmor | 按提示固定 SHA / 收窄权限 |
| G09 第三方许可清单 | 改完依赖跑 `uv run python scripts/gen_third_party_notices.py` 重生成并提交 |
| G10 pytest | 补实现或改测试；行为变更必须带测试 |
| G12 提交信息 | 改成 `<type>(<scope>): <摘要>`，type 白名单见配置 |
| G15 覆盖率 | 补测试；门槛在 `[tool.coverage.report]` 的 `fail_under` |
| G15/G16/G18 | 看 job 日志；依赖漏洞走 `uv lock` 升级 |

### 4. 边界

- 门禁只管**能不能合**：版本号、构建产物、发布流程都不在其中。
- 覆盖率只算 `src`，`scripts/`、`tests/` 不计入。
- 本地钩子可以 `--no-verify` 绕；CI 绕不过。
- `.github/dependabot.yml` 只负责提更新 PR，**不是门禁项**；它开的 PR 照样要过 CI。
- G09 是**法律事实**，不是风格问题：依赖变了不重跑，清单就会悄悄过期，CI 必须红。

## 待定

| # | 待定项 | 卡在哪 | 谁拍 |
|---|---|---|---|
| 1 | 覆盖率门槛 90 的最终取值 | 等 `src/` 真正长大后的覆盖率基线 | 待定 |
| 2 | GitHub 必需状态检查（分支保护） | 只能用仓库设置开、不能落文件；要先在 main 上跑绿一次 | 待定 |
| 3 | 发布流程（tag → 构建 → 发布） | 相邻仓库有 release.yml，本仓尚未立设计 | 待定 |
| 4 | Issue 模板与 release-drafter | 相邻仓库有 `.github/ISSUE_TEMPLATE/` 与 `release-drafter.yml`，本仓未建 | 待定 |

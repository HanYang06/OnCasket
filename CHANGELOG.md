# 变更日志

本项目的重要变更记录在此。格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。
尚未发布的能力与进度见[路线图](docs/roadmap/1.x.md)。

## [Unreleased]

### Added

- **工程脚手架：门禁与许可**（门禁部分对应路线图 027 门禁选型；许可与版权部分尚无路线条目）：
  - 本地三层钩子（`pre-commit` / `commit-msg` / `pre-push`），工具一律走 `uv run`，
    清单见 [`docs/design/gate.txt`](docs/design/gate.txt)；
  - CI 四组作业（lint / typecheck / test × 三平台 / security），所有 action 固定到 commit SHA；
    另有 CodeQL、Dependency Review、Scorecard、Dependabot；
  - 许可与版权：Apache-2.0 的 [LICENSE](LICENSE) / [NOTICE](NOTICE)，由
    [`scripts/gen_third_party_notices.py`](scripts/gen_third_party_notices.py) 生成并在 CI 校验的
    [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，全部 Python 文件带 SPDX 许可头；
  - 社区文件：[SECURITY.md](SECURITY.md) / [SUPPORT.md](SUPPORT.md) / [CONTRIBUTING.md](CONTRIBUTING.md) /
    [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) / [`.github/CODEOWNERS`](.github/CODEOWNERS)。

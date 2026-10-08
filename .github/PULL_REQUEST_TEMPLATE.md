# 变更摘要

<!-- 一到三句话说明：这个 PR 做了什么、为什么这么做。 -->

## 关联 Issue

<!-- 例如：Closes #12 / Refs #34。没有关联 Issue 时请写「无」并说明原因。 -->

## 变更类型

<!-- 勾选所有适用项；破坏性变更请额外勾选最后一项并在下方说明迁移方式。 -->

- [ ] `feat` 新功能
- [ ] `fix` 缺陷修复
- [ ] `docs` 文档
- [ ] `refactor` 重构（不改变外部行为）
- [ ] `perf` 性能优化
- [ ] `test` 测试
- [ ] `build` 构建系统或依赖
- [ ] `ci` CI 与自动化
- [ ] `chore` 杂项
- [ ] `revert` 回滚
- [ ] **`BREAKING CHANGE` 破坏性变更**

## 自查清单

- [ ] 本地已跑过 `uv run pre-commit run --all-files`，且全部通过
- [ ] 已跑过 `uv run pytest`（涉及行为变更时另附 `uv run pytest --cov --cov-report=term-missing`）
- [ ] 已跑过 `uv run mypy`，严格模式下无告警
- [ ] 新增的函数与公共 API 都有完整类型注解与中文 docstring
- [ ] 新增源码文件已在文件顶部写 Apache-2.0 的两行 SPDX 许可头
- [ ] 新增或修改的行为都有对应测试
- [ ] 用户可见的行为变化已同步到 `docs/`（设计口径见 `docs/design/`，落点见路线图）
- [ ] 结构文件（`docs/design/*.txt`）改过就重盖了版本标记
- [ ] 本 PR 不含任何密钥、凭据、`.env` 文件
- [ ] 本 PR 不含运行时产物与构建缓存
- [ ] 所有文件保持 UTF-8 无 BOM、LF 行尾
- [ ] 提交信息符合 Conventional Commits（允许中文 subject）

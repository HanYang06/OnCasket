<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 设计篇索引

> 规矩见[文档规范](../README.md)。本页只列现有设计篇。
>
> 设计篇 = 说明篇（`<域名>.md`）+ 事实依据（`config/` 下的机读配置：位级布局 `.txt` / schema `.sql`）。

| 域 | 事实依据 | 说明篇 | 挂的路线 |
|---|---|---|---|
| 格式：hub / park / slot / block | [config/format.txt](../../config/format.txt) | [format.md](format.md) | 021 |
| 空洞分配：段 / 选择策略 / 死槽额度 | [config/format.txt](../../config/format.txt)（park 头计数）、[config/judge_db.sql](../../config/judge_db.sql)（判定账本） | [alloc.md](alloc.md) | 014, 015 |
| 索引库（数据库）：逻辑块 ID ↔ 物理位置 | [config/index_db.sql](../../config/index_db.sql) | [index_db.md](index_db.md) | 006, 008-013 |
| hub 布局：目录与多 hub | [config/hub.txt](../../config/hub.txt) | [hub.md](hub.md) | 005, 026 |
| 门禁：本地钩子 / CI | [gate.txt](gate.txt) | [gate.md](gate.md) | 027 |

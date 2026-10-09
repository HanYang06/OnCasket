# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""索引库建库 DDL 与基准指纹（**自动生成，勿手改**）。

由 `scripts/gen_index_schema.py` 从 `config/index_db.sql` 生成：改结构先改 `.sql`，
再跑生成脚本；门禁 G21 用 `--check` 比对，手改这份文件必红。

- `DDL`：`config/index_db.sql` 的逐字副本，建库时整段执行；
- `SCHEMA_FINGERPRINTS`：基准指纹集合，新版**增量追加**、不删旧版（索引库 §011）。
"""

DDL: str = """\
-- SPDX-FileCopyrightText: 2026 HanYang06
-- SPDX-License-Identifier: Apache-2.0
-- 索引库结构（事实依据）。实现照这份，不照说明篇；口径见 index_db.md §006–§013。
-- 逻辑块：总表收全量，两张身份分表由引擎原生维护。
-- 连接必开：PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;

CREATE TABLE block (
    block_id      BLOB    NOT NULL PRIMARY KEY,  -- 逻辑块 ID：16 B uuid4，与头槽自述区同一份
    created_at    INTEGER NOT NULL,              -- 创建时间：Unix 秒，UTC
    budget_slot   INTEGER NOT NULL,              -- 预算：预分配槽数
    block_size    INTEGER NOT NULL,              -- 预算：块尺寸（字节）
    global_hash   BLOB    NOT NULL,              -- 全局校验哈希：整块载体字节，不含库侧任何列
    state         TEXT    NOT NULL,              -- pending 待写入 / ok 成功 / error 错误
    park          TEXT,                          -- 逻辑地址：park 唯一名；NULL = 未回流
    first_slot_id INTEGER,                       -- 逻辑地址：首个槽 ID；NULL = 未回流
    CHECK (state IN ('pending', 'ok', 'error')),
    CHECK ((park IS NULL) = (first_slot_id IS NULL))
) STRICT;

CREATE TABLE data_block (
    block_id BLOB NOT NULL PRIMARY KEY REFERENCES block (block_id) ON DELETE CASCADE,
    kind     TEXT NOT NULL  -- 装了什么：笔记 / 视频 …（开放取值，不枚举、不加 CHECK）
) STRICT;

CREATE TABLE index_block (
    block_id BLOB NOT NULL PRIMARY KEY REFERENCES block (block_id) ON DELETE CASCADE,
    kind     TEXT NOT NULL  -- 索引了什么：属性 / title …（开放取值，不枚举、不加 CHECK）
) STRICT;

CREATE INDEX block_state ON block (state);

CREATE INDEX block_addr ON block (park, first_slot_id);
"""

SCHEMA_FINGERPRINTS: tuple[str, ...] = (
    "29245a51045454172be6297a850bea81648b69b57d5df514f0b1747765e6a454",
)

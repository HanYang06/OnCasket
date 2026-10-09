-- SPDX-FileCopyrightText: 2026 HanYang06
-- SPDX-License-Identifier: Apache-2.0
-- 判定账本结构（事实依据）。实现照这份，不照说明篇；口径见 alloc.md §015。
-- 账本记的是「过去观测到了什么」——不能从载体当前状态推出来（死与空在盘上都是 empty），所以必须落盘。
-- 但它可丢弃：丢了只是判定回到冷启动，不影响数据正确性。因此不设指纹、不做迁移，结构变了直接重建。
-- 连接必开：PRAGMA journal_mode = WAL;

CREATE TABLE slot_judge (
    park       TEXT    NOT NULL,  -- park 唯一名
    seg_start  INTEGER NOT NULL,  -- 区间起点：槽 id
    seg_len    INTEGER NOT NULL,  -- 区间长度：槽数
    misses     INTEGER NOT NULL,  -- 连续未命中轮数（证据）
    verdict    TEXT    NOT NULL,  -- empty 挑得中 / dead 判死
    first_seen INTEGER NOT NULL,  -- 首次观测：Unix 秒，UTC
    last_seen  INTEGER NOT NULL,  -- 最近一次观测：Unix 秒，UTC
    revived    INTEGER NOT NULL,  -- 复活次数（误判计数）
    PRIMARY KEY (park, seg_start),
    CHECK (verdict IN ('empty', 'dead')),
    CHECK (seg_len > 0)
) STRICT;

CREATE INDEX slot_judge_verdict ON slot_judge (verdict);

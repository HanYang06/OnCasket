# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""整块全局哈希：链上槽字节拼起来算 XXH3-128（索引库 §009 的 `global_hash`）。"""

from __future__ import annotations

import xxhash

from oncasket._format.block import assemble_block, global_hash, plan_block


def test_empty_chain_hashes_the_empty_string() -> None:
    """公开向量：先钉住算法，别混进 XXH64 或 sha256。"""
    assert global_hash([]) == xxhash.xxh3_128(b"").digest()
    assert global_hash([]).hex() == "99aa06d3014798d86001c324468d497f"


def test_hash_covers_every_slot_byte() -> None:
    plan = plan_block(block_id=b"\x01" * 16, attrs={"title": b"hi"}, body=b"body")
    slots = assemble_block(plan, first_slot_id=0)
    assert global_hash(slots) == xxhash.xxh3_128(b"".join(slots)).digest()
    assert len(global_hash(slots)) == 16


def test_hash_is_deterministic_and_order_sensitive() -> None:
    first = b"\x01" * 8
    second = b"\x02" * 8
    assert global_hash([first, second]) == global_hash([first, second])
    assert global_hash([first, second]) != global_hash([second, first])


def test_hash_follows_the_first_slot_id() -> None:
    """两个 `*_end` 字段跟着链首槽 id 走，所以同一份内容落在不同槽上哈希不同。"""
    plan = plan_block(block_id=b"\x02" * 16, body=b"payload")
    assert global_hash(assemble_block(plan, first_slot_id=0)) != global_hash(
        assemble_block(plan, first_slot_id=5)
    )

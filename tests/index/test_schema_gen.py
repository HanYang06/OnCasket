# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""生成物与事实依据一致（索引库 §011）：DDL 逐字、指纹可复算。"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from oncasket._index import fingerprint, schema_gen


SOURCE = Path(__file__).resolve().parents[2] / "config" / "index_db.sql"
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


def test_ddl_is_the_fact_source_verbatim() -> None:
    on_disk = SOURCE.read_text(encoding="utf-8")
    assert on_disk == schema_gen.DDL


def test_fingerprints_are_hex_and_unique() -> None:
    assert schema_gen.SCHEMA_FINGERPRINTS
    assert len(set(schema_gen.SCHEMA_FINGERPRINTS)) == len(schema_gen.SCHEMA_FINGERPRINTS)
    assert all(FINGERPRINT.match(item) for item in schema_gen.SCHEMA_FINGERPRINTS)


def test_the_newest_fingerprint_is_what_the_ddl_computes() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(schema_gen.DDL)
        computed = fingerprint.compute(connection)
    finally:
        connection.close()
    assert computed == schema_gen.SCHEMA_FINGERPRINTS[-1]

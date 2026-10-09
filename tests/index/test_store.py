# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""索引库连接、版本检查与指纹守卫（索引库 §008、§011–§012）。"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from oncasket._errors import SchemaMismatchError, SqliteTooOldError
from oncasket._index import schema_gen, store


if TYPE_CHECKING:
    from pathlib import Path


def test_create_lays_out_the_fact_source(tmp_path: Path) -> None:
    path = tmp_path / "index" / "index.db"
    with store.IndexStore.create(path) as opened:
        assert opened.path == path
        assert opened.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert opened.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        names = {
            row[0]
            for row in opened.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"block", "data_block", "index_block"} <= names


def test_create_makes_missing_parents(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "index" / "index.db"
    store.IndexStore.create(path).close()
    assert path.is_file()


def test_load_accepts_a_fresh_library(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    store.IndexStore.create(path).close()
    with store.IndexStore.load(path) as opened:
        assert opened.connection.execute("SELECT count(*) FROM block").fetchone()[0] == 0


def test_load_refuses_a_missing_library(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        store.IndexStore.load(tmp_path / "nope.db")


def test_load_refuses_a_changed_schema(tmp_path: Path) -> None:
    path = tmp_path / "index.db"
    with store.IndexStore.create(path) as opened:
        opened.connection.execute("ALTER TABLE block ADD COLUMN extra TEXT")
        opened.connection.commit()
    with pytest.raises(SchemaMismatchError):
        store.IndexStore.load(path)


def test_load_refuses_a_library_whose_fingerprint_is_not_declared(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    path.write_bytes(b"")
    with pytest.raises(SchemaMismatchError):
        store.IndexStore.load(path)


def test_load_refuses_a_file_that_is_not_a_library(tmp_path: Path) -> None:
    path = tmp_path / "garbage.db"
    path.write_bytes(b"not a sqlite database" * 8)
    with pytest.raises(sqlite3.DatabaseError):
        store.IndexStore.load(path)


def test_create_refuses_a_stale_generated_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schema_gen, "SCHEMA_FINGERPRINTS", ())
    with pytest.raises(SchemaMismatchError):
        store.IndexStore.create(tmp_path / "index.db")


def test_create_surfaces_sqlite_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(schema_gen, "DDL", "CREATE TABLE oops (")
    with pytest.raises(sqlite3.Error):
        store.IndexStore.create(tmp_path / "index.db")


def test_a_too_old_sqlite_is_refused(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "index.db"
    store.IndexStore.create(path).close()
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 36, 0))
    with pytest.raises(SqliteTooOldError):
        store.IndexStore.create(tmp_path / "other.db")
    with pytest.raises(SqliteTooOldError):
        store.IndexStore.load(path)

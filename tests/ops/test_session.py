# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""打开 hub：目录树、索引库、清单与写锁口，幂等建开（路线 005/026/036、索引库 §011–012）。"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

from oncasket._errors import LockTimeoutError, SchemaMismatchError
from oncasket._hub import layout
from oncasket._ops import read as read_module
from oncasket._ops import write as write_module
from oncasket._ops.session import HubSession


if TYPE_CHECKING:
    from pathlib import Path


def open_hub(tmp_path: Path) -> HubSession:
    return HubSession.open(tmp_path / "hub")


def test_open_builds_the_directory_tree_and_the_index(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        assert hub.path == (tmp_path / "hub").resolve()
        assert hub.name == "hub"
        assert (hub.path / "pack").is_dir()
        assert hub.paths.index_db.is_file()
        assert hub.container.root == hub.path.parent
        assert hub.manifest.path.is_file()


def test_park_path_shards_the_name(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        name = layout.park_name("hello")
        path = hub.park_path(name)
        assert path == hub.paths.pack / "b5" / "e9" / f"{name}.oncat"


def test_write_lock_points_at_the_container_lock(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        lock = hub.write_lock()
        assert lock.path == hub.container.lock
        with lock:
            assert lock.held
        assert not lock.held


def test_open_is_idempotent_and_data_survives_a_reopen(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        block_id = write_module.write_block(hub, body=b"persist")
    with HubSession.open(tmp_path / "hub") as reopened:
        assert read_module.read_block(reopened, block_id).body == b"persist"


def test_a_foreign_index_db_is_refused(tmp_path: Path) -> None:
    hub = tmp_path / "hub"
    (hub / "index").mkdir(parents=True)
    with closing(sqlite3.connect(hub / "index" / "index.db")) as connection:
        connection.execute("CREATE TABLE block (block_id BLOB NOT NULL PRIMARY KEY) STRICT")
        connection.commit()
    with pytest.raises(SchemaMismatchError, match="拒绝连接"):
        HubSession.open(hub)


def test_the_context_manager_closes_the_store(tmp_path: Path) -> None:
    with open_hub(tmp_path) as hub:
        store = hub.store
    with pytest.raises(sqlite3.ProgrammingError):
        store.connection.execute("SELECT 1")


def test_close_is_idempotent(tmp_path: Path) -> None:
    hub = open_hub(tmp_path)
    hub.close()
    hub.close()


def test_the_manifest_timeout_reaches_the_lock(tmp_path: Path) -> None:
    container = tmp_path / "hub"
    container.mkdir()
    (container.parent / "hub.conf.json").write_text('{"lock_timeout": 0.25}', encoding="utf-8")
    with open_hub(tmp_path) as hub:
        started = time.monotonic()
        with hub.write_lock(), pytest.raises(LockTimeoutError):
            hub.write_lock().acquire()
        assert time.monotonic() - started >= 0.25

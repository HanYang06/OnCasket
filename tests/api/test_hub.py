# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""公开面走一遍：`oncasket.api` 的 `Hub` 增删改查（公开 API §8、§12）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from oncasket import api
from oncasket.api import Attr, Block, Body, ConflictError, Hub, NotFoundError, OnCasketError, Ref


if TYPE_CHECKING:
    from pathlib import Path


class Note:
    """下游自己的数据结构：留着 block 与两个句柄（§6 的约定）。"""

    def __init__(self) -> None:
        """建结构：block 与两个句柄都留成自己的属性。"""
        self.block = Block(self)
        self.block.kind = "note"
        self.attr = self.block.attr.set(Attr(self, self.block.id))
        self.body = self.block.body.set(Body(self, self.block.id))


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        note = Note()
        note.attr.add("title", "我的笔记")
        note.body.write(b"hello, world")
        block_id = hub.write(note.block)

        back = hub.read(block_id)
        assert isinstance(back, Block)
        assert back.id == block_id
        assert back.attr.items() == {"title": "我的笔记".encode()}
        assert back.body.item() == b"hello, world"
        assert back.owner is None


def test_ref_round_trips_through_the_read(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        block = Block()
        block.ref.set(Ref.data)
        block.body.write(b"payload")
        block_id = hub.write(block)
        assert hub.read(block_id).ref.get() == "data"


def test_a_block_without_a_ref_is_written_as_data(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        block = Block()
        block.body.write(b"payload")
        block_id = hub.write(block)
        row = hub.read(block_id)
        assert row.ref.get() == ""
        assert hub.read(block_id).body.item() == b"payload"


def test_an_index_role_lands_in_the_index_table(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        block = Block()
        block.ref.set(Ref.index)
        block.body.write(b'{"attr": []}')
        hub.write(block)
        kinds = hub._session.store.connection.execute("SELECT block_id FROM index_block").fetchall()
        assert len(kinds) == 1


def test_the_kind_of_the_block_reaches_the_identity_table(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        note = Note()
        note.body.write(b"x")
        block_id = hub.write(note.block)
        kind = hub._session.store.connection.execute(
            "SELECT kind FROM data_block WHERE block_id = ?", (block_id,)
        ).fetchone()
        assert kind["kind"] == "note"


def test_update_changes_attrs_and_body(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        note = Note()
        note.attr.add("title", b"old")
        note.body.write(b"old body")
        block_id = hub.write(note.block)

        hub.update(block_id, attr={"title": "new"})
        assert hub.read(block_id).attr.get("title").item() == b"new"
        assert hub.read(block_id).body.item() == b"old body"

        hub.update(block_id, body=b"new body")
        assert hub.read(block_id).body.item() == b"new body"
        assert hub.read(block_id).attr.get("title").item() == b"new"


def test_delete_removes_the_block(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        block = Block()
        block.body.write(b"bye")
        block_id = hub.write(block)
        hub.delete(block_id)
        with pytest.raises(NotFoundError):
            hub.read(block_id)


def test_read_of_an_unknown_id_is_not_found(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub, pytest.raises(NotFoundError):
        hub.read(b"\x00" * 16)


def test_delete_of_an_unknown_id_is_not_found(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub, pytest.raises(NotFoundError):
        hub.delete(b"\x00" * 16)


def test_update_of_an_unknown_id_is_not_found(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub, pytest.raises(NotFoundError):
        hub.update(b"\x00" * 16, body=b"nope")


def test_a_pending_block_cannot_be_read(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        block = Block()
        block.body.write(b"x")
        block_id = hub.write(block)
        with hub._session.store.connection:
            hub._session.store.connection.execute(
                "UPDATE block SET state = 'pending' WHERE block_id = ?", (block_id,)
            )
        with pytest.raises(OnCasketError, match="pending"):
            hub.read(block_id)


def test_reopening_the_hub_keeps_the_data(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        block = Block()
        block.body.write(b"persist")
        block_id = hub.write(block)
    with Hub(tmp_path / "hub") as reopened:
        assert reopened.read(block_id).body.item() == b"persist"


def test_hub_path_is_resolved(tmp_path: Path) -> None:
    with Hub(tmp_path / "hub") as hub:
        assert hub.path == (tmp_path / "hub").resolve()


def test_the_exception_face_is_importable_from_the_public_module() -> None:
    for name in api.__all__:
        assert isinstance(getattr(api, name), type)
    assert issubclass(ConflictError, Exception)


def test_a_hub_takes_a_string_path(tmp_path: Path) -> None:
    with Hub(str(tmp_path / "hub")) as hub:
        block = Block()
        block.body.write(b"x")
        assert len(hub.write(block)) == 16

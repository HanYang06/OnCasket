# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""声明面：`Block` / `Ref` / `Attr` / `Body`——纯内存 ＋ **绑定句柄**的约定（公开 API §6）。"""

from __future__ import annotations

import pytest

from oncasket.api.block import REF_KEY, Attr, AttrEntry, AttrLock, Block, Body, Ref


class Notebook:
    """「基于 block 创建的数据结构」：把 block 与两个句柄都留成自己的属性。"""

    def __init__(self) -> None:
        """建结构：block 与两个句柄都留成自己的属性。"""
        self.block = Block(self)
        self.attr = self.block.attr.set(Attr(self, self.block.id))
        self.body = self.block.body.set(Body(self, self.block.id))


def test_block_comes_with_an_id_and_keeps_its_owner() -> None:
    owner = Notebook()
    assert len(owner.block.id) == 16
    assert owner.block.owner is owner
    assert owner.block.id != Block().id


def test_the_convention_binds_handles_that_point_at_the_same_data() -> None:
    """绑定之后，块上那份与留着的句柄动的是**同一份**东西。"""
    owner = Notebook()
    assert owner.block.attr.owner is owner
    assert owner.block.attr.block_id == owner.block.id
    assert isinstance(owner.attr, Attr)
    assert isinstance(owner.body, Body)

    owner.attr.add("title", b"from handle")
    assert owner.block.attr.items() == {"title": b"from handle"}

    owner.block.attr.add("note", b"from block")
    assert owner.attr.items() == {"title": b"from handle", "note": b"from block"}

    owner.body.write(b"body from handle")
    assert owner.block.body.item() == b"body from handle"


def test_set_returns_the_same_handle() -> None:
    block = Block()
    attr = Attr(None, block.id)
    body = Body(None, block.id)
    assert block.attr.set(attr) is attr
    assert block.body.set(body) is body


def test_an_entry_handle_reads_and_writes() -> None:
    block = Block()
    title = block.attr.add("title", "未命名")
    assert isinstance(title, AttrEntry)
    assert title.name == "title"
    assert title.item() == "未命名".encode()
    title.set(b"Hello,World")
    assert block.attr.get("title").item() == b"Hello,World"
    assert title.owner is None
    assert title.block_id == block.id


def test_add_overwrites_the_same_name() -> None:
    block = Block()
    block.attr.add("title", b"first")
    block.attr.add("title", b"second")
    assert block.attr.items() == {"title": b"second"}


def test_an_empty_name_is_rejected() -> None:
    block = Block()
    with pytest.raises(ValueError, match="属性名不能为空"):
        block.attr.add("", b"x")


def test_get_of_a_missing_name_is_a_key_error() -> None:
    block = Block()
    with pytest.raises(KeyError):
        block.attr.get("nope")


def test_lock_all_freezes_the_whole_area() -> None:
    block = Block()
    entry = block.attr.add("title", b"x")
    assert isinstance(block.attr.lock, AttrLock)
    block.attr.lock.all()
    assert block.attr.locked
    assert entry.locked
    with pytest.raises(ValueError, match="已经锁定"):
        block.attr.add("other", b"y")
    with pytest.raises(ValueError, match="已经锁定"):
        entry.set(b"z")


def test_lock_item_freezes_one_entry_only() -> None:
    block = Block()
    frozen = block.attr.add("title", b"x")
    free = block.attr.add("note", b"y")
    block.attr.lock.item("title")
    assert frozen.locked
    assert not free.locked
    with pytest.raises(ValueError, match="已经锁定"):
        frozen.set(b"z")
    free.set(b"z")
    assert block.attr.items() == {"title": b"x", "note": b"z"}


def test_body_locks_after_writing() -> None:
    block = Block()
    block.body.write(b"first")  # 还没锁：写得进去
    assert block.body.lock() is block.body
    with pytest.raises(ValueError, match="块体已经锁定"):
        block.body.write(b"second")
    assert block.body.item() == b"first"
    assert block.body.locked is True


def test_ref_defaults_to_empty_and_takes_premade_values() -> None:
    block = Block()
    assert block.ref.get() == ""
    block.ref.set(Ref.data)
    assert block.ref.get() == "data"
    assert Ref.data == "data"
    assert Ref.index == "index"
    block.ref.set(Ref(Ref.index))
    assert block.ref.get() == "index"
    assert Ref("custom").get() == "custom"


def test_attributes_merges_ref_as_a_built_in_property() -> None:
    block = Block()
    assert block.attributes() == {}
    block.ref.set(Ref.data)
    block.attr.add("title", b"x")
    assert block.attributes() == {REF_KEY: b"data", "title": b"x"}


def test_a_bound_handle_wins_over_the_blocks_own() -> None:
    block = Block()
    block.attr.add("own", b"1")
    other = Attr("someone", block.id)
    other.add("theirs", b"2")
    block.attr.set(other)
    assert block.attr.items() == {"theirs": b"2"}
    assert other.items() == {"theirs": b"2"}
    block.body.set(Body("someone", block.id))
    block.body.write(b"bound")
    assert block.body.item() == b"bound"

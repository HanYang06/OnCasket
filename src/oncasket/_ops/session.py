# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""打开 hub：清单 → 索引库 → 指纹守卫 → 句柄（索引库 §011–012）。

**路径怎么念**：`Hub(path)` 的 `path` 是 **hub 目录**（`pack/` 与 `index/` 的父目录），
容器就是它的上一级——`hub.conf.json` 与 `hub.lock.json` 落在容器那层
（hub 布局 §005：多 hub 平铺在容器下，hub 之间不共享 park，也不共享索引库）。

**打开是幂等的**：目录不在就建（`pack/` ＋ `index/`），索引库不在就按事实依据建，
清单缺什么补什么。「已存在就打开，不存在就建」是默认那条腿，把建与开拆成两步只会让
常用路径变长。

**指纹守卫在开库那一刻**：`IndexStore.load` 每次连接都比对结构指纹——不在本引擎声明的
集合里就拒绝连接、抛 `SchemaMismatchError`，不降级、不静默重建（§012）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from oncasket._hub.layout import ContainerPaths, HubPaths, park_relative_path
from oncasket._hub.lock import FileLock
from oncasket._hub.manifest import Manifest
from oncasket._index.store import IndexStore


if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True)
class HubSession:
    """一个开着的 hub：路径、清单、索引库与「拿写锁」的口。"""

    path: Path
    paths: HubPaths
    container: ContainerPaths
    manifest: Manifest
    store: IndexStore

    @classmethod
    def open(cls, path: Path) -> HubSession:
        """打开（必要时建）一个 hub。

        Args:
            path: hub 目录；相对路径按当前工作目录解析。

        Returns:
            开着的会话。

        Raises:
            SchemaMismatchError: 索引库指纹不在本引擎声明的集合里——拒开，不降级、不重建。
            SqliteTooOldError: 运行时 SQLite 低于结构所需下限。
        """
        hub = path.resolve()
        paths = HubPaths(hub)
        container = ContainerPaths(hub.parent)
        paths.pack.mkdir(parents=True, exist_ok=True)
        paths.index_db.parent.mkdir(parents=True, exist_ok=True)
        manifest = Manifest.open(container.root)
        store = (
            IndexStore.load(paths.index_db)
            if paths.index_db.is_file()
            else IndexStore.create(paths.index_db)
        )
        return cls(path=hub, paths=paths, container=container, manifest=manifest, store=store)

    @property
    def name(self) -> str:
        """Hub 名：目录名（身份来自结构，名字只是落点）。"""
        return self.path.name

    def park_path(self, name: str) -> Path:
        """Park 名 → 本体路径。

        **名字自带分片**：分片位就是同一条哈希的第 1-2 / 3-4 位，所以拿到名字不必再算哈希，
        也就不是「拿唯一名换路径」那条路（那条见 `layout.park_path`）。

        Args:
            name: 16 位十六进制小写的 park 名。

        Returns:
            `<hub>/pack/<h0:2>/<h2:4>/<name>.oncat`。
        """
        return self.paths.pack / park_relative_path(name)

    def write_lock(self) -> FileLock:
        """拿写锁要用的那把锁：容器级 `hub.lock.json`，等待上限取清单里的配置。

        粒度说明：格式 §6 的写锁是**载体级**（一个 park 同时只有一个写者），而事实依据
        `config/hub.txt` 只给了容器级那一把锁的落点。本期先用容器级锁串行写者——
        方向一致（读者随便读、写者串行），粒度比设计粗；载体级锁的落点定了再收细。

        Returns:
            还没取的一把锁（`with session.write_lock():` 才真取）。
        """
        return FileLock(self.container.lock, timeout=self.manifest.lock_timeout())

    def close(self) -> None:
        """关掉库连接与清单，幂等。"""
        self.store.close()
        self.manifest.close()

    def __enter__(self) -> HubSession:
        """进上下文。

        Returns:
            自己。
        """
        return self

    def __exit__(self, *args: object) -> None:
        """出上下文就关。

        Args:
            *args: 异常三元组，这里不关心。
        """
        self.close()

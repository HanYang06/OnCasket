# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""hub 布局：容器、hub 与 park 的分片路径（照 `config/hub.txt`）。

事实依据是 `config/hub.txt`：改目录先改 `.txt`、重盖版本标记，再改这里；
`tests/hub/test_layout.py` 会拿 `.txt` 里的段名逐项对一遍。

- **容器**：平铺若干 hub，外加清单 `hub.conf.json` 与容器锁 `hub.lock.json`；
  缺省名 `.oncasket`，**但名字只是约定**——hub 放任意路径都能开
  （[hub 布局 §005](../../../docs/design/hub.md)）。
- **hub**：一个目录，`pack/` 放 park 本体、`index/` 放索引库与判定账本、`gc/` 放归档。
- **park 名**：`XXH3-128(唯一名)` 的十六进制小写**前 16 位**；两级分片取同一条
  哈希的第 1-2 / 3-4 位，文件名用满 16 位——**名字不绑语义、不带序**。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import xxhash


#: 缺省容器名（事实依据里的 `root_dir`）；只是约定，判据在 hub 自己的结构里
DEFAULT_CONTAINER = ".oncasket"
#: park 本体的后缀
PARK_SUFFIX = ".oncat"
#: park 名取哈希的前多少位十六进制
PARK_NAME_HEX = 16
#: 两级分片取哈希的第 1-2 / 3-4 位
SHARD_1 = (0, 2)
SHARD_2 = (2, 4)

PACK_DIR = "pack"
INDEX_DIR = "index"
GC_DIR = "gc"

_PARK_NAME = re.compile(rf"^[0-9a-f]{{{PARK_NAME_HEX}}}$")


def park_name(unique_name: str) -> str:
    """算 park 名：`XXH3-128(唯一名)` 的十六进制小写前 16 位。

    Args:
        unique_name: 唯一名，按 utf-8 入哈希。

    Returns:
        16 位十六进制小写。
    """
    return xxhash.xxh3_128(unique_name.encode("utf-8")).hexdigest()[:PARK_NAME_HEX]


def check_park_name(name: str) -> None:
    """校验一个 park 名。

    Args:
        name: park 名。

    Raises:
        ValueError: 不是 16 位十六进制小写。
    """
    if not _PARK_NAME.match(name):
        raise ValueError(f"park 名应是 {PARK_NAME_HEX} 位十六进制小写，实际 {name!r}")


def park_relative_path(name: str) -> Path:
    """把 park 名切成相对 `pack/` 的分片路径。

    Args:
        name: park 名。

    Returns:
        `<h0:2>/<h2:4>/<h0:16>.oncat`。

    Raises:
        ValueError: park 名不合法。
    """
    check_park_name(name)
    outer = name[SHARD_1[0] : SHARD_1[1]]
    inner = name[SHARD_2[0] : SHARD_2[1]]
    return Path(outer) / inner / f"{name}{PARK_SUFFIX}"


def park_path(hub: Path, unique_name: str) -> Path:
    """唯一名 → park 本体的路径。

    Args:
        hub: hub 目录。
        unique_name: 唯一名。

    Returns:
        `<hub>/pack/<h0:2>/<h2:4>/<h0:16>.oncat`。
    """
    return hub / PACK_DIR / park_relative_path(park_name(unique_name))


def find_parks(hub: Path) -> list[Path]:
    """列出一个 hub 里的 park 本体。

    只认 `pack/**` 下**名字合形态**的 `*.oncat`：`index/` 与 `gc/` 整体不是 park，
    名字不是哈希的杂项文件也不算（hub 布局 §005）。

    Args:
        hub: hub 目录。

    Returns:
        排好序的 park 路径；目录不在就是空表。
    """
    found = (hub / PACK_DIR).glob(f"*/*/*{PARK_SUFFIX}")
    return sorted(path for path in found if _PARK_NAME.match(path.stem))


@dataclass(frozen=True, slots=True)
class HubPaths:
    """一个 hub 目录下的固定落点（事实依据里的 `sub_dir`）。"""

    hub: Path

    @property
    def pack(self) -> Path:
        """放 park 本体的 `pack/`。"""
        return self.hub / PACK_DIR

    @property
    def index_db(self) -> Path:
        """索引库 `index/index.db`。"""
        return self.hub / INDEX_DIR / "index.db"

    @property
    def judge_db(self) -> Path:
        """判定账本 `index/judge.db`（可丢弃，不设指纹）。"""
        return self.hub / INDEX_DIR / "judge.db"

    @property
    def gc(self) -> Path:
        """归档区 `gc/`。"""
        return self.hub / GC_DIR

    @property
    def gc_cache(self) -> Path:
        """15 天归档 `gc/cache/`。"""
        return self.gc / "cache"

    @property
    def gc_report(self) -> Path:
        """归档报告 `gc/report/`，每次归档一份 JSON。"""
        return self.gc / "report"

    @property
    def gc_lock(self) -> Path:
        """GC 独占锁 `gc/lock.json`。"""
        return self.gc / "lock.json"


@dataclass(frozen=True, slots=True)
class ContainerPaths:
    """一个容器：平铺若干 hub，外加清单与容器锁。"""

    root: Path

    @property
    def manifest(self) -> Path:
        """清单与配置 `hub.conf.json`（走 OnConf）。"""
        return self.root / "hub.conf.json"

    @property
    def lock(self) -> Path:
        """容器级锁 `hub.lock.json`。"""
        return self.root / "hub.lock.json"

    def hub(self, name: str) -> Path:
        """容器下一个 hub 的目录。

        Args:
            name: hub 目录名。

        Returns:
            `<容器>/<name>`。
        """
        return self.root / name

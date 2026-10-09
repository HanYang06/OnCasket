# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""hub 布局：park 命名与分片、hub 与容器的落点，以及对着 `config/hub.txt` 的一致性。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from oncasket._hub import layout


ROOT = Path(__file__).resolve().parent.parent.parent
FACT = ROOT / "config" / "hub.txt"


def fact_sections() -> tuple[str, dict[str, list[str]]]:
    """把 `hub.txt` 拆成根名与各 `sub_dir` 的条目名。

    跳过空行、`#` 注释与 `copy:` 行（那是「整段复制」，不是落点）。

    Returns:
        (根名, {段名: [条目, …]})。
    """
    root = ""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in FACT.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("root_dir:"):
            root = line.split(":", 1)[1].strip()
            continue
        if line.startswith("sub_dir:"):
            current = line.split(":", 1)[1].strip()
            sections[current] = []
            continue
        if current is None or line.lstrip().startswith("copy:"):
            continue
        sections[current].append(line.strip().removesuffix("/"))
    return root, sections


def test_root_dir_is_the_default_container() -> None:
    root, _ = fact_sections()
    assert root == layout.DEFAULT_CONTAINER
    container = layout.ContainerPaths(Path("/c"))
    assert container.hub("a").as_posix() == "/c/a"
    assert container.manifest.as_posix() == "/c/hub.conf.json"
    assert container.lock.as_posix() == "/c/hub.lock.json"


def test_park_name_is_sixteen_lowercase_hex() -> None:
    name = layout.park_name("hello")
    assert name == "b5e9c1ad071b3e7f"  # 黄金向量：锁住「哈希输入是 utf-8 的唯一名」
    assert re.fullmatch(r"[0-9a-f]{16}", name)
    assert layout.park_name("note-001") == "8b58f03c92ee9874"
    assert layout.park_name("hello") == name  # 确定性：同名同命


def test_park_name_ignores_semantics() -> None:
    assert layout.park_name("笔记") != layout.park_name("笔记2")


def test_check_park_name() -> None:
    layout.check_park_name("0123456789abcdef")
    for bad in ("0123456789ABCDEF", "0123456789abcde", "0123456789abcdeg", ""):
        with pytest.raises(ValueError, match="park 名应是"):
            layout.check_park_name(bad)


def test_park_relative_path_shards_the_same_hash() -> None:
    path = layout.park_relative_path("b5e9c1ad071b3e7f")
    assert path.as_posix() == "b5/e9/b5e9c1ad071b3e7f.oncat"
    assert path.name == f"b5e9c1ad071b3e7f{layout.PARK_SUFFIX}"


def test_park_relative_path_rejects_a_bad_name() -> None:
    with pytest.raises(ValueError, match="park 名应是"):
        layout.park_relative_path("nope")


def test_park_path_hangs_under_pack() -> None:
    hub = Path("/h")
    assert layout.park_path(hub, "hello").as_posix() == "/h/pack/b5/e9/b5e9c1ad071b3e7f.oncat"


def test_fact_declares_the_same_dirs() -> None:
    _, sections = fact_sections()
    assert set(sections) == {"pack", "index", "gc"}
    paths = layout.HubPaths(Path("/h"))
    assert paths.pack.name == "pack"
    assert paths.index_db.as_posix() == "/h/index/index.db"
    assert paths.judge_db.as_posix() == "/h/index/judge.db"
    assert [paths.gc_cache.name, paths.gc_report.name, paths.gc_lock.name] == [
        "cache",
        "report",
        "lock.json",
    ]
    assert sorted(sections["index"]) == ["index.db", "judge.db"]
    assert {"cache", "report", "lock.json"} <= set(sections["gc"])


def test_fact_pins_the_shard_templates() -> None:
    """分片形状由事实依据写死：`<h0:2>` / `<h2:4>` / `<h0:16>.oncat`。"""
    _, sections = fact_sections()
    outer, inner, leaf = sections["pack"]
    assert (outer, inner) == (f"<h0:{layout.SHARD_1[1]}>", f"<h2:{layout.SHARD_2[1]}>")
    assert leaf == f"<h0:{layout.PARK_NAME_HEX}>{layout.PARK_SUFFIX}"
    assert layout.SHARD_1[1] - layout.SHARD_1[0] == 2
    assert layout.SHARD_2[1] - layout.SHARD_2[0] == 2


def test_find_parks_only_takes_well_formed_oncat(tmp_path: Path) -> None:
    pack = tmp_path / layout.PACK_DIR
    good = layout.park_relative_path(layout.park_name("a"))
    second = layout.park_relative_path(layout.park_name("b"))
    for relative in (good, second):
        path = pack / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    junk = pack / "zz" / "zz" / "notahash.oncat"
    junk.parent.mkdir(parents=True, exist_ok=True)
    junk.write_bytes(b"x")
    stray = pack / "b5" / "e9" / "stray.txt"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"x")
    (tmp_path / layout.INDEX_DIR).mkdir()
    (tmp_path / layout.INDEX_DIR / "index.db").write_bytes(b"x")

    assert layout.find_parks(tmp_path) == sorted([pack / good, pack / second])


def test_find_parks_on_a_missing_pack_is_empty(tmp_path: Path) -> None:
    assert layout.find_parks(tmp_path / "nope") == []

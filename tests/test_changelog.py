# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""门禁 G20（变更日志结构）的测试：先铺一份合法布局，再逐条破坏。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent

DECLARATION = (
    "格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，"
    "版本号遵循[语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。"
)


def load_checker() -> ModuleType:
    """按路径加载 `scripts/check_changelog.py`：它不是包，没有可导入的名字。

    Returns:
        已执行的模块对象。
    """
    path = REPO_ROOT / "scripts" / "check_changelog.py"
    spec = importlib.util.spec_from_file_location("check_changelog", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_changelog"] = module
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


def version_text(
    version: str,
    day: str = "2026-10-20",
    sections: tuple[str, ...] = ("Added",),
) -> str:
    """造一份合法的版本文件正文。

    Args:
        version: 版本号。
        day: 发布日。
        sections: 段名序列。

    Returns:
        版本文件全文。
    """
    lines = [f"## [{version}] - {day}", ""]
    for name in sections:
        lines += [f"### {name}", "", "- 占位。", ""]
    return "\n".join(lines)


def index_text(versions: tuple[str, ...] = ()) -> str:
    """造一份合法的 `index.md` 正文。

    Args:
        versions: 已发布版本号，按降序。

    Returns:
        索引全文。
    """
    lines = [
        DECLARATION,
        "",
        "## [Unreleased]",
        "",
        "### Added",
        "",
        "- 占位。",
        "",
        "## 已发布",
        "",
    ]
    lines += [f"- [{version}]({version}.md)" for version in versions]
    if versions:
        lines.append(f"[Unreleased]: {CHECKER.REPO_URL}/compare/v{versions[0]}...HEAD")
    else:
        lines.append(f"[Unreleased]: {CHECKER.REPO_URL}/commits/HEAD")
    lines += [f"[{version}]: {CHECKER.REPO_URL}/compare/v{version}" for version in versions]
    return "\n".join(lines) + "\n"


def build(root: Path, versions: tuple[str, ...] = (), days: tuple[str, ...] = ()) -> None:
    """按合法形态铺一份变更日志目录。

    Args:
        root: 变更日志目录。
        versions: 已发布版本号，按降序。
        days: 与 `versions` 一一对应的发布日。
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.md").write_text(index_text(versions), encoding="utf-8")
    for version, day in zip(versions, days, strict=True):
        (root / f"{version}.md").write_text(version_text(version, day), encoding="utf-8")


def rewrite(path: Path, text: str) -> None:
    """覆写一个文件。

    Args:
        path: 目标路径。
        text: 新内容。
    """
    path.write_text(text, encoding="utf-8")


def test_repo_layout_is_valid() -> None:
    assert CHECKER.check(REPO_ROOT / "docs" / "CHANGELOG") == []


def test_empty_layout_passes(tmp_path: Path) -> None:
    build(tmp_path)
    assert CHECKER.check(tmp_path) == []


def test_released_layout_passes(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0b1", "1.0.0a1"), ("2026-11-01", "2026-10-20"))
    assert CHECKER.check(tmp_path) == []


def test_missing_index_fails(tmp_path: Path) -> None:
    assert CHECKER.check(tmp_path) == [f"{tmp_path / 'index.md'}: 索引缺失"]


def test_missing_declaration_fails(tmp_path: Path) -> None:
    build(tmp_path)
    index = tmp_path / "index.md"
    rewrite(index, index.read_text(encoding="utf-8").replace("semver.org", "example.com"))
    assert any("语义化版本" in error for error in CHECKER.check(tmp_path))


def test_unreleased_must_come_first(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    tail = f"\n\n## [Unreleased]\n\n[Unreleased]: {CHECKER.REPO_URL}/commits/HEAD\n"
    rewrite(tmp_path / "index.md", f"{DECLARATION}\n\n## 已发布{tail}")
    assert any("第一个二级段" in error for error in CHECKER.check(tmp_path))


def test_only_two_headings_allowed(tmp_path: Path) -> None:
    build(tmp_path)
    index = tmp_path / "index.md"
    rewrite(index, index.read_text(encoding="utf-8") + "\n## 别的\n")
    assert any("多出二级段" in error for error in CHECKER.check(tmp_path))


def test_bad_version_filename_fails(tmp_path: Path) -> None:
    build(tmp_path)
    rewrite(tmp_path / "1.0.md", version_text("1.0.0a1"))
    assert any("文件名不是本仓版本形态" in error for error in CHECKER.check(tmp_path))


def test_title_version_must_match_filename(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0a1",), ("2026-10-20",))
    rewrite(tmp_path / "1.0.0a1.md", version_text("1.0.0a2"))
    assert any("与文件名" in error for error in CHECKER.check(tmp_path))


def test_bad_date_fails(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0a1",), ("2026-10-20",))
    rewrite(tmp_path / "1.0.0a1.md", version_text("1.0.0a1", day="2026-13-01"))
    assert any("不是合法日期" in error for error in CHECKER.check(tmp_path))


def test_missing_title_fails(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0a1",), ("2026-10-20",))
    rewrite(tmp_path / "1.0.0a1.md", "### Added\n\n- 占位。\n")
    assert any("缺 `## [1.0.0a1]" in error for error in CHECKER.check(tmp_path))


def test_unknown_section_fails(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0a1",), ("2026-10-20",))
    rewrite(tmp_path / "1.0.0a1.md", version_text("1.0.0a1", sections=("Added", "Nope")))
    assert any("不在六类里" in error for error in CHECKER.check(tmp_path))


def test_duplicate_section_fails(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0a1",), ("2026-10-20",))
    rewrite(tmp_path / "1.0.0a1.md", version_text("1.0.0a1", sections=("Added", "Added")))
    assert any("出现两次" in error for error in CHECKER.check(tmp_path))


def test_section_order_fails(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0a1",), ("2026-10-20",))
    rewrite(tmp_path / "1.0.0a1.md", version_text("1.0.0a1", sections=("Fixed", "Added")))
    assert any("段顺序" in error for error in CHECKER.check(tmp_path))


def test_list_must_match_files(tmp_path: Path) -> None:
    build(tmp_path)
    rewrite(tmp_path / "1.0.0a1.md", version_text("1.0.0a1"))
    assert any("清单与目录不一致" in error for error in CHECKER.check(tmp_path))


def test_missing_link_definition_fails(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0a1",), ("2026-10-20",))
    index = tmp_path / "index.md"
    text = index.read_text(encoding="utf-8")
    kept = [line for line in text.splitlines() if not line.startswith("[1.0.0a1]:")]
    rewrite(index, "\n".join(kept))
    assert any("缺链接引用" in error for error in CHECKER.check(tmp_path))


def test_unreleased_link_must_point_at_newest(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0a1",), ("2026-10-20",))
    index = tmp_path / "index.md"
    text = index.read_text(encoding="utf-8")
    rewrite(index, text.replace("/compare/v1.0.0a1...HEAD", "/commits/HEAD"))
    assert any("`[Unreleased]:` 应为" in error for error in CHECKER.check(tmp_path))


def test_date_must_not_regress(tmp_path: Path) -> None:
    build(tmp_path, ("1.0.0b1", "1.0.0a1"), ("2026-10-01", "2026-10-20"))
    assert any("早于" in error for error in CHECKER.check(tmp_path))

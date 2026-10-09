#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""校验 docs/CHANGELOG/ 的结构（门禁 G20）。

只校验结构，不校验内容：段位、版本号形态、日期、六类顺序、索引与链接引用是否自洽。
「这一版该记什么」不归本脚本管，口径见 docs/design/changelog.md。

用法：
    python scripts/check_changelog.py   # 通过退出 0，否则逐条报错并退出 1
"""

from __future__ import annotations

import itertools
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_DIR = ROOT / "docs" / "CHANGELOG"
REPO_URL = "https://github.com/HanYang06/OnCasket"

# 本仓版本形态：X.Y.Z，可带 aN / bN / rcN 预发布段（PEP 440 的子集，够用即止）
VERSION = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:(?P<stage>a|b|rc)(?P<num>\d+))?$"
)

# Keep a Changelog 1.1.0 的六类，元组顺序即段内顺序
SECTIONS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

# 预发布段的排序权重：a < b < rc < 正式版
STAGES = {"a": 0, "b": 1, "rc": 2, None: 3}

# 版本键兜底：进排序前已滤掉不合形态的文件名，这里只为满足排序键的签名
FALLBACK_KEY = (0, 0, 0, -1, 0)

H2 = re.compile(r"^## (?P<title>.+)$")
H3 = re.compile(r"^### (?P<title>.+)$")
VERSION_HEAD = re.compile(r"^## \[(?P<version>[^\]]+)\] - (?P<day>\d{4}-\d{2}-\d{2})$")
LIST_ITEM = re.compile(r"^- \[(?P<version>[^\]]+)\]\((?P<target>[^)]+)\)$")
LINK_DEF = re.compile(r"^\[(?P<label>[^\]]+)\]: (?P<url>\S+)$")


def version_key(text: str) -> tuple[int, int, int, int, int] | None:
    """把版本号文本转成可比较的键。

    Args:
        text: 版本号文本，如 `1.0.0a1`。

    Returns:
        五元组键；形态不合法时为 None。
    """
    match = VERSION.match(text)
    if match is None:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        STAGES[match.group("stage")],
        int(match.group("num") or 0),
    )


def headings(text: str, pattern: re.Pattern[str]) -> list[str]:
    """按行抽出标题文字。

    Args:
        text: 全文。
        pattern: 匹配标题行的正则，须有 `title` 组。

    Returns:
        标题文字列表，按出现顺序。
    """
    found: list[str] = []
    for line in text.splitlines():
        match = pattern.match(line)
        if match is not None:
            found.append(match.group("title").strip())
    return found


def section_lines(text: str, title: str) -> list[str]:
    """取出某个二级段的正文行。

    Args:
        text: 全文。
        title: 二级段标题，不含 `## `。

    Returns:
        段正文行，到下一个二级段为止；没有这一段时为空。
    """
    lines = text.splitlines()
    wanted = f"## {title}"
    start: int | None = None
    for position, line in enumerate(lines):
        if line.strip() == wanted:
            start = position + 1
            break
    if start is None:
        return []
    for position in range(start, len(lines)):
        if lines[position].startswith("## "):
            return lines[start:position]
    return lines[start:]


def declaration_errors(index: Path, text: str) -> list[str]:
    """校验正文里的两条声明：Keep a Changelog 与语义化版本。

    Args:
        index: 索引文件路径，只用于报错。
        text: 索引全文。

    Returns:
        错误清单。
    """
    wanted = (("keepachangelog.com", "Keep a Changelog"), ("semver.org", "语义化版本"))
    return [
        f"{index}: 缺 {label} 声明（正文里应出现 {needle}）"
        for needle, label in wanted
        if needle not in text
    ]


def heading_errors(index: Path, text: str) -> list[str]:
    """校验索引的二级段：`[Unreleased]` 在最前，另有且仅有 `已发布`。

    Args:
        index: 索引文件路径，只用于报错。
        text: 索引全文。

    Returns:
        错误清单。
    """
    titles = headings(text, H2)
    if not titles:
        return [f"{index}: 没有二级段"]
    errors: list[str] = []
    if titles[0] != "[Unreleased]":
        errors.append(f"{index}: 第一个二级段应为 `## [Unreleased]`，实际是 `## {titles[0]}`")
    extra = [title for title in titles[1:] if title != "已发布"]
    if extra:
        errors.append(f"{index}: 多出二级段 {extra}（只允许 `[Unreleased]` 与 `已发布`）")
    if titles.count("已发布") != 1:
        errors.append(f"{index}: `## 已发布` 应出现且只出现一次")
    return errors


def version_files(root: Path) -> tuple[list[str], list[str]]:
    """列出目录里的版本文件，按版本降序。

    Args:
        root: 变更日志目录。

    Returns:
        (版本号降序列表, 错误清单)。
    """
    versions: list[str] = []
    errors: list[str] = []
    for path in sorted(root.glob("*.md")):
        if path.name == "index.md":
            continue
        if version_key(path.stem) is None:
            errors.append(f"{path}: 文件名不是本仓版本形态（`X.Y.Z` 或带 `aN` / `bN` / `rcN`）")
            continue
        versions.append(path.stem)
    versions.sort(key=lambda name: version_key(name) or FALLBACK_KEY, reverse=True)
    return versions, errors


def section_errors(path: Path, text: str) -> list[str]:
    """校验版本文件里的段：只用六类、不重复、顺序固定。

    Args:
        path: 版本文件路径，只用于报错。
        text: 版本文件全文。

    Returns:
        错误清单。
    """
    errors: list[str] = []
    seen: list[str] = []
    for name in headings(text, H3):
        if name not in SECTIONS:
            errors.append(f"{path}: 段名 `{name}` 不在六类里（{' / '.join(SECTIONS)}）")
        elif name in seen:
            errors.append(f"{path}: 段名 `{name}` 出现两次")
        else:
            seen.append(name)
    order = [SECTIONS.index(name) for name in seen]
    if order != sorted(order):
        errors.append(f"{path}: 段顺序应为 {' → '.join(SECTIONS)}")
    return errors


def version_entry_errors(root: Path, version: str) -> tuple[date | None, list[str]]:
    """校验一份版本文件的标题，并取出发布日。

    Args:
        root: 变更日志目录。
        version: 版本号。

    Returns:
        (发布日, 错误清单)；标题缺失或日期非法时发布日为 None。
    """
    path = root / f"{version}.md"
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    day: date | None = None
    found: str | None = None
    for line in text.splitlines():
        match = VERSION_HEAD.match(line)
        if match is None:
            continue
        found = match.group("version")
        try:
            day = date.fromisoformat(match.group("day"))
        except ValueError:
            errors.append(f"{path}: 日期 `{match.group('day')}` 不是合法日期")
        break
    if found is None:
        errors.append(f"{path}: 缺 `## [{version}] - <YYYY-MM-DD>` 标题")
    elif found != version:
        errors.append(f"{path}: 标题里的版本是 `{found}`，与文件名 `{version}` 不符")
    errors += section_errors(path, text)
    return day, errors


def list_errors(index: Path, text: str, versions: list[str]) -> list[str]:
    """校验 `## 已发布` 清单与版本文件一一对应。

    Args:
        index: 索引文件路径，只用于报错。
        text: 索引全文。
        versions: 版本号降序列表。

    Returns:
        错误清单。
    """
    listed: list[str] = []
    errors: list[str] = []
    for line in section_lines(text, "已发布"):
        match = LIST_ITEM.match(line.strip())
        if match is None:
            continue
        version = match.group("version")
        listed.append(version)
        if match.group("target") != f"{version}.md":
            target = match.group("target")
            errors.append(f"{index}: 清单里 `{version}` 指向 `{target}`，应为 `{version}.md`")
    if listed != versions:
        errors.append(f"{index}: `## 已发布` 清单与目录不一致（清单 {listed}，目录 {versions}）")
    return errors


def order_errors(index: Path, entries: list[tuple[str, date]]) -> list[str]:
    """校验版本降序时发布日随之不增。

    Args:
        index: 索引文件路径，只用于报错。
        entries: (版本, 发布日) 列表，已按版本降序。

    Returns:
        错误清单。
    """
    return [
        f"{index}: `{newer}` 的发布日 {newer_day} 早于更旧的 `{older}` 的 {older_day}"
        for (newer, newer_day), (older, older_day) in itertools.pairwise(entries)
        if newer_day < older_day
    ]


def link_errors(index: Path, text: str, versions: list[str]) -> list[str]:
    """校验末尾的链接引用：每版一条，外加 `[Unreleased]`。

    Args:
        index: 索引文件路径，只用于报错。
        text: 索引全文。
        versions: 版本号降序列表。

    Returns:
        错误清单。
    """
    defined: dict[str, str] = {}
    for line in text.splitlines():
        match = LINK_DEF.match(line)
        if match is not None:
            defined[match.group("label")] = match.group("url")
    errors: list[str] = []
    for version in versions:
        url = defined.get(version)
        if url is None:
            errors.append(f"{index}: 缺链接引用 `[{version}]:`")
        elif "/compare/" not in url:
            errors.append(f"{index}: `[{version}]:` 应指向 `{REPO_URL}/compare/…`")
    want = f"{REPO_URL}/compare/v{versions[0]}...HEAD" if versions else f"{REPO_URL}/commits/HEAD"
    unreleased = defined.get("Unreleased")
    if unreleased is None:
        errors.append(f"{index}: 缺链接引用 `[Unreleased]:`")
    elif unreleased != want:
        errors.append(f"{index}: `[Unreleased]:` 应为 {want}")
    return errors


def check(root: Path) -> list[str]:
    """校验一份变更日志目录。

    Args:
        root: 变更日志目录。

    Returns:
        错误清单；空表示通过。
    """
    index = root / "index.md"
    if not index.is_file():
        return [f"{index}: 索引缺失"]
    text = index.read_text(encoding="utf-8")
    versions, errors = version_files(root)
    errors += declaration_errors(index, text)
    errors += heading_errors(index, text)
    entries: list[tuple[str, date]] = []
    for version in versions:
        day, entry_errors = version_entry_errors(root, version)
        errors += entry_errors
        if day is not None:
            entries.append((version, day))
    errors += list_errors(index, text, versions)
    errors += order_errors(index, entries)
    errors += link_errors(index, text, versions)
    return errors


def main() -> int:
    """命令行入口。

    Returns:
        进程退出码：通过 0，有错 1。
    """
    errors = check(CHANGELOG_DIR)
    for error in errors:
        print(error)
    if errors:
        print(f"{CHANGELOG_DIR}: {len(errors)} 处不符（门禁 G20）")
        return 1
    print(f"{CHANGELOG_DIR}: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

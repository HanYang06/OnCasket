# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""公开面守卫（路线 031）：顶层除白名单外一律私有，`__all__` 里的名字都取得到。"""

from __future__ import annotations

from pathlib import Path

import oncasket


PACKAGE = Path(oncasket.__file__).resolve().parent

# 顶层允许出现的非私有条目。__init__.py / __main__.py / __pycache__ 本就以 `_` 开头，
# 由下划线规则覆盖；py.typed 没有 .py 后缀，只能显式放行。
ALLOWED_PUBLIC = frozenset({"py.typed"})


def public_entries(package: Path) -> list[str]:
    """列出顶层不合规的公开条目。

    Args:
        package: 包目录。

    Returns:
        非私有且不在白名单里的条目名，已排序。
    """
    return sorted(
        entry.name
        for entry in package.iterdir()
        if not entry.name.startswith("_") and entry.name not in ALLOWED_PUBLIC
    )


def test_top_level_is_private() -> None:
    assert public_entries(PACKAGE) == []


def test_guard_catches_a_public_module(tmp_path: Path) -> None:
    package = tmp_path / "oncasket"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "errors.py").write_text("", encoding="utf-8")
    assert public_entries(package) == ["errors.py"]


def test_guard_allows_the_whitelist(tmp_path: Path) -> None:
    package = tmp_path / "oncasket"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "_hub").mkdir()
    (package / "py.typed").write_text("", encoding="utf-8")
    assert public_entries(package) == []


def test_all_names_resolve() -> None:
    assert isinstance(oncasket.__all__, list)
    missing = [name for name in oncasket.__all__ if not hasattr(oncasket, name)]
    assert missing == []

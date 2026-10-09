# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""依赖分层守卫（路线 031）：域之间的 import 只能朝允许的方向走，反向边即红。"""

from __future__ import annotations

import ast
from pathlib import Path

import oncasket


PACKAGE = Path(oncasket.__file__).resolve().parent

# 每个域只许依赖这些域。表必须覆盖代码里出现过的每个域，漏了由 violations 报出来。
ALLOWED: dict[str, frozenset[str]] = {
    "": frozenset({"_errors", "_ops"}),  # 顶层：门面与命令行
    "__main__": frozenset({"_cli"}),
    "_cli": frozenset({"_errors", "_ops"}),
    "_errors": frozenset(),
    "_hub": frozenset({"_errors"}),
    "_format": frozenset({"_errors", "_hub"}),
    "_index": frozenset({"_errors", "_hub"}),
    "_alloc": frozenset({"_errors", "_hub", "_format", "_index"}),
    "_gc": frozenset({"_errors", "_hub", "_format", "_index", "_alloc"}),
    "_repair": frozenset({"_errors", "_hub", "_format", "_index", "_alloc"}),
    "_ops": frozenset({"_errors", "_hub", "_format", "_index", "_alloc", "_gc", "_repair"}),
}


def module_name(package: Path, path: Path) -> str:
    """把包内文件路径转成模块名。

    Args:
        package: 包目录。
        path: 包内的 .py 文件。

    Returns:
        形如 `oncasket._format.park` 的模块名。
    """
    parts = [package.name, *path.relative_to(package).with_suffix("").parts]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def domain(module: str) -> str:
    """取模块所属的域。

    Args:
        module: 绝对模块名。

    Returns:
        域的键：顶层包为 `""`，其余取第二段。
    """
    parts = module.split(".")
    return "" if len(parts) == 1 else parts[1]


def targets(source: str, tree: ast.Module, *, is_package: bool) -> list[str]:
    """列出文件 import 到的绝对模块名。

    Args:
        source: 本文件的模块名，用于解析相对导入。
        tree: 语法树。
        is_package: 本文件是不是包的 `__init__.py`（决定相对导入的基准）。

    Returns:
        被导入的模块名；相对导入已解析成绝对名。
    """
    container = source if is_package else source.rsplit(".", 1)[0]
    parts = container.split(".")
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    found.append(node.module)
                continue
            head = parts[: len(parts) - node.level + 1]
            if node.module is None:
                found += [".".join([*head, alias.name]) for alias in node.names]
            else:
                found.append(".".join([*head, *node.module.split(".")]))
    return found


def violations(package: Path) -> list[str]:
    """列出违反分层的 import 边。

    Args:
        package: 包目录。

    Returns:
        人类可读的违规清单；空表示通过。
    """
    found: list[str] = []
    for path in sorted(package.rglob("*.py")):
        source = module_name(package, path)
        source_domain = domain(source)
        allowed = ALLOWED.get(source_domain)
        if allowed is None:
            found.append(f"{source}: 域 {source_domain or '（顶层）'} 不在分层表里，先补 ALLOWED")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for target in targets(source, tree, is_package=path.name == "__init__.py"):
            if domain(target) == source_domain:
                continue
            if not target.startswith(f"{package.name}.") and target != package.name:
                continue  # 标准库与第三方
            target_domain = domain(target)
            if target_domain not in allowed:
                here = source_domain or "（顶层）"
                there = target_domain or "（顶层）"
                found.append(f"{source} → {target}：{here} 不许依赖 {there}")
    return found


def test_layers_are_respected() -> None:
    assert violations(PACKAGE) == []


def test_every_domain_is_declared() -> None:
    domains = {domain(module_name(PACKAGE, path)) for path in PACKAGE.rglob("*.py")}
    assert domains <= set(ALLOWED)


def make_package(root: Path) -> Path:
    """在临时目录里造一个最小包骨架。

    Args:
        root: 临时目录。

    Returns:
        包目录。
    """
    package = root / "oncasket"
    initials = ("__init__.py", "_hub/__init__.py", "_ops/__init__.py", "_format/__init__.py")
    for relative in initials:
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return package


def test_guard_catches_a_reverse_edge(tmp_path: Path) -> None:
    package = make_package(tmp_path)
    (package / "_hub" / "bad.py").write_text("from oncasket._ops import write\n", encoding="utf-8")
    found = violations(package)
    assert len(found) == 1
    assert "oncasket._hub.bad" in found[0]


def test_guard_allows_a_downward_edge(tmp_path: Path) -> None:
    package = make_package(tmp_path)
    (package / "_format" / "park.py").write_text(
        "from oncasket._hub import layout\n", encoding="utf-8"
    )
    assert violations(package) == []


def test_guard_catches_an_undeclared_domain(tmp_path: Path) -> None:
    package = make_package(tmp_path)
    (package / "_new").mkdir()
    (package / "_new" / "__init__.py").write_text("", encoding="utf-8")
    found = violations(package)
    assert len(found) == 1
    assert "不在分层表里" in found[0]

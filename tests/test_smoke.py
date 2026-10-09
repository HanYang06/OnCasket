# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""冒烟测试：包能导入、版本号单一来源、命令行入口能跑。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import oncasket
from oncasket._cli import main


if TYPE_CHECKING:
    import pytest


ROOT = Path(__file__).resolve().parent.parent


def test_version_comes_from_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert oncasket.__version__ == project["project"]["version"]


def test_cli_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    assert capsys.readouterr().out == "Hello from oncasket!\n"


def test_description_matches_readme() -> None:
    """定位句两处一致：`description` 必须逐字出现在 README 首段，否则漂移没人发现。"""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    description = project["project"]["description"]
    assert description
    assert description in (ROOT / "README.md").read_text(encoding="utf-8")

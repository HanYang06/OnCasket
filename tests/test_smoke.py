# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""冒烟测试：包能导入、CLI 入口能跑。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import oncasket


if TYPE_CHECKING:
    import pytest


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    oncasket.main()
    assert capsys.readouterr().out == "Hello from oncasket!\n"


def test_package_exports_main() -> None:
    assert callable(oncasket.main)

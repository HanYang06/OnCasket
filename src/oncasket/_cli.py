# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""命令行入口。

子命令、参数与输出形态归路线 022；这里只放控制台脚本与 `python -m` 共用的那一个入口。
"""

from __future__ import annotations


def main() -> int:
    """命令行入口。

    Returns:
        进程退出码。
    """
    print("Hello from oncasket!")
    return 0

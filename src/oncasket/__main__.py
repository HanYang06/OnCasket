# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""`python -m oncasket` 的入口：等价于控制台脚本 `oncasket`。

导入刻意留在 `if` 里：`coverage` 的 `exclude_lines` 排除整个 `__main__` 块，
这份引导代码因此不占覆盖率账（包里全是占位模块时，一个未覆盖语句就够把比例打穿）。
"""

if __name__ == "__main__":
    import sys

    from oncasket._cli import main

    sys.exit(main())

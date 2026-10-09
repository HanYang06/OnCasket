<!-- SPDX-FileCopyrightText: 2026 HanYang06 -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 包与目录：公开面、域子包与依赖分层

> 域：工程 / 代码骨架。对应路线图 [1.x 路线增量](../roadmap/1.x.md)。
>
> **事实依据**：结构契约由 [`tests/test_public_surface.py`](../../tests/test_public_surface.py) 与
> [`tests/test_import_layers.py`](../../tests/test_import_layers.py) 两条守卫钉死。
> 本域没有机读的配置型文件——目录树就是它自己的事实依据。
> 规范见[文档规范](../README.md)。

## <a id="r031"></a>031 包与目录：公开面、域子包与依赖分层

- 决策状态：已定（待定项见文末）

### 1. 什么真的不可逆

| 面 | 改了会怎样 | 本轮 |
|---|---|---|
| 包名 `oncasket`、`import oncasket` | 破坏性变更：PyPI 版本不可撤回、下游 import 全断 | 定死 |
| 顶层公开模块路径（`oncasket.X`） | 同上 | 定死（规则见 §2） |
| `__all__` 里的名字、公开签名里的类型 | 同上 | 规则定死；具体名字归路线 022 |
| 控制台脚本名 `oncasket`、`python -m oncasket` | 同上 | 定死 |
| 私有子包怎么切、生成物手写还是生成、测试怎么排 | 不是破坏性变更，只是要动很多文件 | 定个好的，但不供着 |

- **只有前四行值得当契约守**。把内部划分也供成契约，只会让重构变贵——私有面改了不算破坏性变更。

### 2. 公开面 = 白名单

- `src/oncasket/` 顶层**只允许两个非 `_` 开头的条目**：`py.typed` 与 `api/`。
  `__init__.py` / `__main__.py` / `__pycache__` 本就以下划线开头，所以规则只有一条 + 白名单。
- 公开面由两块组成：门面本体 [`__init__.py`](../../src/oncasket/__init__.py) 与拆出去的
  [`api/`](../../src/oncasket/api/)。公开名字在各自的 `__all__` 里逐个列出；**公开签名里不出现
  私有类型**（否则 `oncasket._ops.write.Handle` 会漏进用户的注解与 repr）。
- `api/` 是**整体**拆分，不是「再散出几个公开模块」：门面长大后按域拆进 `api/`
  （`api/block.py` / `api/hub.py` / `api/park.py` / `api/slot.py` / `api/index.py`），
  `api/__init__.py` 只做重导出，子模块自己也有 `__all__`。
  下游 import 的路径只有这一条，冻结时也只记这一条——比在顶层长出 `oncasket/hub.py`、
  `oncasket/index.py` 强得多。
- `__version__` 的单一来源是 `pyproject.toml`，运行时经 `importlib.metadata` 取，由冒烟测试校。
- 守卫：[`tests/test_public_surface.py`](../../tests/test_public_surface.py)——白名单与两个
  `__all__` 的自洽都查。

### 3. 域子包

一域一子包，域内平铺、不再往下嵌套（固定三层 `oncasket/_format/park.py`）：

```text
src/oncasket/
  __init__.py          # 公开面之一：__all__、门面、__version__
  __main__.py          # python -m oncasket
  py.typed             # 类型标记（classifier 声明了 Typed 就得有它）
  api/                 # 公开面之二：公开名字的落点（022 冻结；名字定稿前 __all__ 为空）
    __init__.py
  _cli.py              # [project.scripts] oncasket = "oncasket._cli:main"
  _errors.py           # 异常类的唯一定义处（域模块只抛不定义）
  _hub/                # 005 / 026：容器与 hub
    layout.py  manifest.py  lock.py
  _format/             # 021：位级格式
    spec.py  park.py  slot.py  block.py  scan.py
  _index/              # 006 / 008–013：索引库
    schema_gen.py  fingerprint.py  store.py  commit.py  rebuild.py
  _alloc/              # 014 / 015：空洞分配与死槽判定
    segments.py  policy.py  ledger.py
  _ops/                # 跨域编排
    session.py  write.py  read.py  delete.py
  _repair/             # 032：修复；编号在 ids.py，一条修复一个模块
  _gc/                 # 016 / 017：1.1.0a1 才建，此处只占位
```

- 域与设计篇一一对应：改设计知道动哪个子包，改代码知道翻哪一篇。
- **`_` 前缀就是私有**：域内模块名可以自由改、自由拆，不构成破坏性变更。
- **不预建空目录**：骨架只建当前版本要用的域；`_gc` 这类 1.1 / 1.2 的域只在本文占位。
- 原有 `format/f_pack.py` 那套**域前缀废掉**：域已由子包表达，`f_` 是重复信息。
- 占位模块只写许可头 + 模块 docstring，**不写任何语句**：`coverage` 的 `source` 是 `src`，
  多一行 `import` 就是一个未覆盖语句。

### 4. 依赖分层

| 域 | 只许依赖 | 理由 |
|---|---|---|
| `_errors` | — | 谁都能用；自己不依赖任何域 |
| `_hub` | `_errors` | 路径与锁，最底层 |
| `_format` | `_errors`、`_hub` | 只认路径，不认库 |
| `_index` | `_errors`、`_hub` | 只认库文件，不认 park |
| `_alloc` | 上面 ＋ `_format`（盲扫兜底） | 段表来源是库里现成的 `budget_slot` |
| `_gc` | 上面全部 | 对账要判死依据 |
| `_repair` | `_errors`、`_hub`、`_format`、`_index`、`_alloc` | 读盘、重扫、清孤儿槽、可能重建索引；**不依赖 `_ops`**（否则成环） |
| `_ops` | 上面全部 | **唯一**跨域编排处，也是唯一调 `_repair` 的地方 |
| `__init__` / `api` / `_cli` / `__main__` | `_errors`、`_ops` | 门面只做转发；`api` 与 `__init__` 同层，互不依赖 |

- 只许单向：**同层或更低层**；`_format` 与 `_index` 并列，互不依赖。
- 「提交 ①–⑦」这种横跨几域的流程一律进 `_ops`；域之间不许互相调用。
- 守卫：[`tests/test_import_layers.py`](../../tests/test_import_layers.py) 用 AST 解析 import 图，反向边即红；
  新增域必须同时进这张表，表漏了守卫会报。

### 5. 命名

| 对象 | 规则 |
|---|---|
| 包内模块 | `lower_snake_case`、名词、**不带域前缀** |
| 私有 | 只在顶层用 `_` 前缀；域内不再套一层下划线（整个域都是私有的） |
| 测试 | `tests/<域>/test_<对象>.py`，域名与 `src` 同去掉下划线（`format/` ↔ `_format/`）；跨域守卫放 `tests/` 根 |
| 脚本 | `check_*` 只校验 / `gen_*` 生成（`--check` 校验）/ `stamp_*` 盖章；扁平、不建包 |
| 生成物 | 文件名带 `_gen`，文件头写死「自动生成，勿手改」 |

- 测试目录**不用 `__init__.py`**（延续 `pytest --import-mode=importlib` 的既有口径）；
  `mypy` 侧靠 `mypy_path = ["src", "."]` ＋ `explicit_package_bases = true` 把 tests 当命名空间包，
  一条 `module = ["tests.*"]` 覆盖全部测试——**新增测试文件不必再改 `pyproject.toml`**，
  不同目录下的同名测试文件也不会再撞车。

### 6. 事实依据 → 代码

| 事实依据 | 代码落点 | 关系 |
|---|---|---|
| [`config/index_db.sql`](../../config/index_db.sql) | `_index/schema_gen.py` | **生成物**（011）：建库 DDL ＋ 基准指纹常量，唯一写处是 `.sql`，门禁 `--check` |
| [`config/format.txt`](../../config/format.txt) | `_format/spec.py` | 位偏移**手工写**在 `spec.py`，由 [`tests/format/test_spec_matches_fact.py`](../../tests/format/test_spec_matches_fact.py) 逐项对着 `.txt` 校；要不要升级成生成物见表末待定 |
| [`config/hub.txt`](../../config/hub.txt) | `_hub/layout.py` | 同上 |
| [`config/judge_db.sql`](../../config/judge_db.sql) | `_alloc/ledger.py` | 同 `index_db.sql`；但账本无指纹、结构变了直接重建 |
| [`config/repair.txt`](../../config/repair.txt) | `_repair/ids.py` | **清单型**：编号是对照表的唯一处，代码侧只镜像编号，由测试逐号对账 |

- 运行时包**不装 `config/`**：从 `.sql` 现读等于把设计层的事实依据发货发两份，还要多一次文件 IO。

### 7. 守卫怎么跑

- 两条守卫都是**普通 pytest 用例**，不新开 gate 编号：G10（推送前）与 G15（CI 三平台）本来就会跑。
- 单实现、不重复造钩子：写成脚本再挂 pre-commit，会让同一件事有两份代码。

## 待定

| # | 待定项 | 卡在哪 | 谁拍 |
|---|---|---|---|
| 1 | `_gc` 内部怎么分模块 | 016 / 017 尚无设计篇 | 待定 |
| 2 | `format.txt` / `hub.txt` 的位偏移要不要也走生成物 | 现已按「手工写 + 测试对着 `.txt` 校」落地（`spec.py` ＋ `test_spec_matches_fact.py`）；换生成物要先把 DSL 解析器写出来，等格式稳定后再说 | 待定 |
| 3 | 公开 API 的具体名字与签名 | 路线 022；`oncasket/api/` 已开、`__all__` 仍为空 | 待定 |

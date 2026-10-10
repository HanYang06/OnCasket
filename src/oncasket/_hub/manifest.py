# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""hub 清单与配置：`<容器>/hub.conf.json`（走 OnConf，hub 布局 §005 / §026）。

清单是**容器级**的：一个容器平铺若干 hub，`hub.conf.json` 与 `hub.lock.json` 放在容器那层，
hub 自己的结构（`pack/**/*.oncat` ＋ `index/index.db`）才是它的身份。

三条纪律：

- **只用 OnConf 读写**：引擎不另发明配置格式，也不绕过它直接解析这个文件（§026）。
  走的是 `onconf.Engine`（一个配置目录 = 一个引擎），不是进程级单例 `AutoConf`
  ——同一个进程要能开多个容器，这是「多 hub / 多容器」的底线。
- **声明即默认**：每个键都以缺省值声明一次，`OnConf` 尊重文件里已有的值
  （不覆盖人配的那份），所以「打开一个 hub」= 清单缺什么补什么，幂等。
- **值要过校验**：文件是给人手改的，类型 / 取值不合法一律 `ValueError`，不静默退回缺省
  ——静默退回等于把人改错的地方藏起来。

OnConf 会在容器里落下自己的配套件（词表 `schema/hub.conf.json`、审计 `audit.log`、
派生快照 `.onconf.json`），那是 `home` 这个概念的产物，不由这里安排。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import onconf


if TYPE_CHECKING:
    from pathlib import Path


#: 值文件名主干：`<file_name>.json` ⇒ `hub.conf.json`
MANIFEST_STEM = "hub.conf"

#: 写锁等待上限（秒）。**缺省暂定 1 秒**：口径见公开 API §12 待定项 1
#: （毫秒级还是秒级等压测出结果再拍），这里先给一个能等的值，不拍死。
DEFAULT_LOCK_TIMEOUT = 1.0
LOCK_TIMEOUT_KEY = "lock_timeout"
LOCK_TIMEOUT_DOC = "写锁等待上限（秒）：拿不到锁就等，等过这个数抛 LockTimeoutError"

#: 空洞分配的策略（口径在空洞分配 §014 §3）；取值由 `_alloc.policy` 负责认，这里只管存取。
DEFAULT_ALLOC_PICK = "best_fit"
ALLOC_PICK_KEY = "alloc_pick"
ALLOC_PICK_DOC = "段选择策略：best_fit / first_fit / worst_fit"

DEFAULT_ALLOC_DEAD = "pessimistic"
ALLOC_DEAD_KEY = "alloc_dead"
ALLOC_DEAD_DOC = "死槽判定策略：pessimistic / optimistic / off"

#: 落进清单的键：`(键, 缺省值, 说明)`。三样写在一处，`open` 与各个取值口都从它来。
_DEFAULTS: tuple[tuple[str, object, str], ...] = (
    (LOCK_TIMEOUT_KEY, DEFAULT_LOCK_TIMEOUT, LOCK_TIMEOUT_DOC),
    (ALLOC_PICK_KEY, DEFAULT_ALLOC_PICK, ALLOC_PICK_DOC),
    (ALLOC_DEAD_KEY, DEFAULT_ALLOC_DEAD, ALLOC_DEAD_DOC),
)


class Manifest:
    """一个容器的清单：`hub.conf.json` 的读写口，值一律过校验再出去。"""

    def __init__(self, engine: Any, container: Path) -> None:
        """不直接调；走 `open`。

        Args:
            engine: 已经装配好的 OnConf 引擎（`home` = 容器目录）。
            container: 容器目录。
        """
        self._engine = engine
        self._container = container

    @classmethod
    def open(cls, container: Path) -> Manifest:
        """打开（必要时建）一个容器的清单。

        目录不在就建、文件不在就落：清单是「拿来就用」那条腿的一部分，先让调用方建目录
        只会让常用路径变长。落的是**缺省值**——文件里已有的值一个字都不动。

        Args:
            container: 容器目录。

        Returns:
            清单句柄。
        """
        container.mkdir(parents=True, exist_ok=True)
        engine = onconf.Engine(
            home=container,
            file_name=MANIFEST_STEM,
            file_type="json",
            log_console=False,
        )
        manifest = cls(engine, container)
        manifest._seed()
        return manifest

    def _seed(self) -> None:
        """把每个键都以缺省值声明一遍：文件里没有的补上，已有的尊重文件（OnConf 的规矩）。

        这里只看「声明下去」，**不校验取回来的值**——值不对要由取值口当场报出来（谁读谁负责），
        打开清单时把人手改错的地方变成开不了 hub，反而不好收拾现场。
        """
        for key, default, doc in _DEFAULTS:
            self._engine(key, default, doc)

    @property
    def container(self) -> Path:
        """容器目录。"""
        return self._container

    @property
    def path(self) -> Path:
        """清单文件 `hub.conf.json` 的落点。"""
        return self._container / f"{MANIFEST_STEM}.json"

    def lock_timeout(self) -> float:
        """写锁等待上限（秒）。

        Returns:
            正数秒数。

        Raises:
            TypeError: 文件里不是数。
            ValueError: 文件里的数不是正的。
        """
        raw = self._engine(LOCK_TIMEOUT_KEY, DEFAULT_LOCK_TIMEOUT, LOCK_TIMEOUT_DOC)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError(f"{LOCK_TIMEOUT_KEY} 要数（秒），配置里是 {raw!r}")
        if raw <= 0:
            raise ValueError(f"{LOCK_TIMEOUT_KEY} 要正数秒，配置里是 {raw!r}")
        return float(raw)

    def alloc_pick(self) -> str:
        """段选择策略名（取值合法性归 `_alloc.policy`）。

        Returns:
            策略名字符串。

        Raises:
            TypeError: 文件里不是字符串。
        """
        return self._text(ALLOC_PICK_KEY, DEFAULT_ALLOC_PICK, ALLOC_PICK_DOC)

    def alloc_dead(self) -> str:
        """死槽判定策略名（取值合法性归 `_alloc.policy`）。

        Returns:
            策略名字符串。

        Raises:
            TypeError: 文件里不是字符串。
        """
        return self._text(ALLOC_DEAD_KEY, DEFAULT_ALLOC_DEAD, ALLOC_DEAD_DOC)

    def close(self) -> None:
        """收口：把攒着的声明交出去（`OnConf` 的默认提交点是当场落盘，这里只是保险）。"""
        self._engine.flush()

    def _text(self, key: str, default: str, doc: str) -> str:
        """取一个字符串配置项。

        Args:
            key: 键名。
            default: 缺省值。
            doc: 词表里的说明。

        Returns:
            文件里的值（没配就是缺省值）。

        Raises:
            TypeError: 文件里的值不是字符串。
        """
        raw = self._engine(key, default, doc)
        if not isinstance(raw, str):
            raise TypeError(f"{key} 要字符串，配置里是 {raw!r}")
        return raw

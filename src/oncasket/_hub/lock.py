# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""锁：`hub.lock.json` 容器级锁与 park 写锁；锁不做账本。

口径在[公开 API §11/§12](../../../docs/design/api.md)、[hub 布局 §005](../../../docs/design/hub.md)
与[空洞分配 §015](../../../docs/design/alloc.md)：**锁是「现在谁持有」，随取随放、随时可删**，
不做账本、不判陈旧、不自动破锁——盘上那个文件只是招牌，判据始终是「`O_CREAT | O_EXCL` 建没建成」。

- **取锁**：`os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`。同目录同路径上只有一个赢家，
  拿不到就是别人先到——不探测、不协商。
- **等**：拿不到就按 `poll` 让一步、拿 `time.monotonic()` 计时；等过 `timeout` 抛
  `LockTimeoutError`（正常情形，过会儿再来），不立刻抛。
- **载荷**：`{"pid", "at", "lock"}`，只给人看（诊断用），**不参与判据**。
- **谁建谁删**：`release()` 只删自己建的那把；文件已被外部删掉也算释放成功。
  父目录由调用方建好，这里不偷偷造树。

对应路线 036（并发与锁：等 ＋ 超时）。
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import UTC, datetime
from time import monotonic, sleep
from typing import TYPE_CHECKING

from oncasket._errors import LockTimeoutError


if TYPE_CHECKING:
    from pathlib import Path


#: 让一步的缺省时长：秒。够小才等得细，够大才不至于空转
DEFAULT_POLL = 0.01
#: 载荷里的时间戳形态：UTC、秒级、`Z` 收尾（ISO-8601）
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _close_quietly(fd: int) -> None:
    """关掉 fd，关闭时的 `OSError` 不当回事。

    只在「建过 fd、但写载荷时出错」的收尾路径上用：这时要如实把原异常冒出去，
    不能被关闭时的杂音盖掉。

    Args:
        fd: 要关闭的文件描述符；调用处拿到的都是真 fd。
    """
    with contextlib.suppress(OSError):
        os.close(fd)


class FileLock:
    """一把文件锁：`O_CREAT | O_EXCL` 建文件即持有，删文件即释放。

    Args:
        path: 锁文件路径。父目录必须已存在（调用方建目录）。
        timeout: 最多等多少秒；`0` 表示只试一次，负数不合法。
        poll: 轮询间隔秒数，必须是正数。

    Raises:
        ValueError: `timeout` 为负，或 `poll` 不是正数。
    """

    def __init__(self, path: Path, *, timeout: float, poll: float = DEFAULT_POLL) -> None:
        if timeout < 0:
            raise ValueError(f"锁超时不能为负：{timeout}")
        if poll <= 0:
            raise ValueError(f"轮询间隔必须是正数：{poll}")
        self._path = path
        self._timeout = timeout
        self._poll = poll
        self._fd = -1
        self._held = False

    @property
    def path(self) -> Path:
        """这把锁的锁文件路径。"""
        return self._path

    @property
    def held(self) -> bool:
        """当前是否持有锁。"""
        return self._held

    def acquire(self) -> None:
        """取锁；拿不到就等到超时。

        已持有就是空操作（幂等，不重复开文件）。取锁只有一条判据：`os.open` 的
        `O_CREAT | O_EXCL` 建没建成——载荷写进去只是给人看，不参与判定。

        Raises:
            LockTimeoutError: 等到 `timeout` 还没拿到。
            OSError: 父目录不在等原因导致建文件失败，原样冒出去。
        """
        if self._held:
            return
        deadline = monotonic() + self._timeout
        fd = -1
        while True:
            try:
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if monotonic() >= deadline:
                    raise LockTimeoutError(
                        f"取锁超时（{self._timeout} 秒）：{self._path}"
                    ) from None
                sleep(self._poll)
                continue
            break
        self._fd = fd
        try:
            os.write(fd, self._payload())
        finally:
            _close_quietly(fd)
            self._fd = -1
        self._held = True

    def release(self) -> None:
        """放锁：删掉自己建的那个文件，清掉持有状态。

        没持有时直接返回；文件已被外部删掉（`FileNotFoundError`）也当释放成功。
        幂等。
        """
        if not self._held:
            return
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()
        self._held = False

    def __enter__(self) -> FileLock:
        """进上下文：取锁。

        Returns:
            这把锁自己，便于 `with FileLock(...) as lock` 接着用。
        """
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        """出上下文：无条件放锁——异常路径也要放。

        Args:
            *args: 异常三元组；本方法不压制任何异常。
        """
        self.release()

    def _payload(self) -> bytes:
        """拼诊断载荷（**不参与判据**）。

        Returns:
            UTF-8 编码的 JSON 字节串，末尾一个换行。
        """
        record = {
            "pid": os.getpid(),
            "at": datetime.now(UTC).strftime(_TIME_FORMAT),
            "lock": self._path.as_posix(),
        }
        return (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")

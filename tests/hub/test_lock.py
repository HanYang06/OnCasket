# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""文件锁：`O_CREAT | O_EXCL` 只有一个赢家、等与超时、随取随放。

口径见[公开 API §11/§12](../../docs/design/api.md)与[空洞分配 §015](../../docs/design/alloc.md)：
锁文件不做账本、不判陈旧、不自动破锁——盘上那个文件只是招牌。

写法上有一条硬约束：**`held` 的断言一律写成 `assert 值 is lock.held`**（值在左、属性在右）。
反过来写会让 mypy 把 `FileLock.held` 收窄成 `Literal[False]`，同一模块后面的语句就会被
误判成「unreachable」。语序怪，但这是 `--warn-unreachable` 下唯一不误报的写法。
"""

from __future__ import annotations

import json
import os
from pathlib import Path  # noqa: TC003 —— Path 在运行时用（路径拼接），不是只在注解里

import pytest

from oncasket._errors import LockTimeoutError
from oncasket._hub.lock import FileLock


FILE_NAME = "hub.lock.json"


def test_acquire_holds_and_writes_diagnostic_payload(tmp_path: Path) -> None:
    target = tmp_path / FILE_NAME
    lock = FileLock(target, timeout=0.05)
    assert lock.path == target

    lock.acquire()

    assert True is lock.held
    assert target.is_file()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    assert payload["lock"] == target.as_posix()
    assert isinstance(payload["at"], str)
    assert payload["at"].endswith("Z")

    lock.release()


def test_a_fresh_lock_is_not_held_and_the_mark_is_absent(tmp_path: Path) -> None:
    """没取锁之前：不持有，盘上也没招牌。"""
    target = tmp_path / FILE_NAME
    lock = FileLock(target, timeout=0.05)

    assert False is lock.held
    assert not target.exists()


def test_payload_records_the_lock_path_as_posix(tmp_path: Path) -> None:
    """载荷里的 `lock` 是 posix 形态的路径——诊断用，人看得懂就行。"""
    target = tmp_path / FILE_NAME
    lock = FileLock(target, timeout=0.05)
    lock.acquire()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["lock"] == target.as_posix()
    finally:
        lock.release()


def test_second_lock_times_out_then_gets_it_after_release(tmp_path: Path) -> None:
    target = tmp_path / FILE_NAME
    first = FileLock(target, timeout=0.05)
    second = FileLock(target, timeout=0.05)
    first.acquire()
    try:
        with pytest.raises(LockTimeoutError):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    assert True is second.held
    second.release()


def test_acquire_with_zero_timeout_only_tries_once(tmp_path: Path) -> None:
    target = tmp_path / FILE_NAME
    holder = FileLock(target, timeout=0.05)
    holder.acquire()
    try:
        with pytest.raises(LockTimeoutError):
            FileLock(target, timeout=0).acquire()
    finally:
        holder.release()


def test_acquire_polls_until_it_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / FILE_NAME
    real_open = os.open
    calls = 0

    def flaky_open(path: os.PathLike[str], flags: int, mode: int = 0o777, /) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FileExistsError(17, "别人先到", str(path))
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", flaky_open)

    lock = FileLock(target, timeout=0.2, poll=0.01)
    lock.acquire()

    assert calls >= 2  # 第一次被拒入口，让一步之后再试才拿到
    assert True is lock.held
    lock.release()


def test_repeated_acquire_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / FILE_NAME
    lock = FileLock(target, timeout=0.05)
    lock.acquire()
    real_open = os.open
    calls = 0

    def counting_open(path: os.PathLike[str], flags: int, mode: int = 0o777, /) -> int:
        nonlocal calls
        calls += 1
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", counting_open)

    lock.acquire()

    assert calls == 0  # 已持有就空操作，不重复开文件
    assert True is lock.held
    lock.release()


def test_release_is_idempotent_and_harmless_when_not_held(tmp_path: Path) -> None:
    target = tmp_path / FILE_NAME
    lock = FileLock(target, timeout=0.05)

    lock.release()  # 没持有：无害
    assert not target.exists()

    lock.acquire()
    lock.release()
    assert not target.exists()

    lock.release()  # 再放一次：还是不抛
    assert not target.exists()


def test_release_after_external_delete_does_not_raise(tmp_path: Path) -> None:
    target = tmp_path / FILE_NAME
    lock = FileLock(target, timeout=0.05)
    lock.acquire()

    target.unlink()  # 外部（比如调用方或别的工具）把锁文件删了
    lock.release()

    assert False is lock.held


def test_context_manager_releases_on_normal_exit(tmp_path: Path) -> None:
    target = tmp_path / FILE_NAME
    with FileLock(target, timeout=0.05) as lock:
        assert True is lock.held
        assert target.exists()

    assert not target.exists()


def test_context_manager_releases_on_exception(tmp_path: Path) -> None:
    target = tmp_path / FILE_NAME
    with pytest.raises(RuntimeError), FileLock(target, timeout=0.05):
        raise RuntimeError("上下文里炸了")

    assert not target.exists()


def test_negative_timeout_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        FileLock(tmp_path / FILE_NAME, timeout=-1)


@pytest.mark.parametrize("poll", [0, -0.5])
def test_non_positive_poll_is_rejected(tmp_path: Path, poll: float) -> None:
    with pytest.raises(ValueError):
        FileLock(tmp_path / FILE_NAME, timeout=0.05, poll=poll)


def test_missing_parent_directory_raises_oserror(tmp_path: Path) -> None:
    absent = tmp_path / "nowhere" / FILE_NAME
    lock = FileLock(absent, timeout=0.05)

    with pytest.raises(OSError):
        lock.acquire()

    assert not absent.exists()


def test_parent_directory_is_not_conjured_up(tmp_path: Path) -> None:
    absent = tmp_path / "nowhere" / FILE_NAME
    with pytest.raises(OSError), FileLock(absent, timeout=0.05):
        pass

    assert not absent.parent.exists()


def test_payload_failure_does_not_hold_or_leak_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """载荷拼不出来时：持有没有落到身上，fd 也关了。"""
    target = tmp_path / FILE_NAME
    lock = FileLock(target, timeout=0.05)
    real_open = os.open
    fds: list[int] = []

    def spying_open(path: os.PathLike[str], flags: int, mode: int = 0o777, /) -> int:
        fd = real_open(path, flags, mode)
        fds.append(fd)
        return fd

    def broken_dumps(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("载荷拼不出来")

    monkeypatch.setattr(os, "open", spying_open)
    monkeypatch.setattr(json, "dumps", broken_dumps)

    with pytest.raises(RuntimeError):
        lock.acquire()

    assert lock._fd == -1
    assert len(fds) == 1
    with pytest.raises(OSError):
        os.fstat(fds[0])  # 这个 fd 已经被关掉了

    target.unlink()  # 招牌还在，但没锁住谁：删掉不碍事
    lock.release()  # 没持有：无害
    assert not target.exists()


def test_write_failure_keeps_the_mark_but_not_the_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """写载荷写不下去时：异常冒出去，fd 关掉，不假装自己持着锁。"""
    target = tmp_path / FILE_NAME
    lock = FileLock(target, timeout=0.05)

    def broken_write(_fd: int, _data: bytes, /) -> int:
        raise OSError("盘写不进去")

    monkeypatch.setattr(os, "write", broken_write)

    with pytest.raises(OSError):
        lock.acquire()

    assert lock._fd == -1
    assert target.is_file()  # 招牌留下了——载荷只是给人看，锁归调用方收拾


def test_leftover_mark_still_blocks_the_next_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """招牌还在就是「有人拿着」（不做探测、不判陈旧）：第二个照样超时。"""
    target = tmp_path / FILE_NAME
    lock = FileLock(target, timeout=0.05)

    def broken_write(_fd: int, _data: bytes, /) -> int:
        raise OSError("盘写不进去")

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", broken_write)
        with pytest.raises(OSError):
            lock.acquire()

    with pytest.raises(LockTimeoutError):
        FileLock(target, timeout=0).acquire()

    target.unlink()

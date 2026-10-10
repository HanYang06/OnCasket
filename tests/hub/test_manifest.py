# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""hub 清单：`hub.conf.json` 走 OnConf，缺什么补什么、值过校验（路线 026）。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from oncasket._hub.manifest import (
    DEFAULT_ALLOC_DEAD,
    DEFAULT_ALLOC_PICK,
    DEFAULT_LOCK_TIMEOUT,
    Manifest,
)


if TYPE_CHECKING:
    from pathlib import Path


def write_manifest(container: Path, payload: dict[str, object]) -> None:
    container.mkdir(parents=True, exist_ok=True)
    (container / "hub.conf.json").write_text(json.dumps(payload), encoding="utf-8")


def test_open_creates_the_container_and_the_declared_defaults(tmp_path: Path) -> None:
    container = tmp_path / "container"
    manifest = Manifest.open(container)
    assert manifest.container == container
    assert manifest.path == container / "hub.conf.json"
    assert manifest.lock_timeout() == DEFAULT_LOCK_TIMEOUT
    assert manifest.alloc_pick() == DEFAULT_ALLOC_PICK
    assert manifest.alloc_dead() == DEFAULT_ALLOC_DEAD
    payload = json.loads(manifest.path.read_text(encoding="utf-8"))
    assert payload["lock_timeout"] == DEFAULT_LOCK_TIMEOUT
    assert payload["alloc_pick"] == DEFAULT_ALLOC_PICK
    assert payload["alloc_dead"] == DEFAULT_ALLOC_DEAD
    manifest.close()


def test_open_is_idempotent_and_keeps_what_the_file_says(tmp_path: Path) -> None:
    container = tmp_path / "container"
    write_manifest(container, {"lock_timeout": 2.5, "alloc_pick": "first_fit"})
    with_manifest = Manifest.open(container)
    assert with_manifest.lock_timeout() == 2.5
    assert with_manifest.alloc_pick() == "first_fit"
    assert with_manifest.alloc_dead() == DEFAULT_ALLOC_DEAD


def test_a_reopened_manifest_sees_the_file_again(tmp_path: Path) -> None:
    container = tmp_path / "container"
    Manifest.open(container).close()
    assert Manifest.open(container).lock_timeout() == DEFAULT_LOCK_TIMEOUT


def test_a_wrong_type_is_a_type_error(tmp_path: Path) -> None:
    container = tmp_path / "container"
    write_manifest(container, {"lock_timeout": "soon"})
    manifest = Manifest.open(container)
    with pytest.raises(TypeError, match="lock_timeout 要数"):
        manifest.lock_timeout()


def test_a_non_positive_timeout_is_a_value_error(tmp_path: Path) -> None:
    container = tmp_path / "container"
    write_manifest(container, {"lock_timeout": 0})
    manifest = Manifest.open(container)
    with pytest.raises(ValueError, match="lock_timeout 要正数秒"):
        manifest.lock_timeout()


def test_a_boolean_timeout_is_rejected(tmp_path: Path) -> None:
    container = tmp_path / "container"
    write_manifest(container, {"lock_timeout": True})
    manifest = Manifest.open(container)
    with pytest.raises(TypeError, match="lock_timeout 要数"):
        manifest.lock_timeout()


def test_a_non_string_strategy_is_a_type_error(tmp_path: Path) -> None:
    container = tmp_path / "container"
    write_manifest(container, {"alloc_pick": 3})
    manifest = Manifest.open(container)
    with pytest.raises(TypeError, match="alloc_pick 要字符串"):
        manifest.alloc_pick()


def test_an_integer_timeout_is_accepted_as_a_float(tmp_path: Path) -> None:
    container = tmp_path / "container"
    write_manifest(container, {"lock_timeout": 3})
    manifest = Manifest.open(container)
    assert manifest.lock_timeout() == 3.0

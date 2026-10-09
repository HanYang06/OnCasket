# SPDX-FileCopyrightText: 2026 HanYang06
# SPDX-License-Identifier: Apache-2.0
"""位级布局：偏移、长度、魔数与缺省值（照 `config/format.txt`）。

事实依据是 `config/format.txt`：改布局先改 `.txt`、重盖版本标记，再改这里；
`tests/format/test_spec_matches_fact.py` 逐项比对，对不上即红。

三条**事实依据没写、实现必须钉死**的口径：

- 偏移与长度一律以**位**计（`Offset-unit: bit`），字节只是读写时的换算；
- 整数字段一律**小端**（`endian: little`），计数不带符号；
- 哈希字段存**算法原始输出字节**，不做端序翻转（sha256 的 32 B、xxh3-128 的 16 B 原样落盘）。
"""

from __future__ import annotations


# --- 单位与上限 -------------------------------------------------------------

#: 一个字节几位
BITS_PER_BYTE = 8

#: int32 上界（计数一律非负，按无符号解释）
INT32_MAX = 2**31 - 1

#: 32 位无符号上界：`slot_state` 那类魔数用它
UINT32_MAX = 2**32 - 1

#: pack 头的位长：文件起始这一段
PACK_HEADER_BITS = 1024

#: 缺省槽长（位）：8192 位 = 1024 B
SLOT_SIZE_DEFAULT = 8192

#: 槽长下界（位）：链首头槽至少要放得下六个计数（352）与 `block_id`（128）
SLOT_SIZE_MIN = 480

#: 缺省预算槽数：配缺省槽长即 1 GiB 容量
SLOT_NUM_DEFAULT = 2**20


# --- pack 头字段（位区间，相对文件起点）-------------------------------------

PACK_VERSION = (0, 256)
PACK_SLOT_SIZE = (256, 288)
PACK_SLOT_NUM = (288, 320)
PACK_SLOT_LIVE = (320, 352)
PACK_SLOT_USED = (352, 384)
PACK_SLOT_DEAD = (384, 416)
PACK_SLOT_EMPTY = (416, 448)
#: 保留区：写 0，读不解释
PACK_RESERVED = (448, 1024)


# --- 槽内公共字段（位区间，相对槽起点）--------------------------------------

SLOT_STATE = (0, 32)
SLOT_WRITE_CHECK = (32, 160)


# --- 三种槽形态 -------------------------------------------------------------

#: 链首头槽：六个计数之后是本段自述区
HEADER_START_SLOT_NUM = (160, 192)
HEADER_START_SLOT_END = (192, 224)
HEADER_START_DATA_SLOT_NUM = (224, 256)
HEADER_START_DATA_SLOT_END = (256, 288)
HEADER_START_BODY_SIZE = (288, 320)
HEADER_START_ATTR_NUM = (320, 352)
#: 链首头槽自述区起点（位）；容量见 `header_start_attr_capacity`
HEADER_START_ATTR_BITS = 352

#: 溢出头槽：只报本段条数，不重复六个计数
HEADER_MID_ATTR_NUM = (160, 192)
#: 溢出头槽自述区起点（位）
HEADER_MID_ATTR_BITS = 192

#: data 槽的槽体起点（位）
DATA_BODY_BITS = 160


# --- 自述区内的固定字段 -----------------------------------------------------

#: 每个头槽各一份，同值
BLOCK_ID = (0, 128)
BLOCK_ID_BYTES = 16

#: 自述区条目框架：`<名长:int32><名:utf-8><值长:int32><值:字节>`，长度按**字节**计。
#: `block_self_attr_num` 数的是条目**个数**，不是位长——字典有多大由条数说了算。
ATTR_NAME_LEN_BYTES = 4
ATTR_VALUE_LEN_BYTES = 4
#: 一条条目的固定开销（字节）：两个长度字段
ATTR_ENTRY_OVERHEAD = ATTR_NAME_LEN_BYTES + ATTR_VALUE_LEN_BYTES


# --- `slot_state` 的五个魔数（32 位，两两汉明距离 ≥ 14）---------------------

STATE_HEADER_START = 0x9E3779B1
STATE_HEADER_MID = 0x85EBCA77
STATE_DATA_MID = 0x589965CC
STATE_DATA_END = 0xC2B2AE3D
STATE_EMPTY = 0x00000000


# --- 格式事实依据的指纹 -----------------------------------------------------

#: `config/format.txt` 的带盐 sha256（`scripts/stamp_version.py` 同一套算法）；
#: 既是该文件的版本标记，也是 park 头 `version` 字段的值——「管格式不管数据」。
FORMAT_VERSION_HEX = "077ab2aca25ea8df0a51d5b2d1e15208bb8d97c4c6a18830050d0fbb9ef6f766"
FORMAT_VERSION = bytes.fromhex(FORMAT_VERSION_HEX)


# --- 换算与派生 -------------------------------------------------------------


def bits_to_bytes(bits: int) -> int:
    """位换算成字节数，向上取整。

    Args:
        bits: 位数。

    Returns:
        至少能装下这么多位的字节数。
    """
    return -(-bits // BITS_PER_BYTE)


def byte_offset(bits: int) -> int:
    """位偏移换算成字节偏移。

    Args:
        bits: 位偏移。

    Returns:
        字节偏移。

    Raises:
        ValueError: 位偏移不是整字节。
    """
    if bits % BITS_PER_BYTE:
        raise ValueError(f"位偏移 {bits} 不是整字节")
    return bits // BITS_PER_BYTE


def field_slice(bounds: tuple[int, int]) -> slice:
    """把位区间换成字节切片。

    Args:
        bounds: 位区间 (起点, 终点)，终点不含。

    Returns:
        对应的字节切片。

    Raises:
        ValueError: 区间端点不是整字节。
    """
    start, end = bounds
    return slice(byte_offset(start), byte_offset(end))


def read_uint32(data: bytes | bytearray, bounds: tuple[int, int]) -> int:
    """按小端读一个 32 位字段；计数与魔数都走它。

    Args:
        data: 整段字节。
        bounds: 字段的位区间。

    Returns:
        读到的值，按无符号解释。
    """
    return int.from_bytes(data[field_slice(bounds)], "little")


def write_uint32(data: bytearray, bounds: tuple[int, int], value: int) -> None:
    """按小端写一个 32 位字段；`slot_state` 这类魔数走它。

    Args:
        data: 整段字节，就地改写。
        bounds: 字段的位区间。
        value: 要写入的值。

    Raises:
        ValueError: 取值不是 32 位无符号数。
    """
    if not 0 <= value <= UINT32_MAX:
        raise ValueError(f"{value} 超出 32 位无符号范围")
    data[field_slice(bounds)] = value.to_bytes(4, "little")


def write_int32(data: bytearray, bounds: tuple[int, int], value: int) -> None:
    """按小端写一个 int32 字段；六个计数走它。

    Args:
        data: 整段字节，就地改写。
        bounds: 字段的位区间。
        value: 要写入的值。

    Raises:
        ValueError: 取值不在 int32 的非负范围内。
    """
    if not 0 <= value <= INT32_MAX:
        raise ValueError(f"{value} 超出 int32 非负范围")
    write_uint32(data, bounds, value)


def check_slot_size(slot_size: int) -> None:
    """校验槽长：不小于下界，且整字节。

    Args:
        slot_size: 槽长（位）。

    Raises:
        ValueError: 槽长过小，或不是整字节（实现按字节读写，事实依据里的偏移也都是 32 位对齐）。
    """
    if slot_size < SLOT_SIZE_MIN:
        raise ValueError(f"槽长 {slot_size} 位小于下界 {SLOT_SIZE_MIN} 位")
    if slot_size % BITS_PER_BYTE:
        raise ValueError(f"槽长 {slot_size} 位不是整字节")


def header_start_attr_capacity(slot_size: int) -> int:
    """链首头槽能放多少位自述属性（`slot_size − 480`）。

    Args:
        slot_size: 槽长（位）。

    Returns:
        本段属性的位数上限。
    """
    return slot_size - HEADER_START_ATTR_BITS - BLOCK_ID[1]


def header_mid_attr_capacity(slot_size: int) -> int:
    """溢出头槽能放多少位自述属性（`slot_size − 320`）。

    Args:
        slot_size: 槽长（位）。

    Returns:
        本段属性的位数上限。
    """
    return slot_size - HEADER_MID_ATTR_BITS - BLOCK_ID[1]


def data_body_capacity(slot_size: int) -> int:
    """一个 data 槽能放多少位块体（`slot_size − 160`）。

    Args:
        slot_size: 槽长（位）。

    Returns:
        槽体的位数上限。
    """
    return slot_size - DATA_BODY_BITS

# OnCasket

OnCasket 是单机存储引擎内核。磁盘格式分物理三层：**hub**（目录）、**park**
（定长文件 `<唯一名>.oncat`）、**slot**（park 内的定长格）；逻辑块（block）是一段
**不跨 park** 的连续槽。槽位永不摘除 —— 位置即身份。

设计与路线图见 [`docs/`](docs/)。

## 许可

Apache-2.0，见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。

运行时依赖的许可证清单见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

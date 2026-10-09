# OnCasket

Single-machine storage engine kernel: three on-disk layers (hub, park, slot); a block never crosses a park.

On disk, a **hub** is a directory, a **park** is a fixed-size `<name>.oncat` file, and a **slot** is a
fixed-size cell inside a park; a logical block is a run of contiguous slots.

Design and roadmap live in [`docs/`](docs/) (Chinese).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The licenses of all runtime dependencies are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

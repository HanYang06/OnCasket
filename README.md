# OnCasket

OnCasket is a single-machine storage engine kernel. The on-disk format has three
physical layers: **hub** (a directory), **park** (a fixed-size `<name>.oncat` file),
and **slot** (a fixed-size cell inside a park); a logical block is a run of
contiguous slots that never crosses a park.

Design and roadmap live in [`docs/`](docs/) (Chinese).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The licenses of all runtime dependencies are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

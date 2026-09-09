# Replay fixtures

Real Age of Empires II replay files used by the test suite. Sourced from
[aoc-mgz](https://github.com/happyleavesaoc/aoc-mgz) (MIT, © 2021 happyleavesaoc)
and redistributed under those terms.

Each one is here because it exercises a different parser path:

| File | Why it is here |
| --- | --- |
| `de-25.02.aoe2record` | Queue commands decode, so production metrics are available. Both players reach Castle Age. |
| `de-62.0.aoe2record` | Newer version whose queue commands do *not* decode — the case where production metrics must report `unavailable` rather than zero. |
| `de-13.03.aoe2record` | Too old for the parser. Must raise `ReplayParseError`, not crash. |

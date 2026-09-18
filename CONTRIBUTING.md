# Contributing

NightSky Atlas values small, reproducible changes. Before opening a pull
request, run:

```bash
make check
```

Do not commit downloaded catalogues, generated atlas artifacts, `.env` files,
or API keys. Changes to catalogue or geometry data must include provenance and
licensing information in `docs/DATA_SOURCES.md` and the adjacent fixture
metadata.

The project contract and architectural constraints are in `AGENTS.md`.

# AGENTS.md

Project guidance for AI coding agents (OpenCode, Cursor, etc.) working in this repository.

For full architecture, rules, and build order see [instructions.md](instructions.md).

---

## Commands

```bash
uv sync                                                   # install deps
uv run pytest -v                                          # run all tests
uv run pytest tests/unit/detector/test_anomaly.py -v     # run a single test file
uv run ruff check .                                       # lint
uv run ruff format .                                      # format
```

---

## Key conventions

- All Pydantic models live in `src/schema/models.py` — never `dataclass`/`TypedDict`
- `detector/` and `scorer/` are **pure functions** — no I/O, no DB access
- `storage/db.py` is the only layer that touches SQLite
- All `datetime` values must carry `tzinfo=UTC`; use `get_settings()` (never `os.environ`) for config
- Conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`
- Tests in `tests/unit/`, fixtures in `tests/fixtures/`

# Contributing

This repository is the **reference implementation** of the
[Power-Lab Code Standards](https://github.com/Power-Lab/.github/blob/main/CONTRIBUTING.md).
Read those first — they cover repository layout, naming, config-driven runs, dependencies, and
hygiene for all lab repos.

## Quick checklist

- **Style:** Julia is formatted with `JuliaFormatter` (`.JuliaFormatter.toml`); Python with
  `ruff` (`pyproject.toml`). Run them before committing:
  ```bash
  julia -e 'using JuliaFormatter; format(".")'
  ruff format . && ruff check --fix .
  ```
- **Naming:** `snake_case` for Julia/Python functions and filenames.
- **No edit-the-source configuration:** new run parameters go in `config.json` / `scenario_*.yml`,
  not hardcoded.
- **Don't commit** `.DS_Store`, `__pycache__/`, `.ipynb_checkpoints/`, or large outputs.
- **Verify the demo still runs** (Maluku test case) and that the committed reference results in
  `results/base_maluku_2030_reference/` are unchanged — if they change, that's a real result
  change and must be explained in the PR.

Major changes should be discussed in an issue first to keep the framework consistent.

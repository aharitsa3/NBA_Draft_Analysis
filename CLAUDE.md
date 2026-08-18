# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git / PR workflow

This repo uses `gh` (GitHub CLI) for PRs. Remote: `aharitsa3/NBA_Draft_Analysis`. Default branch: `main`.

1. Create a branch (branch off `main` unless told otherwise):
   ```
   git checkout -b my-feature-branch
   ```

2. Make changes, then commit:
   ```
   git add <files>
   git commit -m "message"
   ```

3. Push the branch:
   ```
   git push -u origin my-feature-branch
   ```

4. Create a PR:
   ```
   gh pr create --title "..." --body "..." --base main
   ```

5. Merge the PR (after review/checks pass):
   ```
   gh pr merge --squash
   ```
   (or `--merge` / `--rebase` depending on preference)

Never push, create, or merge without explicit confirmation from the user each time.

### Known push/PR gotchas

- `git push` can fail with `RPC failed; HTTP 400 ... unexpected disconnect while reading sideband packet` on larger pushes. Retry with a bigger buffer as a one-off flag (don't change git config permanently):
  ```
  git -c http.postBuffer=524288000 -c http.version=HTTP/1.1 push ...
  ```
- If `gh pr create` fails with `The <branch> branch has no history in common with main`, local `main` and `origin/main` have diverged into unrelated histories (e.g. after a local repo restore/reinit). Confirm with the user before force-pushing `main` to reconcile — this rewrites remote history.

## Stack & running the pipeline

Python 3.10+. Not an installable package — run everything from the repo root. Install deps with `pip install -r requirements.txt`. See `README.md` for full setup/usage detail; this section covers only what's easy to get wrong.

- Full pipeline: `python pipeline.py` (skips stages whose outputs already exist; `--force` to recompute; `--stages a b c` to run a subset)
- Dashboard: `streamlit run dashboard/app.py` (reads only precomputed `processed_data/`, pipeline must have run first)
- Report export: `python -m reports.export --team BOS --format both`
- Tests: `python -m pytest tests/`

## Linting

This repo uses `ruff` for Python linting. Run it with:
```
ruff check .
```
Config lives in `pyproject.toml` (`[tool.ruff]`).

## Critical gotchas

- Pipeline stages cache by output-file existence, not by hashing inputs — editing an upstream module and re-running won't pick up the change without `--force`.
- The `model` stage rewrites `features/training_table.parquet` in place (replaces the Phase 2 placeholder target); re-running `features` alone afterward won't undo that.
- `data/` is strictly read-only; `storage/io.py` actively blocks writes outside `processed_data/`.
- Always say "PPS" / "Projected Production Score", never "VORP" — real VORP/BPM/Win Shares aren't in the dataset and are deliberately excluded, even as inputs.
- Only Pure BPA (best-player-available) ranking exists — no positional-fit adjustment. Don't imply otherwise.
- Player identity joins are done by normalized name, never by id (ids differ across NCAA/NBA/picks/order sources). Check `identity/name_overrides.py` first for name-matching bugs.
- `ANTHROPIC_API_KEY` goes in a `.env` file at repo root, loaded via `storage/config.py`. Note: the README references a `.env.example` that doesn't currently exist in the repo.

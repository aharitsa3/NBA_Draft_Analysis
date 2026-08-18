# CLAUDE.md

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

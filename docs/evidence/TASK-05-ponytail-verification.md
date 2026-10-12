# TASK-05 Ponytail pin verification (DEC-0020 re-run)

**Provenance:** Builder re-run of the `development-workflow` section 4 verification, on 2026-10-12, by a Builder agent working on branch `fix/task-05-verification`. This is a sanitized record of the check. It is not an independent Tester report.

## Authority

- Specs: `https://github.com/juandcn9/ABM-Service-Specs`, `origin/main` `fb32e092b7bab696c0dcad7ef76eb7ef7fa08c65` (read for this check; `SPEC_VERSION` in this repository records the same commit, `v1.9.13`).
- Pinned source: `https://github.com/DietrichGebert/ponytail`, tag `v5.1.0`, commit `9cc65d03aa2da1db7121b912d03596409ee340b8` (`development-workflow` section 4; DEC-0013; DEC-0020).
- Code base revision checked: `df97fa717fd619e37f9618e6d024c5b1a66df6ee` (`origin/main` at the start of the run).

## Installed copy

- Install path: `%USERPROFILE%/.claude/plugins/cache/ponytail/ponytail/5.1.0` (the plugin cache folder `ponytail/ponytail/5.1.0`).
- Manifest `.claude-plugin/plugin.json` reports version `5.1.0`.
- Install record (`installed_plugins.json`, entry `ponytail@ponytail`, scope user): version `5.1.0`, `gitCommitSha` `9cc65d03aa2da1db7121b912d03596409ee340b8`, installed 2026-10-09. The record corroborates the comparison below and does not replace it.
- Installation method: not independently verified in this run. The install record names the plugin `ponytail@ponytail`, scope user.

## Commands and steps

1. `git ls-remote https://github.com/DietrichGebert/ponytail refs/tags/v5.1.0 refs/tags/v5.1.0^{}` returned `9cc65d03aa2da1db7121b912d03596409ee340b8` for the tag. The tag is a lightweight tag that points directly to the commit.
2. Shallow clone of the tag (`git clone --depth 1 --branch v5.1.0`) into a temporary directory outside the repository. `git rev-parse HEAD` returned `9cc65d03aa2da1db7121b912d03596409ee340b8`.
3. `git ls-tree -r HEAD` on the clone, saved to a temporary listing file.
4. A read-only comparison script (not stored in the repository) walked every tree entry. For each entry it checked: the file exists; it is not a symlink; the mode is `100644` or `100755`; the git blob hash of the installed bytes equals the tree blob. If the exact hash differs and the file has no NUL byte, it retried with CRLF removed (`tr -d '\r'`) and compared again. Then it listed every installed file that is not in the tree.
5. The temporary clone and temporary listing and script files were removed after the comparison (see Cleanup below).

## Counts

| Measure | Result |
|---|---|
| Pinned tree entries (`git ls-tree -r`) | 199 (199 `blob`, all mode `100644`; no symlink, submodule or other type) |
| Tree entries matching the installed file byte for byte (git blob hash) | 42 (binary files) |
| Tree entries matching only after CRLF normalization | 157 (text files; 42 + 157 = 199) |
| Tree entries missing from the installed copy | 0 |
| Tree entries present but not a regular file | 0 |
| Tree entries with a different hash | 0 |
| Tree entries with a bad mode | 0 |
| Installed regular files | 201 |
| Installed files not in the tree | 2, both under `.in_use/` (runtime markers `.in_use/1608` and `.in_use/12196`) |
| Installed files not in the tree, outside `.in_use/` | 0 |
| Symbolic links in the installed copy | 0 |
| Case-only name collisions in the installed copy | 0 |

## Result

**PASS.** The installed Ponytail 5.1.0 copy matches the pinned tree of `v5.1.0` (`9cc65d03aa2da1db7121b912d03596409ee340b8`) file by file. No difference was found outside the permitted `.in_use/` runtime markers. This is the check that `development-workflow` section 4 requires at the start of each Claude Code task.

Note: the work item records the earlier verification of 2026-10-10 as 199 files on each side with one runtime marker. This re-run finds 199 matching files with two runtime markers. The marker count differs only by the runtime marker files under `.in_use/`, which are excluded by the rule.

## Cleanup

The temporary clone of the pinned tag, the temporary tree listing and the comparison script were deleted after the run. The installed plugin was not modified. Nothing from the upstream repository was executed.

## Non-claims

- This record does not change any status. TASK-05 remains `Implemented` in `docs/work-items/TASK-05.md`.
- This record is not an independent Tester report and does not close Gate 8 by itself.
- No secret, credential or personal data is recorded here.

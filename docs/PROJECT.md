# Tribe Seek — project identity and tracking

2026-11-28 · branch `main-ours` · 86 commits ahead of upstream

Tribe Seek is no longer "Nicotine+ with patches". It is a private collective
instrument that happens to share Nicotine+'s engine lineage. Track it as its own
product, with upstream treated as a security source, not a parent.

## 1. Repository

Today:

- `origin` = `nicotine-plus/nicotine-plus` (read-only upstream)
- `fork` = `santerotribe/nicotine-plus` (our work, but still in the fork network)
- branch `main-ours`, 86 commits ahead

A GitHub fork keeps the "forked from" badge, defaults pull requests to upstream,
and cannot be made standalone. The clean move is a **new private repo**:

```sh
gh repo create santerotribe/tribeseek --private --source=. \
  --remote=tribeseek --push

git remote rename origin upstream      # nicotine-plus, fetch-only
git remote rename tribeseek origin     # our repo, default
git remote remove fork                 # or keep it as "nicotine-archive"
git branch -m main-ours main
git push -u origin main
```

Then update the two docs that name `main-ours` (`HANDOFF.md`,
`HANDOFF-PROMPT.md`, `ROADMAP.md`) and set the new repo's default branch to
`main`.

Keep `upstream` configured; do not push to it.

## 2. Versioning

Three numbers, deliberately separate:

| Thing | Current | Where |
|---|---|---|
| App | `0.1.0` | `native/TribeSeek` bundle version |
| Engine API | `2` | `/health` → `"api": 2` |
| Ledger format | `1` per entry, directory | `pynicotine/digging/rolodex.py` |
| Crate schema | `1` | `crate.json` `"version"` |

Tag releases `v0.1.0`, `v0.2.0`; bump the API only when a payload shape breaks
(it already has once: folders map → array). Add `CHANGELOG.md` in Keep a
Changelog form with Added / Changed / Fixed per tag.

## 3. Milestones

One GitHub milestone per roadmap phase, named `M0`…`M6`:

| Milestone | Scope (see ROADMAP) | State |
|---|---|---|
| M0 Identity and spine | rename, rail, deck, shelf shape | done |
| M1 Search workspace | tabs, paging, grouping | tabs done; grouping open |
| M2 Shelf | dig, bins, filter, freshness | done |
| M3 Crates | sample/DJ, move, delete | done |
| M4 Separation | Passage/stemctl, Live insertion | on hold |
| M5 Rolodex + distribution | ledger, status, packaging | ledger/status done; packaging open |
| M6 v2 | related artists, fingerprint dedupe, key detection | not started |

Use one issue per concrete change, labelled by area: `engine`, `native`,
`shelf`, `crates`, `ledger`, `rig`, `packaging`, `docs`, `review`. Link the
issue from the commit body. The roadmap stays the directional document; issues
are the unit of work. Do not duplicate status in three places — `ROADMAP.md`
for phases, milestone for completion, issue for the task.

## 4. Upstream policy

- `upstream` is **read-only**. Never merge it wholesale: GTK refactors and
  release churn would swamp the fork.
- Cherry-pick security and protocol fixes only, with the upstream commit hash in
  the message. Re-run both suites after each pick.
- Keep SPDX headers and the GPL-3.0-or-later notices. The fork is GPL; sharing
  builds with the collective means the source must be available to them. A
  private repo is fine as long as members can get the source.
- Record each picked commit in `CHANGELOG.md` under "Upstream".

## 5. Release checklist (when packaging starts)

1. Both suites green; `pylint` clean on `engineapi` and `digging`.
2. Bump app version, add the changelog entry, tag.
3. Build the signed app; embed the engine; smoke test on a clean profile.
4. Notarize, staple, publish to the collective only.
5. Keep the previous tag installable for rollback.

## 6. What stays in the repo

- `docs/ROADMAP.md` — direction and phase scope.
- `docs/HANDOFF.md` + `HANDOFF-PROMPT.md` — session continuity.
- `docs/REVIEW-*.md` — audit history.
- `docs/PROJECT.md` — this file: identity, versioning, tracking, release.
- `CHANGELOG.md` — releases.

## 7. Decision

Create `santerotribe/tribeseek` (private) and move the remotes as in §1, or keep
the fork and accept the upstream association. Recommendation: the new repo —
the code, the issues, and the releases should all say Tribe Seek, and upstream
should be a remote you fetch from, not the place the project lives.

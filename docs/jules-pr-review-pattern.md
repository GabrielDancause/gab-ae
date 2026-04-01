# Jules PR Review & Rework Pattern

*Established: April 1, 2026*

## The Flow

1. **Find something to fix** → scan D1 data, check articles, review code
2. **Create a GitHub Issue** → specific bugs, acceptance criteria, label `agent:jules`
3. **Dispatch Jules session** → reference the issue URL, `AUTO_CREATE_PR`, single file focus
4. **Wait for PR** → Gab tells you when it lands (don't poll, don't cron)
5. **Review the diff** → `gh pr diff {number} --color never`
6. **Comment the PR** → specific fixes needed, code examples, clear instructions
7. **Jules reads the comment and pushes fixes** → same PR, same branch, no new session
8. **Review again** → repeat 6-7 until clean
9. **Merge** → `gh pr merge {number} --squash --delete-branch && git pull`
10. **Close issue** → usually auto-closed via `Fix #N` in PR title

## Critical Rules

### DO
- Use `AUTO_CREATE_PR` for the **first** session only
- Comment the PR directly — Jules monitors PR comments and pushes fixes
- Be specific in comments: what's wrong, what the fix should look like, code examples
- Wait for Gab to tell you when a PR lands
- Use `gh pr diff` to review (read-only)
- Label issues: `agent:jules`, `bug`/`enhancement`, `queued`

### DO NOT
- **NEVER dispatch a new Jules session to rework a PR** — comment the PR instead
- **NEVER merge without Gab's approval**
- **NEVER close PRs** — only Gab or a merge closes them
- **NEVER use `AUTO_CREATE_PR` on an existing branch** — it nukes the old PR
- **NEVER dispatch Jules from heartbeat** — heartbeat is passive/report-only
- **NEVER tell Jules to "read the PR comments"** via a new session prompt — he can't

## What We Learned the Hard Way

### Rework = Comment, NOT New Session
- New sessions with `AUTO_CREATE_PR` on the same branch **delete the old branch and close the old PR**
- Jules monitors PR comments natively — just comment and he pushes fixes
- This costs ZERO sessions for rework iterations

### Heartbeat Must Be Passive
- Old heartbeat instructions can be cached in running sessions
- Even after updating HEARTBEAT.md, in-flight heartbeats use old instructions
- Heartbeat closed a PR because it had stale "merge if good" instructions
- Solution: HEARTBEAT.md now says NEVER touch PRs (at the very top, in caps)

### Jules Creates Extra Files
- Always say "Do NOT create any new files" and "ONLY modify [filename]"
- Jules still sometimes creates `parse_title.js`, `pnpm-lock.yaml`, Python scripts
- Check the diff for unexpected new files before merging

### `gh` CLI Uses Gab's Account
- All `gh` actions show as "GabrielDancause" — not "David" or "Jules"
- If a PR was merged/closed by "GabrielDancause", it could be the heartbeat or David

### Zombie Sessions
- Jules sessions can't be cancelled via API
- A PAUSED session can wake up and interfere with current work
- Always archive/close completed sessions in Jules UI to prevent this

## Issue Template

```markdown
## Summary
[What's broken, 1-2 sentences]

## Bug 1: [Name]
**Example:** [concrete example from production data]
**Root cause:** [why it happens]
**Fix:** [specific code change needed]

## Files to modify
- `src/file.js` — this is the ONLY file to change

## Rules
- Reference this issue in commit messages
- Do NOT add pnpm-lock.yaml or lock files
- Do NOT create new files
```

## Jules Dispatch Template

```json
{
  "prompt": "Fix all bugs described in GitHub Issue #N: https://github.com/GabrielDancause/gab-ae/issues/N\n\nThe ONLY file to modify is src/file.js. Do NOT create any new files. Do NOT add pnpm-lock.yaml or lock files.\n\nReference #N in commit messages.\n\nnull over fake data, always.",
  "sourceContext": {
    "source": "sources/github/GabrielDancause/gab-ae",
    "githubRepoContext": {"startingBranch": "main"}
  },
  "automationMode": "AUTO_CREATE_PR",
  "title": "Fix [description] (#N)"
}
```

## PR Review Comment Template

```markdown
## Review — [overall assessment]

### ✅ What's solid
- [list what's good — be specific]

### 🔧 Fix 1: [name]
[What's wrong]
**Fix:** [exactly what to change, with code if helpful]

### 🔧 Fix 2: [name]
[What's wrong]
**Fix:** [exactly what to change]

---
Push fixes to this branch. Reference #N in commits.
```

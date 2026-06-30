#!/usr/bin/env bash
set -euo pipefail

if [[ "$PWD" == *".claude/worktrees"* ]]; then
  echo "ERROR: Deploying from a worktree directory causes cron schedule issues."
  echo "Run 'npx wrangler deploy' from the main repo at ~/Desktop/gab-ae instead."
  exit 1
fi

exec npx wrangler deploy "$@"

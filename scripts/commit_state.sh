#!/usr/bin/env bash
# Commit and push state.json, surviving concurrent runs.
#
# Overlapping runs both rewrite state.json, so a rebase is guaranteed to
# conflict. The freshest scrape is the one worth keeping: replay our state
# onto whatever main has and push again.
set -euo pipefail

cd "$(dirname "$0")/.."

git add state.json

if git diff --staged --quiet; then
  echo "state unchanged"
  exit 0
fi

tmp="$(mktemp)"
cp state.json "$tmp"

for attempt in 1 2 3; do
  git commit -qm "state: $(date -u +'%Y-%m-%dT%H:%M')"

  if git push -q origin HEAD:main; then
    echo "state pushed (attempt $attempt)"
    exit 0
  fi

  echo "push rejected — replaying state onto latest main"
  git fetch -q origin main
  git reset -q --hard origin/main
  cp "$tmp" state.json
  git add state.json

  if git diff --staged --quiet; then
    echo "state already current on main"
    exit 0
  fi
done

echo "could not push state after 3 attempts" >&2
exit 1

#!/usr/bin/env bash
# Check repeatedly inside one Actions job.
#
# GitHub drops the large majority of scheduled triggers for this account —
# a */15 cron yields ~8 runs/day, roughly one every 2-5 hours, measured
# across both a forked and a standalone repo. So instead of asking the
# scheduler for 96 firings a day, one job checks on an interval and exits
# before the 6-hour job ceiling. Each scheduler firing restarts the loop
# (concurrency cancel-in-progress replaces any loop still running).
#
# CHECK_INTERVAL   seconds between checks   (default 900 = 15 min)
# LOOP_DURATION    seconds to keep looping  (default 19800 = 5h30m)
set -uo pipefail

cd "$(dirname "$0")/.."

interval="${CHECK_INTERVAL:-900}"
duration="${LOOP_DURATION:-19800}"
deadline=$(( $(date +%s) + duration ))
iteration=0

events_blob() {
  python3 -c "import json,sys;print(json.dumps(json.load(open('state.json')).get('events',{}),sort_keys=True))" 2>/dev/null || echo ""
}

while :; do
  iteration=$(( iteration + 1 ))
  echo "::group::check $iteration"

  before="$(events_blob)"
  python check.py || echo "check failed — continuing"
  after="$(events_blob)"

  remaining=$(( deadline - $(date +%s) ))
  last=0
  [ "$remaining" -lt "$interval" ] && last=1

  # Commit only when the tracked events actually changed. checked_at alone
  # churns every iteration and would bury the log in noise. Always commit on
  # the final iteration so the job's last state survives.
  if [ "$before" != "$after" ] || [ "$last" -eq 1 ]; then
    scripts/commit_state.sh || echo "state commit failed — continuing"
  else
    echo "no event changes — not committing"
  fi

  echo "::endgroup::"

  if [ "$last" -eq 1 ]; then
    echo "loop finished after $iteration checks"
    exit 0
  fi

  sleep "$interval"
done

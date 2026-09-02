#!/usr/bin/env bash
set -euo pipefail

repo_dir="/home/exedev/.openclaw/workspace/calendar-view"
python_bin="/home/exedev/.openclaw/third-party/trainingpeaks-mcp/.venv/bin/python"

cd "$repo_dir"
"$python_bin" scripts/sync_trainingpeaks_plan.py
git add trainingpeaks-plan.json
if git diff --cached --quiet; then
  exit 0
fi
git commit -m "Refresh TrainingPeaks plan"
git push origin main

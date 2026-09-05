#!/usr/bin/env bash
# Standalone delta review: fixed Sol/xhigh, no implementation or fix loop.
set -euo pipefail
skill_dir="$(cd "$(dirname "$0")" && pwd -P)"
export CODEX_REVIEW_MODEL=gpt-5.6-sol
export CODEX_REVIEW_EFFORT=xhigh
exec bash "$skill_dir/../scripts/review.sh" "$@"

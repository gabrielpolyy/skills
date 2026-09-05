#!/usr/bin/env bash
# Standalone delta review: pinned to Codex Sol/xhigh, no implementation or fix loop.
# This is the only place a model is pinned; scripts/review.sh only has defaults.
set -euo pipefail
skill_dir="$(cd "$(dirname "$0")" && pwd -P)"
export REVIEW_BACKEND=codex
export REVIEW_MODEL=gpt-5.6-sol
export REVIEW_EFFORT=xhigh
exec bash "$skill_dir/../scripts/review.sh" "$@"

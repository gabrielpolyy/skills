#!/usr/bin/env bash
# Pin the reviewer; only an explicit --effort argument overrides its default.
set -euo pipefail
skill_dir="$(cd "$(dirname "$0")" && pwd -P)"
export REVIEW_BACKEND=codex
export REVIEW_MODEL=gpt-6-astra
export REVIEW_EFFORT=medium
exec bash "$skill_dir/../scripts/review.sh" "$@"

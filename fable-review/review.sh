#!/usr/bin/env bash
# Pin the reviewer; only an explicit --effort argument overrides its default.
set -euo pipefail
skill_dir="$(cd "$(dirname "$0")" && pwd -P)"
export REVIEW_BACKEND=claude
export REVIEW_MODEL=fable
export REVIEW_EFFORT=high
exec bash "$skill_dir/../scripts/review.sh" "$@"

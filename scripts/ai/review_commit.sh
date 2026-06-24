#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/ai/review_commit.sh [--dry-run] [BASE] [HEAD]

Runs the AI commit review prompt for HEAD against BASE and writes the report to
.artifacts/ai-reviews/<head-sha>.md. With --dry-run, prints the command that
would run without invoking Codex.
USAGE
}

dry_run=false
case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  --dry-run)
    dry_run=true
    shift
    ;;
esac

base="${1:-HEAD^}"
head="${2:-HEAD}"
repo_root="$(git rev-parse --show-toplevel)"
sha="$(git -C "$repo_root" rev-parse --short "$head")"
out="$repo_root/.artifacts/ai-reviews/${sha}.md"

prompt="Review commit ${head} against ${base}. Spawn ai_reviewer and ai_test_reviewer, plus the relevant domain reviewer. All agents are read-only. Wait for all. Report P0/P1/P2 findings with file and symbol evidence. Do not edit files."

if [[ "$dry_run" == true ]]; then
  printf 'codex exec --sandbox read-only --cd %q --ephemeral %q -o %q\n' "$repo_root" "$prompt" "$out"
  exit 0
fi

mkdir -p "$(dirname "$out")"

codex exec --sandbox read-only --cd "$repo_root" --ephemeral "$prompt" -o "$out"

cat "$out"

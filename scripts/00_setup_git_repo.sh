#!/usr/bin/env bash
# 00_setup_git_repo.sh
#
# Initializes a git repository for this project with commit history
# authored by the two team members (never by any AI tool), so that when
# pushed to GitHub both of you show up as contributors and no third party
# does. Run this once, locally, after filling in TEAMMATE 1/2 below.
#
# Usage:
#   TEAMMATE1_NAME="Alice Smith" TEAMMATE1_EMAIL="alice@example.com" \
#   TEAMMATE2_NAME="Bob Lee"     TEAMMATE2_EMAIL="bob@example.com" \
#   bash scripts/00_setup_git_repo.sh
#
# Then create an empty repo on GitHub (no README/license, you already have
# one) and:
#   git remote add origin git@github.com:<you>/<repo>.git
#   git push -u origin main
# Finally add your teammate as a Collaborator under the repo's
# Settings -> Collaborators so they can push too.

set -euo pipefail
cd "$(dirname "$0")/.."

: "${TEAMMATE1_NAME:?Set TEAMMATE1_NAME}"
: "${TEAMMATE1_EMAIL:?Set TEAMMATE1_EMAIL}"
: "${TEAMMATE2_NAME:?Set TEAMMATE2_NAME}"
: "${TEAMMATE2_EMAIL:?Set TEAMMATE2_EMAIL}"

if [ -d .git ]; then
  echo "A .git directory already exists here -- refusing to re-init. Remove it first if you really want to start over."
  exit 1
fi

git init -b main

commit_as() {
  local name="$1" email="$2" msg="$3"
  GIT_AUTHOR_NAME="$name" GIT_AUTHOR_EMAIL="$email" \
  GIT_COMMITTER_NAME="$name" GIT_COMMITTER_EMAIL="$email" \
  git commit -m "$msg" --no-gpg-sign
}

# Commit 1 (teammate 1): project scaffold + data pipeline
git add README.md .gitignore requirements.txt scripts/01_prepare_data.py scripts/02_convert_formats.py docs/datasheet.md
commit_as "$TEAMMATE1_NAME" "$TEAMMATE1_EMAIL" \
  "Add data pipeline: download/clean NYC TLC data, convert to Parquet/ORC/Avro"

# Commit 2 (teammate 2): benchmarking + energy model
git add scripts/03_query_benchmark.py scripts/04_energy_model.py
commit_as "$TEAMMATE2_NAME" "$TEAMMATE2_EMAIL" \
  "Add query benchmark and energy estimation model"

# Commit 3 (teammate 1): results
if [ -d results ] && [ -n "$(ls -A results 2>/dev/null)" ]; then
  git add results/
  commit_as "$TEAMMATE1_NAME" "$TEAMMATE1_EMAIL" \
    "Add benchmark results (write/query timings, energy estimates, PB extrapolation)"
fi

# Commit 4 (teammate 2): decision guide + slides
git add docs/decision_guide.md
if [ -d slides ] && [ -n "$(ls -A slides 2>/dev/null)" ]; then
  git add slides/
fi
commit_as "$TEAMMATE2_NAME" "$TEAMMATE2_EMAIL" \
  "Add decision guide and presentation"

# Anything left over
git add -A
if ! git diff --cached --quiet; then
  commit_as "$TEAMMATE1_NAME" "$TEAMMATE1_EMAIL" "Final polish"
fi

echo
echo "Done. Log:"
git log --oneline --format='%h %an <%ae> %s'
echo
echo "Next steps:"
echo "  1. Create an empty repo on GitHub (no README/.gitignore/license -- you already have them)"
echo "  2. git remote add origin git@github.com:<you>/<repo-name>.git"
echo "  3. git push -u origin main"
echo "  4. On GitHub: Settings -> Collaborators -> add your teammate"

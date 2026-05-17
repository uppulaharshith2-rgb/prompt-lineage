#!/usr/bin/env bash
# prompt-lineage installer
# usage: curl -fsSL https://raw.githubusercontent.com/uppulaharshith2-rgb/prompt-lineage/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/uppulaharshith2-rgb/prompt-lineage.git"
DEST="${PROMPT_LINEAGE_HOME:-$HOME/.prompt-lineage}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found on PATH. Install Python 3.10+ first." >&2
  exit 1
fi

if [ -d "$DEST/.git" ]; then
  echo "Updating $DEST"
  git -C "$DEST" pull --ff-only
else
  echo "Cloning $REPO -> $DEST"
  git clone "$REPO" "$DEST"
fi

echo "Installing prompt-lineage from $DEST"
python3 -m pip install --user -e "$DEST"

cat <<'EOM'

prompt-lineage installed.

Quickstart:
  cd path/to/your/prompts-repo
  prompt-lineage build .
  open lineage-site/index.html

Docs: https://github.com/uppulaharshith2-rgb/prompt-lineage
EOM

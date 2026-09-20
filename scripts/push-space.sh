#!/usr/bin/env bash
# Deploy mirror: push a clean tree of THIS repo to a Hugging Face Space.
#
# Usage:
#   HF_TOKEN=hf_xxx ./scripts/push-space.sh <hf-username> <space-name>
#
# Requirements:
#   - working tree must be fully committed (deploys are reproducible; what is
#     committed is what runs — `git archive HEAD` ships tracked files only,
#     so node_modules/.venv/untracked junk never leaves your machine)
#   - HF access token with WRITE permission (huggingface.co → avatar →
#     Settings → Access Tokens → Create new token, role: write)
#   - the Space already created as a Docker Space (see docs/DEPLOYMENT.md)
#
# Repeat the same command to redeploy after committing updates.
set -euo pipefail

HF_USER="${1:?Usage: push-space.sh <hf-username> <space-name>}"
SPACE="${2:?Usage: push-space.sh <hf-username> <space-name>}"
: "${HF_TOKEN:?Set HF_TOKEN to a write-role Hugging Face access token.}"

if [ -n "$(git status --porcelain)" ]; then
  echo "Refusing: working tree has uncommitted changes. Commit first so the" >&2
  echo "deployed code is reproducible, then re-run this script." >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
SHA="$(git rev-parse --short HEAD)"

# Tracked files only: build context stays small automatically.
git archive HEAD | tar -x -C "${STAGE}"

# The Space repo needs its own README with Docker frontmatter. This OVERWRITES
# the project readme inside the mirror only — GitHub keeps the real one.
cat > "${STAGE}/README.md" <<EOF
---
title: AI Learning Companion API
emoji: "\U0001F393"
colorFrom: blue
colorTo: navy
sdk: docker
app_port: 7860
pinned: false
---

# AI Learning Companion API (deploy mirror)

Backend + worker in a single container (\`Dockerfile\`, \`scripts/start-single.sh\`).
Canonical source lives on GitHub; this repo is pushed by \`scripts/push-space.sh\`.
Runtime config comes from Space secrets — see \`docs/DEPLOYMENT.md\`.
EOF

(
  cd "${STAGE}"
  git init -q -b main
  git add -A
  git -c user.name="deploy" -c user.email="deploy@local" commit -qm "deploy ${SHA}"
  git push "https://${HF_USER}:${HF_TOKEN}@huggingface.co/spaces/${HF_USER}/${SPACE}" main --force
)

echo "Pushed. Watch the build: https://huggingface.co/spaces/${HF_USER}/${SPACE}"
echo "Health check when live: https://${HF_USER}-${SPACE}.hf.space/api/v1/health"

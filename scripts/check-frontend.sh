#!/usr/bin/env bash
set -euo pipefail
# Frontend quality gate: typecheck + lint + tests + build.
cd "$(dirname "$0")/../frontend"
npm run typecheck
npm run lint
npm test -- --run
npm run build

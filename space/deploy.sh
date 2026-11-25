#!/bin/sh
# Deploy the web demo to a Hugging Face Space.
#   1. Log in once:  uvx --from huggingface_hub hf auth login   (token with write access)
#   2. Run:          sh space/deploy.sh [owner/space-name]
set -e
SPACE="${1:-andreolf/rubato}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$(mktemp -d)"
cp -R "$ROOT/space/." "$BUILD/"
cp "$ROOT/skills/rubato/scripts/rubato.py" "$BUILD/rubato.py"
HF="uvx --from huggingface_hub hf"
$HF repos create "$SPACE" --repo-type space --space-sdk docker --public --exist-ok
$HF upload "$SPACE" "$BUILD" . --repo-type space --exclude "deploy.sh" --commit-message "Deploy Rubato demo"
echo "Deployed: https://huggingface.co/spaces/$SPACE"

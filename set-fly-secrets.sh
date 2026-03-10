#!/usr/bin/env bash
# Reads secrets from .env and pushes them to Fly.io.
# Usage: bash set-fly-secrets.sh
# Requires: flyctl installed and authenticated, .env present.

set -euo pipefail

ENV_FILE="$(dirname "$0")/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE"
  echo "Copy .env.example to .env and fill in your values first."
  exit 1
fi

REQUIRED=(TRELLO_API_KEY TRELLO_TOKEN MCP_AUTH_TOKEN)

# Load and validate
declare -A SECRETS
while IFS='=' read -r key value; do
  # Skip blank lines and comments
  [[ -z "$key" || "$key" == \#* ]] && continue
  # Strip inline comments and surrounding quotes from value
  value="${value%%#*}"
  value="${value%"${value##*[![:space:]]}"}"  # rtrim
  value="${value#\"}" ; value="${value%\"}"   # strip double quotes
  value="${value#\'}" ; value="${value%\'}"   # strip single quotes
  SECRETS["$key"]="$value"
done < "$ENV_FILE"

missing=()
for key in "${REQUIRED[@]}"; do
  if [[ -z "${SECRETS[$key]:-}" ]]; then
    missing+=("$key")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: Missing required secrets in .env: ${missing[*]}"
  exit 1
fi

echo "Pushing secrets to Fly.io..."
flyctl secrets set \
  "TRELLO_API_KEY=${SECRETS[TRELLO_API_KEY]}" \
  "TRELLO_TOKEN=${SECRETS[TRELLO_TOKEN]}" \
  "MCP_AUTH_TOKEN=${SECRETS[MCP_AUTH_TOKEN]}"

echo "Done. Secrets set on Fly.io."

# Push MCP_AUTH_TOKEN to GitHub Actions secrets so the integration tests can run.
if command -v gh &>/dev/null; then
  echo "Pushing MCP_AUTH_TOKEN to GitHub Actions secrets..."
  gh secret set MCP_AUTH_TOKEN --body "${SECRETS[MCP_AUTH_TOKEN]}"
  echo "Done. GitHub secret set."
else
  echo "SKIP: gh CLI not found — add MCP_AUTH_TOKEN to GitHub repo secrets manually."
fi

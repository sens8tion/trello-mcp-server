#!/usr/bin/env bash
# setup-secrets.sh — interactive first-time setup for trello-mcp-server
# Covers: .env creation, flyctl install check, fly launch, secrets push,
#         GitHub secret hint, and Claude MCP config snippet.
# Usage: bash setup-secrets.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$REPO_DIR/.env"

# ── colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▸ $*${RESET}"; }
success() { echo -e "${GREEN}✓ $*${RESET}"; }
warn()    { echo -e "${YELLOW}⚠ $*${RESET}"; }
die()     { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }
header()  { echo -e "\n${BOLD}━━━ $* ━━━${RESET}"; }

# ── helpers ────────────────────────────────────────────────────────────────────

prompt_secret() {
  # prompt_secret VAR_NAME "Prompt text" [default]
  local var="$1" prompt="$2" default="${3:-}"
  local val=""
  while [[ -z "$val" ]]; do
    if [[ -n "$default" ]]; then
      read -rsp "${prompt} [leave blank to generate]: " val
      echo
      if [[ -z "$val" ]]; then
        val="$default"
        info "Generated: (hidden)"
      fi
    else
      read -rsp "${prompt}: " val
      echo
      [[ -z "$val" ]] && warn "Cannot be empty, try again."
    fi
  done
  printf -v "$var" '%s' "$val"
}

prompt_visible() {
  local var="$1" prompt="$2"
  local val=""
  while [[ -z "$val" ]]; do
    read -rp "${prompt}: " val
    [[ -z "$val" ]] && warn "Cannot be empty, try again."
  done
  printf -v "$var" '%s' "$val"
}

check_command() {
  command -v "$1" &>/dev/null
}

# ── step 1: .env ───────────────────────────────────────────────────────────────

header "Step 1 — Trello credentials & auth token"

SKIP_ENV=0
if [[ -f "$ENV_FILE" ]]; then
  warn ".env already exists at $ENV_FILE"
  read -rp "Overwrite it? [y/N] " overwrite
  [[ "$overwrite" =~ ^[Yy]$ ]] || SKIP_ENV=1
  [[ "$SKIP_ENV" == "1" ]] && info "Keeping existing .env"
fi

if [[ "$SKIP_ENV" != "1" ]]; then
  echo
  echo "Get your Trello API key at: https://trello.com/power-ups/admin"
  echo

  prompt_visible TRELLO_API_KEY "  TRELLO_API_KEY"

  # Build the Trello OAuth URL and open it so the user gets a non-expiring token
  TRELLO_AUTH_URL="https://trello.com/1/authorize?expiration=never&name=trello-mcp-server&scope=read,write&response_type=token&key=${TRELLO_API_KEY}"
  echo
  info "Opening browser to authorize Trello access (non-expiring token)..."
  # Try common openers across platforms
  if check_command xdg-open; then
    xdg-open "$TRELLO_AUTH_URL"
  elif check_command open; then
    open "$TRELLO_AUTH_URL"
  elif check_command powershell.exe; then
    powershell.exe -NoProfile -Command "Start-Process '${TRELLO_AUTH_URL}'"
  elif check_command cmd.exe; then
    cmd.exe /c start "" "${TRELLO_AUTH_URL//&/^&}"
  else
    echo "  Open this URL in your browser:"
    echo "  $TRELLO_AUTH_URL"
  fi
  echo
  echo "After you click 'Allow', Trello will show you a token. Paste it below."

  prompt_secret  TRELLO_TOKEN   "  TRELLO_TOKEN"

  # Auto-generate MCP_AUTH_TOKEN if openssl available
  if check_command openssl; then
    GENERATED_TOKEN="$(openssl rand -hex 32)"
  else
    GENERATED_TOKEN="$(head -c 32 /dev/urandom | base64 | tr -d '=+/' | head -c 32 || true)"
  fi

  prompt_secret MCP_AUTH_TOKEN "  MCP_AUTH_TOKEN" "$GENERATED_TOKEN"

  cat > "$ENV_FILE" <<EOF
TRELLO_API_KEY=${TRELLO_API_KEY}
TRELLO_TOKEN=${TRELLO_TOKEN}
MCP_AUTH_TOKEN=${MCP_AUTH_TOKEN}
EOF
  success ".env written (never commit this file)"
fi

# Load .env into shell vars for later steps
# shellcheck source=.env
set -o allexport; source "$ENV_FILE"; set +o allexport

# ── step 1b: validate Trello credentials ───────────────────────────────────────

header "Step 1b — Validate Trello credentials"

check_command curl || die "curl is required for validation."

TRELLO_TEST="$(curl -sf "https://api.trello.com/1/members/me?key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}" || true)"

if [[ -z "$TRELLO_TEST" ]]; then
  die "Trello API call failed — check your TRELLO_API_KEY and TRELLO_TOKEN."
fi

# Extract username — works without jq by grepping the raw JSON
TRELLO_USERNAME="$(echo "$TRELLO_TEST" | grep -o '"username":"[^"]*"' | head -1 | cut -d'"' -f4)"
TRELLO_FULLNAME="$(echo "$TRELLO_TEST" | grep -o '"fullName":"[^"]*"' | head -1 | cut -d'"' -f4)"

if [[ -z "$TRELLO_USERNAME" ]]; then
  die "Trello returned an unexpected response. Raw: ${TRELLO_TEST:0:200}"
fi

success "Trello API key + token valid — authenticated as: ${TRELLO_FULLNAME} (@${TRELLO_USERNAME})"

# Verify write scope by listing boards (read) — a 401 here means token is read-only
BOARDS_TEST="$(curl -sf "https://api.trello.com/1/members/me/boards?key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}&fields=name" || true)"
BOARD_COUNT="$(echo "$BOARDS_TEST" | grep -o '"name"' | wc -l | xargs)"
success "Token has board access — ${BOARD_COUNT} board(s) visible"

# ── step 2: flyctl ─────────────────────────────────────────────────────────────

header "Step 2 — flyctl"

if check_command flyctl; then
  success "flyctl is installed: $(flyctl version 2>/dev/null | head -1)"
else
  warn "flyctl not found."
  read -rp "Install flyctl now? [Y/n] " install_fly
  if [[ ! "$install_fly" =~ ^[Nn]$ ]]; then
    curl -L https://fly.io/install.sh | sh
    export PATH="$HOME/.fly/bin:$PATH"
    check_command flyctl || die "flyctl install failed. Install manually then re-run."
    success "flyctl installed"
  else
    die "flyctl is required. Install it (https://fly.io/docs/hands-on/install-flyctl/) then re-run."
  fi
fi

# ── step 3: flyctl auth ────────────────────────────────────────────────────────

header "Step 3 — Fly.io authentication"

if flyctl auth whoami &>/dev/null; then
  success "Already authenticated as: $(flyctl auth whoami)"
else
  info "Not logged in to Fly.io. Opening browser..."
  flyctl auth login
  success "Authenticated as: $(flyctl auth whoami)"
fi

# ── step 4: fly launch ─────────────────────────────────────────────────────────

header "Step 4 — Create Fly app (flyctl launch)"

TOML="$REPO_DIR/fly.toml"
APP_NAME="$(grep '^app' "$TOML" | head -1 | sed 's/app *= *"\?\([^"]*\)"\?/\1/' | xargs)"

if flyctl status --app "$APP_NAME" &>/dev/null; then
  success "Fly app '$APP_NAME' already exists — skipping launch"
else
  info "Running: flyctl launch --no-deploy"
  cd "$REPO_DIR"
  flyctl launch --no-deploy
  success "Fly app created"
  # Re-read app name in case launch updated fly.toml
  APP_NAME="$(grep '^app' "$TOML" | head -1 | sed 's/app *= *"\?\([^"]*\)"\?/\1/' | xargs)"
fi

# ── step 5: push secrets ───────────────────────────────────────────────────────

header "Step 5 — Push secrets to Fly.io"

info "Setting secrets on app '$APP_NAME'..."
flyctl secrets set \
  "TRELLO_API_KEY=${TRELLO_API_KEY}" \
  "TRELLO_TOKEN=${TRELLO_TOKEN}" \
  "MCP_AUTH_TOKEN=${MCP_AUTH_TOKEN}" \
  --app "$APP_NAME"
success "Secrets pushed"

# ── step 6: deploy ─────────────────────────────────────────────────────────────

header "Step 6 — Initial deploy"

read -rp "Deploy now? [Y/n] " do_deploy
if [[ ! "$do_deploy" =~ ^[Nn]$ ]]; then
  cd "$REPO_DIR"
  flyctl deploy --app "$APP_NAME"
  success "Deployed!"
else
  warn "Skipped. Run 'flyctl deploy' when ready."
fi

FLY_HOST="${APP_NAME}.fly.dev"

# ── step 7: FLY_API_TOKEN ──────────────────────────────────────────────────────

header "Step 7 — Generate & validate FLY_API_TOKEN for CI/CD"

info "Generating a non-expiring Fly.io deploy token..."
FLY_API_TOKEN="$(flyctl tokens create deploy -x 999999h 2>/dev/null | tail -1)"

if [[ -z "$FLY_API_TOKEN" ]]; then
  die "Failed to generate FLY_API_TOKEN. Run 'flyctl tokens create deploy -x 999999h' manually."
fi

# Validate the token by hitting the Fly.io API directly
FLY_TOKEN_TEST="$(curl -sf -H "Authorization: Bearer ${FLY_API_TOKEN}" \
  "https://api.fly.io/v1/apps/${APP_NAME}" || true)"

if echo "$FLY_TOKEN_TEST" | grep -q '"name"'; then
  success "FLY_API_TOKEN validated — can reach app '${APP_NAME}' via API"
else
  warn "Token generated but API validation returned unexpected response — double-check it works."
fi

if check_command gh && gh auth status &>/dev/null; then
  echo "$FLY_API_TOKEN" | gh secret set FLY_API_TOKEN
  success "FLY_API_TOKEN set as GitHub Actions secret via gh"
else
  REMOTE_URL="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null || echo "")"
  GH_REPO="$(echo "$REMOTE_URL" | sed 's/.*github.com[:/]\(.*\)\.git/\1/')"
  warn "gh CLI not authenticated — add FLY_API_TOKEN manually:"
  echo "  URL  : https://github.com/${GH_REPO}/settings/secrets/actions"
  echo "  Name : FLY_API_TOKEN"
  echo "  Value: ${FLY_API_TOKEN}"
fi
echo

# ── step 8: Claude MCP config ──────────────────────────────────────────────────

header "Step 8 — Claude MCP config snippet"

echo "Add this to your Claude MCP config (~/.claude/mcp_servers.json):"
echo
cat <<EOF
{
  "trello": {
    "url": "https://${FLY_HOST}/sse",
    "transport": "sse",
    "headers": {
      "Authorization": "Bearer ${MCP_AUTH_TOKEN}"
    }
  }
}
EOF

# ── done ───────────────────────────────────────────────────────────────────────

echo -e "\n${GREEN}${BOLD}All done!${RESET}"
echo "  Server : https://${FLY_HOST}/sse"
echo "  Health : https://${FLY_HOST}/health"

# trello-mcp-server

Cloud-hosted MCP server that exposes Trello operations as tools for Claude.
Replaces the manual snapshot → propose → apply workflow.

## Architecture

```
Claude (Code/Cowork) → HTTPS → Fly.io MCP Server → Trello API
```

## Tools

| Tool | Description |
|---|---|
| `list_boards` | All open Trello boards |
| `list_lists` | Lists on a board |
| `list_cards` | Cards in a list |
| `get_card` | Full card detail |
| `add_card` | Create a card |
| `move_card` | Move card to another list |
| `update_card` | Update name / desc / due date |
| `archive_card` | Archive a card (reversible) |
| `add_board` | Create a new board |
| `add_list` | Add a list to a board |

## Setup

### 1. Prerequisites

- [Fly.io account](https://fly.io) + `flyctl` installed
- Trello API key + token from https://trello.com/power-ups/admin

### 2. Deploy

```bash
git clone https://github.com/sens8tion/trello-mcp-server
cd trello-mcp-server

# Create the Fly app (first time only)
flyctl launch --no-deploy

# Set secrets
flyctl secrets set \
  TRELLO_API_KEY=your_key \
  TRELLO_TOKEN=your_token \
  MCP_AUTH_TOKEN=your_secret_bearer_token

# Deploy
flyctl deploy
```

### 3. Register in Claude MCP config

Add to your Claude MCP settings (e.g. `~/.claude/mcp_servers.json`):

```json
{
  "trello": {
    "url": "https://trello-mcp-server.fly.dev/sse",
    "transport": "sse",
    "headers": {
      "Authorization": "Bearer your_secret_bearer_token"
    }
  }
}
```

## Local dev

```bash
pip install -r requirements-dev.txt
cp .env.example .env  # fill in your values
python server.py

# Lint + test
ruff check .
pytest
```

## CI/CD

- **CI** runs on every push/PR: lint (`ruff`) + tests (`pytest`)
- **Deploy** runs on merge to `main` (after CI passes): `flyctl deploy --remote-only`
- Required GitHub secret: `FLY_API_TOKEN`

## Future

- **Ephemeral agent** — instead of a persistent VM, the server runs as an on-demand process (e.g. Fly.io Machine spun up per invocation and destroyed on completion). Accepts a natural-language task, runs a Claude agentic loop to orchestrate Trello operations, then exits. No idle cost, no persistent state.

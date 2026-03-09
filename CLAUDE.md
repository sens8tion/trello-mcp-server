# trello-mcp-server

Cloud-hosted MCP server exposing Trello as tools for Claude.
Replaces the manual snapshot → propose → apply workflow in the main working area repo.

## What this is

Claude calls this server directly over HTTP/SSE to read and mutate Trello boards in real time.
No more snapshot files, no more `pending.sh`.

Stack: Python · FastMCP · Fly.io (lhr) · GitHub Actions CI/CD

## Status

- [x] Repo scaffolded and pushed
- [x] Fly.io account created
- [x] `flyctl launch --no-deploy` run in this repo
- [x] Fly secrets set (TRELLO_API_KEY, TRELLO_TOKEN, MCP_AUTH_TOKEN)
- [x] FLY_API_TOKEN added as GitHub repo secret (for CD)
- [x] First deploy succeeded
- [x] Registered in Claude MCP config → tools verified working

## Next steps (in order)

1. Copy `.env.example` → `.env` and fill in `TRELLO_API_KEY`, `TRELLO_TOKEN`, `MCP_AUTH_TOKEN`
2. Oak creates Fly.io account and installs `flyctl`
3. In this repo: `flyctl launch --no-deploy` (creates the app on Fly, writes app name into fly.toml)
4. Push secrets to Fly: `bash set-fly-secrets.sh` (reads from `.env`, never exposes values in shell history)
5. Add `FLY_API_TOKEN` to GitHub repo secrets (Settings → Secrets → Actions)
6. Push any change to `main` → CI runs → deploys automatically
7. Add to Claude MCP config (see README for snippet)
8. Test each tool from Claude

## Project layout

```
server.py                      # FastMCP server — all tools defined here
fly.toml                       # Fly.io deploy config
set-fly-secrets.sh             # Reads .env and pushes secrets to Fly
requirements.txt               # Runtime deps
requirements-dev.txt           # + lint/test deps
tests/test_server.py           # Smoke tests
.github/workflows/ci.yml       # Lint + test on push/PR
.github/workflows/deploy.yml   # Deploy to Fly on merge to main
```

## Conventions

- **Never commit secrets** — all credentials go in Fly secrets or `.env` (gitignored)
- **Prefer `archive_card` over delete** — archive is reversible; there is no delete tool by design
- **Auth** — every request must carry `Authorization: Bearer <MCP_AUTH_TOKEN>`
- **Trello calls use query params, not JSON body** — matches Trello API convention (see `_post`/`_put` helpers)
- **Transport** — HTTP + SSE (`mcp.run(transport="sse")`); do not switch to stdio

## Running locally

```bash
pip install -r requirements-dev.txt
cp .env.example .env   # fill in real values
python server.py

# Lint + test
ruff check .
pytest
```

## Trello credentials

- API key + token: https://trello.com/power-ups/admin
- `MCP_AUTH_TOKEN`: generate any strong random string (e.g. `openssl rand -hex 32`)

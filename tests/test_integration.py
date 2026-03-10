"""
Integration tests — hit the live deployed server over HTTP.

These prove the server is up, auth works, all tools are registered,
and Trello calls succeed end-to-end.

Run locally:
    TEST_SERVER_URL=https://trello-mcp-server.fly.dev \
    MCP_AUTH_TOKEN=<token> \
    pytest tests/test_integration.py -v

Trello round-trip tests are skipped unless TRELLO_API_KEY is also set.
All tests are skipped if MCP_AUTH_TOKEN is not set.
"""

import json
import os

import httpx
import pytest

SERVER_URL = os.environ.get("TEST_SERVER_URL", "https://trello-mcp-server.fly.dev")
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")
HAS_TRELLO = bool(os.environ.get("TRELLO_API_KEY"))

MCP_URL = f"{SERVER_URL}/mcp"
HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"}

EXPECTED_TOOLS = {
    "list_boards", "list_lists", "list_cards", "get_card",
    "add_card", "move_card", "update_card", "archive_card",
    "add_board", "add_list",
}

needs_token = pytest.mark.skipif(not AUTH_TOKEN, reason="MCP_AUTH_TOKEN not set")
needs_trello = pytest.mark.skipif(not HAS_TRELLO, reason="TRELLO_API_KEY not set")


def _rpc(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}


def _parse(response: httpx.Response) -> dict:
    """Parse MCP response — handles both JSON and SSE (text/event-stream)."""
    ct = response.headers.get("content-type", "")
    if "text/event-stream" in ct:
        for line in response.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        pytest.fail(f"No data line in SSE response:\n{response.text}")
    return response.json()


@pytest.fixture(scope="session")
def client():
    with httpx.Client(timeout=20) as c:
        yield c


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

def test_health(client):
    """Health endpoint is reachable without auth."""
    resp = client.get(f"{SERVER_URL}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@needs_token
def test_auth_rejected_no_token(client):
    """Requests without a token are rejected with 401."""
    resp = client.post(MCP_URL, json=_rpc("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    }))
    assert resp.status_code == 401


@needs_token
def test_auth_rejected_bad_token(client):
    """Requests with a wrong token are rejected with 401."""
    resp = client.post(
        MCP_URL,
        headers={"Authorization": "Bearer wrong_token", "Content-Type": "application/json"},
        json=_rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# MCP protocol
# ---------------------------------------------------------------------------

@needs_token
def test_initialize(client):
    """MCP initialize handshake returns a valid protocol version."""
    resp = client.post(MCP_URL, headers=HEADERS, json=_rpc("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "integration-test", "version": "1.0"},
    }))
    resp.raise_for_status()
    data = _parse(resp)
    assert "result" in data
    assert "protocolVersion" in data["result"]


@needs_token
def test_tools_list(client):
    """All expected tools are registered on the live server."""
    resp = client.post(MCP_URL, headers=HEADERS, json=_rpc("tools/list"))
    resp.raise_for_status()
    data = _parse(resp)
    registered = {t["name"] for t in data["result"]["tools"]}
    missing = EXPECTED_TOOLS - registered
    extra = registered - EXPECTED_TOOLS
    assert not missing and not extra, f"Missing: {missing}, Extra: {extra}"


# ---------------------------------------------------------------------------
# Trello round-trips (require live Trello credentials on the server)
# ---------------------------------------------------------------------------

@needs_token
@needs_trello
def test_list_boards_returns_list(client):
    """list_boards returns a non-empty list of board dicts."""
    resp = client.post(MCP_URL, headers=HEADERS, json=_rpc(
        "tools/call", {"name": "list_boards", "arguments": {}}
    ))
    resp.raise_for_status()
    data = _parse(resp)
    # MCP tool result comes back as content[0].text (JSON string)
    content = data["result"]["content"]
    assert isinstance(content, list) and len(content) > 0
    boards = json.loads(content[0]["text"])
    assert isinstance(boards, list)
    assert all("id" in b and "name" in b for b in boards)

"""
Trello MCP Server — exposes Trello operations as MCP tools.

Runs over HTTP + SSE (remote MCP transport).
Auth: Bearer token checked on every request.
"""

import os
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

load_dotenv()  # no-op in prod (Fly injects env vars directly)

TRELLO_API_KEY = os.environ["TRELLO_API_KEY"]
TRELLO_TOKEN = os.environ["TRELLO_TOKEN"]
MCP_AUTH_TOKEN = os.environ["MCP_AUTH_TOKEN"]

BASE_URL = "https://api.trello.com/1"

mcp = FastMCP("trello-mcp-server")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {MCP_AUTH_TOKEN}":
            return Response("Unauthorized", status_code=401)
        return await call_next(request)


mcp.app.add_middleware(BearerAuthMiddleware)


def _params(**kwargs) -> dict:
    """Base Trello auth params merged with any extras."""
    return {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN, **kwargs}


def _get(path: str, **kwargs) -> dict | list:
    url = f"{BASE_URL}{path}"
    r = httpx.get(url, params=_params(**kwargs), timeout=10)
    r.raise_for_status()
    return r.json()


def _post(path: str, **kwargs) -> dict:
    url = f"{BASE_URL}{path}"
    r = httpx.post(url, params=_params(**kwargs), timeout=10)
    r.raise_for_status()
    return r.json()


def _put(path: str, **kwargs) -> dict:
    url = f"{BASE_URL}{path}"
    r = httpx.put(url, params=_params(**kwargs), timeout=10)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_boards() -> list[dict]:
    """Return all Trello boards accessible to this account."""
    boards = _get("/members/me/boards", fields="name,shortUrl,closed")
    return [{"id": b["id"], "name": b["name"], "url": b["shortUrl"]} for b in boards if not b["closed"]]


@mcp.tool()
def list_lists(board_id: str) -> list[dict]:
    """Return all open lists on a board."""
    lists = _get(f"/boards/{board_id}/lists", filter="open")
    return [{"id": lst["id"], "name": lst["name"]} for lst in lists]


@mcp.tool()
def list_cards(list_id: str) -> list[dict]:
    """Return all open cards in a list."""
    cards = _get(f"/lists/{list_id}/cards", fields="name,desc,due,shortUrl")
    return [{"id": c["id"], "name": c["name"], "desc": c["desc"], "due": c["due"], "url": c["shortUrl"]} for c in cards]


@mcp.tool()
def get_card(card_id: str) -> dict:
    """Get full detail for a single card."""
    return _get(f"/cards/{card_id}")


@mcp.tool()
def add_card(list_id: str, name: str, desc: str = "", due: str = "") -> dict:
    """Add a new card to a list. due is optional ISO 8601 date string."""
    kwargs = {"name": name, "idList": list_id}
    if desc:
        kwargs["desc"] = desc
    if due:
        kwargs["due"] = due
    card = _post("/cards", **kwargs)
    return {"id": card["id"], "name": card["name"], "url": card["shortUrl"]}


@mcp.tool()
def move_card(card_id: str, list_id: str) -> dict:
    """Move a card to a different list."""
    card = _put(f"/cards/{card_id}", idList=list_id)
    return {"id": card["id"], "name": card["name"]}


@mcp.tool()
def update_card(card_id: str, name: str = "", desc: str = "", due: str = "") -> dict:
    """Update a card's name, description, and/or due date. Pass only fields to change."""
    kwargs = {}
    if name:
        kwargs["name"] = name
    if desc:
        kwargs["desc"] = desc
    if due:
        kwargs["due"] = due
    if not kwargs:
        return {"error": "No fields to update"}
    card = _put(f"/cards/{card_id}", **kwargs)
    return {"id": card["id"], "name": card["name"]}


@mcp.tool()
def archive_card(card_id: str) -> dict:
    """Archive (close) a card. Reversible. Prefer this over delete."""
    card = _put(f"/cards/{card_id}", closed=True)
    return {"id": card["id"], "name": card["name"], "archived": True}


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="sse", port=port)

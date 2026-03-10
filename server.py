"""
Trello MCP Server — exposes Trello operations as MCP tools.

Runs over streamable HTTP (stateless POST per call).
Auth: Bearer token checked on every request.
Logging: MCP protocol notifications/message emitted via Context.
"""

import os
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

load_dotenv()  # no-op in prod (Fly injects env vars directly)

TRELLO_API_KEY = os.environ["TRELLO_API_KEY"]
TRELLO_TOKEN = os.environ["TRELLO_TOKEN"]
MCP_AUTH_TOKEN = os.environ["MCP_AUTH_TOKEN"]

BASE_URL = "https://api.trello.com/1"

# Disable DNS rebinding protection — we use Bearer token auth instead.
# stateless_http=True: each HTTP request is independent, no sessions to lose on reconnect.
mcp = FastMCP(
    "trello-mcp-server",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    stateless_http=True,
)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {MCP_AUTH_TOKEN}":
            return Response("Unauthorized", status_code=401)
        return await call_next(request)


def _params(**kwargs) -> dict:
    """Base Trello auth params merged with any extras."""
    return {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN, **kwargs}


async def _get(path: str, **kwargs) -> dict | list:
    url = f"{BASE_URL}{path}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=_params(**kwargs), timeout=10)
    r.raise_for_status()
    return r.json()


async def _post(path: str, **kwargs) -> dict:
    url = f"{BASE_URL}{path}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, params=_params(**kwargs), timeout=10)
    r.raise_for_status()
    return r.json()


async def _put(path: str, **kwargs) -> dict:
    url = f"{BASE_URL}{path}"
    async with httpx.AsyncClient() as client:
        r = await client.put(url, params=_params(**kwargs), timeout=10)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_boards(ctx: Context) -> list[dict]:
    """Return all Trello boards accessible to this account."""
    await ctx.info("Fetching boards from Trello")
    boards = await _get("/members/me/boards", fields="name,shortUrl,closed")
    result = [{"id": b["id"], "name": b["name"], "url": b["shortUrl"]} for b in boards if not b["closed"]]
    await ctx.info(f"Found {len(result)} open boards")
    return result


@mcp.tool()
async def list_lists(board_id: str, ctx: Context) -> list[dict]:
    """Return all open lists on a board."""
    await ctx.info(f"Fetching lists for board {board_id}")
    lists = await _get(f"/boards/{board_id}/lists", filter="open")
    result = [{"id": lst["id"], "name": lst["name"]} for lst in lists]
    await ctx.info(f"Found {len(result)} lists")
    return result


@mcp.tool()
async def list_cards(list_id: str, ctx: Context) -> list[dict]:
    """Return all open cards in a list."""
    await ctx.info(f"Fetching cards for list {list_id}")
    cards = await _get(f"/lists/{list_id}/cards", fields="name,desc,due,shortUrl")
    result = [{"id": c["id"], "name": c["name"], "desc": c["desc"], "due": c["due"], "url": c["shortUrl"]} for c in cards]
    await ctx.info(f"Found {len(result)} cards")
    return result


@mcp.tool()
async def get_card(card_id: str, ctx: Context) -> dict:
    """Get full detail for a single card."""
    await ctx.info(f"Fetching card {card_id}")
    return await _get(f"/cards/{card_id}")


@mcp.tool()
async def add_card(list_id: str, name: str, ctx: Context, desc: str = "", due: str = "") -> dict:
    """Add a new card to a list. due is optional ISO 8601 date string."""
    await ctx.info(f"Creating card '{name}' in list {list_id}")
    kwargs = {"name": name, "idList": list_id}
    if desc:
        kwargs["desc"] = desc
    if due:
        kwargs["due"] = due
    card = await _post("/cards", **kwargs)
    await ctx.info(f"Created card {card['id']}")
    return {"id": card["id"], "name": card["name"], "url": card["shortUrl"]}


@mcp.tool()
async def move_card(card_id: str, list_id: str, ctx: Context) -> dict:
    """Move a card to a different list."""
    await ctx.info(f"Moving card {card_id} to list {list_id}")
    card = await _put(f"/cards/{card_id}", idList=list_id)
    await ctx.info(f"Moved card '{card['name']}'")
    return {"id": card["id"], "name": card["name"]}


@mcp.tool()
async def update_card(card_id: str, ctx: Context, name: str = "", desc: str = "", due: str = "") -> dict:
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
    await ctx.info(f"Updating card {card_id}: {list(kwargs.keys())}")
    card = await _put(f"/cards/{card_id}", **kwargs)
    await ctx.info(f"Updated card '{card['name']}'")
    return {"id": card["id"], "name": card["name"]}


@mcp.tool()
async def archive_card(card_id: str, ctx: Context) -> dict:
    """Archive (close) a card. Reversible. Prefer this over delete."""
    await ctx.info(f"Archiving card {card_id}")
    card = await _put(f"/cards/{card_id}", closed=True)
    await ctx.info(f"Archived card '{card['name']}'")
    return {"id": card["id"], "name": card["name"], "archived": True}


@mcp.tool()
async def add_board(name: str, ctx: Context, default_lists: bool = False) -> dict:
    """Create a new Trello board. default_lists=True adds To Do / Doing / Done lists."""
    await ctx.info(f"Creating board '{name}'")
    board = await _post("/boards", name=name, defaultLists=str(default_lists).lower())
    await ctx.info(f"Created board {board['id']}")
    return {"id": board["id"], "name": board["name"], "url": board["shortUrl"]}


@mcp.tool()
async def add_list(board_id: str, name: str, ctx: Context) -> dict:
    """Add a new list to a board."""
    await ctx.info(f"Creating list '{name}' on board {board_id}")
    lst = await _post("/lists", name=name, idBoard=board_id)
    await ctx.info(f"Created list {lst['id']}")
    return {"id": lst["id"], "name": lst["name"]}


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok"})


# Build the ASGI app after all tools/routes are registered.
# streamable_http_app() uses stateless HTTP POST per call — no persistent connection to drop.
app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

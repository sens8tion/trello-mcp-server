"""Smoke tests — verify the server module loads and all tools are registered."""

import os
import importlib
import pytest


EXPECTED_TOOLS = {
    "list_boards",
    "list_lists",
    "list_cards",
    "get_card",
    "add_card",
    "move_card",
    "update_card",
    "archive_card",
}


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    monkeypatch.setenv("TRELLO_API_KEY", "test_key")
    monkeypatch.setenv("TRELLO_TOKEN", "test_token")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test_bearer")


def test_server_imports():
    import server  # noqa: F401 — just verify no import error


def test_all_tools_registered():
    import server
    # FastMCP stores tools by name in its internal registry
    registered = set(server.mcp._tool_manager._tools.keys())
    assert EXPECTED_TOOLS == registered, (
        f"Missing: {EXPECTED_TOOLS - registered}, Extra: {registered - EXPECTED_TOOLS}"
    )

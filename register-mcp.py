#!/usr/bin/env python3
"""
Register the Trello MCP server in the Claude Desktop config.

Usage:
    python register-mcp.py

Reads MCP_AUTH_TOKEN from .env (or environment).
Detects the Claude Desktop config path for the current OS.
Adds or updates the "trello" entry without touching other servers.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

# ---------------------------------------------------------------------------
# Config path detection
# ---------------------------------------------------------------------------

def find_claude_config() -> Path:
    if sys.platform == "win32":
        # Windows Store app (sandboxed AppData)
        store = Path(os.environ.get("LOCALAPPDATA", "")) / \
            "Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude/claude_desktop_config.json"
        # Standard install
        standard = Path(os.environ.get("APPDATA", "")) / "Claude/claude_desktop_config.json"
        for p in (store, standard):
            if p.exists():
                return p
        return store  # default to Store path even if not yet created
    elif sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    else:
        return Path.home() / ".config/Claude/claude_desktop_config.json"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    env = {**dotenv_values(".env"), **os.environ}
    token = env.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        print("ERROR: MCP_AUTH_TOKEN not set in .env or environment")
        sys.exit(1)

    config_path = find_claude_config()
    print(f"Claude config: {config_path}")

    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        config = {}
        config_path.parent.mkdir(parents=True, exist_ok=True)

    config.setdefault("mcpServers", {})
    config["mcpServers"]["trello"] = {
        "command": "mcp-remote",
        "args": [
            "https://trello-mcp-server.fly.dev/mcp",
            "--transport",
            "http-only",
            "--header",
            f"Authorization:Bearer {token}",
        ],
    }

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Registered trello MCP server.")
    print("Restart Claude Desktop to pick up the change.")


if __name__ == "__main__":
    main()

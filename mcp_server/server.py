"""North Star Governed Context Server using the official MCP Python SDK v2."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

from mcp.server import MCPServer

from mcp_server.adapters import DEFAULT_TIMEOUT_SECONDS, adapter
from mcp_server.prompts import register_prompts
from mcp_server.resources import register_resources
from mcp_server.tools import register_tools

SERVER_VERSION = "1.0.0"
REQUEST_TIMEOUT_SECONDS = DEFAULT_TIMEOUT_SECONDS
API_BASE_URL = adapter.api_base_url
EXPENSE_WEBHOOK_URL = adapter.expense_webhook_url
APPROVAL_WEBHOOK_URL = adapter.approval_webhook_url

logging.basicConfig(stream=sys.stderr, level=os.getenv("NORTHSTAR_MCP_LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("northstar.mcp")

mcp = MCPServer(
    name="north-star-governed-context",
    title="North Star Governed Context Server",
    description="Governed enterprise expense context, decision provenance and controlled workflow actions.",
    instructions=(
        "Use read tools and resources for stored North Star facts. Treat submit_expense as an "
        "orchestration bridge and approve_expense as a consequential trusted-operator action."
    ),
    version=SERVER_VERSION,
    log_level="WARNING",
)
register_tools(mcp)
register_resources(mcp)
register_prompts(mcp)


def _request(method: str, url: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
    """Compatibility shim for callers of the original five-tool module."""
    return adapter.request(method, url, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.transport == "stdio":
        logger.info(json.dumps({"event": "mcp_start", "transport": "stdio", "version": SERVER_VERSION}))
        mcp.run("stdio")
        return
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Gate 7 Streamable HTTP is restricted to a loopback host")
    logger.info(json.dumps({"event": "mcp_start", "transport": "streamable-http", "host": args.host, "port": args.port, "version": SERVER_VERSION}))
    mcp.run(
        "streamable-http", host=args.host, port=args.port, streamable_http_path="/mcp",
        json_response=True, stateless_http=True,
    )


if __name__ == "__main__":
    main()

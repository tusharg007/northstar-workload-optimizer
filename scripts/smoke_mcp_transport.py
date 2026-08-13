"""Real-process MCP read smoke for stdio or localhost Streamable HTTP."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client


async def exercise(transport: str, expense_id: str, url: str) -> dict:
    if transport == "stdio":
        parameters = StdioServerParameters(
            command=str(ROOT / ".venv" / "Scripts" / "python.exe"),
            args=["-m", "mcp_server.server"], cwd=ROOT,
            env={key: value for key, value in os.environ.items() if key.startswith(("NORTHSTAR_", "N8N_"))},
        )
        target = stdio_client(parameters)
    else:
        target = url
    async with Client(target) as client:
        tools = await client.list_tools()
        resources = await client.list_resource_templates()
        status = await client.call_tool("get_expense_status", {"expense_id": expense_id})
        policy = await client.call_tool("get_policy_version", {"policy_key": "EXPENSE_APPROVAL_ROUTING"})
        trace = await client.call_tool("get_decision_trace", {"expense_id": expense_id})
        resource = await client.read_resource(f"northstar://expenses/{expense_id}/trace")
        if any(item.is_error for item in (status, policy, trace)):
            raise RuntimeError("one or more MCP read calls failed")
        return {
            "status": "PASS", "transport": transport, "tool_count": len(tools.tools),
            "resource_template_count": len(resources.resource_templates),
            "expense_status": status.structured_content["status"],
            "policy_version": policy.structured_content["version_number"],
            "trace_verified": trace.structured_content["verification"]["status"],
            "resource_bytes": len(resource.contents[0].text),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "http"), required=True)
    parser.add_argument("--expense-id", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(exercise(args.transport, args.expense_id, args.url)), sort_keys=True))
        return 0
    except Exception as exc:
        print(f"MCP TRANSPORT SMOKE: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

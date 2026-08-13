"""Bounded localhost Streamable HTTP runtime test with guaranteed cleanup."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import Client

ROOT = Path(__file__).resolve().parents[1]


async def wait_ready(url: str, process: asyncio.subprocess.Process) -> None:
    for _ in range(60):
        if process.returncode is not None:
            raise RuntimeError(f"MCP HTTP server exited with {process.returncode}")
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", 8765), timeout=1)
            writer.close()
            await writer.wait_closed()
            return
        except (OSError, TimeoutError):
            await asyncio.sleep(0.25)
    raise RuntimeError("MCP HTTP server did not become ready")


async def run(expense_id: str, url: str) -> dict:
    env = os.environ.copy()
    process = await asyncio.create_subprocess_exec(
        str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "mcp_server.server",
        "--transport", "streamable-http", "--host", "127.0.0.1", "--port", "8765",
        cwd=ROOT, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        await wait_ready(url, process)
        async with Client(url) as client:
            tools = await client.list_tools()
            resources = await client.list_resource_templates()
            status = await client.call_tool("get_expense_status", {"expense_id": expense_id})
            policy = await client.call_tool("get_policy_version", {"policy_key": "EXPENSE_APPROVAL_ROUTING"})
            trace = await client.call_tool("get_decision_trace", {"expense_id": expense_id})
            resource = await client.read_resource(f"northstar://expenses/{expense_id}/trace")
            if any(item.is_error for item in (status, policy, trace)):
                raise RuntimeError("one or more Streamable HTTP calls failed")
            return {
                "status": "PASS", "transport": "streamable-http", "binding": "127.0.0.1",
                "tool_count": len(tools.tools), "resource_template_count": len(resources.resource_templates),
                "expense_status": status.structured_content["status"],
                "policy_version": policy.structured_content["version_number"],
                "trace_verified": trace.structured_content["verification"]["status"],
                "resource_bytes": len(resource.contents[0].text),
            }
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expense-id", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args.expense_id, args.url)), sort_keys=True))
        return 0
    except Exception as exc:
        print(f"MCP STREAMABLE HTTP SMOKE: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

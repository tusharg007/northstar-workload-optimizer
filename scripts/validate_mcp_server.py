"""Static catalog and safety validation for the Gate 7 MCP provider."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_server.server import SERVER_VERSION, mcp

PACKAGE = ROOT / "mcp_server"
CONTRACT = PACKAGE / "contract.json"
FORBIDDEN_SOURCE = re.compile(r"\b(sqlalchemy|psycopg|create_engine|Session|\.execute\s*\()", re.I)
SECRET = re.compile(r"(password\s*[=:]\s*['\"][^<{$]|authorization\s*:\s*bearer|postgresql(?:\+psycopg)?://[^<\s]+:[^<\s]+@)", re.I)


async def validate() -> list[str]:
    errors: list[str] = []
    try:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"contract is unreadable: {exc}"]
    tools = await mcp.list_tools()
    resources = await mcp.list_resource_templates()
    prompts = await mcp.list_prompts()
    expected_tools = contract.get("tools", [])
    names = [item.get("name") for item in expected_tools]
    if len(names) != len(set(names)) or None in names:
        errors.append("contract tool names must be unique and non-empty")
    live = {item.name: item for item in tools}
    if set(live) != set(names):
        errors.append(f"tool inventory mismatch: live={sorted(live)} contract={sorted(names)}")
    for spec in expected_tools:
        item = live.get(spec["name"])
        if item is None:
            continue
        if not item.description:
            errors.append(f"{item.name}: description is empty")
        if item.output_schema is None:
            errors.append(f"{item.name}: structured output schema is missing")
        actual_read_only = bool(item.annotations and item.annotations.read_only_hint)
        if actual_read_only != spec["read_only"]:
            errors.append(f"{item.name}: read-only annotation mismatch")
        if spec["classification"] == "WRITE_PRIVILEGED" and "CONSEQUENTIAL ACTION" not in item.description:
            errors.append(f"{item.name}: privileged description lacks consequential-action warning")
    actual_resources = {item.uri_template for item in resources}
    if actual_resources != set(contract.get("resource_templates", [])):
        errors.append("resource template inventory mismatch")
    if {item.name for item in prompts} != set(contract.get("prompts", [])):
        errors.append("prompt inventory mismatch")
    sdk = importlib.metadata.version("mcp")
    if sdk != contract.get("server", {}).get("mcp_sdk") or not sdk.startswith("2."):
        errors.append(f"MCP SDK mismatch: installed={sdk}")
    if SERVER_VERSION != contract.get("server", {}).get("version"):
        errors.append("server version mismatch")
    source = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py"))
    if FORBIDDEN_SOURCE.search(source):
        errors.append("MCP package contains direct database access")
    if re.search(r"\bprint\s*\(", source):
        errors.append("MCP package contains print(), which can corrupt stdio JSON-RPC")
    tracked = CONTRACT.read_text(encoding="utf-8") + source
    if SECRET.search(tracked):
        errors.append("MCP contract/source appears to contain a credential")
    return errors


def main() -> int:
    errors = asyncio.run(validate())
    if errors:
        print("MCP SERVER VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    print(
        "MCP SERVER VALIDATION: PASS "
        f"({len(contract['tools'])} tools, {len(contract['resource_templates'])} resources, "
        f"{len(contract['prompts'])} prompt)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

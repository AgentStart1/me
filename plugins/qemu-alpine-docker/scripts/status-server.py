# /// script
# requires-python = ">=3.10"
# dependencies = ["openai-mcp-extensions==0.1.0", "mcp==2.2.0"]
# ///
"""Local MCP App: VM state, service health, and container list."""
from mcp.server.apps import APP_MIME_TYPE, Apps
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.resources import TextResource
import json
from mcp_types import ToolAnnotations, CallToolResult, TextContent, Annotations
from openai_mcp_extensions import OpenAIExtensions, OpenAIGlobalEntrypoint, OpenAIThreadEntrypoint, OpenAIUiToolMetadata
from status import ROOT, collect_status

URI = "ui://qemu-alpine-docker/status"
apps = Apps()
apps.add_resource(TextResource(
    uri=URI, name="QEMU Docker status panel", mime_type=APP_MIME_TYPE,
    text=(ROOT / "templates/status-panel.html").read_text(encoding="utf-8"),
    meta={"ui": {"csp": {"connectDomains": [], "resourceDomains": []}}},
))


@apps.tool(
    name="qemu_docker_status", title="VM & Containers", resource_uri=URI,
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False),
    meta={"openai/ui": OpenAIUiToolMetadata(entrypoints=[OpenAIGlobalEntrypoint(), OpenAIThreadEntrypoint()]).model_dump(by_alias=True, exclude_none=True)},
)
def qemu_docker_status() -> CallToolResult:
    """Show read-only QEMU VM state, local SSH/Docker health, and all Docker containers."""
    snapshot = collect_status()
    return CallToolResult(structured_content=snapshot, content=[TextContent(type="text", text=json.dumps(snapshot), annotations=Annotations(audience=["assistant"]))])


server = MCPServer("qemu-docker-status", extensions=[apps, OpenAIExtensions()])
if __name__ == "__main__":
    server.run(transport="stdio")

# /// script
# requires-python = ">=3.10"
# dependencies = ["openai-mcp-extensions==0.1.0", "mcp==2.2.0"]
# ///
import json
from pathlib import Path
from mcp.server.apps import APP_MIME_TYPE, Apps
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.resources import TextResource
from mcp_types import ToolAnnotations, CallToolResult, TextContent, Annotations, ImageContent
from openai_mcp_extensions import OpenAIExtensions, OpenAIGlobalEntrypoint, OpenAIThreadEntrypoint, OpenAIUiToolMetadata
from emulator_status import collect_status

ROOT = Path(__file__).resolve().parents[1]
URI = "ui://android-emulator-profile/status"
apps = Apps()
apps.add_resource(TextResource(uri=URI, name="Android Emulators", mime_type=APP_MIME_TYPE,
    text=(ROOT / "templates/status-panel.html").read_text(encoding="utf-8"),
    meta={"ui": {"csp": {"connectDomains": [], "resourceDomains": []}}}))

@apps.tool(name="android_emulator_status", title="Android Emulators", resource_uri=URI,
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False),
    meta={"openai/ui": OpenAIUiToolMetadata(entrypoints=[OpenAIGlobalEntrypoint(), OpenAIThreadEntrypoint()]).model_dump(by_alias=True, exclude_none=True)})
def status() -> CallToolResult:
    """Read local Android status for the conversation panel without changing device state."""
    snapshot = collect_status()
    return CallToolResult(structured_content=snapshot,
        content=[TextContent(type="text", text=json.dumps(snapshot), annotations=Annotations(audience=["assistant"]))])

@apps.tool(name="android_emulator_screenshot", resource_uri=URI, visibility=["app"],
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def capture(serial: str) -> CallToolResult:
    """Capture the selected emulator screen only when requested in the panel."""
    from emulator_status import screenshot
    return CallToolResult(content=[ImageContent(type="image", data=screenshot(serial), mime_type="image/png")])

server = MCPServer("android-emulator-profile-status", extensions=[apps, OpenAIExtensions()])
if __name__ == "__main__":
    server.run(transport="stdio")

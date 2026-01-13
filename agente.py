import asyncio
import httpx
import json
import re

SONARQUBE_TOKEN = "dad1da5727a0c251ee00b49649fd07a8fd9fbae1"
SERVER_URL = "http://localhost:8080"


class SonarQubeMCPClient:
    def __init__(self, url: str, token: str):
        self.base_url = url
        self.token = token
        self.client = None
        self.session_id = None
        self.request_id = 0

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

        # Inicializar
        response = await self.client.post(
            f"{self.base_url}/mcp",
            headers={
                "SONARQUBE_TOKEN": self.token,
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json"
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "python-client", "version": "1.0"}
                }
            }
        )
        response.raise_for_status()

        self.session_id = response.headers.get("mcp-session-id")
        if not self.session_id:
            raise Exception("No session ID recibido")

        result = response.json()
        server_info = result.get("result", {}).get("serverInfo", {})
        print(f"✅ Conectado: {server_info.get('name')} v{server_info.get('version')}\n")

        self.request_id = 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def _parse_sse_response(self, text: str) -> dict:
        """Parsear respuesta SSE y extraer JSON"""
        match = re.search(r'data:\s*(\{.*\})', text)
        if match:
            return json.loads(match.group(1))
        raise ValueError("No se encontró JSON válido en respuesta SSE")

    async def call_method(self, method: str, params: dict = None):
        """Llamar méthod MCP"""
        self.request_id += 1

        response = await self.client.post(
            f"{self.base_url}/mcp",
            headers={
                "SONARQUBE_TOKEN": self.token,
                "mcp-session-id": self.session_id,
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json"
            },
            json={
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": method,
                "params": params or {}
            }
        )
        response.raise_for_status()

        return self._parse_sse_response(response.text)

    async def list_tools(self):
        """Listar herramientas"""
        result = await self.call_method("tools/list")
        return result.get("result", {}).get("tools", [])

    async def call_tool(self, tool_name: str, arguments: dict):
        """Ejecutar herramienta"""
        result = await self.call_method("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        return result.get("result")


async def main():
    async with SonarQubeMCPClient(SERVER_URL, SONARQUBE_TOKEN) as client:
        # Listar herramientas
        print("📋 Herramientas disponibles:")
        tools = await client.list_tools()
        for i, tool in enumerate(tools, 1):
            print(f"{i:2}. {tool.get('name')}")
        print(f"\nTotal: {len(tools)}\n")

        # Listar proyectos
        print("=" * 60)
        print("🔍 Proyectos:\n")
        projects = await client.call_tool("list_sonar_projects", {})
        print(json.dumps(projects, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
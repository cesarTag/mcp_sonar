import httpx
import json
import re
from dotenv import load_dotenv

load_dotenv()

class SonarQubeMCPTransport:
    """Transporte HTTP personalizado para SonarQube MCP"""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self.session_id = None
        self.client = None
        self.request_id = 0

    async def connect(self):
        self.client = httpx.AsyncClient(timeout=30.0)

        response = await self.client.post(
            f"{self.url}/mcp",
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
                    "clientInfo": {"name": "python-mcp-client", "version": "1.0"}
                }
            }
        )
        response.raise_for_status()

        self.session_id = response.headers.get("mcp-session-id")
        result = self._parse_sse(response.text)

        print(f"✅ Conectado: {result.get('result', {}).get('serverInfo', {}).get('name')}\n")
        self.request_id = 1

    def _parse_sse(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r'data:\s*(\{.*\})', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        raise ValueError("No JSON en respuesta SSE")

    async def send(self, method: str, params: dict = None):
        self.request_id += 1

        response = await self.client.post(
            f"{self.url}/mcp",
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
        return self._parse_sse(response.text)

    async def close(self):
        if self.client:
            await self.client.aclose()


class SonarQubeMCPClient:
    """Cliente MCP para SonarQube"""

    def __init__(self, url: str, token: str):
        self.transport = SonarQubeMCPTransport(url, token)

    async def __aenter__(self):
        await self.transport.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.transport.close()

    async def list_tools(self):
        result = await self.transport.send("tools/list")
        return result.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict):
        result = await self.transport.send("tools/call", {
            "name": name,
            "arguments": arguments
        })
        return result.get("result")
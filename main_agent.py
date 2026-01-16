# agente_mcp_oficial.py
import os
import json
from typing import List, Dict, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, create_model
from langchain_openai import ChatOpenAI
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.tools import StructuredTool
from langchain_core.prompts import ChatPromptTemplate
import httpx
from dotenv import load_dotenv

load_dotenv()


# ==================== CLIENTE MCP HTTP ====================

class MCPHTTPClient:
    """Cliente MCP usando HTTP JSON-RPC (servidor oficial SonarQube)"""

    def __init__(self, mcp_url: str = "http://localhost:8080/sse"):
        self.mcp_url = mcp_url
        self.request_id = 0
        self.tools_cache = None
        self.initialized = False
        # Token para autenticación (requerido por servidor oficial)
        self.token = os.getenv("SONARQUBE_TOKEN")

    def _next_id(self):
        self.request_id += 1
        return self.request_id

    def _get_headers(self):
        """Headers con autenticación TOKEN"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "SONARQUBE_TOKEN": "dad1da5727a0c251ee00b49649fd07a8fd9fbae1"
        }

    async def send_request(self, method: str, params: dict = None):
        """Envía request JSON-RPC via HTTP POST"""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method
        }
        if params:
            payload["params"] = params

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.mcp_url,
                    json=payload,
                    headers={"SONARQUBE_TOKEN": "dad1da5727a0c251ee00b49649fd07a8fd9fbae1"}#self._get_headers()

                )

                if response.status_code != 200:
                    return {"error": f"HTTP {response.status_code}: {response.text}"}

                return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def initialize(self):
        """Inicializa protocolo MCP"""
        if self.initialized:
            return {"status": "ok"}

        response = await self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "agente-sonarqube", "version": "1.0.0"}
        })

        if "error" in response:
            return response

        self.initialized = True
        await self.send_request("notifications/initialized", {})
        return response

    async def list_tools(self):
        """Lista herramientas"""
        if self.tools_cache:
            return {"tools": self.tools_cache}

        if not self.initialized:
            await self.initialize()

        response = await self.send_request("tools/list", {})

        if "error" in response:
            return response

        self.tools_cache = response.get("result", {}).get("tools", [])
        return {"tools": self.tools_cache}

    async def call_tool(self, name: str, arguments: dict = None):
        """Ejecuta herramienta"""
        if not self.initialized:
            await self.initialize()

        response = await self.send_request("tools/call", {
            "name": name,
            "arguments": arguments or {}
        })

        if "error" in response:
            return response

        result = response.get("result", {})
        content_items = result.get("content", [])
        texts = [item.get("text", "") for item in content_items if item.get("type") == "text"]

        return {"text": "\n".join(texts)}


# Cliente MCP
mcp = MCPHTTPClient("http://localhost:8080/sse")

# Variables globales
dynamic_tools: List[StructuredTool] = []
mcp_tools_info: List[Dict] = []
agent_executor: Optional[AgentExecutor] = None


# ==================== GENERADOR DINÁMICO ====================

def create_dynamic_tool(tool_info: Dict) -> StructuredTool:
    tool_name = tool_info.get("name")
    tool_description = tool_info.get("description", "")
    input_schema = tool_info.get("inputSchema", {})
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    async def dynamic_tool_func(**kwargs) -> str:
        result = await mcp.call_tool(tool_name, kwargs)
        if "error" in result:
            return f"❌ {result['error']}"
        return result.get("text", "")

    if properties:
        field_definitions = {}
        for prop_name, prop_info in properties.items():
            prop_type = str
            if prop_info.get("type") == "integer":
                prop_type = int
            elif prop_info.get("type") == "boolean":
                prop_type = bool

            if prop_name not in required:
                prop_type = Optional[prop_type]
                field_definitions[prop_name] = (
                prop_type, Field(default=None, description=prop_info.get("description", "")))
            else:
                field_definitions[prop_name] = (prop_type, Field(description=prop_info.get("description", "")))

        Model = create_model(f"{tool_name.replace('-', '_').replace(':', '_')}_input", **field_definitions)
        return StructuredTool(name=tool_name, description=tool_description, coroutine=dynamic_tool_func,
                              args_schema=Model)
    else:
        return StructuredTool(name=tool_name, description=tool_description, coroutine=dynamic_tool_func)


async def load_tools():
    global dynamic_tools, mcp_tools_info

    print("🔧 Cargando herramientas del servidor MCP oficial...")

    tools_result = await mcp.list_tools()

    if "error" in tools_result:
        print(f"❌ {tools_result['error']}")
        return False

    tools_list = tools_result.get("tools", [])
    mcp_tools_info = tools_list

    print(f"📋 {len(tools_list)} herramientas disponibles:")

    dynamic_tools = []
    for t in tools_list:
        try:
            tool = create_dynamic_tool(t)
            dynamic_tools.append(tool)
            print(f"   ✓ {t.get('name')}")
        except Exception as e:
            print(f"   ✗ {t.get('name')}: {e}")

    return len(dynamic_tools) > 0


# ==================== AGENTE ====================

llm = ChatOpenAI(model="gpt-4", api_key=os.getenv("OPENAI_API_KEY"), temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "Eres un experto en análisis de código con SonarQube. Usa las herramientas MCP para responder consultas."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}")
])


def create_agent():
    global agent_executor
    if not dynamic_tools:
        return False
    agent = create_tool_calling_agent(llm, dynamic_tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=dynamic_tools, verbose=True)
    return True


# ==================== FASTAPI ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "=" * 60)
    print("🚀 Iniciando Agente con Servidor MCP Oficial de SonarQube")
    print("=" * 60)
    print(f"📡 MCP URL: {mcp.mcp_url}")

    init_result = await mcp.initialize()
    if "error" in init_result:
        print(f"❌ Error al inicializar: {init_result['error']}")
        print("\n🔧 Verifica que el servidor MCP esté corriendo:")
        print("   docker ps | grep sonarqube-mcp")
    else:
        print("✅ MCP inicializado")
        if await load_tools():
            if create_agent():
                print("✅ Agente listo con servidor oficial")

    print("=" * 60 + "\n")
    yield


app = FastAPI(lifespan=lifespan)


class AgentRequest(BaseModel):
    query: str


@app.post("/consulta")
async def consultar(request: AgentRequest):
    if not agent_executor:
        raise HTTPException(503, "Agente no disponible")
    result = await agent_executor.ainvoke({"input": request.query})
    return {"respuesta": result["output"]}


@app.get("/")
async def root():
    tools_list = [
        {
            "name": t.get("name"),
            "description": t.get("description"),
            "parameters": list(t.get("inputSchema", {}).get("properties", {}).keys())
        }
        for t in mcp_tools_info
    ]

    return {
        "servicio": "Agente SonarQube MCP Oficial",
        "servidor": "mcp/sonarqube (Docker)",
        "tools": len(dynamic_tools),
        "ready": agent_executor is not None,
        "herramientas": tools_list
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy" if agent_executor else "degraded",
        "mcp_initialized": mcp.initialized,
        "tools_loaded": len(dynamic_tools)
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
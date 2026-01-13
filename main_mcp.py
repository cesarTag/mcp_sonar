import asyncio
import json
import os
from anthropic import Anthropic
from dotenv import load_dotenv

from sonar_client import SonarQubeMCPClient

# Configuración
SONARQUBE_TOKEN = "dad1da5727a0c251ee00b49649fd07a8fd9fbae1"
SERVER_URL = "http://localhost:8080"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # export ANTHROPIC_API_KEY=tu_key

load_dotenv()

class SonarQubeAgent:
    def __init__(self, mcp_client: SonarQubeMCPClient):
        self.mcp_client = mcp_client
        self.anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.tools_schema = []
        self.conversation_history = []

    async def initialize(self):
        """Cargar herramientas del MCP"""
        print("🔧 Cargando herramientas del MCP...")
        tools = await self.mcp_client.list_tools()

        # Convertir herramientas MCP a formato Claude
        self.tools_schema = [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}})
            }
            for tool in tools
        ]

        print(f"✅ {len(self.tools_schema)} herramientas disponibles\n")

    async def process_query(self, user_query: str) -> str:
        """Procesar consulta en lenguaje natural"""
        print(f"💬 Usuario: {user_query}\n")

        # Agregar mensaje del usuario
        self.conversation_history.append({
            "role": "user",
            "content": user_query
        })

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Llamar a Claude con herramientas
            response = self.anthropic.messages.create(
                model="claude-haiku-4-5",
                max_tokens=4096,
                system="""Eres un asistente experto en análisis de código con SonarQube.

Tienes acceso a herramientas MCP de SonarQube para:
- Listar proyectos
- Buscar issues (bugs, vulnerabilidades, code smells)
- Analizar quality gates
- Buscar hotspots de seguridad
- Analizar métricas de código

Usa las herramientas necesarias para responder las preguntas del usuario de forma precisa y útil.""",
                messages=self.conversation_history,
                tools=self.tools_schema
            )

            # Procesar respuesta
            assistant_content = []
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    tool_calls.append(block)
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })

            # Agregar respuesta del asistente al historial
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_content
            })

            # Si no hay tool calls, devolver respuesta
            if not tool_calls:
                final_text = next(
                    (block.text for block in response.content if block.type == "text"),
                    "No hay respuesta de texto"
                )
                return final_text

            # Ejecutar herramientas
            print(f"🔧 Ejecutando {len(tool_calls)} herramienta(s)...\n")
            tool_results = []

            for tool_call in tool_calls:
                print(f"  → {tool_call.name}")
                try:
                    result = await self.mcp_client.call_tool(
                        tool_call.name,
                        tool_call.input
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
                except Exception as e:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": f"Error: {str(e)}",
                        "is_error": True
                    })

            # Agregar resultados al historial
            self.conversation_history.append({
                "role": "user",
                "content": tool_results
            })

            print()

        return "⚠️ Se alcanzó el límite de iteraciones"


async def main():
    async with SonarQubeMCPClient(SERVER_URL, SONARQUBE_TOKEN) as mcp_client:
        agent = SonarQubeAgent(mcp_client)
        await agent.initialize()

        # Ejemplos de consultas
        queries = [
            "¿Cuántos proyectos tengo en SonarQube?",
            "¿Cuáles son los issues críticos abiertos en mi proyecto spring-boot-java8-demo?",
            "Dame un resumen del estado de calidad de mis proyectos"
        ]

        for query in queries:
            print("=" * 60)
            response = await agent.process_query(query)
            print(f"🤖 Asistente: {response}\n")

            # Limpiar historial entre consultas
            agent.conversation_history = []


async def interactive_mode():
    """Modo interactivo"""
    async with SonarQubeMCPClient(SERVER_URL, SONARQUBE_TOKEN) as mcp_client:
        agent = SonarQubeAgent(mcp_client)
        await agent.initialize()

        print("=" * 60)
        print("🤖 Agente SonarQube listo. Escribe 'salir' para terminar.")
        print("=" * 60 + "\n")

        while True:
            try:
                query = input("💬 Tú: ").strip()

                if query.lower() in ['salir', 'exit', 'quit']:
                    print("\n👋 ¡Hasta luego!")
                    break

                if not query:
                    continue

                print()
                response = await agent.process_query(query)
                print(f"🤖 Asistente: {response}\n")

            except KeyboardInterrupt:
                print("\n\n👋 ¡Hasta luego!")
                break


if __name__ == "__main__":
    # asyncio.run(main())
    asyncio.run(interactive_mode())
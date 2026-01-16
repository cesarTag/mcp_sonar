import asyncio
import json
import os
from anthropic import Anthropic

from guardrails_config import AgentGuardrails
from openrewrite_tool import openrewrite_tool
from plantuml_tool import plantuml_tool
from sonar_client import SonarQubeMCPClient
from github_tool import github_tool


SERVER_URL = os.getenv("SERVER_URL")
SONARQUBE_TOKEN = os.getenv("SONARQUBE_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


class SonarQubeAgent:
    def __init__(self, mcp_client: SonarQubeMCPClient):
        self.mcp_client = mcp_client
        self.openrewrite = openrewrite_tool
        self.github = github_tool
        self.plantuml = plantuml_tool
        self.anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.guardrails = AgentGuardrails()
        self.tools_schema = []
        self.conversation_history = []

    async def initialize(self):
        print("🔧 Cargando herramientas...")

        # 1. Cargar herramientas del servidor MCP SonarQube
        sonar_tools = await self.mcp_client.list_tools()
        sonar_schema = [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}})
            }
            for tool in sonar_tools
        ]

        # 2. Cargar herramientas locales de OpenRewrite
        openrewrite_schema = self.openrewrite.get_tools_schema()
        plantuml_schema = self.plantuml.get_tools_schema()
        github_schema = self.github.get_tools_schema()

        # 3. Combinar todas las herramientas
        self.tools_schema = sonar_schema + openrewrite_schema +github_schema+plantuml_schema

        print(f"✅ SonarQube: {len(sonar_schema)} herramientas")
        print(f"✅ OpenRewrite: {len(openrewrite_schema)} herramientas")
        print(f"✅ GitHub: {len(github_schema)} herramientas")
        print(f"✅ PlantUML: {len(plantuml_schema)} herramientas")
        print(f"📦 Total: {len(self.tools_schema)} herramientas disponibles\n")

    async def _execute_tool(self, tool_name: str, arguments: dict):
        """Ejecutar herramienta (local o remota)"""

        if tool_name.startswith("plantuml_"):
            return await self.plantuml.execute_tool(tool_name, arguments)

        if tool_name.startswith("github_"):
            return await self.github.execute_tool(tool_name, arguments)

        # Herramientas de OpenRewrite (locales)
        if tool_name.startswith("openrewrite_"):
            return await self.openrewrite.execute_tool(tool_name, arguments)

        # Herramientas de SonarQube (remotas)
        else:
            return await self.mcp_client.call_tool(tool_name, arguments)

    async def process_query(self, user_query: str) -> str:
        print(f"💬 Usuario: {user_query}\n")

        is_valid_intent, intent_error = self.guardrails.validate_intent(user_query)
        if not is_valid_intent:
            print("Query fuera de scope técnico", "WARNING")
            return intent_error

        # ✅ GUARDRAIL: Validar input del usuario
        is_valid, error_msg = self.guardrails.validate_user_input(user_query)
        if not is_valid:
            print(f"Input bloqueado: {error_msg}", "WARNING")
            return f"🚫 {error_msg}"



        self.conversation_history.append({
            "role": "user",
            "content": user_query
        })

        max_iterations = 50  # Aumentado para permitir más herramientas
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            response = self.anthropic.messages.create(
                model="claude-haiku-4-5",
                max_tokens=4096,
                system="""Asistente experto en análisis y migración de código Java.

SCOPE PERMITIDO:
- Análisis de código (SonarQube): métricas, issues, vulnerabilidades
- Migración/refactoring (OpenRewrite): actualización de versiones
- Repositorios (GitHub): lectura, clonación, búsqueda de código
- Diagramas (PlantUML): clases, secuencia, estados, componentes

Si la consulta NO es técnica relacionada con lo anterior, responde:
"Esta consulta está fuera de mi área. Solo ayudo con análisis de código, migraciones y diagramas técnicos."

CUÁNDO USAR CADA HERRAMIENTA:
- "diagrama/UML/visualizar" → PlantUML
- "métricas/calidad/issues" → SonarQube
- "leer código/repositorio" → GitHub
- "migrar/actualizar/refactor" → OpenRewrite

WORKFLOWS:
Diagramas: GitHub (leer código) → PlantUML (crear diagrama)
Reportes: GitHub → SonarQube → PlantUML → OpenRewrite → generar reporte

Explica brevemente qué herramienta usas.""",
                messages=self.conversation_history,
                tools=self.tools_schema
            )

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

            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_content
            })

            if not tool_calls:
                final_text = next(
                    (block.text for block in response.content if block.type == "text"),
                    "No hay respuesta"
                )
                # ✅ GUARDRAIL: Validar output del LLM
                is_valid, error_msg = self.guardrails.validate_llm_output(final_text)
                if not is_valid:
                    print(f"Output bloqueado: {error_msg}", "WARNING")
                    return "🚫 Respuesta bloqueada por contener información sensible"

                return final_text

            print(f"🔧 Ejecutando {len(tool_calls)} herramienta(s)...")
            tool_results = []

            for tool_call in tool_calls:
                # Determinar fuente de la herramienta - CORREGIDO
                tool_name = tool_call.name
                if tool_name.startswith("github_"):
                    tool_source = "GitHub"
                elif tool_name.startswith("openrewrite_"):
                    tool_source = "OpenRewrite"
                elif tool_name.startswith("plantuml_"):
                    tool_source = "PlantUML"
                else:
                    tool_source = "SonarQube"

                print(f"  → [{tool_source}] {tool_name}")

                if not self.guardrails.validate_tool_arguments(tool_name, tool_call.input):
                    print(f"Argumentos bloqueados para {tool_name}", "WARNING")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": "Operación bloqueada por guardrails de seguridad",
                        "is_error": True
                    })
                    continue

                try:
                    result = await self._execute_tool(
                        tool_name,
                        tool_call.input
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False, indent=2)
                    })
                except Exception as e:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": f"Error: {str(e)}",
                        "is_error": True
                    })

            self.conversation_history.append({
                "role": "user",
                "content": tool_results
            })

            print()

        return "⚠️ Límite de iteraciones alcanzado"


async def demo_mode():
    """Modo demo con ejemplos"""
    async with SonarQubeMCPClient(SERVER_URL, SONARQUBE_TOKEN) as mcp_client:
        agent = SonarQubeAgent(mcp_client)
        await agent.initialize()

        queries = [
            "¿Qué proyectos tengo en SonarQube?",
            "Dame un plan de actualización de código deprecado de Java 8 a Java 21 para el proyecto /path/to/my/project",
            "¿Qué recetas de migración están disponibles para Spring Boot?"
        ]

        for query in queries:
            print("=" * 60)
            response = await agent.process_query(query)
            print(f"🤖 Asistente:\n{response}\n")

            agent.conversation_history = []  # Limpiar entre consultas


async def interactive_mode():
    """Modo interactivo"""
    async with SonarQubeMCPClient(SERVER_URL, SONARQUBE_TOKEN) as mcp_client:
        agent = SonarQubeAgent(mcp_client)
        await agent.initialize()

        print("=" * 60)
        print("🤖 Agente SonarQube + OpenRewrite + GitHub listo")
        print("   Pregunta sobre calidad de código o migraciones")
        print("   Escribe 'salir' para terminar")
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
                print(f"🤖 Asistente:\n{response}\n")

            except KeyboardInterrupt:
                print("\n\n👋 ¡Hasta luego!")
                break


if __name__ == "__main__":
    # Elige el modo:
    # asyncio.run(demo_mode())
    asyncio.run(interactive_mode())
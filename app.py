import asyncio
import time
from pathlib import Path
import streamlit as st
import os
from dotenv import load_dotenv
from sonar_client import SonarQubeMCPClient
from agente import SonarQubeAgent
from openrewrite_tool import openrewrite_tool
from github_tool import github_tool
from plantuml_tool import plantuml_tool
import json

load_dotenv()
SERVER_URL = os.getenv("SERVER_URL")
SONARQUBE_TOKEN = os.getenv("SONARQUBE_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Configuración de página
st.set_page_config(
    page_title="Asistente de migracion y reporteria de proyectos",
    page_icon="🤖",
    layout="wide"
)

# Título
st.title("Asistente de Migracion y Reporteria")
st.markdown("Asistente experto en SonarQube, OpenRewrite, GitHub y PlantUML")

# Inicializar session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent_ready" not in st.session_state:
    st.session_state.agent_ready = False

if "mcp_client" not in st.session_state:
    st.session_state.mcp_client = None

if "agent" not in st.session_state:
    st.session_state.agent = None

if "last_diagrams" not in st.session_state:
    st.session_state.last_diagrams = []


async def initialize_agent():
    """Inicializar el agente y cliente MCP"""
    if st.session_state.agent_ready:
        return

    with st.spinner("🔌 Conectando a servidores MCP..."):
        # Crear cliente MCP
        st.session_state.mcp_client = SonarQubeMCPClient(SERVER_URL, SONARQUBE_TOKEN)
        await st.session_state.mcp_client.__aenter__()

        # Crear agente
        st.session_state.agent = SonarQubeAgent(st.session_state.mcp_client)
        st.session_state.agent.openrewrite = openrewrite_tool
        st.session_state.agent.github = github_tool
        st.session_state.agent.plantuml = plantuml_tool

        # Inicializar herramientas
        await st.session_state.agent.initialize()

        st.session_state.agent_ready = True


def extract_diagram_paths(agent_conversation_history):
    """Extraer rutas de diagramas de la conversación del agente"""
    diagram_paths = []

    # Buscar en el historial del agente (últimos 5 mensajes)
    for msg in agent_conversation_history[-5:]:
        if msg.get("role") == "user":
            content = msg.get("content", [])

            # Contenido puede ser lista de tool_results
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        tool_content = item.get("content", "")

                        # Parsear JSON del resultado
                        try:
                            result = json.loads(tool_content)
                            if result.get("status") == "success" and "diagram_file" in result:
                                diagram_path = Path(result["diagram_file"])
                                if diagram_path.exists():
                                    diagram_paths.append({
                                        "path": diagram_path,
                                        "name": result.get("message", diagram_path.name)
                                    })
                        except (json.JSONDecodeError, TypeError):
                            pass

    return diagram_paths


async def process_message(user_input: str):
    """Procesar mensaje del usuario"""
    # Timestamp antes de procesar
    time_before = time.time()

    # Agregar mensaje del usuario al chat
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })

    # Mostrar mensaje del usuario
    with st.chat_message("user"):
        st.markdown(user_input)

    # Procesar con el agente
    with st.chat_message("assistant"):
        message_placeholder = st.empty()

        # Mostrar indicador de procesamiento
        with st.spinner("Procesando..."):
            response = await st.session_state.agent.process_query(user_input)

        # Mostrar respuesta en markdown
        message_placeholder.markdown(response)

        # Extraer diagramas del historial del agente
        diagrams = extract_diagram_paths(st.session_state.agent.conversation_history)

        # Si no hay diagramas en el historial, buscar por timestamp
        if not diagrams:
            plantuml_output = Path("/tmp/plantuml-diagrams")
            if plantuml_output.exists():
                # Buscar archivos PNG creados después de time_before
                recent_files = [
                    f for f in plantuml_output.glob("*.png")
                    if f.stat().st_mtime > time_before
                ]

                diagrams = [
                    {"path": f, "name": f.stem.replace('_', ' ').title()}
                    for f in recent_files
                ]

        # Mostrar diagramas si existen
        if diagrams:
            st.markdown("---")
            st.markdown("### 📊 Diagramas UML Generados")

            for idx, diagram in enumerate(diagrams):
                st.markdown(f"**{diagram['name']}**")

                # Crear columnas para controlar el ancho de la imagen
                col_left, col_center, col_right = st.columns([1, 10, 1])

                with col_center:
                    # Imagen con ancho controlado
                    st.image(
                        str(diagram['path']),
                        width=800,  # Ancho máximo en pixels
                        caption=diagram['name']
                    )

                # Botones de descarga en una fila compacta
                btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 10])

                with btn_col1:
                    with open(diagram['path'], "rb") as f:
                        st.download_button(
                            label="📥 PNG",
                            data=f,
                            file_name=diagram['path'].name,
                            mime="image/png",
                            key=f"download_png_{idx}_{diagram['path'].name}",
                            use_container_width=True
                        )

                with btn_col2:
                    # Botón para descargar .puml
                    puml_path = diagram['path'].with_suffix('.puml')
                    if puml_path.exists():
                        with open(puml_path, "r") as f:
                            st.download_button(
                                label="📄 PUML",
                                data=f.read(),
                                file_name=puml_path.name,
                                mime="text/plain",
                                key=f"download_puml_{idx}_{puml_path.name}",
                                use_container_width=True
                            )

                # Expander con el código PlantUML
                puml_path = diagram['path'].with_suffix('.puml')
                if puml_path.exists():
                    with st.expander("👁️ Ver código PlantUML"):
                        code = puml_path.read_text(encoding='utf-8')
                        st.code(code, language="plantuml")

                st.markdown("")  # Espacio entre diagramas

            # Guardar diagramas en session state
            st.session_state.last_diagrams = diagrams

    # Agregar respuesta al historial
    st.session_state.messages.append({
        "role": "assistant",
        "content": response,
        "diagrams": diagrams
    })


def main():
    """Función principal de la app"""

    # Inicializar agente si no está listo
    if not st.session_state.agent_ready:
        asyncio.run(initialize_agent())
        st.success("✅ Agente inicializado correctamente")

    # Mostrar historial de mensajes
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # Mostrar diagramas asociados si existen
            if message.get("diagrams"):
                st.markdown("---")
                for diag_idx, diagram in enumerate(message["diagrams"]):
                    if diagram['path'].exists():
                        # Imagen centrada con ancho controlado
                        col_left, col_center, col_right = st.columns([1, 10, 1])
                        with col_center:
                            st.image(
                                str(diagram['path']),
                                width=800,
                                caption=diagram['name']
                            )

    # Input del usuario
    if prompt := st.chat_input("Escribe tu consulta aquí..."):
        # Procesar mensaje
        asyncio.run(process_message(prompt))
        st.rerun()


    # Sidebar con información
    with st.sidebar:
        st.header("ℹ️ Información")

        if st.session_state.agent_ready:
            st.success("🟢 Agente activo")

            # Mostrar herramientas disponibles
            with st.expander("🔧 Herramientas disponibles"):
                sonar_count = sum(1 for t in st.session_state.agent.tools_schema
                                  if not t["name"].startswith(("openrewrite_", "github_", "plantuml_")))
                openrewrite_count = sum(1 for t in st.session_state.agent.tools_schema
                                        if t["name"].startswith("openrewrite_"))
                github_count = sum(1 for t in st.session_state.agent.tools_schema
                                   if t["name"].startswith("github_"))
                plantuml_count = sum(1 for t in st.session_state.agent.tools_schema
                                     if t["name"].startswith("plantuml_"))

                st.write(f"**SonarQube:** {sonar_count} herramientas")
                st.write(f"**OpenRewrite:** {openrewrite_count} herramientas")
                st.write(f"**GitHub:** {github_count} herramientas")
                st.write(f"**PlantUML:** {plantuml_count} herramientas")
                st.write(f"**Total:** {len(st.session_state.agent.tools_schema)} herramientas")
        else:
            st.warning("🟡 Inicializando...")

        st.divider()

        st.markdown("""
        ### 💡 Ejemplos de preguntas:
    
        **SonarQube:**
        - ¿Cuántos proyectos tengo?
        - ¿Cuáles son los issues críticos?
        - Analiza la calidad del proyecto X
    
        **GitHub:**
        - Lista mis repositorios
        - Clona el repo X y muéstrame el pom.xml
        - Busca código deprecated en mis repos
    
        **OpenRewrite:**
        - Dame un plan de migración de Java 8 a 21
        - ¿Qué recetas de migración existen?
    
        **PlantUML:**
        - Genera un diagrama de clases para UserService
        - Crea un diagrama de secuencia de login
        - Diagrama de estados para un pedido
        - Usa este código PlantUML: @startuml...
    
        **Combinado:**
        - Analiza mi proyecto X y genera diagrama de arquitectura
        - Clona el repo Y y genera diagrama de clases
        """)

        st.divider()

        # Mostrar últimos diagramas generados en miniatura
        if st.session_state.last_diagrams:
            st.markdown("### 📊 Últimos diagramas")
            for diagram in st.session_state.last_diagrams[:3]:
                if diagram['path'].exists():
                    with st.expander(f"📄 {diagram['name'][:30]}..."):
                        st.image(str(diagram['path']), width=250)

        st.divider()

        # Configuración de visualización
        with st.expander("⚙️ Configuración de visualización"):
            st.markdown("**Tamaño de imágenes:**")
            st.info("Las imágenes se muestran con ancho máximo de 800px para mejor legibilidad")
            st.markdown("**Tips:**")
            st.markdown("- Haz clic en la imagen para expandir")
            st.markdown("- Descarga PNG para usar en documentos")
            st.markdown("- Descarga PUML para editar el código")

        st.divider()

        # Botón para limpiar historial
        if st.button("🗑️ Limpiar conversación", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_diagrams = []
            if st.session_state.agent:
                st.session_state.agent.conversation_history = []
            st.rerun()


if __name__ == "__main__":
    main()
import os
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_classic.agents import AgentExecutor
from langchain_classic.agents import create_tool_calling_agent
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
import httpx
from dotenv import load_dotenv

# Carga variables de entorno
load_dotenv()
app = FastAPI(title="Agente SonarQube")

# Configuración SonarQube
SONARQUBE_URL = os.getenv("SONARQUBE_URL")
SONARQUBE_TOKEN = os.getenv("SONARQUBE_TOKEN")
SONARQUBE_ORG = os.getenv("SONARQUBE_ORG")


def get_headers():
    return {"Authorization": f"Bearer {SONARQUBE_TOKEN}"}


# ==================== HERRAMIENTAS ====================
@tool(description="Busca y lista todos los proyectos disponibles en SonarQube. Permite filtrar por nombre o clave usando un query de búsqueda opcional.")
async def buscar_proyectos_sonar(query: str = "") -> str:
    """Busca proyectos en SonarQube por nombre o clave"""
    async with httpx.AsyncClient() as client:
        params = {"organization": SONARQUBE_ORG}
        if query:
            params["q"] = query

        resp = await client.get(
            f"{SONARQUBE_URL}/api/projects/search",
            headers=get_headers(),
            params=params
        )
        data = resp.json()
        proyectos = [f"{p['name']} (key: {p['key']})" for p in data.get("components", [])]
        return f"Proyectos encontrados:\n" + "\n".join(proyectos)


@tool
async def obtener_metricas_sonar(project_key: str) -> str:
    """Obtiene métricas de calidad de código de un proyecto"""
    async with httpx.AsyncClient() as client:
        params = {
            "component": project_key,
            "metricKeys": "bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density"
        }

        resp = await client.get(
            f"{SONARQUBE_URL}/api/measures/component",
            headers=get_headers(),
            params=params
        )
        data = resp.json()

        metricas = {m["metric"]: m.get("value", "N/A") for m in data["component"]["measures"]}

        return f"""Métricas de {project_key}:
- Bugs: {metricas.get('bugs', 'N/A')}
- Vulnerabilidades: {metricas.get('vulnerabilities', 'N/A')}
- Code Smells: {metricas.get('code_smells', 'N/A')}
- Cobertura: {metricas.get('coverage', 'N/A')}%
- Duplicación: {metricas.get('duplicated_lines_density', 'N/A')}%"""


@tool(description="Lista los primeros 10 issues activos de un proyecto filtrados por tipo. Tipos disponibles: BUG (errores), VULNERABILITY (vulnerabilidades de seguridad), CODE_SMELL (problemas de mantenibilidad), SECURITY_HOTSPOT (puntos de seguridad a revisar).")
async def listar_issues_sonar(project_key: str, tipo: str = "BUG") -> str:
    """
    Lista issues de un proyecto.
    tipo: BUG, VULNERABILITY, CODE_SMELL
    """
    async with httpx.AsyncClient() as client:
        params = {
            "componentKeys": project_key,
            "types": tipo,
            "ps": 10
        }

        resp = await client.get(
            f"{SONARQUBE_URL}/api/issues/search",
            headers=get_headers(),
            params=params
        )
        data = resp.json()

        total = data.get("total", 0)
        resultado = f"Total de {tipo}: {total}\n\nPrimeros 10:\n"

        for i, issue in enumerate(data.get("issues", [])[:10], 1):
            resultado += f"{i}. [{issue['severity']}] {issue['message']}\n"

        return resultado


@tool(description="Obtiene el estado actual del Quality Gate de un proyecto (PASSED/FAILED) junto con todas las condiciones evaluadas. Indica si el proyecto cumple con los estándares de calidad definidos.")
async def obtener_quality_gate(project_key: str) -> str:
    """Obtiene el estado del Quality Gate de un proyecto"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SONARQUBE_URL}/api/qualitygates/project_status",
            headers=get_headers(),
            params={"projectKey": project_key}
        )
        data = resp.json()
        status = data["projectStatus"]["status"]

        resultado = f"Quality Gate: {status}\n\nCondiciones:\n"
        for condition in data["projectStatus"].get("conditions", []):
            resultado += f"- {condition['metricKey']}: {condition['actualValue']} ({condition['status']})\n"

        return resultado


@tool(description="Lista todas las reglas que han sido violadas en un proyecto, ordenadas por frecuencia de violación. Muestra cuántas veces se violó cada regla, su severidad y tipo. Permite filtrar por categoría (SECURITY, RELIABILITY, MAINTAINABILITY) y severidad.")
async def listar_reglas_violadas(project_key: str, categoria: str = "", severidad: str = "") -> str:
    """
    Lista las reglas que han sido violadas en un proyecto.
    categoria: SECURITY, RELIABILITY, MAINTAINABILITY (opcional)
    severidad: BLOCKER, CRITICAL, MAJOR, MINOR, INFO (opcional)
    """
    async with httpx.AsyncClient() as client:
        params = {
            "componentKeys": project_key,
            "resolved": "false",  # Solo issues no resueltos
            "ps": 100,
            "facets": "rules"
        }

        # Mapeo de categorías a tipos de issues
        if categoria:
            tipo_map = {
                "SECURITY": "VULNERABILITY,SECURITY_HOTSPOT",
                "RELIABILITY": "BUG",
                "MAINTAINABILITY": "CODE_SMELL"
            }
            params["types"] = tipo_map.get(categoria.upper(), "")

        if severidad:
            params["severities"] = severidad.upper()

        resp = await client.get(
            f"{SONARQUBE_URL}/api/issues/search",
            headers=get_headers(),
            params=params
        )
        data = resp.json()

        # Agrupar issues por regla
        reglas_violadas = {}
        for issue in data.get("issues", []):
            rule_key = issue["rule"]
            if rule_key not in reglas_violadas:
                reglas_violadas[rule_key] = {
                    "count": 0,
                    "message": issue["message"],
                    "severity": issue["severity"],
                    "type": issue["type"]
                }
            reglas_violadas[rule_key]["count"] += 1

        # Ordenar por cantidad de violaciones
        reglas_ordenadas = sorted(
            reglas_violadas.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )

        resultado = f"Reglas violadas en {project_key}:\n"
        resultado += f"Total de issues: {data.get('total', 0)}\n"
        resultado += f"Reglas diferentes violadas: {len(reglas_violadas)}\n\n"

        for i, (rule_key, info) in enumerate(reglas_ordenadas[:20], 1):
            resultado += f"{i}. {rule_key} ({info['count']} violaciones)\n"
            resultado += f"   Tipo: {info['type']} | Severidad: {info['severity']}\n"
            resultado += f"   Descripción: {info['message']}\n\n"

        return resultado


@tool(description="Obtiene información detallada de una regla específica: nombre completo, descripción técnica, tipo, severidad, lenguaje al que aplica y tags asociados. Útil para entender qué evalúa exactamente una regla.")
async def obtener_detalle_regla(rule_key: str) -> str:
    """Obtiene información detallada de una regla específica"""
    async with httpx.AsyncClient() as client:
        params = {"rule": rule_key}

        resp = await client.get(
            f"{SONARQUBE_URL}/api/rules/show",
            headers=get_headers(),
            params=params
        )
        data = resp.json()
        rule = data.get("rule", {})

        resultado = f"Regla: {rule.get('key', 'N/A')}\n"
        resultado += f"Nombre: {rule.get('name', 'N/A')}\n"
        resultado += f"Tipo: {rule.get('type', 'N/A')}\n"
        resultado += f"Severidad: {rule.get('severity', 'N/A')}\n"
        resultado += f"Lenguaje: {rule.get('lang', 'N/A')}\n\n"
        resultado += f"Descripción:\n{rule.get('htmlDesc', 'N/A')[:500]}...\n"

        # Tags
        if rule.get('tags'):
            resultado += f"\nTags: {', '.join(rule['tags'])}\n"

        return resultado


@tool(description="Analiza la distribución de todas las violaciones de un proyecto agrupadas por nivel de severidad: BLOCKER, CRITICAL, MAJOR, MINOR, INFO. Muestra el total de issues por cada nivel.")
async def analizar_violaciones_por_severidad(project_key: str) -> str:
    """Analiza la distribución de violaciones por severidad"""
    async with httpx.AsyncClient() as client:
        params = {
            "componentKeys": project_key,
            "resolved": "false",
            "facets": "severities",
            "ps": 1
        }

        resp = await client.get(
            f"{SONARQUBE_URL}/api/issues/search",
            headers=get_headers(),
            params=params
        )
        data = resp.json()

        resultado = f"Distribución de violaciones por severidad en {project_key}:\n\n"
        resultado += f"Total de issues: {data.get('total', 0)}\n\n"

        # Obtener facets de severidad
        for facet in data.get("facets", []):
            if facet["property"] == "severities":
                for value in facet["values"]:
                    resultado += f"- {value['val']}: {value['count']} issues\n"

        return resultado


@tool(description="Identifica las 10 reglas más violadas dentro de una categoría específica. SECURITY: problemas de seguridad, RELIABILITY: bugs que afectan funcionamiento, MAINTAINABILITY: deuda técnica. Ordena por cantidad de violaciones.")
async def top_reglas_violadas_por_categoria(project_key: str, categoria: str) -> str:
    """
    Muestra las reglas más violadas de una categoría específica.
    categoria: SECURITY, RELIABILITY, MAINTAINABILITY
    """
    tipo_map = {
        "SECURITY": "VULNERABILITY,SECURITY_HOTSPOT",
        "RELIABILITY": "BUG",
        "MAINTAINABILITY": "CODE_SMELL"
    }

    tipos = tipo_map.get(categoria.upper(), "BUG")

    async with httpx.AsyncClient() as client:
        params = {
            "componentKeys": project_key,
            "types": tipos,
            "resolved": "false",
            "ps": 100
        }

        resp = await client.get(
            f"{SONARQUBE_URL}/api/issues/search",
            headers=get_headers(),
            params=params
        )
        data = resp.json()

        # Agrupar por regla
        reglas = {}
        for issue in data.get("issues", []):
            rule = issue["rule"]
            if rule not in reglas:
                reglas[rule] = {
                    "count": 0,
                    "severity": issue["severity"],
                    "message": issue["message"]
                }
            reglas[rule]["count"] += 1

        # Top 10
        top_reglas = sorted(reglas.items(), key=lambda x: x[1]["count"], reverse=True)[:10]

        resultado = f"Top 10 reglas de {categoria} más violadas en {project_key}:\n\n"

        for i, (rule_key, info) in enumerate(top_reglas, 1):
            resultado += f"{i}. {rule_key}\n"
            resultado += f"   Violaciones: {info['count']}\n"
            resultado += f"   Severidad: {info['severity']}\n"
            resultado += f"   Mensaje: {info['message']}\n\n"

        return resultado


@tool(description="Busca violaciones en archivos específicos del proyecto. Si se proporciona un nombre de archivo, lista todos sus issues. Si no se especifica archivo, muestra los 15 archivos con más problemas de calidad.")
async def buscar_violaciones_por_archivo(project_key: str, archivo: str = "") -> str:
    """Busca violaciones en archivos específicos o lista archivos con más issues"""
    async with httpx.AsyncClient() as client:
        params = {
            "componentKeys": project_key,
            "resolved": "false",
            "ps": 100
        }

        if archivo:
            params["componentKeys"] = f"{project_key}:{archivo}"

        resp = await client.get(
            f"{SONARQUBE_URL}/api/issues/search",
            headers=get_headers(),
            params=params
        )
        data = resp.json()

        if archivo:
            resultado = f"Issues en archivo {archivo}:\n"
            resultado += f"Total: {data.get('total', 0)}\n\n"

            for i, issue in enumerate(data.get("issues", [])[:10], 1):
                resultado += f"{i}. [{issue['severity']}] {issue['rule']}\n"
                resultado += f"   Línea: {issue.get('line', 'N/A')}\n"
                resultado += f"   Mensaje: {issue['message']}\n\n"
        else:
            # Agrupar por archivo
            archivos = {}
            for issue in data.get("issues", []):
                comp = issue.get("component", "").split(":")[-1]
                archivos[comp] = archivos.get(comp, 0) + 1

            top_archivos = sorted(archivos.items(), key=lambda x: x[1], reverse=True)[:15]

            resultado = f"Top 15 archivos con más issues:\n\n"
            for i, (archivo, count) in enumerate(top_archivos, 1):
                resultado += f"{i}. {archivo}: {count} issues\n"

        return resultado


# ==================== SCHEMAS PARA OUTPUT ESTRUCTURADO ====================

class Violacion(BaseModel):
    regla: str = Field(description="Identificador de la regla violada")
    severidad: str = Field(description="BLOCKER, CRITICAL, MAJOR, MINOR, INFO")
    tipo: str = Field(description="BUG, VULNERABILITY, CODE_SMELL, SECURITY_HOTSPOT")
    mensaje: str = Field(description="Descripción del problema")
    archivo: Optional[str] = Field(default=None, description="Archivo donde ocurre")
    linea: Optional[int] = Field(default=None, description="Número de línea")
    recomendacion: str = Field(description="Cómo resolver el problema")

class ResumenCategoria(BaseModel):
    categoria: str = Field(description="SECURITY, RELIABILITY, MAINTAINABILITY")
    total_issues: int = Field(description="Cantidad total de issues")
    criticos: int = Field(description="Issues críticos o bloqueantes")
    recomendacion_general: str = Field(description="Recomendación prioritaria")

class AnalisisCalidad(BaseModel):
    proyecto: str = Field(description="Nombre del proyecto analizado")
    estado_quality_gate: str = Field(description="PASSED, FAILED, ERROR")
    metricas_clave: dict = Field(description="Bugs, vulnerabilidades, code smells, cobertura")
    resumen_por_categoria: List[ResumenCategoria] = Field(description="Análisis por categoría")
    top_violaciones: List[Violacion] = Field(description="Top 10 violaciones más críticas")
    recomendaciones_prioritarias: List[str] = Field(description="3-5 acciones prioritarias")
    nivel_riesgo: str = Field(description="ALTO, MEDIO, BAJO")


# ==================== AGENTE ====================

'''llm = ChatAnthropic(
    model="claude-haiku-4-5",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)'''

llm = ChatOpenAI(
    model="gpt-5-nano",
    api_key=os.getenv("OPENAI_API_KEY"), temperature=0)

# LLM con output estructurado
llm_structured = llm.with_structured_output(AnalisisCalidad)

tools = [
    buscar_proyectos_sonar,
    obtener_metricas_sonar,
    listar_issues_sonar,
    obtener_quality_gate,
    listar_reglas_violadas,
    obtener_detalle_regla,
    analizar_violaciones_por_severidad,
    top_reglas_violadas_por_categoria,
    buscar_violaciones_por_archivo
]

prompt = ChatPromptTemplate.from_messages([
    ("system", """Eres un experto en seguridad y calidad de código especializado en análisis de SonarQube.

Tu objetivo es identificar vulnerabilidades, violaciones de reglas y proporcionar recomendaciones accionables.

RESPONSABILIDADES CLAVE:
1. Analizar vulnerabilidades de seguridad con prioridad crítica.
2. Identificar patrones de violaciones recurrentes.
3. Evaluar el impacto real de cada issue en la producción.
4. Proporcionar recomendaciones específicas y priorizadas.
5. Clasificar el nivel de riesgo del proyecto.

CUANDO ANALICES ISSUES:
- Prioriza BLOCKER y CRITICAL sobre otros.
- Agrupa violaciones similares para identificar patrones.
- Para cada vulnerabilidad, explica el riesgo real y cómo explotarla.
- Da ejemplos de código corregido cuando sea posible.
- Considera el contexto del negocio en tus recomendaciones.

FORMATO DE RESPUESTA:
Siempre estructura tu análisis en este formato JSON:
- proyecto: nombre del proyecto
- estado_quality_gate: PASSED/FAILED
- metricas_clave: bugs, vulnerabilidades, code smells, cobertura
- resumen_por_categoria: análisis por SECURITY, RELIABILITY, MAINTAINABILITY
- top_violaciones: 10 issues más críticos con sus recomendaciones
- recomendaciones_prioritarias: 3-5 acciones inmediatas ordenadas por impacto
- nivel_riesgo: ALTO (>10 critical), MEDIO (1-10 critical), BAJO (0 critical)

RECOMENDACIONES DEBEN SER:
✓ Específicas: "Sanitizar entrada en UserController línea 45".
✓ Accionables: "Implementar prepared statements en DatabaseHelper".
✓ Priorizadas: "URGENTE: Cerrar SQL injection en endpoint /api/users".

Usa tus herramientas de SonarQube para obtener datos reales y actualizados."""),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}")
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)


# ==================== API ====================

class AgentRequest(BaseModel):
    query: str


@app.post("/consulta_basica")
async def consultar_agente(request: AgentRequest):
    """Consulta al agente"""
    result = await agent_executor.ainvoke({"input": request.query})
    return {"respuesta": result["output"]}


@app.post("/consulta")
async def consultar_agente(request: AgentRequest):
    result = await agent_executor.ainvoke({"input": request.query})

    # Si usas structured output, convierte a dict
    if isinstance(result["output"], AnalisisCalidad):
        return result["output"].model_dump()  # Pydantic v2
        # o result["output"].dict() para Pydantic v1

    return {"respuesta": result["output"]}

@app.get("/")
async def root():
    return {
        "servicio": "Agente SonarQube",
        "herramientas": [t.name for t in tools]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
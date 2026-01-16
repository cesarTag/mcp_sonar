from typing import Dict, Any
import re


class AgentGuardrails:
    """Guardrails simples sin dependencias externas"""

    def __init__(self):
        self.suspicious_urls = [
            "localhost", "127.0.0.1", "192.168.", "10.0.",
            "172.16.", "internal", "file://", ".local"
        ]

        self.dangerous_commands = [
            "rm -rf", "delete", "drop database", "format",
            "__import__", "eval(", "exec(", "system("
        ]

        self.api_token_patterns = [
            r'sk-[a-zA-Z0-9]{48}',  # OpenAI
            r'sk-ant-[a-zA-Z0-9\-]{95}',  # Anthropic
            r'ghp_[a-zA-Z0-9]{36}',  # GitHub
            r'sq[a-z0-9]{40}',  # SonarQube
        ]

        self.technical_keywords = [
            "sonarqube", "proyecto", "código", "codigo", "java", "spring",
            "métricas", "metricas", "calidad", "vulnerabilidad", "issue",
            "migración", "migracion", "actualización", "actualizacion",
            "refactoring", "reporte", "análisis", "analisis", "diagrama",
            "github", "repositorio", "commit", "openrewrite", "plantuml",
            "clase", "método", "metodo", "función", "funcion"
        ]

        self.off_topic_keywords = [
            "historia", "cuento", "poema", "canción", "cancion",
            "cocina", "comida", "chiste", "entretenimiento",
            "película", "pelicula", "música", "musica", "juego",
            "salud", "ejercicio", "viaje", "turismo"
        ]

        self.technical_keywords = [
            "sonarqube", "proyecto", "código", "codigo", "java", "spring",
            "métricas", "metricas", "calidad", "vulnerabilidad", "issue",
            "migración", "migracion", "actualización", "actualizacion",
            "refactoring", "reporte", "análisis", "analisis", "diagrama",
            "github", "repositorio", "commit", "openrewrite", "plantuml",
            "clase", "método", "metodo", "función", "funcion"
        ]

        self.off_topic_keywords = [
            "historia", "cuento", "poema", "canción", "cancion",
            "receta", "cocina", "comida", "chiste", "entretenimiento",
            "película", "pelicula", "música", "musica", "juego",
            "salud", "ejercicio", "viaje", "turismo"
        ]


    def validate_intent(self, user_query: str) -> tuple[bool, str]:
            """Valida que la query esté dentro del scope técnico"""
            query_lower = user_query.lower()

            # Calcular score
            technical_score = sum(1 for kw in self.technical_keywords if kw in query_lower)
            off_topic_score = sum(1 for kw in self.off_topic_keywords if kw in query_lower)

            # Si hay keywords claramente off-topic
            if off_topic_score > 0:
                return False, self._get_scope_message()

            # Si es muy corto y no tiene keywords técnicas (ej: "hola", "ayuda")
            if len(query_lower.split()) < 3 and technical_score == 0:
                # Permitir saludos básicos
                greetings = ["hola", "hi", "hey", "buenos", "buenas"]
                if any(g in query_lower for g in greetings):
                    return True, ""
                return False, self._get_scope_message()

            # Si tiene al menos 1 keyword técnica o es una pregunta sobre el sistema
            system_questions = ["qué proyectos", "que proyectos", "cuales", "cuáles",
                                "lista", "muestra", "dame", "obtén", "obten"]
            if technical_score > 0 or any(sq in query_lower for sq in system_questions):
                return True, ""

            # Queries muy largas sin keywords → probablemente off-topic
            if len(query_lower.split()) > 10 and technical_score == 0:
                return False, self._get_scope_message()

            # Por defecto permitir (ser permisivo en casos ambiguos)
            return True, ""

    def _get_scope_message(self) -> str:
            """Mensaje cuando query está fuera de scope"""
            return """ Esta consulta está fuera de mi área de especialización.

    Puedo ayudarte con:
    - Análisis de código y métricas de SonarQube
    - Migraciones con OpenRewrite (Java 8→21, Spring Boot, etc)
    - Repositorios de GitHub (lectura, análisis, clonación)
    - Generación de diagramas UML (clases, secuencia, componentes)

    Ejemplo: "Dame un reporte de calidad del proyecto spring-petmascotas"
             "Genera un diagrama de clases del proyecto X"
             "Crea un plan de migración a Java 21" """


    def validate_user_input(self, user_query: str) -> tuple[bool, str]:
        """Valida el input del usuario"""
        query_lower = user_query.lower()

        # Validar URLs sospechosas
        for url_pattern in self.suspicious_urls:
            if url_pattern in query_lower:
                return False, f"Input rechazado: URL sospechosa detectada ({url_pattern})"

        # Validar comandos peligrosos
        for cmd in self.dangerous_commands:
            if cmd in query_lower:
                return False, f"Input rechazado: Comando peligroso detectado ({cmd})"

        return True, ""

    def validate_llm_output(self, response: str) -> tuple[bool, str]:
        """Valida que el LLM no filtre información sensible"""

        # Detectar tokens de API
        for pattern in self.api_token_patterns:
            if re.search(pattern, response):
                return False, "Output bloqueado: Token de API detectado"

        # Detectar keywords de secretos
        secret_keywords = ["password", "secret", "api_key", "token"]
        response_lower = response.lower()

        for keyword in secret_keywords:
            # Buscar patrones como "password: xyz123"
            pattern = rf'{keyword}\s*[:=]\s*[\w\-]{{8,}}'
            if re.search(pattern, response_lower):
                return False, f"Output bloqueado: Posible secreto detectado ({keyword})"

        return True, ""

    def validate_tool_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Valida argumentos de herramientas peligrosas"""

        # Validar github_clone
        if tool_name == "github_clone":
            url = str(arguments.get("url", "")).lower()
            for pattern in self.suspicious_urls:
                if pattern in url:
                    return False

        # Validar paths sospechosos
        if "path" in arguments:
            path = str(arguments["path"])
            if ".." in path or path.startswith("/etc") or path.startswith("/root"):
                return False

        # Validar recetas de OpenRewrite
        if tool_name.startswith("openrewrite_"):
            recipe = str(arguments.get("recipe", "")).lower()
            dangerous_ops = ["delete", "remove", "drop"]
            if any(op in recipe for op in dangerous_ops):
                return False

        return True
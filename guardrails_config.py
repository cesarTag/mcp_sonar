from guardrails import Guard
from guardrails.hub import DetectPII
from guardrails.validator_base import Validator, register_validator
from typing import Dict, Any
import re


@register_validator(name="detect_api_tokens", data_type="string")
class DetectAPITokens(Validator):
    """Detecta tokens de API en el texto"""

    def validate(self, value: str, metadata: Dict) -> str:
        patterns = [
            r'sk-[a-zA-Z0-9]{48}',  # OpenAI
            r'sk-ant-[a-zA-Z0-9\-]{95}',  # Anthropic
            r'ghp_[a-zA-Z0-9]{36}',  # GitHub
            r'sq[a-z0-9]{40}',  # SonarQube
        ]

        for pattern in patterns:
            if re.search(pattern, value):
                raise ValueError("Se detectó un posible token de API en el texto")

        return value


@register_validator(name="block_dangerous_commands", data_type="string")
class BlockDangerousCommands(Validator):
    """Bloquea comandos peligrosos en inputs"""

    def validate(self, value: str, metadata: Dict) -> str:
        dangerous_keywords = [
            "rm -rf", "delete", "drop database", "format",
            "__import__", "eval(", "exec(", "system("
        ]

        value_lower = value.lower()
        for keyword in dangerous_keywords:
            if keyword in value_lower:
                raise ValueError(f"Comando peligroso detectado: {keyword}")

        return value


class AgentGuardrails:
    def __init__(self):
        # Validador de inputs del usuario (sin toxic_language)
        self.input_guard = Guard().use_many(
            DetectPII(pii_entities=["EMAIL_ADDRESS", "PHONE_NUMBER", "API_KEY"]),
            BlockDangerousCommands(),
            DetectAPITokens()
        )

        # Validador de outputs del LLM
        self.output_guard = Guard().use_many(
            DetectPII(pii_entities=["API_KEY", "PASSWORD", "SECRET"]),
            DetectAPITokens()  # ✅ Validador custom
        )

    def validate_user_input(self, user_query: str) -> tuple[bool, str]:
        """Valida el input del usuario"""
        try:
            self.input_guard.validate(user_query)
            return True, ""
        except Exception as e:
            return False, f"Input rechazado: {str(e)}"

    def validate_llm_output(self, response: str) -> tuple[bool, str]:
        """Valida que el LLM no filtre información sensible"""
        try:
            self.output_guard.validate(response)
            return True, ""
        except Exception as e:
            return False, f"Output bloqueado: {str(e)}"

    def validate_tool_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Valida argumentos de herramientas peligrosas"""
        # Validar URLs sospechosas
        if tool_name == "github_clone":
            url = arguments.get("url", "")
            if any(keyword in url.lower() for keyword in ["localhost", "127.0.0.1", "internal", "192.168"]):
                return False

        # Validar paths fuera del proyecto
        if "path" in arguments:
            path = str(arguments["path"])
            if ".." in path or path.startswith("/etc") or path.startswith("/root"):
                return False

        # Validar recetas peligrosas en OpenRewrite
        if tool_name.startswith("openrewrite_"):
            recipe = str(arguments.get("recipe", ""))
            if any(dangerous in recipe.lower() for dangerous in ["delete", "remove", "drop"]):
                return False

        return True
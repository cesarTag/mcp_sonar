import asyncio
import subprocess
import json
import os
from typing import Dict, List, Optional
from pathlib import Path


class GitHubTool:
    """Herramienta para interactuar con GitHub usando gh CLI"""

    def __init__(self, cache_dir: str = "/tmp/github-cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_tools_schema(self) -> List[Dict]:
        """Definir herramientas disponibles"""
        return [
            {
                "name": "github_list_repositories",
                "description": "Lista repositorios del usuario autenticado o de una organización específica en GitHub",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "org": {
                            "type": "string",
                            "description": "Nombre de la organización (opcional, si no se provee lista repos del usuario)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Número máximo de repos a listar",
                            "default": 30
                        }
                    }
                }
            },
            {
                "name": "github_get_repository_info",
                "description": "Obtiene información detallada de un repositorio específico incluyendo descripción, lenguajes, branches, etc.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Propietario del repositorio (usuario u organización)"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Nombre del repositorio"
                        }
                    },
                    "required": ["owner", "repo"]
                }
            },
            {
                "name": "github_clone_repository",
                "description": "Clona un repositorio de GitHub al filesystem local para poder trabajar con el código fuente",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Propietario del repositorio"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Nombre del repositorio"
                        },
                        "branch": {
                            "type": "string",
                            "description": "Branch específico a clonar (opcional)",
                            "default": "main"
                        }
                    },
                    "required": ["owner", "repo"]
                }
            },
            {
                "name": "github_get_file_content",
                "description": "Lee el contenido de un archivo específico de un repositorio en GitHub",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Propietario del repositorio"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Nombre del repositorio"
                        },
                        "path": {
                            "type": "string",
                            "description": "Ruta del archivo en el repositorio (ej: 'src/main/Main.java')"
                        },
                        "branch": {
                            "type": "string",
                            "description": "Branch del que leer (opcional)",
                            "default": "main"
                        }
                    },
                    "required": ["owner", "repo", "path"]
                }
            },
            {
                "name": "github_search_code",
                "description": "Busca código en repositorios de GitHub usando queries específicas",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Query de búsqueda (ej: 'deprecated language:java')"
                        },
                        "owner": {
                            "type": "string",
                            "description": "Limitar búsqueda a repos de este owner (opcional)"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Limitar búsqueda a este repo específico (opcional)"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """Ejecutar herramienta según el nombre"""
        handlers = {
            "github_list_repositories": self.list_repositories,
            "github_get_repository_info": self.get_repository_info,
            "github_clone_repository": self.clone_repository,
            "github_get_file_content": self.get_file_content,
            "github_search_code": self.search_code
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Herramienta desconocida: {tool_name}"}

        try:
            return await handler(**arguments)
        except Exception as e:
            return {"error": str(e)}

    async def _run_gh_command(self, args: List[str]) -> Dict:
        """Ejecutar comando gh CLI"""
        try:
            result = subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True,
                check=True
            )

            # Intentar parsear como JSON
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"output": result.stdout.strip()}

        except subprocess.CalledProcessError as e:
            return {
                "error": e.stderr.strip() or e.stdout.strip(),
                "returncode": e.returncode
            }
        except FileNotFoundError:
            return {
                "error": "GitHub CLI (gh) no está instalado. Instala con: brew install gh",
                "install_instructions": "https://cli.github.com/manual/installation"
            }

    async def list_repositories(
            self,
            org: Optional[str] = None,
            limit: int = 30
    ) -> Dict:
        """Listar repositorios"""

        if org:
            args = ["repo", "list", org, "--limit", str(limit), "--json",
                    "name,description,url,isPrivate,updatedAt,primaryLanguage"]
        else:
            args = ["repo", "list", "--limit", str(limit), "--json",
                    "name,description,url,isPrivate,updatedAt,primaryLanguage"]

        result = await self._run_gh_command(args)

        if isinstance(result, list):
            return {
                "repositories": result,
                "count": len(result),
                "org": org or "user"
            }

        return result

    async def get_repository_info(self, owner: str, repo: str) -> Dict:
        """Obtener información del repositorio"""

        args = [
            "repo", "view", f"{owner}/{repo}",
            "--json", "name,description,url,isPrivate,createdAt,updatedAt,"
                      "pushedAt,defaultBranchRef,diskUsage,forkCount,stargazerCount,"
                      "watchers,primaryLanguage,languages,licenseInfo"
        ]

        result = await self._run_gh_command(args)

        if "error" not in result:
            result["full_name"] = f"{owner}/{repo}"
            result["clone_url"] = f"https://github.com/{owner}/{repo}.git"

        return result

    async def clone_repository(
            self,
            owner: str,
            repo: str,
            branch: str = "main"
    ) -> Dict:
        """Clonar repositorio al filesystem local"""

        repo_path = self.cache_dir / owner / repo

        # Si ya existe, hacer pull
        if repo_path.exists():
            try:
                result = subprocess.run(
                    ["git", "-C", str(repo_path), "pull"],
                    capture_output=True,
                    text=True,
                    check=True
                )

                return {
                    "status": "updated",
                    "path": str(repo_path.absolute()),
                    "message": "Repositorio actualizado",
                    "output": result.stdout.strip()
                }
            except subprocess.CalledProcessError as e:
                return {
                    "status": "error",
                    "error": f"Error al actualizar: {e.stderr}"
                }

        # Clonar nuevo
        repo_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            clone_url = f"https://github.com/{owner}/{repo}.git"
            args = ["clone", "--branch", branch, clone_url, str(repo_path)]

            result = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                check=True
            )

            # Contar archivos
            file_count = len(list(repo_path.rglob("*"))) if repo_path.exists() else 0

            return {
                "status": "cloned",
                "path": str(repo_path.absolute()),
                "branch": branch,
                "message": f"Repositorio clonado exitosamente",
                "file_count": file_count
            }

        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "error": f"Error al clonar: {e.stderr}"
            }

    async def get_file_content(
            self,
            owner: str,
            repo: str,
            path: str,
            branch: str = "main"
    ) -> Dict:
        """Obtener contenido de un archivo"""

        # Primero asegurar que el repo esté clonado
        clone_result = await self.clone_repository(owner, repo, branch)

        if clone_result.get("status") == "error":
            return clone_result

        repo_path = Path(clone_result["path"])
        file_path = repo_path / path

        if not file_path.exists():
            return {
                "error": f"Archivo no encontrado: {path}",
                "repository": f"{owner}/{repo}",
                "searched_path": str(file_path)
            }

        if not file_path.is_file():
            return {
                "error": f"La ruta es un directorio, no un archivo: {path}"
            }

        try:
            content = file_path.read_text(encoding='utf-8')

            return {
                "path": path,
                "repository": f"{owner}/{repo}",
                "branch": branch,
                "content": content,
                "size_bytes": len(content),
                "lines": len(content.splitlines())
            }

        except UnicodeDecodeError:
            return {
                "error": f"Archivo no es texto UTF-8: {path}",
                "note": "Puede ser un archivo binario"
            }
        except Exception as e:
            return {
                "error": f"Error al leer archivo: {str(e)}"
            }

    async def search_code(
            self,
            query: str,
            owner: Optional[str] = None,
            repo: Optional[str] = None
    ) -> Dict:
        """Buscar código en GitHub"""

        # Construir query completa
        full_query = query
        if owner and repo:
            full_query = f"{query} repo:{owner}/{repo}"
        elif owner:
            full_query = f"{query} user:{owner}"

        args = [
            "search", "code", full_query,
            "--limit", "20",
            "--json", "path,repository,textMatches"
        ]

        result = await self._run_gh_command(args)

        if isinstance(result, list):
            return {
                "query": query,
                "results": result,
                "count": len(result)
            }

        return result


# Singleton instance
github_tool = GitHubTool()
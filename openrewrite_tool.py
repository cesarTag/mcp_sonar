from typing import Dict, List, Optional
from pathlib import Path


class OpenRewriteTool:
    """Herramienta para análisis y migración de código con OpenRewrite"""

    def __init__(self):
        self.recipes_cache = None

    def get_tools_schema(self) -> List[Dict]:
        """Definir herramientas disponibles para el agente"""
        return [
            {
                "name": "openrewrite_list_recipes",
                "description": "Lista todas las recetas de migración disponibles en OpenRewrite, incluyendo migraciones de versiones de Java, Spring Boot, y frameworks.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filter": {
                            "type": "string",
                            "description": "Filtro opcional para buscar recetas específicas (ej: 'java', 'spring', 'migrate')"
                        }
                    }
                }
            },
            {
                "name": "openrewrite_analyze_project",
                "description": "Analiza un proyecto para determinar qué cambios son necesarios para una migración específica (ej: Java 8 a Java 21). No aplica cambios, solo analiza.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": "Ruta absoluta al proyecto a analizar"
                        },
                        "recipe": {
                            "type": "string",
                            "description": "Receta de OpenRewrite a aplicar (ej: 'org.openrewrite.java.migrate.UpgradeToJava21')"
                        }
                    },
                    "required": ["project_path", "recipe"]
                }
            },
            {
                "name": "openrewrite_generate_migration_plan",
                "description": "Genera un plan detallado de migración de código con estimaciones y cambios necesarios",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": "Ruta al proyecto"
                        },
                        "from_version": {
                            "type": "string",
                            "description": "Versión origen (ej: '8', '11', '17')"
                        },
                        "to_version": {
                            "type": "string",
                            "description": "Versión destino (ej: '11', '17', '21')"
                        }
                    },
                    "required": ["project_path", "from_version", "to_version"]
                }
            },
            {
                "name": "openrewrite_preview_changes",
                "description": "Muestra un preview de los cambios que se aplicarían sin modificar archivos (dry-run)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": "Ruta al proyecto"
                        },
                        "recipe": {
                            "type": "string",
                            "description": "Receta a previsualizar"
                        },
                        "max_files": {
                            "type": "integer",
                            "description": "Número máximo de archivos a mostrar en el preview",
                            "default": 10
                        }
                    },
                    "required": ["project_path", "recipe"]
                }
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """Ejecutar herramienta según el nombre"""
        handlers = {
            "openrewrite_list_recipes": self.list_recipes,
            "openrewrite_analyze_project": self.analyze_project,
            "openrewrite_generate_migration_plan": self.generate_migration_plan,
            "openrewrite_preview_changes": self.preview_changes
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Herramienta desconocida: {tool_name}"}

        try:
            return await handler(**arguments)
        except Exception as e:
            return {"error": str(e)}

    async def list_recipes(self, filter: Optional[str] = None) -> Dict:
        """Listar recetas disponibles"""
        # Recetas principales de migración Java
        recipes = {
            "java_migrations": [
                {
                    "name": "org.openrewrite.java.migrate.UpgradeToJava11",
                    "description": "Migrar de Java 8 a Java 11",
                    "from": "8",
                    "to": "11"
                },
                {
                    "name": "org.openrewrite.java.migrate.UpgradeToJava17",
                    "description": "Migrar de Java 11 a Java 17",
                    "from": "11",
                    "to": "17"
                },
                {
                    "name": "org.openrewrite.java.migrate.UpgradeToJava21",
                    "description": "Migrar de Java 17 a Java 21",
                    "from": "17",
                    "to": "21"
                },
                {
                    "name": "org.openrewrite.java.migrate.Java8toJava11",
                    "description": "Migración completa Java 8 a 11",
                    "from": "8",
                    "to": "11"
                }
            ],
            "deprecated_apis": [
                {
                    "name": "org.openrewrite.java.migrate.RemovedLegacyApis",
                    "description": "Reemplazar APIs legacy y deprecated"
                },
                {
                    "name": "org.openrewrite.java.migrate.javax.AddJaxbDependencies",
                    "description": "Agregar dependencias JAXB (removido en Java 11+)"
                }
            ],
            "spring_migrations": [
                {
                    "name": "org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_0",
                    "description": "Migrar a Spring Boot 3.0"
                },
                {
                    "name": "org.openrewrite.java.spring.boot2.UpgradeSpringBoot_2_7",
                    "description": "Migrar a Spring Boot 2.7"
                }
            ]
        }

        if filter:
            # Filtrar recetas
            filtered = {}
            for category, items in recipes.items():
                filtered_items = [
                    r for r in items
                    if filter.lower() in r["name"].lower() or
                       filter.lower() in r["description"].lower()
                ]
                if filtered_items:
                    filtered[category] = filtered_items
            return filtered

        return recipes

    async def generate_migration_plan(
            self,
            project_path: str,
            from_version: str,
            to_version: str
    ) -> Dict:
        """Generar plan de migración"""

        # Validar versiones
        valid_versions = ["8", "11", "17", "21"]
        if from_version not in valid_versions or to_version not in valid_versions:
            return {
                "error": f"Versiones válidas: {valid_versions}",
                "from": from_version,
                "to": to_version
            }

        if int(from_version) >= int(to_version):
            return {"error": "La versión origen debe ser menor que la destino"}

        # Determinar recetas necesarias
        migration_path = self._get_migration_path(from_version, to_version)

        # Analizar proyecto
        project_info = await self._scan_project(project_path)

        return {
            "project_path": project_path,
            "from_version": from_version,
            "to_version": to_version,
            "migration_steps": migration_path,
            "project_info": project_info,
            "estimated_changes": self._estimate_changes(from_version, to_version),
            "recommendations": self._get_recommendations(from_version, to_version),
            "next_steps": [
                "1. Revisar el plan de migración",
                "2. Hacer backup del código",
                "3. Usar 'openrewrite_preview_changes' para ver cambios específicos",
                "4. Ejecutar migración gradual por versión",
                "5. Ejecutar tests después de cada paso",
                "6. Validar con SonarQube"
            ]
        }

    def _get_migration_path(self, from_ver: str, to_ver: str) -> List[Dict]:
        """Determinar pasos de migración"""
        steps = []
        current = int(from_ver)
        target = int(to_ver)

        migration_map = {
            (8, 11): {
                "recipe": "org.openrewrite.java.migrate.Java8toJava11",
                "description": "Java 8 → 11",
                "key_changes": [
                    "Remover APIs deprecated de Java 8",
                    "Migrar javax.xml.bind (JAXB) si se usa",
                    "Actualizar javax.annotation",
                    "Migrar java.util.logging deprecations"
                ]
            },
            (11, 17): {
                "recipe": "org.openrewrite.java.migrate.UpgradeToJava17",
                "description": "Java 11 → 17",
                "key_changes": [
                    "Actualizar APIs deprecated en Java 11-16",
                    "Migrar a nuevos patrones de switch",
                    "Actualizar reflection APIs",
                    "Preparar para sealed classes"
                ]
            },
            (17, 21): {
                "recipe": "org.openrewrite.java.migrate.UpgradeToJava21",
                "description": "Java 17 → 21",
                "key_changes": [
                    "Adoptar pattern matching",
                    "Migrar a record patterns",
                    "Actualizar APIs deprecated",
                    "Preparar para virtual threads"
                ]
            }
        }

        # Construir path de migración
        while current < target:
            next_version = min(current + 6, target)  # Saltos de 6 (8->11, 11->17, 17->21)
            if next_version == 14:
                next_version = 17
            elif next_version == 20:
                next_version = 21

            step = migration_map.get((current, next_version))
            if step:
                steps.append(step)

            current = next_version

        return steps

    async def _scan_project(self, project_path: str) -> Dict:
        """Escanear proyecto para obtener información"""
        path = Path(project_path)

        if not path.exists():
            return {"error": "Ruta no existe", "path": project_path}

        # Detectar tipo de proyecto
        has_maven = (path / "pom.xml").exists()
        has_gradle = (path / "build.gradle").exists() or (path / "build.gradle.kts").exists()

        # Contar archivos Java
        java_files = list(path.rglob("*.java"))

        return {
            "path": str(path.absolute()),
            "build_tool": "maven" if has_maven else "gradle" if has_gradle else "unknown",
            "java_files_count": len(java_files),
            "has_tests": any("test" in str(f).lower() for f in java_files),
            "approximate_size": "small" if len(java_files) < 100 else "medium" if len(java_files) < 500 else "large"
        }

    def _estimate_changes(self, from_ver: str, to_ver: str) -> Dict:
        """Estimar número de cambios"""
        version_gap = int(to_ver) - int(from_ver)

        # Estimaciones basadas en salto de versión
        base_changes = {
            3: {"min": 20, "max": 50, "time": "1-2 horas"},
            6: {"min": 50, "max": 150, "time": "2-4 horas"},
            9: {"min": 100, "max": 250, "time": "4-8 horas"},
            13: {"min": 150, "max": 400, "time": "1-2 días"}
        }

        estimate = base_changes.get(version_gap, {"min": 200, "max": 500, "time": "2-3 días"})

        return {
            "estimated_files_changed": estimate,
            "estimated_time": estimate["time"],
            "complexity": "baja" if version_gap <= 3 else "media" if version_gap <= 9 else "alta"
        }

    def _get_recommendations(self, from_ver: str, to_ver: str) -> List[str]:
        """Recomendaciones para la migración"""
        recommendations = [
            "Asegurar que todos los tests pasen antes de iniciar",
            "Hacer commit/backup del código actual",
            "Migrar gradualmente (no saltar múltiples versiones de una vez)",
            "Ejecutar suite de tests después de cada paso",
            "Revisar y actualizar dependencias externas"
        ]

        if int(to_ver) >= 11:
            recommendations.append("Verificar uso de JAXB - removido del JDK en Java 11+")

        if int(to_ver) >= 17:
            recommendations.append("Considerar adoptar records para DTOs inmutables")
            recommendations.append("Revisar uso de reflection - cambios en Java 17")

        if int(to_ver) >= 21:
            recommendations.append("Evaluar usar virtual threads para código concurrente")
            recommendations.append("Adoptar pattern matching donde sea apropiado")

        return recommendations

    async def analyze_project(self, project_path: str, recipe: str) -> Dict:
        """Analizar proyecto con receta específica"""

        # Verificar si OpenRewrite está disponible
        if not await self._check_openrewrite_available(project_path):
            return {
                "status": "warning",
                "message": "OpenRewrite no configurado en el proyecto",
                "solution": "Para análisis real, agrega OpenRewrite al pom.xml o build.gradle",
                "simulated_analysis": await self._simulate_analysis(project_path, recipe)
            }

        # Aquí ejecutarías OpenRewrite real
        # Por ahora simulamos
        return await self._simulate_analysis(project_path, recipe)

    async def _check_openrewrite_available(self, project_path: str) -> bool:
        """Verificar si OpenRewrite está configurado"""
        path = Path(project_path)

        # Buscar en pom.xml
        pom = path / "pom.xml"
        if pom.exists():
            content = pom.read_text()
            return "openrewrite" in content.lower()

        # Buscar en build.gradle
        gradle = path / "build.gradle"
        if gradle.exists():
            content = gradle.read_text()
            return "openrewrite" in content.lower()

        return False

    async def _simulate_analysis(self, project_path: str, recipe: str) -> Dict:
        """Simular análisis (para demo sin OpenRewrite instalado)"""
        project_info = await self._scan_project(project_path)

        return {
            "recipe": recipe,
            "project": project_info,
            "simulated_findings": {
                "deprecated_apis": [
                    "java.util.Date constructors",
                    "Thread.stop() calls",
                    "Finalize() overrides"
                ],
                "files_to_modify": project_info.get("java_files_count", 0) // 3,
                "breaking_changes": [
                    "JAXB ya no incluido en JDK",
                    "Algunos packages javax.* renombrados"
                ],
                "automatic_fixes": "~70% de cambios pueden ser automáticos",
                "manual_review": "~30% requieren revisión manual"
            },
            "note": "Esta es una simulación. Para análisis real, configura OpenRewrite en el proyecto."
        }

    async def preview_changes(
            self,
            project_path: str,
            recipe: str,
            max_files: int = 10
    ) -> Dict:
        """Preview de cambios sin aplicar"""

        return {
            "recipe": recipe,
            "project_path": project_path,
            "preview_note": "Simulación de cambios (requiere OpenRewrite configurado para preview real)",
            "sample_changes": [
                {
                    "file": "src/main/java/com/example/DateUtil.java",
                    "changes": [
                        {
                            "line": 15,
                            "old": "Date date = new Date(2024, 1, 1);",
                            "new": "LocalDate date = LocalDate.of(2024, 1, 1);"
                        }
                    ]
                },
                {
                    "file": "src/main/java/com/example/ThreadManager.java",
                    "changes": [
                        {
                            "line": 42,
                            "old": "thread.stop();",
                            "new": "// Thread.stop() is deprecated - use interrupt() instead\nthread.interrupt();"
                        }
                    ]
                }
            ],
            "total_files_affected": max_files,
            "recommendation": "Revisa estos cambios antes de aplicar la receta completa"
        }


# Singleton instance
openrewrite_tool = OpenRewriteTool()
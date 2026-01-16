import requests
from typing import Dict, List, Optional
from pathlib import Path
import zlib


class PlantUMLTool:
    """Herramienta para generar diagramas UML con PlantUML"""

    def __init__(self, output_dir: str = "/tmp/plantuml-diagrams"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.server_url = "http://www.plantuml.com/plantuml"

    def _plantuml_encode(self, text: str) -> str:
        """Encoding específico de PlantUML"""
        # Alfabeto especial de PlantUML
        plantuml_alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_'

        # Comprimir con deflate
        compressed = zlib.compress(text.encode('utf-8'))[2:-4]

        # Convertir a encoding PlantUML
        result = []
        for i in range(0, len(compressed), 3):
            if i + 2 < len(compressed):
                b1, b2, b3 = compressed[i], compressed[i + 1], compressed[i + 2]
                result.append(plantuml_alphabet[(b1 >> 2) & 0x3F])
                result.append(plantuml_alphabet[((b1 & 0x3) << 4) | ((b2 >> 4) & 0xF)])
                result.append(plantuml_alphabet[((b2 & 0xF) << 2) | ((b3 >> 6) & 0x3)])
                result.append(plantuml_alphabet[b3 & 0x3F])
            elif i + 1 < len(compressed):
                b1, b2 = compressed[i], compressed[i + 1]
                result.append(plantuml_alphabet[(b1 >> 2) & 0x3F])
                result.append(plantuml_alphabet[((b1 & 0x3) << 4) | ((b2 >> 4) & 0xF)])
                result.append(plantuml_alphabet[(b2 & 0xF) << 2])
            else:
                b1 = compressed[i]
                result.append(plantuml_alphabet[(b1 >> 2) & 0x3F])
                result.append(plantuml_alphabet[(b1 & 0x3) << 4])

        return ''.join(result)

    def get_tools_schema(self) -> List[Dict]:
        """Definir herramientas disponibles"""
        return [
            {
                "name": "plantuml_create_class_diagram",
                "description": "Genera y renderiza un diagrama de clases UML mostrando clases Java, sus atributos, métodos y relaciones (herencia, composición, etc). Usa esta herramienta cuando el usuario pida visualizar la estructura de clases de un proyecto.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "classes": {
                            "type": "array",
                            "description": "Lista de clases con sus atributos y métodos",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "attributes": {"type": "array", "items": {"type": "string"}},
                                    "methods": {"type": "array", "items": {"type": "string"}}
                                }
                            }
                        },
                        "relationships": {
                            "type": "array",
                            "description": "Relaciones entre clases (inheritance, composition, aggregation, association)",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "type": {"type": "string",
                                             "enum": ["extends", "implements", "uses", "has", "aggregates"]}
                                }
                            }
                        },
                        "title": {
                            "type": "string",
                            "description": "Título del diagrama"
                        }
                    },
                    "required": ["classes"]
                }
            },
            {
                "name": "plantuml_create_sequence_diagram",
                "description": "Genera y renderiza un diagrama de secuencia UML mostrando el flujo de mensajes entre objetos en el tiempo. Usa esta herramienta para visualizar interacciones, flujos de trabajo, o procesos secuenciales.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "participants": {
                            "type": "array",
                            "description": "Lista de participantes/actores",
                            "items": {"type": "string"}
                        },
                        "interactions": {
                            "type": "array",
                            "description": "Lista de mensajes entre participantes",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "message": {"type": "string"},
                                    "type": {"type": "string", "enum": ["sync", "async", "return"]}
                                }
                            }
                        },
                        "title": {
                            "type": "string",
                            "description": "Título del diagrama"
                        }
                    },
                    "required": ["participants", "interactions"]
                }
            },
            {
                "name": "plantuml_create_state_diagram",
                "description": "Genera y renderiza un diagrama de estados UML mostrando los diferentes estados de un objeto y las transiciones entre ellos. Usa esta herramienta para visualizar máquinas de estado, ciclos de vida, o flujos de estado.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "states": {
                            "type": "array",
                            "description": "Lista de estados",
                            "items": {"type": "string"}
                        },
                        "transitions": {
                            "type": "array",
                            "description": "Transiciones entre estados",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "label": {"type": "string"}
                                }
                            }
                        },
                        "title": {
                            "type": "string",
                            "description": "Título del diagrama"
                        }
                    },
                    "required": ["states", "transitions"]
                }
            },
            {
                "name": "plantuml_create_component_diagram",
                "description": "Genera y renderiza un diagrama de componentes UML mostrando la arquitectura del sistema, sus componentes y dependencias. Usa esta herramienta para visualizar la estructura de alto nivel de un proyecto.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "components": {
                            "type": "array",
                            "description": "Lista de componentes del sistema",
                            "items": {"type": "string"}
                        },
                        "dependencies": {
                            "type": "array",
                            "description": "Dependencias entre componentes",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"}
                                }
                            }
                        },
                        "title": {
                            "type": "string",
                            "description": "Título del diagrama"
                        }
                    },
                    "required": ["components"]
                }
            },
            {
                "name": "plantuml_from_code",
                "description": "Genera y renderiza un diagrama desde código PlantUML completo proporcionado por el usuario. Usa esta herramienta cuando el usuario proporciona código PlantUML directo o para cualquier tipo de diagrama UML personalizado.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "plantuml_code": {
                            "type": "string",
                            "description": "Código PlantUML completo incluyendo @startuml y @enduml"
                        },
                        "diagram_name": {
                            "type": "string",
                            "description": "Nombre del archivo de salida (sin extensión)"
                        }
                    },
                    "required": ["plantuml_code", "diagram_name"]
                }
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """Ejecutar herramienta según el nombre"""
        handlers = {
            "plantuml_create_class_diagram": self.create_class_diagram,
            "plantuml_create_sequence_diagram": self.create_sequence_diagram,
            "plantuml_create_state_diagram": self.create_state_diagram,
            "plantuml_create_component_diagram": self.create_component_diagram,
            "plantuml_from_code": self.from_code
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Herramienta desconocida: {tool_name}"}

        try:
            return await handler(**arguments)
        except Exception as e:
            return {"error": str(e), "traceback": str(e.__class__.__name__)}

    def _generate_plantuml(self, code: str, filename: str) -> Dict:
        """Generar diagrama usando servidor PlantUML online"""
        try:
            # Guardar código PlantUML
            puml_path = self.output_dir / f"{filename}.puml"
            puml_path.write_text(code, encoding='utf-8')

            # Encoding específico de PlantUML
            encoded = self._plantuml_encode(code)

            # Generar URL del diagrama
            diagram_url = f"{self.server_url}/png/{encoded}"

            print(f"  → Generando diagrama: {diagram_url[:100]}...")

            # Descargar imagen
            response = requests.get(diagram_url, timeout=30)
            response.raise_for_status()

            # Guardar imagen
            png_path = self.output_dir / f"{filename}.png"
            png_path.write_bytes(response.content)

            print(f"  ✅ Diagrama guardado: {png_path}")

            return {
                "status": "success",
                "plantuml_code": code,
                "plantuml_file": str(puml_path.absolute()),
                "diagram_file": str(png_path.absolute()),
                "diagram_url": diagram_url,
                "message": f"Diagrama generado: {filename}.png"
            }

        except requests.RequestException as e:
            error_msg = f"Error al descargar diagrama: {str(e)}"
            print(f"  ❌ {error_msg}")

            # Intentar con servidor alternativo
            try:
                alt_url = f"https://kroki.io/plantuml/png/{encoded}"
                print(f"  → Intentando servidor alternativo: kroki.io")
                response = requests.get(alt_url, timeout=30)
                response.raise_for_status()

                png_path = self.output_dir / f"{filename}.png"
                png_path.write_bytes(response.content)

                print(f"  ✅ Diagrama guardado (servidor alternativo): {png_path}")

                return {
                    "status": "success",
                    "plantuml_code": code,
                    "plantuml_file": str(puml_path.absolute()),
                    "diagram_file": str(png_path.absolute()),
                    "diagram_url": alt_url,
                    "message": f"Diagrama generado con servidor alternativo: {filename}.png"
                }
            except Exception as alt_error:
                return {
                    "status": "error",
                    "error": error_msg,
                    "alternative_error": str(alt_error),
                    "plantuml_file": str(puml_path.absolute()),
                    "note": "Código PlantUML guardado. Puedes usar https://plantuml.com para visualizarlo."
                }
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def create_class_diagram(
            self,
            classes: List[Dict],
            relationships: Optional[List[Dict]] = None,
            title: str = "Class Diagram"
    ) -> Dict:
        """Crear diagrama de clases"""

        code = "@startuml\n"
        code += f"title {title}\n\n"

        # Agregar clases
        for cls in classes:
            code += f"class {cls['name']} {{\n"

            # Atributos
            if cls.get('attributes'):
                for attr in cls['attributes']:
                    code += f"  {attr}\n"

            # Métodos
            if cls.get('methods'):
                if cls.get('attributes'):
                    code += "  --\n"
                for method in cls['methods']:
                    code += f"  {method}\n"

            code += "}\n\n"

        # Agregar relaciones
        if relationships:
            for rel in relationships:
                rel_type = rel.get('type', 'uses')

                if rel_type == 'extends':
                    code += f"{rel['from']} --|> {rel['to']}\n"
                elif rel_type == 'implements':
                    code += f"{rel['from']} ..|> {rel['to']}\n"
                elif rel_type == 'has':
                    code += f"{rel['from']} *-- {rel['to']}\n"
                elif rel_type == 'aggregates':
                    code += f"{rel['from']} o-- {rel['to']}\n"
                else:  # uses
                    code += f"{rel['from']} ..> {rel['to']}\n"

        code += "@enduml"

        filename = title.lower().replace(' ', '_')
        return self._generate_plantuml(code, filename)

    async def create_sequence_diagram(
            self,
            participants: List[str],
            interactions: List[Dict],
            title: str = "Sequence Diagram"
    ) -> Dict:
        """Crear diagrama de secuencia"""

        code = "@startuml\n"
        code += f"title {title}\n\n"

        # Declarar participantes
        for participant in participants:
            code += f"participant {participant}\n"

        code += "\n"

        # Agregar interacciones
        for interaction in interactions:
            msg_type = interaction.get('type', 'sync')

            if msg_type == 'async':
                arrow = "->>"
            elif msg_type == 'return':
                arrow = "-->"
            else:  # sync
                arrow = "->"

            code += f"{interaction['from']} {arrow} {interaction['to']}: {interaction['message']}\n"

        code += "@enduml"

        filename = title.lower().replace(' ', '_')
        return self._generate_plantuml(code, filename)

    async def create_state_diagram(
            self,
            states: List[str],
            transitions: List[Dict],
            title: str = "State Diagram"
    ) -> Dict:
        """Crear diagrama de estados"""

        code = "@startuml\n"
        code += f"title {title}\n\n"

        code += "[*] --> " + states[0] + "\n\n"

        # Agregar transiciones
        for trans in transitions:
            label = trans.get('label', '')
            if label:
                code += f"{trans['from']} --> {trans['to']} : {label}\n"
            else:
                code += f"{trans['from']} --> {trans['to']}\n"

        # Si el último estado es final
        if states:
            code += f"\n{states[-1]} --> [*]\n"

        code += "@enduml"

        filename = title.lower().replace(' ', '_')
        return self._generate_plantuml(code, filename)

    async def create_component_diagram(
            self,
            components: List[str],
            dependencies: Optional[List[Dict]] = None,
            title: str = "Component Diagram"
    ) -> Dict:
        """Crear diagrama de componentes"""

        code = "@startuml\n"
        code += f"title {title}\n\n"

        # Agregar componentes
        for component in components:
            code += f"component [{component}]\n"

        code += "\n"

        # Agregar dependencias
        if dependencies:
            for dep in dependencies:
                code += f"[{dep['from']}] --> [{dep['to']}]\n"

        code += "@enduml"

        filename = title.lower().replace(' ', '_')
        return self._generate_plantuml(code, filename)

    async def from_code(
            self,
            plantuml_code: str,
            diagram_name: str
    ) -> Dict:
        """Generar diagrama desde código PlantUML directo"""

        # Asegurar que tiene @startuml y @enduml
        if not plantuml_code.strip().startswith('@startuml'):
            plantuml_code = f"@startuml\n{plantuml_code}\n@enduml"

        if not plantuml_code.strip().endswith('@enduml'):
            plantuml_code = f"{plantuml_code}\n@enduml"

        return self._generate_plantuml(plantuml_code, diagram_name)


# Singleton instance
plantuml_tool = PlantUMLTool()
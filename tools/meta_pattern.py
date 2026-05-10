from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient
from memory.meta_pattern import MetaPatternManager


class MetaPatternTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._mgr = MetaPatternManager(neo4j)

    def schema(self):
        return ToolSchema(
            name="meta_pattern",
            description="Manage L4 Meta-Patterns: create cross-domain strategies or extract patterns from Skills. For searching patterns, use memory_search(mode='rag', strategy='global').",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "extract"]},
                    "pattern_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "abstract_steps": {"type": "array", "items": {"type": "string"}},
                    "source_skills": {"type": "array", "items": {"type": "string"}},
                    "category": {"type": "string"},
                },
                "required": ["action"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        action = call.arguments["action"]
        try:
            if action == "create":
                r = await self._mgr.create(
                    pattern_id=call.arguments["pattern_id"],
                    name=call.arguments.get("name", call.arguments["pattern_id"]),
                    description=call.arguments.get("description", ""),
                    abstract_steps=call.arguments.get("abstract_steps"),
                    source_skills=call.arguments.get("source_skills"),
                )
                return ToolResult(call_id=call.id, name="meta_pattern", success=True,
                                  output=f"Pattern {r['pattern_id']} created")

            elif action == "extract":
                patterns = await self._mgr.extract_from_skills(
                    category=call.arguments.get("category", ""),
                )
                lines = [f"Extracted {len(patterns)} candidate patterns:"]
                for p in patterns:
                    lines.append(f"- {p['key']}: {p['skill_count']} skills {p['names']}")
                return ToolResult(call_id=call.id, name="meta_pattern", success=True,
                                  output="\n".join(lines))

            return ToolResult(call_id=call.id, name="meta_pattern", success=False,
                              output="", error=f"Unknown action: {action}")
        except Exception as e:
            return ToolResult(call_id=call.id, name="meta_pattern", success=False,
                              output="", error=str(e))

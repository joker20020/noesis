from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient
from skill_system.registry import SkillRegistry


class SkillManageTool(BaseTool):
    """Main agent Skill operations: register and link only.
    Evolution, optimization, compilation -> subconscious via start_long_term_update."""

    def __init__(self, neo4j: Neo4jClient):
        self._reg = SkillRegistry(neo4j)

    def schema(self):
        return ToolSchema(
            name="skill_manage",
            description="Register new Skills or link relationships. For evolving, optimizing, or compiling, use start_long_term_update to queue subconscious processing.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["register", "link"]},
                    "skill_id": {"type": "string", "description": "Skill ID like 'category/name'"},
                    "name": {"type": "string", "description": "Display name (register)"},
                    "category": {"type": "string", "description": "Category like 'web_automation' (register)"},
                    "description": {"type": "string", "description": "What this skill does (register)"},
                    "content": {"type": "string", "description": "Full SKILL.md content. If empty, a template is generated (register)"},
                    "stage": {"type": "string", "description": "Initial stage: NL, SOP, or CODE (register, default NL)"},
                    "relation": {"type": "string", "enum": ["DEPENDS_ON", "CONFLICTS_WITH", "ALTERNATIVE_TO"], "description": "Relationship type (link)"},
                    "target_skill_id": {"type": "string", "description": "Target skill for relationship (link)"},
                },
                "required": ["action", "skill_id"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        action = call.arguments["action"]
        sid = call.arguments["skill_id"]
        try:
            if action == "register":
                content = call.arguments.get("content", "")
                await self._reg.register(
                    name=call.arguments.get("name", sid.split("/")[-1]),
                    category=call.arguments.get("category", "general"),
                    description=call.arguments.get("description", ""),
                    stage=call.arguments.get("stage", "NL"),
                    create_files=True,
                    skill_md_content=content or None,
                )
                return ToolResult(call_id=call.id, name="skill_manage", success=True,
                                  output=f"Skill {sid} registered. "
                                  f"To evolve or compile it later, use start_long_term_update.")

            elif action == "link":
                rel = call.arguments["relation"]
                target = call.arguments["target_skill_id"]
                await self._reg._neo4j.run(
                    f"MATCH (a:Skill {{skill_id: $sid}}), (b:Skill {{skill_id: $target}}) MERGE (a)-[:{rel}]->(b)",
                    {"sid": sid, "target": target},
                )
                return ToolResult(call_id=call.id, name="skill_manage", success=True,
                                  output=f"Linked {sid} -[{rel}]-> {target}")

            return ToolResult(call_id=call.id, name="skill_manage", success=False,
                              output="", error=f"Unknown action: {action}. Use register or link here; use start_long_term_update for evolution.")
        except Exception as e:
            return ToolResult(call_id=call.id, name="skill_manage", success=False,
                              output="", error=str(e))

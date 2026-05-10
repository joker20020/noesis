from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient


class StartLongTermUpdateTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    def schema(self):
        return ToolSchema(
            name="start_long_term_update",
            description="Queue a subconscious evolution request. reason=reusable_pattern evolves Skills, subgoal_completed and fault_recovery extract L2 entities.",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Current session ID (from system prompt)"},
                    "reason": {"type": "string", "enum": ["subgoal_completed", "fault_recovery", "reusable_pattern"],
                               "description": "reusable_pattern=evolve Skill, subgoal_completed=extract entities, fault_recovery=record error pattern"},
                    "summary": {"type": "string", "description": "What was learned or discovered"},
                    "skill_id": {"type": "string", "description": "Optional: target Skill ID like 'category/name'. If provided, this skill is evolved. Otherwise found via session."},
                },
                "required": ["session_id", "reason", "summary"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        await self._neo4j.run(
            """CREATE (d:DistillationRequest {
                session_id: $sid, reason: $reason, summary: $summary,
                skill_id: $skid, status: 'pending', created_at: datetime()
            })""",
            {"sid": call.arguments["session_id"], "reason": call.arguments["reason"],
             "summary": call.arguments["summary"],
             "skid": call.arguments.get("skill_id", "")},
        )
        return ToolResult(call_id=call.id, name="start_long_term_update", success=True,
                          output="Distillation request queued for subconscious processing")

from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient


class UpdateWorkingCheckpointTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    def schema(self):
        return ToolSchema(
            name="update_working_checkpoint",
            description="Update working memory key_info block. Find the current Session ID in the system prompt's Working Memory section.",
            parameters={
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "findings": {"type": "string"},
                    "next_steps": {"type": "string"},
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        sid = call.arguments["session_id"]
        goal = call.arguments.get("goal", "")
        findings = call.arguments.get("findings", "")
        next_steps = call.arguments.get("next_steps", "")
        key_info = f"Goal: {goal}\nFindings: {findings}\nNext: {next_steps}"
        await self._neo4j.run(
            "MERGE (s:Session {session_id: $sid}) SET s.key_info = $key_info",
            {"sid": sid, "key_info": key_info},
        )
        return ToolResult(call_id=call.id, name="update_working_checkpoint", success=True, output="Checkpoint updated")

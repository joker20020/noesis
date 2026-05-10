import uuid
from pathlib import Path
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient


class SubagentTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient, dispatcher, llm_client, config,
                 workspace_dir: str = "./workspace"):
        self._neo4j = neo4j
        self._dispatcher = dispatcher
        self._llm = llm_client
        self._config = config
        self._workspace = Path(workspace_dir)

    def schema(self):
        return ToolSchema(
            name="subagent",
            description="Spawn an independent sub-agent to handle a subtask. The subagent has its own conscious loop and isolated workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "skill_dirs": {"type": "array", "items": {"type": "string"}},
                    "max_rounds": {"type": "integer"},
                },
                "required": ["task"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        task = call.arguments["task"]
        max_rounds = call.arguments.get("max_rounds", self._config.max_subagent_rounds)
        sub_session_id = f"sub_{uuid.uuid4().hex[:12]}"
        sub_workspace = self._workspace / sub_session_id
        sub_workspace.mkdir(parents=True, exist_ok=True)

        await self._neo4j.run(
            """CREATE (s:Session {
                session_id: $sid, type: 'subagent', parent_session_id: $parent,
                status: 'running', created_at: datetime()
            })""",
            {"sid": sub_session_id, "parent": call.id},
        )

        from agent.conscious import ConsciousLoop
        sub_loop = ConsciousLoop(
            llm_client=self._llm,
            dispatcher=self._dispatcher,
            neo4j=self._neo4j,
            config=self._config,
            session_id=sub_session_id,
            workspace_dir=str(sub_workspace),
        )
        result_text = await sub_loop.run(task, max_rounds=max_rounds)

        await self._neo4j.run(
            "MATCH (s:Session {session_id: $sid}) SET s.status = 'completed'",
            {"sid": sub_session_id},
        )
        return ToolResult(call_id=call.id, name="subagent", success=True, output=result_text)

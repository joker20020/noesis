"""Execute exploration tasks in ephemeral sessions (not persisted to DB)."""
import uuid
from pathlib import Path
from memory.neo4j_client import Neo4jClient


class ExplorationExecutor:
    def __init__(self, neo4j: Neo4jClient, llm_client, dispatcher, config):
        self._neo4j = neo4j
        self._llm = llm_client
        self._dispatcher = dispatcher
        self._config = config

    async def execute(self, task: dict, max_rounds: int = 20) -> dict:
        session_id = f"explore_{uuid.uuid4().hex[:8]}"
        workspace = Path(self._config.workspace_dir) / "exploration" / session_id
        workspace.mkdir(parents=True, exist_ok=True)

        from agent.conscious import ConsciousLoop
        loop = ConsciousLoop(
            llm_client=self._llm, dispatcher=self._dispatcher,
            neo4j=self._neo4j, config=self._config,
            session_id=session_id, workspace_dir=str(workspace),
        )

        # Build a structured exploration prompt that includes goal, method, and success criteria
        goal = task.get("goal", "Explore and improve agent capabilities")
        method = task.get("method", "Use available tools to investigate and record findings")
        success_criteria = task.get("success_criteria", "Register at least one useful discovery")
        task_prompt = task.get("prompt", "")

        exploration_input = (
            f"## Exploration Task\n\n"
            f"**Goal**: {goal}\n\n"
            f"**Method**: {method}\n\n"
            f"**Success Criteria**: {success_criteria}\n\n"
            f"{task_prompt}\n\n"
            f"---\n\n"
            f"Begin exploration now. State your initial hypothesis and first experiment."
        )

        try:
            result = await loop.run(exploration_input, max_rounds=max_rounds)
            status = "completed"
        except Exception as e:
            result = f"Exploration failed: {e}"
            status = "failed"

        return {
            "session_id": session_id,
            "task_type": task.get("type"),
            "category": task.get("category", ""),
            "goal": goal,
            "method": method,
            "success_criteria": success_criteria,
            "status": status,
            "result": result[:2000],
        }

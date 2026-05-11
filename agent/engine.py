import asyncio
from agent.config import Config
from llm.openai_client import OpenAIClient
from llm.deepseek_client import DeepSeekClient
from memory.neo4j_client import Neo4jClient
from tools.dispatcher import ToolDispatcher
from tools.file_ops import FileReadTool, FileWriteTool, FilePatchTool
from tools.code_run import CodeRunTool
from tools.web_interact import WebScanTool, WebExecuteJsTool
from tools.web_scraper import WebScraperTool
from tools.memory_search import MemorySearchTool
from tools.checkpoint import UpdateWorkingCheckpointTool
from tools.long_term_update import StartLongTermUpdateTool
from tools.skill_manage import SkillManageTool
from tools.entity_manage import EntityManageTool
from tools.meta_pattern import MetaPatternTool
from tools.ask_user import AskUserTool
from tools.subagent import SubagentTool
from agent.conscious import ConsciousLoop
from agent.subconscious import SubconsciousLoop

FIXED_SESSION = "noesis"


class AgentEngine:
    def __init__(self, config: Config):
        self.config = config
        self.neo4j = Neo4jClient(config.neo4j)
        if config.llm.provider == "openai":
            self.llm = OpenAIClient(config.llm)
        elif config.llm.provider == "deepseek":
            self.llm = DeepSeekClient(config.llm)
        else:
            raise ValueError(f"Unknown LLM provider: {config.llm.provider}")
        self.dispatcher = ToolDispatcher()
        self._web_scan_tool = WebScanTool()
        self._register_tools()
        # Single conscious loop per engine — persists context across messages
        self._loop = ConsciousLoop(
            llm_client=self.llm, dispatcher=self.dispatcher,
            neo4j=self.neo4j, config=config, session_id=FIXED_SESSION,
        )
        self._subconscious = SubconsciousLoop(self.neo4j, config, self.llm, self.dispatcher)
        self._sub_task = None

    def _register_tools(self):
        self.dispatcher.register(FileReadTool())
        self.dispatcher.register(FileWriteTool())
        self.dispatcher.register(FilePatchTool())
        self.dispatcher.register(CodeRunTool(self.config.workspace_dir))
        self.dispatcher.register(self._web_scan_tool)
        self.dispatcher.register(WebExecuteJsTool(self._web_scan_tool))
        self.dispatcher.register(WebScraperTool())
        self.dispatcher.register(MemorySearchTool(self.neo4j))
        self.dispatcher.register(UpdateWorkingCheckpointTool(self.neo4j))
        self.dispatcher.register(StartLongTermUpdateTool(self.neo4j))
        self.dispatcher.register(SkillManageTool(self.neo4j))
        self.dispatcher.register(EntityManageTool(self.neo4j))
        self.dispatcher.register(MetaPatternTool(self.neo4j))
        self.dispatcher.register(AskUserTool())
        self.dispatcher.register(SubagentTool(
            self.neo4j, self.dispatcher, self.llm, self.config,
        ))

    async def init(self):
        await self.neo4j.init_schema()
        self._sub_task = asyncio.create_task(self._subconscious.start())

    async def run(self, user_input: str,
                  on_event=None) -> str:
        self._subconscious.touch()
        return await self._loop.run(user_input, on_event=on_event, max_rounds=30)

    def abort(self):
        """Send interrupt signal to stop current agent response."""
        self._loop.abort()

    def clear_history(self):
        """Clear in-memory history for a fresh conversation."""
        self._loop._history.clear()
        self._loop._turn_count = 0
        self._loop._last_20_summaries.clear()
        self._loop._history_summary = ""

    async def restart_session(self):
        """Clear DB records + in-memory history. Full restart."""
        self.clear_history()
        await self.neo4j.run(
            """MATCH (s:Session {session_id: $sid})
               OPTIONAL MATCH (s)-[:HAS_STEP]->(first:ExecutionStep)
               OPTIONAL MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               DETACH DELETE step, first, s""",
            {"sid": self._loop.session_id})

    async def close(self):
        self._subconscious.stop()
        if self._sub_task:
            self._sub_task.cancel()
            try:
                await self._sub_task
            except asyncio.CancelledError:
                pass
        try:
            await self._web_scan_tool.close()
        except Exception:
            pass
        await self.neo4j.close()

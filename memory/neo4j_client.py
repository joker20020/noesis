from neo4j import AsyncGraphDatabase, AsyncDriver
from agent.config import Neo4jConfig


class Neo4jClient:
    def __init__(self, config: Neo4jConfig):
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            config.uri,
            auth=(config.user, config.password),
        )

    async def close(self):
        await self._driver.close()

    async def init_schema(self):
        queries = [
            # Uniqueness constraints
            "CREATE CONSTRAINT skill_id_unique     IF NOT EXISTS FOR (s:Skill)           REQUIRE s.skill_id IS UNIQUE",
            "CREATE CONSTRAINT agent_id_unique     IF NOT EXISTS FOR (a:Agent)           REQUIRE a.agent_id IS UNIQUE",
            "CREATE CONSTRAINT session_id_unique   IF NOT EXISTS FOR (s:Session)         REQUIRE s.session_id IS UNIQUE",
            "CREATE CONSTRAINT step_id_unique      IF NOT EXISTS FOR (s:ExecutionStep)   REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT entity_id_unique    IF NOT EXISTS FOR (e:Entity)          REQUIRE e.entity_id IS UNIQUE",
            "CREATE CONSTRAINT sop_id_unique       IF NOT EXISTS FOR (s:SOP)             REQUIRE s.sop_id IS UNIQUE",
            "CREATE CONSTRAINT pattern_id_unique   IF NOT EXISTS FOR (p:MetaPattern)     REQUIRE p.pattern_id IS UNIQUE",
            "CREATE CONSTRAINT user_id_unique      IF NOT EXISTS FOR (u:User)            REQUIRE u.user_id IS UNIQUE",
            "CREATE CONSTRAINT category_name_unique IF NOT EXISTS FOR (c:SkillCategory)   REQUIRE c.name IS UNIQUE",
            # Query indexes
            "CREATE INDEX skill_category_idx   IF NOT EXISTS FOR (s:Skill)     ON (s.category)",
            "CREATE INDEX skill_stage_idx      IF NOT EXISTS FOR (s:Skill)     ON (s.stage)",
            "CREATE INDEX skill_activation_idx IF NOT EXISTS FOR (s:Skill)     ON (s.activation)",
            "CREATE INDEX entity_type_idx       IF NOT EXISTS FOR (e:Entity)    ON (e.entity_type)",
            "CREATE INDEX entity_source_idx     IF NOT EXISTS FOR (e:Entity)    ON (e.source)",
            "CREATE INDEX entity_confidence_idx IF NOT EXISTS FOR (e:Entity)    ON (e.confidence)",
            "CREATE INDEX session_status_idx   IF NOT EXISTS FOR (s:Session)   ON (s.status)",
            "CREATE INDEX step_role_idx        IF NOT EXISTS FOR (s:ExecutionStep) ON (s.role)",
            "CREATE INDEX step_index_idx       IF NOT EXISTS FOR (s:ExecutionStep) ON (s.step_index)",
            "CREATE INDEX sop_skill_idx        IF NOT EXISTS FOR (s:SOP)       ON (s.skill_id)",
            "CREATE INDEX distillation_status_idx IF NOT EXISTS FOR (d:DistillationRequest) ON (d.status)",
            # Full-text indexes
            "CREATE FULLTEXT INDEX skill_search  IF NOT EXISTS FOR (s:Skill)  ON EACH [s.name, s.description]",
            "CREATE FULLTEXT INDEX entity_search IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.content]",
        ]
        async with self._driver.session() as session:
            for q in queries:
                await session.run(q)

    async def run(self, query: str, params: dict | None = None) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(query, params or {})
            return await result.data()

    async def get_driver(self) -> AsyncDriver:
        return self._driver

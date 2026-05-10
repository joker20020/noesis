from pathlib import Path
from memory.neo4j_client import Neo4jClient
from skill_system.template import generate_skill_md


class SkillRegistry:
    def __init__(self, neo4j: Neo4jClient, skills_dir: str = "./skills"):
        self._neo4j = neo4j
        self._skills_dir = Path(skills_dir)

    def _skill_dir(self, category: str, name: str) -> Path:
        return self._skills_dir / category / name

    async def register(
        self, name: str, category: str, description: str = "",
        stage: str = "NL", create_files: bool = True,
        skill_md_content: str | None = None,
    ) -> dict:
        skill_id = name if "/" in name else f"{category}/{name}"
        name_only = skill_id.split("/")[-1]
        dir_path = str(self._skill_dir(category, name_only))

        await self._neo4j.run(
            """MERGE (s:Skill {skill_id: $sid})
               ON CREATE SET s.name = $name, s.description = $desc,
                  s.category = $cat, s.stage = $stage, s.version = 1,
                  s.dir = $dir, s.usage_count = 0, s.success_rate = 0.0,
                  s.activation = 1.0, s.confidence = 0.0,
                  s.created_at = datetime()
               ON MATCH SET s.description = $desc""",
            {"sid": skill_id, "name": name_only, "desc": description,
             "cat": category, "stage": stage, "dir": dir_path},
        )

        await self._neo4j.run(
            """MERGE (c:SkillCategory {name: $cat})
               ON CREATE SET c.created_at = datetime()
               WITH c
               MATCH (s:Skill {skill_id: $sid})
               MERGE (s)-[:BELONGS_TO]->(c)""",
            {"cat": category, "sid": skill_id},
        )
        await self._neo4j.run(
            """MATCH (c:SkillCategory {name: $cat})
               OPTIONAL MATCH (s:Skill)-[:BELONGS_TO]->(c)
               WITH c, count(s) AS cnt
               SET c.skill_count = cnt""",
            {"cat": category},
        )

        if create_files:
            d = self._skill_dir(category, name_only)
            d.mkdir(parents=True, exist_ok=True)
            if skill_md_content:
                # Merge: template YAML header + custom body content
                template = generate_skill_md(name_only, description, category, stage)
                header = self._extract_yaml_header(template)
                body = self._extract_body(skill_md_content)
                md = header + "\n" + body if body else template
            else:
                md = generate_skill_md(name_only, description, category, stage)
            (d / "SKILL.md").write_text(md, encoding="utf-8")
            (d / "scripts").mkdir(exist_ok=True)
            (d / "references").mkdir(exist_ok=True)
            (d / "checkpoints").mkdir(exist_ok=True)

        return {"skill_id": skill_id, "dir": dir_path}

    @staticmethod
    def _extract_yaml_header(md: str) -> str:
        """Extract YAML frontmatter (between --- markers)."""
        lines = md.split("\n")
        if lines and lines[0].strip() == "---":
            end = 1
            while end < len(lines) and lines[end].strip() != "---":
                end += 1
            if end < len(lines):
                return "\n".join(lines[:end + 1])
        return ""

    @staticmethod
    def _extract_body(md: str) -> str:
        """Extract content after YAML frontmatter."""
        lines = md.split("\n")
        if lines and lines[0].strip() == "---":
            end = 1
            while end < len(lines) and lines[end].strip() != "---":
                end += 1
            return "\n".join(lines[end + 1:]).strip()
        return md  # No frontmatter found, return as-is

    async def get(self, skill_id: str) -> dict | None:
        records = await self._neo4j.run(
            "MATCH (s:Skill {skill_id: $sid}) RETURN s", {"sid": skill_id},
        )
        return records[0]["s"] if records else None

    async def list_by_category(self, category: str) -> list[dict]:
        records = await self._neo4j.run(
            """MATCH (s:Skill)-[:BELONGS_TO]->(c:SkillCategory {name: $cat})
               RETURN s ORDER BY s.usage_count DESC""",
            {"cat": category},
        )
        return [r["s"] for r in records]

    async def list_categories(self) -> list[dict]:
        records = await self._neo4j.run(
            "MATCH (c:SkillCategory) RETURN c ORDER BY c.skill_count DESC"
        )
        return [r["c"] for r in records]

    async def update_stage(self, skill_id: str, new_stage: str, content: str = ""):
        """Evolve skill stage and update SKILL.md content (SOP text, etc.)."""
        await self._neo4j.run(
            """MATCH (s:Skill {skill_id: $sid})
               SET s.stage = $stage, s.version = coalesce(s.version, 1) + 1,
                   s.confidence = CASE WHEN $stage = 'CODE' THEN 0.9 ELSE s.confidence END,
                   s.updated_at = datetime()""",
            {"sid": skill_id, "stage": new_stage},
        )
        # Rewrite SKILL.md with evolved content
        if content:
            skill = await self.get(skill_id)
            if skill:
                d = Path(skill["dir"])
                d.mkdir(parents=True, exist_ok=True)
                (d / "SKILL.md").write_text(content, encoding="utf-8")

    async def update_skill_md(self, skill_id: str, content: str):
        """Directly update SKILL.md content (for SOP text, etc.)."""
        skill = await self.get(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")
        d = Path(skill["dir"])
        (d / "SKILL.md").write_text(content, encoding="utf-8")

    async def record_usage(self, skill_id: str, success: bool):
        await self._neo4j.run(
            """MATCH (s:Skill {skill_id: $sid})
               SET s.usage_count = coalesce(s.usage_count, 0) + 1,
                   s.activation = coalesce(s.activation, 0) * 1.1,
                   s.updated_at = datetime()""",
            {"sid": skill_id},
        )

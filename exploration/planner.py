"""Curriculum planner for autonomous skill exploration.

Generates data-driven exploration tasks based on:
- Pain points: recent failed tool calls and error patterns
- Coverage gaps: under-represented categories and unmet user needs
- Skill health: high-potential skills that need deepening
"""
from memory.neo4j_client import Neo4jClient
from skill_system.scorer import SkillScorer

ALL_KNOWN_CATEGORIES = {
    "web_automation", "data_processing", "code_generation",
    "file_management", "system_ops", "communication",
    "security", "monitoring", "deployment",
}


class ExplorationPlanner:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j
        self._scorer = SkillScorer(neo4j)

    async def plan(self, max_tasks: int = 3) -> list[dict]:
        """Generate exploration tasks driven by actual usage data."""
        scores = await self._scorer.score_all()
        cats = await self._neo4j.run(
            "MATCH (c:SkillCategory) RETURN c.name AS name, c.skill_count AS cnt ORDER BY c.skill_count ASC"
        )
        existing_cats = {r["name"] for r in cats}
        tasks = []

        # --- Task source 1: Pain Fix (highest priority) ---
        pain_points = await self._query_pain_points()
        for pain in pain_points[:2]:
            tasks.append(self._build_pain_fix_task(pain))

        # --- Task source 2: Gap Fill (medium priority) ---
        gaps = await self._query_coverage_gaps(existing_cats)
        for gap in gaps[:2]:
            tasks.append(self._build_gap_fill_task(gap))

        # --- Task source 3: Deepen (lower priority, only if no pain/gap) ---
        deepen_candidates = await self._query_deepen_candidates(scores)
        for cand in deepen_candidates[:2]:
            tasks.append(self._build_deepen_task(cand))

        # Deduplicate by goal hash and return top N
        seen = set()
        deduped = []
        for t in tasks:
            key = t["goal"][:60]
            if key not in seen:
                seen.add(key)
                deduped.append(t)
        return deduped[:max_tasks]

    # ------------------------------------------------------------------ #
    # Data queries
    # ------------------------------------------------------------------ #

    async def _query_pain_points(self) -> list[dict]:
        """Find recent tool failures and error clusters."""
        # Query 1: tools with high failure rate in recent sessions
        recent_fails = await self._neo4j.run(
            """MATCH (s:Session)-[:HAS_STEP]->(step:ExecutionStep)
               WHERE step.role = 'system'
                 AND step.timestamp > datetime() - duration('P7D')
                 AND (step.content CONTAINS 'error' OR step.content CONTAINS 'Error'
                      OR step.content CONTAINS 'failed' OR step.content CONTAINS 'exception')
               WITH step.name AS tool_name, count(*) AS fail_count
               WHERE fail_count >= 2
               RETURN tool_name, fail_count ORDER BY fail_count DESC LIMIT 5"""
        )
        # Query 2: sessions that ended in failure
        failed_sessions = await self._neo4j.run(
            """MATCH (s:Session {status: 'failed'})
               WHERE s.created_at > datetime() - duration('P7D')
               RETURN s.session_id AS sid, s.key_info AS info
               ORDER BY s.created_at DESC LIMIT 5"""
        )
        pains = []
        for r in recent_fails:
            pains.append({
                "type": "tool_failure",
                "tool_name": r["tool_name"],
                "fail_count": r["fail_count"],
                "source": "recent_execution",
            })
        for r in failed_sessions:
            info = r.get("info", "") or ""
            # Extract a short theme from key_info
            theme = info.split(".")[0] if info else "unknown failure"
            pains.append({
                "type": "session_failure",
                "theme": theme[:80],
                "session_id": r["sid"],
                "source": "failed_session",
            })
        return pains

    async def _query_coverage_gaps(self, existing_cats: set) -> list[dict]:
        """Find missing categories and under-represented domains."""
        gaps = []
        # Missing categories
        missing = ALL_KNOWN_CATEGORIES - existing_cats
        for cat in missing:
            gaps.append({
                "type": "missing_category",
                "category": cat,
                "reason": f"No skills registered in '{cat}'",
            })
        # Categories with very few skills (< 2)
        few_skills = await self._neo4j.run(
            """MATCH (c:SkillCategory)
               OPTIONAL MATCH (s:Skill)-[:BELONGS_TO]->(c)
               WITH c, count(s) AS cnt
               WHERE cnt < 2
               RETURN c.name AS cat, cnt ORDER BY cnt ASC"""
        )
        for r in few_skills:
            if r["cat"] not in missing:
                gaps.append({
                    "type": "under_represented",
                    "category": r["cat"],
                    "skill_count": r["cnt"],
                    "reason": f"Only {r['cnt']} skill(s) in '{r['cat']}'",
                })
        return gaps

    async def _query_deepen_candidates(self, scores: list[dict]) -> list[dict]:
        """Find skills that score well but have low usage or are still NL stage."""
        candidates = []
        for s in scores[:8]:
            # High score but low usage = theoretical potential not realized
            # Or NL stage = needs to be hardened into SOP/CODE
            dim = s.get("dimensions", {})
            if s["score"] > 5.0 and (dim.get("D", 0) < 3.0 or dim.get("I", 0) > 5.0):
                candidates.append(s)
        return candidates

    # ------------------------------------------------------------------ #
    # Task builders
    # ------------------------------------------------------------------ #

    def _build_pain_fix_task(self, pain: dict) -> dict:
        if pain["type"] == "tool_failure":
            tool = pain["tool_name"]
            return {
                "type": "pain_fix",
                "goal": f"Diagnose and mitigate repeated failures of tool '{tool}' ({pain['fail_count']} recent failures)",
                "method": (
                    f"1. Search memory for recent error patterns involving '{tool}'.\n"
                    f"2. Identify root causes (wrong parameters, missing preconditions, edge cases).\n"
                    f"3. Design and test a robust usage pattern or wrapper strategy.\n"
                    f"4. Document the recovery pattern as a reusable skill."
                ),
                "success_criteria": (
                    "A reproducible test case for the failure is identified, "
                    "a working recovery pattern is verified, and a Skill or SOP is registered."
                ),
                "prompt": self._pain_fix_prompt(pain),
            }
        else:
            theme = pain.get("theme", "unknown")
            return {
                "type": "pain_fix",
                "goal": f"Investigate and prevent failures like: {theme}",
                "method": (
                    "1. Load the failed session's history and identify where it diverged from success.\n"
                    "2. Find the earliest recoverable failure point.\n"
                    "3. Design a checkpoint or fallback strategy.\n"
                    "4. Register the lesson as an error-recovery skill."
                ),
                "success_criteria": (
                    "Root cause of the failure is documented, a recovery strategy is tested, "
                    "and a reusable pattern is saved to long-term memory."
                ),
                "prompt": self._pain_fix_prompt(pain),
            }

    def _build_gap_fill_task(self, gap: dict) -> dict:
        cat = gap["category"]
        return {
            "type": "gap_fill",
            "goal": f"Establish foundational coverage for category '{cat}'",
            "method": (
                f"1. Research what tasks are typical in '{cat}' using available tools (web search, file ops).\n"
                f"2. Attempt 2-3 simple but realistic examples.\n"
                f"3. Identify common parameters, preconditions, and pitfalls.\n"
                f"4. Synthesize a reusable workflow and register it as a Skill."
            ),
            "success_criteria": (
                f"At least one verified workflow for '{cat}' is discovered, tested, "
                f"and registered with concrete tool usage examples."
            ),
            "prompt": self._gap_fill_prompt(gap),
        }

    def _build_deepen_task(self, cand: dict) -> dict:
        sid = cand["skill_id"]
        name = cand["name"]
        dims = cand.get("dimensions", {})
        return {
            "type": "deepen",
            "goal": f"Harden skill '{name}' from theory to practice (score={cand['score']}, usage={dims.get('D', 0)})",
            "method": (
                f"1. Load the existing Skill '{sid}' and understand its current SOP.\n"
                f"2. Identify 2-3 edge cases or variations not covered by the SOP.\n"
                f"3. Execute each variation using the correct tools.\n"
                f"4. Update the SOP with verified edge-case handling."
            ),
            "success_criteria": (
                "At least one new edge case is discovered, a working solution is verified, "
                "and the Skill's SOP is updated with the new knowledge."
            ),
            "prompt": self._deepen_prompt(cand),
        }

    # ------------------------------------------------------------------ #
    # Prompts
    # ------------------------------------------------------------------ #

    def _pain_fix_prompt(self, pain: dict) -> str:
        if pain["type"] == "tool_failure":
            return (
                f"## Mission: Fix Repeated Tool Failure\n\n"
                f"Tool '{pain['tool_name']}' has failed {pain['fail_count']} times recently.\n\n"
                f"### Exploration Protocol\n"
                f"1. **Investigate**: Use memory_search to find recent error logs and failed invocations of '{pain['tool_name']}'.\n"
                f"2. **Classify**: Determine if failures are due to wrong parameters, missing context, timeout, or unexpected output format.\n"
                f"3. **Reproduce**: Attempt to trigger the same failure in a controlled way.\n"
                f"4. **Solve**: Find a robust workaround (pre-validation, retry logic, parameter template).\n"
                f"5. **Preserve**: Register the recovery pattern as a Skill with category='fault_recovery'.\n\n"
                f"### Success Criteria\n"
                f"- Root cause documented\n"
                f"- Reproduction test case created\n"
                f"- Verified recovery pattern saved\n"
                f"- Skill registered with concrete tool examples"
            )
        else:
            return (
                f"## Mission: Investigate Session Failure\n\n"
                f"Failed session theme: {pain.get('theme', 'unknown')}\n\n"
                f"### Exploration Protocol\n"
                f"1. **Load context**: Search memory for session '{pain.get('session_id', '')}' and related failures.\n"
                f"2. **Trace**: Identify the first divergence point where the session went from progress to failure.\n"
                f"3. **Recover**: Design a checkpoint or fallback strategy that could have rescued the session.\n"
                f"4. **Generalize**: Turn the recovery strategy into a reusable pattern.\n\n"
                f"### Success Criteria\n"
                f"- Failure root cause identified\n"
                f"- Recoverable point marked\n"
                f"- Fallback strategy tested\n"
                f"- Pattern saved to long-term memory"
            )

    def _gap_fill_prompt(self, gap: dict) -> str:
        cat = gap["category"]
        reason = gap.get("reason", "")
        return (
            f"## Mission: Fill Coverage Gap — {cat}\n\n"
            f"Context: {reason}\n\n"
            f"### Exploration Protocol\n"
            f"1. **Research**: Use web_scraper or file ops to understand what '{cat}' tasks look like in practice.\n"
            f"2. **Prototype**: Attempt 2-3 simple but realistic tasks using available tools.\n"
            f"3. **Analyze**: For each attempt, record: tools used, parameters, failures, workarounds.\n"
            f"4. **Synthesize**: Combine successful attempts into a reusable workflow.\n\n"
            f"### Success Criteria\n"
            f"- At least 2 realistic tasks attempted\n"
            f"- Common parameters and pitfalls documented\n"
            f"- One verified workflow registered as Skill\n"
            f"- SKILL.md includes concrete tool calls with example parameters"
        )

    def _deepen_prompt(self, cand: dict) -> str:
        sid = cand["skill_id"]
        name = cand["name"]
        dims = cand.get("dimensions", {})
        return (
            f"## Mission: Deepen Skill — {name}\n\n"
            f"Skill ID: {sid}\n"
            f"Current score: {cand['score']} (B={dims.get('B', 0)}, D={dims.get('D', 0)}, U={dims.get('U', 0)}, I={dims.get('I', 0)})\n\n"
            f"### Exploration Protocol\n"
            f"1. **Load**: Read the current SKILL.md and SOP for '{sid}'.\n"
            f"2. **Question**: Identify what the SOP does NOT cover (edge cases, failure modes, input variations).\n"
            f"3. **Test**: Execute 2-3 variations that stress the uncovered areas.\n"
            f"4. **Update**: Enhance the SOP with verified edge-case handling.\n\n"
            f"### Success Criteria\n"
            f"- At least one new edge case discovered and solved\n"
            f"- SOP updated with verified steps\n"
            f"- If solution is generalizable, register as new Skill or update existing"
        )

    async def get_gap_analysis(self) -> dict:
        cats = await self._neo4j.run(
            "MATCH (c:SkillCategory) RETURN c.name AS name, c.skill_count AS cnt"
        )
        existing = {r["name"]: r["cnt"] for r in cats}
        pains = await self._query_pain_points()
        gaps = await self._query_coverage_gaps(set(existing.keys()))
        return {
            "existing": existing,
            "missing": list(ALL_KNOWN_CATEGORIES - set(existing.keys())),
            "pain_points": pains,
            "coverage_gaps": gaps,
        }

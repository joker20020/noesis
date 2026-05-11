from memory.neo4j_client import Neo4jClient


class MemoryLifecycle:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def decay_all(self, days_threshold: int = 7, rate: float = 0.95, confidence_rate: float = 0.99):
        """Decay activation and confidence for unused nodes. Confidence decays much slower."""
        for label in ["Skill", "Entity", "MetaPattern"]:
            await self._neo4j.run(
                f"""MATCH (n:{label})
                   WHERE (coalesce(n.updated_at, n.created_at) < datetime() - duration({{days: $days}}))
                   SET n.activation = coalesce(n.activation, 1.0) * $rate,
                       n.confidence = coalesce(n.confidence, 0.5) * $crate,
                       n.updated_at = datetime()""",
                {"days": days_threshold, "rate": rate, "crate": confidence_rate},
            )

    async def consolidate_skill(self, skill_id: str, boost: float = 0.2):
        """Boost activation for a used Skill."""
        await self._neo4j.run(
            """MATCH (s:Skill {skill_id: $sid})
               SET s.activation = coalesce(s.activation, 0) + $boost,
                   s.updated_at = datetime()""",
            {"sid": skill_id, "boost": boost},
        )

    async def consolidate_entity(self, entity_id: str, boost: float = 0.2):
        """Boost activation for a used Entity."""
        await self._neo4j.run(
            """MATCH (e:Entity {entity_id: $eid})
               SET e.activation = coalesce(e.activation, 0) + $boost,
                   e.updated_at = datetime()""",
            {"eid": entity_id, "boost": boost},
        )

    async def consolidate_pattern(self, pattern_id: str, boost: float = 0.2):
        """Boost usage for a MetaPattern."""
        await self._neo4j.run(
            """MATCH (p:MetaPattern {pattern_id: $pid})
               SET p.usage_count = coalesce(p.usage_count, 0) + 1""",
            {"pid": pattern_id},
        )

    async def forget_stale(self, activation_threshold: float = 0.1):
        """Deprecate stale Skills, delete abandoned Entities, remove unused MetaPatterns."""
        await self._neo4j.run(
            """MATCH (s:Skill)
               WHERE coalesce(s.activation, 0) < $threshold
               SET s.stage = 'DEPRECATED'""",
            {"threshold": activation_threshold},
        )
        await self._neo4j.run(
            """MATCH (e:Entity)
               WHERE coalesce(e.activation, 0) < $threshold
               DETACH DELETE e""",
            {"threshold": activation_threshold},
        )
        await self._neo4j.run(
            """MATCH (p:MetaPattern)
               WHERE coalesce(p.usage_count, 0) = 0
                 AND (coalesce(p.created_at, datetime()) < datetime() - duration({days: 30}))
               DETACH DELETE p""",
        )

    async def evict_compressed_steps(self):
        """Evict compressed ExecutionSteps. If a completed DistillationRequest
        exists, only evict steps created before its creation time (knowledge was
        extracted). If no DistillationRequest exists at all, evict all compressed
        steps immediately. Rewires Session, renumbers turns, deletes nodes."""
        # 1. Find cutoff from latest completed DistillationRequest
        records = await self._neo4j.run(
            """MATCH (d:DistillationRequest {status: 'completed'})
               RETURN d.created_at AS created_at
               ORDER BY d.processed_at DESC LIMIT 1""")
        has_distillation = bool(records and records[0].get("created_at"))
        cutoff = records[0]["created_at"] if has_distillation else None

        # Also check if ANY DistillationRequest exists at all
        if not has_distillation:
            any_dr = await self._neo4j.run(
                "MATCH (d:DistillationRequest) RETURN count(d) AS c")
            any_exists = any_dr and any_dr[0]["c"] > 0
            if any_exists:
                # DRs exist but none completed yet — wait for completion
                return

        # 2. Find sessions with compressed steps
        if has_distillation:
            sessions = await self._neo4j.run(
                """MATCH (s:Session)-[:HAS_STEP]->(:ExecutionStep)-[:NEXT*0..]->(step:ExecutionStep)
                   WHERE step.status = 'compressed' AND step.timestamp <= $cutoff
                   RETURN DISTINCT s.session_id AS sid""",
                {"cutoff": cutoff})
        else:
            sessions = await self._neo4j.run(
                """MATCH (s:Session)-[:HAS_STEP]->(:ExecutionStep)-[:NEXT*0..]->(step:ExecutionStep)
                   WHERE step.status = 'compressed'
                   RETURN DISTINCT s.session_id AS sid""")

        for row in sessions:
            sid = row["sid"]
            # 3. Find first non-compressed step (new head)
            new_head = await self._neo4j.run(
                """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
                   MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
                   WHERE coalesce(step.status, '') <> 'compressed'
                   RETURN step.id AS id, step.step_index AS idx
                   ORDER BY step.step_index ASC LIMIT 1""",
                {"sid": sid})

            # 4. Delete compressed steps
            if has_distillation:
                await self._neo4j.run(
                    """MATCH (s:Session {session_id: $sid})
                       OPTIONAL MATCH (s)-[:HAS_STEP]->(first:ExecutionStep)
                       OPTIONAL MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
                       WHERE step.status = 'compressed' AND step.timestamp <= $cutoff
                       DETACH DELETE step""",
                    {"sid": sid, "cutoff": cutoff})
            else:
                await self._neo4j.run(
                    """MATCH (s:Session {session_id: $sid})
                       OPTIONAL MATCH (s)-[:HAS_STEP]->(first:ExecutionStep)
                       OPTIONAL MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
                       WHERE step.status = 'compressed'
                       DETACH DELETE step""",
                    {"sid": sid})

            if new_head:
                hid = new_head[0]["id"]
                # 5. Rewire session to new head
                await self._neo4j.run(
                    """MATCH (s:Session {session_id: $sid})
                       OPTIONAL MATCH (s)-[r:HAS_STEP]->()
                       DELETE r
                       WITH s
                       MATCH (step:ExecutionStep {id: $hid})
                       CREATE (s)-[:HAS_STEP]->(step)""",
                    {"sid": sid, "hid": hid})

                # 6. Renumber turns for remaining steps
                remaining = await self._neo4j.run(
                    """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
                       MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
                       RETURN min(step.turn) AS min_turn, max(step.turn) AS max_turn""",
                    {"sid": sid})
                if remaining and remaining[0].get("min_turn"):
                    min_t = remaining[0]["min_turn"]
                    max_t = remaining[0]["max_turn"]
                    offset = min_t - 1
                    if offset > 0:
                        await self._neo4j.run(
                            """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
                               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
                               SET step.turn = step.turn - $offset""",
                            {"sid": sid, "offset": offset})
                    # 7. Update session turn_count
                    await self._neo4j.run(
                        """MATCH (s:Session {session_id: $sid})
                           SET s.turn_count = $tc""",
                        {"sid": sid, "tc": max_t - offset})
            else:
                # No non-compressed steps remain — clear the session HAS_STEP
                await self._neo4j.run(
                    """MATCH (s:Session {session_id: $sid})
                       OPTIONAL MATCH (s)-[r:HAS_STEP]->()
                       DELETE r
                       SET s.turn_count = 0""",
                    {"sid": sid})

    async def get_stats(self) -> dict:
        skill = await self._neo4j.run(
            "MATCH (s:Skill) WHERE s.stage <> 'DEPRECATED' RETURN count(s) AS cnt"
        )
        entity = await self._neo4j.run(
            "MATCH (e:Entity) RETURN count(e) AS cnt"
        )
        meta = await self._neo4j.run(
            "MATCH (p:MetaPattern) RETURN count(p) AS cnt"
        )
        return {
            "skills": skill[0]["cnt"] if skill else 0,
            "entities": entity[0]["cnt"] if entity else 0,
            "patterns": meta[0]["cnt"] if meta else 0,
        }

"""4-dimensional skill scoring for curriculum planning."""
from memory.neo4j_client import Neo4jClient


class SkillScorer:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j
        self.weights = {"w_b": 0.3, "w_d": 0.2, "w_u": 0.3, "w_i": 0.2}

    async def score_all(self) -> list[dict]:
        cat_stats = await self._neo4j.run(
            "MATCH (s:Skill) WHERE s.stage <> 'DEPRECATED' RETURN s.category AS cat, count(*) AS cnt"
        )
        cats = {r["cat"]: r["cnt"] for r in cat_stats}
        avg = sum(cats.values()) / max(len(cats), 1)
        max_cnt = max(cats.values()) if cats else 1
        max_usage = await self._get_max_usage()

        skills = await self._neo4j.run(
            "MATCH (s:Skill) WHERE s.stage <> 'DEPRECATED' RETURN s ORDER BY coalesce(s.activation, 0) DESC"
        )
        results = []
        for r in skills:
            s = r["s"]
            cat = s.get("category", "")
            usage = s.get("usage_count", 0)
            stage = s.get("stage", "NL")

            B = 10 * max(0, 1 - cats.get(cat, 0) / (avg + 1))
            D = 10 * usage / (max_usage + 1)
            U = s.get("activation", 1.0) * 5
            I = 10.0 if stage == "NL" else 2.0 if stage == "SOP" else 0

            score = (self.weights["w_b"] * B + self.weights["w_d"] * D +
                     self.weights["w_u"] * U + self.weights["w_i"] * I)
            results.append({
                "skill_id": s["skill_id"], "name": s.get("name", ""),
                "score": round(score, 2),
                "dimensions": {"B": round(B, 1), "D": round(D, 1), "U": round(U, 1), "I": round(I, 1)},
            })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    async def _get_max_usage(self) -> int:
        r = await self._neo4j.run("MATCH (s:Skill) RETURN max(coalesce(s.usage_count, 0)) AS m")
        return r[0]["m"] if r and r[0]["m"] else 1

    async def adapt_weights(self, predicted: dict, actual_usage: int):
        S = predicted["score"]
        dims = predicted["dimensions"]
        dominant = max(dims, key=dims.get)[0].lower()
        if S > 8.0 and actual_usage < 3:
            self.weights[f"w_{dominant}"] *= 0.9
        elif S < 5.0 and actual_usage > 5:
            self.weights[f"w_{dominant}"] *= 1.1
        total = sum(self.weights.values())
        for k in self.weights:
            self.weights[k] /= total

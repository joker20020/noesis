from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient
from memory.entities import EntityManager


class EntityManageTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._mgr = EntityManager(neo4j)

    def schema(self):
        return ToolSchema(
            name="entity_manage",
            description="Full L2 entity CRUD: create, update, delete, link, update_confidence, search. For graph-based RAG search, use memory_search(mode='rag').",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "update", "delete", "link", "update_confidence", "search"]},
                    "entity_id": {"type": "string"},
                    "entity_type": {"type": "string", "description": "Person, Service, API, Config, Error, Fact, etc."},
                    "name": {"type": "string"},
                    "content": {"type": "string", "description": "Human-readable description (update)"},
                    "properties": {"type": "object", "description": "Structured properties dict"},
                    "relation": {"type": "string", "description": "Dynamic relationship type (link)"},
                    "target_entity_id": {"type": "string", "description": "Target entity (link)"},
                    "delta": {"type": "number", "description": "Confidence adjustment: +0.1 to boost, -0.1 to reduce. Triggers belief revision propagation."},
                    "keyword": {"type": "string", "description": "Keyword to search entity names and content (search action)"},
                },
                "required": ["action"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        action = call.arguments["action"]
        try:
            if action == "create":
                r = await self._mgr.create(
                    entity_id=call.arguments["entity_id"],
                    entity_type=call.arguments.get("entity_type", "Fact"),
                    name=call.arguments.get("name", call.arguments["entity_id"]),
                    content=call.arguments.get("content", ""),
                    properties=call.arguments.get("properties"),
                )
                return ToolResult(call_id=call.id, name="entity_manage", success=True,
                                  output=f"Entity {r['entity_id']} created/updated. Search via memory_search(mode='rag').")

            elif action == "update":
                await self._mgr.update(
                    entity_id=call.arguments["entity_id"],
                    name=call.arguments.get("name"),
                    content=call.arguments.get("content"),
                    entity_type=call.arguments.get("entity_type"),
                    properties=call.arguments.get("properties"),
                )
                return ToolResult(call_id=call.id, name="entity_manage", success=True,
                                  output=f"Entity {call.arguments['entity_id']} updated.")

            elif action == "delete":
                await self._mgr.delete(call.arguments["entity_id"])
                return ToolResult(call_id=call.id, name="entity_manage", success=True,
                                  output=f"Entity {call.arguments['entity_id']} deleted.")

            elif action == "link":
                await self._mgr.link(
                    call.arguments["entity_id"], call.arguments["relation"],
                    call.arguments["target_entity_id"],
                )
                return ToolResult(call_id=call.id, name="entity_manage", success=True,
                                  output=f"Linked {call.arguments['entity_id']} -[{call.arguments['relation']}]-> {call.arguments['target_entity_id']}")

            elif action == "update_confidence":
                delta = call.arguments.get("delta", 0.1)
                await self._mgr.update_confidence(call.arguments["entity_id"], delta)
                # Trigger belief revision propagation
                from memory.belief import BeliefReviser
                reviser = BeliefReviser(self._mgr._neo4j)
                entity = await self._mgr.get(call.arguments["entity_id"])
                if entity:
                    await reviser.revise(call.arguments["entity_id"], entity.get("confidence", 0.5))
                return ToolResult(call_id=call.id, name="entity_manage", success=True,
                                  output=f"Confidence adjusted by {delta:+.1f} for {call.arguments['entity_id']}. Dependents propagated.")

            elif action == "search":
                results = await self._mgr.search(
                    keyword=call.arguments.get("keyword", ""),
                    entity_type=call.arguments.get("entity_type", ""),
                )
                if not results:
                    return ToolResult(call_id=call.id, name="entity_manage", success=True,
                                      output="No entities found.")
                # Boost confidence for found entities (they were useful)
                from memory.belief import BeliefReviser
                reviser = BeliefReviser(self._mgr._neo4j)
                for e in results:
                    await reviser.on_successful_use(e["entity_id"])
                lines = [f"Found {len(results)} entities:"]
                for e in results:
                    props = e.get("properties", {})
                    props_str = f" props={props}" if props else ""
                    lines.append(f"- [{e.get('entity_type', '?')}] {e.get('name', e['entity_id'])} "
                                 f"(conf:{e.get('confidence', '?')}){props_str}")
                    lines.append(f"  {e.get('content', '')[:120]}")
                return ToolResult(call_id=call.id, name="entity_manage", success=True, output="\n".join(lines))

            return ToolResult(call_id=call.id, name="entity_manage", success=False,
                              output="", error=f"Unknown action: {action}")
        except Exception as e:
            return ToolResult(call_id=call.id, name="entity_manage", success=False,
                              output="", error=str(e))

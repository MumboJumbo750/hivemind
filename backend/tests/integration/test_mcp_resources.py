"""Integration tests for MCP resource capability (TASK-IDE-007)."""
from __future__ import annotations

import json
import re
import uuid

import pytest
from sqlalchemy import delete

from app.db import AsyncSessionLocal
from app.mcp.prompts import get_prompt, list_prompts
from app.mcp.resources import list_resources, read_resource
from app.mcp.server import server
from app.models.conductor import ConductorDispatch
from app.models.context_boundary import ContextBoundary, TaskSkill
from app.models.epic import Epic
from app.models.federation import Node
from app.models.guard import Guard, TaskGuard
from app.models.prompt_history import PromptHistory
from app.models.skill import Skill
from app.models.task import Task
from app.models.user import User
from app.models.wiki import WikiArticle
from app.services.prompt_generator import PromptGenerator


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")


async def _seed_resource_data() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    phase = 50000 + int(uuid.uuid4().int % 4000)
    prev_epic_key = f"EPIC-PHASE-{phase - 1}"
    epic_key = f"EPIC-PHASE-{phase}"
    task_key = f"TASK-IDE-007-{suffix.upper()}"
    health_task_key = f"TASK-HEALTH-{suffix.upper()}"
    skill_title = f"MCP Skill {suffix}"
    wiki_slug = f"mcp-resource-{suffix}"

    async with AsyncSessionLocal() as db:
        user = User(username=f"mcp-res-{suffix}", role="admin")
        node = Node(node_name=f"mcp-node-{suffix}", node_url=f"http://mcp-{suffix}.local:8000")
        db.add_all([user, node])
        await db.flush()

        prev_epic = Epic(
            epic_key=prev_epic_key,
            title=f"Previous Epic {suffix}",
            state="done",
            origin_node_id=node.id,
        )
        epic = Epic(
            epic_key=epic_key,
            title=f"Main Epic {suffix}",
            state="in_progress",
            origin_node_id=node.id,
        )
        db.add_all([prev_epic, epic])
        await db.flush()

        task = Task(
            task_key=task_key,
            epic_id=epic.id,
            title="Implement MCP resources",
            description="Task resource test payload",
            state="in_progress",
            definition_of_done={"criteria": ["Resource capability active", "Read/list works"]},
            pinned_skills=[skill_title],
        )
        health_task = Task(
            task_key=health_task_key,
            epic_id=epic.id,
            title="Repo Health Report",
            state="done",
            result=f"# Health report for {suffix}\n\nAll checks green.",
        )
        db.add_all([task, health_task])
        await db.flush()

        skill = Skill(
            title=skill_title,
            content=f"## Worker skill content {suffix}\n\nUse MCP resources for context.",
            lifecycle="active",
            origin_node_id=node.id,
        )
        wiki = WikiArticle(
            title=f"MCP Resource Wiki {suffix}",
            slug=wiki_slug,
            content=f"# MCP Resource Wiki {suffix}\n\nContext article content.",
            author_id=user.id,
        )
        guard = Guard(
            title=f"Guard {suffix}",
            type="executable",
            command="make test",
            lifecycle="active",
            created_by=user.id,
        )
        db.add_all([skill, wiki, guard])
        await db.flush()

        db.add(TaskSkill(task_id=task.id, skill_id=skill.id))
        db.add(TaskGuard(task_id=task.id, guard_id=guard.id, status="passed", result="ok"))
        db.add(
            ContextBoundary(
                task_id=task.id,
                allowed_skills=[skill.id],
                max_token_budget=6000,
                set_by=user.id,
            )
        )
        await db.commit()

        return {
            "user_id": str(user.id),
            "node_id": str(node.id),
            "prev_epic_id": str(prev_epic.id),
            "prev_epic_key": prev_epic_key,
            "epic_id": str(epic.id),
            "epic_key": epic_key,
            "task_id": str(task.id),
            "task_key": task_key,
            "health_task_id": str(health_task.id),
            "health_task_key": health_task_key,
            "skill_id": str(skill.id),
            "skill_title": skill_title,
            "wiki_id": str(wiki.id),
            "wiki_slug": wiki_slug,
            "guard_id": str(guard.id),
        }


async def _cleanup_resource_data(data: dict[str, str]) -> None:
    task_id = uuid.UUID(data["task_id"])
    health_task_id = uuid.UUID(data["health_task_id"])

    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(ConductorDispatch).where(
                ConductorDispatch.trigger_id.in_([data["task_key"], data["health_task_key"]])
            )
        )
        await db.execute(delete(PromptHistory).where(PromptHistory.task_id.in_([task_id, health_task_id])))
        await db.execute(delete(TaskGuard).where(TaskGuard.task_id.in_([task_id, health_task_id])))
        await db.execute(delete(ContextBoundary).where(ContextBoundary.task_id == task_id))
        await db.execute(delete(TaskSkill).where(TaskSkill.task_id == task_id))
        await db.execute(delete(Guard).where(Guard.id == uuid.UUID(data["guard_id"])))
        await db.execute(delete(WikiArticle).where(WikiArticle.id == uuid.UUID(data["wiki_id"])))
        await db.execute(delete(Skill).where(Skill.id == uuid.UUID(data["skill_id"])))
        await db.execute(delete(Task).where(Task.id.in_([task_id, health_task_id])))
        await db.execute(delete(Epic).where(Epic.id.in_([uuid.UUID(data["epic_id"]), uuid.UUID(data["prev_epic_id"])])))
        await db.execute(delete(Node).where(Node.id == uuid.UUID(data["node_id"])))
        await db.execute(delete(User).where(User.id == uuid.UUID(data["user_id"])))
        await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_mcp_resource_listing_exposes_required_types() -> None:
    data = await _seed_resource_data()
    try:
        init_options = server.create_initialization_options()
        assert init_options.capabilities.resources is not None

        resources = await list_resources()
        by_uri = {str(resource.uri): resource for resource in resources}

        task_uri = f"hivemind://task/{data['task_key']}"
        epic_uri = f"hivemind://epic/{data['epic_id']}"
        wiki_uri = f"hivemind://wiki/{data['wiki_slug']}"
        skill_uri = f"hivemind://skill/{_slugify(data['skill_title'])}"
        context_boundary_uri = f"hivemind://context-boundary/{data['task_key']}"

        assert task_uri in by_uri
        assert epic_uri in by_uri
        assert wiki_uri in by_uri
        assert skill_uri in by_uri
        assert context_boundary_uri in by_uri
        assert "hivemind://prompt/worker" in by_uri
        assert "hivemind://health-report" in by_uri
        assert by_uri[task_uri].name.startswith("Open Task:")
    finally:
        await _cleanup_resource_data(data)


@pytest.mark.asyncio(loop_scope="session")
async def test_mcp_resource_read_returns_structured_payloads() -> None:
    data = await _seed_resource_data()
    try:
        task_payload = json.loads(await read_resource(f"hivemind://task/{data['task_key']}"))
        assert task_payload["task_key"] == data["task_key"]
        assert task_payload["guards"][0]["status"] == "passed"
        assert task_payload["linked_skills"][0]["title"] == data["skill_title"]
        assert task_payload["context_boundary"]["max_token_budget"] == 6000

        epic_payload = json.loads(await read_resource(f"hivemind://epic/{data['epic_id']}"))
        dep_keys = {dep["epic_key"] for dep in epic_payload["dependencies"]}
        assert data["prev_epic_key"] in dep_keys

        wiki_text = await read_resource(f"hivemind://wiki/{data['wiki_slug']}")
        assert "MCP Resource Wiki" in wiki_text

        skill_text = await read_resource(f"hivemind://skill/{_slugify(data['skill_title'])}")
        assert "Worker skill content" in skill_text

        health_text = await read_resource("hivemind://health-report")
        assert data["health_task_key"] in health_text

        prompt_result = await get_prompt("hivemind.worker", {"task_key": data["task_key"]})
        embedded_messages = [
            message for message in prompt_result.messages if getattr(message.content, "type", "") == "resource"
        ]
        embedded_uris = {str(message.content.resource.uri) for message in embedded_messages}
        assert f"hivemind://task/{data['task_key']}" in embedded_uris
        assert f"hivemind://skill/{_slugify(data['skill_title'])}" in embedded_uris
    finally:
        await _cleanup_resource_data(data)


@pytest.mark.asyncio(loop_scope="session")
async def test_prompt_templates_include_skills_dod_guards_and_context_boundary() -> None:
    data = await _seed_resource_data()
    try:
        async with AsyncSessionLocal() as db:
            generator = PromptGenerator(db)
            worker_prompt = await generator.generate("worker", task_id=data["task_key"])
            review_prompt = await generator.generate("review", task_id=data["task_key"])
            await db.commit()

        assert "### Skills" in worker_prompt
        assert "### Definition of Done" in worker_prompt
        assert "### Guards (Phase 5 Enforcement aktiv)" in worker_prompt
        assert "### Context Boundary" in worker_prompt
        assert data["skill_title"] in worker_prompt
        assert f"hivemind://context-boundary/{data['task_key']}" in worker_prompt

        assert "### Skills" in review_prompt
        assert "### Definition of Done — Checkliste" in review_prompt
        assert "### Guards — Status mit Provenance" in review_prompt
        assert "### Context Boundary" in review_prompt
        assert data["skill_title"] in review_prompt
        assert f"hivemind://context-boundary/{data['task_key']}" in review_prompt
    finally:
        await _cleanup_resource_data(data)


@pytest.mark.asyncio(loop_scope="session")
async def test_prompt_list_registers_all_agent_role_templates() -> None:
    prompts = await list_prompts()
    names = {prompt.name for prompt in prompts}
    assert "hivemind.worker" in names
    assert "hivemind.kartograph" in names
    assert "hivemind.reviewer" in names
    assert "hivemind.gaertner" in names
    assert "hivemind.stratege" in names
    assert "hivemind.architekt" in names
    assert "hivemind.next" in names


@pytest.mark.asyncio(loop_scope="session")
async def test_hivemind_next_uses_open_ide_dispatch() -> None:
    data = await _seed_resource_data()
    try:
        async with AsyncSessionLocal() as db:
            dispatch = ConductorDispatch(
                trigger_type="task_state",
                trigger_id=data["task_key"],
                trigger_detail="state:scoped→in_progress",
                agent_role="worker",
                prompt_type="worker_implement",
                execution_mode="ide",
                status="dispatched",
            )
            db.add(dispatch)
            await db.commit()

        result = await get_prompt("hivemind.next", {})
        assert "[WORKER]" in result.description
        text_messages = [m for m in result.messages if getattr(m.content, "type", "") == "text"]
        assert text_messages
        assert data["task_key"] in text_messages[0].content.text
    finally:
        await _cleanup_resource_data(data)

"""GitHub Projects V2 Sync — Phase 8 (TASK-8-013).

Bidirectional sync: Hivemind ↔ GitHub Projects V2

Direction Hivemind→GitHub: Task state changes update GitHub Board via sync_outbox (direction='outbound', system='github')
Direction GitHub→Hivemind: Webhook events (projects_v2_item.*) land as [UNROUTED] in Triage

State mapping:
  incoming        → Backlog
  scoped/ready    → Todo
  in_progress     → In Progress
  in_review       → In Review
  done            → Done
  cancelled/other → stays as-is

IMPORTANT: GitHub Board changes NEVER auto-change Hivemind state (Review-Gate protection).
Board changes → Triage [UNROUTED] only.

API: GitHub Projects V2 = exclusively GraphQL (POST /graphql)
"""
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Hivemind state → GitHub Projects V2 status
HIVEMIND_TO_GITHUB_STATUS: dict[str, str] = {
    "incoming": "Backlog",
    "scoped": "Todo",
    "ready": "Todo",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "done": "Done",
    "cancelled": "Done",
    "blocked": "In Progress",
    "escalated": "In Progress",
    "qa_failed": "In Progress",
}


async def _graphql_request(query: str, variables: dict) -> dict:
    """Execute a GitHub GraphQL query."""
    if not settings.hivemind_github_token:
        raise ValueError("HIVEMIND_GITHUB_TOKEN not configured")

    headers = {
        "Authorization": f"Bearer {settings.hivemind_github_token}",
        "Content-Type": "application/json",
    }
    # GraphQL endpoint is always api.github.com/graphql, even for GitHub Enterprise
    graphql_url = "https://api.github.com/graphql"
    if settings.hivemind_github_url != "https://api.github.com":
        # GitHub Enterprise
        base = settings.hivemind_github_url.rstrip("/")
        graphql_url = f"{base}/api/graphql"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            graphql_url,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise ValueError(f"GraphQL errors: {data['errors']}")
        return data.get("data", {})


async def sync_task_to_github(
    task_key: str,
    task_state: str,
    github_project_id: str,
    status_field_id: str,
    item_id: str,
) -> dict:
    """Update a GitHub Projects V2 item status to match Hivemind task state.

    Called by outbox consumer for direction='outbound', system='github'.
    """
    target_status = HIVEMIND_TO_GITHUB_STATUS.get(task_state, "Backlog")

    # First, get the option ID for the target status
    query = """
    query GetProjectField($projectId: ID!, $fieldId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          field(name: "Status") {
            ... on ProjectV2SingleSelectField {
              options {
                id
                name
              }
            }
          }
        }
      }
    }
    """
    # Simplified: use updateProjectV2ItemFieldValue mutation
    mutation = """
    mutation UpdateProjectItem($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId
        itemId: $itemId
        fieldId: $fieldId
        value: { singleSelectOptionId: $optionId }
      }) {
        projectV2Item {
          id
        }
      }
    }
    """

    try:
        # Get available options
        field_data = await _graphql_request(
            """query GetOptions($projectId: ID!) {
                node(id: $projectId) {
                    ... on ProjectV2 {
                        fields(first: 20) {
                            nodes {
                                ... on ProjectV2SingleSelectField {
                                    id
                                    name
                                    options { id name }
                                }
                            }
                        }
                    }
                }
            }""",
            {"projectId": github_project_id},
        )

        # Find the Status field and matching option
        option_id = None
        fields = field_data.get("node", {}).get("fields", {}).get("nodes", [])
        for field in fields:
            if field.get("name") == "Status":
                for opt in field.get("options", []):
                    if opt.get("name", "").lower() == target_status.lower():
                        option_id = opt["id"]
                        break
                break

        if not option_id:
            logger.warning("Could not find Status option '%s' in GitHub Project", target_status)
            return {"error": f"Status option '{target_status}' not found", "task_key": task_key}

        # Apply the update
        await _graphql_request(
            mutation,
            {
                "projectId": github_project_id,
                "itemId": item_id,
                "fieldId": status_field_id,
                "optionId": option_id,
            },
        )

        logger.info("GitHub Projects sync: task=%s → %s", task_key, target_status)
        return {"task_key": task_key, "github_status": target_status, "synced": True}

    except Exception as e:
        logger.error("GitHub Projects sync failed for %s: %s", task_key, e)
        return {"error": str(e), "task_key": task_key}


async def get_project_integration(project_id: str, db: Any) -> Any:
    """Get ProjectIntegration config for a project."""
    from sqlalchemy import select
    from app.models.project_integration import ProjectIntegration
    result = await db.execute(
        select(ProjectIntegration).where(
            ProjectIntegration.project_id == project_id,
            ProjectIntegration.integration_type == "github_projects",
            ProjectIntegration.sync_enabled == True,
        )
    )
    return result.scalar_one_or_none()

"""Task and Epic State Machine.

Erlaubte Transitionen gemäß docs/architecture/state-machine.md.
"""
from fastapi import HTTPException, status

# ─── Task State Machine ───────────────────────────────────────────────────────

# Mapping: current_state → set of valid next_states
TASK_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "incoming":    {"scoped", "cancelled"},
    "scoped":      {"ready", "cancelled"},
    "ready":       {"in_progress", "cancelled"},
    "in_progress": {"in_review", "blocked", "cancelled"},
    "in_review":   {"done", "qa_failed"},          # NOTE: cancelled NOT allowed from in_review
    "qa_failed":   {"in_progress", "escalated"},
    "blocked":     {"in_progress", "escalated", "cancelled"},
    "escalated":   {"in_progress", "cancelled"},
    "done":        set(),
    "cancelled":   set(),
}

# States from which only Admin can cancel
ADMIN_ONLY_CANCEL_STATES = {"incoming", "scoped", "ready", "in_progress", "blocked", "escalated"}


def validate_task_transition(current_state: str, new_state: str) -> None:
    """Raise HTTP 422 if the transition is not allowed."""
    allowed = TASK_ALLOWED_TRANSITIONS.get(current_state, set())
    if new_state not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Transition '{current_state}' → '{new_state}' ist nicht erlaubt. "
                f"Erlaubt: {sorted(allowed) or 'keine (Terminal-State)'}."
            ),
        )


def validate_review_gate(current_state: str, new_state: str) -> None:
    """Enforce Review-Gate: done only reachable from in_review."""
    if new_state == "done" and current_state != "in_review":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Review-Gate: 'done' ist nur aus 'in_review' erreichbar, "
                f"nicht aus '{current_state}'."
            ),
        )


def validate_qa_failed_count(current_state: str, requested_state: str, qa_failed_count: int) -> str:
    """
    If Worker tries in_progress from qa_failed but qa_failed_count >= 3,
    the system sets escalated instead of in_progress.
    Returns the effective new state.
    """
    if current_state == "qa_failed" and requested_state == "in_progress":
        if qa_failed_count >= 3:
            return "escalated"
    return requested_state


# ─── Epic State Machine ───────────────────────────────────────────────────────

EPIC_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "incoming":    {"scoped", "cancelled"},
    "scoped":      {"in_progress", "cancelled"},
    "in_progress": {"done", "cancelled"},
    "done":        set(),
    "cancelled":   set(),
}


def calculate_epic_state_after_task_transition(
    epic_state: str,
    new_task_state: str,
    all_task_states: list[str],
) -> str | None:
    """
    Returns the new Epic state if an auto-transition is triggered, else None.

    Rules (from state-machine.md — Epic Auto-Transition):
      - If new_task_state == 'in_progress' and epic.state == 'scoped' → 'in_progress'
      - If new_task_state in ('done', 'cancelled') and all tasks are done/cancelled
        and epic.state not 'cancelled' → 'done'
    """
    terminal = {"done", "cancelled"}

    if new_task_state == "in_progress" and epic_state == "scoped":
        return "in_progress"

    if new_task_state in terminal and epic_state not in terminal:
        if all(s in terminal for s in all_task_states):
            if epic_state != "cancelled":
                return "done"

    return None

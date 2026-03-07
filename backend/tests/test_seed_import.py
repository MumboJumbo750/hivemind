from scripts.seed_import import _normalize_seed_task_state


def test_normalize_seed_task_state_maps_open_to_incoming() -> None:
    assert _normalize_seed_task_state("open") == "incoming"


def test_normalize_seed_task_state_keeps_valid_runtime_states() -> None:
    assert _normalize_seed_task_state("in_progress") == "in_progress"
    assert _normalize_seed_task_state("qa_failed") == "qa_failed"


def test_normalize_seed_task_state_falls_back_to_incoming() -> None:
    assert _normalize_seed_task_state("todo") == "incoming"
    assert _normalize_seed_task_state(None) == "incoming"

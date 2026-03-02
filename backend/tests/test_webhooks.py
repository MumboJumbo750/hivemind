"""Unit tests for webhook normalizers."""

from app.routers.webhooks import _normalize_sentry


def test_normalize_sentry_prefers_issue_id_and_keeps_stacktrace_context() -> None:
    raw = {
        "project": {"slug": "core-api"},
        "data": {
            "issue": {
                "id": "ISSUE-42",
                "title": "Unhandled Exception",
                "firstSeen": "2026-03-01T10:00:00Z",
                "web_url": "https://sentry.local/issue/42",
            },
            "event": {
                "event_id": "0123456789abcdef0123456789abcdef",
                "title": "NullPointerException in AuthMiddleware",
                "message": "object is None",
                "culprit": "backend/app/auth.py",
                "level": "error",
                "fingerprint": ["{{ default }}", "NullPointerException"],
                "exception": {
                    "values": [
                        {
                            "stacktrace": {
                                "frames": [
                                    {
                                        "filename": "backend/app/auth.py",
                                        "function": "authenticate",
                                    }
                                ]
                            }
                        }
                    ]
                },
            },
        },
    }

    normalized = _normalize_sentry(raw)

    assert normalized["external_id"] == "ISSUE-42"
    assert normalized["issue_id"] == "ISSUE-42"
    assert normalized["event_id"] == "0123456789abcdef0123456789abcdef"
    assert normalized["project"] == "core-api"
    assert normalized["first_seen"] == "2026-03-01T10:00:00Z"
    assert normalized["fingerprint"] == ["{{ default }}", "NullPointerException"]
    assert normalized["stacktrace"]["frames"][0]["filename"] == "backend/app/auth.py"


def test_normalize_sentry_falls_back_to_event_id_when_issue_missing() -> None:
    raw = {
        "data": {
            "event": {
                "event_id": "abcdef0123456789abcdef0123456789",
                "title": "Error title",
                "level": "error",
            }
        }
    }

    normalized = _normalize_sentry(raw)

    assert normalized["external_id"] == "abcdef0123456789abcdef0123456789"
    assert normalized["issue_id"] is None
    assert normalized["event_id"] == "abcdef0123456789abcdef0123456789"

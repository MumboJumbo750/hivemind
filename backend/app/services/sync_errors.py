"""Common sync-related exceptions for outbound/inbound integrations."""


class PermanentSyncError(Exception):
    """Raised for non-retryable sync failures (for example HTTP 4xx responses)."""

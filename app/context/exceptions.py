"""Governed-context domain exceptions."""


class ContextNotFoundError(Exception):
    """The requested stable context identity does not exist."""


class ContextConflictError(Exception):
    """Multiple authoritative versions resolve for the requested time."""


class ContextIntegrityError(Exception):
    """A versioning, overlap, or immutability invariant was violated."""


class SeedConflictError(ContextIntegrityError):
    """Seed content conflicts with existing governed history."""


class ContextSafetyError(Exception):
    """Authoritative governed policy could not be bound to the engine."""

    def __init__(self, reason_code: str, safe_reason: str, correlation_id: str):
        super().__init__(safe_reason)
        self.code = "CONTEXT_NOT_AUTHORITATIVE"
        self.reason_code = reason_code
        self.safe_reason = safe_reason
        self.correlation_id = correlation_id

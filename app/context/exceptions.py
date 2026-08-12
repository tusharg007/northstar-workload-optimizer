"""Governed-context domain exceptions."""


class ContextNotFoundError(Exception):
    """The requested stable context identity does not exist."""


class ContextConflictError(Exception):
    """Multiple authoritative versions resolve for the requested time."""


class ContextIntegrityError(Exception):
    """A versioning, overlap, or immutability invariant was violated."""


class SeedConflictError(ContextIntegrityError):
    """Seed content conflicts with existing governed history."""
